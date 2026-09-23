from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ortools.sat.python import cp_model


DEFAULT_SLOTS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "C2",
                 "BN1", "BN2", "BN3", "SP1", "SP2", "SP3", "SP4", "SP5",
                 "RP1", "RP2", "RP3", "RP4", "RP5", "RP6", "RP7", "RP8")

# Bench and backup-catcher slots play a fraction of a season, so their value counts for
# less than a starter's. 0.25 is roughly a bench bat's share of a starter's plate
# appearances. Override per scenario through RosterRules(slot_weights=...).
DEFAULT_SLOT_WEIGHTS = {"C2": 0.25, "BN": 0.25}
SOLVER_SECONDS = 15


@dataclass(frozen=True)
class Candidate:
    id: int
    name: str
    team: str
    salary: int
    war: float
    eligible_positions: set[str]
    is_two_way: bool = False


@dataclass(frozen=True)
class RosterRules:
    slots: tuple[str, ...] = DEFAULT_SLOTS
    require_bench_catcher: bool = True
    slot_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SLOT_WEIGHTS))

    def weight(self, slot: str) -> float:
        return self.slot_weights.get(_role(slot), 1.0)


@dataclass(frozen=True)
class Pick:
    player_id: int
    name: str
    team: str
    slot: str
    salary: int
    war: float  # the player's own estimate; the roster counts war * weight
    is_two_way: bool
    weight: float = 1.0


@dataclass
class RosterResult:
    status: str  # optimal | feasible | infeasible | timeout
    picks: list[Pick] = field(default_factory=list)
    total_salary: int = 0
    total_war: float = 0.0  # slot-weighted
    minimum_feasible_salary: int | None = None
    reason: str | None = None
    code: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("optimal", "feasible")


