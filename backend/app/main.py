from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
import csv
import io
import os
from time import perf_counter
from typing import Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from pydantic import BaseModel, Field

from . import auth
from .demo import demo_data
from .mlb import fetch_player_snapshot
from .optimizer import Candidate, RosterRules, optimize_roster
from .salaries import MAX_SALARY_USD, load_salary_csv, salary_coverage
from .storage import (LiveDataPresent, NotOwner, VersionGone, delete_demo, delete_scenario, get_scenario, latest_salaries,
                      latest_snapshot, list_scenarios, save_demo, save_salaries, save_scenario, save_snapshot,
                      seasons_with_data, session)
from .domain import SalaryRecord
from .value import MODEL_VERSION, innings_pitched, project_values


DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "roster.db"
SCENARIO_SOLVE_BUDGET_SECONDS = 20.0
# Only these exact origins may call the API with the session cookie. Not "any localhost port": SameSite ignores
# ports, so any other local page (another dev server, a notebook) would otherwise read private rosters.
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def allowed_origins() -> list[str]:
    raw = os.environ.get("ROSTER_ALLOWED_ORIGINS", DEFAULT_ORIGINS)
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


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
    # MLB's image CDN serves the 2:3 studio portrait at any width, and d_people:generic
    # swaps in MLB's silhouette for players without a photo (verified 2026-09-27).
    # w_240 is 2.5x the 96px-wide card portrait. The old 60x60@2x file upscaled blurry.
    return (
        "https://img.mlbstatic.com/mlb-photos/image/upload/"
        f"d_people:generic:headshot:67:current.png/w_240,q_auto:best/v1/people/{pid}/headshot/67/current"
    )

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


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=auth.PASSWORD_MAX * 4)  # the length policy is checked in auth, with a clear message


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
            innings = sum(innings_pitched(stat) for stat in recent)
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
    origins = allowed_origins()
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    secure_cookies = os.environ.get("ROSTER_SECURE_COOKIES") == "1"  # set when served over HTTPS
    # Three login limits: per address+email (tight), per email alone (so faking the address does not reset it),
    # and per address across all emails (applied before any password hashing). The address is only trustworthy
    # when uvicorn runs with --no-proxy-headers; see README.
    login_limiter = auth.RateLimiter(limit=5, window_seconds=15 * 60)
    login_email_limiter = auth.RateLimiter(limit=20, window_seconds=15 * 60)
    login_ip_limiter = auth.RateLimiter(limit=50, window_seconds=15 * 60)
    register_limiter = auth.RateLimiter(limit=5, window_seconds=60 * 60)

    @app.middleware("http")
    async def reject_foreign_origins(request: Request, call_next):
        # Cookies make cross-site form posts a CSRF risk. Browsers send Origin on such requests, so a
        # state-changing request from any non-local origin is refused before it reaches a handler.
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            fetch_site = request.headers.get("sec-fetch-site")
            foreign = (origin is not None and origin.rstrip("/") not in origins) or \
                      (origin is None and fetch_site in ("cross-site", "same-site"))
            if foreign:
                return JSONResponse({"detail": {"code": "bad_origin", "message": "Cross-site request refused."}},
                                    status_code=403)
        return await call_next(request)

    def current_user(request: Request) -> auth.User | None:
        token = request.cookies.get(auth.SESSION_COOKIE)
        if not token:
            return None
        with session(db_path) as db:
            return auth.user_for_token(db, token)

    def require_user(user: auth.User | None = Depends(current_user)) -> auth.User:
        if user is None:
            raise HTTPException(401, detail={"code": "not_signed_in", "message": "Sign in first."})
        return user

    def _limit(limiter: auth.RateLimiter, key: str) -> None:
        wait = limiter.retry_after(key)
        if wait is not None:
            raise HTTPException(429, detail={"code": "rate_limited", "message": f"Too many attempts. Try again in {wait} s."},
                                headers={"Retry-After": str(wait)})

    def _start_session(response: Response, user: auth.User) -> dict:
        with session(db_path) as db:
            token = auth.create_session(db, user)
        response.set_cookie(auth.SESSION_COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True,
                            samesite="lax", secure=secure_cookies, path="/")
        return {"id": user.id, "email": user.email}

    def _client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    @app.post("/api/auth/register", status_code=201)
    def register(body: Credentials, request: Request, response: Response):
        _limit(register_limiter, _client_ip(request))
        try:
            with session(db_path) as db:
                user = auth.register(db, body.email, body.password)
        except auth.AuthError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from None
        return _start_session(response, user)

    @app.post("/api/auth/login")
    def login(body: Credentials, request: Request, response: Response):
        ip, email = _client_ip(request), body.email.strip().lower()
        key = f"{ip}|{email}"
        _limit(login_ip_limiter, ip)
        _limit(login_email_limiter, email)
        _limit(login_limiter, key)
        try:
            with session(db_path) as db:
                user = auth.authenticate(db, body.email, body.password)
        except auth.AuthError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from None
        login_limiter.reset(key)
        with session(db_path) as db:  # rotate: a session that existed before this login stops working
            auth.delete_session(db, request.cookies.get(auth.SESSION_COOKIE))
        return _start_session(response, user)

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        with session(db_path) as db:
            auth.delete_session(db, request.cookies.get(auth.SESSION_COOKIE))
        response.delete_cookie(auth.SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=secure_cookies)
        return {"message": "Signed out"}

    @app.get("/api/auth/me")
    def me(user: auth.User | None = Depends(current_user)):
        return {"id": user.id, "email": user.email} if user else None

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
        try:
            snapshot_id, salary_id = save_demo(db_path, snapshot, salaries)
        except LiveDataPresent:
            raise HTTPException(409, detail={"code": "live_data_present",
                                             "message": "Live player data is loaded; demo data would hide it."}) from None
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
        identifier = save_snapshot(db_path, snapshot)  # also replaces demo data for this season
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
        for pid in result.missing_player_ids:
            player = snapshot[1].players.get(pid)
            if player:
                missing.append({"id": player.id, "name": player.name, "team": player.team, "primary_position": player.primary_position})
        return {"priced_count": result.priced_count, "total_players": len(snapshot[1].players),
                "missing_player_ids": result.missing_player_ids, "missing_players": missing}

    @app.post("/api/scenarios")
    def create_scenario(request: ScenarioRequest, user: auth.User | None = Depends(current_user)):
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
        solve_deadline = perf_counter() + SCENARIO_SOLVE_BUDGET_SECONDS
        result = optimize_roster(candidates, RosterRules(), request.cap_usd,
                                 set(request.locked_ids), set(request.excluded_ids),
                                 deadline=solve_deadline)
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
        alternatives_truncated = False
        primary_ids = {pick["player_id"] for pick in roster["picks"]}
        locked_ids = set(request.locked_ids)
        avoid_ids = primary_ids - locked_ids
        for alt_cap in (round(request.cap_usd * 0.9), round(request.cap_usd * 1.1)):
            if perf_counter() >= solve_deadline:
                alternatives_truncated = True
                break
            alt = optimize_roster(candidates, RosterRules(), alt_cap,
                                  locked_ids, set(request.excluded_ids),
                                  avoid_ids=avoid_ids, deadline=solve_deadline)
            if alt.status == "timeout":
                alternatives_truncated = True
                break
            distinct = bool(avoid_ids) and alt.ok
            cap_cannot_fit_roster = (alt.status == "infeasible" and alt.code == "constraints"
                                     and alt.minimum_feasible_salary is not None
                                     and alt.minimum_feasible_salary > alt_cap)
            if not distinct and avoid_ids and not cap_cannot_fit_roster:
                if perf_counter() >= solve_deadline:
                    alternatives_truncated = True
                    break
                alt = optimize_roster(candidates, RosterRules(), alt_cap,
                                      locked_ids, set(request.excluded_ids),
                                      deadline=solve_deadline)
                if alt.status == "timeout":
                    alternatives_truncated = True
                    break
            if alt.ok:
                alternatives.append({"cap_usd": alt_cap, "roster": asdict(alt),
                                     "distinct_from_primary": distinct})
        coverage = salary_coverage(set(snapshot.players), salaries, request.season)
        payload = {"season": request.season, "cap_usd": request.cap_usd, "locked_ids": request.locked_ids,
                   "excluded_ids": request.excluded_ids, "roster": roster, "alternatives": alternatives,
                   "alternatives_truncated": alternatives_truncated, "is_demo": is_demo,
                   "model_version": MODEL_VERSION, "snapshot_at": snapshot.fetched_at.isoformat(),
                   "mlb_source_urls": snapshot.source_urls,
                   "salary_coverage": {"priced_count": coverage.priced_count,
                                       "total_players": len(snapshot.players),
                                       "missing_player_ids": coverage.missing_player_ids},
                   "salary_sources": sorted({record.source_url for record in salaries
                                             if record.player_id in {pick.player_id for pick in result.picks}})}
        try:
            # Signed in: the scenario is private to its owner. Anonymous: public, as before accounts existed.
            identifier = save_scenario(db_path, request.season, snapshot_id, salary_id, payload,
                                       owner_id=user.id if user else None)
        except VersionGone:
            raise HTTPException(409, detail={"code": "data_changed",
                                             "message": "Player or salary data changed while building. Build again."}) from None
        return dict(payload, id=identifier, snapshot_id=snapshot_id, salary_id=salary_id, owned_by_me=user is not None)

    @app.get("/api/scenarios")
    def scenarios(season: int | None = None, mine: bool = False, user: auth.User | None = Depends(current_user)):
        if mine and user is None:
            raise HTTPException(401, detail={"code": "not_signed_in", "message": "Sign in to see your saved rosters."})
        return list_scenarios(db_path, season, viewer_id=user.id if user else None, mine_only=mine)

    @app.delete("/api/scenarios/{identifier}", status_code=204)
    def remove_scenario(identifier: str, user: auth.User = Depends(require_user)):
        try:
            deleted = delete_scenario(db_path, identifier, user.id)
        except NotOwner:
            raise HTTPException(403, detail={"code": "public_scenario",
                                             "message": "Shared scenarios saved before accounts cannot be deleted."}) from None
        if not deleted:
            raise HTTPException(404, detail={"code": "not_found", "message": "Scenario not found"})
        return Response(status_code=204)

    @app.get("/api/scenarios/{identifier}")
    def scenario(identifier: str, user: auth.User | None = Depends(current_user)):
        result = get_scenario(db_path, identifier, viewer_id=user.id if user else None)
        if result is None:
            raise HTTPException(404, detail={"code": "not_found", "message": "Scenario not found"})
        # Presentation, not data: re-derive so scenarios saved with an older photo URL still render sharp.
        rosters = [result.get("roster"), *(alt.get("roster") for alt in result.get("alternatives") or [])]
        for pick in (pick for roster in rosters if roster for pick in roster.get("picks", [])):
            pick["headshot_url"] = _headshot_url(pick["player_id"])
        return result

    return app


app = create_app()
