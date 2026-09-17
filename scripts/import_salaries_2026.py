"""Build an MLB-ID salary register from the 2026 Baseball Cube roster export.

The Baseball Cube publishes salary figures on each 2026 opening-day roster page.
Those pages use their own player identifiers, so this script joins the export to
the live MLB Stats API player list by normalized name (and team when needed).
The resulting register keeps the app's stable salary CSV schema and leaves live
players without a source row blank rather than inventing a salary.
"""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx


SEASON = 2026
CHECKED_AT = "2026-09-17"
SOURCE_URL = "https://www.thebaseballcube.com/content/payroll_year/2026/"
MLB_API = "https://statsapi.mlb.com/api/v1"
REGISTER_COLUMNS = [
    "player_id",
    "player_name",
    "season",
    "base_salary_usd",
    "source_url",
    "checked_at",
    "reviewer_note",
]


@dataclass(frozen=True)
class SourceSalary:
    source_player_id: int
    player_name: str
    salary_usd: int
    teams: tuple[str, ...]


def normalize_name(value: str) -> str:
    """Normalize punctuation, accents, and Baseball Cube IL prefixes."""

    value = re.sub(r"^il[-\s]*", "", value or "", flags=re.IGNORECASE)
    value = value.replace("’", "'").replace("–", "-")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", value.lower())


def core_name(value: str) -> str:
    key = normalize_name(value)
    # Check longer suffixes first so "iii" is not reduced to "i".
    return re.sub(r"(?:iii|iv|ii|jr|sr)$", "", key)


def normalize_team(value: str) -> str:
    return normalize_name(value)


def read_source(path: Path) -> list[SourceSalary]:
    """Read the roster-page export and collapse repeated traded-player rows."""

    grouped: dict[int, dict[str, object]] = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"source_player_id", "player_name", "team", "salary_usd"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Source CSV requires columns: {', '.join(sorted(required))}")
        for row_number, row in enumerate(reader, start=2):
            try:
                source_id = int((row.get("source_player_id") or "").strip())
                salary = int((row.get("salary_usd") or "").strip())
            except ValueError as exc:
                raise ValueError(f"Invalid source row {row_number}: {exc}") from exc
            name = (row.get("player_name") or "").strip()
            team = (row.get("team") or "").strip()
            if source_id <= 0 or salary <= 0 or not name:
                raise ValueError(f"Invalid source row {row_number}: player and salary are required")
            existing = grouped.get(source_id)
            if existing is None:
                grouped[source_id] = {"name": name, "salary": salary, "teams": {team} if team else set()}
                continue
            if existing["name"] != name or existing["salary"] != salary:
                raise ValueError(f"Source player {source_id} has conflicting name or salary")
            if team:
                existing["teams"].add(team)  # type: ignore[union-attr]

    return [
        SourceSalary(source_id, str(item["name"]), int(item["salary"]), tuple(sorted(item["teams"])))  # type: ignore[arg-type]
        for source_id, item in sorted(grouped.items())
    ]


def fetch_mlb_players(client: httpx.Client, season: int) -> list[dict]:
    response = client.get(f"{MLB_API}/sports/1/players", params={"season": season}, timeout=30)
    response.raise_for_status()
    return response.json().get("people", [])


def fetch_mlb_teams(client: httpx.Client, season: int) -> dict[int, str]:
    response = client.get(f"{MLB_API}/teams", params={"sportId": 1, "season": season}, timeout=30)
    response.raise_for_status()
    return {int(team["id"]): team["name"] for team in response.json().get("teams", [])}


def match_source_rows(source_rows: Iterable[SourceSalary], players: list[dict], team_names: dict[int, str]) -> dict[int, SourceSalary]:
    exact: dict[str, list[dict]] = defaultdict(list)
    core: dict[str, list[dict]] = defaultdict(list)
    for player in players:
        exact[normalize_name(player.get("fullName", ""))].append(player)
        core[core_name(player.get("fullName", ""))].append(player)

    result: dict[int, SourceSalary] = {}
    for source in source_rows:
        candidates = exact.get(normalize_name(source.player_name), [])
        if not candidates:
            candidates = core.get(core_name(source.player_name), [])
        if len(candidates) > 1:
            source_teams = {normalize_team(team) for team in source.teams}
            candidates = [
                player for player in candidates
                if normalize_team(team_names.get(int(player.get("currentTeam", {}).get("id", 0)), "")) in source_teams
            ]
        if len(candidates) != 1:
            details = ", ".join(f"{p.get('id')} {p.get('fullName')}" for p in candidates) or "no candidate"
            raise ValueError(f"Could not uniquely match {source.player_name} ({source.teams}): {details}")
        result[int(candidates[0]["id"])] = source
    return result


def write_register(template_path: Path, output_path: Path, matched: dict[int, SourceSalary], checked_at: str = CHECKED_AT) -> tuple[int, int]:
    priced = 0
    unpriced = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with template_path.open(newline="", encoding="utf-8-sig") as source_stream, output_path.open("w", newline="", encoding="utf-8") as output_stream:
        reader = csv.DictReader(source_stream)
        writer = csv.DictWriter(output_stream, fieldnames=REGISTER_COLUMNS)
        writer.writeheader()
        for row in reader:
            player_id = int(row["player_id"])
            source = matched.get(player_id)
            if source is None:
                unpriced += 1
                writer.writerow({
                    "player_id": player_id,
                    "player_name": row["player_name"],
                    "season": SEASON,
                    "base_salary_usd": "",
                    "source_url": "",
                    "checked_at": "",
                    "reviewer_note": "",
                })
                continue
            priced += 1
            note = (
                "The Baseball Cube 2026 opening-day roster salary snapshot; "
                f"source player {source.source_player_id}; captured {checked_at}; "
                "matched to MLB Stats API by normalized player name."
            )
            writer.writerow({
                "player_id": player_id,
                "player_name": row["player_name"],
                "season": SEASON,
                "base_salary_usd": source.salary_usd,
                "source_url": SOURCE_URL,
                "checked_at": checked_at,
                "reviewer_note": note,
            })
    return priced, unpriced


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/the-baseball-cube-2026-roster.csv"))
    parser.add_argument("--template", type=Path, default=Path("data/salary-template-2026.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/salary-register-2026.csv"))
    args = parser.parse_args()

    source_rows = read_source(args.source)
    with httpx.Client() as client:
        players = fetch_mlb_players(client, SEASON)
        team_names = fetch_mlb_teams(client, SEASON)
    matched = match_source_rows(source_rows, players, team_names)
    priced, unpriced = write_register(args.template, args.output, matched)
    print(f"Wrote {args.output}: {priced} priced players, {unpriced} live players without a source salary")


if __name__ == "__main__":
    main()
