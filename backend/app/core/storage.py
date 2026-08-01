"""SQLite 저장소. 스키마는 JSON 블롭으로 두어 계약이 바뀌어도 마이그레이션 부담이 없게 한다.

[7] 저장 단계. 계약이 굳으면 정규화된 테이블로 옮긴다.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from app.core.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id          TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);

CREATE TABLE IF NOT EXISTS retrospectives (
    session_id  TEXT NOT NULL,
    horizon     TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, horizon)
);

CREATE INDEX IF NOT EXISTS idx_sessions_decision ON sessions(decision_id);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(get_settings().db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)


def put(table: str, row_id: str, payload: dict[str, Any], **extra: str) -> None:
    cols = ["id", "payload", "created_at", *extra.keys()]
    placeholders = ", ".join("?" for _ in cols)
    values = [
        row_id,
        json.dumps(payload, ensure_ascii=False, default=str),
        payload.get("created_at", ""),
        *extra.values(),
    ]
    with connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
            values,
        )


def get(table: str, row_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            f"SELECT payload FROM {table} WHERE id = ?", (row_id,)
        ).fetchone()
    return json.loads(row["payload"]) if row else None


def list_all(table: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT payload FROM {table} ORDER BY created_at"
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def put_retrospective(session_id: str, horizon: str, payload: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO retrospectives "
            "(session_id, horizon, payload, created_at) VALUES (?, ?, ?, ?)",
            (
                session_id,
                horizon,
                json.dumps(payload, ensure_ascii=False, default=str),
                str(payload.get("created_at", "")),
            ),
        )


def list_retrospectives() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT payload FROM retrospectives").fetchall()
    return [json.loads(r["payload"]) for r in rows]
