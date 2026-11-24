"""The reasoning layer. Pure, deterministic graph walks over the curriculum pack and the evidence
table. No model calls. Every result names the evidence rows it rests on."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from . import db
from .curriculum import Pack, load_pack

STRUGGLE_BELOW = 0.5   # a period mean below this is a struggle
STRENGTH_ABOVE = 0.8   # a period mean above this is a strength
CLEAR_GAIN = 0.15      # an approach "improved" things when the mean rose at least this much
UNCERTAIN_CAP = 0.35   # highest confidence for a root whose prerequisites have holes in the record

Row = dict[str, Any]


# ---------------------------------------------------------------- shared helpers

def _load(conn, learner_id: str) -> tuple[Row, Pack]:
    """The learner row and the curriculum pack they follow. Unknown learner raises."""
    learner = db.one(conn, "SELECT * FROM learners WHERE id = ?", (learner_id,))
    if learner is None:
        raise ValueError(f"Unknown learner '{learner_id}'. Call list_learners to see valid ids.")
    return learner, load_pack(learner["pack_id"])


def _scored(conn, learner_id: str) -> list[Row]:
    """Items that count toward mastery: active and scored, oldest first."""
    return db.rows(conn, "SELECT * FROM evidence WHERE learner_id = ? AND status = 'active' "
                         "AND score IS NOT NULL ORDER BY period_ord, id", (learner_id,))


def _mean(items: list[Row]) -> float:
    return round(sum(r["score"] for r in items) / len(items), 3)


def _ids(items: list[Row]) -> list[str]:
    return [r["id"] for r in items]


def _confidence(n_items: int, n_unknowns_on_path: int = 0) -> float:
    """More items give more confidence: n / (n + 4). Each unrecorded concept between the target and
    the root (a hole in the chain) cuts it by a fifth."""
    return round(n_items / (n_items + 4) * 0.8 ** n_unknowns_on_path, 2)


def _group(items: list[Row], scope_ids_of: Callable[[Row], list[str]]) -> dict[str, dict[int, list[Row]]]:
    """{scope_id: {period_ord: [items]}} for one scope type."""
    groups: dict[str, dict[int, list[Row]]] = defaultdict(lambda: defaultdict(list))
    for row in items:
        for scope_id in scope_ids_of(row):
            groups[scope_id][row["period_ord"]].append(row)
    return groups


def _period_entry(ord_: int, items: list[Row]) -> dict:
    return {"period_ord": ord_, "period": db.period_label(ord_), "mean": _mean(items),
            "n": len(items), "evidence_ids": _ids(items)}


def _concept_of(pack: Pack) -> Callable[[Row], list[str]]:
    return lambda row: [row["concept_id"]] if row["concept_id"] in pack.concepts else []


def _strand_of(pack: Pack) -> Callable[[Row], list[str]]:
    return lambda row: [pack.concepts[row["concept_id"]].strand] if row["concept_id"] in pack.concepts else []


def _skills_of(pack: Pack) -> Callable[[Row], list[str]]:
    """A row shows a skill when it is tagged with it, or when its concept is tagged with it."""
    def skills(row: Row) -> list[str]:
        found = set(pack.concepts[row["concept_id"]].skills) if row["concept_id"] in pack.concepts else set()
        if row["skill_id"] in pack.skills:
            found.add(row["skill_id"])
        return sorted(found)
    return skills


# ---------------------------------------------------------------- concept_mastery

def concept_mastery(learner_id: str, *, db_path=None) -> dict:
    """Per concept, the mean score in each period that has scored items."""
    with db.connect(db_path) as conn:
        _, pack = _load(conn, learner_id)
        items = _scored(conn, learner_id)
    groups = _group(items, _concept_of(pack))
    return {cid: [_period_entry(o, rows) for o, rows in sorted(periods.items())]
            for cid, periods in sorted(groups.items())}


# ---------------------------------------------------------------- find_patterns

def _period_kind(mean: float) -> str | None:
    if mean < STRUGGLE_BELOW:
        return "struggle"
    if mean > STRENGTH_ABOVE:
        return "strength"
    return None


def _runs(periods: dict[int, list[Row]], min_periods: int) -> list[tuple[str, list[int]]]:
    """Runs of consecutive data periods with the same kind, at least `min_periods` long."""
    found, run, run_kind = [], [], None
    for ord_ in sorted(periods):
        kind = _period_kind(_mean(periods[ord_]))
        if kind != run_kind:
            if run_kind and len(run) >= min_periods:
                found.append((run_kind, run))
            run, run_kind = [], kind
        run.append(ord_)
    if run_kind and len(run) >= min_periods:
        found.append((run_kind, run))
    return found


def _concepts_behind(kind: str, items: list[Row]) -> list[str]:
    """Concepts inside a strand or skill pattern that are themselves low (struggle) or strong
    (strength) over the pattern's periods, most recent first. Tells the agent where to trace from."""
    by_concept: dict[str, list[Row]] = defaultdict(list)
    for row in items:
        if row["concept_id"]:
            by_concept[row["concept_id"]].append(row)
    matching = [cid for cid, rows in by_concept.items() if _period_kind(_mean(rows)) == kind]
    latest = {cid: max(r["period_ord"] for r in by_concept[cid]) for cid in matching}
    return sorted(matching, key=lambda cid: (-latest[cid], cid))


