"""The service layer. These twelve functions are the MCP tools. Each is audited, takes keyword
arguments only (so the audit log records every input), and returns a JSON-able dict.

Errors raise ValueError with a message a caller can act on. Nothing here approves anything:
approval lives in review.py, which is never exposed over MCP."""

from __future__ import annotations

from . import audit, db, graph, guard
from .audit import audited
from .curriculum import load_pack

EVIDENCE_KINDS = ("quiz_item", "assignment", "project", "observation", "attendance")
FINDING_KINDS = ("root_cause", "strength", "struggle", "what_worked")
NEEDS_TWO_ROWS = ("root_cause", "strength", "struggle")
AUDIENCES = ("teacher_handover", "guardian")
FINDING_STATUSES = ("proposed", "approved", "edited", "rejected")
SUMMARY_STATUSES = ("draft", "approved", "rejected")
REQUEST_STATUSES = ("open", "provided", "no_record")
MIN_PATTERN_PERIODS = 3
MAX_TIMELINE_ROWS = 1000


def _learner(conn, learner_id: str) -> dict:
    learner = db.one(conn, "SELECT * FROM learners WHERE id = ?", (learner_id,))
    if learner is None:
        raise ValueError(f"Unknown learner '{learner_id}'. Call list_learners to see valid ids.")
    return learner


def _caller() -> str:
    """Who is proposing: the agent run id when there is one, else the actor."""
    return audit.current_run_id.get() or audit.current_actor.get()


def _check_text(text: str, what: str) -> None:
    problems = guard.check_statement(text)
    if problems:
        raise ValueError(f"The {what} was rejected: " + " | ".join(problems))


def learner_rows(conn, names: bool = False) -> list[dict]:
    """Every learner with the grade of their latest evidence. Shared with the web app, which
    lists learners for a teacher without writing an agent row to the audit log. Only the web app
    asks for `names`: an MCP client gets aliases and nothing else."""
    found = db.rows(conn, """
        SELECT l.id AS learner_id, l.alias, l.display_name, l.home_language, l.start_grade,
               MAX(e.grade) AS latest_grade, COUNT(e.id) AS evidence_count
        FROM learners l LEFT JOIN evidence e ON e.learner_id = l.id AND e.status != 'retracted'
        GROUP BY l.id ORDER BY l.alias COLLATE NOCASE, l.id""")
    return [{"learner_id": r["learner_id"], "alias": r["alias"],
             **({"name": r["display_name"] or r["alias"]} if names else {}),
             "grade_now": r["latest_grade"] or r["start_grade"],
             "home_language": r["home_language"], "evidence_count": r["evidence_count"]} for r in found]


def check_min_periods(min_periods: int) -> None:
    """The evidence bar cannot be lowered by any caller: fewer than 3 terms is not a pattern."""
    if min_periods < MIN_PATTERN_PERIODS:
        raise ValueError(f"A pattern needs at least {MIN_PATTERN_PERIODS} terms of data.")


# ---------------------------------------------------------------- read tools

@audited("list_learners")
def list_learners(*, db_path=None) -> dict:
    """Every learner with an alias, current grade, home language and evidence count."""
    with db.connect(db_path) as conn:
        return {"learners": learner_rows(conn)}


@audited("get_learner_timeline")
def get_learner_timeline(*, learner_id: str, since_year: int | None = None, concept_id: str | None = None,
                         limit: int = 200, db_path=None) -> dict:
    """The learner's most recent evidence (up to `limit` rows), grouped by period, oldest first."""
    if not 1 <= limit <= MAX_TIMELINE_ROWS:
        raise ValueError(f"limit must be between 1 and {MAX_TIMELINE_ROWS}, got {limit}.")
    sql = "SELECT * FROM evidence WHERE learner_id = ? AND status != 'retracted'"
    params: list = [learner_id]
    if since_year is not None:
        sql += " AND year >= ?"
        params.append(since_year)
    if concept_id is not None:
        sql += " AND concept_id = ?"
        params.append(concept_id)
    sql += " ORDER BY period_ord DESC, id DESC LIMIT ?"
    params.append(limit)
    with db.connect(db_path) as conn:
        learner = _learner(conn, learner_id)
        items = list(reversed(db.rows(conn, sql, tuple(params))))
    periods: dict[str, list[dict]] = {}
    for item in items:
        periods.setdefault(db.period_label(item["period_ord"]), []).append(item)
    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
    learner.pop("display_name", None)   # a name is for the teacher's screen, never for a tool result
    return {"learner": learner,
            "periods": [{"period": p, "items": rows} for p, rows in periods.items()],
            "counts": {"items": len(items), "by_kind": by_kind,
                       "needs_review": sum(i["status"] == "needs_review" for i in items)}}


