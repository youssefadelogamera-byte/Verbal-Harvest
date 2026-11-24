"""The whole school on one map: the curriculum, what the records show for the class as a whole, who
taught what and how, and where teachers have approved findings.

It aggregates by topic, never by learner. A learner appears on it only where a named teacher has
approved a finding about a topic, with no score. Nothing here ranks or compares learners."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx

from . import db
from .curriculum import load_pack
from .graph import STRENGTH_ABOVE, STRUGGLE_BELOW

FINDING_KINDS = ("root_cause", "struggle", "strength", "what_worked")


def _state(mean: float | None) -> str:
    if mean is None:
        return "unseen"
    if mean > STRENGTH_ABOVE:
        return "strong"
    return "gap" if mean < STRUGGLE_BELOW else "shaky"


def _finding_topics(kind: str, concept_ids: list[str]) -> list[str]:
    """The topics a finding is about. A root-cause finding lists [struggling topic, root]: it is
    placed on the root, because the map shows where difficulties begin."""
    if kind == "root_cause" and concept_ids:
        return [concept_ids[-1]]
    return list(dict.fromkeys(concept_ids))


def school_graph(db_path=None, only: set[str] | None = None) -> dict[str, Any]:
    """Nodes, links and totals for drawing the school map. `only`: the learners the person asking may see."""
    with db.connect(db_path) as conn:
        learners = db.rows(conn, "SELECT id, alias, display_name, pack_id FROM learners ORDER BY alias COLLATE NOCASE, id")
        scored = db.rows(conn, "SELECT learner_id, concept_id, score FROM evidence "
                               "WHERE status = 'active' AND score IS NOT NULL AND concept_id IS NOT NULL")
        units = db.rows(conn, "SELECT u.concept_id, u.approach_id, u.teacher_id, t.name AS teacher FROM teaching_units u "
                              "JOIN teachers t ON t.id = u.teacher_id")
        teachers = db.rows(conn, "SELECT id, name FROM teachers ORDER BY name COLLATE NOCASE")
        approved = db.rows(conn, "SELECT learner_id, kind, concept_ids FROM findings WHERE status IN ('approved', 'edited')")
    pack_id = learners[0]["pack_id"] if learners else None
    if only is not None:
        learners = [row for row in learners if row["id"] in only]
        scored = [row for row in scored if row["learner_id"] in only]
        approved = [row for row in approved if row["learner_id"] in only]
    if not learners:
        return {"nodes": [], "edges": [], "teachers": [], "subjects": [], "strand_subject": {},
                "totals": {"learners": 0, "topics": 0, "topics_with_records": 0, "approved_findings": 0}}
    pack = load_pack(pack_id)
    alias = {row["id"]: row["alias"] for row in learners}
    shown = {row["id"]: row["display_name"] or row["alias"] for row in learners}

    scores: dict[str, list[float]] = defaultdict(list)
    seen_by: dict[str, set[str]] = defaultdict(set)
    for row in scored:
        scores[row["concept_id"]].append(row["score"])
        seen_by[row["concept_id"]].add(row["learner_id"])
    taught: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for unit in units:
        taught[unit["concept_id"]].add((unit["teacher_id"], unit["teacher"], pack.label(unit["approach_id"])))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(FINDING_KINDS, 0))
    links: dict[str, list[dict]] = defaultdict(list)
    for finding in approved:
        for topic in _finding_topics(finding["kind"], db.jload(finding["concept_ids"], [])):
            counts[topic][finding["kind"]] += 1
            links[topic].append({"learner_id": finding["learner_id"], "alias": alias.get(finding["learner_id"], "?"),
                                 "name": shown.get(finding["learner_id"], "?"),
                                 "kind": finding["kind"]})

    nodes: list[dict[str, Any]] = []
    for concept in pack.concepts.values():
        values = scores.get(concept.id, [])
        mean = round(sum(values) / len(values), 3) if values else None
        nodes.append({
            "id": concept.id, "type": "concept", "label": pack.label(concept.id), "grade": concept.grade,
            "strand": concept.strand, "records": len(values), "learners": len(seen_by.get(concept.id, ())),
            "mean": mean, "state": _state(mean),
            "taught": [{"teacher_id": t, "teacher": name, "approach": approach}
                       for t, name, approach in sorted(taught.get(concept.id, ()), key=lambda x: (x[1], x[2]))],
            "findings": counts[concept.id] if concept.id in counts else dict.fromkeys(FINDING_KINDS, 0),
            "approved_for": sorted(links.get(concept.id, []), key=lambda x: (x["alias"], x["kind"])),
        })
    nodes += [{"id": strand, "type": "strand", "label": pack.label(strand)} for strand in pack.strands]
    edges = [{"source": a, "target": b, "type": "requires"} for a, b in pack.graph.edges]
    taught_topics: dict[str, int] = defaultdict(int)
    for who in taught.values():
        for teacher_id in {t for t, _, _ in who}:
            taught_topics[teacher_id] += 1
    return {
        "curriculum": pack.title(), "nodes": nodes, "edges": edges,
        "teachers": [{"id": t["id"], "name": t["name"], "topics": taught_topics.get(t["id"], 0)} for t in teachers],
        "subjects": [{"id": s, "label": pack.label(s)} for s in pack.subjects],
        "strand_subject": dict(pack.strand_subject),
        "thresholds": {"strong_above": STRENGTH_ABOVE, "gap_below": STRUGGLE_BELOW},
        "totals": {"learners": len(learners), "topics": len(pack.concepts), "topics_with_records": len(scores),
                   "approved_findings": len(approved)},
    }


def export_graph(path: Path | str, *, db_path=None) -> dict[str, int]:
    """Write the school graph to a GraphML file that Gephi, Cytoscape, yEd or Neo4j can open.
    Learners are aliases. A learner links to a topic by the number of records and by approved
    findings only: no scores per learner leave the database this way."""
    data = school_graph(db_path)
    graph = nx.DiGraph(name="Athar school graph")
    for node in data["nodes"]:
        if node["type"] == "strand":
            graph.add_node(node["id"], kind="strand", label=node["label"])
            continue
        graph.add_node(node["id"], kind="topic", label=node["label"], grade=node["grade"], records=node["records"],
                       learners_with_records=node["learners"], class_mean=-1.0 if node["mean"] is None else node["mean"],
                       state=node["state"], approved_root_causes=node["findings"]["root_cause"])
        graph.add_edge(node["id"], node["strand"], kind="in_strand")
        for unit in node["taught"]:
            graph.add_node(unit["teacher_id"], kind="teacher", label=unit["teacher"])
            graph.add_edge(unit["teacher_id"], node["id"], kind="taught", approach=unit["approach"])
        for link in node["approved_for"]:
            graph.add_node(link["learner_id"], kind="learner", label=link["alias"])
            graph.add_edge(link["learner_id"], node["id"], kind=f"approved_{link['kind']}")
    for edge in data["edges"]:
        graph.add_edge(edge["source"], edge["target"], kind="needed_before")
    with db.connect(db_path) as conn:
        for row in db.rows(conn, "SELECT e.learner_id, l.alias, e.concept_id, COUNT(*) AS n FROM evidence e "
                                 "JOIN learners l ON l.id = e.learner_id WHERE e.status = 'active' "
                                 "AND e.concept_id IS NOT NULL GROUP BY e.learner_id, e.concept_id"):
            if row["concept_id"] not in graph:
                continue
            if graph.has_edge(row["learner_id"], row["concept_id"]):
                graph[row["learner_id"]][row["concept_id"]]["records"] = row["n"]
            else:
                graph.add_node(row["learner_id"], kind="learner", label=row["alias"])
                graph.add_edge(row["learner_id"], row["concept_id"], kind="has_records", records=row["n"])
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, target)
    return {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()}
