from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from . import auth
from .domain import Player, PlayerSnapshot, SalaryRecord


# Newest real snapshot/salary versions kept per season, plus the versions behind the newest
# PINNED_SCENARIOS saved scenarios (the number the UI lists) so their provenance stays traceable.
# Older scenarios keep their own self-contained payload but stop pinning full league snapshots,
# which is what keeps the database from growing without bound.
KEEP_VERSIONS = 3
PINNED_SCENARIOS = 20


class LiveDataPresent(Exception):
    """Raised when demo data would hide live player data."""


class VersionGone(Exception):
    """Raised when a scenario's snapshot or salary version was replaced and pruned mid-build."""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, season INTEGER, fetched_at TEXT, payload TEXT, is_demo INTEGER);
        CREATE TABLE IF NOT EXISTS salaries (id TEXT PRIMARY KEY, season INTEGER, created_at TEXT, payload TEXT, is_demo INTEGER);
        CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, season INTEGER, created_at TEXT, snapshot_id TEXT, salary_id TEXT, payload TEXT);
    """)
    # Migration: scenarios saved before accounts existed have no owner and stay public.
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(scenarios)")}
    if "owner_id" not in columns:
        try:
            connection.execute("ALTER TABLE scenarios ADD COLUMN owner_id TEXT")
        except sqlite3.OperationalError as exc:  # another connection migrated first
            if "duplicate column" not in str(exc):
                raise
    connection.execute("CREATE INDEX IF NOT EXISTS scenarios_owner ON scenarios(owner_id)")
    auth.ensure_tables(connection)
    return connection


@contextmanager
def session(path: Path):
    """Public handle on one committed-or-rolled-back connection (used by the auth endpoints)."""
    with _session(path) as db:
        yield db


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
    _invalidate_snapshot_cache()


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
    _invalidate_snapshot_cache()
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
        identifier = _insert_snapshot(db, snapshot, is_demo)
    _invalidate_snapshot_cache()
    return identifier


def _snapshot_from_payload(payload_json: str) -> PlayerSnapshot:
    payload = json.loads(payload_json)
    players = {}
    for key, raw in payload["players"].items():
        raw["eligible_positions"] = set(raw["eligible_positions"])
        raw["hitting"] = {int(year): stat for year, stat in raw["hitting"].items()}
        raw["pitching"] = {int(year): stat for year, stat in raw["pitching"].items()}
        raw["fielding"] = {int(year): stat for year, stat in raw["fielding"].items()}
        players[int(key)] = Player(**raw)
    return PlayerSnapshot(payload["season"], datetime.fromisoformat(payload["fetched_at"]),
                          payload["source_urls"], players, payload["adapter_version"])


@lru_cache(maxsize=8)
def _cached_snapshot(path_key: str, identifier: str, season: int) -> PlayerSnapshot | None:
    with _session(Path(path_key)) as db:
        row = db.execute("SELECT payload FROM snapshots WHERE id=? AND season=?",
                         (identifier, season)).fetchone()
    return _snapshot_from_payload(row["payload"]) if row is not None else None


def _invalidate_snapshot_cache() -> None:
    _cached_snapshot.cache_clear()


def latest_snapshot(path: Path, season: int) -> tuple[str, PlayerSnapshot, bool] | None:
    path_key = str(path.resolve())
    for _ in range(2):
        with _session(path) as db:
            row = db.execute("SELECT id, is_demo FROM snapshots WHERE season=? ORDER BY rowid DESC LIMIT 1",
                             (season,)).fetchone()
        if row is None:
            return None
        snapshot = _cached_snapshot(path_key, row["id"], season)
        if snapshot is not None:
            return row["id"], snapshot, bool(row["is_demo"])
    return None


def _insert_salaries(db: sqlite3.Connection, season: int, records: list[SalaryRecord], is_demo: bool) -> str:
    identifier = str(uuid4())
    payload = [dict(asdict(record), checked_at=record.checked_at.isoformat()) for record in records]
    db.execute("INSERT INTO salaries VALUES (?, ?, ?, ?, ?)",
               (identifier, season, datetime.now().isoformat(), json.dumps(payload), int(is_demo)))
    _prune(db, "salaries", "salary_id", season, is_demo)
    return identifier


def save_salaries(path: Path, season: int, records: list[SalaryRecord], is_demo: bool = False) -> str:
    with _session(path) as db:
        identifier = _insert_salaries(db, season, records, is_demo)
    _invalidate_snapshot_cache()
    return identifier


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


def save_scenario(path: Path, season: int, snapshot_id: str, salary_id: str, payload: dict,
                  owner_id: str | None = None) -> str:
    """Save a scenario, refusing if its snapshot or salary version was pruned while it was being solved.

    The existence check and the insert share one write-locked transaction, so no prune can run between them;
    once saved, the scenario itself pins both versions."""
    identifier = str(uuid4())
    with _session(path) as db:
        db.execute("BEGIN IMMEDIATE")
        if (db.execute("SELECT 1 FROM snapshots WHERE id=?", (snapshot_id,)).fetchone() is None
                or db.execute("SELECT 1 FROM salaries WHERE id=?", (salary_id,)).fetchone() is None):
            raise VersionGone()
        db.execute("INSERT INTO scenarios (id, season, created_at, snapshot_id, salary_id, payload, owner_id) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (identifier, season, datetime.now().isoformat(), snapshot_id, salary_id, json.dumps(payload), owner_id))
    return identifier


def _visible(viewer_id: str | None) -> tuple[str, tuple]:
    """SQL filter: public (unowned) scenarios plus the viewer's own. Everyone else's are invisible."""
    if viewer_id is None:
        return "owner_id IS NULL", ()
    return "(owner_id IS NULL OR owner_id=?)", (viewer_id,)


def get_scenario(path: Path, identifier: str, viewer_id: str | None = None) -> dict | None:
    """None both when the scenario does not exist and when it belongs to someone else, so ids cannot be probed."""
    clause, params = _visible(viewer_id)
    with _session(path) as db:
        row = db.execute(f"SELECT * FROM scenarios WHERE id=? AND {clause}", (identifier, *params)).fetchone()
    if row is None:
        return None
    return dict(json.loads(row["payload"]), id=row["id"], snapshot_id=row["snapshot_id"],
                salary_id=row["salary_id"], created_at=row["created_at"],
                owned_by_me=viewer_id is not None and row["owner_id"] == viewer_id)


class NotOwner(Exception):
    """Raised when deleting a public scenario, which has no owner who could delete it."""


def delete_scenario(path: Path, identifier: str, user_id: str) -> bool:
    """Delete the caller's own scenario. False if it does not exist or is someone else's (indistinguishable)."""
    with _session(path) as db:
        row = db.execute("SELECT owner_id FROM scenarios WHERE id=?", (identifier,)).fetchone()
        if row is None or (row["owner_id"] is not None and row["owner_id"] != user_id):
            return False
        if row["owner_id"] is None:
            raise NotOwner()
        db.execute("DELETE FROM scenarios WHERE id=? AND owner_id=?", (identifier, user_id))
    return True


def list_scenarios(path: Path, season: int | None = None, limit: int = 20, viewer_id: str | None = None,
                   mine_only: bool = False) -> list[dict]:
    if mine_only and viewer_id is None:
        return []
    clause, visible_params = ("owner_id=?", (viewer_id,)) if mine_only else _visible(viewer_id)
    query = f"SELECT * FROM scenarios WHERE {clause}"
    params: list[object] = list(visible_params)
    if season is not None:
        query += " AND season=?"
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
            "owned_by_me": viewer_id is not None and row["owner_id"] == viewer_id,
        })
    return summaries
