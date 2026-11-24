"""Family mode: a parent, their own children, results typed in at home, and the summary they read."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from athar import db, family


@pytest.fixture()
def client(db_path):
    from athar.web.app import app

    return TestClient(app)


def _home(client) -> str:
    """A family with one child in grade 4. Returns the child's id."""
    assert client.post("/api/mode", json={"mode": "family", "name": "Mona Farouk"}).status_code == 200
    made = client.post("/api/family/children", json={"name": "Salma", "grade": 4})
    assert made.status_code == 200, made.text
    return made.json()["learner_id"]


def test_nobody_has_chosen_at_first_and_a_parent_must_give_a_name(client):
    assert client.get("/api/session").json()["mode"] is None
    assert client.post("/api/mode", json={"mode": "family", "name": ""}).status_code == 400
    assert client.post("/api/mode", json={"mode": "club"}).status_code == 400
    chosen = client.post("/api/mode", json={"mode": "family", "name": "Mona Farouk"}).json()
    assert chosen["mode"] == "family" and chosen["guardian"]["name"] == "Mona Farouk"
    seen = client.get("/api/session").json()
    assert seen["mode"] == "family" and seen["guardian"]["name"] == "Mona Farouk"


def test_a_family_sees_only_its_own_children(client):
    child = _home(client)
    assert [row["learner_id"] for row in client.get("/api/learners").json()["learners"]] == [child]
    assert [c["name"] for c in client.get("/api/family/children").json()["children"]] == ["Salma"]
    assert client.get(f"/api/learners/{child}/dashboard").status_code == 200
    for path in ("/api/learners/lrn_a/dashboard", "/api/learners/lrn_a/timeline", "/learners/lrn_a/report"):
        assert client.get(path).status_code == 403, path
    assert client.get("/api/evidence?ids=evd_a01").json()["evidence"] == []
    assert client.post("/api/family/children/lrn_a/notes", json={"text": "a note about someone else"}).status_code == 400
    assert client.post("/api/runs", json={"learner_id": "lrn_a"}).status_code == 403


def test_switching_back_to_school_shows_the_school_again_and_loses_nothing(client):
    child = _home(client)
    assert client.post("/api/mode", json={"mode": "school"}).status_code == 200
    shown = [row["learner_id"] for row in client.get("/api/learners").json()["learners"]]
    assert len(shown) == 5 and child not in shown                          # a family's own child never shows at school
    assert client.get(f"/api/learners/{child}/dashboard").status_code == 403
    assert client.get(f"/api/learners/{child}/export").status_code == 403
    assert client.post("/api/runs", json={"learner_id": child}).status_code == 403
    assert client.post("/api/mode", json={"mode": "family"}).json()["guardian"]["name"] == "Mona Farouk"
    assert [row["learner_id"] for row in client.get("/api/learners").json()["learners"]] == [child]


def test_results_typed_at_home_become_records_and_bad_lines_are_refused(client):
    child = _home(client)
    bad = client.post(f"/api/family/children/{child}/results",
                      json={"items": [{"topic_id": "no-such-topic", "mark": 3, "out_of": 5},
                                      {"topic_id": "ratios", "mark": 9, "out_of": 5}]})
    assert bad.status_code == 400 and bad.json()["error"].startswith("Line 1")
    assert client.post(f"/api/family/children/{child}/results", json={"items": []}).status_code == 400
    saved = client.post(f"/api/family/children/{child}/results",
                        json={"title": "اختبار شهر نوفمبر", "term": 1, "grade": 4, "year": 2026,
                              "items": [{"topic_id": "ratios", "mark": "١", "out_of": "٥"},      # Arabic digits
                                        {"topic_id": "fractions", "mark": 2, "out_of": 4},
                                        {"topic_id": "", "mark": "", "out_of": ""}]})          # an empty line is skipped
    assert saved.status_code == 200 and saved.json()["saved"] == 2
    with db.connect() as conn:
        rows = db.rows(conn, "SELECT concept_id, score, language, teacher_id, source_ref, grade, year, term FROM evidence "
                             "WHERE learner_id = ? ORDER BY concept_id", (child,))
        parent = db.one(conn, "SELECT value FROM settings WHERE key = 'guardian_id'")["value"]
    assert [(r["concept_id"], r["score"]) for r in rows] == [("fractions", 0.5), ("ratios", 0.2)]
    assert all(r["teacher_id"] == parent and r["source_ref"].startswith("home:2026-T1:") and r["language"] == "ar" for r in rows)


