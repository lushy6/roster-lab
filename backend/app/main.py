from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
import csv
import io
import os
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel, Field

from .demo import demo_data
from .mlb import fetch_player_snapshot
from .optimizer import Candidate, RosterRules, optimize_roster
from .salaries import MAX_SALARY_USD, load_salary_csv, salary_coverage
from .storage import (delete_demo, get_scenario, has_live_snapshot, latest_salaries, latest_snapshot,
                      list_scenarios, save_salaries, save_scenario, save_snapshot, seasons_with_data)
from .domain import SalaryRecord
from .value import MODEL_VERSION, project_values


DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "roster.db"


def default_db_path() -> Path:
    """`ROSTER_DB` lets tests and experiments use their own database instead of data/roster.db."""
    override = os.environ.get("ROSTER_DB")
    return Path(override) if override else DEFAULT_DB


TEAM_ABBREV = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC", "Chicago White Sox": "CWS", "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL", "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN", "New York Mets": "NYM", "New York Yankees": "NYY", "Oakland Athletics": "ATH",
    "Athletics": "ATH", "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SD",
    "San Francisco Giants": "SF", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL", "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR", "Washington Nationals": "WSH", "Fictional club": "FIC",
}

def _headshot_url(pid: int) -> str:
    # verified 200 for 660271, 669127 at 60x60@2x; larger crops require hash and 400 on direct ID — use content CDN
    return f"https://content.mlb.com/images/headshots/current/60x60/{pid}@2x.png"

def _team_logo_url(team: str) -> str | None:
    if not team or not team.strip():
        return None
    abbr = TEAM_ABBREV.get(team, "MLB")
    if abbr == "MLB":
        return None
    # ESPN CDN verified 200 for lad, ath, etc.
    return f"https://a3.espncdn.com/combiner/i?img=%2Fi%2Fteamlogos%2Fmlb%2F500%2F{abbr.lower()}.png&h=40&w=40"

def _stats_for_pick(player, season: int) -> dict:
    hitting = player.hitting.get(season - 1) or player.hitting.get(season - 2) or {}
    pitching = player.pitching.get(season - 1) or player.pitching.get(season - 2) or {}
    return {
        "ops": hitting.get("ops"),
        "avg": hitting.get("avg"),
        "hr": hitting.get("homeRuns"),
        "rbi": hitting.get("rbi"),
        "pa": hitting.get("plateAppearances"),
        "era": pitching.get("era"),
        "ip": pitching.get("inningsPitched"),
        "so": pitching.get("strikeOuts"),
        "whip": pitching.get("whip"),
    }


def _numeric(value: object) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


class ScenarioRequest(BaseModel):
    season: int = Field(ge=1900, le=2100)
    cap_usd: int = Field(gt=0, le=MAX_SALARY_USD)
    locked_ids: list[int] = Field(default_factory=list)
    excluded_ids: list[int] = Field(default_factory=list)


def _candidates(snapshot, salaries):
    values = project_values(snapshot, snapshot.season)
    salary_by_id = {record.player_id: record for record in salaries if record.season == snapshot.season}
    candidates = []
    for player in snapshot.players.values():
        salary = salary_by_id.get(player.id)
        if salary is None:
            continue
        positions = set(player.eligible_positions)
        if player.primary_position not in {"P"} and player.hitting:
            positions.add("DH")
        if player.primary_position == "P" or player.is_two_way:
            recent = list(player.pitching.values())
            starts = sum(int(stat.get("gamesStarted", 0) or 0) for stat in recent)
            games = sum(int(stat.get("gamesPlayed", 0) or 0) for stat in recent)
            innings = sum(_numeric(stat.get("inningsPitched", 0)) for stat in recent)
            has_pitching_history = games > 0 or innings > 0
            if has_pitching_history and starts >= 5:
                positions.add("SP")
            if has_pitching_history and (games == 0 or starts / games < 0.5):
                positions.add("RP")
        if player.is_two_way:
            positions.add("DH")
        candidates.append(Candidate(player.id, player.name, player.team, salary.base_salary_usd,
                                    values[player.id].estimated_war, positions, player.is_two_way))
    return candidates, values


