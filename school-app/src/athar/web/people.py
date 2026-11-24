"""The learner's picture and the teacher's way of teaching, side by side.

Three rules hold here:
- A learner is described by what the records show (results by strand and by thinking skill), never by a label.
- A teacher describes their own way of teaching. Nothing here scores or ranks a teacher.
- "Fit" puts two facts next to each other: what was followed by gains for this learner, and how often
  this teacher says they teach that way. The teacher draws the conclusion.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from .. import audit, db, graph
from ..curriculum import Pack, load_pack

FREQUENCIES = ("often", "sometimes", "rarely")
_PROFILE_TABLE = """
CREATE TABLE IF NOT EXISTS teacher_profiles (
  teacher_id TEXT PRIMARY KEY REFERENCES teachers(id),
  answers    TEXT NOT NULL,                 -- JSON: the teacher's own answers
  updated_at TEXT NOT NULL
);
"""


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _state(mean: float | None) -> str:
    if mean is None:
        return "unseen"
    return "strong" if mean >= graph.STRENGTH_ABOVE else "gap" if mean < graph.STRUGGLE_BELOW else "shaky"


# ------------------------------------------------------------------ learner

def learner_mind(learner_id: str, db_path=None) -> dict[str, Any]:
    """Everything connected to one learner, for the knowledge graph and the strengths picture."""
    with db.connect(db_path) as conn:
        learner = db.one(conn, "SELECT * FROM learners WHERE id = ?", (learner_id,))
        if learner is None:
            raise ValueError(f"Unknown learner '{learner_id}'.")
        evidence = db.rows(conn, "SELECT concept_id, skill_id, score, unit_id FROM evidence "
                                 "WHERE learner_id = ? AND status != 'retracted'", (learner_id,))
        unit_ids = sorted({e["unit_id"] for e in evidence if e["unit_id"]})
        units: list[dict] = []
        if unit_ids:
            marks = ",".join("?" for _ in unit_ids)
            units = db.rows(conn, f"SELECT u.approach_id, t.id AS teacher_id, t.name FROM teaching_units u "
                                  f"JOIN teachers t ON t.id = u.teacher_id WHERE u.id IN ({marks})", tuple(unit_ids))
    pack = load_pack(learner["pack_id"])
    by_strand: dict[str, list[float]] = defaultdict(list)
    by_skill: dict[str, list[float]] = defaultdict(list)
    for e in evidence:
        if e["score"] is None:
            continue
        concept = pack.concepts.get(e["concept_id"]) if e["concept_id"] else None
        if concept:
            by_strand[concept.strand].append(e["score"])
        if e["skill_id"]:
            by_skill[e["skill_id"]].append(e["score"])
    strands = [{"id": sid, "label": pack.label(sid), "mean": _mean(by_strand[sid]), "n": len(by_strand[sid]),
                "subject": pack.strand_subject.get(sid), "state": _state(_mean(by_strand[sid]))}
               for sid in pack.strands if by_strand.get(sid)]
    subjects = []
    for subject_id in pack.subjects:
        scores = [x for sid, values in by_strand.items() if pack.strand_subject.get(sid) == subject_id for x in values]
        if scores:
            subjects.append({"id": subject_id, "label": pack.label(subject_id), "mean": _mean(scores), "n": len(scores),
                             "state": _state(_mean(scores))})
    # Thinking skills only. A disposition (such as persistence) is never summarised as a trait of a child.
    skills = [{"id": kid, "label": pack.label(kid), "mean": _mean(by_skill[kid]), "n": len(by_skill[kid]),
               "state": _state(_mean(by_skill[kid]))}
              for kid in pack.skills if by_skill.get(kid) and pack.skill_kinds.get(kid, "thinking") != "disposition"]
    teachers: dict[str, dict[str, Any]] = {}
    for u in units:
        mine = teachers.setdefault(u["teacher_id"], {"teacher_id": u["teacher_id"], "name": u["name"], "units": 0})
        mine["units"] += 1
    worked = graph.what_worked(learner_id, db_path=db_path)
    approaches = [{"id": a["approach_id"], "label": a["label"], "improved": a["improved"],
                   "not_improved": a["not_improved"]} for a in worked.get("approaches", [])]
    return {"learner": {"learner_id": learner_id, "alias": learner["alias"],
                        "name": learner.get("display_name") or learner["alias"]}, "subjects": subjects,
            "strands": strands, "skills": skills,
            "teachers": sorted(teachers.values(), key=lambda t: t["name"]), "approaches": approaches,
            "thresholds": {"strong_above": graph.STRENGTH_ABOVE, "gap_below": graph.STRUGGLE_BELOW}}


def next_step(finding: dict, pack: Pack) -> str | None:
    """A plain suggestion that follows from a finding. It is a prompt for the teacher, not a decision."""
    kind, path = finding.get("kind"), finding.get("path") or []
    concepts = finding.get("concept_ids") or []
    if kind == "root_cause" and len(path) > 1:
        return (f"Before moving on with {pack.label(path[0])}, revisit {pack.label(path[-1])}. "
                f"A short check on {pack.label(path[-1])} would confirm whether the gap is still there.")
    if kind == "root_cause" and concepts:
        return f"Spend time on {pack.label(concepts[0])} itself: the topics it builds on look secure."
    if kind == "strength":
        return "Offer harder or wider work in this area, and consider letting this learner explain it to others."
    if kind == "struggle":
        return "Check the topics this area builds on, and trace back on the learning map to see where it starts."
    if kind == "what_worked":
        return "Try the same approach when the next new topic is introduced, and see whether the gain repeats."
    return None


# ------------------------------------------------------------------ teacher

def _ensure_table(conn) -> None:
    conn.executescript(_PROFILE_TABLE)


def _questions(pack: Pack) -> dict[str, Any]:
    return {"approaches": [{"id": aid, "label": pack.label(aid)} for aid in pack.approaches],
            "frequencies": list(FREQUENCIES)}


def teacher_profile(teacher_id: str, db_path=None) -> dict[str, Any]:
    with db.connect(db_path) as conn:
        _ensure_table(conn)
        teacher = db.one(conn, "SELECT id, name, subjects FROM teachers WHERE id = ?", (teacher_id,))
        if teacher is None:
            raise ValueError(f"Unknown teacher '{teacher_id}'.")
        saved = db.one(conn, "SELECT answers, updated_at FROM teacher_profiles WHERE teacher_id = ?", (teacher_id,))
        used = db.rows(conn, "SELECT approach_id, COUNT(*) AS n FROM teaching_units WHERE teacher_id = ? "
                             "GROUP BY approach_id", (teacher_id,))
        pack_row = db.one(conn, "SELECT pack_id FROM learners LIMIT 1")
    pack = load_pack(pack_row["pack_id"] if pack_row else None)
    counts = {u["approach_id"]: u["n"] for u in used}
    return {"teacher": {"id": teacher["id"], "name": teacher["name"], "subjects": db.jload(teacher["subjects"], [])},
            "questions": _questions(pack),
            "answers": db.jload(saved["answers"], {}) if saved else {},
            "updated_at": saved["updated_at"] if saved else None,
            "recorded_units": [{"id": aid, "label": pack.label(aid), "n": counts.get(aid, 0)} for aid in pack.approaches]}


def save_teacher_profile(teacher_id: str, answers: dict[str, Any], db_path=None) -> dict[str, Any]:
    """Store a teacher's own description of how they teach. Logged like every other write."""
    started = time.perf_counter()
    approaches = {k: v for k, v in (answers.get("approaches") or {}).items() if v in FREQUENCIES}
    clean = {"approaches": approaches,
             "languages": str(answers.get("languages") or "")[:200],
             "class_size": str(answers.get("class_size") or "")[:40],
             "what_works": str(answers.get("what_works") or "")[:1000],
             "wants_help_with": str(answers.get("wants_help_with") or "")[:1000]}
    with db.connect(db_path) as conn:
        _ensure_table(conn)
        if db.one(conn, "SELECT id FROM teachers WHERE id = ?", (teacher_id,)) is None:
            raise ValueError(f"Unknown teacher '{teacher_id}'.")
        conn.execute("INSERT INTO teacher_profiles (teacher_id, answers, updated_at) VALUES (?,?,?) "
                     "ON CONFLICT(teacher_id) DO UPDATE SET answers = excluded.answers, updated_at = excluded.updated_at",
                     (teacher_id, db.jdump(clean), db.now_iso()))
        audit.write_row(conn, "save_teaching_style", {"teacher_id": teacher_id, "answers": clean}, {"saved": True},
                        True, int((time.perf_counter() - started) * 1000), actor=f"teacher:{teacher_id}")
    return {"saved": True, "answers": clean}