def _pattern(kind: str, scope: str, scope_id: str, run: list[int],
             periods: dict[int, list[Row]], pack: Pack) -> dict:
    items = [row for ord_ in run for row in periods[ord_]]
    concept_ids = [scope_id] if scope == "concept" else _concepts_behind(kind, items)
    return {"kind": kind, "scope": scope, "scope_id": scope_id, "label": pack.label(scope_id),
            "periods": [db.period_label(o) for o in run], "mean": _mean(items), "n_items": len(items),
            "evidence_ids": _ids(items), "confidence": _confidence(len(items)), "concept_ids": concept_ids}


def _data_gaps(conn, learner_id: str, items: list[Row], min_periods: int) -> list[dict]:
    """Periods inside the learner's record with no scored items, and a note when data is too thin."""
    span = db.one(conn, "SELECT MIN(period_ord) AS lo, MAX(period_ord) AS hi FROM evidence "
                        "WHERE learner_id = ? AND status = 'active'", (learner_id,))
    with_data = {r["period_ord"] for r in items}
    gaps = []
    if span["lo"] is not None:
        gaps = [{"period": db.period_label(o), "reason": "no scored items recorded"}
                for o in range(span["lo"], span["hi"] + 1) if o not in with_data]
    if len(with_data) < min_periods:
        gaps.append({"period": None, "reason": f"only {len(with_data)} period(s) have scored items; "
                                               f"a pattern needs at least {min_periods}"})
    return gaps


def _is_disposition_struggle(kind: str, scope: str, scope_id: str, pack: Pack) -> bool:
    """A low run on a disposition skill (such as persistence) would read as a label on a child, so it is
    never reported. A strength on one is fine."""
    return kind == "struggle" and scope == "skill" and pack.skill_kinds.get(scope_id) == "disposition"


def find_patterns(learner_id: str, min_periods: int = 3, *, db_path=None) -> dict:
    """Strengths and struggles held for `min_periods` data periods, by strand, skill and concept."""
    with db.connect(db_path) as conn:
        _, pack = _load(conn, learner_id)
        items = _scored(conn, learner_id)
        gaps = _data_gaps(conn, learner_id, items, min_periods)
    patterns = []
    for scope, scope_ids_of in (("strand", _strand_of(pack)), ("skill", _skills_of(pack)),
                                ("concept", _concept_of(pack))):
        for scope_id, periods in sorted(_group(items, scope_ids_of).items()):
            for kind, run in _runs(periods, min_periods):
                if not _is_disposition_struggle(kind, scope, scope_id, pack):
                    patterns.append(_pattern(kind, scope, scope_id, run, periods, pack))
    return {"learner_id": learner_id, "patterns": patterns, "data_gaps": gaps}


