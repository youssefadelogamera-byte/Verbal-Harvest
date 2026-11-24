import json

import pytest

from athar import audit, db, review, tools


def _audit_rows(db_path) -> list[dict]:
    with db.connect(db_path) as conn:
        return db.rows(conn, "SELECT * FROM audit_log ORDER BY id")


def _approve(db_path, finding_id: str) -> None:
    with db.connect(db_path) as conn:
        conn.execute("UPDATE findings SET status = 'approved', decided_by = 'tch_amina' WHERE id = ?", (finding_id,))


def _ratios_finding(db_path, **overrides) -> dict:
    args = {"learner_id": "lrn_a", "kind": "root_cause",
            "statement": "Ratio items trace back to division, first met in a term with 18 days absent.",
            "evidence_ids": ["evd_a03", "evd_a04", "evd_a05"], "concept_ids": ["ratios", "division"],
            "path": ["ratios", "fractions", "division"], "confidence": 0.67, "db_path": db_path}
    return tools.propose_finding(**(args | overrides))


def test_list_learners(db_path):
    learners = {r["learner_id"]: r for r in tools.list_learners(db_path=db_path)["learners"]}
    assert set(learners) == {"lrn_a", "lrn_b", "lrn_c", "lrn_d", "lrn_e"}
    assert learners["lrn_a"] == {"learner_id": "lrn_a", "alias": "Learner A-01", "grade_now": 4,
                                 "home_language": "ar", "evidence_count": 13}


def test_timeline_keeps_non_ascii_text(db_path):
    result = tools.get_learner_timeline(learner_id="lrn_a", concept_id="ratios", db_path=db_path)
    assert [p["period"] for p in result["periods"]] == ["2023-T1", "2023-T2", "2023-T3"]
    assert result["counts"]["items"] == 5
    observation = result["periods"][-1]["items"][-1]
    assert observation["raw_text"] == "يجد صعوبة في مقارنة الكميات"
    assert "مقارنة" in _audit_rows(db_path)[-1]["output"]


def test_timeline_limit_keeps_most_recent(db_path):
    result = tools.get_learner_timeline(learner_id="lrn_a", limit=2, db_path=db_path)
    assert [i["id"] for p in result["periods"] for i in p["items"]] == ["evd_a12", "evd_a13"]


def test_record_evidence_and_duplicate(db_path):
    first = tools.record_evidence(learner_id="lrn_b", kind="quiz_item", year=2022, term=2, grade=2,
                                  source_ref="quiz:2022-T2-maths#4", concept_id="volume", score=0.9,
                                  raw_text="Volume du pavé", language="fr", db_path=db_path)
    assert first["status"] == "active" and first["warnings"] == []
    again = tools.record_evidence(learner_id="lrn_b", kind="quiz_item", year=2022, term=2, grade=2,
                                  source_ref="quiz:2022-T2-maths#4", concept_id="volume", score=0.9,
                                  db_path=db_path)
    assert again["evidence_id"] == first["evidence_id"]
    assert "Already recorded" in again["warnings"][0]
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT * FROM evidence WHERE id = ?", (first["evidence_id"],))
    assert row["period_ord"] == 2022 * 3 + 1 and row["raw_text"] == "Volume du pavé"


def test_record_evidence_unknown_concept_needs_review(db_path):
    result = tools.record_evidence(learner_id="lrn_b", kind="quiz_item", year=2022, term=2, grade=2,
                                   source_ref="quiz:x", concept_id="calculus", score=0.5, db_path=db_path)
    assert result["status"] == "needs_review"
    assert "calculus" in result["warnings"][0]


@pytest.mark.parametrize("bad, message", [
    ({"learner_id": "lrn_zz"}, "Unknown learner"),
    ({"score": 1.5}, "between 0 and 1"),
    ({"kind": "rumour"}, "Unknown evidence kind"),
    ({"term": 4}, "Term must be"),
    ({"teacher_id": "tch_nobody"}, "Unknown id"),
])
def test_record_evidence_rejects_bad_input(db_path, bad, message):
    args = {"learner_id": "lrn_b", "kind": "quiz_item", "year": 2022, "term": 2, "grade": 2,
            "source_ref": "quiz:y", "score": 0.5, "db_path": db_path}
    with pytest.raises(ValueError, match=message):
        tools.record_evidence(**(args | bad))


