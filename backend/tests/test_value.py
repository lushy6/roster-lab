from datetime import datetime, timezone

from app.domain import Player, PlayerSnapshot
from app.value import innings_pitched, project_values


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


def test_a_single_season_is_not_penalised_for_the_missing_year():
    one = Player(10, "One", "Club", "1B", {"1B"}, hitting={2025: {"plateAppearances": 600, "ops": ".800"}})
    two = Player(11, "Two", "Club", "1B", {"1B"}, hitting={2024: {"plateAppearances": 600, "ops": ".800"},
                                                           2025: {"plateAppearances": 600, "ops": ".800"}})
    result = project_values(PlayerSnapshot(2026, datetime.now(timezone.utc), [], {10: one, 11: two}), 2026)
    assert result[10].estimated_war == result[11].estimated_war


def test_a_single_pitching_season_is_not_penalised_for_the_missing_year():
    one = Player(10, "One", "Club", "P", {"SP"}, pitching={2025: {"inningsPitched": "180.0", "era": "3.50"}})
    two = Player(11, "Two", "Club", "P", {"SP"}, pitching={2024: {"inningsPitched": "180.0", "era": "3.50"},
                                                           2025: {"inningsPitched": "180.0", "era": "3.50"}})
    result = project_values(PlayerSnapshot(2026, datetime.now(timezone.utc), [], {10: one, 11: two}), 2026)
    assert result[10].estimated_war == result[11].estimated_war


def test_recent_season_still_outweighs_the_older_one():
    improving = Player(10, "Up", "Club", "1B", {"1B"}, hitting={2024: {"plateAppearances": 600, "ops": ".700"},
                                                                2025: {"plateAppearances": 600, "ops": ".900"}})
    declining = Player(11, "Down", "Club", "1B", {"1B"}, hitting={2024: {"plateAppearances": 600, "ops": ".900"},
                                                                  2025: {"plateAppearances": 600, "ops": ".700"}})
    result = project_values(PlayerSnapshot(2026, datetime.now(timezone.utc), [], {10: improving, 11: declining}), 2026)
    assert result[10].estimated_war > result[11].estimated_war


def test_model_version_is_v3_after_innings_notation_fix():
    player = Player(10, "One", "Club", "1B", {"1B"}, hitting={2025: {"plateAppearances": 600, "ops": ".800"}})
    assert project_values(snapshot(player), 2026)[10].model_version == "war-proxy-v3"


def _war(position: str = "1B", **history):
    player = Player(1, "P", "Club", position, {position}, **history)
    return project_values(PlayerSnapshot(2026, datetime.now(timezone.utc), [], {1: player}), 2026)[1]


def _pa(pa: int) -> dict:
    return {"plateAppearances": pa, "ops": ".800"}


def test_a_player_who_missed_last_season_is_not_boosted_to_full_weight():
    missed = _war(hitting={2024: _pa(600)})
    barely_played = _war(hitting={2024: _pa(600), 2025: _pa(3)})
    full = _war(hitting={2024: _pa(600), 2025: _pa(600)})
    assert missed.estimated_war < full.estimated_war * 0.5
    assert abs(missed.estimated_war - barely_played.estimated_war) < 0.05  # no cliff between "no row" and "3 PA"
    assert missed.uncertainty != "low"


def test_a_zero_playing_time_row_counts_like_no_row():
    assert _war(hitting={2024: _pa(0), 2025: _pa(600)}).estimated_war == _war(hitting={2025: _pa(600)}).estimated_war
    assert _war(hitting={2024: _pa(600), 2025: _pa(0)}).estimated_war == _war(hitting={2024: _pa(600)}).estimated_war


def test_zero_playing_time_pitching_rows_are_ignored_too():
    real = {"inningsPitched": "150.0", "era": "3.50"}
    empty = {"inningsPitched": "0.0", "era": "-.--"}
    assert (_war("P", pitching={2024: empty, 2025: real}).estimated_war ==
            _war("P", pitching={2025: real}).estimated_war)


def test_input_seasons_leave_out_rows_without_playing_time():
    assert _war(hitting={2024: _pa(0), 2025: _pa(600)}).input_seasons == [2025]

def test_pitching_golden_uses_baseball_thirds_not_decimal_ip():
    # MLB's 180.2 means 180 innings plus two outs, or 180.667 IP; v3 updates this golden.
    result = _war("P", pitching={2025: {"inningsPitched": "180.2", "era": "3.50"}})
    assert round(innings_pitched("180.2"), 3) == 180.667
    assert round(innings_pitched({"outs": 542}), 3) == 180.667
    assert result.pitching_war == 3.108
    assert result.model_version == "war-proxy-v3"
