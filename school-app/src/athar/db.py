"""SQLite access. One connection per call site; WAL mode so the web app, the MCP server
and the agent can share the file."""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import get_settings

_SCHEMA = Path(__file__).with_name("schema.sql")
_schema_checked: set[str] = set()


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    """Short random id with a type prefix: lrn_, tch_, unt_, evd_, fnd_, sum_, req_, run_."""
    return f"{prefix}_{secrets.token_hex(5)}"


def period_ord(year: int, term: int) -> int:
    return year * 3 + (term - 1)


def period_label(ord_: int) -> str:
    return f"{ord_ // 3}-T{ord_ % 3 + 1}"


@contextmanager
def connect(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """`with db.connect() as conn:` commits on success, rolls back on error, and always closes."""
    path = Path(db_path) if db_path else get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if str(path) not in _schema_checked:
        # Once per file per process: a database made by an older version gains any new table.
        conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
        if "display_name" not in {column[1] for column in conn.execute("PRAGMA table_info(learners)")}:
            conn.execute("ALTER TABLE learners ADD COLUMN display_name TEXT")   # added after the first release
        _schema_checked.add(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA.read_text(encoding="utf-8"))


def rows(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def jload(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default
