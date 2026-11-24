"""Read-only numbers for the dashboards. Nothing here ranks or compares learners: the class view
aggregates by curriculum strand and term, and the roster shows how complete each record is and
what is waiting for a teacher, never a score."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .. import db
from ..curriculum import load_pack
from ..graph import STRENGTH_ABOVE, STRUGGLE_BELOW


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def overview(db_path=None, only: set[str] | None = None) -> dict[str, Any]:
    """`only`: the learner ids the person asking may see. None means everyone."""
    with db.connect(db_path) as conn:
        learners = db.rows(conn, "SELECT id, alias, display_name, pack_id, home_language, start_grade FROM learners "
                                 "ORDER BY alias COLLATE NOCASE, id")
        evidence = db.rows(conn, "SELECT learner_id, kind, period_ord, grade, concept_id, score, language "
                                 "FROM evidence WHERE status != 'retracted'")
        findings = db.rows(conn, "SELECT learner_id, status FROM findings")
        summaries = db.rows(conn, "SELECT learner_id, status FROM summaries")
        audit = db.one(conn, "SELECT COUNT(*) AS n, COALESCE(SUM(ok = 0), 0) AS refused, "
                             "COUNT(DISTINCT run_id) AS runs FROM audit_log")
        by_tool = db.rows(conn, "SELECT tool, COUNT(*) AS n FROM audit_log GROUP BY tool ORDER BY n DESC, tool")
        recent = db.rows(conn, "SELECT ts, actor, tool, ok FROM audit_log ORDER BY id DESC LIMIT 8")
        decisions = db.one(conn, "SELECT COUNT(*) AS n FROM approvals")
        teachers = db.one(conn, "SELECT COUNT(*) AS n FROM teachers")
    if only is not None:
        learners = [row for row in learners if row["id"] in only]
        evidence = [row for row in evidence if row["learner_id"] in only]
        findings = [row for row in findings if row["learner_id"] in only]
        summaries = [row for row in summaries if row["learner_id"] in only]

    pack = load_pack(learners[0]["pack_id"]) if learners else None
    by_period: dict[int, int] = defaultdict(int)
    by_kind: dict[str, int] = defaultdict(int)
    by_language: dict[str, int] = defaultdict(int)
    cell: dict[tuple[str, int], list[float]] = defaultdict(list)
    per_learner: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "periods": set(), "last": None})
    concepts_seen: set[str] = set()
    for e in evidence:
        by_period[e["period_ord"]] += 1
        by_kind[e["kind"]] += 1
        by_language[e["language"]] += 1
        mine = per_learner[e["learner_id"]]
        mine["n"] += 1
        mine["periods"].add(e["period_ord"])
        mine["last"] = max(mine["last"] or 0, e["period_ord"])
        concept = pack.concepts.get(e["concept_id"]) if pack and e["concept_id"] else None
        if concept:
            concepts_seen.add(concept.id)
            if e["score"] is not None:
                cell[(concept.strand, concept.grade)].append(e["score"])

    pending: dict[str, int] = defaultdict(int)
    approved: dict[str, int] = defaultdict(int)
    for f in findings:
        if f["status"] == "proposed":
            pending[f["learner_id"]] += 1
        elif f["status"] in ("approved", "edited"):
            approved[f["learner_id"]] += 1
    for s in summaries:
        if s["status"] == "draft":
            pending[s["learner_id"]] += 1
        elif s["status"] == "approved":
            approved[s["learner_id"]] += 1

    grades = sorted({g for (_, g) in cell})
    strands = [{"id": sid, "label": pack.label(sid), "subject": pack.label(pack.strand_subject.get(sid, "")),
                "cells": [{"grade": g, "mean": _mean(cell.get((sid, g), [])), "n": len(cell.get((sid, g), []))}
                          for g in grades]}
               for sid in (pack.strands if pack else {}) if any((sid, g) in cell for g in grades)]
    roster = []
    for row in learners:
        mine = per_learner.get(row["id"], {"n": 0, "periods": set(), "last": None})
        roster.append({"learner_id": row["id"], "alias": row["alias"], "name": row["display_name"] or row["alias"],
                       "home_language": row["home_language"],
                       "records": mine["n"], "terms": len(mine["periods"]),
                       "last_period": db.period_label(mine["last"]) if mine["last"] else None,
                       "waiting": pending.get(row["id"], 0), "approved": approved.get(row["id"], 0)})
    return {
        "totals": {"learners": len(learners), "teachers": teachers["n"], "records": len(evidence),
                   "concepts_with_records": len(concepts_seen), "concepts_in_curriculum": len(pack.concepts) if pack else 0,
                   "waiting": sum(pending.values()), "approved": sum(approved.values()),
                   "tool_calls": audit["n"], "refused_calls": audit["refused"], "agent_runs": audit["runs"],
                   "decisions": decisions["n"]},
        "records_by_period": [{"period": db.period_label(p), "n": n} for p, n in sorted(by_period.items())],
        "records_by_kind": [{"kind": k, "n": n} for k, n in sorted(by_kind.items(), key=lambda kv: -kv[1])],
        "records_by_language": [{"language": k, "n": n} for k, n in sorted(by_language.items(), key=lambda kv: -kv[1])],
        "coverage": {"grades": grades, "strands": strands,
                     "thresholds": {"strong_above": STRENGTH_ABOVE, "gap_below": STRUGGLE_BELOW}},
        "roster": roster,
        "calls_by_tool": by_tool,
        "recent_calls": recent,
        "curriculum": {"id": pack.id, "name": pack.title(),
                       "subjects": [pack.label(s) for s in pack.subjects]} if pack else None,
    }


def learner_dashboard(learner_id: str, db_path=None) -> dict[str, Any]:
    with db.connect(db_path) as conn:
        learner = db.one(conn, "SELECT * FROM learners WHERE id = ?", (learner_id,))
        if learner is None:
            raise ValueError(f"Unknown learner '{learner_id}'.")
        evidence = db.rows(conn, "SELECT kind, period_ord, grade, concept_id, score, absent_days, language, unit_id "
                                 "FROM evidence WHERE learner_id = ? AND status != 'retracted' ORDER BY period_ord",
                           (learner_id,))
        unit_ids = sorted({e["unit_id"] for e in evidence if e["unit_id"]})
        units = []
        if unit_ids:
            marks = ",".join("?" for _ in unit_ids)
            units = db.rows(conn, f"SELECT u.id, u.year, u.term, u.grade, u.concept_id, u.approach_id, t.name AS teacher "
                                  f"FROM teaching_units u JOIN teachers t ON t.id = u.teacher_id WHERE u.id IN ({marks})",
                            tuple(unit_ids))
        findings = db.rows(conn, "SELECT status, COUNT(*) AS n FROM findings WHERE learner_id = ? GROUP BY status",
                           (learner_id,))
        summaries = db.rows(conn, "SELECT status, COUNT(*) AS n FROM summaries WHERE learner_id = ? GROUP BY status",
                            (learner_id,))
    pack = load_pack(learner["pack_id"])

    periods = sorted({e["period_ord"] for e in evidence})
    scores: dict[tuple[str, int], list[float]] = defaultdict(list)
    absent: dict[int, int] = defaultdict(int)
    by_kind: dict[str, int] = defaultdict(int)
    grade_of: dict[int, int] = {}
    for e in evidence:
        by_kind[e["kind"]] += 1
        grade_of[e["period_ord"]] = e["grade"]
        if e["kind"] == "attendance":
            absent[e["period_ord"]] += e["absent_days"] or 0
        concept = pack.concepts.get(e["concept_id"]) if e["concept_id"] else None
        if concept and e["score"] is not None:
            scores[(concept.strand, e["period_ord"])].append(e["score"])

    strands = []
    for sid in pack.strands:
        points = [{"period": db.period_label(p), "mean": _mean(scores[(sid, p)]), "n": len(scores[(sid, p)])}
                  for p in periods if (sid, p) in scores]
        if points:
            strands.append({"id": sid, "label": pack.label(sid),
                            "subject": pack.label(pack.strand_subject.get(sid, "")), "points": points})

    taught: dict[int, list[dict]] = defaultdict(list)
    for u in units:
        taught[db.period_ord(u["year"], u["term"])].append(
            {"concept": pack.label(u["concept_id"]), "approach": pack.label(u["approach_id"]), "teacher": u["teacher"]})
    timeline = [{"period": db.period_label(p), "grade": grade_of.get(p), "absent_days": absent.get(p, 0),
                 "records": sum(1 for e in evidence if e["period_ord"] == p),
                 "taught": sorted(taught.get(p, []), key=lambda t: t["concept"])} for p in periods]

    count = lambda rows, *names: sum(r["n"] for r in rows if r["status"] in names)
    return {
        "learner": {"learner_id": learner_id, "alias": learner["alias"],
                    "name": learner.get("display_name") or learner["alias"], "home_language": learner["home_language"],
                    "grade_now": max(grade_of.values()) if grade_of else learner["start_grade"],
                    "curriculum": pack.title()},
        "totals": {"records": len(evidence), "terms": len(periods),
                   "first_period": db.period_label(periods[0]) if periods else None,
                   "last_period": db.period_label(periods[-1]) if periods else None,
                   "days_absent": sum(absent.values()),
                   "waiting": count(findings, "proposed") + count(summaries, "draft"),
                   "approved": count(findings, "approved", "edited") + count(summaries, "approved")},
        "periods": [db.period_label(p) for p in periods],
        "strands": strands,
        "absences": [{"period": db.period_label(p), "days": absent.get(p, 0)} for p in periods],
        "records_by_kind": [{"kind": k, "n": n} for k, n in sorted(by_kind.items(), key=lambda kv: -kv[1])],
        "timeline": timeline,
        "thresholds": {"strong_above": STRENGTH_ABOVE, "gap_below": STRUGGLE_BELOW},
    }