def test_an_older_paper_moves_the_start_of_the_record_back(client):
    child = _home(client)
    client.post(f"/api/family/children/{child}/results",
                json={"grade": 2, "year": family.school_year() - 2, "term": 2, "items": [{"topic_id": "division", "mark": 1, "out_of": 4}]})
    with db.connect() as conn:
        row = db.one(conn, "SELECT start_year, start_grade FROM learners WHERE id = ?", (child,))
    assert (row["start_year"], row["start_grade"]) == (family.school_year() - 2, 2)


def test_a_note_is_kept_as_written_and_the_log_does_not_hold_its_words(client):
    child = _home(client)
    assert client.post(f"/api/family/children/{child}/notes", json={"text": "x"}).status_code == 400
    words = "بتذاكر الكسور كويس لكن بتتلخبط في القسمة المطولة"
    assert client.post(f"/api/family/children/{child}/notes", json={"text": words, "topic_id": "division"}).status_code == 200
    kept = client.get(f"/api/family/children/{child}/notes").json()["notes"]
    assert [(n["text"], n["language"], n["concept_id"]) for n in kept] == [(words, "ar", "division")]
    with db.connect() as conn:
        logged = " ".join(r["input"] + r["output"] for r in db.rows(conn, "SELECT input, output FROM audit_log"))
        assert db.one(conn, "SELECT score FROM evidence WHERE raw_text = ?", (words,))["score"] is None
    assert "القسمة" not in logged and "Salma" not in logged


def test_the_summary_says_too_little_then_traces_a_low_topic_to_where_it_started(client):
    child = _home(client)
    empty = client.get(f"/api/family/children/{child}/summary").json()
    assert empty["records"] == 0 and not empty["enough"] and empty["help_first"] == [] and empty["going_well"] == []
    year = family.school_year()
    for grade, back, topic, marks in ((2, 2, "multiplication", (4, 5)), (2, 2, "division", (1, 1)),
                                      (3, 1, "fractions", (2, 1)), (4, 0, "ratios", (1, 1)), (4, 0, "shapes-2d", (5, 5))):
        r = client.post(f"/api/family/children/{child}/results",
                        json={"grade": grade, "year": year - back, "term": 1,
                              "items": [{"topic_id": topic, "mark": m, "out_of": 5} for m in marks]})
        assert r.status_code == 200, r.text
    got = client.get(f"/api/family/children/{child}/summary").json()
    assert got["records"] == 10 and got["enough"]
    first = got["help_first"][0]
    assert first["topic_id"] == "ratios" and not first["starts_here"] and first["start"]["topic_id"] == "division"
    assert first["evidence_ids"] and all(isinstance(i, str) for i in first["evidence_ids"])
    assert "shapes-2d" not in [h["topic_id"] for h in got["help_first"]]
    assert any(g["kind"] == "topic" and g["average"] >= 0.8 for g in got["going_well"])
    text = str(got).lower()
    assert "rank" not in text and "weak" not in text and "better than" not in text      # nothing compares or labels


def test_a_made_up_child_can_be_shown_and_taken_away_again(client):
    client.post("/api/mode", json={"mode": "family", "name": "Mona Farouk"})
    shown = client.post("/api/family/example-child").json()
    assert shown["example"] and [c["example"] for c in client.get("/api/family/children").json()["children"]] == [True]
    assert client.get(f"/api/family/children/{shown['learner_id']}/summary").json()["records"] > 0
    assert client.delete("/api/family/example-child").json()["removed"] == 1
    assert client.get("/api/family/children").json()["children"] == []
    with db.connect() as conn:                                        # the made-up records themselves are untouched
        assert db.one(conn, "SELECT COUNT(*) AS n FROM evidence WHERE learner_id = ?", (shown["learner_id"],))["n"] > 0


