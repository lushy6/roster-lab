from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class SalaryRecord:
    player_id: int
    season: int
    base_salary_usd: int
    source_url: str
    checked_at: date


@dataclass(frozen=True)
class ImportIssue:
    row_number: int
    code: str
    detail: str


@dataclass(frozen=True)
class Coverage:
    priced_count: int
    missing_player_ids: list[int] = field(default_factory=list)