def _eligible(candidate: Candidate, slot: str) -> bool:
    positions = candidate.eligible_positions
    if slot.startswith("SP"):
        return "SP" in positions
    if slot.startswith("RP"):
        return "RP" in positions
    if slot == "C2":
        return "C" in positions
    if slot.startswith("BN"):
        return bool(positions & {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"})
    return slot in positions


def _role(slot: str) -> str:
    if slot.startswith("SP"):
        return "SP"
    if slot.startswith("RP"):
        return "RP"
    if slot.startswith("BN"):
        return "BN"
    if slot == "C2":
        return "C2"
    return slot


def _weighted_war(picks: list[Pick]) -> float:
    return round(sum(pick.war * pick.weight for pick in picks), 3)


def _solve(players: list[Candidate], rules: RosterRules, cap_usd: int | None,
           locked_ids: set[int], excluded_ids: set[int], *, minimize_cost: bool = False,
           avoid_ids: set[int] | None = None) -> RosterResult:
    model = cp_model.CpModel()
    by_id = {player.id: player for player in players}
    roles = {_role(slot) for slot in rules.slots}
    slots_per_role = Counter(_role(slot) for slot in rules.slots)
    variables = {}
    by_role: dict[str, list] = defaultdict(list)
    by_player: dict[int, list] = defaultdict(list)
    for player in players:
        if player.id in excluded_ids:
            continue
        for role in roles:
            if _eligible(player, role):
                var = variables[player.id, role] = model.new_bool_var(f"p{player.id}_{role}")
                by_role[role].append(var)
                by_player[player.id].append(var)
    for role in roles:
        if not by_role[role]:
            return RosterResult("infeasible", reason=f"No eligible players for {role}", code="no_eligible")
        model.add(sum(by_role[role]) == slots_per_role[role])
    if rules.require_bench_catcher and "BN" in roles and "C2" not in roles:
        bench_catchers = [var for (player_id, role), var in variables.items()
                          if role == "BN" and _eligible(by_id[player_id], "C2")]
        if not bench_catchers:
            return RosterResult("infeasible", reason="No eligible bench catcher", code="no_bench_catcher")
        model.add(sum(bench_catchers) >= 1)
    for player in players:
        options = by_player.get(player.id)
        if options:
            model.add(sum(options) == 1 if player.id in locked_ids else sum(options) <= 1)
        elif player.id in locked_ids:
            return RosterResult("infeasible", reason=f"Locked player {player.name} has no eligible slot",
                                code="locked_ineligible")
    avoid_ids = avoid_ids or set()
    if avoid_ids:
        avoid_variables = [var for player_id in avoid_ids for var in by_player.get(player_id, [])]
        if avoid_variables:
            model.add(sum(avoid_variables) <= len(avoid_ids) - 1)
    salary_expr = sum(by_id[player_id].salary * var for (player_id, _), var in variables.items())
    if cap_usd is not None:
        model.add(salary_expr <= cap_usd)
    if minimize_cost:
        model.minimize(salary_expr)
    else:
        # Scale slot-weighted WAR to integer points, and prefer lower salary for exact WAR ties.
        model.maximize(sum((round(by_id[player_id].war * rules.slot_weights.get(role, 1.0) * 1000) * 1_000_000
                            - by_id[player_id].salary // 1000) * var
                           for (player_id, role), var in variables.items()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_SECONDS
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        return RosterResult("infeasible", reason="No roster satisfies these constraints", code="constraints")
    if status == cp_model.UNKNOWN:
        # Out of time with no answer: that is not the same as "impossible".
        return RosterResult("timeout", reason=f"The solver hit its {SOLVER_SECONDS}s limit before finding a roster",
                            code="timeout")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"Unexpected solver status {status}")
    chosen_by_role: dict[str, list[Candidate]] = defaultdict(list)
    for (player_id, role), var in variables.items():
        if solver.value(var):
            chosen_by_role[role].append(by_id[player_id])
    for chosen in chosen_by_role.values():
        chosen.sort(key=lambda player: (-player.war, player.id))
    picks = []
    for slot in rules.slots:
        player = chosen_by_role[_role(slot)].pop(0)
        picks.append(Pick(player.id, player.name, player.team, slot, player.salary, player.war,
                          player.is_two_way, rules.weight(slot)))
    result = RosterResult("optimal" if status == cp_model.OPTIMAL else "feasible", picks,
                          sum(p.salary for p in picks), _weighted_war(picks))
    problems = validate_roster(result, rules, cap_usd, players, locked_ids, excluded_ids)
    if problems:
        raise RuntimeError("Solver returned invalid roster: " + "; ".join(problems))
    return result


def optimize_roster(players: list[Candidate], rules: RosterRules, cap_usd: int,
                    locked_ids: set[int] | None = None, excluded_ids: set[int] | None = None,
                    avoid_ids: set[int] | None = None) -> RosterResult:
    locked_ids = locked_ids or set()
    excluded_ids = excluded_ids or set()
    if locked_ids & excluded_ids:
        return RosterResult("infeasible", reason="A player cannot be both locked and excluded", code="conflict")
    result = _solve(players, rules, cap_usd, locked_ids, excluded_ids, avoid_ids=avoid_ids)
    if result.code == "constraints":
        cheapest = _solve(players, rules, None, locked_ids, excluded_ids, minimize_cost=True)
        if cheapest.status == "optimal":
            result.minimum_feasible_salary = cheapest.total_salary
            result.reason = f"Cap is below the cheapest valid roster (${cheapest.total_salary:,})"
    return result


def validate_roster(result: RosterResult, rules: RosterRules, cap_usd: int | None,
                    candidates: list[Candidate] | None = None, locked_ids: set[int] | None = None,
                    excluded_ids: set[int] | None = None) -> list[str]:
    if not result.ok:
        return []
    errors = []
    if len(result.picks) != len(rules.slots) or {p.slot for p in result.picks} != set(rules.slots):
        errors.append("Roster slots are incomplete or duplicated")
    if len({p.player_id for p in result.picks}) != len(result.picks):
        errors.append("A player fills multiple slots")
    if cap_usd is not None and sum(p.salary for p in result.picks) > cap_usd:
        errors.append("Roster exceeds salary cap")
    if sum(p.salary for p in result.picks) != result.total_salary:
        errors.append("Salary total is incorrect")
    if _weighted_war(result.picks) != result.total_war:
        errors.append("Value total is incorrect")
    if any(pick.weight != rules.weight(pick.slot) for pick in result.picks):
        errors.append("Slot weight is incorrect")
    if candidates is not None:
        by_id = {candidate.id: candidate for candidate in candidates}
        for pick in result.picks:
            candidate = by_id.get(pick.player_id)
            if candidate is None or not _eligible(candidate, pick.slot):
                errors.append(f"Player {pick.player_id} is not eligible for {pick.slot}")
            elif pick.salary != candidate.salary or pick.war != candidate.war:
                errors.append(f"Player {pick.player_id} has incorrect salary or value")
    chosen = {pick.player_id for pick in result.picks}
    if locked_ids and not locked_ids.issubset(chosen):
        errors.append("A locked player is missing")
    if excluded_ids and excluded_ids & chosen:
        errors.append("An excluded player is selected")
    return errors
