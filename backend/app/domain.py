from dataclasses import dataclass, field
from datetime import date, datetime


MODEL_VERSION = "war-proxy-v1"


@dataclass(frozen=True)
class SalaryRecord:
    player_id: int
    season: int
    base_salary_usd: int
    source_url: str
    checked_at: date
    reviewer_note: str = ""


@dataclass(frozen=True)
class ImportIssue:
    row_number: int
    code: str
    detail: str


@dataclass(frozen=True)
class Coverage:
    priced_count: int
    missing_player_ids: list[int] = field(default_factory=list)


@dataclass
class Player:
    id: int
    name: str
    team: str
    primary_position: str
    eligible_positions: set[str]
    hitting: dict[int, dict] = field(default_factory=dict)
    pitching: dict[int, dict] = field(default_factory=dict)
    fielding: dict[int, list[dict]] = field(default_factory=dict)
    is_two_way: bool = False


@dataclass
class PlayerSnapshot:
    season: int
    fetched_at: datetime
    source_urls: list[str]
    players: dict[int, Player]
    adapter_version: str = "mlb-v1"


@dataclass(frozen=True)
class ValueProjection:
    player_id: int
    estimated_war: float
    hitting_war: float
    pitching_war: float
    uncertainty: str
    input_seasons: list[int]
    model_version: str = MODEL_VERSION