def test_propose_finding_stores_proposal(db_path):
    result = _ratios_finding(db_path)
    assert result["status"] == "proposed"
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT * FROM findings WHERE id = ?", (result["finding_id"],))
    assert json.loads(row["evidence_ids"]) == ["evd_a03", "evd_a04", "evd_a05"]
    assert row["proposed_by"] == "mcp-client"


def test_propose_finding_records_agent_run(db_path):
    token = audit.current_run_id.set("run_123")
    try:
        result = _ratios_finding(db_path)
    finally:
        audit.current_run_id.reset(token)
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT proposed_by FROM findings WHERE id = ?", (result["finding_id"],))
    assert row["proposed_by"] == "run_123"
    assert _audit_rows(db_path)[-1]["run_id"] == "run_123"


@pytest.mark.parametrize("bad, message", [
    ({"evidence_ids": []}, "at least one evidence"),
    ({"evidence_ids": ["evd_a03", "evd_nope"]}, "does not exist"),
    ({"evidence_ids": ["evd_a03", "evd_b01"]}, "belongs to another learner"),
    ({"evidence_ids": ["evd_a03"]}, "at least 2"),
    ({"statement": "A lazy learner who never tries."}, "label on a child"),
    ({"statement": "Ranked below peers in ratios."}, "comparison with classmates"),
    ({"statement": "She is not suited for science."}, "track"),
])
def test_propose_finding_rejections(db_path, bad, message):
    with pytest.raises(ValueError, match=message):
        _ratios_finding(db_path, **bad)
    with db.connect(db_path) as conn:
        assert db.one(conn, "SELECT COUNT(*) AS n FROM findings")["n"] == 0


def test_single_row_is_enough_for_what_worked(db_path):
    result = tools.propose_finding(learner_id="lrn_c", kind="what_worked", evidence_ids=["evd_c03"],
                                   statement="Scores on multiplication rose after visual models.", db_path=db_path)
    assert result["status"] == "proposed"


def test_draft_summary_needs_approved_findings(db_path):
    finding_id = _ratios_finding(db_path)["finding_id"]
    args = {"learner_id": "lrn_a", "finding_ids": [finding_id], "audience": "guardian", "language": "ar",
            "text": "نعمل على القسمة أولاً ثم النسب.", "db_path": db_path}
    with pytest.raises(ValueError, match="must approve"):
        tools.draft_summary(**args)
    _approve(db_path, finding_id)
    with pytest.raises(ValueError, match="label on a child"):
        tools.draft_summary(**(args | {"text": "A slow learner in maths."}))
    with pytest.raises(ValueError, match="does not exist for learner"):
        tools.draft_summary(**(args | {"learner_id": "lrn_b"}))
    result = tools.draft_summary(**args)
    assert result["status"] == "draft"
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT text FROM summaries WHERE id = ?", (result["summary_id"],))
    assert row["text"] == "نعمل على القسمة أولاً ثم النسب."


def test_every_call_is_audited(db_path):
    calls = [
        ("list_learners", lambda: tools.list_learners(db_path=db_path)),
        ("get_learner_timeline", lambda: tools.get_learner_timeline(learner_id="lrn_e", db_path=db_path)),
        ("find_patterns", lambda: tools.find_patterns(learner_id="lrn_e", db_path=db_path)),
        ("trace_root", lambda: tools.trace_root(learner_id="lrn_a", concept_id="ratios", db_path=db_path)),
        ("what_worked", lambda: tools.what_worked(learner_id="lrn_c", db_path=db_path)),
        ("record_evidence", lambda: tools.record_evidence(
            learner_id="lrn_e", kind="attendance", year=2022, term=3, grade=1, source_ref="register:2022-T3",
            absent_days=3, db_path=db_path)),
        ("propose_finding", lambda: _ratios_finding(db_path)),
    ]
    for name, call in calls:
        call()
        row = _audit_rows(db_path)[-1]
        assert row["tool"] == name and row["ok"] == 1 and row["actor"] == "mcp-client"
        assert row["ts"] and json.loads(row["output"])
        assert "db_path" in json.loads(row["input"])
    assert len(_audit_rows(db_path)) == len(calls)


