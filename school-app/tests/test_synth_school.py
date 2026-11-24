"""The pack-driven school generator: what it plants, the engine finds, on any pack."""

from __future__ import annotations

import json

import pytest

from athar import db, graph, imports, synth_school
from athar.curriculum import load_pack

PACKS = ["generic-maths", "cambridge-maths", "cambridge-science", "cambridge-english", "cambridge-school"]


@pytest.fixture(scope="module", params=PACKS)
def school(request, tmp_path_factory):
    base = tmp_path_factory.mktemp("school-" + request.param)
    mp = pytest.MonkeyPatch()
    mp.setenv("ATHAR_DB", str(base / "athar.db"))
    summary = synth_school.generate_school(db_path=base / "athar.db", pack_id=request.param, out_dir=base)
    truth = json.loads((base / "ground_truth.json").read_text(encoding="utf-8"))
    yield {"pack": load_pack(request.param), "summary": summary, "truth": truth, "base": base}
    mp.undo()


def test_same_seed_same_school(school, tmp_path):
    again = synth_school.generate_school(db_path=tmp_path / "again.db", pack_id=school["pack"].id, out_dir=tmp_path)
    assert again["counts"] == school["summary"]["counts"] and again["planted"] == school["summary"]["planted"]


def test_school_shape(school):
    pack = school["pack"]
    with db.connect() as conn:
        learners = db.rows(conn, "SELECT * FROM learners")
        grades = {r["grade"] for r in db.rows(conn, "SELECT DISTINCT grade FROM evidence")}
        current = db.rows(conn, "SELECT DISTINCT term FROM evidence WHERE year = ?", (synth_school.CURRENT_YEAR,))
        bad_terms = db.one(conn, "SELECT COUNT(*) AS n FROM evidence WHERE term > ?", (pack.terms,))["n"]
        accounts = db.one(conn, "SELECT COUNT(*) AS n FROM accounts")["n"]
        unknown = db.rows(conn, "SELECT DISTINCT concept_id FROM evidence WHERE concept_id IS NOT NULL")
    assert len(learners) == 40 and all(row["display_name"] and row["alias"].startswith("Learner ") for row in learners)
    assert grades <= set(range(pack.grades[0], pack.grades[1] + 1)) and pack.grades[1] in grades
    assert [r["term"] for r in current] == [1]                 # the current year stops in term 1
    assert bad_terms == 0 and accounts == 0                    # no account is ever seeded
    assert {r["concept_id"] for r in unknown} <= set(pack.concepts)


def test_engine_finds_the_planted_patterns(school):
    by_case: dict[str, list[dict]] = {}
    for plant in school["truth"]["planted"]:
        by_case.setdefault(plant["case"], []).append(plant)
    assert by_case.get("root_gap") and by_case.get("strand_strength") and by_case.get("what_worked")
    for plant in by_case["root_gap"]:
        trace = graph.trace_root(plant["learner_id"], plant["later"][-1])
        assert trace["root"] and trace["root"]["concept_id"] == plant["root"], plant
    for plant in by_case.get("unknown_root", []):              # the honest answer: the record cannot say
        trace = graph.trace_root(plant["learner_id"], plant["later"][-1])
        assert not trace.get("root_is_certain"), plant
    for plant in by_case["strand_strength"]:
        found = graph.find_patterns(plant["learner_id"])["patterns"]
        assert any(p["kind"] == "strength" and p["scope_id"] == plant["strand"] for p in found), plant
    for plant in by_case["what_worked"]:
        best = max(graph.what_worked(plant["learner_id"])["approaches"], key=lambda a: a["improved"] - a["not_improved"])
        assert best["approach_id"] == plant["approach"], plant
    for plant in by_case.get("no_pattern", []):
        assert graph.find_patterns(plant["learner_id"])["patterns"] == []


def test_sample_marks_sheet_uploads_cleanly(school):
    path = school["summary"]["sample_marks_sheet"]
    with open(path, "rb") as fh:
        table = imports.read_table("sample.csv", fh.read())
    grade = int(path.split("marks-grade")[1].split("-")[0])
    checked = imports.check_marks(table, title="Sample quiz", year=synth_school.CURRENT_YEAR, term=1, grade=grade)
    assert checked["ok"], checked["problems"]
    assert checked["new_rows"] == 5 * len(checked["learners"]) > 0


@pytest.mark.parametrize("pack_id", ["cambridge-maths", "cambridge-science", "cambridge-english"])
def test_cambridge_pack_is_sourced_and_termed(pack_id):
    pack = load_pack(pack_id)
    assert pack.grades == (1, 11) and pack.terms == 3
    assert {c.grade for c in pack.concepts.values()} == set(range(1, 12))      # every year, Primary to IGCSE
    for concept in pack.concepts.values():
        assert concept.term in (1, 2, 3), concept.id
        assert concept.source, f"{concept.id} has no source"
        assert all(pack.concepts[r].grade <= concept.grade for r in concept.requires), concept.id
    # a topic may only need topics taught earlier: an earlier grade, or the same grade no later in the year
    for concept in pack.concepts.values():
        for needed in (pack.concepts[r] for r in concept.requires):
            assert (needed.grade, needed.term) <= (concept.grade, concept.term), (concept.id, needed.id)


BAD_PACK = """id: bad
name: Bad
subject: maths
grades: [1, 1]
strands:
  - {id: s, label: {en: One, two}}
concepts:
  - {id: c, label: {en: C}, strand: s, grade: 1}
"""


def test_no_pack_label_is_cut_at_a_comma(tmp_path):
    """`{en: Ratio, proportion and percent}` without quotes reads as the label "Ratio". The loader refuses it."""
    from athar.config import get_settings
    for folder in sorted(p for p in get_settings().packs_dir.iterdir() if (p / "pack.yaml").exists()):
        load_pack(folder.name)
    assert load_pack("cambridge-maths").label("frac") == "Fractions, decimals, percentages and ratio"
    bad = tmp_path / "bad" / "pack.yaml"
    bad.parent.mkdir()
    bad.write_text(BAD_PACK, encoding="utf-8")
    with pytest.raises(ValueError, match="quotes"):
        load_pack("bad", packs_dir=tmp_path)


def test_story_and_classes_on_a_generated_school(school):
    """The presenting state is built from the planted list, and every grade has a class with a teacher."""
    from athar import classes, story
    made = story.build()
    assert made["proposed"] >= 2 and made["approved"] >= 1 and len(made["learners"]) >= 3
    found = classes.list_classes()
    assert len(found) == school["pack"].grades[1] - school["pack"].grades[0] + 1
    # 40 learners spread over the grades as evenly as they go (11 grades: three or four in each)
    assert sum(len(c["learners"]) for c in found) == 40
    assert all(c["teachers"] and len(c["learners"]) in (40 // len(found), -(-40 // len(found)))
               and c["year"] == synth_school.CURRENT_YEAR for c in found)
    with db.connect() as conn:
        teacher = db.one(conn, "SELECT teacher_id FROM class_teachers LIMIT 1")["teacher_id"]
    own = {x["learner_id"] for c in found if any(t["teacher_id"] == teacher for t in c["teachers"]) for x in c["learners"]}
    assert set(classes.visible({"id": teacher, "role": "teacher"})) == own
    assert classes.visible({"id": teacher, "role": "admin"}) is None
