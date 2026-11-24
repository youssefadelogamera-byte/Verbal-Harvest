"""A whole synthetic school, the model picker, and reseeding over existing work."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from athar import db, review, synth, tools
from athar.curriculum import load_pack


@pytest.fixture(scope="module")
def school(tmp_path_factory):
    base = tmp_path_factory.mktemp("school")
    path = base / "athar.db"
    summary = synth.generate(db_path=path, n_learners=14, pack_id="generic-school", out_dir=base / "out", school=True)
    return path, summary


def test_school_has_staff_for_every_subject_and_each_teaches_their_own(school):
    path, summary = school
    assert summary["school"]["name"] == synth.SCHOOL_NAME and summary["counts"]["teachers"] == 10
    assert summary["school"]["teachers_by_subject"] == {"maths": 3, "science": 2, "language": 3, "technology": 2}
    pack = load_pack("generic-school")
    with db.connect(path) as conn:
        subject_of = {t["id"]: db.jload(t["subjects"], []) for t in db.rows(conn, "SELECT id, subjects FROM teachers")}
        units = db.rows(conn, "SELECT teacher_id, concept_id FROM teaching_units")
        mismatched = db.one(conn, "SELECT COUNT(*) AS n FROM evidence e JOIN teaching_units u ON u.id = e.unit_id "
                                  "WHERE e.teacher_id != u.teacher_id")["n"]
    assert all(len(subjects) == 1 for subjects in subject_of.values())
    assert units and all(subject_of[u["teacher_id"]] == [pack.strand_subject[pack.concepts[u["concept_id"]].strand]]
                         for u in units)
    assert mismatched == 0          # a record made in a unit carries that unit's teacher
    assert len({u["teacher_id"] for u in units}) == 10


def test_every_teacher_describes_how_they_teach_and_it_matches_what_they_recorded(school):
    path, _ = school
    pack = load_pack("generic-school")
    with db.connect(path) as conn:
        profiles = {p["teacher_id"]: db.jload(p["answers"], {}) for p in db.rows(conn, "SELECT * FROM teacher_profiles")}
        teachers = db.rows(conn, "SELECT id FROM teachers")
        for teacher in teachers:
            answers = profiles[teacher["id"]]
            assert set(answers) == {"approaches", "languages", "class_size", "what_works", "wants_help_with"}
            assert set(answers["approaches"]) == set(pack.approaches)
            assert set(answers["approaches"].values()) <= {"often", "sometimes", "rarely"}
            top = db.one(conn, "SELECT approach_id FROM teaching_units WHERE teacher_id = ? GROUP BY approach_id "
                               "ORDER BY COUNT(*) DESC, approach_id LIMIT 1", (teacher["id"],))
            assert answers["approaches"][top["approach_id"]] == "often"
            assert "{" not in answers["what_works"] + answers["wants_help_with"]
    assert len(profiles) == len(teachers) == 10


def test_the_school_layer_does_not_change_the_learners_or_their_records(tmp_path):
    def evidence(path):
        with db.connect(path) as conn:
            return db.rows(conn, "SELECT id, learner_id, kind, period_ord, concept_id, score, raw_text, unit_id "
                                 "FROM evidence ORDER BY id")
    plain, staffed = tmp_path / "a.db", tmp_path / "b.db"
    synth.generate(db_path=plain, n_learners=8, pack_id="generic-school", out_dir=tmp_path / "a")
    synth.generate(db_path=staffed, n_learners=8, pack_id="generic-school", out_dir=tmp_path / "b", school=True)
    assert evidence(plain) == evidence(staffed)
    with db.connect(plain) as conn:
        assert db.one(conn, "SELECT COUNT(*) AS n FROM teachers")["n"] == 6
        assert db.one(conn, "SELECT COUNT(*) AS n FROM teacher_profiles")["n"] == 0


def test_reseeding_works_after_the_agent_asked_for_a_record(tmp_path):
    """A record request points at a learner. Reseeding used to fail on that link."""
    path = tmp_path / "athar.db"
    synth.generate(db_path=path, n_learners=6, out_dir=tmp_path / "out")
    with db.connect(path) as conn:
        learner = db.one(conn, "SELECT id, pack_id FROM learners ORDER BY id LIMIT 1")
        seen = {r["concept_id"] for r in db.rows(conn, "SELECT DISTINCT concept_id FROM evidence WHERE learner_id = ? "
                                                       "AND score IS NOT NULL", (learner["id"],))}
        teacher = db.one(conn, "SELECT id FROM teachers LIMIT 1")["id"]
    concept = next(c for c in load_pack(learner["pack_id"]).concepts if c not in seen)
    asked = tools.request_record(learner_id=learner["id"], concept_id=concept, db_path=path,
                                 question="There are no records for this topic. Do you have a quiz?")
    review.answer_request(asked["request_id"], "no_record", teacher, db_path=path)
    synth.generate(db_path=path, n_learners=6, out_dir=tmp_path / "out")
    with db.connect(path) as conn:
        assert db.one(conn, "SELECT COUNT(*) AS n FROM record_requests")["n"] == 0
        assert db.one(conn, "SELECT COUNT(*) AS n FROM learners")["n"] == 6


# ---------------------------------------------------------------- choosing a model

@pytest.fixture()
def client(tmp_path, monkeypatch):
    path = tmp_path / "athar.db"
    monkeypatch.setenv("ATHAR_DB", str(path))
    synth.generate(db_path=path, n_learners=6, out_dir=tmp_path / "out")
    from athar.web.app import app
    return TestClient(app)


def test_models_endpoint_lists_what_the_endpoint_serves(client, monkeypatch):
    from athar.agent import llm
    monkeypatch.setattr(llm, "list_models", lambda: ["gemma-3-12b", "qwen3.5-9b"])
    monkeypatch.setenv("ATHAR_LLM_MODEL", "qwen3.5-9b")
    got = client.get("/api/models").json()
    assert got["models"] == ["gemma-3-12b", "qwen3.5-9b"] and got["default"] == "qwen3.5-9b" and got["problem"] is None


def test_models_endpoint_says_so_when_the_model_server_is_off(client, monkeypatch):
    from athar.agent import llm

    def down():
        raise ConnectionError("refused")
    monkeypatch.setattr(llm, "list_models", down)
    got = client.get("/api/models")
    assert got.status_code == 200 and got.json()["models"] == [] and "did not answer" in got.json()["problem"]


def test_list_models_leaves_out_embedding_models(monkeypatch):
    import httpx

    from athar.agent import llm

    class Reply:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "qwen3.5-9b"}, {"id": "text-embedding-nomic-embed-text-v1.5"}, {"id": "gemma-3-12b"}, {}]}
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: Reply())
    assert llm.list_models() == ["gemma-3-12b", "qwen3.5-9b"]


def test_a_run_takes_the_chosen_model_and_refuses_a_strange_id(client, monkeypatch):
    from athar.web import app as web
    started = []

    class Runner:
        def start(self, task):
            started.append(task)
            return {"run_id": "run_x", "status": "running"}
    monkeypatch.setattr(web, "_runner", lambda: Runner())
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    assert client.post("/api/runs", json={"learner_id": lid, "model": "gemma-3-12b"}).status_code == 200
    assert started[0]["model"] == "gemma-3-12b"
    assert client.post("/api/runs", json={"learner_id": lid}).status_code == 200 and "model" not in started[1]
    bad = client.post("/api/runs", json={"learner_id": lid, "model": "x; rm -rf / \n"})
    assert bad.status_code == 400 and len(started) == 2


# ---------------------------------------------------------------- invented names

def test_learners_get_invented_names_that_only_the_teacher_app_shows(client):
    shown = client.get("/api/learners").json()["learners"]
    names = [row["name"] for row in shown]
    assert len(set(names)) == len(names) == 6 and all(n.endswith(".") and not n.startswith("Learner") for n in names)
    assert all(row["alias"].startswith("Learner ") for row in shown)          # the record code is still there
    a17 = next(row for row in shown if row["alias"] == "Learner A-17")
    assert a17["name"] == synth.invented_name(0) == "Amani K."               # the same child every time
    # No tool result carries a name: an MCP client and the model only ever get the alias.
    listed = tools.list_learners()["learners"]
    assert all("name" not in row and "display_name" not in row for row in listed)
    timeline = tools.get_learner_timeline(learner_id=a17["learner_id"], limit=3)
    assert "display_name" not in timeline["learner"] and "Amani" not in str(timeline)
    page = client.get(f"/learners/{a17['learner_id']}/report").text
    assert "Learning report: Amani K." in page and "Record code A-17" in page


def test_a_database_made_before_names_existed_still_opens(tmp_path):
    import sqlite3
    old = tmp_path / "old.db"
    with sqlite3.connect(old) as conn:
        conn.execute("CREATE TABLE learners (id TEXT PRIMARY KEY, alias TEXT NOT NULL, pack_id TEXT NOT NULL, "
                     "start_year INTEGER NOT NULL, start_grade INTEGER NOT NULL, home_language TEXT NOT NULL DEFAULT 'en', "
                     "created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO learners VALUES ('lrn_1', 'Learner A-01', 'generic-maths', 2021, 3, 'en', 'x')")
    with db.connect(old) as conn:
        row = db.one(conn, "SELECT alias, display_name FROM learners")
        rows = tools.learner_rows(conn, names=True)
    assert row == {"alias": "Learner A-01", "display_name": None} and rows[0]["name"] == "Learner A-01"
