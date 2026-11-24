"""Sign-in, the school admin's page, and the marks upload."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from athar import accounts, db, imports, tools

ADMIN = {"name": "Mona Farouk", "username": "mona", "password": "a-long-test-passphrase"}


@pytest.fixture()
def client(db_path):
    from athar.web.app import app

    accounts._failures.clear()
    return TestClient(app)


def _setup(client) -> None:
    assert client.post("/api/session/setup", json=ADMIN).status_code == 200


def _sheet(*learner_rows, topics=("fractions", "ratios"), out_of=("2", "3")) -> list[list[str]]:
    return [["Learner code", "Name", "Q1", "Q2"], ["Topic", "", *topics], ["Out of", "", *out_of], *learner_rows]


# ------------------------------------------------------------------ passwords and accounts

def test_password_is_hashed_and_checked():
    stored = accounts.hash_password("correct horse")
    assert "correct horse" not in stored and stored.startswith("scrypt$")
    assert accounts.verify_password("correct horse", stored)
    assert not accounts.verify_password("wrong horse", stored)
    assert not accounts.verify_password("correct horse", "not-a-hash")


def test_first_account_must_be_the_admin(db_path):
    with pytest.raises(ValueError, match="first account must be the school admin"):
        accounts.create_account("tch_amina", "amina", "long-enough-pass", "teacher")
    accounts.create_account("tch_amina", "amina", "long-enough-pass", "admin")
    accounts.create_account("tch_jean", "jean", "long-enough-pass", "teacher")
    with pytest.raises(ValueError, match="taken"):
        accounts.create_teacher("Someone Else", [], "JEAN", "long-enough-pass")
    with pytest.raises(ValueError, match="at least 8"):
        accounts.create_teacher("Short Pass", [], "short", "1234567")


def test_people_and_audit_never_hold_a_password(db_path):
    accounts.create_account("tch_amina", "amina", "long-enough-pass", "admin")
    accounts.sign_in("amina", "long-enough-pass")
    assert all("password" not in key for row in accounts.people() for key in row)
    with db.connect() as conn:
        logged = " ".join(r["input"] + r["output"] for r in db.rows(conn, "SELECT input, output FROM audit_log"))
        stored = db.one(conn, "SELECT password_hash FROM accounts")["password_hash"]
    assert "long-enough-pass" not in logged and "long-enough-pass" not in stored


def test_wrong_passwords_are_refused_then_locked(db_path):
    accounts._failures.clear()
    accounts.create_account("tch_amina", "amina", "long-enough-pass", "admin")
    for _ in range(8):
        with pytest.raises(ValueError, match="do not match"):
            accounts.sign_in("amina", "guess")
    with pytest.raises(ValueError, match="Too many"):
        accounts.sign_in("amina", "long-enough-pass")
    accounts._failures.clear()


def test_expired_session_is_not_a_session(db_path):
    accounts.create_account("tch_amina", "amina", "long-enough-pass", "admin")
    token = accounts.sign_in("amina", "long-enough-pass")["token"]
    assert accounts.session_teacher(token)["name"] == "Amina Okafor"
    assert accounts.session_teacher("made-up-token") is None
    with db.connect() as conn:
        assert db.one(conn, "SELECT token_hash FROM sessions")["token_hash"] != token   # only a hash is stored
        conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert accounts.session_teacher(token) is None


# ------------------------------------------------------------------ the web app behind sign-in

def test_demo_mode_is_open_until_an_admin_exists(client):
    assert client.get("/api/session").json()["sign_in"] is False
    assert client.get("/api/learners").status_code == 200
    # With made-up data and no sign-in, a learner can be added to try things out.
    assert client.post("/api/learners", json={"name": "Test Child", "grade": 2}).status_code == 200


def test_data_needs_sign_in_once_an_admin_exists(client):
    _setup(client)
    client.cookies.clear()
    assert client.get("/api/learners").status_code == 401
    assert client.get("/api/audit").status_code == 401
    assert client.get("/learners/lrn_a/report").status_code == 401
    assert client.get("/").status_code == 200                        # the page itself holds no data
    assert client.post("/api/session/setup", json=ADMIN).status_code == 403
    assert client.post("/api/session/sign-in", json={"username": "mona", "password": "nope"}).status_code == 400
    assert client.post("/api/session/sign-in", json={"username": "mona", "password": ADMIN["password"]}).status_code == 200
    assert client.get("/api/learners").status_code == 200
    assert client.post("/api/session/sign-out").status_code == 200
    assert client.get("/api/learners").status_code == 401


def test_a_decision_is_recorded_under_the_signed_in_teacher(client):
    _setup(client)
    me = client.get("/api/session").json()["teacher"]
    proposed = tools.propose_finding(learner_id="lrn_a", kind="struggle", evidence_ids=["evd_a09", "evd_a10"],
                                     statement="Scores on ratios stayed low over several terms.",
                                     concept_ids=["ratios"], confidence=0.6)
    r = client.post(f"/api/findings/{proposed['finding_id']}/decision",
                    json={"decision": "approved", "teacher_id": "tch_jean"})     # claims to be someone else
    assert r.status_code == 200
    with db.connect() as conn:
        assert db.one(conn, "SELECT decided_by FROM findings WHERE id = ?", (proposed["finding_id"],))["decided_by"] == me["id"]
    assert client.post("/api/teachers/tch_jean/profile", json={"approaches": {}}).status_code == 403


def test_only_the_admin_adds_teachers(client):
    _setup(client)
    made = client.post("/api/teachers", json={"name": "Hany Adel", "username": "hany", "password": "another-long-pass"})
    assert made.status_code == 200 and made.json()["role"] == "teacher"
    assert "hany" in [p["username"] for p in client.get("/api/school/people").json()["people"]]
    client.post("/api/session/sign-out")
    assert client.post("/api/session/sign-in", json={"username": "hany", "password": "another-long-pass"}).status_code == 200
    assert client.get("/api/school/people").status_code == 403
    assert client.post("/api/teachers", json={"name": "X Y", "username": "xyz", "password": "another-long-pass"}).status_code == 403
    assert client.post("/api/learners", json={"name": "Salma Ibrahim", "grade": 2}).status_code == 403   # no class yet
    client.post("/api/session/sign-out")
    client.post("/api/session/sign-in", json={"username": ADMIN["username"], "password": ADMIN["password"]})
    added = client.post("/api/learners", json={"name": "Salma Ibrahim", "grade": 2})
    assert added.status_code == 200 and added.json()["alias"].startswith("Learner ")
    with db.connect() as conn:
        logged = " ".join(r["input"] + r["output"] for r in db.rows(conn, "SELECT input, output FROM audit_log"))
    assert "Salma" not in logged                                      # the log holds the code, never the name


# ------------------------------------------------------------------ marks upload

def test_marks_sheet_is_checked_then_saved_once(db_path):
    table = _sheet(["A-01", "", "1", "3"], ["B-02", "ignored name", "٢", ""])    # Arabic digit, one blank
    checked = imports.check_marks(table, title="Unit quiz", year=2024, term=1, grade=5)
    assert checked["ok"] and checked["new_rows"] == 3 and checked["blank"] == 1
    saved = imports.save_marks(table, title="Unit quiz", year=2024, term=1, grade=5, teacher_id="tch_amina")
    assert saved["saved"] == 3
    with db.connect() as conn:
        rows = db.rows(conn, "SELECT * FROM evidence WHERE source_ref LIKE 'upload:%' ORDER BY learner_id, source_ref")
        logged = db.one(conn, "SELECT actor FROM audit_log WHERE tool = 'import_marks'")
    assert [(r["learner_id"], r["concept_id"], r["score"]) for r in rows] == [
        ("lrn_a", "fractions", 0.5), ("lrn_a", "ratios", 1.0), ("lrn_b", "fractions", 1.0)]
    assert all(r["kind"] == "quiz_item" and r["teacher_id"] == "tch_amina" and "ignored name" not in r["raw_text"] for r in rows)
    assert logged["actor"] == "teacher:tch_amina"
    again = imports.save_marks(table, title="Unit quiz", year=2024, term=1, grade=5, teacher_id="tch_amina")
    assert again["saved"] == 0 and again["skipped_already_saved"] == 3


def test_an_unclear_sheet_saves_nothing(db_path):
    table = _sheet(["A-01", "", "5", "x"], ["Z-99", "", "1", "1"], ["A-01", "", "1", "1"], topics=("fractions", "algebra-ii"))
    checked = imports.check_marks(table, title="", year=2024, term=1, grade=5)
    text = " ".join(checked["problems"])
    assert not checked["ok"]
    for expected in ("Give the quiz a name", "'algebra-ii' is not a topic", "outside 0 to 2", "'Z-99' is not a learner", "appears twice"):
        assert expected in text
    with pytest.raises(ValueError, match="still has problems"):
        imports.save_marks(table, title="", year=2024, term=1, grade=5, teacher_id="tch_amina")
    with db.connect() as conn:
        assert db.one(conn, "SELECT COUNT(*) AS n FROM evidence WHERE source_ref LIKE 'upload:%'")["n"] == 0
    assert not imports.check_marks([["just", "a", "list"]], title="Quiz", year=2024, term=1, grade=5)["ok"]


def test_template_round_trip_through_excel_and_the_web(client):
    template = client.get("/api/upload/template", params={"grade": 4, "term": 1, "questions": 2})
    assert template.status_code == 200
    table = imports.read_table("marks.xlsx", template.content)
    assert table[0][:3] == ["Learner code", "Name", "Q1"] and table[1][0] == "Topic" and table[2][0] == "Out of"
    codes = [row[0] for row in table[3:]]
    assert codes and all("-" in code for code in codes)

    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(template.content))
    sheet = book["Marks"]
    assert "Topics" in book.sheetnames
    sheet["C2"], sheet["D2"], sheet["C3"], sheet["D3"] = "fractions of a WHOLE", "ratios", 4, 2      # a label and an id both work
    sheet["C4"], sheet["D4"] = 3, 2
    filled = io.BytesIO()
    book.save(filled)
    form = {"title": "Week 3 quiz", "year": "2024", "term": "1", "grade": "4", "teacher_id": "tch_amina"}
    files = {"file": ("marks.xlsx", filled.getvalue(), "application/octet-stream")}
    checked = client.post("/api/upload/marks", data=form, files=files).json()["check"]
    assert checked["ok"], checked["problems"]
    assert [q["topic_id"] for q in checked["questions"]] == ["fractions", "ratios"]
    saved = client.post("/api/upload/marks", data={**form, "confirm": "true"}, files=files).json()["saved"]
    assert saved["saved"] == 2
    assert client.post("/api/upload/marks", data={**form, "teacher_id": "", "confirm": "true"}, files=files).status_code == 400


def test_csv_template_and_document_upload(client, tmp_path):
    csv_bytes = client.get("/api/upload/template", params={"grade": 4, "format": "csv"}).content
    assert csv_bytes.startswith(b"\xef\xbb\xbf") and imports.read_table("m.csv", csv_bytes)[0][0] == "Learner code"
    with pytest.raises(ValueError, match="Excel file"):
        imports.read_table("marks.pdf", b"%PDF")
    ok = client.post("/api/upload/document", data={"teacher_id": "tch_amina"},
                     files={"file": ("../../note one.txt", "C-31: ملاحظة".encode(), "text/plain")})
    assert ok.status_code == 200 and ok.json()["name"] == "note_one.txt"       # a path from the page is never followed
    assert any(f["name"] == "note_one.txt" for f in client.get("/api/inbox").json()["files"])
    bad = client.post("/api/upload/document", data={"teacher_id": "tch_amina"},
                      files={"file": ("run.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400


def test_a_marks_sheet_in_arabic_is_read_in_either_language(tmp_path, monkeypatch):
    """The Arabic template has Arabic row names and Arabic topic names. It is read whatever the reader's language."""
    from athar import synth_school
    from athar.curriculum import current_lang
    monkeypatch.setenv("ATHAR_DB", str(tmp_path / "athar.db"))
    made = synth_school.generate_school(db_path=tmp_path / "athar.db", pack_id="egypt-maths", out_dir=tmp_path, lang="ar")
    with open(made["sample_marks_sheet"], "rb") as fh:
        table = imports.read_table("sample.csv", fh.read())
    assert table[0][0] == "كود التلميذ" and table[1][0] == "الموضوع" and table[2][0] == "الدرجة من"
    grade = int(made["sample_marks_sheet"].split("marks-grade")[1].split("-")[0])
    for lang in ("en", "ar"):
        token = current_lang.set(lang)
        try:
            checked = imports.check_marks(table, title="اختبار قصير", year=2026, term=1, grade=grade)
            rows = imports.template_rows([{"alias": "Learner A-01", "name": "زينب أ."}], 2)
        finally:
            current_lang.reset(token)
        assert checked["ok"], checked["problems"]
        assert rows[0][0] == ("كود التلميذ" if lang == "ar" else "Learner code")
    assert len(imports.template_xlsx(imports.template_rows([], 2, "ar"), imports.topics(__import__("athar").curriculum.load_pack("egypt-maths"), 4, 1), "ar")) > 2000


