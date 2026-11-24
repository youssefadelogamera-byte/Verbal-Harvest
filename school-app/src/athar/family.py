"""Family mode: one installation used by a parent for their own children.

The same engine and the same curriculum map as the school mode. What differs:

- The app is told once who is using it: a school, or a family. That is one row in `settings`.
- A family has one grown-up (stored like a teacher, so every record still carries who wrote it) and a few
  children, kept in one group. Only those children are shown.
- A parent has no marks sheet. They type a result in (a topic and a mark), or add a note in their own words.
- The summary a parent reads is computed here in plain code from the engine's results: what is going well,
  where to help first, what comes next, what to ask the teacher. Every part lists the records it rests on.
  No model writes it, and nothing here compares the child with anyone.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path
from typing import Any

from . import audit, db, graph, imports
from .config import get_settings
from .curriculum import load_pack

MODES = ("school", "family")
FAMILY_CLASS = "cls_family"
MAX_CHILDREN = 8
ENOUGH_ITEMS = 6            # under this many marks the summary says "too little to tell" rather than guess
CLEARLY_LOW = 0.45          # a topic average under this is offered as a place to help; nearer the middle is left alone
_ARABIC = re.compile(r"[؀-ۿ]")


def school_year(today: dt.date | None = None) -> int:
    """The calendar year the current school year started in (the year begins in September)."""
    today = today or dt.date.today()
    return today.year if today.month >= 9 else today.year - 1


def _get(conn, key: str) -> str | None:
    row = db.one(conn, "SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else None


def _set(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))


def mode(db_path=None) -> str | None:
    """'school', 'family', or None when nobody has chosen yet."""
    with db.connect(db_path) as conn:
        return _get(conn, "mode")


def guardian(db_path=None) -> dict[str, Any] | None:
    """The grown-up of the family, when the app is in family mode."""
    with db.connect(db_path) as conn:
        if _get(conn, "mode") != "family":
            return None
        return db.one(conn, "SELECT id, name FROM teachers WHERE id = ?", (_get(conn, "guardian_id") or "",))


def choose(new_mode: str, name: str = "", db_path=None) -> dict[str, Any]:
    """Say who uses this installation. Choosing 'family' makes the parent's own record and the family group.
    Nothing is deleted by switching: the school's records stay, they are just not shown in family mode."""
    if new_mode not in MODES:
        raise ValueError("Choose school or family.")
    with db.connect(db_path) as conn:
        if new_mode == "family":
            who = _get(conn, "guardian_id")
            name = " ".join(str(name or "").split())[:60]
            if not who:
                if len(name) < 2:
                    raise ValueError("Write your name, so each note shows who wrote it.")
                who = db.new_id("tch")
                conn.execute("INSERT INTO teachers (id, name, subjects) VALUES (?, ?, '[]')", (who, name))
                _set(conn, "guardian_id", who)
            elif len(name) >= 2:
                conn.execute("UPDATE teachers SET name = ? WHERE id = ?", (name, who))
            if db.one(conn, "SELECT id FROM classes WHERE id = ?", (FAMILY_CLASS,)) is None:
                conn.execute("INSERT INTO classes (id, name, grade, year, created_at) VALUES (?, ?, 0, 0, ?)",
                             (FAMILY_CLASS, "family", db.now_iso()))
            conn.execute("INSERT OR IGNORE INTO class_teachers (class_id, teacher_id, subject) VALUES (?, ?, 'all')",
                         (FAMILY_CLASS, who))
        _set(conn, "mode", new_mode)
        audit.write_row(conn, "choose_mode", {"mode": new_mode}, {"mode": new_mode}, True, 0, actor="setup")
    return {"mode": new_mode, "guardian": guardian(db_path)}


def children_ids(db_path=None) -> set[str]:
    with db.connect(db_path) as conn:
        return {r["learner_id"] for r in db.rows(conn, "SELECT learner_id FROM class_learners WHERE class_id = ?",
                                                 (FAMILY_CLASS,))}


def own_children_ids(db_path=None) -> set[str]:
    """The children a parent added themselves (not the made-up ones borrowed from the sample school).
    These belong to the family and are never shown on the school side."""
    with db.connect(db_path) as conn:
        mine = {r["learner_id"] for r in db.rows(conn, "SELECT learner_id FROM class_learners WHERE class_id = ?",
                                                 (FAMILY_CLASS,))}
        return mine - set(_examples(conn))


