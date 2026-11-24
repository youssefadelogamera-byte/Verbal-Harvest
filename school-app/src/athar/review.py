"""Teacher decisions. Only a named teacher approves, edits or rejects a finding or a note, or answers
the agent's question about a missing record. These functions are never exposed over MCP; the web app
calls them for a teacher chosen by name."""

from __future__ import annotations

import time

from . import audit, db, guard
from .curriculum import load_pack
from .explain import explain

FINDING_DECISIONS = ("approved", "edited", "rejected")
SUMMARY_DECISIONS = ("approved", "rejected")
REQUEST_ANSWERS = ("provided", "no_record")


def expand_finding(conn, finding: dict) -> dict:
    """A finding with its JSON fields decoded, its cited evidence rows attached, and a plain
    explanation computed from those rows (never from a model)."""
    finding = dict(finding, concept_ids=db.jload(finding["concept_ids"], []),
                   evidence_ids=db.jload(finding["evidence_ids"], []), path=db.jload(finding["path"], []))
    marks = ",".join("?" for _ in finding["evidence_ids"])
    finding["evidence"] = db.rows(conn, f"SELECT * FROM evidence WHERE id IN ({marks}) ORDER BY period_ord, id",
                                  tuple(finding["evidence_ids"])) if marks else []
    learner = db.one(conn, "SELECT pack_id FROM learners WHERE id = ?", (finding["learner_id"],))
    finding["explain"] = explain(finding, load_pack(learner["pack_id"])) if learner else None
    return finding


def pending(db_path=None) -> dict:
    """Findings and summaries waiting for a teacher, with the evidence behind them."""
    with db.connect(db_path) as conn:
        findings = [expand_finding(conn, f) for f in db.rows(
            conn, "SELECT * FROM findings WHERE status = 'proposed' ORDER BY proposed_at, id")]
        summaries = []
        for summary in db.rows(conn, "SELECT * FROM summaries WHERE status = 'draft' ORDER BY created_at, id"):
            ids = db.jload(summary["finding_ids"], [])
            summary = dict(summary, finding_ids=ids, findings=[
                expand_finding(conn, f) for f in db.rows(
                    conn, f"SELECT * FROM findings WHERE id IN ({','.join('?' for _ in ids)})", tuple(ids))])
            summaries.append(summary)
        requests = db.rows(conn, "SELECT r.*, l.alias AS learner_alias, l.display_name AS learner_display_name FROM record_requests r "
                                 "JOIN learners l ON l.id = r.learner_id WHERE r.status = 'open' "
                                 "ORDER BY r.asked_at, r.id")
    return {"findings": findings, "summaries": summaries, "requests": requests}


def _teacher(conn, teacher_id: str) -> dict:
    teacher = db.one(conn, "SELECT * FROM teachers WHERE id = ?", (teacher_id,))
    if teacher is None:
        raise ValueError(f"Unknown teacher '{teacher_id}'. Only a named teacher can decide.")
    return teacher


def _refuse(conn, table: str, what: str, target_id: str) -> None:
    """Say why nothing was decided: the item does not exist, or someone decided it first."""
    row = db.one(conn, f"SELECT status FROM {table} WHERE id = ?", (target_id,))
    if row is None:
        raise ValueError(f"Unknown {what.lower()} '{target_id}'.")
    raise ValueError(f"{what} '{target_id}' was already decided ({row['status']}).")


def _record_approval(conn, target_type: str, target_id: str, decision: str, teacher: dict,
                     note: str | None) -> None:
    conn.execute("INSERT INTO approvals (ts, target_type, target_id, decision, teacher_id, teacher_name, note) "
                 "VALUES (?,?,?,?,?,?,?)",
                 (db.now_iso(), target_type, target_id, decision, teacher["id"], teacher["name"], note))