@audited("find_patterns")
def find_patterns(*, learner_id: str, min_periods: int = 3, db_path=None) -> dict:
    """Strengths and struggles that held for several periods. See graph.find_patterns.
    The evidence bar cannot be lowered: fewer than 3 periods is refused."""
    check_min_periods(min_periods)
    return graph.find_patterns(learner_id, min_periods, db_path=db_path)


@audited("trace_root")
def trace_root(*, learner_id: str, concept_id: str, db_path=None) -> dict:
    """Walk prerequisites back to where a struggle starts. See graph.trace_root."""
    return graph.trace_root(learner_id, concept_id, db_path=db_path)


@audited("what_worked")
def what_worked(*, learner_id: str, db_path=None) -> dict:
    """Teaching approaches followed by clear gains for this learner. See graph.what_worked."""
    return graph.what_worked(learner_id, db_path=db_path)


def _select_decided(conn, table: str, learner_id: str, ids: list[str] | None, status: str | None,
                    statuses: tuple[str, ...]) -> list[dict]:
    """Rows of `findings` or `summaries` for one learner, with the deciding teacher's name."""
    if status is not None and status not in statuses:
        raise ValueError(f"Unknown status '{status}'. Use one of: {', '.join(statuses)}.")
    _learner(conn, learner_id)
    sql = (f"SELECT x.*, t.name AS decided_by_name FROM {table} x "
           "LEFT JOIN teachers t ON t.id = x.decided_by WHERE x.learner_id = ?")
    params: list = [learner_id]
    if ids is not None:
        sql += f" AND x.id IN ({','.join('?' for _ in ids) or 'NULL'})"
        params += ids
    if status is not None:
        sql += " AND x.status = ?"
        params.append(status)
    return db.rows(conn, sql + " ORDER BY x.rowid", tuple(params))


@audited("get_findings")
def get_findings(*, learner_id: str, finding_ids: list[str] | None = None, status: str | None = None,
                 db_path=None) -> dict:
    """Findings for a learner and what a teacher decided about them."""
    with db.connect(db_path) as conn:
        found = _select_decided(conn, "findings", learner_id, finding_ids, status, FINDING_STATUSES)
    return {"findings": [{"finding_id": f["id"], "kind": f["kind"], "statement": f["statement"],
                          "concept_ids": db.jload(f["concept_ids"], []),
                          "evidence_ids": db.jload(f["evidence_ids"], []), "confidence": f["confidence"],
                          "status": f["status"], "proposed_by": f["proposed_by"], "proposed_at": f["proposed_at"],
                          "decided_by_name": f["decided_by_name"], "decided_at": f["decided_at"],
                          "teacher_note": f["teacher_note"]} for f in found]}


@audited("get_summaries")
def get_summaries(*, learner_id: str, summary_ids: list[str] | None = None, status: str | None = None,
                  db_path=None) -> dict:
    """Summary drafts for a learner and what a teacher decided about them."""
    with db.connect(db_path) as conn:
        found = _select_decided(conn, "summaries", learner_id, summary_ids, status, SUMMARY_STATUSES)
    return {"summaries": [{"summary_id": s["id"], "audience": s["audience"], "language": s["language"],
                           "text": s["text"], "finding_ids": db.jload(s["finding_ids"], []),
                           "status": s["status"], "created_at": s["created_at"],
                           "decided_by_name": s["decided_by_name"], "decided_at": s["decided_at"]}
                          for s in found]}


@audited("get_record_requests")
def get_record_requests(*, learner_id: str, request_ids: list[str] | None = None, status: str | None = None,
                        db_path=None) -> dict:
    """Questions asked about holes in a learner's record, and what a teacher answered."""
    if status is not None and status not in REQUEST_STATUSES:
        raise ValueError(f"Unknown status '{status}'. Use one of: {', '.join(REQUEST_STATUSES)}.")
    sql = ("SELECT r.*, t.name AS answered_by_name FROM record_requests r "
           "LEFT JOIN teachers t ON t.id = r.answered_by WHERE r.learner_id = ?")
    params: list = [learner_id]
    if request_ids is not None:
        sql += f" AND r.id IN ({','.join('?' for _ in request_ids) or 'NULL'})"
        params += request_ids
    if status is not None:
        sql += " AND r.status = ?"
        params.append(status)
    with db.connect(db_path) as conn:
        _learner(conn, learner_id)
        found = db.rows(conn, sql + " ORDER BY r.rowid", tuple(params))
    return {"requests": [{"request_id": r["id"], "concept_id": r["concept_id"],
                          "about_concept_id": r["about_concept_id"], "question": r["question"],
                          "status": r["status"], "asked_by": r["asked_by"], "asked_at": r["asked_at"],
                          "answered_by_name": r["answered_by_name"], "answered_at": r["answered_at"],
                          "answer_text": r["answer_text"], "answer_file": r["answer_file"],
                          "answer_year": r["answer_year"], "answer_term": r["answer_term"]} for r in found]}


