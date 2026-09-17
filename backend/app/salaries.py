import csv
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .domain import Coverage, ImportIssue, SalaryRecord


def load_salary_csv(path: Path) -> tuple[list[SalaryRecord], list[ImportIssue]]:
    records: list[SalaryRecord] = []
    issues: list[ImportIssue] = []
    seen: set[tuple[int, int]] = set()
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"player_id", "season", "base_salary_usd", "source_url", "checked_at"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Salary CSV requires columns: {', '.join(sorted(required))}")
        for row_number, row in enumerate(reader, start=2):
            if not (row["base_salary_usd"] or "").strip():
                continue
            try:
                player_id = int(row["player_id"])
                season = int(row["season"])
                salary = int(row["base_salary_usd"])
                checked_at = date.fromisoformat(row["checked_at"])
                if player_id <= 0 or season < 1900 or salary <= 0:
                    raise ValueError("IDs, season, and salary must be positive")
            except (TypeError, ValueError) as exc:
                issues.append(ImportIssue(row_number, "invalid_value", str(exc)))
                continue
            source_url = (row["source_url"] or "").strip()
            parsed = urlparse(source_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                issues.append(ImportIssue(row_number, "missing_source", "An HTTP(S) source URL is required"))
                continue
            key = (player_id, season)
            if key in seen:
                issues.append(ImportIssue(row_number, "duplicate_player_season", str(key)))
                continue
            seen.add(key)
            records.append(SalaryRecord(player_id, season, salary, source_url, checked_at))
    return records, issues


def salary_coverage(player_ids: set[int], salaries: list[SalaryRecord], season: int) -> Coverage:
    priced = {record.player_id for record in salaries if record.season == season} & player_ids
    return Coverage(len(priced), sorted(player_ids - priced))