def decide_finding(finding_id: str, decision: str, teacher_id: str, note: str | None = None,
                   edited_statement: str | None = None, *, db_path=None) -> dict:
    """Approve, edit or reject a proposed finding. The decision, its `approvals` row and its
    `audit_log` row are written in one transaction: all three or none."""
    started = time.perf_counter()
    if decision not in FINDING_DECISIONS:
        raise ValueError(f"Decision must be one of: {', '.join(FINDING_DECISIONS)}.")
    if decision == "edited":
        if not edited_statement:
            raise ValueError("An 'edited' decision needs the edited_statement.")
        problems = guard.check_statement(edited_statement)
        if problems:
            raise ValueError("The edited statement was rejected: " + " | ".join(problems))
    with db.connect(db_path) as conn:
        teacher = _teacher(conn, teacher_id)
        # The check and the change are one statement: of two decisions arriving together, one wins.
        changed = conn.execute(
            "UPDATE findings SET status = ?, statement = COALESCE(?, statement), decided_by = ?, "
            "decided_at = ?, teacher_note = ? WHERE id = ? AND status = 'proposed'",
            (decision, edited_statement if decision == "edited" else None, teacher_id, db.now_iso(), note,
             finding_id)).rowcount
        if not changed:
            _refuse(conn, "findings", "Finding", finding_id)
        _record_approval(conn, "finding", finding_id, decision, teacher, note)
        result = expand_finding(conn, db.one(conn, "SELECT * FROM findings WHERE id = ?", (finding_id,)))
        audit.write_row(conn, "decide_finding", {"finding_id": finding_id, "decision": decision,
                                                 "teacher_id": teacher_id, "note": note,
                                                 "edited_statement": edited_statement},
                        result, True, int((time.perf_counter() - started) * 1000), actor=f"teacher:{teacher_id}")
    return result


def decide_summary(summary_id: str, decision: str, teacher_id: str, note: str | None = None,
                   *, db_path=None) -> dict:
    """Approve or reject a summary draft. Decision, approval and audit row share one transaction."""
    started = time.perf_counter()
    if decision not in SUMMARY_DECISIONS:
        raise ValueError(f"Decision must be one of: {', '.join(SUMMARY_DECISIONS)}.")
    with db.connect(db_path) as conn:
        teacher = _teacher(conn, teacher_id)
        changed = conn.execute(
            "UPDATE summaries SET status = ?, decided_by = ?, decided_at = ? WHERE id = ? AND status = 'draft'",
            (decision, teacher_id, db.now_iso(), summary_id)).rowcount
        if not changed:
            _refuse(conn, "summaries", "Summary", summary_id)
        _record_approval(conn, "summary", summary_id, decision, teacher, note)
        result = db.one(conn, "SELECT * FROM summaries WHERE id = ?", (summary_id,))
        result["finding_ids"] = db.jload(result["finding_ids"], [])
        audit.write_row(conn, "decide_summary", {"summary_id": summary_id, "decision": decision,
                                                 "teacher_id": teacher_id, "note": note},
                        result, True, int((time.perf_counter() - started) * 1000), actor=f"teacher:{teacher_id}")
    return result


def answer_request(request_id: str, answer: str, teacher_id: str, text: str | None = None,
                   file_name: str | None = None, year: int | None = None, term: int | None = None,
                   *, db_path=None) -> dict:
    """Answer the agent's question about a missing record: 'provided' with the teacher's own words or a
    file in the inbox, or 'no_record'. The answer and its audit row share one transaction."""
    started = time.perf_counter()
    if answer not in REQUEST_ANSWERS:
        raise ValueError(f"Answer must be one of: {', '.join(REQUEST_ANSWERS)}.")
    text = (text or "").strip() or None
    if answer == "provided" and not (text or file_name):
        raise ValueError("A 'provided' answer needs the record: type it, or choose a file from the inbox.")
    if answer == "no_record":
        text, file_name, year, term = None, None, None, None
    if term is not None and term not in (1, 2, 3):
        raise ValueError(f"Term must be 1, 2 or 3, got {term}.")
    with db.connect(db_path) as conn:
        _teacher(conn, teacher_id)
        changed = conn.execute(
            "UPDATE record_requests SET status = ?, answered_by = ?, answered_at = ?, answer_text = ?, "
            "answer_file = ?, answer_year = ?, answer_term = ? WHERE id = ? AND status = 'open'",
            (answer, teacher_id, db.now_iso(), text, file_name, year, term, request_id)).rowcount
        if not changed:
            row = db.one(conn, "SELECT status FROM record_requests WHERE id = ?", (request_id,))
            if row is None:
                raise ValueError(f"Unknown request '{request_id}'.")
            raise ValueError(f"Request '{request_id}' was already answered ({row['status']}).")
        result = db.one(conn, "SELECT * FROM record_requests WHERE id = ?", (request_id,))
        audit.write_row(conn, "answer_request", {"request_id": request_id, "answer": answer,
                                                 "teacher_id": teacher_id, "text": text, "file_name": file_name,
                                                 "year": year, "term": term},
                        result, True, int((time.perf_counter() - started) * 1000), actor=f"teacher:{teacher_id}")
    return result