# ---------------------------------------------------------------- trace_root

def _concept_stats(items: list[Row]) -> dict[str, dict]:
    """Per concept over all periods: mean, n, evidence ids and the first period it was seen."""
    by_concept: dict[str, list[Row]] = defaultdict(list)
    for row in items:
        if row["concept_id"]:
            by_concept[row["concept_id"]].append(row)
    return {cid: {"mean": _mean(rows), "n": len(rows), "evidence_ids": _ids(rows),
                  "first_ord": rows[0]["period_ord"]} for cid, rows in by_concept.items()}


def _is_low(stats: dict, concept_id: str) -> bool:
    return concept_id in stats and stats[concept_id]["mean"] < STRUGGLE_BELOW


def _walk_back(pack: Pack, target: str, stats: dict) -> dict[str, str | None]:
    """Breadth-first walk over prerequisites. We keep walking through concepts that are low or have
    no evidence, and stop at concepts that are fine. Returns {concept: the concept we came from}."""
    came_from: dict[str, str | None] = {target: None}
    queue = deque([target])
    while queue:
        current = queue.popleft()
        for prerequisite in pack.prerequisites(current):
            if prerequisite in came_from:
                continue
            came_from[prerequisite] = current
            if _is_low(stats, prerequisite) or prerequisite not in stats:
                queue.append(prerequisite)
    return came_from


def _path_to(came_from: dict[str, str | None], root: str) -> list[str]:
    """Concept ids from the target back to `root`."""
    path, current = [], root
    while current is not None:
        path.append(current)
        current = came_from[current]
    return list(reversed(path))


def _root_entry(pack: Pack, stats: dict, concept_id: str, taught_ord: int | None = None) -> dict:
    s = stats[concept_id]
    return {"concept_id": concept_id, "label": pack.label(concept_id), "grade": pack.concepts[concept_id].grade,
            "mean": s["mean"], "n": s["n"], "period": db.period_label(s["first_ord"]),
            "taught_period": db.period_label(taught_ord) if taught_ord is not None else None,
            "evidence_ids": s["evidence_ids"]}


def _taught_ord(conn, learner: Row, concept_id: str) -> int | None:
    """When the concept was taught to this learner's year group, from teaching_units. A unit is for
    this learner's group when unit.grade - unit.year == start_grade - start_year."""
    row = db.one(conn, "SELECT MIN(year * 3 + term - 1) AS ord FROM teaching_units "
                       "WHERE concept_id = ? AND grade - year = ?",
                 (concept_id, learner["start_grade"] - learner["start_year"]))
    return row["ord"]


def _absences(conn, learner_id: str, ord_: int) -> list[dict]:
    """Attendance rows with absent days in one period."""
    found = db.rows(conn, "SELECT id, period_ord, absent_days FROM evidence WHERE learner_id = ? "
                          "AND kind = 'attendance' AND status = 'active' AND period_ord = ? "
                          "AND absent_days > 0 ORDER BY id", (learner_id, ord_))
    return [{"type": "absence", "period": db.period_label(r["period_ord"]), "absent_days": r["absent_days"],
             "evidence_id": r["id"]} for r in found]


def _unrecorded_prerequisites(pack: Pack, learner: Row, stats: dict, root_id: str) -> tuple[list, list]:
    """Direct prerequisites of the root with no evidence, split in two: taught before the learner's
    records begin (grade below start_grade), and holes in the record (the learner was enrolled)."""
    unrecorded = [p for p in pack.prerequisites(root_id) if p not in stats]
    before_record = [p for p in unrecorded if pack.concepts[p].grade < learner["start_grade"]]
    return before_record, [p for p in unrecorded if p not in before_record]


