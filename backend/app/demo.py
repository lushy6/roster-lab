from datetime import date, datetime, timezone

from .domain import Player, PlayerSnapshot, SalaryRecord


def demo_data() -> tuple[PlayerSnapshot, list[SalaryRecord]]:
    players: dict[int, Player] = {}
    salaries = []
    identifier = 900000
    counts = {"C": 4, "1B": 3, "2B": 3, "3B": 3, "SS": 3,
              "LF": 3, "CF": 3, "RF": 3, "DH": 3, "SP": 15, "RP": 24}
    for position, count in counts.items():
        for index in range(count):
            identifier += 1
            if position in {"SP", "RP"}:
                primary = "P"
                pitching = {2025: {"inningsPitched": str(150 - index * 4 if position == "SP" else 60 - index),
                                   "era": str(round(3.10 + index * 0.15, 2)),
                                   "gamesStarted": 25 if position == "SP" else 0,
                                   "gamesPlayed": 28 if position == "SP" else 55}}
                hitting = {}
            else:
                primary = position
                pitching = {}
                hitting = {2025: {"plateAppearances": 550 - index * 40,
                                  "ops": str(round(0.85 - index * 0.035, 3))}}
            players[identifier] = Player(identifier, f"Demo {position} {index + 1}", "Fictional club",
                                         primary, {position}, hitting, pitching)
            salary = 1_200_000 + index * 1_500_000 + (4_000_000 if position == "SP" else 0)
            salaries.append(SalaryRecord(identifier, 2026, salary,
                                         f"https://example.org/fictional/{identifier}", date(2026, 9, 17)))
    return PlayerSnapshot(2026, datetime.now(timezone.utc), ["Fictional demo data"], players, "demo-v1"), salaries