def test_failed_call_is_audited(db_path):
    with pytest.raises(ValueError):
        tools.find_patterns(learner_id="lrn_zz", db_path=db_path)
    row = _audit_rows(db_path)[-1]
    assert row["ok"] == 0
    assert json.loads(row["input"])["learner_id"] == "lrn_zz"
    assert "Unknown learner" in json.loads(row["output"])["error"]


def test_tools_use_the_db_setting(db_path):
    assert len(tools.list_learners()["learners"]) == 5


def test_tools_are_keyword_only(db_path):
    with pytest.raises(TypeError):
        tools.find_patterns("lrn_a")


def test_find_patterns_refuses_a_lower_evidence_bar(db_path):
    with pytest.raises(ValueError, match="at least 3 terms"):
        tools.find_patterns(learner_id="lrn_a", min_periods=2, db_path=db_path)


def test_get_findings_shows_the_teacher_decision(db_path):
    first = _ratios_finding(db_path)["finding_id"]
    second = _ratios_finding(db_path, statement="Division items were low in 2021-T2.")["finding_id"]
    review.decide_finding(first, "approved", "tch_amina", note="Seen in class", db_path=db_path)

    found = tools.get_findings(learner_id="lrn_a", db_path=db_path)["findings"]
    assert [f["finding_id"] for f in found] == [first, second]
    assert found[0]["status"] == "approved" and found[0]["decided_by_name"] == "Amina Okafor"
    assert found[0]["teacher_note"] == "Seen in class"
    assert found[0]["evidence_ids"] == ["evd_a03", "evd_a04", "evd_a05"]
    assert found[1]["status"] == "proposed" and found[1]["decided_by_name"] is None

    only = tools.get_findings(learner_id="lrn_a", status="proposed", db_path=db_path)["findings"]
    assert [f["finding_id"] for f in only] == [second]
    picked = tools.get_findings(learner_id="lrn_a", finding_ids=[first], db_path=db_path)["findings"]
    assert [f["finding_id"] for f in picked] == [first]
    assert tools.get_findings(learner_id="lrn_b", db_path=db_path)["findings"] == []
    assert _audit_rows(db_path)[-1]["tool"] == "get_findings"
    with pytest.raises(ValueError, match="Unknown status"):
        tools.get_findings(learner_id="lrn_a", status="maybe", db_path=db_path)


def test_get_summaries_shows_the_teacher_decision(db_path):
    finding_id = _ratios_finding(db_path)["finding_id"]
    review.decide_finding(finding_id, "approved", "tch_amina", db_path=db_path)
    summary_id = tools.draft_summary(learner_id="lrn_a", finding_ids=[finding_id], audience="guardian",
                                     language="ar", text="نعمل على القسمة أولاً ثم النسب.",
                                     db_path=db_path)["summary_id"]
    assert tools.get_summaries(learner_id="lrn_a", db_path=db_path)["summaries"][0]["status"] == "draft"
    review.decide_summary(summary_id, "approved", "tch_jean", db_path=db_path)
    summary = tools.get_summaries(learner_id="lrn_a", summary_ids=[summary_id], db_path=db_path)["summaries"][0]
    assert summary == {"summary_id": summary_id, "audience": "guardian", "language": "ar",
                       "text": "نعمل على القسمة أولاً ثم النسب.", "finding_ids": [finding_id],
                       "status": "approved", "created_at": summary["created_at"],
                       "decided_by_name": "Jean Dupont", "decided_at": summary["decided_at"]}
    assert tools.get_summaries(learner_id="lrn_a", status="rejected", db_path=db_path)["summaries"] == []


def test_audit_row_follows_db_path(db_path, tmp_path, monkeypatch):
    other = tmp_path / "other.db"
    db.init_db(other)
    monkeypatch.setenv("ATHAR_DB", str(other))
    tools.list_learners(db_path=db_path)
    assert _audit_rows(db_path)[-1]["tool"] == "list_learners"
    assert _audit_rows(other) == []