def _no_root(target: dict, reason: str, path: list[str] | None = None, unknowns: list[str] | None = None,
             missing: list[str] | None = None, evidence_ids: list[str] | None = None) -> dict:
    """A trace that names no root: nothing to trace, or the records cannot tell where it began."""
    return {"target": target, "path": path or [], "root": None, "root_is_target": False, "root_is_certain": False,
            "context": [], "unknowns": unknowns or [], "unknowns_on_path": [],
            "unrecorded_prerequisites_of_root": missing or [], "prerequisites_before_record": [],
            "prerequisites_missing_in_record": missing or [], "alternatives": [],
            "evidence_ids": evidence_ids or [], "confidence": 0.0, "reason": reason}


def _labels_of(pack: Pack, concept_ids: list[str]) -> str:
    return ", ".join(pack.label(c) for c in concept_ids)


def _days(n: int) -> str:
    return f"{n} day of absence was" if n == 1 else f"{n} days of absence were"


def _reason(pack: Pack, learner: Row, target: dict, root: dict, unknowns_on_path: list[str],
            before_record: list[str], missing: list[str], context: list[dict]) -> str:
    """Plain sentences, in the order a teacher would check them. A missing-record caveat comes last."""
    text = f"{target['label']} is low (mean {target['mean']} over {target['n']} items). "
    if root["concept_id"] == target["concept_id"]:
        text += "Its recorded prerequisites are fine, so the difficulty starts here. "
    else:
        text += (f"Walking back through prerequisites, {root['label']} (grade {root['grade']}, first seen "
                 f"{root['period']}) is the deepest low concept on the way. ")
    if context:
        text += (f"{_days(sum(c['absent_days'] for c in context))} recorded in {context[0]['period']}, "
                 f"when {root['label']} was taught. ")
    if unknowns_on_path:
        text += f"There are no records for {_labels_of(pack, unknowns_on_path)} between them; this was not guessed. "
    if before_record:
        was = "was" if len(before_record) == 1 else "were"
        text += (f"Records begin in grade {learner['start_grade']}, so {_labels_of(pack, before_record)} "
                 f"{was} taught before the record. ")
    if missing:
        it = "it was" if len(missing) == 1 else "they were"
        text += (f"The difficulty may begin earlier: there are no records for {_labels_of(pack, missing)}, "
                 f"although the learner was enrolled when {it} taught. ")
    return text.strip()


def _cannot_tell(pack: Pack, target: dict, missing: list[str], unknowns: list[str], stats: dict) -> dict:
    """The target is the only low concept, but a prerequisite it needs has no records at all."""
    plural = "s" if len(missing) > 1 else ""
    return _no_root(target, f"{target['label']} is low, but there are no records for {_labels_of(pack, missing)} "
                            f"(its prerequisite{plural}), so where the difficulty began cannot be told from "
                            "the records.",
                    path=[target["concept_id"]], unknowns=unknowns, missing=missing,
                    evidence_ids=stats[target["concept_id"]]["evidence_ids"])


def _root_candidates(pack: Pack, came_from: dict, stats: dict) -> list[str]:
    """Low concepts on the walk with no low direct prerequisite; deepest (lowest grade) first."""
    candidates = [c for c in came_from if _is_low(stats, c)
                  and not any(_is_low(stats, p) for p in pack.prerequisites(c))]
    return sorted(candidates, key=lambda c: (pack.concepts[c].grade, -len(_path_to(came_from, c)), stats[c]["mean"]))


