"""Classes: which learners a teacher works with.

A class is a group of learners in one school year (for example 5A in 2026). The admin puts learners in a
class and says which teacher takes it for which subject. Once sign-in is on, a teacher sees the learners
of their own classes and nobody else. The admin sees everyone. In demonstration mode (no account yet,
synthetic data) everyone is shown.

A teacher who can see a learner sees that learner's whole record, every subject and every year: the point
of the product is the long view, and a difficulty in one subject often starts in another.
"""

from __future__ import annotations

import time
from typing import Any

from . import audit, db
from .accounts import NotAllowed


def visible(who: dict | None, db_path=None) -> set[str] | None:
    """The learner ids this person may see. None means everyone."""
    if who is None or who.get("role") == "admin":
        return None
    with db.connect(db_path) as conn:
        found = db.rows(conn, "SELECT DISTINCT cl.learner_id FROM class_learners cl "
                              "JOIN class_teachers ct ON ct.class_id = cl.class_id WHERE ct.teacher_id = ?", (who["id"],))
    return {row["learner_id"] for row in found}


def check(who: dict | None, learner_id: str, db_path=None) -> None:
    """Refuse a learner outside this teacher's classes."""
    allowed = visible(who, db_path)
    if allowed is not None and learner_id not in allowed:
        raise NotAllowed("This learner is not in one of your classes. Ask the school admin.")


def list_classes(who: dict | None = None, db_path=None) -> list[dict[str, Any]]:
    """Classes with their teachers and learners, newest year first. A teacher gets their own classes."""
    with db.connect(db_path) as conn:
        found = db.rows(conn, "SELECT id, name, grade, year FROM classes ORDER BY year DESC, grade, name COLLATE NOCASE")
        teachers = db.rows(conn, "SELECT ct.class_id, ct.teacher_id, ct.subject, t.name FROM class_teachers ct "
                                 "JOIN teachers t ON t.id = ct.teacher_id ORDER BY ct.subject, t.name COLLATE NOCASE")
        learners = db.rows(conn, "SELECT cl.class_id, l.id AS learner_id, l.alias, l.display_name FROM class_learners cl "
                                 "JOIN learners l ON l.id = cl.learner_id ORDER BY l.alias COLLATE NOCASE")
    mine = None if who is None or who.get("role") == "admin" else {t["class_id"] for t in teachers if t["teacher_id"] == who["id"]}
    out = []
    for row in found:
        if mine is not None and row["id"] not in mine:
            continue
        out.append({**row,
                    "teachers": [{"teacher_id": t["teacher_id"], "name": t["name"], "subject": t["subject"]}
                                 for t in teachers if t["class_id"] == row["id"]],
                    "learners": [{"learner_id": x["learner_id"], "alias": x["alias"],
                                  "name": x["display_name"] or x["alias"]} for x in learners if x["class_id"] == row["id"]]})
    return out


def class_of(db_path=None) -> dict[str, dict[str, Any]]:
    """learner id -> their class in the latest year they have one."""
    with db.connect(db_path) as conn:
        found = db.rows(conn, "SELECT cl.learner_id, c.id, c.name, c.grade, c.year FROM class_learners cl "
                              "JOIN classes c ON c.id = cl.class_id ORDER BY c.year")
    return {row["learner_id"]: {"id": row["id"], "name": row["name"], "grade": row["grade"], "year": row["year"]}
            for row in found}


def _class(conn, class_id: str) -> dict:
    row = db.one(conn, "SELECT * FROM classes WHERE id = ?", (class_id,))
    if row is None:
        raise ValueError(f"Unknown class '{class_id}'.")
    return row


