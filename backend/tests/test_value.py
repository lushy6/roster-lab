from datetime import datetime, timezone

from app.domain import Player, PlayerSnapshot
from app.value import project_values


def snapshot(player: Player) -> PlayerSnapshot:
    return PlayerSnapshot(2026, datetime(2026, 9, 17, tzinfo=timezone.utc), [], {player.id: player})


def test_projection_ignores_target_season_stats():
    player = Player(10, "Hitter", "Club", "1B", {"1B"}, hitting={
        2024: {"plateAppearances": 600, "ops": ".700"},
        2025: {"plateAppearances": 600, "ops": ".800"},
        2026: {"plateAppearances": 600, "ops": "1.500"},
    })
    with_future = project_values(snapshot(player), 2026)[10]
    del player.hitting[2026]
    without_future = project_values(snapshot(player), 2026)[10]
    assert with_future.estimated_war == without_future.estimated_war
    assert with_future.input_seasons == [2024, 2025]


def test_small_sample_gets_less_value_and_high_uncertainty():
    full = Player(10, "Full", "Club", "1B", {"1B"}, hitting={2025: {"plateAppearances": 600, "ops": ".900"}})
    tiny = Player(11, "Tiny", "Club", "1B", {"1B"}, hitting={2025: {"plateAppearances": 30, "ops": ".900"}})
    result = project_values(PlayerSnapshot(2026, datetime.now(timezone.utc), [], {10: full, 11: tiny}), 2026)
    assert result[10].estimated_war > result[11].estimated_war
    assert result[11].uncertainty == "high"


def test_two_way_adds_hitting_and_pitching_once():
    player = Player(10, "Two Way", "Club", "TWP", {"DH", "P"},
                    hitting={2025: {"plateAppearances": 500, "ops": ".850"}},
                    pitching={2025: {"inningsPitched": "120.0", "era": "3.00"}}, is_two_way=True)
    value = project_values(snapshot(player), 2026)[10]
    assert value.hitting_war > 0
    assert value.pitching_war > 0
    assert value.estimated_war == round(value.hitting_war + value.pitching_war, 3)


def test_input_seasons_only_list_seasons_used_by_projection():
    player = Player(10, "Hitter", "Club", "1B", {"1B"}, hitting={
        2022: {"plateAppearances": 600, "ops": ".900"},
        2024: {"plateAppearances": 600, "ops": ".700"},
        2025: {"plateAppearances": 600, "ops": ".800"},
    })
    assert project_values(snapshot(player), 2026)[10].input_seasons == [2024, 2025]