def create_app(db_path: Path | None = None) -> FastAPI:
    db_path = db_path or default_db_path()
    app = FastAPI(title="Roster Lab API")
    # Local-only app: any localhost port may call it (dev server, preview, e2e on its own port).
    app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/status")
    def status(season: int = 2026):
        latest = latest_snapshot(db_path, season)
        salary = latest_salaries(db_path, season)
        coverage = salary_coverage(set(latest[1].players), salary[1], season) if latest and salary else None
        return {"season": season, "snapshot_id": latest[0] if latest else None,
                "snapshot_at": latest[1].fetched_at.isoformat() if latest else None,
                "salary_id": salary[0] if salary else None,
                "players": len(latest[1].players) if latest else 0,
                "priced_players": coverage.priced_count if coverage else 0,
                "is_demo": bool(latest and latest[2]),
                "model_version": MODEL_VERSION}

    @app.get("/api/seasons")
    def seasons():
        return seasons_with_data(db_path)

    @app.post("/api/demo/seed")
    def seed_demo():
        snapshot, salaries = demo_data()
        if has_live_snapshot(db_path, snapshot.season):
            raise HTTPException(409, detail={"code": "live_data_present",
                                             "message": "Live player data is loaded; demo data would hide it."})
        snapshot_id = save_snapshot(db_path, snapshot, is_demo=True)
        salary_id = save_salaries(db_path, 2026, salaries, is_demo=True)
        return {"snapshot_id": snapshot_id, "salary_id": salary_id, "players": len(snapshot.players),
                "message": "Fictional demo data loaded"}

    @app.delete("/api/demo")
    def exit_demo():
        delete_demo(db_path)
        return {"message": "Demo data removed"}

    @app.post("/api/refresh/mlb")
    def refresh_mlb(season: int = 2026):
        try:
            with httpx.Client() as client:
                snapshot = fetch_player_snapshot(season, client)
            if not snapshot.players:
                raise ValueError("MLB returned an empty player pool")
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, detail={"code": "refresh_failed", "message": str(exc)}) from exc
        identifier = save_snapshot(db_path, snapshot)
        delete_demo(db_path)  # live data supersedes any fictional data
        return {"snapshot_id": identifier, "players": len(snapshot.players), "fetched_at": snapshot.fetched_at}

    @app.post("/api/salaries/import")
    def import_salaries(season: int, csv_text: str = Body(media_type="text/csv"),
                        mode: Literal["merge", "replace"] = "merge"):
        current = latest_snapshot(db_path, season)
        if current and current[2]:
            raise HTTPException(409, detail={"code": "demo_active",
                                             "message": "Exit demo mode before importing real salaries."})
        with NamedTemporaryFile(mode="w", suffix=".csv", encoding="utf-8", delete=False) as file:
            file.write(csv_text)
            temp_path = Path(file.name)
        try:
            records, issues = load_salary_csv(temp_path)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_csv", "message": str(exc)}) from exc
        finally:
            os.unlink(temp_path)
        accepted = [record for record in records if record.season == season]
        if not accepted:
            raise HTTPException(422, detail={"code": "no_salaries", "message": "No valid salaries for this season"})
        if mode == "merge":
            # New rows win per player; everything else already on file is kept.
            existing = latest_salaries(db_path, season)
            kept = {record.player_id: record for record in existing[1]} if existing and not existing[2] else {}
            kept.update({record.player_id: record for record in accepted})
            accepted_all: list[SalaryRecord] = list(kept.values())
        else:
            accepted_all = accepted
        identifier = save_salaries(db_path, season, accepted_all)
        return {"salary_id": identifier, "accepted": len(accepted), "total": len(accepted_all), "mode": mode,
                "issues": [asdict(issue) for issue in issues]}

    @app.get("/api/salaries/template")
    def salary_template(season: int = 2026):
        snapshot_entry = latest_snapshot(db_path, season)
        if not snapshot_entry:
            raise HTTPException(404, detail={"code": "missing_players", "message": "Refresh players first"})
        salary_entry = latest_salaries(db_path, season)
        by_id = {record.player_id: record for record in salary_entry[1]} if salary_entry else {}
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["player_id", "player_name", "season", "base_salary_usd", "source_url", "checked_at", "reviewer_note"])
        for player in sorted(snapshot_entry[1].players.values(), key=lambda p: p.name):
            record = by_id.get(player.id)
            writer.writerow([player.id, player.name, season, record.base_salary_usd if record else "",
                             record.source_url if record else "", record.checked_at.isoformat() if record else "",
                             record.reviewer_note if record else ""])
        return Response(buffer.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="salary-template-{season}.csv"'})

    @app.get("/api/players")
    def players(season: int = 2026, q: str = "", limit: int = 12):
        snapshot_entry = latest_snapshot(db_path, season)
        if not snapshot_entry:
            raise HTTPException(404, detail={"code": "missing_players", "message": "Refresh players first"})
        _, snapshot, _ = snapshot_entry
        salary_entry = latest_salaries(db_path, season)
        salary_by_id = {r.player_id: r for r in salary_entry[1]} if salary_entry else {}
        values = project_values(snapshot, season)
        query = q.strip().lower()
        limit = max(1, min(50, limit))
        candidates = []
        for player in snapshot.players.values():
            if query and query not in player.name.lower() and query not in player.team.lower() and query not in str(player.id):
                continue
            salary = salary_by_id.get(player.id)
            value = values.get(player.id)
            stats = _stats_for_pick(player, season)
            team_abbrev = TEAM_ABBREV.get(player.team, "FA") if player.team else "FA"
            candidates.append({
                "id": player.id,
                "name": player.name,
                "team": player.team or "Free Agent",
                "team_abbrev": team_abbrev,
                "primary_position": player.primary_position,
                "eligible_positions": sorted(player.eligible_positions),
                "is_priced": salary is not None,
                "salary": salary.base_salary_usd if salary else None,
                "war": round(value.estimated_war, 2) if value else 0,
                "uncertainty": value.uncertainty if value else "high",
                "headshot_url": _headshot_url(player.id),
                "team_logo_url": _team_logo_url(player.team),
                "stats": stats,
            })
        candidates.sort(key=lambda x: (0 if x["is_priced"] else 1, -x["war"], x["name"]))
        return candidates[:limit]

    @app.get("/api/coverage")
    def coverage(season: int = 2026):
        snapshot = latest_snapshot(db_path, season)
        if not snapshot:
            raise HTTPException(404, detail={"code": "missing_players", "message": "Refresh players first"})
        salary = latest_salaries(db_path, season)  # before any import, everyone is simply unpriced
        result = salary_coverage(set(snapshot[1].players), salary[1] if salary else [], season)
        missing = []
        for pid in result.missing_player_ids[:200]:
            player = snapshot[1].players.get(pid)
            if player:
                missing.append({"id": player.id, "name": player.name, "team": player.team, "primary_position": player.primary_position})
        return {"priced_count": result.priced_count, "total_players": len(snapshot[1].players),
                "missing_player_ids": result.missing_player_ids, "missing_players": missing}

    @app.post("/api/scenarios")
    def create_scenario(request: ScenarioRequest):
        snapshot_entry = latest_snapshot(db_path, request.season)
        salary_entry = latest_salaries(db_path, request.season)
        if not snapshot_entry or not salary_entry:
            raise HTTPException(409, detail={"code": "missing_data", "message": "Refresh players and import salaries first"})
        snapshot_id, snapshot, is_demo = snapshot_entry
        salary_id, salaries, _ = salary_entry
        candidates, values = _candidates(snapshot, salaries)
        known_ids = {candidate.id for candidate in candidates}
        if set(request.locked_ids) - known_ids:
            raise HTTPException(422, detail={"code": "unknown_locked_player", "message": "A locked player has no salary or is outside this season"})
        if set(request.excluded_ids) - known_ids:
            raise HTTPException(422, detail={"code": "unknown_excluded_player", "message": "An excluded player has no salary or is outside this season"})
        result = optimize_roster(candidates, RosterRules(), request.cap_usd,
                                 set(request.locked_ids), set(request.excluded_ids))
        if result.status == "timeout":
            raise HTTPException(503, detail={"code": "solver_timeout", "message": result.reason})
        if result.status == "infeasible":
            raise HTTPException(422, detail={"code": "infeasible_roster", "message": result.reason,
                                             "minimum_feasible_salary": result.minimum_feasible_salary})
        roster = asdict(result)
        salary_by_id = {record.player_id: record for record in salaries}
        for pick in roster["picks"]:
            value = values[pick["player_id"]]
            salary_record = salary_by_id[pick["player_id"]]
            player = snapshot.players[pick["player_id"]]
            stats = _stats_for_pick(player, request.season)
            pick["uncertainty"] = value.uncertainty
            pick["input_seasons"] = value.input_seasons
            pick["hitting_war"] = value.hitting_war
            pick["pitching_war"] = value.pitching_war
            pick["salary_source_url"] = salary_record.source_url
            pick["salary_checked_at"] = salary_record.checked_at.isoformat()
            pick["salary_reviewer_note"] = salary_record.reviewer_note
            pick["headshot_url"] = _headshot_url(player.id)
            pick["team_logo_url"] = _team_logo_url(player.team)
            pick["team_abbrev"] = TEAM_ABBREV.get(player.team, "FA") if player.team else "FA"
            if not player.team:
                pick["team"] = "Free Agent"
            pick["stats"] = stats
        alternatives = []
        primary_ids = {pick["player_id"] for pick in roster["picks"]}
        locked_ids = set(request.locked_ids)
        avoid_ids = primary_ids - locked_ids
        for alt_cap in (round(request.cap_usd * 0.9), round(request.cap_usd * 1.1)):
            alt = optimize_roster(candidates, RosterRules(), alt_cap,
                                  locked_ids, set(request.excluded_ids),
                                  avoid_ids=avoid_ids)
            distinct = bool(avoid_ids) and alt.ok
            if not distinct:
                alt = optimize_roster(candidates, RosterRules(), alt_cap,
                                      locked_ids, set(request.excluded_ids))
            if alt.ok:
                alternatives.append({"cap_usd": alt_cap, "roster": asdict(alt),
                                     "distinct_from_primary": distinct})
        coverage = salary_coverage(set(snapshot.players), salaries, request.season)
        payload = {"season": request.season, "cap_usd": request.cap_usd, "locked_ids": request.locked_ids,
                   "excluded_ids": request.excluded_ids, "roster": roster, "alternatives": alternatives,
                   "is_demo": is_demo,
                   "model_version": MODEL_VERSION, "snapshot_at": snapshot.fetched_at.isoformat(),
                   "mlb_source_urls": snapshot.source_urls,
                   "salary_coverage": {"priced_count": coverage.priced_count,
                                       "total_players": len(snapshot.players),
                                       "missing_player_ids": coverage.missing_player_ids},
                   "salary_sources": sorted({record.source_url for record in salaries
                                             if record.player_id in {pick.player_id for pick in result.picks}})}
        identifier = save_scenario(db_path, request.season, snapshot_id, salary_id, payload)
        return dict(payload, id=identifier, snapshot_id=snapshot_id, salary_id=salary_id)

    @app.get("/api/scenarios")
    def scenarios(season: int | None = None):
        return list_scenarios(db_path, season)

    @app.get("/api/scenarios/{identifier}")
    def scenario(identifier: str):
        result = get_scenario(db_path, identifier)
        if result is None:
            raise HTTPException(404, detail={"code": "not_found", "message": "Scenario not found"})
        return result

    return app


app = create_app()
