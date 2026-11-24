"""Parent accounts made by the school admin, and the school's own (empty) start."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from athar import accounts, db, parents, privacy

ADMIN = {"name": "Test Admin", "username": "admin1", "password": "a-long-test-passphrase"}
PARENT = {"name": "Test Parent", "username": "parent1", "password": "parent-passphrase", "learner_ids": ["lrn_a"]}


def _client():
    from athar.web.app import app

    return TestClient(app)


@pytest.fixture()
def admin(db_path):
    accounts._failures.clear()
    parents._failures.clear()
    client = _client()
    assert client.post("/api/session/setup", json=ADMIN).status_code == 200
    return client


def _parent_client(username="parent1", password="parent-passphrase"):
    client = _client()
    signed = client.post("/api/parent/sign-in", json={"username": username, "password": password})
    assert signed.status_code == 200, signed.text
    return client


def _decisions(db_path):
    """One approved and one proposed finding, and an approved note for the family and one for the next teacher."""
    now = db.now_iso()
    with db.connect(db_path) as conn:
        for fid, status, text in (("fnd_ok", "approved", "Results in ratios rose after visual models."),
                                  ("fnd_wait", "proposed", "Not yet decided by a teacher.")):
            conn.execute("INSERT INTO findings (id, learner_id, kind, statement, evidence_ids, confidence, status, proposed_by, "
                         "proposed_at, decided_by, decided_at) VALUES (?, 'lrn_a', 'what_worked', ?, '[\"evd_1\"]', 0.6, ?, "
                         "'test', ?, ?, ?)", (fid, text, status, now, "tch_amina" if status == "approved" else None,
                                               now if status == "approved" else None))
        for sid, audience, text in (("sum_home", "guardian", "A note for the family."),
                                    ("sum_next", "teacher_handover", "A note only for the next teacher.")):
            conn.execute("INSERT INTO summaries (id, learner_id, audience, language, text, finding_ids, status, created_by, "
                         "created_at, decided_by, decided_at) VALUES (?, 'lrn_a', ?, 'en', ?, '[\"fnd_ok\"]', 'approved', "
                         "'test', ?, 'tch_amina', ?)", (sid, audience, text, now, now))


def test_only_the_school_admin_makes_parent_accounts(db_path):
    nobody = _client()
    refused = nobody.post("/api/parents", json=PARENT)
    assert refused.status_code == 400 and "school admin" in refused.json()["error"]      # no admin yet: nothing is open
    client = _client()
    assert client.post("/api/session/setup", json=ADMIN).status_code == 200
    made = client.post("/api/parents", json=PARENT)
    assert made.status_code == 200 and made.json()["children"] == ["lrn_a"]
    listed = client.get("/api/parents").json()["parents"]
    assert [p["username"] for p in listed] == ["parent1"] and "password_hash" not in listed[0]
    assert listed[0]["children"][0]["learner_id"] == "lrn_a"
    accounts.create_teacher("Test Teacher", ["maths"], "teacher1", "teacher-passphrase", actor="test")
    teacher = _client()
    assert teacher.post("/api/session/sign-in", json={"username": "teacher1", "password": "teacher-passphrase"}).status_code == 200
    assert teacher.post("/api/parents", json={**PARENT, "username": "parent2"}).status_code == 403
    assert teacher.get("/api/parents").status_code == 403


def test_a_parent_sees_only_their_child_and_only_what_was_approved(admin, db_path):
    _decisions(db_path)
    assert admin.post("/api/parents", json=PARENT).status_code == 200
    mine = _parent_client()
    me = mine.get("/api/parent/me").json()
    assert me["parent"]["name"] == "Test Parent" and [c["learner_id"] for c in me["children"]] == ["lrn_a"]
    child = me["children"][0]
    assert [f["statement"] for f in child["findings"]] == ["Results in ratios rose after visual models."]
    assert [n["text"] for n in child["notes"]] == ["A note for the family."]
    page = mine.get("/api/parent/report/lrn_a")
    assert page.status_code == 200 and "A note for the family." in page.text
    assert "A note only for the next teacher." not in page.text and "Not yet decided" not in page.text
    assert mine.get("/api/parent/report/lrn_b").status_code == 403                      # another family's child
    # a parent's session opens nothing on the staff side
    for path in ("/api/learners", "/api/learners/lrn_a/profile", "/learners/lrn_a/report", "/api/parents"):
        assert mine.get(path).status_code in (401, 403), path


def test_signing_in_needs_the_right_password_and_signing_out_ends_it(admin):
    assert admin.post("/api/parents", json=PARENT).status_code == 200
    stranger = _client()
    assert stranger.get("/api/parent/me").status_code == 403
    bad = stranger.post("/api/parent/sign-in", json={"username": "parent1", "password": "wrong-password"})
    assert bad.status_code == 400 and "do not match" in bad.json()["error"]
    mine = _parent_client()
    assert mine.post("/api/parent/sign-out").status_code == 200
    assert mine.get("/api/parent/me").status_code == 403


def test_the_admin_changes_children_password_and_removes_a_parent(admin, db_path):
    pid = admin.post("/api/parents", json=PARENT).json()["id"]
    assert admin.post(f"/api/parents/{pid}/children", json={"learner_ids": ["lrn_a", "lrn_b"]}).json()["children"] == ["lrn_a", "lrn_b"]
    assert admin.post(f"/api/parents/{pid}/children", json={"learner_ids": []}).status_code == 400
    mine = _parent_client()
    assert admin.post(f"/api/parents/{pid}/password", json={"password": "a-new-passphrase"}).status_code == 200
    assert mine.get("/api/parent/me").status_code == 403                                 # signed out everywhere
    mine = _parent_client(password="a-new-passphrase")
    assert len(mine.get("/api/parent/me").json()["children"]) == 2
    assert admin.delete(f"/api/parents/{pid}").status_code == 200
    assert mine.get("/api/parent/me").status_code == 403 and admin.get("/api/parents").json()["parents"] == []


def test_usernames_are_not_shared_between_teachers_and_parents(admin):
    assert admin.post("/api/parents", json={**PARENT, "username": "admin1"}).status_code == 400
    assert admin.post("/api/parents", json=PARENT).status_code == 200
    with pytest.raises(ValueError, match="taken"):
        accounts.create_teacher("Another Teacher", [], "parent1", "teacher-passphrase", actor="test")


def test_deleting_a_learner_removes_the_parent_link(admin, db_path):
    pid = admin.post("/api/parents", json={**PARENT, "learner_ids": ["lrn_a", "lrn_e"]}).json()["id"]
    privacy.delete_learner("lrn_e", "E-05", actor="test")
    assert parents.children_of(pid) == {"lrn_a"}


def test_the_schools_own_start_offers_no_made_up_data(db_path, monkeypatch):
    monkeypatch.setenv("ATHAR_REAL_SCHOOL", "1")
    client = _client()
    assert client.get("/api/session").json()["real_school"] is True
    refused = client.post("/api/family/example-child")
    assert refused.status_code == 400 and "made-up" in refused.json()["error"]
    page = client.get("/parent")
    assert page.status_code == 200 and "/api/parent/sign-in" in page.text
    assert "http://" not in page.text and "https://" not in page.text                     # nothing from outside
