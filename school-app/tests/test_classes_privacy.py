"""Classes (a teacher sees their own learners) and looking after the records (backup, export, delete)."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from athar import accounts, classes, db, privacy, tools

ADMIN = {"name": "Mona Farouk", "username": "mona", "password": "a-long-test-passphrase"}
HANY = {"name": "Hany Adel", "username": "hany", "password": "another-long-pass"}


@pytest.fixture()
def client(db_path):
    from athar.web.app import app

    accounts._failures.clear()
    return TestClient(app)


def _sign_in(client, who) -> None:
    client.post("/api/session/sign-out")
    assert client.post("/api/session/sign-in", json={"username": who["username"], "password": who["password"]}).status_code == 200


def _school(client) -> dict:
    """An admin, a teacher called Hany, and one class holding lrn_a that Hany takes for maths."""
    assert client.post("/api/session/setup", json=ADMIN).status_code == 200
    hany = client.post("/api/teachers", json=HANY).json()
    made = client.post("/api/classes", json={"name": "4A", "grade": 4, "year": 2023})
    assert made.status_code == 200
    class_id = made.json()["id"]
    assert client.post(f"/api/classes/{class_id}/teachers", json={"teacher_id": hany["teacher_id"], "subject": "maths"}).status_code == 200
    assert client.post(f"/api/classes/{class_id}/learners", json={"learner_ids": ["lrn_a"]}).status_code == 200
    return {"class_id": class_id, "hany": hany["teacher_id"]}


# ------------------------------------------------------------------ classes

def test_everyone_is_shown_until_sign_in_is_on(client):
    assert classes.visible(None) is None
    assert len(client.get("/api/learners").json()["learners"]) == 5


def test_a_teacher_sees_only_the_learners_of_their_classes(client):
    _school(client)
    assert len(client.get("/api/learners").json()["learners"]) == 5          # the admin sees everyone
    _sign_in(client, HANY)
    shown = client.get("/api/learners").json()["learners"]
    assert [row["learner_id"] for row in shown] == ["lrn_a"] and shown[0]["class_name"] == "4A"
    assert client.get("/api/learners/lrn_a/dashboard").status_code == 200
    for path in ("/api/learners/lrn_b/dashboard", "/api/learners/lrn_b/timeline", "/api/learners/lrn_b/report",
                 "/learners/lrn_b/report", "/api/learners/lrn_b/trace/multiplication", "/api/learners/lrn_b/export"):
        assert client.get(path).status_code == 403, path
    assert {row["learner_id"] for row in client.get("/api/evidence?ids=evd_a01,evd_b01").json()["evidence"]} == {"lrn_a"}
    assert client.get("/api/overview").status_code == 200
    assert [c["name"] for c in client.get("/api/classes").json()["classes"]] == ["4A"]


def test_a_teacher_with_no_class_sees_nobody(client):
    made = _school(client)
    client.delete(f"/api/classes/{made['class_id']}/teachers/{made['hany']}")
    _sign_in(client, HANY)
    assert client.get("/api/learners").json()["learners"] == []
    assert client.get("/api/learners/lrn_a/dashboard").status_code == 403
    assert client.post("/api/learners", json={"name": "Salma Ibrahim", "grade": 2}).status_code == 403


def test_a_teacher_cannot_decide_for_a_learner_outside_their_classes(client):
    _school(client)
    theirs = tools.propose_finding(learner_id="lrn_b", kind="strength", evidence_ids=["evd_b01", "evd_b02"],
                                   statement="Scores on 2D shapes stayed high over two terms.",
                                   concept_ids=["shapes-2d"], confidence=0.6)
    own = tools.propose_finding(learner_id="lrn_a", kind="struggle", evidence_ids=["evd_a09", "evd_a10"],
                                statement="Scores on ratios stayed low over several terms.",
                                concept_ids=["ratios"], confidence=0.6)
    _sign_in(client, HANY)
    waiting = client.get("/api/review/pending").json()["findings"]
    assert [f["id"] for f in waiting] == [own["finding_id"]]
    assert [f["id"] for f in client.get("/api/findings").json()["findings"]] == [own["finding_id"]]
    refused = client.post(f"/api/findings/{theirs['finding_id']}/decision", json={"decision": "approved", "teacher_id": ""})
    assert refused.status_code == 403
    assert client.post(f"/api/findings/{own['finding_id']}/decision",
                       json={"decision": "approved", "teacher_id": ""}).status_code == 200
    with db.connect() as conn:
        assert db.one(conn, "SELECT status FROM findings WHERE id = ?", (theirs["finding_id"],))["status"] == "proposed"
    assert client.post("/api/runs", json={"learner_id": "lrn_b"}).status_code == 403


def test_a_marks_sheet_cannot_name_a_learner_outside_the_class(client):
    _school(client)
    _sign_in(client, HANY)
    sheet = b"Learner code,Name,Q1\nTopic,,Ratios\nOut of,,2\nA-01,,1\nB-02,,2\n"
    checked = client.post("/api/upload/marks", data={"title": "Ratios quiz", "year": "2023", "term": "1", "grade": "4"},
                          files={"file": ("quiz.csv", sheet, "text/csv")}).json()["check"]
    assert not checked["ok"] and any("B-02 is not in one of your classes" in p for p in checked["problems"])


def test_only_the_admin_manages_classes_and_a_learner_is_in_one_class_a_year(client):
    made = _school(client)
    other = client.post("/api/classes", json={"name": "4B", "grade": 4, "year": 2023}).json()
    client.post(f"/api/classes/{other['id']}/learners", json={"learner_ids": ["lrn_a", "lrn_b"]})
    by_name = {c["name"]: [x["learner_id"] for x in c["learners"]] for c in client.get("/api/classes").json()["classes"]}
    assert by_name == {"4A": [], "4B": ["lrn_a", "lrn_b"]}                 # moved, not copied
    assert client.post("/api/classes", json={"name": "4B", "grade": 4, "year": 2023}).status_code == 400
    _sign_in(client, HANY)
    assert client.post("/api/classes", json={"name": "4C", "grade": 4, "year": 2023}).status_code == 403
    assert client.post(f"/api/classes/{made['class_id']}/learners", json={"learner_ids": ["lrn_c"]}).status_code == 403


def test_a_teacher_adds_a_learner_to_their_own_class(client):
    made = _school(client)
    _sign_in(client, HANY)
    assert client.post("/api/learners", json={"name": "Salma Ibrahim", "grade": 4}).status_code == 400   # no class chosen
    added = client.post("/api/learners", json={"name": "Salma Ibrahim", "grade": 4, "class_id": made["class_id"]})
    assert added.status_code == 200
    assert added.json()["learner_id"] in {row["learner_id"] for row in client.get("/api/learners").json()["learners"]}


# ------------------------------------------------------------------ backup, export, delete

def test_backup_is_a_whole_copy_and_can_be_restored(db_path, tmp_path):
    made = privacy.make_backup()
    copy = sqlite3.connect(made["path"])
    assert copy.execute("SELECT COUNT(*) FROM learners").fetchone()[0] == 5
    copy.close()
    assert [b["file"] for b in privacy.list_backups()] == [made["file"]]
    privacy.delete_learner("lrn_e", "E-05")
    with db.connect() as conn:
        assert db.one(conn, "SELECT COUNT(*) AS n FROM learners")["n"] == 4
    privacy.restore_backup(made["path"])
    with db.connect() as conn:
        assert db.one(conn, "SELECT COUNT(*) AS n FROM learners")["n"] == 5
    with pytest.raises(ValueError, match="not a"):
        (tmp_path / "junk.db").write_text("not a database at all, just some text " * 40)
        privacy.restore_backup(tmp_path / "junk.db")


def test_export_holds_the_whole_record_of_one_learner(db_path):
    data = privacy.export_learner("lrn_a")
    assert data["learner"]["alias"] == "Learner A-01"
    assert len(data["evidence"]) == 13 and {row["learner_id"] for row in data["evidence"]} == {"lrn_a"}


def test_delete_needs_the_record_code_and_leaves_nothing_behind(db_path):
    proposed = tools.propose_finding(learner_id="lrn_a", kind="struggle", evidence_ids=["evd_a09", "evd_a10"],
                                     statement="Scores on ratios stayed low over several terms.",
                                     concept_ids=["ratios"], confidence=0.6)
    from athar import review
    review.decide_finding(proposed["finding_id"], "approved", "tch_amina")
    inbox = db_path.parent / "inbox"
    inbox.mkdir(exist_ok=True)
    (inbox / "quiz_sheet_A-01_2023-T1.md").write_text("Learner: Learner A-01\n", encoding="utf-8")
    (inbox / "quiz_sheet_BA-01_2023-T1.md").write_text("someone else\n", encoding="utf-8")
    with pytest.raises(ValueError, match="record code"):
        privacy.delete_learner("lrn_a", "B-02")
    out = privacy.delete_learner("lrn_a", "a-01", actor="teacher:tch_amina")
    assert out["evidence"] == 13 and out["findings"] == 1 and out["inbox_files_removed"] == 1
    assert (inbox / "quiz_sheet_BA-01_2023-T1.md").exists()
    with db.connect() as conn:
        for table in ("evidence", "findings", "summaries", "record_requests"):
            assert db.one(conn, f"SELECT COUNT(*) AS n FROM {table} WHERE learner_id = 'lrn_a'")["n"] == 0
        assert db.one(conn, "SELECT COUNT(*) AS n FROM approvals WHERE target_id = ?", (proposed["finding_id"],))["n"] == 0
        logged = " ".join(r["input"] + r["output"] for r in db.rows(conn, "SELECT input, output FROM audit_log"))
        assert db.one(conn, "SELECT COUNT(*) AS n FROM audit_log WHERE tool = 'delete_learner'")["n"] == 1
        assert db.one(conn, "SELECT COUNT(*) AS n FROM learners")["n"] == 4
    assert "lrn_a" not in logged and "A-01" not in logged


def test_only_the_admin_deletes_exports_and_backs_up(client):
    _school(client)
    _sign_in(client, HANY)
    assert client.post("/api/learners/lrn_a/delete", json={"confirm_code": "A-01"}).status_code == 403
    assert client.get("/api/learners/lrn_a/export").status_code == 403
    assert client.post("/api/admin/backups").status_code == 403
    _sign_in(client, ADMIN)
    assert client.post("/api/learners/lrn_a/delete", json={"confirm_code": "wrong"}).status_code == 400
    made = client.post("/api/admin/backups").json()["made"]
    assert client.get(f"/api/admin/backups/{made['file']}").status_code == 200
    assert client.get("/api/admin/backups/..%2Fathar.db").status_code in (400, 404)
    assert client.get("/api/learners/lrn_a/export").headers["content-disposition"].endswith('record-A-01.json"')
    assert client.post("/api/learners/lrn_a/delete", json={"confirm_code": "A-01"}).json()["deleted"] is True
    assert client.get("/api/learners/lrn_a/dashboard").status_code == 400


def test_a_wrong_record_is_withdrawn_not_edited(client):
    _school(client)
    _sign_in(client, HANY)
    assert client.post("/api/evidence/evd_b01/withdraw", json={"reason": "typed for the wrong child"}).status_code == 403
    assert client.post("/api/evidence/evd_a09/withdraw", json={"reason": ""}).status_code == 400
    done = client.post("/api/evidence/evd_a09/withdraw", json={"reason": "typed for the wrong child"})
    assert done.status_code == 200 and done.json()["status"] == "retracted"
    shown = [item["id"] for period in client.get("/api/learners/lrn_a/timeline").json()["periods"] for item in period["items"]]
    assert "evd_a09" not in shown and "evd_a10" in shown
    with db.connect() as conn:
        assert db.one(conn, "SELECT status FROM evidence WHERE id = 'evd_a09'")["status"] == "retracted"   # kept, not erased
        logged = db.one(conn, "SELECT actor, input FROM audit_log WHERE tool = 'withdraw_record'")
    assert logged["actor"].startswith("teacher:") and "wrong child" in logged["input"]
