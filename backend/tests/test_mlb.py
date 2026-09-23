from datetime import datetime, timezone

import httpx

from app.mlb import fetch_player_snapshot


def test_snapshot_combines_live_player_and_prior_stats():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/teams"):
            return httpx.Response(200, json={"teams": []})
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
        if request.url.path.endswith("/teams"):
            return httpx.Response(200, json={"teams": []})
        if request.url.path.endswith("/players"):
            return httpx.Response(200, json={"people": [{"id": 10, "fullName": "Player", "primaryPosition": {"abbreviation": "P"}}]})
        return httpx.Response(200, json={"stats": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    snapshot = fetch_player_snapshot(2026, client)
    assert snapshot.players[10].pitching == {}


def test_snapshot_identifies_two_way_player_from_recent_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/teams"):
            return httpx.Response(200, json={"teams": []})
        if request.url.path.endswith("/players"):
            return httpx.Response(200, json={"people": [{
                "id": 10, "fullName": "Two Way", "primaryPosition": {"abbreviation": "P"},
            }]})
        group = request.url.params["group"]
        if group == "hitting":
            return httpx.Response(200, json={"stats": [{"splits": [{
                "player": {"id": 10}, "stat": {"plateAppearances": 100, "gamesPlayed": 30},
            }]}]})
        if group == "pitching":
            return httpx.Response(200, json={"stats": [{"splits": [{
                "player": {"id": 10}, "stat": {"inningsPitched": "25.0", "gamesStarted": 2,
                "gamesPlayed": 12},
            }]}]})
        return httpx.Response(200, json={"stats": [{"splits": [{
            "player": {"id": 10}, "position": {"abbreviation": "RF"}, "stat": {"gamesStarted": 20},
        }]}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    snapshot = fetch_player_snapshot(2026, client)
    assert snapshot.players[10].is_two_way is True


def test_team_names_come_from_the_teams_list_when_a_player_only_carries_a_team_id():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/teams"):
            return httpx.Response(200, json={"teams": [{"id": 147, "name": "New York Yankees"},
                                                       {"id": 113, "name": "Cincinnati Reds"}]})
        if request.url.path.endswith("/players"):
            return httpx.Response(200, json={"people": [
                {"id": 1, "fullName": "Id Only", "primaryPosition": {"abbreviation": "RF"},
                 "currentTeam": {"id": 147, "link": "/api/v1/teams/147"}},
                {"id": 2, "fullName": "Has Name", "primaryPosition": {"abbreviation": "C"},
                 "currentTeam": {"id": 113, "name": "Cincinnati Reds"}},
                {"id": 3, "fullName": "Unknown Team", "primaryPosition": {"abbreviation": "CF"},
                 "currentTeam": {"id": 999, "link": "/api/v1/teams/999"}},
                {"id": 4, "fullName": "No Team", "primaryPosition": {"abbreviation": "1B"}},
            ]})
        return httpx.Response(200, json={"stats": []})

    snapshot = fetch_player_snapshot(2026, httpx.Client(transport=httpx.MockTransport(handler)))
    teams = {player.id: player.team for player in snapshot.players.values()}
    assert teams == {1: "New York Yankees", 2: "Cincinnati Reds", 3: "", 4: ""}
    assert any("/teams" in url for url in snapshot.source_urls)


def test_a_failing_teams_lookup_fails_the_refresh_instead_of_saving_teamless_players():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/teams"):
            return httpx.Response(500)
        return httpx.Response(200, json={"people": []})

    import pytest
    with pytest.raises(httpx.HTTPStatusError):
        fetch_player_snapshot(2026, httpx.Client(transport=httpx.MockTransport(handler)))