def trace_root(learner_id: str, concept_id: str, *, db_path=None) -> dict:
    """Walk prerequisites back from a struggling concept to the deepest low concept on the way."""
    with db.connect(db_path) as conn:
        learner, pack = _load(conn, learner_id)
        if concept_id not in pack.concepts:
            raise ValueError(f"Unknown concept '{concept_id}' in pack '{pack.id}'.")
        stats = _concept_stats(_scored(conn, learner_id))
        target_stats = stats.get(concept_id, {"mean": None, "n": 0})
        target = {"concept_id": concept_id, "label": pack.label(concept_id),
                  "mean": target_stats["mean"], "n": target_stats["n"]}
        if concept_id not in stats:
            return _no_root(target, "No scored evidence for this concept yet, so there is nothing to trace.")
        if not _is_low(stats, concept_id):
            return _no_root(target, f"This concept is not low (mean {target['mean']}), so there is no "
                                    "struggle to trace.")
        came_from = _walk_back(pack, concept_id, stats)
        candidates = _root_candidates(pack, came_from, stats)
        root_id = candidates[0]
        taught = _taught_ord(conn, learner, root_id)
        context = _absences(conn, learner_id, taught if taught is not None else stats[root_id]["first_ord"])
    unknowns = [c for c in came_from if c not in stats]
    before_record, missing = _unrecorded_prerequisites(pack, learner, stats, root_id)
    if root_id == concept_id and missing:
        return _cannot_tell(pack, target, missing, unknowns, stats)
    path = _path_to(came_from, root_id)
    unknowns_on_path = [c for c in path[1:-1] if c not in stats]
    on_path = [c for c in path if c in stats]
    evidence_ids = sorted({e for c in on_path for e in stats[c]["evidence_ids"]} | {c["evidence_id"] for c in context})
    root = _root_entry(pack, stats, root_id, taught)
    n_claim = stats[root_id]["n"] + (stats[concept_id]["n"] if root_id != concept_id else 0)
    confidence = _confidence(n_claim, len(unknowns_on_path))
    return {"target": target, "path": path, "root": root, "root_is_target": root_id == concept_id,
            "root_is_certain": not missing, "context": context, "unknowns": unknowns,
            "unknowns_on_path": unknowns_on_path, "unrecorded_prerequisites_of_root": before_record + missing,
            "prerequisites_before_record": before_record, "prerequisites_missing_in_record": missing,
            "alternatives": [_root_entry(pack, stats, c) for c in candidates[1:]],
            "evidence_ids": evidence_ids,
            "confidence": min(confidence, UNCERTAIN_CAP) if missing else confidence,
            "reason": _reason(pack, learner, target, root, unknowns_on_path, before_record, missing, context)}


# ---------------------------------------------------------------- what_worked

BASELINE_PERIODS = 2     # the learner's own recent average comes from this many earlier data periods
MIN_BASELINE_ITEMS = 4


def _unit_instance(unit: Row, items: list[Row]) -> dict | None:
    """Before/after for one teaching unit. After = the learner's items tagged with this unit.
    Before = the learner's own recent baseline: all their scored items, any concept, in the two most
    recent earlier periods with data. None when there is no after or too thin a baseline."""
    after = [r for r in items if r["unit_id"] == unit["id"]]
    unit_ord = db.period_ord(unit["year"], unit["term"])
    baseline_ords = sorted({r["period_ord"] for r in items if r["period_ord"] < unit_ord})[-BASELINE_PERIODS:]
    before = [r for r in items if r["period_ord"] in baseline_ords]
    if not after or len(before) < MIN_BASELINE_ITEMS:
        return None
    return {"concept_id": unit["concept_id"], "period": db.period_label(unit_ord), "before": _mean(before),
            "after": _mean(after), "unit_id": unit["id"],
            "baseline_periods": [db.period_label(o) for o in baseline_ords],
            "evidence_ids": _ids(before) + _ids(after)}