def test_quizzes_named_in_arabic_or_in_two_subjects_do_not_collide():
    """Two different quizzes must never share a key, or the second is skipped as already saved."""
    from athar.curriculum import load_pack
    assert imports._slug("اختبار الكسور") != imports._slug("اختبار الهندسة")
    assert imports._slug("اختبار الكسور") == imports._slug("  اختبار   الكسور ")
    assert imports._slug("Fractions quiz, week 6") == "fractions-quiz-week-6" and imports._slug("!!!") == "quiz"
    pack = load_pack("egypt-school")
    maths = {"n": 1, "topic_id": "g4-place-value"}
    science = {"n": 1, "topic_id": next(c for c in pack.concepts if c.startswith("sci-g4-"))}
    one = imports._quiz_ref(pack, 2026, 1, 4, "Quiz 1", maths)
    assert one == imports._quiz_ref(pack, 2026, 1, 4, "Quiz 1", maths)              # the same quiz again
    assert one != imports._quiz_ref(pack, 2026, 1, 4, "Quiz 1", science)            # another subject
    assert one != imports._quiz_ref(pack, 2026, 1, 5, "Quiz 1", maths)              # another grade
    assert one != imports._quiz_ref(pack, 2026, 2, 4, "Quiz 1", maths)              # another term
