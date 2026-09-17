from datetime import datetime, timezone
import time

import httpx

from .domain import Player, PlayerSnapshot


BASE = "https://statsapi.mlb.com/api/v1"


def _get_json(client: httpx.Client, url: str, params: dict) -> dict:
    for attempt in range(3):
        try:
            response = client.get(url, params=params, timeout=20)
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 2:
                raise
            time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError("Unreachable")


def _stats(client: httpx.Client, season: int, group: str, urls: list[str]) -> list[dict]:
    result: list[dict] = []
    offset = 0
    while True:
        url = f"{BASE}/stats"
        params = {"stats": "season", "group": group, "season": season, "sportIds": 1,
                  "playerPool": "ALL", "limit": 2000, "offset": offset}
        payload = _get_json(client, url, params)
        urls.append(str(httpx.URL(url, params=params)))
        stat_groups = payload.get("stats") or []
        rows = stat_groups[0].get("splits", []) if stat_groups else []
        result.extend(rows)
        if len(rows) < 2000:
            break
        offset += 2000
    return result


def fetch_player_snapshot(season: int, client: httpx.Client, *, fetched_at: datetime | None = None) -> PlayerSnapshot:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    url = f"{BASE}/sports/1/players"
    params = {"season": season}
    payload = _get_json(client, url, params)
    urls = [str(httpx.URL(url, params=params))]
    players: dict[int, Player] = {}
    for raw in payload.get("people", []):
        position = raw.get("primaryPosition", {}).get("abbreviation", "")
        players[raw["id"]] = Player(
            id=raw["id"], name=raw["fullName"], team=raw.get("currentTeam", {}).get("name", ""),
            primary_position=position, eligible_positions={position} if position else set(),
            is_two_way=position == "TWP",
        )
    for prior_season in (season - 2, season - 1):
        for group in ("hitting", "pitching", "fielding"):
            for row in _stats(client, prior_season, group, urls):
                player = players.get(row.get("player", {}).get("id"))
                if player is None:
                    continue
                stat = row.get("stat", {})
                if group == "hitting":
                    player.hitting[prior_season] = stat
                elif group == "pitching":
                    player.pitching[prior_season] = stat
                else:
                    position = row.get("position", {}).get("abbreviation", "")
                    player.fielding.setdefault(prior_season, []).append({"position": position, "stat": stat})
                    if position and int(stat.get("gamesStarted", 0) or 0) >= 5:
                        player.eligible_positions.add(position)
    for player in players.values():
        recent_hitting_pa = sum(float(str(stat.get("plateAppearances", 0) or 0).replace(",", ""))
                                for stat in player.hitting.values())
        recent_pitching_ip = sum(float(str(stat.get("inningsPitched", 0) or 0).replace(",", ""))
                                 for stat in player.pitching.values())
        recent_fielding_starts = sum(int(stat.get("gamesStarted", 0) or 0)
                                     for rows in player.fielding.values() for row in rows
                                     for stat in [row.get("stat", {})])
        if recent_hitting_pa >= 60 and recent_pitching_ip >= 20 and recent_fielding_starts >= 20:
            player.is_two_way = True
    return PlayerSnapshot(season=season, fetched_at=fetched_at, source_urls=urls, players=players)