def what_worked(learner_id: str, *, db_path=None) -> dict:
    """For each teaching approach used with this learner, how often scores rose clearly afterwards."""
    with db.connect(db_path) as conn:
        _, pack = _load(conn, learner_id)
        items = _scored(conn, learner_id)
        units = db.rows(conn, "SELECT DISTINCT u.* FROM teaching_units u JOIN evidence e ON e.unit_id = u.id "
                              "WHERE e.learner_id = ? ORDER BY u.year, u.term, u.id", (learner_id,))
    by_approach: dict[str, list[dict]] = defaultdict(list)
    for unit in units:
        instance = _unit_instance(unit, items)
        if instance:
            by_approach[unit["approach_id"]].append(instance)
    approaches = []
    for approach_id, instances in by_approach.items():
        gains = [i["after"] - i["before"] for i in instances]
        approaches.append({"approach_id": approach_id, "label": pack.label(approach_id),
                           "units": len(instances),
                           "improved": sum(g >= CLEAR_GAIN for g in gains),
                           "not_improved": sum(g < CLEAR_GAIN for g in gains),
                           "mean_gain": round(sum(gains) / len(gains), 3), "instances": instances})
    approaches.sort(key=lambda a: (-a["improved"], -a["mean_gain"], a["approach_id"]))
    return {"approaches": approaches,
            "note": "Describes teaching approaches for this learner. It does not rate teachers. "
                    "Gains are measured against the learner's own recent average, so topic difficulty "
                    "also plays a part."}


# ---------------------------------------------------------------- learner_graph

def _state(mean: float | None) -> str:
    if mean is None:
        return "unseen"
    if mean > STRENGTH_ABOVE:
        return "strong"
    if mean < STRUGGLE_BELOW:
        return "gap"
    return "shaky"


def _node(node_id: str, node_type: str, pack: Pack, items: list[Row], grade=None, strand=None) -> dict:
    mean = _mean(items) if items else None
    return {"id": node_id, "type": node_type, "label": pack.label(node_id), "grade": grade, "strand": strand,
            "mastery": mean, "n": len(items), "state": _state(mean)}


def _timeline(items: list[Row], all_periods: list[int], pack: Pack) -> dict[str, dict[str, float]]:
    """For each period, every concept's mean over all items up to and including that period."""
    timeline, so_far = {}, defaultdict(list)
    for ord_ in all_periods:
        for row in items:
            if row["period_ord"] == ord_ and row["concept_id"] in pack.concepts:
                so_far[row["concept_id"]].append(row)
        timeline[db.period_label(ord_)] = {cid: _mean(rows) for cid, rows in sorted(so_far.items())}
    return timeline


def learner_graph(learner_id: str, *, db_path=None) -> dict:
    """The curriculum graph coloured by this learner's evidence, for drawing."""
    with db.connect(db_path) as conn:
        learner, pack = _load(conn, learner_id)
        items = _scored(conn, learner_id)
        all_periods = [r["period_ord"] for r in db.rows(
            conn, "SELECT DISTINCT period_ord FROM evidence WHERE learner_id = ? AND status = 'active' "
                  "ORDER BY period_ord", (learner_id,))]
    by_concept = {cid: [r for rows in periods.values() for r in rows]
                  for cid, periods in _group(items, _concept_of(pack)).items()}
    by_skill = {sid: [r for rows in periods.values() for r in rows]
                for sid, periods in _group(items, _skills_of(pack)).items()}
    by_strand = {sid: [r for rows in periods.values() for r in rows]
                 for sid, periods in _group(items, _strand_of(pack)).items()}
    nodes = [_node(c.id, "concept", pack, by_concept.get(c.id, []), c.grade, c.strand)
             for c in pack.concepts.values()]
    nodes += [_node(s, "skill", pack, by_skill.get(s, [])) for s in pack.skills]
    nodes += [_node(s, "strand", pack, by_strand.get(s, [])) for s in pack.strands]
    edges = [{"source": a, "target": b, "type": "requires"} for a, b in pack.graph.edges]
    for concept in pack.concepts.values():
        edges += [{"source": concept.id, "target": s, "type": "shows"} for s in concept.skills]
        edges.append({"source": concept.id, "target": concept.strand, "type": "shows"})
    return {"learner": learner, "periods": [db.period_label(o) for o in all_periods], "nodes": nodes,
            "edges": edges, "timeline": _timeline(items, all_periods, pack)}
