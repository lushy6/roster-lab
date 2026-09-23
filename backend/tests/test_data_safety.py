"""Guards for real data: demo mode must never shadow it, imports must not wipe it."""
from datetime import date, datetime, timezone
import sqlite3

from fastapi.testclient import TestClient

from app import main as app_main
from app.domain import Player, PlayerSnapshot, SalaryRecord
from app.main import create_app
from app.storage import KEEP_VERSIONS, latest_salaries, save_salaries, save_scenario, save_snapshot


def live_snapshot(season: int = 2026, player_id: int = 1) -> PlayerSnapshot:
    players = {player_id: Player(player_id, f"Live {player_id}", "Club", "1B", {"1B"})}
    return PlayerSnapshot(season, datetime.now(timezone.utc), ["https://statsapi.mlb.com/x"], players)


def salary(player_id: int, amount: int = 5_000_000, season: int = 2026) -> SalaryRecord:
    return SalaryRecord(player_id, season, amount, f"https://example.org/{player_id}", date(2026, 9, 17))


def seed_live(db_path, season: int = 2026):
    snapshot_id = save_snapshot(db_path, live_snapshot(season))
    salary_id = save_salaries(db_path, season, [salary(1, season=season)])
    return snapshot_id, salary_id


def count(db_path, table: str, where: str = "1=1") -> int:
    with sqlite3.connect(db_path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]


CSV_HEADER = "player_id,season,base_salary_usd,source_url,checked_at\n"


def test_roster_db_env_var_selects_the_database(tmp_path, monkeypatch):
    target = tmp_path / "env.db"
    monkeypatch.setenv("ROSTER_DB", str(target))
    client = TestClient(create_app())
    assert client.get("/api/status").status_code == 200
    assert target.exists()


def test_demo_seed_refuses_to_shadow_live_data(tmp_path):
    db = tmp_path / "test.db"
    seed_live(db)
    client = TestClient(create_app(db))
    response = client.post("/api/demo/seed")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "live_data_present"
    status = client.get("/api/status").json()
    assert status["players"] == 1 and status["is_demo"] is False


def test_demo_seed_is_idempotent_and_can_be_exited(tmp_path):
    db = tmp_path / "test.db"
    client = TestClient(create_app(db))
    client.post("/api/demo/seed")
    client.post("/api/demo/seed")
    assert count(db, "snapshots", "is_demo=1") == 1
    assert count(db, "salaries", "is_demo=1") == 1
    assert client.get("/api/status").json()["is_demo"] is True
    assert client.delete("/api/demo").status_code == 200
    status = client.get("/api/status").json()
    assert status["players"] == 0 and status["is_demo"] is False


def test_live_refresh_supersedes_demo_data(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    client = TestClient(create_app(db))
    client.post("/api/demo/seed")
    monkeypatch.setattr(app_main, "fetch_player_snapshot", lambda season, http: live_snapshot(season))
    assert client.post("/api/refresh/mlb?season=2026").status_code == 200
    status = client.get("/api/status").json()
    assert status["is_demo"] is False and status["players"] == 1
    assert count(db, "snapshots", "is_demo=1") == 0
    assert count(db, "salaries", "is_demo=1") == 0


def test_salary_import_is_refused_while_demo_is_active(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    client.post("/api/demo/seed")
    response = client.post("/api/salaries/import?season=2026",
                           content=CSV_HEADER + "1,2026,1000000,https://example.org/1,2026-09-17\n",
                           headers={"content-type": "text/csv"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "demo_active"


def test_salary_import_merges_by_default_and_replace_is_explicit(tmp_path):
    db = tmp_path / "test.db"
    seed_live(db)
    client = TestClient(create_app(db))
    row = CSV_HEADER + "2,2026,2000000,https://example.org/2,2026-09-17\n"
    merged = client.post("/api/salaries/import?season=2026", content=row, headers={"content-type": "text/csv"})
    assert merged.status_code == 200
    assert merged.json()["accepted"] == 1 and merged.json()["total"] == 2
    assert {r.player_id for r in latest_salaries(db, 2026)[1]} == {1, 2}
    replaced = client.post("/api/salaries/import?season=2026&mode=replace", content=row,
                           headers={"content-type": "text/csv"})
    assert replaced.json()["total"] == 1
    assert {r.player_id for r in latest_salaries(db, 2026)[1]} == {2}


def test_merge_lets_new_rows_override_existing_salaries(tmp_path):
    db = tmp_path / "test.db"
    seed_live(db)
    client = TestClient(create_app(db))
    client.post("/api/salaries/import?season=2026", headers={"content-type": "text/csv"},
                content=CSV_HEADER + "1,2026,9000000,https://example.org/new,2026-09-18\n")
    records = {r.player_id: r for r in latest_salaries(db, 2026)[1]}
    assert records[1].base_salary_usd == 9_000_000 and len(records) == 1


def test_import_rejects_unknown_mode(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    response = client.post("/api/salaries/import?season=2026&mode=nuke", headers={"content-type": "text/csv"},
                           content=CSV_HEADER + "1,2026,1000000,https://example.org/1,2026-09-17\n")
    assert response.status_code == 422


def test_old_snapshots_and_salaries_are_pruned(tmp_path):
    db = tmp_path / "test.db"
    for _ in range(KEEP_VERSIONS + 4):
        save_snapshot(db, live_snapshot())
        save_salaries(db, 2026, [salary(1)])
    assert count(db, "snapshots") == KEEP_VERSIONS
    assert count(db, "salaries") == KEEP_VERSIONS


def test_versions_referenced_by_a_scenario_survive_pruning(tmp_path):
    db = tmp_path / "test.db"
    pinned_snapshot = save_snapshot(db, live_snapshot())
    pinned_salary = save_salaries(db, 2026, [salary(1)])
    save_scenario(db, 2026, pinned_snapshot, pinned_salary, {"roster": {}})
    for _ in range(KEEP_VERSIONS + 3):
        save_snapshot(db, live_snapshot())
        save_salaries(db, 2026, [salary(1)])
    assert count(db, "snapshots", f"id='{pinned_snapshot}'") == 1
    assert count(db, "salaries", f"id='{pinned_salary}'") == 1


def test_pruning_is_scoped_to_season_and_real_data(tmp_path):
    db = tmp_path / "test.db"
    other = save_snapshot(db, live_snapshot(season=2025))
    for _ in range(KEEP_VERSIONS + 2):
        save_snapshot(db, live_snapshot(season=2026))
    assert count(db, "snapshots", f"id='{other}'") == 1


def test_seasons_endpoint_lists_only_seasons_with_players_and_salaries(tmp_path):
    db = tmp_path / "test.db"
    seed_live(db, season=2026)
    save_snapshot(db, live_snapshot(season=2025))  # players but no salaries
    client = TestClient(create_app(db))
    assert client.get("/api/seasons").json() == [2026]


def test_seasons_endpoint_is_empty_on_a_fresh_database(tmp_path):
    assert TestClient(create_app(tmp_path / "test.db")).get("/api/seasons").json() == []


def test_cors_allows_any_localhost_port_but_not_lookalike_hosts(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    def allowed(origin: str) -> str | None:
        return client.get("/api/status", headers={"Origin": origin}).headers.get("access-control-allow-origin")
    assert allowed("http://127.0.0.1:5183") == "http://127.0.0.1:5183"
    assert allowed("http://localhost:5173") == "http://localhost:5173"
    assert allowed("http://localhost.evil.example") is None
    assert allowed("https://127.0.0.1:5173") is None
