from fastapi.testclient import TestClient
from datetime import date, datetime, timezone

from app.demo import demo_data
from app.domain import Player, PlayerSnapshot, SalaryRecord
from app.main import _candidates, create_app


def test_demo_scenario_is_saved_and_reopened(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    seed = client.post("/api/demo/seed")
    assert seed.status_code == 200
    assert seed.json()["players"] >= 52

    made = client.post("/api/scenarios", json={"season": 2026, "cap_usd": 150_000_000,
                                               "locked_ids": [], "excluded_ids": []})
    assert made.status_code == 200, made.text
    body = made.json()
    assert len(body["roster"]["picks"]) == 26
    assert body["roster"]["total_salary"] <= 150_000_000
    assert all(pick["salary_source_url"] for pick in body["roster"]["picks"])
    assert body["alternatives"]
    assert all(alt["roster"]["total_salary"] <= alt["cap_usd"] for alt in body["alternatives"])
    primary_ids = {pick["player_id"] for pick in body["roster"]["picks"]}
    assert any(alt.get("distinct_from_primary") and
               {pick["player_id"] for pick in alt["roster"]["picks"]} != primary_ids
               for alt in body["alternatives"])
    reopened = client.get(f"/api/scenarios/{body['id']}")
    assert reopened.status_code == 200
    assert reopened.json()["snapshot_id"] == body["snapshot_id"]
    assert reopened.json()["roster"]["picks"] == body["roster"]["picks"]


def test_impossible_demo_cap_has_structured_reason(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    client.post("/api/demo/seed")
    response = client.post("/api/scenarios", json={"season": 2026, "cap_usd": 1_000_000})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "infeasible_roster"
    assert response.json()["detail"]["minimum_feasible_salary"] > 1_000_000


def test_salary_csv_import_reports_invalid_rows(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    csv_text = ("player_id,season,base_salary_usd,source_url,checked_at\n"
                "10,2026,2000000,https://example.org/10,2026-09-17\n"
                "11,2026,3000000,,2026-09-17\n")
    response = client.post("/api/salaries/import?season=2026", content=csv_text,
                           headers={"content-type": "text/csv"})
    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    assert response.json()["issues"][0]["code"] == "missing_source"


def test_demo_starters_do_not_fill_bullpen_roles():
    snapshot, salaries = demo_data()
    candidates, _ = _candidates(snapshot, salaries)
    starter = next(candidate for candidate in candidates if candidate.name == "Demo SP 1")
    reliever = next(candidate for candidate in candidates if candidate.name == "Demo RP 1")
    assert "SP" in starter.eligible_positions
    assert "RP" not in starter.eligible_positions
    assert "RP" in reliever.eligible_positions
    assert "SP" not in reliever.eligible_positions


def test_unqualified_two_way_record_does_not_fill_pitching_slots():
    player = Player(10, "Hitter pitcher", "Club", "TWP", {"TWP"},
                    hitting={2025: {"plateAppearances": 500, "ops": ".850"}})
    snapshot = PlayerSnapshot(2026, datetime.now(timezone.utc), [], {10: player})
    candidates, _ = _candidates(snapshot, [SalaryRecord(10, 2026, 1_000_000,
                                                          "https://example.org/10", date(2026, 9, 17))])
    assert candidates[0].eligible_positions.isdisjoint({"SP", "RP"})


def test_salary_template_lists_player_ids_and_names(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    client.post("/api/demo/seed")
    response = client.get("/api/salaries/template?season=2026")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "player_id,player_name,season,base_salary_usd,source_url,checked_at" in response.text
    assert "Demo C 1" in response.text


def test_api_rejects_unknown_excluded_player_and_unbounded_cap(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    client.post("/api/demo/seed")
    unknown = client.post("/api/scenarios", json={"season": 2026, "cap_usd": 150_000_000,
                                                  "excluded_ids": [123456789]})
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "unknown_excluded_player"
    huge = client.post("/api/scenarios", json={"season": 2026, "cap_usd": 10**30})
    assert huge.status_code == 422


def test_saved_scenario_history_lists_recent_scenarios(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    client.post("/api/demo/seed")
    made = client.post("/api/scenarios", json={"season": 2026, "cap_usd": 150_000_000}).json()
    history = client.get("/api/scenarios?season=2026")
    assert history.status_code == 200
    assert history.json()[0]["id"] == made["id"]
    assert history.json()[0]["total_war"] == made["roster"]["total_war"]


def test_solver_timeout_surfaces_as_a_retryable_503(tmp_path, monkeypatch):
    import types
    from ortools.sat.python import cp_model
    from app import optimizer

    class Timeout:
        def __init__(self):
            self.parameters = types.SimpleNamespace()

        def solve(self, model):
            return cp_model.UNKNOWN

    client = TestClient(create_app(tmp_path / "test.db"))
    client.post("/api/demo/seed")
    monkeypatch.setattr(optimizer.cp_model, "CpSolver", Timeout)
    response = client.post("/api/scenarios", json={"season": 2026, "cap_usd": 150_000_000})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "solver_timeout"


def test_scenario_bench_picks_carry_their_slot_weight(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    client.post("/api/demo/seed")
    picks = client.post("/api/scenarios", json={"season": 2026, "cap_usd": 150_000_000}).json()["roster"]["picks"]
    weights = {pick["slot"]: pick["weight"] for pick in picks}
    assert weights["BN1"] == 0.25 and weights["C2"] == 0.25 and weights["SP1"] == 1.0 and weights["RP1"] == 1.0


def test_reopened_scenarios_use_the_current_headshot_url(tmp_path):
    # Scenarios saved before 2026-09-27 stored MLB's 60x60 headshot, which upscaled blurry.
    # The URL is a pure function of the player id, so reopening re-derives it.
    import json
    import sqlite3

    db_path = tmp_path / "test.db"
    client = TestClient(create_app(db_path))
    client.post("/api/demo/seed")
    made = client.post("/api/scenarios", json={"season": 2026, "cap_usd": 150_000_000,
                                               "locked_ids": [], "excluded_ids": []}).json()
    with sqlite3.connect(db_path) as db:
        payload = json.loads(db.execute("SELECT payload FROM scenarios WHERE id=?", (made["id"],)).fetchone()[0])
        rosters = [payload["roster"], *(alt["roster"] for alt in payload["alternatives"])]
        for pick in (pick for roster in rosters for pick in roster["picks"]):
            pick["headshot_url"] = f"https://content.mlb.com/images/headshots/current/60x60/{pick['player_id']}@2x.png"
        db.execute("UPDATE scenarios SET payload=? WHERE id=?", (json.dumps(payload), made["id"]))

    reopened = client.get(f"/api/scenarios/{made['id']}").json()

    rosters = [reopened["roster"], *(alt["roster"] for alt in reopened["alternatives"])]
    picks = [pick for roster in rosters for pick in roster["picks"]]
    assert picks
    for pick in picks:
        assert pick["headshot_url"].startswith("https://img.mlbstatic.com/mlb-photos/image/upload/")
        assert f"/people/{pick['player_id']}/headshot/67/current" in pick["headshot_url"]