def fit(learner_id: str, teacher_id: str, db_path=None) -> dict[str, Any]:
    """What was followed by gains for this learner, next to how this teacher says they teach."""
    profile = teacher_profile(teacher_id, db_path=db_path)
    said = (profile["answers"].get("approaches") or {})
    recorded = {r["id"]: r["n"] for r in profile["recorded_units"]}
    worked = graph.what_worked(learner_id, db_path=db_path)
    rows, notes = [], []
    for a in worked.get("approaches", []):
        total = a["improved"] + a["not_improved"]
        helped = a["improved"] >= 2 and a["improved"] > a["not_improved"]
        frequency = said.get(a["approach_id"])
        rows.append({"id": a["approach_id"], "label": a["label"], "improved": a["improved"], "times": total,
                     "followed_by_gains": helped, "you_said": frequency, "your_recorded_units": recorded.get(a["approach_id"], 0)})
        if helped and frequency == "rarely":
            notes.append(f"{a['label']} was followed by gains {a['improved']} of {total} times for this learner. "
                         "You said you teach this way rarely, so it may be worth trying here.")
        elif helped and frequency == "often":
            notes.append(f"{a['label']} was followed by gains {a['improved']} of {total} times for this learner, "
                         "and it is a way you often teach.")
    return {"teacher": profile["teacher"], "has_profile": bool(said), "rows": rows, "notes": notes,
            "caution": "Counts are small and topic difficulty also plays a part. This describes what followed, "
                       "not what caused it, and it does not rate anyone."}
