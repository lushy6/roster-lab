from datetime import datetime, timezone

import httpx

from app.mlb import fetch_player_snapshot


def test_snapshot_combines_live_player_and_prior_stats():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/players"):
            return httpx.Response(200, json={"people": [
                {"id": 10, "fullName": "A Catcher", "primaryPosition": {"abbreviation": "C"}, "currentTeam": {"name": "Club"}},
                {"id": 20, "fullName": "A Pitcher", "primaryPosition": {"abbreviation": "P"}, "currentTeam": {"name": "Club"}},
            ]})
        group = request.url.params["group"]
        if group == "fielding":
            return httpx.Response(200, json={"stats": [{"splits": [
                {"player": {"id": 10}, "position": {"abbreviation": "C"}, "stat": {"gamesStarted": 40}},
                {"player": {"id": 10}, "position": {"abbreviation": "1B"}, "stat": {"gamesStarted": 8}},
            ]}]})
        return httpx.Response(200, json={"stats": [{"splits": [
            {"player": {"id": 10 if group == "hitting" else 20}, "stat": {"gamesPlayed": 80, "plateAppearances": 300, "inningsPitched": "50.0", "ops": ".750", "era": "3.50"}}
        ]}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    at = datetime(2026, 9, 17, tzinfo=timezone.utc)
    snapshot = fetch_player_snapshot(2026, client, fetched_at=at)
    assert len(snapshot.players) == 2
    assert snapshot.players[10].eligible_positions == {"C", "1B"}
    assert snapshot.players[10].hitting[2025]["plateAppearances"] == 300
    assert snapshot.players[20].pitching[2025]["era"] == "3.50"
    assert snapshot.fetched_at == at
    assert any("/sports/1/players" in url for url in calls)


def test_snapshot_handles_a_season_with_no_stats_group():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/players"):
            return httpx.Response(200, json={"people": [{"id": 10, "fullName": "Player", "primaryPosition": {"abbreviation": "P"}}]})
        return httpx.Response(200, json={"stats": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    snapshot = fetch_player_snapshot(2026, client)
    assert snapshot.players[10].pitching == {}