def create_class(name: str, grade: int, year: int, actor: str, db_path=None) -> dict[str, Any]:
    started = time.perf_counter()
    name = " ".join(str(name or "").split())
    if not 1 <= len(name) <= 30:
        raise ValueError("Give the class a short name, for example 5A.")
    if not 1 <= int(grade) <= 12 or not 2000 <= int(year) <= 2100:
        raise ValueError("Give the grade and the year the school year starts in.")
    with db.connect(db_path) as conn:
        if db.one(conn, "SELECT id FROM classes WHERE name = ? AND year = ?", (name, int(year))):
            raise ValueError(f"There is already a class called {name} in {year}.")
        out = {"id": db.new_id("cls"), "name": name, "grade": int(grade), "year": int(year)}
        conn.execute("INSERT INTO classes (id, name, grade, year, created_at) VALUES (?,?,?,?,?)",
                     (out["id"], name, int(grade), int(year), db.now_iso()))
        audit.write_row(conn, "create_class", {"name": name, "grade": int(grade), "year": int(year)}, out, True,
                        int((time.perf_counter() - started) * 1000), actor=actor)
    return out


def assign_teacher(class_id: str, teacher_id: str, subject: str, actor: str, db_path=None) -> dict[str, Any]:
    subject = str(subject or "").strip().lower()[:40] or "all"
    with db.connect(db_path) as conn:
        _class(conn, class_id)
        if db.one(conn, "SELECT id FROM teachers WHERE id = ?", (teacher_id,)) is None:
            raise ValueError(f"Unknown teacher '{teacher_id}'.")
        conn.execute("INSERT OR IGNORE INTO class_teachers (class_id, teacher_id, subject) VALUES (?,?,?)",
                     (class_id, teacher_id, subject))
        out = {"class_id": class_id, "teacher_id": teacher_id, "subject": subject}
        audit.write_row(conn, "assign_teacher", out, {"assigned": True}, True, 0, actor=actor)
    return out


def remove_teacher(class_id: str, teacher_id: str, actor: str, db_path=None) -> dict[str, Any]:
    with db.connect(db_path) as conn:
        _class(conn, class_id)
        gone = conn.execute("DELETE FROM class_teachers WHERE class_id = ? AND teacher_id = ?",
                            (class_id, teacher_id)).rowcount
        audit.write_row(conn, "remove_teacher", {"class_id": class_id, "teacher_id": teacher_id}, {"removed": gone},
                        True, 0, actor=actor)
    return {"removed": gone}


def put_learners(class_id: str, learner_ids: list[str], actor: str, db_path=None) -> dict[str, Any]:
    """Put learners in a class. A learner is in one class per school year, so this moves them out of any
    other class of the same year."""
    with db.connect(db_path) as conn:
        target = _class(conn, class_id)
        known = {row["id"] for row in db.rows(conn, "SELECT id FROM learners")}
        unknown = [lid for lid in learner_ids if lid not in known]
        if unknown:
            raise ValueError(f"Unknown learner '{unknown[0]}'.")
        same_year = [row["id"] for row in db.rows(conn, "SELECT id FROM classes WHERE year = ? AND id != ?",
                                                  (target["year"], class_id))]
        for lid in dict.fromkeys(learner_ids):
            for other in same_year:
                conn.execute("DELETE FROM class_learners WHERE class_id = ? AND learner_id = ?", (other, lid))
            conn.execute("INSERT OR IGNORE INTO class_learners (class_id, learner_id) VALUES (?,?)", (class_id, lid))
        out = {"class_id": class_id, "learners": len(set(learner_ids))}
        audit.write_row(conn, "put_learners_in_class", {"class_id": class_id, "learner_ids": list(learner_ids)[:200]},
                        out, True, 0, actor=actor)
    return out


def take_learner_out(class_id: str, learner_id: str, actor: str, db_path=None) -> dict[str, Any]:
    with db.connect(db_path) as conn:
        _class(conn, class_id)
        gone = conn.execute("DELETE FROM class_learners WHERE class_id = ? AND learner_id = ?",
                            (class_id, learner_id)).rowcount
        audit.write_row(conn, "take_learner_out_of_class", {"class_id": class_id, "learner_id": learner_id},
                        {"removed": gone}, True, 0, actor=actor)
    return {"removed": gone}
