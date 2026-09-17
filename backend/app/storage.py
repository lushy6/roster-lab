from dataclasses import asdict
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .domain import Player, PlayerSnapshot, SalaryRecord


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


def save_snapshot(path: Path, snapshot: PlayerSnapshot, is_demo: bool = False) -> str:
    identifier = str(uuid4())
    payload = asdict(snapshot)
    for player in payload["players"].values():
        player["eligible_positions"] = sorted(player["eligible_positions"])
    payload["fetched_at"] = snapshot.fetched_at.isoformat()
    with _connect(path) as db:
        db.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
                   (identifier, snapshot.season, snapshot.fetched_at.isoformat(), json.dumps(payload), int(is_demo)))
    return identifier


def latest_snapshot(path: Path, season: int) -> tuple[str, PlayerSnapshot, bool] | None:
    with _connect(path) as db:
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


def save_salaries(path: Path, season: int, records: list[SalaryRecord], is_demo: bool = False) -> str:
    identifier = str(uuid4())
    payload = [dict(asdict(record), checked_at=record.checked_at.isoformat()) for record in records]
    with _connect(path) as db:
        db.execute("INSERT INTO salaries VALUES (?, ?, ?, ?, ?)",
                   (identifier, season, datetime.now().isoformat(), json.dumps(payload), int(is_demo)))
    return identifier


def latest_salaries(path: Path, season: int) -> tuple[str, list[SalaryRecord], bool] | None:
    with _connect(path) as db:
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
    with _connect(path) as db:
        db.execute("INSERT INTO scenarios VALUES (?, ?, ?, ?, ?, ?)",
                   (identifier, season, datetime.now().isoformat(), snapshot_id, salary_id, json.dumps(payload)))
    return identifier


def get_scenario(path: Path, identifier: str) -> dict | None:
    with _connect(path) as db:
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
    with _connect(path) as db:
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