# ---------------------------------------------------------------- write tools

def _validate_evidence(kind: str, term: int, score: float | None) -> None:
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"Unknown evidence kind '{kind}'. Use one of: {', '.join(EVIDENCE_KINDS)}.")
    if term not in (1, 2, 3):
        raise ValueError(f"Term must be 1, 2 or 3, got {term}.")
    if score is not None and not 0 <= score <= 1:
        raise ValueError(f"Score must be between 0 and 1, got {score}. Divide marks by the maximum.")


def _check_reference(conn, table: str, ref_id: str | None) -> None:
    if ref_id is not None and db.one(conn, f"SELECT id FROM {table} WHERE id = ?", (ref_id,)) is None:
        raise ValueError(f"Unknown id '{ref_id}' in {table}.")


def _curriculum_warnings(pack_id: str, concept_id: str | None, skill_id: str | None) -> list[str]:
    """Ids the learner's pack does not know. Such rows are kept but set aside for review."""
    pack = load_pack(pack_id)
    warnings = []
    if concept_id is not None and concept_id not in pack.concepts:
        warnings.append(f"Concept '{concept_id}' is not in pack '{pack.id}'; stored as needs_review.")
    if skill_id is not None and skill_id not in pack.skills:
        warnings.append(f"Skill '{skill_id}' is not in pack '{pack.id}'; stored as needs_review.")
    return warnings


@audited("record_evidence")
def record_evidence(*, learner_id: str, kind: str, year: int, term: int, grade: int, source_ref: str,
                    concept_id: str | None = None, skill_id: str | None = None, score: float | None = None,
                    absent_days: int | None = None, raw_text: str | None = None, language: str = "en",
                    teacher_id: str | None = None, unit_id: str | None = None, logged_late: bool = False,
                    db_path=None) -> dict:
    """Store one evidence row. A repeated (learner, source_ref) returns the existing row instead."""
    _validate_evidence(kind, term, score)
    with db.connect(db_path) as conn:
        learner = _learner(conn, learner_id)
        existing = db.one(conn, "SELECT id, status FROM evidence WHERE learner_id = ? AND source_ref = ?",
                          (learner_id, source_ref))
        if existing:
            return {"evidence_id": existing["id"], "status": existing["status"],
                    "warnings": [f"Already recorded from '{source_ref}'; returned the existing row."]}
        _check_reference(conn, "teachers", teacher_id)
        _check_reference(conn, "teaching_units", unit_id)
        warnings = _curriculum_warnings(learner["pack_id"], concept_id, skill_id)
        evidence_id = db.new_id("evd")
        status = "needs_review" if warnings else "active"
        conn.execute(
            "INSERT INTO evidence (id, learner_id, kind, year, term, period_ord, grade, concept_id, skill_id, "
            "score, absent_days, raw_text, language, source_ref, teacher_id, unit_id, recorded_at, "
            "logged_late, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (evidence_id, learner_id, kind, year, term, db.period_ord(year, term), grade, concept_id, skill_id,
             score, absent_days, raw_text, language, source_ref, teacher_id, unit_id, db.now_iso(),
             int(logged_late), status))
    return {"evidence_id": evidence_id, "status": status, "warnings": warnings}


def _check_evidence(conn, learner_id: str, kind: str, evidence_ids: list[str]) -> None:
    """Every cited row must exist and belong to this learner. No evidence, no finding."""
    if not evidence_ids:
        raise ValueError("A finding must cite at least one evidence id. No evidence, no finding.")
    if kind in NEEDS_TWO_ROWS and len(set(evidence_ids)) < 2:
        raise ValueError(f"A '{kind}' finding must cite at least 2 evidence rows.")
    for evidence_id in evidence_ids:
        row = db.one(conn, "SELECT learner_id FROM evidence WHERE id = ?", (evidence_id,))
        if row is None:
            raise ValueError(f"Evidence '{evidence_id}' does not exist.")
        if row["learner_id"] != learner_id:
            raise ValueError(f"Evidence '{evidence_id}' belongs to another learner and cannot be cited here.")


