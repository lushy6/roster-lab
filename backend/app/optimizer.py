from dataclasses import dataclass, field

from ortools.sat.python import cp_model


DEFAULT_SLOTS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "C2",
                 "BN1", "BN2", "BN3", "SP1", "SP2", "SP3", "SP4", "SP5",
                 "RP1", "RP2", "RP3", "RP4", "RP5", "RP6", "RP7", "RP8")


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


@dataclass(frozen=True)
class Pick:
    player_id: int
    name: str
    team: str
    slot: str
    salary: int
    war: float
    is_two_way: bool


@dataclass
class RosterResult:
    status: str
    picks: list[Pick] = field(default_factory=list)
    total_salary: int = 0
    total_war: float = 0.0
    minimum_feasible_salary: int | None = None
    reason: str | None = None


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
        return "C"
    return slot


def _solve(players: list[Candidate], rules: RosterRules, cap_usd: int | None,
           locked_ids: set[int], excluded_ids: set[int], *, minimize_cost: bool = False) -> RosterResult:
    model = cp_model.CpModel()
    variables = {}
    roles = {_role(slot) for slot in rules.slots}
    for player in players:
        if player.id in excluded_ids:
            continue
        for role in roles:
            if _eligible(player, role):
                variables[player.id, role] = model.new_bool_var(f"p{player.id}_{role}")
    for role in roles:
        options = [var for (player_id, name), var in variables.items() if name == role]
        if not options:
            return RosterResult("infeasible", reason=f"No eligible players for {role}")
        model.add(sum(options) == sum(1 for slot in rules.slots if _role(slot) == role))
    for player in players:
        options = [var for (player_id, _), var in variables.items() if player_id == player.id]
        if options:
            if player.id in locked_ids:
                model.add(sum(options) == 1)
            else:
                model.add(sum(options) <= 1)
        elif player.id in locked_ids:
            return RosterResult("infeasible", reason=f"Locked player {player.name} has no eligible slot")
    salary_expr = sum(player.salary * var for player in players for role in roles
                      if (var := variables.get((player.id, role))) is not None)
    if cap_usd is not None:
        model.add(salary_expr <= cap_usd)
    if minimize_cost:
        model.minimize(salary_expr)
    else:
        # Scale WAR to integer points, and prefer lower salary for exact WAR ties.
        model.maximize(sum((round(player.war * 1000) * 1_000_000 - player.salary // 1000) * var
                           for player in players for role in roles
                           if (var := variables.get((player.id, role))) is not None))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return RosterResult("infeasible", reason="No roster satisfies these constraints")
    chosen_by_role = {role: sorted((player for player in players
                                    if (var := variables.get((player.id, role))) is not None and solver.value(var)),
                                   key=lambda player: (-player.war, player.id))
                      for role in roles}
    picks = []
    for slot in rules.slots:
        player = chosen_by_role[_role(slot)].pop(0)
        picks.append(Pick(player.id, player.name, player.team, slot, player.salary, player.war, player.is_two_way))
    result = RosterResult("optimal" if status == cp_model.OPTIMAL else "feasible", picks,
                          sum(p.salary for p in picks), round(sum(p.war for p in picks), 3))
    problems = validate_roster(result, rules, cap_usd, players, locked_ids, excluded_ids)
    if problems:
        raise RuntimeError("Solver returned invalid roster: " + "; ".join(problems))
    return result


def optimize_roster(players: list[Candidate], rules: RosterRules, cap_usd: int,
                    locked_ids: set[int] | None = None, excluded_ids: set[int] | None = None) -> RosterResult:
    locked_ids = locked_ids or set()
    excluded_ids = excluded_ids or set()
    if locked_ids & excluded_ids:
        return RosterResult("infeasible", reason="A player cannot be both locked and excluded")
    result = _solve(players, rules, cap_usd, locked_ids, excluded_ids)
    if result.status == "infeasible" and result.reason == "No roster satisfies these constraints":
        cheapest = _solve(players, rules, None, locked_ids, excluded_ids, minimize_cost=True)
        if cheapest.status == "optimal":
            result.minimum_feasible_salary = cheapest.total_salary
            result.reason = f"Cap is below the cheapest valid roster (${cheapest.total_salary:,})"
    return result


def validate_roster(result: RosterResult, rules: RosterRules, cap_usd: int | None,
                    candidates: list[Candidate] | None = None, locked_ids: set[int] | None = None,
                    excluded_ids: set[int] | None = None) -> list[str]:
    if result.status == "infeasible":
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
    if round(sum(p.war for p in result.picks), 3) != result.total_war:
        errors.append("Value total is incorrect")
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
