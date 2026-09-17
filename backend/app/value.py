from .domain import Player, PlayerSnapshot, ValueProjection


LEAGUE_OPS = 0.720
LEAGUE_ERA = 4.20
POSITION_WAR_600_PA = {"C": 1.25, "SS": 0.75, "2B": 0.25, "CF": 0.25,
                       "3B": 0.0, "RF": -0.25, "LF": -0.25, "1B": -0.75, "DH": -1.0}


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _recent(history: dict[int, dict], target_season: int) -> list[tuple[int, dict]]:
    return [(year, history[year]) for year in (target_season - 2, target_season - 1) if year in history]


def _hitting(player: Player, target_season: int) -> tuple[float, float]:
    recent = _recent(player.hitting, target_season)
    if not recent or player.primary_position == "P" and not player.is_two_way:
        return 0.0, 0.0
    weighted_pa = sum(_number(s.get("plateAppearances")) * (0.35 if year == target_season - 2 else 0.65)
                      for year, s in recent)
    projected_pa = min(650.0, weighted_pa)
    if projected_pa <= 0:
        return 0.0, 0.0
    rate_numerator = sum(_number(s.get("ops"), LEAGUE_OPS) * _number(s.get("plateAppearances"))
                         * (0.35 if year == target_season - 2 else 0.65) for year, s in recent)
    rate = (rate_numerator + LEAGUE_OPS * 200) / (weighted_pa + 200)
    position = "DH" if player.primary_position == "TWP" else player.primary_position
    positional = POSITION_WAR_600_PA.get(position, 0.0)
    # Approximate offensive runs from OPS gap, then add replacement and position runs.
    war = ((rate - LEAGUE_OPS) * projected_pa / 4 / 10) + (2 + positional) * projected_pa / 600
    return round(war, 3), weighted_pa


def _pitching(player: Player, target_season: int) -> tuple[float, float]:
    recent = _recent(player.pitching, target_season)
    if not recent:
        return 0.0, 0.0
    weighted_ip = sum(_number(s.get("inningsPitched")) * (0.35 if year == target_season - 2 else 0.65)
                      for year, s in recent)
    projected_ip = min(200.0, weighted_ip)
    if projected_ip <= 0:
        return 0.0, 0.0
    rate_numerator = sum(_number(s.get("era"), LEAGUE_ERA) * _number(s.get("inningsPitched"))
                         * (0.35 if year == target_season - 2 else 0.65) for year, s in recent)
    era = (rate_numerator + LEAGUE_ERA * 50) / (weighted_ip + 50)
    war = ((LEAGUE_ERA - era) * projected_ip / 9 / 10) + 2 * projected_ip / 180
    return round(war, 3), weighted_ip


def project_values(snapshot: PlayerSnapshot, target_season: int) -> dict[int, ValueProjection]:
    result = {}
    for player in snapshot.players.values():
        hitting_war, pa = _hitting(player, target_season)
        pitching_war, ip = _pitching(player, target_season)
        years = sorted({year for year in (*player.hitting, *player.pitching) if year < target_season})
        uncertainty = "high" if pa < 100 and ip < 30 else "medium" if pa < 300 and ip < 90 else "low"
        result[player.id] = ValueProjection(player.id, round(hitting_war + pitching_war, 3),
                                            hitting_war, pitching_war, uncertainty, years)
    return result
