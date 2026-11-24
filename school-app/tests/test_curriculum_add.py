"""Adding to the curriculum: a draft, a teacher's approval, and the pack with the addition laid over it."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from athar import curriculum_add, db, family, server
from athar.curriculum import load_pack

TEACHER = "tch_reviewer"
LINES = """# Numbers up to 1000
Term 1
Counting to 1000 | العد حتى 1000
Place value of three-digit numbers | القيمة المكانية للأعداد من ثلاثة أرقام
الفصل الدراسي الثاني
1. Adding three-digit numbers
2. Subtracting three-digit numbers
"""


def _packs_from_year_4(folder):
    """The installed Cambridge packs with Years 1 to 3 taken out, so a school can add Year 3 below them."""
    import yaml

    from athar.config import ROOT

    for name in ("cambridge-maths", "cambridge-science", "cambridge-english", "cambridge-school"):
        data = yaml.safe_load((ROOT / "packs" / name / "pack.yaml").read_text(encoding="utf-8"))
        kept = [c for c in data.get("concepts") or [] if c["grade"] >= 4]
        ids = {c["id"] for c in kept}
        for c in kept:
            c["requires"] = [r for r in c["requires"] if r in ids]
        if data.get("concepts"):
            data["concepts"] = kept
        data["grades"] = [4, 11]
        data["links"] = [x for x in data.get("links") or [] if x["concept"][1:2].isdigit() and int(x["concept"][1:].split("-")[0]) >= 4
                         and all(int(r[1:].split("-")[0]) >= 4 for r in x["requires"])]
        (folder / name).mkdir(parents=True)
        (folder / name / "pack.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return folder


@pytest.fixture
def school(tmp_path, monkeypatch):
    """An empty database on the Cambridge packs from Year 4 up, with one named teacher."""
    path = tmp_path / "athar.db"
    monkeypatch.setenv("ATHAR_DB", str(path))
    monkeypatch.setenv("ATHAR_PACK", "cambridge-school")
    monkeypatch.setenv("ATHAR_PACKS", str(_packs_from_year_4(tmp_path / "packs")))
    db.init_db(path)
    with db.connect(path) as conn:
        conn.execute("INSERT INTO teachers (id, name, subjects) VALUES (?,?,?)", (TEACHER, "Reviewer One", '["maths"]'))
    return path


def _draft(**more):
    return curriculum_add.create_draft(load_pack(), subject_id="maths", grade=3, text=LINES, actor=TEACHER, **more)


def test_typed_lines_become_a_draft_and_change_nothing(school):
    before = len(load_pack().concepts)
    draft = _draft()
    assert [t["en"] for t in draft["topics"]] == ["Counting to 1000", "Place value of three-digit numbers",
                                                 "Adding three-digit numbers", "Subtracting three-digit numbers"]
    assert [t["term"] for t in draft["topics"]] == [1, 1, 2, 2]
    assert draft["topics"][0]["ar"] == "العد حتى 1000"
    assert draft["areas"] == [{"key": "a1", "en": "Numbers up to 1000", "ar": ""}]
    assert {t["area"] for t in draft["topics"]} == {"a1"} and draft["read_by"] == "typed"
    assert draft["status"] == "draft" and draft["menus"]["areas"] and draft["menus"]["topics"]
    assert len(load_pack().concepts) == before and load_pack().grades == (4, 11)      # a draft is not in the curriculum


def test_a_named_teacher_must_tick_the_box_to_approve(school):
    draft = _draft()
    pack = load_pack()
    with pytest.raises(ValueError, match="Tick the box"):
        curriculum_add.approve(pack, draft["id"], teacher_id=TEACHER, checked=False)
    with pytest.raises(ValueError, match="Choose your name"):
        curriculum_add.approve(pack, draft["id"], teacher_id="tch_nobody", checked=True)
    assert load_pack().grades == (4, 11)


def test_an_approved_addition_is_laid_over_the_pack_and_the_file_is_untouched(school):
    from athar.config import get_settings

    pack_file = get_settings().packs_dir / "cambridge-maths" / "pack.yaml"
    before_bytes, before = pack_file.read_bytes(), len(load_pack().concepts)
    draft = _draft()
    topics = draft["topics"]
    topics[2]["needs"] = [topics[1]["key"]]                       # adding needs place value
    topics[1]["needed_by"] = ["m4-place-value-10000"]                   # and the grade 4 topic needs the new one
    curriculum_add.save_draft(load_pack(), draft["id"], topics=topics, areas=draft["areas"], actor=TEACHER)
    done = curriculum_add.approve(load_pack(), draft["id"], teacher_id=TEACHER, checked=True)
    assert done == {"id": draft["id"], "status": "approved", "topics": 4, "approved_by": "Reviewer One"}

    pack = load_pack()
    added = pack.additions[0]["concepts"]
    assert len(pack.concepts) == before + 4 and pack.grades == (3, 11)
    assert pack.label(added[0], "ar") == "العد حتى 1000" and pack.concepts[added[0]].grade == 3
    assert pack.prerequisites(added[2]) == [added[1]]
    assert added[1] in pack.prerequisites("m4-place-value-10000")       # the trace-back now reaches into Year 3
    assert added[1] in pack.ancestors("m4-negative")
    assert pack.strand_subject[pack.concepts[added[0]].strand] == "maths"
    assert pack_file.read_bytes() == before_bytes                 # the installed curriculum is never rewritten
    with db.connect() as conn:
        tools = [r["tool"] for r in db.rows(conn, "SELECT tool FROM audit_log ORDER BY id")]
    assert tools == ["curriculum_draft", "curriculum_approve"]


def test_a_link_to_a_later_topic_or_an_unknown_one_is_dropped(school):
    draft = _draft()
    topics = draft["topics"]
    topics[0]["needs"] = [topics[2]["key"], "m4-place-value-10000", "no-such-topic", topics[0]["key"]]   # later term, later grade, unknown, itself
    topics[3]["needed_by"] = ["s4-food-chains", "no-such-topic"]                                    # another subject
    topics[1]["skills"] = ["reasoning", "not-a-skill"]
    saved = curriculum_add.save_draft(load_pack(), draft["id"], topics=topics, areas=draft["areas"], actor=TEACHER)
    assert saved["topics"][0]["needs"] == [] and saved["topics"][3]["needed_by"] == []
    assert saved["topics"][1]["skills"] == ["reasoning"]


def _model(monkeypatch, replies):
    """Stand in for the model: each call gets the next canned reply, and the prompts are kept."""
    seen = []

    class Reply:
        status_code = 200

        def __init__(self, data):
            self._data = data

        def json(self):
            return {"choices": [{"message": {"content": "Here you are:\n```json\n" + json.dumps(self._data) + "\n```"}}]}

    def post(url, json=None, **kwargs):
        seen.append(json)
        return Reply(replies[len(seen) - 1])

    monkeypatch.setattr(curriculum_add.httpx, "post", post)
    return seen


def test_what_the_model_returns_is_checked_in_plain_code(school, monkeypatch):
    seen = _model(monkeypatch, [
        {"topics": [{"en": "Counting to 1000", "ar": "العد حتى 1000", "term": 1, "area": "number", "skills": ["fluency", "made-up"]},
                    {"en": "Comparing numbers to 1000", "term": 2, "area": "Number", "skills": []},   # the area by its name
                    {"en": "counting to 1000", "term": 1, "area": "number"},                 # the same topic twice
                    {"en": "", "term": 1}, "not a topic"]},
        {"needs": {"N2": ["N1", "m4-place-value-10000", "invented-id"], "N1": ["N2"]}},           # a later grade, an invented id, and a loop
        {"needs": {"m4-place-value-10000": ["N1", "N9"], "g8-not-real": ["N1"]}},
    ])
    draft = curriculum_add.create_draft(load_pack(), subject_id="maths", grade=3, text="a contents page", use_model=True,
                                        model="test-model", actor=TEACHER)
    first, second = draft["topics"]
    assert len(draft["topics"]) == 2 and draft["read_by"] == "model:test-model"
    assert first["area"] == "number" and second["area"] == "number" and draft["areas"] == []
    assert first["skills"] == ["fluency"] and first["from"] == "model"
    assert second["needs"] == [first["key"]] and first["needs"] == []
    assert first["needed_by"] == ["m4-place-value-10000"]
    assert "a contents page" in seen[0]["messages"][0]["content"] and "number:" in seen[0]["messages"][0]["content"]
    assert load_pack().grades == (4, 11)                           # still only a draft


def test_a_picture_goes_to_the_model_and_needs_it(school, monkeypatch):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    with pytest.raises(ValueError, match="only be read by the model"):
        curriculum_add.create_draft(load_pack(), subject_id="maths", grade=3, image=png, actor=TEACHER)
    seen = _model(monkeypatch, [{"topics": [{"en": "Counting to 1000", "area": "number"}]}, {"needs": {}}, {"needs": {}}])
    curriculum_add.create_draft(load_pack(), subject_id="maths", grade=3, image=png, use_model=True, actor=TEACHER)
    assert seen[0]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_a_new_subject_gets_its_own_area(school):
    draft = curriculum_add.create_draft(load_pack(), new_subject="Computing", grade=5, term=2,
                                        text="How a computer stores numbers\nWriting a first program", actor=TEACHER)
    assert draft["subject"]["new"] and draft["areas"] == [{"key": "a1", "en": "General", "ar": "عام"}]
    assert [t["term"] for t in draft["topics"]] == [2, 2]
    curriculum_add.approve(load_pack(), draft["id"], teacher_id=TEACHER, checked=True)
    pack = load_pack()
    subject = next(s for s in pack.subjects if s.startswith("add-"))
    assert pack.label(subject) == "Computing" and len(pack.additions[0]["concepts"]) == 2
    with pytest.raises(ValueError, match="Choose the subject"):
        curriculum_add.create_draft(pack, grade=5, text="A topic", actor=TEACHER)


def test_withdrawing_is_refused_once_a_record_uses_a_topic(school):
    draft = _draft()
    curriculum_add.approve(load_pack(), draft["id"], teacher_id=TEACHER, checked=True)
    topic = load_pack().additions[0]["concepts"][0]
    with db.connect() as conn:
        conn.execute("INSERT INTO learners (id, alias, pack_id, start_year, start_grade, home_language, created_at) "
                     "VALUES ('lrn_x','Learner X-1','cambridge-school',2026,3,'ar',?)", (db.now_iso(),))
        conn.execute("INSERT INTO evidence (id, learner_id, kind, year, term, period_ord, grade, concept_id, score, "
                     "language, source_ref, recorded_at) VALUES ('evd_x','lrn_x','quiz_item',2026,1,?,3,?,0.5,'ar','test',?)",
                     (db.period_ord(2026, 1), topic, db.now_iso()))
    with pytest.raises(ValueError, match="1 records already use"):
        curriculum_add.withdraw(draft["id"], actor=TEACHER)
    with db.connect() as conn:
        conn.execute("DELETE FROM evidence WHERE id = 'evd_x'")
    assert curriculum_add.withdraw(draft["id"], actor=TEACHER)["status"] == "withdrawn"
    assert load_pack().grades == (4, 11) and load_pack().additions == []


def test_an_addition_that_no_longer_fits_is_left_out_and_the_curriculum_still_loads(school):
    good, broken = _draft(title="Good"), _draft(title="Broken")
    curriculum_add.approve(load_pack(), good["id"], teacher_id=TEACHER, checked=True)
    curriculum_add.approve(load_pack(), broken["id"], teacher_id=TEACHER, checked=True)
    assert len(load_pack().additions) == 2
    with db.connect() as conn:
        body = db.jload(db.one(conn, "SELECT approved FROM curriculum_additions WHERE id = ?", (broken["id"],))["approved"])
        body["concepts"][0]["requires"] = ["a-topic-that-is-gone"]
        conn.execute("UPDATE curriculum_additions SET approved = ?, decided_at = ? WHERE id = ?",
                     (db.jdump(body), "2099-01-01T00:00:00+00:00", broken["id"]))
    pack = load_pack()
    assert [a["id"] for a in pack.additions] == [good["id"]] and "m4-place-value-10000" in pack.concepts


def test_files_a_school_might_upload():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml",
                         '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                         "<w:p><w:r><w:t>Counting to </w:t></w:r><w:r><w:t>1000</w:t></w:r></w:p><w:p><w:r><w:t>الكسور</w:t></w:r></w:p>"
                         "</w:body></w:document>")
    assert curriculum_add.text_of_file("book.docx", buffer.getvalue()) == "Counting to 1000\nالكسور"
    assert curriculum_add.text_of_file("list.txt", "الكسور\n".encode()) == "الكسور\n"
    with pytest.raises(ValueError, match="screenshot or a photo"):
        curriculum_add.text_of_file("book.pdf", b"%PDF-1.7")
    with pytest.raises(ValueError, match="could not be opened"):
        curriculum_add.text_of_file("book.docx", b"not a zip")


def test_the_agent_has_no_tool_that_touches_the_curriculum():
    import asyncio

    names = [tool.name for tool in asyncio.run(server.mcp.list_tools())]
    assert names and not [n for n in names if "curriculum" in n or "addition" in n]


# ------------------------------------------------------------------ over the web

@pytest.fixture
def client(school):
    from athar.web.app import app

    return TestClient(app)


def test_the_page_flow_from_draft_to_approved(client):
    assert client.post("/api/curriculum/drafts", data={"subject": "maths", "grade": "3", "text": LINES}).status_code == 400
    made = client.post("/api/curriculum/drafts", data={"subject": "maths", "grade": "3", "text": LINES, "teacher_id": TEACHER})
    assert made.status_code == 200, made.text
    draft = made.json()
    listed = client.get("/api/curriculum").json()
    assert listed["can_add"] and listed["installed_grades"] == [4, 11]
    assert [(a["status"], a["topic_count"]) for a in listed["additions"]] == [("draft", 4)]
    edit = {"teacher_id": TEACHER, "title": "Maths, Primary 3", "topics": draft["topics"][:3], "areas": draft["areas"]}
    assert client.post(f"/api/curriculum/drafts/{draft['id']}/approve", json=edit).status_code == 400      # no tick
    done = client.post(f"/api/curriculum/drafts/{draft['id']}/approve", json={**edit, "checked": True})
    assert done.status_code == 200 and done.json()["topics"] == 3
    after = client.get("/api/curriculum").json()
    assert after["installed_grades"] == [3, 11] and after["additions"][0]["in_use"]
    assert after["additions"][0]["decided_by"] == "Reviewer One" and after["additions"][0]["title"] == "Maths, Primary 3"
    assert client.get("/api/session").json()["curriculum"]["grades"] == [3, 11]
    assert client.post(f"/api/curriculum/additions/{draft['id']}/withdraw", json={"teacher_id": TEACHER}).status_code == 200
    assert client.get("/api/curriculum").json()["installed_grades"] == [4, 11]


def test_a_parent_cannot_add_to_the_curriculum(client, school):
    family.choose("family", "A Parent", db_path=school)
    refused = client.post("/api/curriculum/drafts", data={"subject": "maths", "grade": "3", "text": LINES, "teacher_id": TEACHER})
    assert refused.status_code == 403 and "school side" in refused.json()["error"]
    assert client.get("/api/curriculum").json()["can_add"] is False


def test_lazy_answers_from_a_model_are_taken_out_in_plain_code(school, monkeypatch):
    names = ["Plants", "Animals", "States of matter", "Heating and cooling", "Light"]
    areas = ["bio", "bio", "chem", "chem", "phys"]
    _model(monkeypatch, [
        {"topics": [{"en": n, "area": a, "term": 1, "skills": ["investigating"] + (["modelling"] if i == 0 else [])}
                    for i, (n, a) in enumerate(zip(names, areas, strict=True))]},
        {"needs": {"N2": ["N1"], "N3": ["N2", "N1"], "N4": ["N3", "N2"], "N5": ["N4"]}},     # each chained to the one before
        {"needs": {}},
    ])
    draft = curriculum_add.create_draft(load_pack(), subject_id="science", grade=3, text="a page", use_model=True, actor=TEACHER)
    topics = draft["topics"]
    assert [t["skills"] for t in topics] == [["modelling"], [], [], [], []]        # the skill on every topic is gone
    assert [t["needs"] for t in topics] == [[], ["t1"], [], ["t3"], []]                      # no link across two areas


def test_a_link_that_only_repeats_a_longer_path_is_dropped():
    topics = [{"key": "t1", "needs": []}, {"key": "t2", "needs": ["t1"]}, {"key": "t3", "needs": ["t2", "t1", "g4-installed"]}]
    curriculum_add._drop_shortcuts(topics)
    assert topics[2]["needs"] == ["t2", "g4-installed"] and topics[1]["needs"] == ["t1"]