def test_actor_and_run_id_kwargs_reach_the_tool(db_path):
    result = _ratios_finding(db_path, _actor="agent", _run_id="run_456")
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT proposed_by FROM findings WHERE id = ?", (result["finding_id"],))
    assert row["proposed_by"] == "run_456"
    last = _audit_rows(db_path)[-1]
    assert (last["actor"], last["run_id"]) == ("agent", "run_456")
    assert "_actor" not in json.loads(last["input"])
    assert audit.current_actor.get() == "mcp-client" and audit.current_run_id.get() is None


@pytest.mark.parametrize("limit", [0, -1, 5000])
def test_timeline_refuses_an_unbounded_limit(db_path, limit):
    learner_id = tools.list_learners(db_path=db_path)["learners"][0]["learner_id"]
    with pytest.raises(ValueError, match="limit must be between"):
        tools.get_learner_timeline(learner_id=learner_id, limit=limit, db_path=db_path)


# ---------------------------------------------------------------- asking for a missing record

def _unrecorded_concept(db_path, learner_id="lrn_a") -> str:
    """A topic in the learner's curriculum with no scored evidence."""
    from athar.curriculum import load_pack
    with db.connect(db_path) as conn:
        pack_id = db.one(conn, "SELECT pack_id FROM learners WHERE id = ?", (learner_id,))["pack_id"]
        seen = {r["concept_id"] for r in db.rows(conn, "SELECT DISTINCT concept_id FROM evidence WHERE learner_id = ? "
                                                       "AND score IS NOT NULL", (learner_id,))}
    return next(c for c in load_pack(pack_id).concepts if c not in seen)


QUESTION = "Results in ratios are low and there are no records for this earlier topic. Do you have a quiz or a note?"


def test_request_record_asks_once_and_is_audited(db_path):
    concept = _unrecorded_concept(db_path)
    first = tools.request_record(learner_id="lrn_a", concept_id=concept, question=QUESTION, db_path=db_path,
                                 _actor="agent", _run_id="run_1")
    assert first["status"] == "open" and first["request_id"].startswith("req_")
    again = tools.request_record(learner_id="lrn_a", concept_id=concept, question=QUESTION, db_path=db_path)
    assert again["request_id"] == first["request_id"] and again["warnings"]
    with db.connect(db_path) as conn:
        assert db.one(conn, "SELECT COUNT(*) AS n FROM record_requests")["n"] == 1
        row = db.one(conn, "SELECT actor, run_id, ok FROM audit_log WHERE tool = 'request_record' ORDER BY id LIMIT 1")
    assert (row["actor"], row["run_id"], row["ok"]) == ("agent", "run_1", 1)


def test_request_record_refusals(db_path):
    concept = _unrecorded_concept(db_path)
    with pytest.raises(ValueError, match="already .* scored records"):
        tools.request_record(learner_id="lrn_a", concept_id="division", question=QUESTION, db_path=db_path)
    with pytest.raises(ValueError, match="rejected"):
        tools.request_record(learner_id="lrn_a", concept_id=concept, db_path=db_path,
                             question="This lazy, slow learner has no records. Do you have any?")
    with pytest.raises(ValueError, match="Unknown concept"):
        tools.request_record(learner_id="lrn_a", concept_id="no-such-topic", question=QUESTION, db_path=db_path)
    with pytest.raises(ValueError, match="Unknown learner"):
        tools.request_record(learner_id="lrn_zz", concept_id=concept, question=QUESTION, db_path=db_path)


def test_a_teacher_is_not_asked_the_same_question_twice(db_path):
    concept = _unrecorded_concept(db_path)
    asked = tools.request_record(learner_id="lrn_a", concept_id=concept, question=QUESTION, db_path=db_path)
    review.answer_request(asked["request_id"], "no_record", "tch_jean", db_path=db_path)
    with pytest.raises(ValueError, match="not asked the same question twice"):
        tools.request_record(learner_id="lrn_a", concept_id=concept, question=QUESTION, db_path=db_path)
    shown = tools.get_record_requests(learner_id="lrn_a", db_path=db_path)["requests"]
    assert [(r["status"], bool(r["answered_by_name"])) for r in shown] == [("no_record", True)]
    assert tools.get_record_requests(learner_id="lrn_a", status="open", db_path=db_path)["requests"] == []
    with pytest.raises(ValueError, match="Unknown status"):
        tools.get_record_requests(learner_id="lrn_a", status="bogus", db_path=db_path)
