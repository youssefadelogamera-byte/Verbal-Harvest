"""Start, pause and resume agent runs.

A run is a LangGraph thread checkpointed to SQLite, so it survives the process: the agent
stops at a teacher gate (an approval, or a question about a missing record), the teacher
answers hours later in the review page, and `resume`
picks the run up exactly where it stopped. A small JSON file per run holds what the UI shows.
"""

from __future__ import annotations

import asyncio
import json
import threading
import traceback
from datetime import datetime
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from .. import db
from ..config import get_settings
from .llm import PROVIDERS, Usage, chat_model, scrub
from .mcp_io import McpHub
from .workflow import RESOURCES, build_graph


def _runs_dir() -> Path:
    path = get_settings().db_path.parent / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _record_path(run_id: str) -> Path:
    return _runs_dir() / f"{run_id}.json"


def _save(record: dict) -> dict:
    _record_path(record["run_id"]).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def status(run_id: str) -> dict:
    path = _record_path(run_id)
    if not path.exists():
        raise ValueError(f"Unknown run {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs() -> list[dict]:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in _runs_dir().glob("run_*.json")]
    return sorted(records, key=lambda r: r.get("started_at", ""), reverse=True)


async def _drive(run_id: str, graph_input) -> dict:
    """Run the graph until it finishes or stops at a teacher gate."""
    record = status(run_id)
    settings = get_settings()
    usage = Usage()
    checkpoints = settings.db_path.parent / "checkpoints.db"
    try:
        needs_converter = (bool(record["task"].get("inbox_file")) and not record.get("steps")) \
            or _answered_with_a_file(record.get("pending") or {})
        async with AsyncSqliteSaver.from_conn_string(str(checkpoints)) as saver, \
                McpHub(run_id, settings.db_path, with_converter=needs_converter) as hub:
            RESOURCES[run_id] = {"hub": hub, "usage": usage,
                                 "llm": chat_model(record.get("which_model", "local"), record.get("model"))}
            graph = build_graph().compile(checkpointer=saver)
            config = {"configurable": {"thread_id": run_id}, "recursion_limit": 50}
            result = await graph.ainvoke(graph_input, config)
            interrupts = result.get("__interrupt__") or []
            # A teacher may have decided the last item while the gate was being checked. If
            # nothing is undecided any more, continue straight away instead of waiting forever.
            while interrupts and not _still_undecided(interrupts[0].value):
                result = await graph.ainvoke(_resume_input(), config)
                interrupts = result.get("__interrupt__") or []
            record["steps"] = result.get("steps", [])
            record["open_questions"] = result.get("open_questions", [])
            record["finding_ids"] = result.get("finding_ids", [])
            record["summary_ids"] = result.get("summary_ids", [])
            record["request_ids"] = result.get("request_ids", [])
            if interrupts:
                record["status"] = "waiting_for_teacher"
                record["pending"] = interrupts[0].value
            else:
                record["status"] = "done"
                record["pending"] = None
    except Exception as exc:  # noqa: BLE001 - record the failure honestly for the UI and evals
        record["status"] = "failed"
        record["error"] = scrub(f"{type(exc).__name__}: {exc}")      # a provider error must never carry a key
        record["trace"] = scrub(traceback.format_exc()[-1500:])
    finally:
        RESOURCES.pop(run_id, None)
    totals = record.setdefault("usage", {"calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0})
    for key, value in usage.as_dict().items():
        totals[key] = round(totals.get(key, 0) + value, 1)
    record["updated_at"] = db.now_iso()
    _save(record)
    # Last check, after the waiting state is visible to the web app: if the final decision
    # slipped in just before it was saved, nobody else will resume this run.
    if record["status"] == "waiting_for_teacher" and not _still_undecided(record["pending"]):
        resume(run_id)
    return record


# What each gate waits on: the table, and the status that means "a teacher has not acted yet".
_GATES = {"findings": ("findings", "proposed"), "summaries": ("summaries", "draft"),
          "records": ("record_requests", "open")}


def _answered_with_a_file(pending: dict) -> bool:
    """True when the run is resuming after a teacher answered a record request with a file,
    so the document converter is needed again."""
    ids = pending.get("waiting_for") or []
    if pending.get("gate") != "records" or not ids:
        return False
    with db.connect() as conn:
        marks = ",".join("?" * len(ids))
        row = db.one(conn, f"SELECT COUNT(*) AS n FROM record_requests WHERE answer_file IS NOT NULL AND id IN ({marks})",
                     tuple(ids))
    return row["n"] > 0


def _still_undecided(pending: dict) -> bool:
    """True while a teacher still has to decide something this run is waiting for."""
    table, open_status = _GATES[pending.get("gate")]
    ids = pending.get("waiting_for") or []
    if not ids:
        return False
    with db.connect() as conn:
        marks = ",".join("?" * len(ids))
        row = db.one(conn, f"SELECT COUNT(*) AS n FROM {table} WHERE status = ? AND id IN ({marks})", (open_status, *ids))
    return row["n"] > 0


STALE_AFTER_SECONDS = 15 * 60


def _open_run_for(learner_id: str) -> dict | None:
    """A run for this learner that is still running or waiting for a teacher.
    Two runs at once would both propose the same findings. A run left 'running' by a
    process that died is marked failed so it does not block the learner forever."""
    for record in list_runs():
        if record["task"].get("learner_id") != learner_id or record["status"] not in ("running", "waiting_for_teacher"):
            continue
        age = (datetime.fromisoformat(db.now_iso()) - datetime.fromisoformat(record["updated_at"])).total_seconds()
        if record["status"] == "running" and age > STALE_AFTER_SECONDS:
            _save({**record, "status": "failed", "error": "The process running this run stopped before it finished."})
            continue
        return record
    return None


def _new_record(task: dict) -> dict:
    if not task.get("learner_id"):
        raise ValueError("task needs a learner_id")
    open_run = _open_run_for(task["learner_id"])
    if open_run:
        raise ValueError(f"This learner already has an open run ({open_run['run_id']}, {open_run['status']}). "
                         "Decide what is waiting, or wait for it to finish, before starting another.")
    settings = get_settings()
    which = task.get("which_model", "local")
    if which != "frontier" and which not in PROVIDERS:
        raise ValueError(f"Unknown model provider '{which}'.")
    if which in PROVIDERS and PROVIDERS[which].cloud and not task.get("model"):
        raise ValueError(f"Choose a model for {PROVIDERS[which].label}.")
    return _save({
        "run_id": db.new_id("run"), "task": task, "status": "running", "steps": [], "pending": None,
        "which_model": which,
        "model": task.get("model") or (settings.frontier_model if which == "frontier" else settings.llm_model),
        "started_at": db.now_iso(), "updated_at": db.now_iso(),
    })


def _initial_state(record: dict) -> dict:
    task = record["task"]
    return {"run_id": record["run_id"], "learner_id": task["learner_id"], "inbox_file": task.get("inbox_file"), "steps": []}


_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _agent_loop() -> asyncio.AbstractEventLoop:
    """One long-lived event loop, in its own thread, for every run in this process.
    The model client keeps network connections tied to the loop that created them, so
    starting a new loop per run breaks the second run ("Event loop is closed")."""
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, name="athar-agent", daemon=True).start()
        return _loop


def _submit(coroutine):
    return asyncio.run_coroutine_threadsafe(coroutine, _agent_loop())


def _resume_input() -> Command:
    return Command(resume={"resumed_at": db.now_iso()})


def run_blocking(task: dict) -> dict:
    """Start a run and wait until it finishes or reaches a teacher gate. Used by the CLI and evals."""
    record = _new_record(task)
    return _submit(_drive(record["run_id"], _initial_state(record))).result()


_claim_lock = threading.Lock()


def _claim_waiting(run_id: str) -> bool:
    """Atomically move a run from waiting to running. Two decisions arriving together
    must not both resume the same run."""
    with _claim_lock:
        record = status(run_id)
        if record["status"] != "waiting_for_teacher":
            return False
        _save({**record, "status": "running", "updated_at": db.now_iso()})
        return True


def resume_blocking(run_id: str) -> dict:
    if not _claim_waiting(run_id):
        raise ValueError(f"Run {run_id} is {status(run_id)['status']}, not waiting for a teacher.")
    return _submit(_drive(run_id, _resume_input())).result()


def start(task: dict) -> dict:
    """Start a run in the background. Poll `status(run_id)`."""
    record = _new_record(task)
    _submit(_drive(record["run_id"], _initial_state(record)))
    return {"run_id": record["run_id"], "status": "running"}


def resume(run_id: str) -> dict:
    """Continue a run after the teacher has decided. Safe to call when nothing is pending."""
    if not _claim_waiting(run_id):
        return {"run_id": run_id, "status": status(run_id)["status"]}
    _submit(_drive(run_id, _resume_input()))
    return {"run_id": run_id, "status": "running"}
