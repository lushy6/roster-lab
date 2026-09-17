from fastapi.testclient import TestClient

from app.main import create_app


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