def _family(conn) -> dict:
    who = db.one(conn, "SELECT id, name FROM teachers WHERE id = ?", (_get(conn, "guardian_id") or "",))
    if _get(conn, "mode") != "family" or who is None:
        raise ValueError("This is for family mode. Choose it first.")
    return who


def _child(conn, learner_id: str) -> dict:
    row = db.one(conn, "SELECT l.* FROM learners l JOIN class_learners c ON c.learner_id = l.id "
                       "WHERE c.class_id = ? AND l.id = ?", (FAMILY_CLASS, learner_id))
    if row is None:
        raise ValueError("That child is not in this family's records.")
    return row


def add_child(name: str, grade: int, db_path=None) -> dict[str, Any]:
    """Open a record for a child. The name is shown on this computer only; documents and any model see the code."""
    with db.connect(db_path) as conn:
        who = _family(conn)
        if len(db.rows(conn, "SELECT 1 AS x FROM class_learners WHERE class_id = ?", (FAMILY_CLASS,))) >= MAX_CHILDREN:
            raise ValueError(f"A family record holds up to {MAX_CHILDREN} children.")
    return imports.add_learner(name, grade, school_year(), "ar", actor=f"guardian:{who['id']}", db_path=db_path,
                               class_id=FAMILY_CLASS)


def add_example_child(db_path=None) -> dict[str, Any]:
    """Put one made-up learner from the sample school into the family, so a parent can look around before
    typing anything. It is labelled as made up on the page."""
    with db.connect(db_path) as conn:
        _family(conn)
        taken = {r["learner_id"] for r in db.rows(conn, "SELECT learner_id FROM class_learners WHERE class_id = ?",
                                                  (FAMILY_CLASS,))}
        found = db.rows(conn, "SELECT l.id, COUNT(e.id) AS n FROM learners l JOIN evidence e ON e.learner_id = l.id "
                              "GROUP BY l.id ORDER BY n DESC, l.id")
        # Prefer a made-up learner with a clear story to show: a gap that began in an earlier grade.
        truth = (Path(db_path).parent if db_path else get_settings().db_path.parent) / "ground_truth.json"
        planted = json.loads(truth.read_text(encoding="utf-8")).get("planted", []) if truth.exists() else []
        known = {r["id"] for r in found}
        first = [p["learner_id"] for p in planted if p.get("case") == "root_gap" and p["learner_id"] in known]
        other = [p["learner_id"] for p in planted if p.get("case") in ("strand_strength", "what_worked")
                 and p["learner_id"] in known]
        pick = next((i for i in [*first[:1], *other[:1], *first, *(r["id"] for r in found)] if i not in taken), None)
        if pick is None:
            raise ValueError("There is no made-up learner to show. You can add your own child.")
        if len(taken) >= MAX_CHILDREN:
            raise ValueError(f"A family record holds up to {MAX_CHILDREN} children.")
        conn.execute("INSERT OR IGNORE INTO class_learners (class_id, learner_id) VALUES (?, ?)", (FAMILY_CLASS, pick))
        _set(conn, "example_child", ",".join([*_examples(conn), pick]))
    return {"learner_id": pick, "example": True}


def _examples(conn) -> list[str]:
    return [x for x in (_get(conn, "example_child") or "").split(",") if x]


def remove_example_child(learner_id: str | None = None, db_path=None) -> dict[str, Any]:
    """Take a made-up learner (or all of them) out of the family again. Their made-up records stay in the
    sample school."""
    with db.connect(db_path) as conn:
        shown = _examples(conn)
        gone = [x for x in shown if learner_id in (None, x)]
        for pick in gone:
            conn.execute("DELETE FROM class_learners WHERE class_id = ? AND learner_id = ?", (FAMILY_CLASS, pick))
        _set(conn, "example_child", ",".join(x for x in shown if x not in gone))
    return {"removed": len(gone)}


