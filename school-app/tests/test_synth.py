import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from athar import synth
from athar.config import ROOT

PACK = ROOT / "packs" / "generic-maths" / "pack.yaml"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    base = tmp_path_factory.mktemp("synth")
    db_path = base / "a.db"
    summary = synth.generate(db_path=db_path, seed=7, out_dir=base / "out")
    return db_path, base / "out", summary


def _pack():
    return yaml.safe_load(PACK.read_text(encoding="utf-8"))


def _q(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_deterministic(tmp_path):
    results = []
    for name in ("one", "two"):
        db_path = tmp_path / f"{name}.db"
        synth.generate(db_path=db_path, seed=11, out_dir=tmp_path / name)
        n = _q(db_path, "SELECT COUNT(*) FROM evidence")[0][0]
        first = _q(db_path, "SELECT * FROM evidence ORDER BY rowid LIMIT 20")
        results.append((n, first))
    assert results[0][0] == results[1][0] > 500
    assert results[0][1] == results[1][1]


def test_concepts_exist_in_pack(run):
    db_path, _, _ = run
    ids = {c["id"] for c in _pack()["concepts"]}
    rows = _q(db_path, "SELECT concept_id, status FROM evidence WHERE concept_id IS NOT NULL")
    bad = [r for r in rows if r[0] not in ids and r[1] != "needs_review"]
    assert bad == []
    assert any(r[0] not in ids and r[1] == "needs_review" for r in rows)
    marks = ",".join("?" * len(ids))
    sql = f"SELECT COUNT(*) FROM teaching_units WHERE concept_id NOT IN ({marks})"
    assert _q(db_path, sql, tuple(ids))[0][0] == 0


def test_messiness(run):
    db_path, _, summary = run
    assert 4.0 <= summary["logged_late_pct"] <= 14.0
    assert summary["observations_without_concept"] >= 2
    dup = _q(db_path, "SELECT learner_id, source_ref, COUNT(*) FROM evidence "
                      "GROUP BY learner_id, source_ref HAVING COUNT(*) > 1")
    assert dup == []


def test_planted_a17(run):
    db_path, out_dir, _ = run
    pack = _pack()
    by_id = {c["id"]: c for c in pack["concepts"]}
    lid = _q(db_path, "SELECT id FROM learners WHERE alias = 'Learner A-17'")[0][0]

    def mean_for(pred):
        scores = [s for c, s in _q(
            db_path, "SELECT concept_id, score FROM evidence WHERE learner_id = ? AND kind = 'quiz_item' "
                     "AND score IS NOT NULL AND status = 'active'", (lid,)) if c in by_id and pred(by_id[c])]
        assert scores
        return sum(scores) / len(scores)

    assert mean_for(lambda c: c["id"] == "division-basic") < 0.5
    assert mean_for(lambda c: c["id"].startswith("ratio")) < 0.5
    assert mean_for(lambda c: c["strand"] == "geometry") > 0.8

    truth = json.loads((out_dir / "ground_truth.json").read_text(encoding="utf-8"))
    entry = next(x for x in truth["learners"] if x["alias"] == "Learner A-17")
    root = next(p for p in entry["planted"] if p["type"] == "root_cause")
    assert root["root_concept"] == "division-basic"
    year, term = int(root["root_period"][:4]), int(root["root_period"][-1])
    absent = _q(db_path, "SELECT absent_days FROM evidence WHERE learner_id = ? AND kind = 'attendance' "
                         "AND year = ? AND term = ?", (lid, year, term))
    assert absent and absent[0][0] >= 15


def test_other_planted_cases(run):
    db_path, out_dir, _ = run
    truth = json.loads((out_dir / "ground_truth.json").read_text(encoding="utf-8"))
    types = {p["type"] for e in truth["learners"] for p in e["planted"]}
    assert {"root_cause", "strength", "what_worked", "unknown_root", "too_little_data", "no_pattern"} <= types
    by_type = {p["type"]: (e, p) for e in truth["learners"] for p in e["planted"]}

    e, p = by_type["unknown_root"]
    year, term = int(p["missing_period"][:4]), int(p["missing_period"][-1])
    assert _q(db_path, "SELECT COUNT(*) FROM evidence WHERE learner_id = ? AND year = ? AND term = ?",
              (e["learner_id"], year, term))[0][0] == 0

    e, p = by_type["too_little_data"]
    n_terms = _q(db_path, "SELECT COUNT(DISTINCT period_ord) FROM evidence WHERE learner_id = ?",
                 (e["learner_id"],))[0][0]
    assert n_terms == 2

    e, p = by_type["what_worked"]
    assert p["n_concepts"] >= 3


def test_files(run):
    _, out_dir, _ = run
    (out_dir / "ground_truth.json").read_text(encoding="utf-8")
    inbox = out_dir / "inbox"
    names = ["quiz_sheet_A17_2025-T1.md", "teacher_note_A17_sw.txt", "teacher_note_ar.txt",
             "register_2025-T1.csv", "README.md"]
    for name in names:
        path = Path(inbox / name)
        assert path.exists(), name
        assert path.read_text(encoding="utf-8").strip()
    assert "Learner A-17" in (inbox / "quiz_sheet_A17_2025-T1.md").read_text(encoding="utf-8")
