"""SQLite access. One connection per request; WAL so the runner can poll concurrently."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / os.environ.get("SKILLSTORE_DB", "data/skillstore.db")
SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA.read_text())


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run a write and return lastrowid."""
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.lastrowid


def seed_skills(path: Path | None = None, replace: bool = True) -> int:
    """Load the catalog from JSON. Idempotent."""
    path = path or ROOT / "data" / "seed_skills.json"
    manifests = json.loads(path.read_text())
    with connect() as conn:
        if replace:
            # Composites were built here from verified plans; they are not in the
            # seed file and must survive a catalog edit.
            conn.execute("DELETE FROM skills WHERE category != 'composite'")
        for m in manifests:
            conn.execute(
                """INSERT OR REPLACE INTO skills
                   (id, name, vendor, category, price_eur, status, description, manifest)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    m["id"], m["name"], m["vendor"], m["category"],
                    m["price_eur"], m["status"], m["description"], json.dumps(m),
                ),
            )
        conn.commit()
    return len(manifests)