def rename_child(learner_id: str, name: str, db_path=None) -> dict[str, Any]:
    """Change the name shown for a child. The record code and the records stay as they are."""
    name = " ".join(str(name or "").split())
    if not 2 <= len(name) <= 60:
        raise ValueError("Give the learner's name as the class list shows it (2 to 60 characters).")
    with db.connect(db_path) as conn:
        who = _family(conn)
        _child(conn, learner_id)
        if learner_id in _examples(conn):
            raise ValueError("A made-up child cannot be renamed. Remove it and add your own child.")
        conn.execute("UPDATE learners SET display_name = ? WHERE id = ?", (name, learner_id))
        audit.write_row(conn, "rename_child", {"learner_id": learner_id}, {"renamed": True}, True, 0,
                        actor=f"guardian:{who['id']}")
    return {"learner_id": learner_id, "name": name}


def children(db_path=None) -> list[dict[str, Any]]:
    with db.connect(db_path) as conn:
        example = _examples(conn)
        found = db.rows(conn, """
            SELECT l.id AS learner_id, l.alias, l.display_name, l.start_grade, l.start_year, l.pack_id,
                   MAX(e.grade) AS latest_grade, COUNT(e.id) AS records
            FROM learners l JOIN class_learners c ON c.learner_id = l.id AND c.class_id = ?
            LEFT JOIN evidence e ON e.learner_id = l.id AND e.status != 'retracted'
            GROUP BY l.id ORDER BY l.created_at, l.rowid""", (FAMILY_CLASS,))
    found.sort(key=lambda r: r["learner_id"] in example)        # the family's own children first, made-up ones after
    return [{"learner_id": r["learner_id"], "alias": r["alias"], "name": r["display_name"] or r["alias"],
             "grade_now": _grade_now(r), "records": r["records"],
             "example": r["learner_id"] in example} for r in found]


def _grade_now(row: dict) -> int:
    """The grade a child is in this school year. A child moves up a grade each year by itself, so a parent
    who added a child last year does not have to change anything. A made-up child keeps the grade of its
    latest record."""
    top = load_pack(row["pack_id"]).grades[1]
    by_year = row["start_grade"] + max(0, school_year() - row["start_year"])
    return min(top, max(row["latest_grade"] or 0, by_year))


def _number(text: Any) -> float | None:
    return imports._number(text)


def add_results(learner_id: str, items: list[dict], *, title: str = "", grade: int | None = None,
                year: int | None = None, term: int = 1, db_path=None) -> dict[str, Any]:
    """Save marks a parent typed in from one paper: each line is a topic, a mark and what it was out of.
    A line with no mark is skipped. Nothing is guessed: a topic that is not in the map is refused."""
    started = time.perf_counter()
    title = " ".join(str(title or "").split())[:80] or "Result added at home"
    with db.connect(db_path) as conn:
        who = _family(conn)
        child = _child(conn, learner_id)
        pack = load_pack(child["pack_id"])
        if not 1 <= int(term) <= pack.terms:
            raise ValueError(f"The term is 1 to {pack.terms}.")
        latest = db.one(conn, "SELECT MAX(grade) AS g FROM evidence WHERE learner_id = ?", (learner_id,))["g"]
        grade = int(grade or _grade_now({**child, "latest_grade": latest}))
        if not pack.grades[0] <= grade <= pack.grades[1]:
            raise ValueError(f"This curriculum covers grades {pack.grades[0]} to {pack.grades[1]}.")
        year = int(year or school_year())
        problems, rows = [], []
        for n, item in enumerate(items or [], start=1):
            topic = pack.concepts.get(str(item.get("topic_id") or ""))
            mark, out_of = _number(item.get("mark")), _number(item.get("out_of"))
            if item.get("mark") in (None, "") and item.get("out_of") in (None, ""):
                continue
            if topic is None:
                problems.append(f"Line {n}: choose a topic from the list.")
            elif mark is None or out_of is None or out_of <= 0:
                problems.append(f"Line {n}: write the mark and what it was out of, as numbers.")
            elif not 0 <= mark <= out_of:
                problems.append(f"Line {n}: the mark is outside 0 to {imports._cell_text(out_of)}.")
            else:
                rows.append((n, topic, mark, out_of))
        if problems:
            raise ValueError(problems[0])          # one thing to fix at a time
        if not rows:
            raise ValueError("Add at least one line with a topic and a mark.")
        stamp, now = db.new_id("home").replace("home_", ""), db.now_iso()
        language = "ar" if _ARABIC.search(title) else "en"
        for n, topic, mark, out_of in rows:
            conn.execute(
                "INSERT INTO evidence (id, learner_id, kind, year, term, period_ord, grade, concept_id, skill_id, score, "
                "raw_text, language, source_ref, teacher_id, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id("evd"), learner_id, "quiz_item", year, int(term), db.period_ord(year, int(term)), grade, topic.id,
                 topic.skills[0] if topic.skills else None, round(mark / out_of, 3),
                 f"{title} ({imports._cell_text(mark)} / {imports._cell_text(out_of)})", language,
                 f"home:{year}-T{int(term)}:{stamp}#{n}", who["id"], now))
        if year < child["start_year"]:          # an older paper: the record now starts earlier
            conn.execute("UPDATE learners SET start_year = ?, start_grade = ? WHERE id = ?", (year, grade, learner_id))
        out = {"saved": len(rows), "learner_id": learner_id, "year": year, "term": int(term), "grade": grade}
        audit.write_row(conn, "add_home_results", {"learner_id": learner_id, "topics": [t.id for _, t, _, _ in rows]},
                        out, True, int((time.perf_counter() - started) * 1000), actor=f"guardian:{who['id']}")
    return out