@audited("propose_finding")
def propose_finding(*, learner_id: str, kind: str, statement: str, evidence_ids: list[str],
                    concept_ids: list[str] | None = None, path: list[str] | None = None,
                    confidence: float = 0.5, db_path=None) -> dict:
    """Store a finding as 'proposed'. Only a named teacher can approve it (review.py)."""
    if kind not in FINDING_KINDS:
        raise ValueError(f"Unknown finding kind '{kind}'. Use one of: {', '.join(FINDING_KINDS)}.")
    if not 0 <= confidence <= 1:
        raise ValueError(f"Confidence must be between 0 and 1, got {confidence}.")
    _check_text(statement, "statement")
    with db.connect(db_path) as conn:
        _learner(conn, learner_id)
        _check_evidence(conn, learner_id, kind, evidence_ids)
        finding_id = db.new_id("fnd")
        conn.execute(
            "INSERT INTO findings (id, learner_id, kind, statement, concept_ids, evidence_ids, path, "
            "confidence, status, proposed_by, proposed_at) VALUES (?,?,?,?,?,?,?,?,'proposed',?,?)",
            (finding_id, learner_id, kind, statement, db.jdump(concept_ids or []), db.jdump(evidence_ids),
             db.jdump(path or []), confidence, _caller(), db.now_iso()))
    return {"finding_id": finding_id, "status": "proposed"}


@audited("draft_summary")
def draft_summary(*, learner_id: str, finding_ids: list[str], audience: str, language: str, text: str,
                  db_path=None) -> dict:
    """Store a summary draft built only from approved findings. It needs its own approval."""
    if audience not in AUDIENCES:
        raise ValueError(f"Unknown audience '{audience}'. Use one of: {', '.join(AUDIENCES)}.")
    if not finding_ids:
        raise ValueError("A summary must be built from at least one approved finding.")
    _check_text(text, "summary text")
    with db.connect(db_path) as conn:
        _learner(conn, learner_id)
        for finding_id in finding_ids:
            finding = db.one(conn, "SELECT learner_id, status FROM findings WHERE id = ?", (finding_id,))
            if finding is None or finding["learner_id"] != learner_id:
                raise ValueError(f"Finding '{finding_id}' does not exist for learner '{learner_id}'.")
            if finding["status"] not in ("approved", "edited"):
                raise ValueError(f"Finding '{finding_id}' is '{finding['status']}'. A teacher must approve "
                                 "it before it can be used in a summary.")
        summary_id = db.new_id("sum")
        conn.execute(
            "INSERT INTO summaries (id, learner_id, audience, language, text, finding_ids, status, "
            "created_by, created_at) VALUES (?,?,?,?,?,?,'draft',?,?)",
            (summary_id, learner_id, audience, language, text, db.jdump(finding_ids), _caller(), db.now_iso()))
    return {"summary_id": summary_id, "status": "draft"}


@audited("request_record")
def request_record(*, learner_id: str, concept_id: str, question: str, about_concept_id: str | None = None,
                   db_path=None) -> dict:
    """Ask a teacher for a record of a topic the learner has no scored evidence for. It only asks:
    the answer comes from a named teacher (review.py). A teacher is asked about a topic once."""
    _check_text(question, "question")
    with db.connect(db_path) as conn:
        learner = _learner(conn, learner_id)
        pack = load_pack(learner["pack_id"])
        for concept in (concept_id, about_concept_id):
            if concept is not None and concept not in pack.concepts:
                raise ValueError(f"Unknown concept '{concept}' in pack '{pack.id}'.")
        have = db.one(conn, "SELECT COUNT(*) AS n FROM evidence WHERE learner_id = ? AND concept_id = ? "
                            "AND score IS NOT NULL AND status = 'active'", (learner_id, concept_id))["n"]
        if have:
            raise ValueError(f"There are already {have} scored records for '{concept_id}'. Read them with "
                             "get_learner_timeline instead of asking a teacher.")
        asked = db.one(conn, "SELECT id, status FROM record_requests WHERE learner_id = ? AND concept_id = ? "
                             "ORDER BY rowid DESC", (learner_id, concept_id))
        if asked and asked["status"] == "open":
            return {"request_id": asked["id"], "status": "open",
                    "warnings": ["Already asked and still waiting for a teacher; returned the existing request."]}
        if asked:
            raise ValueError(f"A teacher already answered a request about '{concept_id}' ({asked['status']}). "
                             "A teacher is not asked the same question twice.")
        request_id = db.new_id("req")
        conn.execute(
            "INSERT INTO record_requests (id, learner_id, concept_id, about_concept_id, question, status, "
            "asked_by, asked_at) VALUES (?,?,?,?,?,'open',?,?)",
            (request_id, learner_id, concept_id, about_concept_id, question, _caller(), db.now_iso()))
    return {"request_id": request_id, "status": "open", "warnings": []}
