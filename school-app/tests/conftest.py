"""A small hand-checkable dataset on the mini-maths test pack.

Planted cases:
  lrn_a  struggles with ratios; the root is division, taught in 2021-T2 with 18 days absent.
  lrn_b  strong in the geometry strand (and spatial reasoning) for 4 periods; multiplication is low
         in one term while addition is fine, so multiplication is its own root. It was taught in
         2021-T3 (unt_b1), a term with 1 day absent.
  lrn_c  "visual_models" is followed by clear gains over the learner's recent average twice;
         "worked_examples" once without a gain.
  lrn_d  ratios struggle whose path runs through fractions, which has no evidence (an unknown on the
         path); the root, division, has an unrecorded prerequisite (multiplication) that was
         taught while the learner was enrolled: a hole in the record, so the root is not certain.
  lrn_e  only two periods of data: no patterns. Addition is low but counting has no records, so
         where it began cannot be told.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("ATHAR_LANGUAGE", "en")   # the product opens in Arabic; these tests read English wording

from athar import db

FIXTURE_PACKS = Path(__file__).parent / "fixtures" / "packs"

LEARNERS = [  # id, alias, start_year, start_grade, home_language
    ("lrn_a", "Learner A-01", 2019, 1, "ar"),
    ("lrn_b", "Learner B-02", 2021, 1, "fr"),
    ("lrn_c", "Learner C-03", 2020, 1, "sw"),
    ("lrn_d", "Learner D-04", 2021, 1, "am"),
    ("lrn_e", "Learner E-05", 2022, 1, "en"),
]

TEACHERS = [("tch_amina", "Amina Okafor"), ("tch_jean", "Jean Dupont")]

UNITS = [  # id, teacher, year, term, grade, concept, approach
    ("unt_c1", "tch_amina", 2021, 2, 2, "multiplication", "visual_models"),
    ("unt_c2", "tch_amina", 2022, 1, 3, "division", "visual_models"),
    ("unt_c3", "tch_jean", 2021, 1, 2, "subtraction", "worked_examples"),
    # Taught to lrn_a's year group (grade - year == 1 - 2019) and to lrn_b's (1 - 2021); no evidence links
    # to them, so they only tell trace_root when the concept was taught.
    ("unt_a1", "tch_jean", 2021, 2, 3, "division", "worked_examples"),
    ("unt_b1", "tch_jean", 2021, 3, 1, "multiplication", "concrete_objects"),
]

EVIDENCE = [  # id, learner, kind, year, term, grade, concept, score, absent_days, unit, raw_text, language
    ("evd_a01", "lrn_a", "quiz_item", 2020, 1, 1, "multiplication", 0.8, None, None, None, "en"),
    ("evd_a02", "lrn_a", "quiz_item", 2020, 1, 1, "multiplication", 0.9, None, None, None, "en"),
    ("evd_a03", "lrn_a", "quiz_item", 2021, 2, 2, "division", 0.3, None, None, None, "en"),
    ("evd_a04", "lrn_a", "quiz_item", 2021, 2, 2, "division", 0.2, None, None, None, "en"),
    ("evd_a05", "lrn_a", "attendance", 2021, 2, 2, None, None, 18, None, None, "en"),
    ("evd_a06", "lrn_a", "attendance", 2022, 1, 3, None, None, 2, None, None, "en"),
    ("evd_a07", "lrn_a", "quiz_item", 2022, 1, 3, "fractions", 0.4, None, None, None, "en"),
    ("evd_a08", "lrn_a", "quiz_item", 2022, 1, 3, "fractions", 0.3, None, None, None, "en"),
    ("evd_a09", "lrn_a", "quiz_item", 2023, 1, 4, "ratios", 0.3, None, None, None, "en"),
    ("evd_a10", "lrn_a", "quiz_item", 2023, 1, 4, "ratios", 0.2, None, None, None, "en"),
    ("evd_a11", "lrn_a", "quiz_item", 2023, 2, 4, "ratios", 0.35, None, None, None, "en"),
    ("evd_a12", "lrn_a", "quiz_item", 2023, 3, 4, "ratios", 0.25, None, None, None, "en"),
    ("evd_a13", "lrn_a", "observation", 2023, 3, 4, "ratios", None, None, None,
     "يجد صعوبة في مقارنة الكميات", "ar"),

    ("evd_b01", "lrn_b", "quiz_item", 2021, 1, 1, "shapes-2d", 0.9, None, None, None, "fr"),
    ("evd_b02", "lrn_b", "quiz_item", 2021, 1, 1, "shapes-2d", 0.85, None, None, None, "fr"),
    ("evd_b03", "lrn_b", "quiz_item", 2021, 2, 1, "shapes-2d", 0.95, None, None, None, "fr"),
    ("evd_b04", "lrn_b", "project", 2021, 2, 1, "position-direction", 0.9, None, None,
     "Très bonne maîtrise du plan", "fr"),
    ("evd_b05", "lrn_b", "quiz_item", 2021, 3, 1, "position-direction", 0.85, None, None, None, "fr"),
    ("evd_b06", "lrn_b", "quiz_item", 2021, 3, 1, "position-direction", 0.9, None, None, None, "fr"),
    ("evd_b07", "lrn_b", "quiz_item", 2022, 1, 2, "area", 0.9, None, None, None, "fr"),
    ("evd_b08", "lrn_b", "quiz_item", 2022, 1, 2, "area", 0.95, None, None, None, "fr"),
    ("evd_b09", "lrn_b", "quiz_item", 2021, 1, 1, "addition", 0.6, None, None, None, "fr"),
    ("evd_b10", "lrn_b", "quiz_item", 2021, 3, 1, "addition", 0.7, None, None, None, "fr"),
    ("evd_b11", "lrn_b", "quiz_item", 2022, 1, 2, "subtraction", 0.65, None, None, None, "fr"),
    ("evd_b12", "lrn_b", "quiz_item", 2022, 1, 2, "multiplication", 0.3, None, None, None, "fr"),
    ("evd_b13", "lrn_b", "quiz_item", 2022, 1, 2, "multiplication", 0.2, None, None, None, "fr"),
    ("evd_b14", "lrn_b", "attendance", 2021, 3, 1, None, None, 1, None, None, "fr"),

    ("evd_c10", "lrn_c", "quiz_item", 2020, 2, 1, "addition", 0.5, None, None, None, "sw"),
    ("evd_c11", "lrn_c", "quiz_item", 2020, 2, 1, "addition", 0.5, None, None, None, "sw"),
    ("evd_c08", "lrn_c", "quiz_item", 2020, 3, 1, "subtraction", 0.5, None, None, None, "sw"),
    ("evd_c12", "lrn_c", "quiz_item", 2020, 3, 1, "addition", 0.4, None, None, None, "sw"),
    ("evd_c01", "lrn_c", "quiz_item", 2021, 1, 2, "multiplication", 0.3, None, None, None, "sw"),
    ("evd_c02", "lrn_c", "quiz_item", 2021, 1, 2, "multiplication", 0.4, None, None, None, "sw"),
    ("evd_c09", "lrn_c", "quiz_item", 2021, 1, 2, "subtraction", 0.55, None, "unt_c3", None, "sw"),
    ("evd_c03", "lrn_c", "quiz_item", 2021, 2, 2, "multiplication", 0.8, None, "unt_c1", None, "sw"),
    ("evd_c04", "lrn_c", "quiz_item", 2021, 2, 2, "multiplication", 0.9, None, "unt_c1",
     "Anaelewa kuzidisha kwa kutumia safu", "sw"),
    ("evd_c05", "lrn_c", "quiz_item", 2021, 3, 2, "division", 0.3, None, None, None, "sw"),
    ("evd_c13", "lrn_c", "quiz_item", 2021, 3, 2, "division", 0.4, None, None, None, "sw"),
    ("evd_c06", "lrn_c", "quiz_item", 2022, 1, 3, "division", 0.8, None, "unt_c2", None, "sw"),
    ("evd_c07", "lrn_c", "quiz_item", 2022, 1, 3, "division", 0.85, None, "unt_c2", None, "sw"),

    ("evd_d03", "lrn_d", "quiz_item", 2021, 1, 2, "division", 0.3, None, None, None, "am"),
    ("evd_d04", "lrn_d", "observation", 2021, 1, 2, "division", 0.35, None, None,
     "ማካፈል ላይ ችግር አለበት", "am"),
    ("evd_d05", "lrn_d", "quiz_item", 2023, 1, 4, "ratios", 0.2, None, None, None, "am"),
    ("evd_d06", "lrn_d", "quiz_item", 2023, 1, 4, "ratios", 0.3, None, None, None, "am"),

    ("evd_e01", "lrn_e", "quiz_item", 2022, 1, 1, "addition", 0.3, None, None, None, "en"),
    ("evd_e02", "lrn_e", "quiz_item", 2022, 2, 1, "addition", 0.2, None, None, None, "en"),
]


def seed(path: Path) -> None:
    """Insert the planted dataset directly, bypassing the tools."""
    with db.connect(path) as conn:
        for lid, alias, year, grade, lang in LEARNERS:
            conn.execute("INSERT INTO learners (id, alias, pack_id, start_year, start_grade, home_language, "
                         "created_at) VALUES (?,?,?,?,?,?,?)",
                         (lid, alias, "mini-maths", year, grade, lang, db.now_iso()))
        for tid, name in TEACHERS:
            conn.execute("INSERT INTO teachers (id, name, subjects) VALUES (?,?,?)", (tid, name, '["maths"]'))
        conn.executemany("INSERT INTO teaching_units (id, teacher_id, year, term, grade, concept_id, approach_id) "
                         "VALUES (?,?,?,?,?,?,?)", UNITS)
        for eid, lid, kind, year, term, grade, concept, score, absent, unit, text, lang in EVIDENCE:
            conn.execute(
                "INSERT INTO evidence (id, learner_id, kind, year, term, period_ord, grade, concept_id, score, "
                "absent_days, raw_text, language, source_ref, unit_id, recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (eid, lid, kind, year, term, db.period_ord(year, term), grade, concept, score, absent, text,
                 lang, f"test:{eid}", unit, db.now_iso()))


@pytest.fixture
def db_path(tmp_path, monkeypatch) -> Path:
    """A fresh seeded database. ATHAR_DB points at it so audit rows land there too."""
    path = tmp_path / "athar.db"
    monkeypatch.setenv("ATHAR_DB", str(path))
    monkeypatch.setenv("ATHAR_PACKS", str(FIXTURE_PACKS))
    monkeypatch.delenv("ATHAR_ACTOR", raising=False)
    monkeypatch.delenv("ATHAR_RUN_ID", raising=False)
    db.init_db(path)
    seed(path)
    return path