def add_note(learner_id: str, text: str, topic_id: str | None = None, db_path=None) -> dict[str, Any]:
    """Keep a note in the parent's own words. It is stored as written and is never turned into a score."""
    text = " ".join(str(text or "").split())
    if not 3 <= len(text) <= 1000:
        raise ValueError("Write a short note (up to 1000 characters).")
    with db.connect(db_path) as conn:
        who = _family(conn)
        child = _child(conn, learner_id)
        pack = load_pack(child["pack_id"])
        if topic_id and topic_id not in pack.concepts:
            raise ValueError("Choose a topic from the list, or leave it empty.")
        latest = db.one(conn, "SELECT MAX(grade) AS g FROM evidence WHERE learner_id = ?", (learner_id,))["g"]
        year, grade = school_year(), _grade_now({**child, "latest_grade": latest})
        term = 1 if dt.date.today().month in (9, 10, 11, 12, 1) else min(2, pack.terms)
        evidence_id = db.new_id("evd")
        conn.execute(
            "INSERT INTO evidence (id, learner_id, kind, year, term, period_ord, grade, concept_id, raw_text, language, "
            "source_ref, teacher_id, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (evidence_id, learner_id, "observation", year, term, db.period_ord(year, term), grade, topic_id or None, text,
             "ar" if _ARABIC.search(text) else "en", f"home-note:{dt.date.today().isoformat()}", who["id"], db.now_iso()))
        # The log holds that a note was added, not its words.
        audit.write_row(conn, "add_home_note", {"learner_id": learner_id, "topic_id": topic_id or None},
                        {"evidence_id": evidence_id, "characters": len(text)}, True, 0, actor=f"guardian:{who['id']}")
    return {"evidence_id": evidence_id}


def notes(learner_id: str, db_path=None) -> list[dict[str, Any]]:
    with db.connect(db_path) as conn:
        _child(conn, learner_id)
        return db.rows(conn, "SELECT id, raw_text AS text, language, concept_id, recorded_at FROM evidence "
                             "WHERE learner_id = ? AND kind = 'observation' AND source_ref LIKE 'home-note:%' "
                             "AND status != 'retracted' ORDER BY recorded_at DESC, id DESC LIMIT 50", (learner_id,))


