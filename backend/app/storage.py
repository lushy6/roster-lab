from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .domain import Player, PlayerSnapshot, SalaryRecord


# Newest real snapshot/salary versions kept per season, plus the versions behind the newest
# PINNED_SCENARIOS saved scenarios (the number the UI lists) so their provenance stays traceable.
# Older scenarios keep their own self-contained payload but stop pinning full league snapshots,
# which is what keeps the database from growing without bound.
KEEP_VERSIONS = 3
PINNED_SCENARIOS = 20


class LiveDataPresent(Exception):
    """Raised when demo data would hide live player data."""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, season INTEGER, fetched_at TEXT, payload TEXT, is_demo INTEGER);
        CREATE TABLE IF NOT EXISTS salaries (id TEXT PRIMARY KEY, season INTEGER, created_at TEXT, payload TEXT, is_demo INTEGER);
        CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, season INTEGER, created_at TEXT, snapshot_id TEXT, salary_id TEXT, payload TEXT);
    """)
    return connection


@contextmanager
def _session(path: Path):
    """Commit on success, roll back on error, and always close (sqlite3's own
    context manager only commits, so connections used to leak until GC)."""
    connection = _connect(path)
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _prune(db: sqlite3.Connection, table: str, reference_column: str, season: int, is_demo: bool) -> None:
    """Demo data keeps only its newest row; real data keeps KEEP_VERSIONS plus what recent scenarios reference.

    `table` and `reference_column` are literals from the two call sites below, never user input.
    The IS NOT NULL is inside the LIMITed subquery: a single NULL in a NOT IN list would make it match nothing."""
    keep = 1 if is_demo else KEEP_VERSIONS
    db.execute(f"""
        DELETE FROM {table} WHERE season=? AND is_demo=? AND rowid NOT IN (
            SELECT rowid FROM {table} WHERE season=? AND is_demo=? ORDER BY rowid DESC LIMIT ?)
        AND id NOT IN (SELECT {reference_column} FROM scenarios WHERE {reference_column} IS NOT NULL
                       ORDER BY rowid DESC LIMIT ?)
    """, (season, int(is_demo), season, int(is_demo), keep, PINNED_SCENARIOS))


def _supersede_demo(db: sqlite3.Connection, season: int) -> None:
    db.execute("DELETE FROM snapshots WHERE is_demo=1 AND season=?", (season,))
    db.execute("DELETE FROM salaries WHERE is_demo=1 AND season=?", (season,))


def delete_demo(path: Path) -> None:
    with _session(path) as db:
        db.execute("DELETE FROM snapshots WHERE is_demo=1")
        db.execute("DELETE FROM salaries WHERE is_demo=1")


def save_demo(path: Path, snapshot: PlayerSnapshot, records: list[SalaryRecord]) -> tuple[str, str]:
    """Replace the demo data for the snapshot's season, unless live data would be hidden.

    The check and both writes share one write-locked transaction, so a concurrent refresh
    cannot leave demo rows newest above live data."""
    with _session(path) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM snapshots WHERE season=? AND is_demo=0 LIMIT 1", (snapshot.season,)).fetchone():
            raise LiveDataPresent()
        _supersede_demo(db, snapshot.season)
        snapshot_id = _insert_snapshot(db, snapshot, is_demo=True)
        salary_id = _insert_salaries(db, snapshot.season, records, is_demo=True)
    return snapshot_id, salary_id


def seasons_with_data(path: Path) -> list[int]:
    """Seasons that can actually build a roster: players and salaries both present."""
    with _session(path) as db:
        rows = db.execute("SELECT season FROM snapshots INTERSECT SELECT season FROM salaries ORDER BY season DESC").fetchall()
    return [row["season"] for row in rows]


def _insert_snapshot(db: sqlite3.Connection, snapshot: PlayerSnapshot, is_demo: bool) -> str:
    identifier = str(uuid4())
    payload = asdict(snapshot)
    for player in payload["players"].values():
        player["eligible_positions"] = sorted(player["eligible_positions"])
    payload["fetched_at"] = snapshot.fetched_at.isoformat()
    db.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
               (identifier, snapshot.season, snapshot.fetched_at.isoformat(), json.dumps(payload), int(is_demo)))
    _prune(db, "snapshots", "snapshot_id", snapshot.season, is_demo)
    return identifier


def save_snapshot(path: Path, snapshot: PlayerSnapshot, is_demo: bool = False) -> str:
    with _session(path) as db:
        if not is_demo:
            _supersede_demo(db, snapshot.season)  # live data replaces fictional data in the same transaction
        return _insert_snapshot(db, snapshot, is_demo)


def latest_snapshot(path: Path, season: int) -> tuple[str, PlayerSnapshot, bool] | None:
    with _session(path) as db:
        row = db.execute("SELECT * FROM snapshots WHERE season=? ORDER BY rowid DESC LIMIT 1", (season,)).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload"])
    players = {}
    for key, raw in payload["players"].items():
        raw["eligible_positions"] = set(raw["eligible_positions"])
        raw["hitting"] = {int(year): stat for year, stat in raw["hitting"].items()}
        raw["pitching"] = {int(year): stat for year, stat in raw["pitching"].items()}
        raw["fielding"] = {int(year): stat for year, stat in raw["fielding"].items()}
        players[int(key)] = Player(**raw)
    snapshot = PlayerSnapshot(payload["season"], datetime.fromisoformat(payload["fetched_at"]),
                              payload["source_urls"], players, payload["adapter_version"])
    return row["id"], snapshot, bool(row["is_demo"])


def _insert_salaries(db: sqlite3.Connection, season: int, records: list[SalaryRecord], is_demo: bool) -> str:
    identifier = str(uuid4())
    payload = [dict(asdict(record), checked_at=record.checked_at.isoformat()) for record in records]
    db.execute("INSERT INTO salaries VALUES (?, ?, ?, ?, ?)",
               (identifier, season, datetime.now().isoformat(), json.dumps(payload), int(is_demo)))
    _prune(db, "salaries", "salary_id", season, is_demo)
    return identifier


def save_salaries(path: Path, season: int, records: list[SalaryRecord], is_demo: bool = False) -> str:
    with _session(path) as db:
        return _insert_salaries(db, season, records, is_demo)


def latest_salaries(path: Path, season: int) -> tuple[str, list[SalaryRecord], bool] | None:
    with _session(path) as db:
        row = db.execute("SELECT * FROM salaries WHERE season=? ORDER BY rowid DESC LIMIT 1", (season,)).fetchone()
    if row is None:
        return None
    records = []
    for raw in json.loads(row["payload"]):
        raw.setdefault("reviewer_note", "")
        records.append(SalaryRecord(**dict(raw, checked_at=date.fromisoformat(raw["checked_at"]))))
    return row["id"], records, bool(row["is_demo"])


def save_scenario(path: Path, season: int, snapshot_id: str, salary_id: str, payload: dict) -> str:
    identifier = str(uuid4())
    with _session(path) as db:
        db.execute("INSERT INTO scenarios VALUES (?, ?, ?, ?, ?, ?)",
                   (identifier, season, datetime.now().isoformat(), snapshot_id, salary_id, json.dumps(payload)))
    return identifier


def get_scenario(path: Path, identifier: str) -> dict | None:
    with _session(path) as db:
        row = db.execute("SELECT * FROM scenarios WHERE id=?", (identifier,)).fetchone()
    if row is None:
        return None
    return dict(json.loads(row["payload"]), id=row["id"], snapshot_id=row["snapshot_id"],
                salary_id=row["salary_id"], created_at=row["created_at"])


def list_scenarios(path: Path, season: int | None = None, limit: int = 20) -> list[dict]:
    query = "SELECT * FROM scenarios"
    params: list[object] = []
    if season is not None:
        query += " WHERE season=?"
        params.append(season)
    query += " ORDER BY rowid DESC LIMIT ?"
    params.append(limit)
    with _session(path) as db:
        rows = db.execute(query, tuple(params)).fetchall()
    summaries = []
    for row in rows:
        payload = json.loads(row["payload"])
        roster = payload.get("roster", {})
        summaries.append({
            "id": row["id"],
            "season": row["season"],
            "created_at": row["created_at"],
            "cap_usd": payload.get("cap_usd"),
            "total_salary": roster.get("total_salary", 0),
            "total_war": roster.get("total_war", 0),
            "is_demo": bool(payload.get("is_demo")),
            "snapshot_id": row["snapshot_id"],
            "salary_id": row["salary_id"],
        })
    return summaries
