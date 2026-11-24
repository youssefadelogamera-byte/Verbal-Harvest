"""Audit log: one row per tool call, by anyone. This is what a parent's "why?" is answered from."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from . import db

# Set by the agent (or a test) so tool calls are attributed to a run and an actor.
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)
current_actor: ContextVar[str] = ContextVar("current_actor", default="mcp-client")

_MAX_OUTPUT = 4000


def write_row(conn, tool: str, input_: Any, output: Any, ok: bool, duration_ms: int,
              actor: str | None = None, run_id: str | None = None) -> int:
    """Insert one audit row on an open connection, so it can share a transaction with the change."""
    out = db.jdump(output)
    if len(out) > _MAX_OUTPUT:
        out = out[:_MAX_OUTPUT] + "...(truncated)"
    cur = conn.execute(
        "INSERT INTO audit_log (ts, run_id, actor, tool, input, output, ok, duration_ms) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (db.now_iso(), run_id or current_run_id.get(), actor or current_actor.get(), tool,
         db.jdump(input_), out, 1 if ok else 0, duration_ms),
    )
    return int(cur.lastrowid)


def log_call(tool: str, input_: Any, output: Any, ok: bool, duration_ms: int,
             actor: str | None = None, run_id: str | None = None, db_path=None) -> int:
    """Write one audit row in its own transaction."""
    with db.connect(db_path) as conn:
        return write_row(conn, tool, input_, output, ok, duration_ms, actor, run_id)


def audited(tool: str) -> Callable:
    """Decorator for tool functions that take keyword arguments and return JSON-able data.
    Reserved kwargs `_actor` and `_run_id` are stripped and used for attribution: they are set on the
    context variables for the duration of the call, so the tool itself can see who is calling.
    A `db_path` kwarg is passed to the tool and also decides where the audit row is written."""

    def wrap(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            actor = kwargs.pop("_actor", None)
            run_id = kwargs.pop("_run_id", None)
            db_path = kwargs.get("db_path")
            actor_token = current_actor.set(actor) if actor else None
            run_token = current_run_id.set(run_id) if run_id else None
            started = time.perf_counter()
            try:
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:
                    log_call(tool, kwargs, {"error": f"{type(exc).__name__}: {exc}"}, False,
                             int((time.perf_counter() - started) * 1000), db_path=db_path)
                    raise
                log_call(tool, kwargs, result, True, int((time.perf_counter() - started) * 1000),
                         db_path=db_path)
                return result
            finally:
                if actor_token:
                    current_actor.reset(actor_token)
                if run_token:
                    current_run_id.reset(run_token)

        return inner

    return wrap