def summary(learner_id: str, db_path=None) -> dict[str, Any]:
    """What a parent reads first. Computed from the engine's results. Each part carries the ids of the
    records behind it, and when there is too little to say, it says so."""
    with db.connect(db_path) as conn:
        child = _child(conn, learner_id)
        scored = db.one(conn, "SELECT COUNT(*) AS n, COUNT(DISTINCT period_ord) AS terms FROM evidence "
                              "WHERE learner_id = ? AND score IS NOT NULL AND status != 'retracted'", (learner_id,))
        latest = db.one(conn, "SELECT MAX(grade) AS g, MAX(period_ord) AS p FROM evidence WHERE learner_id = ?", (learner_id,))
        recorded = {r["concept_id"] for r in db.rows(
            conn, "SELECT DISTINCT concept_id FROM evidence WHERE learner_id = ? AND concept_id IS NOT NULL", (learner_id,))}
    pack = load_pack(child["pack_id"])
    out: dict[str, Any] = {"learner_id": learner_id, "records": scored["n"], "terms": scored["terms"],
                           "enough": scored["n"] >= ENOUGH_ITEMS, "going_well": [], "help_first": [], "next_up": [],
                           "worked": None}
    if not out["enough"]:             # too little to read anything into: say so, and say nothing else
        return out
    nodes = {n["id"]: n for n in graph.learner_graph(learner_id, db_path=db_path)["nodes"] if n.get("type") == "concept"}

    # ---- going well: whole areas that stayed strong, then single topics
    patterns = graph.find_patterns(learner_id, db_path=db_path)["patterns"]
    for p in sorted((p for p in patterns if p["kind"] == "strength" and p["scope"] == "strand"), key=lambda p: -p["mean"])[:3]:
        out["going_well"].append({"kind": "area", "label": p["label"], "average": p["mean"], "items": p["n_items"],
                                  "terms": len(p["periods"]), "evidence_ids": p["evidence_ids"][:12]})
    strong = sorted((n for n in nodes.values() if n.get("state") == "strong" and (n.get("n") or 0) >= 2),
                    key=lambda n: (-(n["grade"] or 0), -n["mastery"]))
    for n in strong[:max(0, 4 - len(out["going_well"]))]:
        out["going_well"].append({"kind": "topic", "label": n["label"], "average": n["mastery"], "items": n["n"],
                                  "grade": n["grade"]})

    # ---- where to help first: the lowest recent topics, each traced back to where it may have started
    low = sorted((n for n in nodes.values() if (n.get("n") or 0) >= 2 and n.get("mastery") is not None
                  and n["mastery"] < CLEARLY_LOW), key=lambda n: (-(n["grade"] or 0), n["mastery"], n["id"]))
    seen_starts: set[str] = set()
    for n in low:
        if len(out["help_first"]) >= 3:
            break
        traced = graph.trace_root(learner_id, n["id"], db_path=db_path)
        root = traced.get("root")
        start = root["concept_id"] if root else n["id"]
        if start in seen_starts:
            continue
        seen_starts.add(start)
        same = not root or root["concept_id"] == n["id"]
        out["help_first"].append({
            "topic_id": n["id"], "topic": n["label"], "grade": n["grade"], "average": n["mastery"], "items": n["n"],
            "starts_here": same, "certain": bool(traced.get("root_is_certain", True)) if root else False,
            "start": None if same else {"topic_id": root["concept_id"], "topic": root["label"], "grade": root.get("grade"),
                                        "average": root.get("mean"), "period": root.get("period")},
            "days_absent": sum(c.get("absent_days", 0) for c in traced.get("context", [])),
            "evidence_ids": (traced.get("evidence_ids") or [])[:12]})

    # ---- coming next: topics of the child's grade with no record yet that need a topic which is low
    weak = {n["id"] for n in nodes.values() if n.get("mastery") is not None and n["mastery"] < CLEARLY_LOW}
    grade_now = _grade_now({**child, "latest_grade": latest["g"]})
    for concept in sorted(pack.concepts.values(), key=lambda c: (c.term or 0, c.id)):
        if len(out["next_up"]) >= 3:
            break
        needs = [r for r in concept.requires if r in weak]
        if concept.grade == grade_now and concept.id not in recorded and needs:
            out["next_up"].append({"topic_id": concept.id, "topic": pack.label(concept.id), "term": concept.term,
                                   "needs": [pack.label(r) for r in needs[:2]]})

    # ---- what seemed to help, only when the records show it clearly
    approaches = graph.what_worked(learner_id, db_path=db_path).get("approaches", [])
    best = max(approaches, key=lambda a: a["improved"] - a["not_improved"], default=None)
    if best and best["improved"] >= 2 and best["improved"] > best["not_improved"]:
        out["worked"] = {"label": best["label"], "improved": best["improved"], "not_improved": best["not_improved"]}
    return out
