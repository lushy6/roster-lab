from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
import os

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel, Field

from .demo import demo_data
from .mlb import fetch_player_snapshot
from .optimizer import Candidate, RosterRules, optimize_roster
from .salaries import load_salary_csv, salary_coverage
from .storage import (get_scenario, latest_salaries, latest_snapshot, save_salaries,
                      save_scenario, save_snapshot)
from .value import project_values


DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "roster.db"


class ScenarioRequest(BaseModel):
    season: int = Field(ge=1900, le=2100)
    cap_usd: int = Field(gt=0)
    locked_ids: list[int] = []
    excluded_ids: list[int] = []


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
            if starts or not games:
                positions.add("SP")
            if games > starts or not games:
                positions.add("RP")
        if player.is_two_way:
            positions.add("DH")
        candidates.append(Candidate(player.id, player.name, player.team, salary.base_salary_usd,
                                    values[player.id].estimated_war, positions, player.is_two_way))
    return candidates, values


def create_app(db_path: Path = DEFAULT_DB) -> FastAPI:
    app = FastAPI(title="Roster Lab API")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
                "model_version": "war-proxy-v1"}

    @app.post("/api/demo/seed")
    def seed_demo():
        snapshot, salaries = demo_data()
        snapshot_id = save_snapshot(db_path, snapshot, is_demo=True)
        salary_id = save_salaries(db_path, 2026, salaries, is_demo=True)
        return {"snapshot_id": snapshot_id, "salary_id": salary_id, "players": len(snapshot.players),
                "message": "Fictional demo data loaded"}

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
        return {"snapshot_id": identifier, "players": len(snapshot.players), "fetched_at": snapshot.fetched_at}

    @app.post("/api/salaries/import")
    def import_salaries(season: int, csv_text: str = Body(media_type="text/csv")):
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
        identifier = save_salaries(db_path, season, accepted)
        return {"salary_id": identifier, "accepted": len(accepted), "issues": [asdict(issue) for issue in issues]}

    @app.get("/api/coverage")
    def coverage(season: int = 2026):
        snapshot = latest_snapshot(db_path, season)
        salary = latest_salaries(db_path, season)
        if not snapshot or not salary:
            raise HTTPException(404, detail={"code": "missing_data", "message": "Refresh players and import salaries first"})
        result = salary_coverage(set(snapshot[1].players), salary[1], season)
        return {"priced_count": result.priced_count, "total_players": len(snapshot[1].players),
                "missing_player_ids": result.missing_player_ids}

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
        result = optimize_roster(candidates, RosterRules(), request.cap_usd,
                                 set(request.locked_ids), set(request.excluded_ids))
        if result.status == "infeasible":
            raise HTTPException(422, detail={"code": "infeasible_roster", "message": result.reason,
                                             "minimum_feasible_salary": result.minimum_feasible_salary})
        roster = asdict(result)
        salary_by_id = {record.player_id: record for record in salaries}
        for pick in roster["picks"]:
            value = values[pick["player_id"]]
            salary_record = salary_by_id[pick["player_id"]]
            pick["uncertainty"] = value.uncertainty
            pick["input_seasons"] = value.input_seasons
            pick["hitting_war"] = value.hitting_war
            pick["pitching_war"] = value.pitching_war
            pick["salary_source_url"] = salary_record.source_url
            pick["salary_checked_at"] = salary_record.checked_at.isoformat()
        alternatives = []
        selected_ids = {pick.player_id for pick in result.picks}
        for alt_cap in (round(request.cap_usd * 0.9), round(request.cap_usd * 1.1)):
            alt = optimize_roster(candidates, RosterRules(), alt_cap,
                                  set(request.locked_ids), set(request.excluded_ids))
            if alt.status != "infeasible" and {pick.player_id for pick in alt.picks} != selected_ids:
                alternatives.append({"cap_usd": alt_cap, "roster": asdict(alt)})
        payload = {"season": request.season, "cap_usd": request.cap_usd, "locked_ids": request.locked_ids,
                   "excluded_ids": request.excluded_ids, "roster": roster, "alternatives": alternatives,
                   "is_demo": is_demo,
                   "model_version": "war-proxy-v1", "snapshot_at": snapshot.fetched_at.isoformat(),
                   "salary_sources": sorted({record.source_url for record in salaries
                                             if record.player_id in {pick.player_id for pick in result.picks}})}
        identifier = save_scenario(db_path, request.season, snapshot_id, salary_id, payload)
        return dict(payload, id=identifier, snapshot_id=snapshot_id, salary_id=salary_id)

    @app.get("/api/scenarios/{identifier}")
    def scenario(identifier: str):
        result = get_scenario(db_path, identifier)
        if result is None:
            raise HTTPException(404, detail={"code": "not_found", "message": "Scenario not found"})
        return result

    return app


app = create_app()
