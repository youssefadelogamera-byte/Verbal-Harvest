"""A ready state for presenting, built without a model.

`athar story` runs the same audited tools the agent uses (find_patterns, trace_root, what_worked,
propose_finding) for three synthetic learners, words each finding with the fixed templates, and
records a few decisions by a synthetic teacher. Every step lands in the audit log with the actor
`demo-setup`, so nobody can mistake it for the agent's work or for a real teacher's decision.
It leaves some findings waiting, so the review queue has something to decide live."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import audit, db, review, tools
from .config import get_settings
from .curriculum import load_pack

ACTOR = "demo-setup"
# alias suffix -> finding kinds to approve during setup; everything else stays waiting.
PLAN: dict[str, tuple[str, ...]] = {"A-17": ("strength",), "B-04": (), "C-31": ("strength",), "R-08": ()}
MAX_TRACES = 4
CLEARLY_LOW = 0.4   # a topic average under this is traced even when no wider pattern shows
# For a generated school: one learner of each planted kind, and what to approve for them.
SCHOOL_PLAN: dict[str, tuple[str, ...]] = {"root_gap": (), "strand_strength": ("strength",), "what_worked": (),
                                           "unknown_root": ()}


def _plan(learners: list[dict], db_path) -> dict[str, tuple[str, ...]]:
    """Which learners to prepare. The reference cohort has fixed codes. A generated school is read from the
    list of planted patterns written beside its database."""
    if any(row["alias"].endswith(tuple(PLAN)) for row in learners):
        return PLAN
    truth = (Path(db_path).parent if db_path else get_settings().db_path.parent) / "ground_truth.json"
    if not truth.exists():
        return {}
    planted = json.loads(truth.read_text(encoding="utf-8")).get("planted", [])
    plan: dict[str, tuple[str, ...]] = {}
    for case, approve in SCHOOL_PLAN.items():
        first = next((p for p in planted if p["case"] == case), None)
        if first:
            plan[first["alias"].replace("Learner ", "")] = approve
    return plan


def _analyses(learner_id: str, db_path) -> dict[str, Any]:
    patterns = tools.find_patterns(learner_id=learner_id, db_path=db_path)
    targets: list[str] = []
    for p in patterns.get("patterns", []):
        if p["kind"] == "struggle":
            targets.extend(c for c in (p.get("concept_ids") or []) if c not in targets)
    # A gap in one topic does not always show as a pattern across a whole area, least of all in a school with
    # five subjects. So the latest topics whose records are low are traced as well.
    from . import graph
    low = [n for n in graph.learner_graph(learner_id, db_path=db_path)["nodes"]
           if n.get("type") == "concept" and n.get("grade") is not None and (n.get("mastery") or 1) < CLEARLY_LOW]
    for node in sorted(low, key=lambda n: (-n["grade"], n["mastery"], n["id"]))[:2]:
        if node["id"] not in targets:
            targets.append(node["id"])
    roots = {c: tools.trace_root(learner_id=learner_id, concept_id=c, db_path=db_path) for c in targets[-MAX_TRACES:]}
    return {"patterns": patterns, "roots": roots, "what_worked": tools.what_worked(learner_id=learner_id, db_path=db_path)}


def propose_for(learner: dict, approve_kinds: tuple[str, ...], decider_id: str, note: str, out: dict[str, Any],
                db_path=None) -> None:
    """Run the engine for one learner, word each result with the fixed sentences, propose it, and record a
    decision for the kinds named. Used by the school story and by the demo family."""
    from .agent.workflow import (  # deterministic helpers, no model
        _candidates,
        _template_statement,
        in_language,
    )
    pack = load_pack(learner["pack_id"])
    candidates, questions = _candidates(_analyses(learner["id"], db_path), pack)
    candidates = [in_language(c, pack, get_settings().language) for c in candidates]
    out["open_questions"] += len(questions)
    for candidate in candidates:
        made = tools.propose_finding(
            learner_id=learner["id"], kind=candidate["kind"], statement=_template_statement(candidate),
            evidence_ids=candidate["evidence_ids"], concept_ids=candidate["concept_ids"],
            path=candidate["path"], confidence=candidate["confidence"], db_path=db_path)
        out["proposed"] += 1
        if candidate["kind"] in approve_kinds:
            review.decide_finding(made["finding_id"], "approved", decider_id, note=note, db_path=db_path)
            out["approved"] += 1
        else:
            out["waiting"] += 1


def build(db_path=None) -> dict[str, Any]:
    """Create the presenting state. Safe to run once on a freshly seeded database."""
    with db.connect(db_path) as conn:
        learners = db.rows(conn, "SELECT id, alias, pack_id FROM learners ORDER BY alias")
        teacher = db.one(conn, "SELECT id, name FROM teachers ORDER BY name")
        already = db.one(conn, "SELECT COUNT(*) AS n FROM findings")["n"]
    if already:
        return {"skipped": "There are findings already. Run `athar seed` first for a clean start.", "findings": already}

    token = audit.current_actor.set(ACTOR)
    out: dict[str, Any] = {"proposed": 0, "approved": 0, "waiting": 0, "open_questions": 0, "learners": []}
    try:
        for suffix, approve_kinds in _plan(learners, db_path).items():
            learner = next((row for row in learners if row["alias"].endswith(suffix)), None)
            if learner is None:
                continue
            propose_for(learner, approve_kinds, teacher["id"],
                        ("سُجّل ضمن إعداد العرض التجريبي، وليس بقرار مدرس حقيقي." if get_settings().language == "ar"
                         else "Recorded by the demo setup, not by a real teacher."), out, db_path)
            out["learners"].append(learner["alias"])
    finally:
        audit.current_actor.reset(token)
    out["decisions_recorded_as"] = teacher["name"]
    return out
