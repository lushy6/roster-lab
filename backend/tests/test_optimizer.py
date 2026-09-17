from app.optimizer import Candidate, RosterRules, optimize_roster, validate_roster
from app.demo import demo_data
from app.main import _candidates


def test_exact_solver_beats_value_per_dollar_greedy_choice():
    rules = RosterRules(slots=("1B", "DH"), require_bench_catcher=False)
    players = [
        Candidate(1, "Cheap", "A", 3_000_000, 5.0, {"1B", "DH"}),
        Candidate(2, "Middle", "B", 5_000_000, 7.0, {"1B", "DH"}),
        Candidate(3, "Other", "C", 5_000_000, 7.0, {"1B", "DH"}),
    ]
    result = optimize_roster(players, rules, 10_000_000)
    assert {pick.player_id for pick in result.picks} == {2, 3}
    assert result.total_war == 14.0
    assert validate_roster(result, rules, 10_000_000) == []


def test_impossible_cap_returns_cheapest_valid_cost():
    rules = RosterRules(slots=("C", "1B"), require_bench_catcher=False)
    players = [Candidate(1, "C", "A", 2_000_000, 2.0, {"C"}),
               Candidate(2, "1B", "A", 3_000_000, 3.0, {"1B"})]
    result = optimize_roster(players, rules, 4_000_000)
    assert result.status == "infeasible"
    assert result.minimum_feasible_salary == 5_000_000


def test_two_way_player_counts_once_for_roster_and_salary():
    rules = RosterRules(slots=("DH", "SP1"), require_bench_catcher=False)
    players = [Candidate(1, "Two Way", "A", 4_000_000, 5.0, {"DH", "SP"}, is_two_way=True),
               Candidate(2, "Starter", "B", 3_000_000, 2.0, {"SP"}),
               Candidate(3, "DH", "C", 3_000_000, 1.0, {"DH"})]
    result = optimize_roster(players, rules, 7_000_000)
    assert len({pick.player_id for pick in result.picks}) == 2
    assert result.total_salary == 7_000_000
    assert validate_roster(result, rules, 7_000_000) == []


def test_locks_and_exclusions_change_selected_players():
    rules = RosterRules(slots=("DH",), require_bench_catcher=False)
    players = [Candidate(1, "Best", "A", 1_000_000, 5.0, {"DH"}),
               Candidate(2, "Other", "B", 1_000_000, 1.0, {"DH"})]
    assert optimize_roster(players, rules, 2_000_000).picks[0].player_id == 1
    assert optimize_roster(players, rules, 2_000_000, excluded_ids={1}).picks[0].player_id == 2
    assert optimize_roster(players, rules, 2_000_000, locked_ids={2}).picks[0].player_id == 2


def test_validator_rejects_duplicate_player_even_when_slots_filled():
    rules = RosterRules(slots=("DH", "1B"), require_bench_catcher=False)
    result = optimize_roster([Candidate(1, "Only", "A", 1_000_000, 2.0, {"DH", "1B"}),
                              Candidate(2, "Other", "A", 1_000_000, 1.0, {"DH", "1B"})], rules, 2_000_000)
    result.picks[1] = result.picks[1].__class__(result.picks[0].player_id, result.picks[1].name,
                                                result.picks[1].team, result.picks[1].slot,
                                                result.picks[1].salary, result.picks[1].war, False)
    assert "A player fills multiple slots" in validate_roster(result, rules, 2_000_000)


def test_demo_pool_reaches_proven_optimum():
    snapshot, salaries = demo_data()
    candidates, _ = _candidates(snapshot, salaries)
    result = optimize_roster(candidates, RosterRules(), 150_000_000)
    assert result.status == "optimal"
