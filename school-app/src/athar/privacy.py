"""Looking after the records: a backup copy, one learner's record as a file, and deleting one learner.

These are the school admin's jobs. None of them is an MCP tool, so the agent cannot reach them.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from . import audit, db
from .config import get_settings

KEEP_BACKUPS = 14


def backups_dir() -> Path:
    return get_settings().db_path.parent / "backups"


def make_backup(folder: Path | str | None = None, actor: str = "system", db_path=None) -> dict[str, Any]:
    """Copy the whole database to one file, safely, while the app is running. Old copies beyond the
    newest 14 in the default folder are removed. The copy holds everything the database holds, names
    included, so keep it as carefully as the database."""
    started = time.perf_counter()
    source = Path(db_path) if db_path else get_settings().db_path
    if not source.exists():
        raise ValueError("There is no database to back up yet.")
    default = folder is None
    target_dir = Path(folder) if folder else backups_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"athar-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    n = 1
    while target.exists():
        n += 1
        target = target_dir / f"{target.stem.split('_')[0]}_{n}.db"
    src = sqlite3.connect(source, timeout=30)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    removed = 0
    if default:
        for old in sorted(target_dir.glob("athar-*.db"), reverse=True)[KEEP_BACKUPS:]:
            old.unlink()
            removed += 1
    out = {"file": target.name, "folder": str(target_dir), "bytes": target.stat().st_size, "old_copies_removed": removed}
    audit.log_call("backup", {"folder": "default" if default else "chosen"}, {"file": target.name, "bytes": out["bytes"]},
                   True, int((time.perf_counter() - started) * 1000), actor=actor, db_path=db_path)
    return {**out, "path": str(target)}


def list_backups() -> list[dict[str, Any]]:
    folder = backups_dir()
    files = sorted(folder.glob("athar-*.db"), reverse=True) if folder.is_dir() else []
    return [{"file": p.name, "bytes": p.stat().st_size,
             "made_at": dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")} for p in files]


def restore_backup(path: Path | str, db_path=None) -> dict[str, Any]:
    """Replace the database with a backup copy. Stop the app first. The current database is kept
    beside it as a `.before-restore` file."""
    source, target = Path(path), Path(db_path) if db_path else get_settings().db_path
    if not source.is_file():
        raise ValueError(f"No backup file at {source}.")
    check = sqlite3.connect(source)
    try:
        tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.DatabaseError as exc:
        raise ValueError("That file is not a database backup.") from exc
    finally:
        check.close()
    if not {"learners", "evidence", "audit_log"} <= tables:
        raise ValueError("That file is not a backup of this product.")
    kept = None
    if target.exists():
        kept = target.with_name(target.name + ".before-restore")
        make = sqlite3.connect(target, timeout=30)
        try:
            copy = sqlite3.connect(kept)
            try:
                make.backup(copy)
            finally:
                copy.close()
        finally:
            make.close()
    src = sqlite3.connect(source)
    try:
        dst = sqlite3.connect(target, timeout=30)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    audit.log_call("restore_backup", {"file": source.name}, {"restored": True}, True, 0, actor="system", db_path=db_path)
    return {"restored_from": str(source), "previous_kept_as": str(kept) if kept else None}


_LEARNER_TABLES = ("evidence", "findings", "summaries", "record_requests")


def export_learner(learner_id: str, actor: str = "system", db_path=None) -> dict[str, Any]:
    """Everything held about one learner, as plain data, for a family that asks what the school holds."""
    with db.connect(db_path) as conn:
        learner = db.one(conn, "SELECT * FROM learners WHERE id = ?", (learner_id,))
        if learner is None:
            raise ValueError(f"Unknown learner '{learner_id}'.")
        out: dict[str, Any] = {"exported_at": db.now_iso(), "learner": learner}
        for table in _LEARNER_TABLES:
            out[table] = db.rows(conn, f"SELECT * FROM {table} WHERE learner_id = ? ORDER BY id", (learner_id,))
        ids = [row["id"] for row in out["findings"]] + [row["id"] for row in out["summaries"]]
        out["decisions"] = db.rows(conn, f"SELECT * FROM approvals WHERE target_id IN ({','.join('?' for _ in ids)}) "
                                         "ORDER BY id", tuple(ids)) if ids else []
        out["classes"] = db.rows(conn, "SELECT c.name, c.grade, c.year FROM class_learners cl JOIN classes c "
                                       "ON c.id = cl.class_id WHERE cl.learner_id = ? ORDER BY c.year", (learner_id,))
        audit.write_row(conn, "export_learner", {"learner_id": learner_id},
                        {table: len(out[table]) for table in _LEARNER_TABLES}, True, 0, actor=actor)
    return out


def delete_learner(learner_id: str, confirm_code: str, actor: str = "system", db_path=None) -> dict[str, Any]:
    """Delete one learner's record for good: the learner, every record, finding, note and question about
    them, the agent runs about them, and inbox files named with their record code. Rows of the audit log
    that mention them are blanked, and one new row says that a record was deleted, without a name.

    `confirm_code` must be the learner's record code (such as K-42), typed by the person deleting.
    This cannot be undone. Backup copies made earlier still hold the record until they are deleted too.
    """
    started = time.perf_counter()
    data_dir = (Path(db_path).parent if db_path else get_settings().db_path.parent)
    with db.connect(db_path) as conn:
        learner = db.one(conn, "SELECT id, alias FROM learners WHERE id = ?", (learner_id,))
        if learner is None:
            raise ValueError(f"Unknown learner '{learner_id}'.")
        code = learner["alias"].replace("Learner ", "").strip()
        if str(confirm_code or "").strip().upper() != code.upper():
            raise ValueError(f"To delete this record, type its record code exactly: {code}.")
        counts: dict[str, int] = {}
        targets = [r["id"] for r in db.rows(conn, "SELECT id FROM findings WHERE learner_id = ?", (learner_id,))]
        targets += [r["id"] for r in db.rows(conn, "SELECT id FROM summaries WHERE learner_id = ?", (learner_id,))]
        if targets:
            counts["decisions"] = conn.execute(
                f"DELETE FROM approvals WHERE target_id IN ({','.join('?' for _ in targets)})", tuple(targets)).rowcount
        for table in ("record_requests", "summaries", "findings", "evidence"):
            counts[table] = conn.execute(f"DELETE FROM {table} WHERE learner_id = ?", (learner_id,)).rowcount
        conn.execute("DELETE FROM class_learners WHERE learner_id = ?", (learner_id,))
        counts["parent_links"] = conn.execute("DELETE FROM parent_learners WHERE learner_id = ?", (learner_id,)).rowcount
        blank = db.jdump({"removed": "this learner's record was deleted"})
        counts["audit_rows_blanked"] = conn.execute(
            "UPDATE audit_log SET input = ?, output = ? WHERE input LIKE ? OR output LIKE ? OR input LIKE ? OR output LIKE ?",
            (blank, blank, f"%{learner_id}%", f"%{learner_id}%", f"%{learner['alias']}%", f"%{learner['alias']}%")).rowcount
        conn.execute("DELETE FROM learners WHERE id = ?", (learner_id,))
        audit.write_row(conn, "delete_learner", {"record": "one learner"}, counts, True,
                        int((time.perf_counter() - started) * 1000), actor=actor)

    runs_gone, run_ids = 0, []
    runs = data_dir / "runs"
    for path in (runs.glob("run_*.json") if runs.is_dir() else []):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if learner_id in json.dumps(record.get("task") or {}) or record.get("learner_id") == learner_id:
            run_ids.append(record.get("run_id") or path.stem)
            path.unlink()
            runs_gone += 1
    checkpoints = data_dir / "checkpoints.db"
    if run_ids and checkpoints.exists():
        conn2 = sqlite3.connect(checkpoints, timeout=30)
        try:
            for table in ("checkpoints", "writes"):
                try:
                    conn2.execute(f"DELETE FROM {table} WHERE thread_id IN ({','.join('?' for _ in run_ids)})",
                                  tuple(run_ids))
                except sqlite3.OperationalError:
                    pass
            conn2.commit()
        finally:
            conn2.close()
    files_gone = 0
    inbox = data_dir / "inbox"
    for path in (inbox.iterdir() if inbox.is_dir() else []):
        if path.is_file() and re.search(rf"(?<![A-Z0-9]){re.escape(code.upper())}(?![0-9])", path.name.upper()):
            path.unlink()
            files_gone += 1
    return {"deleted": True, "code": code, **counts, "agent_runs_removed": runs_gone, "inbox_files_removed": files_gone,
            "backups_that_still_hold_it": [b["file"] for b in list_backups()]}


def withdraw_record(evidence_id: str, teacher_id: str, reason: str, db_path=None) -> dict[str, Any]:
    """Take one wrong record out of the analysis. The row is kept, marked as withdrawn, with who did it and
    why in the audit log, so a correction is never a silent edit. Findings that cite it are listed, because
    a teacher should look at them again."""
    reason = " ".join(str(reason or "").split())[:200]
    if len(reason) < 3:
        raise ValueError("Say in a few words why this record is wrong.")
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT id, learner_id, status FROM evidence WHERE id = ?", (evidence_id,))
        if row is None:
            raise ValueError(f"Unknown record '{evidence_id}'.")
        if db.one(conn, "SELECT id FROM teachers WHERE id = ?", (teacher_id,)) is None:
            raise ValueError("Only a named teacher can withdraw a record. Choose your name first.")
        if row["status"] == "retracted":
            raise ValueError("This record was already withdrawn.")
        conn.execute("UPDATE evidence SET status = 'retracted' WHERE id = ?", (evidence_id,))
        cited = [f["id"] for f in db.rows(conn, "SELECT id, evidence_ids FROM findings WHERE learner_id = ? "
                                                "AND status != 'rejected'", (row["learner_id"],))
                 if evidence_id in db.jload(f["evidence_ids"], [])]
        out = {"evidence_id": evidence_id, "status": "retracted", "findings_that_cite_it": cited}
        audit.write_row(conn, "withdraw_record", {"evidence_id": evidence_id, "reason": reason}, out, True, 0,
                        actor=f"teacher:{teacher_id}")
    return out
