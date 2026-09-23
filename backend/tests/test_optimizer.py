import time
import types

from ortools.sat.python import cp_model

from app import optimizer
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


def test_validator_catches_wrong_position_assignment():
    rules = RosterRules(slots=("C",), require_bench_catcher=False)
    candidate = Candidate(1, "Catcher", "A", 1_000_000, 1.0, {"C"})
    result = optimize_roster([candidate], rules, 2_000_000)
    result.picks[0] = result.picks[0].__class__(1, "Catcher", "A", "1B", 1_000_000, 1.0, False)
    assert "Player 1 is not eligible for 1B" in validate_roster(result, rules, 2_000_000, [candidate])


def test_bench_catcher_requirement_is_enforced_for_custom_bench_slots():
    rules = RosterRules(slots=("1B", "BN1"), require_bench_catcher=True)
    players = [Candidate(1, "First", "A", 1_000_000, 2.0, {"1B"}),
               Candidate(2, "Bench bat", "B", 1_000_000, 1.5, {"DH"})]
    result = optimize_roster(players, rules, 2_000_000)
    assert result.status == "infeasible"


def test_catcher_can_fill_the_explicit_c2_slot():
    rules = RosterRules(slots=("C", "C2"), require_bench_catcher=True)
    players = [Candidate(1, "Catcher one", "A", 1_000_000, 2.0, {"C"}),
               Candidate(2, "Catcher two", "B", 1_000_000, 1.0, {"C"})]
    result = optimize_roster(players, rules, 2_000_000)
    assert result.status == "optimal"
    assert {pick.slot for pick in result.picks} == {"C", "C2"}


def test_bench_and_backup_catcher_slots_count_a_fraction_of_a_players_value():
    rules = RosterRules(slots=("1B", "BN1"), require_bench_catcher=False)
    players = [Candidate(1, "Star", "A", 1_000_000, 5.0, {"1B"}),
               Candidate(2, "Depth", "B", 1_000_000, 3.0, {"1B"})]
    result = optimize_roster(players, rules, 2_000_000)
    by_slot = {pick.slot: pick for pick in result.picks}
    assert by_slot["1B"].player_id == 1 and by_slot["BN1"].player_id == 2
    assert by_slot["1B"].weight == 1.0 and by_slot["BN1"].weight == 0.25
    assert by_slot["BN1"].war == 3.0  # the player's own estimate is untouched
    assert result.total_war == 5.75
    assert validate_roster(result, rules, 2_000_000) == []


def test_the_better_catcher_takes_the_starting_slot():
    rules = RosterRules(slots=("C", "C2"), require_bench_catcher=False)
    players = [Candidate(1, "Backup", "A", 1_000_000, 1.0, {"C"}), Candidate(2, "Starter", "B", 1_000_000, 4.0, {"C"})]
    by_slot = {pick.slot: pick.player_id for pick in optimize_roster(players, rules, 2_000_000).picks}
    assert by_slot == {"C": 2, "C2": 1}


def test_validator_rejects_a_wrong_slot_weight():
    rules = RosterRules(slots=("1B", "BN1"), require_bench_catcher=False)
    players = [Candidate(1, "Star", "A", 1_000_000, 5.0, {"1B"}), Candidate(2, "Depth", "B", 1_000_000, 3.0, {"1B"})]
    result = optimize_roster(players, rules, 2_000_000)
    bench = next(pick for pick in result.picks if pick.slot == "BN1")
    result.picks[result.picks.index(bench)] = bench.__class__(bench.player_id, bench.name, bench.team, bench.slot,
                                                              bench.salary, bench.war, bench.is_two_way, 1.0)
    assert "Slot weight is incorrect" in validate_roster(result, rules, 2_000_000)


class _TimedOutSolver:
    def __init__(self):
        self.parameters = types.SimpleNamespace()

    def solve(self, model):
        return cp_model.UNKNOWN


def test_solver_timeout_is_not_reported_as_infeasible(monkeypatch):
    monkeypatch.setattr(optimizer.cp_model, "CpSolver", _TimedOutSolver)
    rules = RosterRules(slots=("DH",), require_bench_catcher=False)
    result = optimize_roster([Candidate(1, "Only", "A", 1_000_000, 1.0, {"DH"})], rules, 2_000_000)
    assert result.status == "timeout"
    assert result.minimum_feasible_salary is None
    assert "limit" in result.reason


def test_a_genuinely_infeasible_cap_is_still_infeasible_with_a_cheapest_cost():
    rules = RosterRules(slots=("DH",), require_bench_catcher=False)
    result = optimize_roster([Candidate(1, "Only", "A", 3_000_000, 1.0, {"DH"})], rules, 1_000_000)
    assert result.status == "infeasible" and result.minimum_feasible_salary == 3_000_000


def test_solver_scales_to_a_league_sized_pool():
    pool = []
    for i in range(1, 1201):
        hitters = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
        positions = {hitters[(i // 3) % 9]} if i % 3 else {("SP", "RP")[i % 2]}
        pool.append(Candidate(i, f"P{i}", "T", 700_000 + (i * 37_000) % 30_000_000, ((i * 7919) % 500) / 100, positions))
    started = time.perf_counter()
    result = optimize_roster(pool, RosterRules(), 220_000_000)
    assert result.status in {"optimal", "feasible"}
    assert time.perf_counter() - started < 20


def test_slot_weights_change_which_players_are_chosen_not_just_the_labels():
    # Unweighted, B + C (9.0 WAR) beats A + B (8.0). Weighted, C on the bench only counts
    # 1.5, so paying for A at first base wins (5.0 + 0.25 * 3.0 = 5.75 vs 3.0 + 0.25 * 6.0 = 4.5).
    players = [Candidate(1, "A", "X", 10_000_000, 5.0, {"1B"}),
               Candidate(2, "B", "X", 2_000_000, 3.0, {"1B"}),
               Candidate(3, "C", "X", 10_000_000, 6.0, {"DH"})]
    slots = ("1B", "BN1")
    weighted = optimize_roster(players, RosterRules(slots=slots, require_bench_catcher=False), 12_000_000)
    unweighted = optimize_roster(players, RosterRules(slots=slots, require_bench_catcher=False,
                                                      slot_weights={}), 12_000_000)
    assert {pick.player_id for pick in weighted.picks} == {1, 2} and weighted.total_war == 5.75
    assert {pick.player_id for pick in unweighted.picks} == {2, 3} and unweighted.total_war == 9.0
