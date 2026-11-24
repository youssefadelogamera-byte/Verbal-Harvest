import pytest

from athar import db, review, tools


def _propose(db_path) -> str:
    return tools.propose_finding(
        learner_id="lrn_b", kind="strength", evidence_ids=["evd_b01", "evd_b07"],
        statement="Geometry items above 0.8 for four terms in a row.", db_path=db_path)["finding_id"]


def _approvals(db_path) -> list[dict]:
    with db.connect(db_path) as conn:
        return db.rows(conn, "SELECT * FROM approvals ORDER BY id")


def _last_audit(db_path) -> dict:
    with db.connect(db_path) as conn:
        return db.one(conn, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 1")


def test_pending_expands_evidence(db_path):
    finding_id = _propose(db_path)
    result = review.pending(db_path=db_path)
    assert [f["id"] for f in result["findings"]] == [finding_id]
    assert [e["id"] for e in result["findings"][0]["evidence"]] == ["evd_b01", "evd_b07"]
    assert result["summaries"] == []


def test_approve_writes_approval_with_teacher_name(db_path):
    finding_id = _propose(db_path)
    result = review.decide_finding(finding_id, "approved", "tch_amina", note="Matches my notes", db_path=db_path)
    assert result["status"] == "approved" and result["decided_by"] == "tch_amina"
    approval = _approvals(db_path)[-1]
    assert (approval["target_type"], approval["target_id"], approval["decision"]) == ("finding", finding_id,
                                                                                      "approved")
    assert approval["teacher_name"] == "Amina Okafor" and approval["note"] == "Matches my notes"
    audit_row = _last_audit(db_path)
    assert audit_row["tool"] == "decide_finding" and audit_row["actor"] == "teacher:tch_amina"
    assert review.pending(db_path=db_path)["findings"] == []


def test_edit_replaces_statement(db_path):
    finding_id = _propose(db_path)
    result = review.decide_finding(finding_id, "edited", "tch_jean", db_path=db_path,
                                   edited_statement="Geometry quiz and project work above 0.8 since 2021-T1.")
    assert result["status"] == "edited"
    assert result["statement"] == "Geometry quiz and project work above 0.8 since 2021-T1."
    assert _approvals(db_path)[-1]["teacher_name"] == "Jean Dupont"


def test_edit_needs_a_clean_statement(db_path):
    finding_id = _propose(db_path)
    with pytest.raises(ValueError, match="edited_statement"):
        review.decide_finding(finding_id, "edited", "tch_jean", db_path=db_path)
    with pytest.raises(ValueError, match="label on a child"):
        review.decide_finding(finding_id, "edited", "tch_jean", edited_statement="A gifted child.", db_path=db_path)


def test_reject_and_deciding_twice_raises(db_path):
    finding_id = _propose(db_path)
    review.decide_finding(finding_id, "rejected", "tch_jean", note="Too early", db_path=db_path)
    assert _approvals(db_path)[-1]["decision"] == "rejected"
    with pytest.raises(ValueError, match="already decided"):
        review.decide_finding(finding_id, "approved", "tch_amina", db_path=db_path)
    assert len(_approvals(db_path)) == 1


def test_unknown_teacher_and_bad_decision_raise(db_path):
    finding_id = _propose(db_path)
    with pytest.raises(ValueError, match="Unknown teacher"):
        review.decide_finding(finding_id, "approved", "tch_ghost", db_path=db_path)
    with pytest.raises(ValueError, match="Decision must be"):
        review.decide_finding(finding_id, "maybe", "tch_amina", db_path=db_path)
    assert _approvals(db_path) == []


def test_summary_flow(db_path):
    finding_id = _propose(db_path)
    review.decide_finding(finding_id, "approved", "tch_amina", db_path=db_path)
    summary_id = tools.draft_summary(learner_id="lrn_b", finding_ids=[finding_id], audience="guardian",
                                     language="fr", text="Les activités de géométrie réussissent bien.",
                                     db_path=db_path)["summary_id"]
    pending = review.pending(db_path=db_path)["summaries"]
    assert [s["id"] for s in pending] == [summary_id]
    assert pending[0]["findings"][0]["id"] == finding_id

    result = review.decide_summary(summary_id, "approved", "tch_jean", db_path=db_path)
    assert result["status"] == "approved"
    approval = _approvals(db_path)[-1]
    assert (approval["target_type"], approval["teacher_name"]) == ("summary", "Jean Dupont")
    assert _last_audit(db_path)["actor"] == "teacher:tch_jean"
    with pytest.raises(ValueError, match="already decided"):
        review.decide_summary(summary_id, "rejected", "tch_jean", db_path=db_path)
    with pytest.raises(ValueError, match="Decision must be"):
        review.decide_summary(summary_id, "edited", "tch_jean", db_path=db_path)
    with pytest.raises(ValueError, match="Unknown teacher"):
        review.decide_summary(summary_id, "approved", "tch_ghost", db_path=db_path)


def test_decision_is_undone_if_its_audit_row_cannot_be_written(db_path, monkeypatch):
    finding_id = _propose(db_path)

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(review.audit, "write_row", broken)
    with pytest.raises(RuntimeError):
        review.decide_finding(finding_id, "approved", "tch_amina", db_path=db_path)
    with db.connect(db_path) as conn:
        assert db.one(conn, "SELECT status FROM findings WHERE id = ?", (finding_id,))["status"] == "proposed"
    assert _approvals(db_path) == []


def test_a_decision_that_loses_the_race_changes_nothing(db_path):
    """The status check is part of the UPDATE, so a second decision cannot overwrite the first."""
    finding_id = _propose(db_path)
    review.decide_finding(finding_id, "approved", "tch_jean", db_path=db_path)
    with pytest.raises(ValueError, match=r"already decided \(approved\)"):
        review.decide_finding(finding_id, "edited", "tch_amina", edited_statement="Results stayed low for three terms.",
                              db_path=db_path)
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT status, decided_by, statement FROM findings WHERE id = ?", (finding_id,))
    assert (row["status"], row["decided_by"]) == ("approved", "tch_jean")
    assert row["statement"] != "Results stayed low for three terms."
    with pytest.raises(ValueError, match="Unknown finding"):
        review.decide_finding("fnd_missing", "approved", "tch_jean", db_path=db_path)


# ---------------------------------------------------------------- answering a record request

def _ask(db_path) -> str:
    from athar.curriculum import load_pack
    with db.connect(db_path) as conn:
        pack_id = db.one(conn, "SELECT pack_id FROM learners WHERE id = 'lrn_a'")["pack_id"]
        seen = {r["concept_id"] for r in db.rows(conn, "SELECT DISTINCT concept_id FROM evidence WHERE learner_id = 'lrn_a' "
                                                       "AND score IS NOT NULL")}
    concept = next(c for c in load_pack(pack_id).concepts if c not in seen)
    return tools.request_record(learner_id="lrn_a", concept_id=concept, db_path=db_path,
                                question="There are no records for this topic. Do you have a quiz or a note?")["request_id"]


def test_answering_a_request_needs_a_named_teacher_and_a_record(db_path):
    request_id = _ask(db_path)
    assert [r["id"] for r in review.pending(db_path=db_path)["requests"]] == [request_id]
    with pytest.raises(ValueError, match="needs the record"):
        review.answer_request(request_id, "provided", "tch_jean", text="   ", db_path=db_path)
    with pytest.raises(ValueError, match="Only a named teacher"):
        review.answer_request(request_id, "no_record", "tch_nobody", db_path=db_path)
    with pytest.raises(ValueError, match="Answer must be one of"):
        review.answer_request(request_id, "approved", "tch_jean", db_path=db_path)
    with pytest.raises(ValueError, match="Term must be"):
        review.answer_request(request_id, "provided", "tch_jean", text="Q1 1 out of 2", term=4, db_path=db_path)
    with pytest.raises(ValueError, match="Unknown request"):
        review.answer_request("req_missing", "no_record", "tch_jean", db_path=db_path)
    assert [r["id"] for r in review.pending(db_path=db_path)["requests"]] == [request_id]   # nothing changed


def test_an_answer_is_recorded_once_with_the_teacher_in_the_audit_log(db_path):
    request_id = _ask(db_path)
    out = review.answer_request(request_id, "provided", "tch_jean", text="Q1 1 out of 2", year=2022, term=2,
                                db_path=db_path)
    assert (out["status"], out["answered_by"], out["answer_year"], out["answer_term"]) == ("provided", "tch_jean", 2022, 2)
    with pytest.raises(ValueError, match="already answered"):
        review.answer_request(request_id, "no_record", "tch_amina", db_path=db_path)
    with db.connect(db_path) as conn:
        rows = db.rows(conn, "SELECT actor FROM audit_log WHERE tool = 'answer_request'")
        status = db.one(conn, "SELECT status, answered_by FROM record_requests WHERE id = ?", (request_id,))
    assert rows == [{"actor": "teacher:tch_jean"}]
    assert (status["status"], status["answered_by"]) == ("provided", "tch_jean")
    assert review.pending(db_path=db_path)["requests"] == []
