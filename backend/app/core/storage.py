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

DEFAULT_USER_ID = "local"
"""user_id 가 생기기 전에 저장된 행들의 주인. NULL 을 이 값으로 읽는다."""

# user_id 는 나중에 들어왔다. ALTER TABLE 은 이미 있는 컬럼에 실패하므로 따로 시도한다.
_MIGRATIONS = [
    "ALTER TABLE decisions ADD COLUMN user_id TEXT",
    "ALTER TABLE sessions ADD COLUMN user_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_decisions_user ON decisions(user_id)",
]


_ready: set[str] = set()
"""스키마를 확인한 DB 경로. 서비스를 직접 부르는 테스트도 마이그레이션을 타야 한다."""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = get_settings().db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        if path not in _ready:
            _apply_schema(conn)
            _ready.add(path)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    for statement in _MIGRATIONS:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            # 이미 적용된 마이그레이션. SQLite 에는 IF NOT EXISTS 컬럼 문법이 없다.
            pass


def init_db() -> None:
    with connect() as conn:
        _apply_schema(conn)


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


def list_all(table: str, *, user_id: str | None = None) -> list[dict[str, Any]]:
    """★user_id 를 주면 그 사람 것만.

    주지 않으면 전원이 섞인다. [8] 축적과 개인 표준화는 **반드시** 주어야 한다 —
    안 주면 남의 기록이 내 가치관 지도에 들어온다.
    """
    with connect() as conn:
        if user_id is None:
            rows = conn.execute(
                f"SELECT payload FROM {table} ORDER BY created_at"
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT payload FROM {table} "
                "WHERE COALESCE(user_id, ?) = ? ORDER BY created_at",
                (DEFAULT_USER_ID, user_id),
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


def list_retrospectives(*, user_id: str | None = None) -> list[dict[str, Any]]:
    """회고는 세션에 딸려 있으므로 세션의 주인을 따라간다."""
    with connect() as conn:
        if user_id is None:
            rows = conn.execute("SELECT payload FROM retrospectives").fetchall()
        else:
            rows = conn.execute(
                "SELECT r.payload FROM retrospectives r "
                "JOIN sessions s ON s.id = r.session_id "
                "WHERE COALESCE(s.user_id, ?) = ?",
                (DEFAULT_USER_ID, user_id),
            ).fetchall()
    return [json.loads(r["payload"]) for r in rows]
