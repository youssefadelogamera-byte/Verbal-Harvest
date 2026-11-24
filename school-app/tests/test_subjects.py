"""More than one subject: the subject packs, the whole-school pack, and tracing across subjects."""

import pytest

from athar import db, graph, story, synth
from athar.curriculum import load_pack
from athar.web import people

SUBJECT_PACKS = ("generic-maths", "generic-science", "generic-language", "generic-technology")


@pytest.mark.parametrize("pack_id", SUBJECT_PACKS)
def test_each_subject_pack_stands_alone(pack_id):
    pack = load_pack(pack_id)
    assert len(pack.concepts) >= 15 and len(pack.subjects) == 1
    assert set(pack.strand_subject.values()) == set(pack.subjects)


def test_school_pack_is_the_subject_packs_plus_cross_subject_links():
    school = load_pack("generic-school")
    assert list(school.subjects) == ["maths", "science", "language", "technology"]
    assert len(school.concepts) == sum(len(load_pack(p).concepts) for p in SUBJECT_PACKS)
    # A physics topic needs maths first, and a maths topic needs reading first.
    assert {"division-long", "unit-rates"} <= set(school.prerequisites("speed-distance-time"))
    assert "literal-comprehension" in school.prerequisites("problem-solving-multistep")
    # The link exists only in the school pack; the maths pack on its own is unchanged.
    assert "literal-comprehension" not in load_pack("generic-maths").concepts


@pytest.fixture(scope="module")
def school_db(tmp_path_factory):
    base = tmp_path_factory.mktemp("school")
    synth.generate(db_path=base / "athar.db", out_dir=base / "out", pack_id="generic-school")
    return base / "athar.db"


def test_a_maths_difficulty_is_traced_back_to_reading(school_db):
    with db.connect(school_db) as conn:
        learner = db.one(conn, "SELECT id FROM learners WHERE alias LIKE '%R-08'")
    traced = graph.trace_root(learner["id"], "problem-solving-multistep", db_path=school_db)
    assert traced["root"]["concept_id"] == "literal-comprehension"
    assert traced["path"] == ["problem-solving-multistep", "literal-comprehension"]
    assert traced["evidence_ids"]


def test_learner_picture_reports_every_subject(school_db):
    with db.connect(school_db) as conn:
        learner = db.one(conn, "SELECT id FROM learners WHERE alias LIKE '%R-08'")
    mind = people.learner_mind(learner["id"], db_path=school_db)
    assert {s["id"] for s in mind["subjects"]} == {"maths", "science", "language", "technology"}
    assert all(s["n"] > 0 and 0 <= s["mean"] <= 1 for s in mind["subjects"])


def test_story_runs_on_the_school_pack(school_db):
    out = story.build(db_path=school_db)
    assert "Learner R-08" in out["learners"] and out["waiting"] >= 1


def test_the_default_cohort_has_no_cross_subject_learner(tmp_path):
    synth.generate(db_path=tmp_path / "athar.db", out_dir=tmp_path / "out")
    with db.connect(tmp_path / "athar.db") as conn:
        assert db.one(conn, "SELECT id FROM learners WHERE alias LIKE '%R-08'") is None