def test_a_decision_at_home_is_recorded_under_the_parent(client):
    from athar import tools
    child = _home(client)
    client.post(f"/api/family/children/{child}/results",
                json={"items": [{"topic_id": "ratios", "mark": 1, "out_of": 5}, {"topic_id": "ratios", "mark": 1, "out_of": 5}]})
    with db.connect() as conn:
        ids = [r["id"] for r in db.rows(conn, "SELECT id FROM evidence WHERE learner_id = ?", (child,))]
        parent = db.one(conn, "SELECT value FROM settings WHERE key = 'guardian_id'")["value"]
    made = tools.propose_finding(learner_id=child, kind="struggle", evidence_ids=ids,
                                 statement="Results in ratios have been low.", concept_ids=["ratios"], confidence=0.5)
    done = client.post(f"/api/findings/{made['finding_id']}/decision", json={"decision": "approved", "teacher_id": ""})
    assert done.status_code == 200
    with db.connect() as conn:
        assert db.one(conn, "SELECT decided_by FROM findings WHERE id = ?", (made["finding_id"],))["decided_by"] == parent


def test_once_a_school_has_sign_in_only_its_admin_changes_the_mode(client):
    assert client.post("/api/session/setup", json={"name": "Mona Farouk", "username": "mona",
                                                    "password": "a-long-test-passphrase"}).status_code == 200
    client.post("/api/teachers", json={"name": "Hany Adel", "username": "hany", "password": "another-long-pass"})
    client.post("/api/session/sign-out")
    assert client.post("/api/mode", json={"mode": "family", "name": "Someone"}).status_code == 401
    client.post("/api/session/sign-in", json={"username": "hany", "password": "another-long-pass"})
    assert client.post("/api/mode", json={"mode": "family", "name": "Someone"}).status_code == 403


def test_two_made_up_children_a_rename_and_a_grade_that_moves_up_by_itself(client, monkeypatch):
    child = _home(client)
    one = client.post("/api/family/example-child").json()["learner_id"]
    two = client.post("/api/family/example-child").json()["learner_id"]
    assert one != two and len(client.get("/api/family/children").json()["children"]) == 3
    assert client.delete(f"/api/family/example-child?learner_id={one}").json()["removed"] == 1
    assert [c["learner_id"] for c in client.get("/api/family/children").json()["children"]] == [child, two]
    assert client.post(f"/api/family/children/{two}/name", json={"name": "Someone"}).status_code == 400     # made up
    assert client.post(f"/api/family/children/{child}/name", json={"name": "Salma Ibrahim"}).status_code == 200
    kids = {c["learner_id"]: c for c in client.get("/api/family/children").json()["children"]}
    assert kids[child]["name"] == "Salma Ibrahim" and kids[child]["grade_now"] == 4
    listed = {row["learner_id"]: row for row in client.get("/api/learners").json()["learners"]}
    assert listed[child]["grade_now"] == 4 and listed[two]["example"] is True
    real = family.school_year()
    monkeypatch.setattr(family, "school_year", lambda today=None: real + 1)          # a year later, nothing typed
    assert {c["learner_id"]: c for c in client.get("/api/family/children").json()["children"]}[child]["grade_now"] == 5


def test_a_family_has_its_own_folder_for_papers(client, db_path):
    assert [f["name"] for f in client.get("/api/inbox").json()["files"]] == []
    school = db_path.parent / "inbox"
    school.mkdir(exist_ok=True)
    (school / "quiz_sheet_A-01.md").write_text("made-up school file", encoding="utf-8")
    assert [f["name"] for f in client.get("/api/inbox").json()["files"]] == ["quiz_sheet_A-01.md"]
    _home(client)
    assert client.get("/api/inbox").json()["files"] == []                 # the school's samples are not shown at home
    sent = client.post("/api/upload/document", files={"file": ("paper.txt", b"Learner X-01: 3 out of 5", "text/plain")})
    assert sent.status_code == 200 and (db_path.parent / "inbox-family" / "paper.txt").exists()
    assert [f["name"] for f in client.get("/api/inbox").json()["files"]] == ["paper.txt"]


def test_the_page_can_be_opened_in_a_language_and_has_a_parent_footer(client):
    page = client.get("/").text
    assert 'get("lang")' in page and 'id="foot"' in page
    assert "Athar never compares your child with anyone" in page and "No records yet." in page
