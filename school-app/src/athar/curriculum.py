"""Curriculum map: concepts and "needs this first" links, loaded from packs/<pack_id>/pack.yaml.

We graph the school's curriculum; we never change it.

A school can add topics of its own (more grades, another subject). Those additions live in the database, each
one approved by a named teacher, and are laid over the installed pack when it is loaded. The pack file itself
is never rewritten, and an addition that does not fit is left out, so the installed curriculum always loads."""

from __future__ import annotations

import copy
import json
import sqlite3
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import yaml

from .config import get_settings

SKILL_KINDS = ("thinking", "disposition")  # a disposition describes character, never a struggle finding
_CACHE: dict[tuple[str, Path], Pack] = {}
_MERGED: dict[tuple, Pack] = {}   # the same packs with a school's approved additions laid over them


# The language labels are given in when a caller does not say. The web app sets it for each request from
# the reader's choice. Everything else (the MCP tools, tests, the command line) gets English unless it asks.
current_lang: ContextVar[str] = ContextVar("current_lang", default="en")


@dataclass(frozen=True)
class Concept:
    id: str
    label: dict[str, str]
    strand: str
    grade: int
    requires: tuple[str, ...]
    skills: tuple[str, ...]
    term: int | None = None      # the term it is taught in, when the curriculum says so
    source: str | None = None    # where the topic comes from, when the pack records it


@dataclass
class Pack:
    id: str
    name: str
    subject: str
    grades: tuple[int, int]
    strands: dict[str, dict[str, str]]
    skills: dict[str, dict[str, str]]
    approaches: dict[str, dict[str, str]]
    concepts: dict[str, Concept]
    graph: nx.DiGraph  # edge prerequisite -> concept
    skill_kinds: dict[str, str] = field(default_factory=dict)  # skill id -> "thinking" | "disposition"
    subjects: dict[str, dict[str, str]] = field(default_factory=dict)  # subject id -> labels
    strand_subject: dict[str, str] = field(default_factory=dict)       # strand id -> subject id
    terms: int = 3                                                     # terms in a school year
    names: dict[str, str] = field(default_factory=dict)                # the pack's own name in other languages
    additions: list[dict] = field(default_factory=list)               # what the school added: id, title, who approved, topic ids

    def title(self, lang: str | None = None) -> str:
        """The curriculum's name in the reader's language, else in English."""
        return self.names.get(lang or current_lang.get()) or self.name

    def label(self, any_id: str, lang: str | None = None) -> str:
        """Label of a concept, strand, skill or approach; falls back to English, then the id."""
        lang = lang or current_lang.get()
        if any_id in self.concepts:
            labels = self.concepts[any_id].label
        else:
            labels = (self.strands.get(any_id) or self.skills.get(any_id) or self.approaches.get(any_id)
                      or self.subjects.get(any_id) or {})
        return labels.get(lang) or labels.get("en") or any_id

    def prerequisites(self, concept_id: str) -> list[str]:
        """Concepts this one directly needs first."""
        return sorted(self.graph.predecessors(concept_id))

    def ancestors(self, concept_id: str) -> list[str]:
        """Every concept needed before this one, nearest first (breadth-first)."""
        seen: list[str] = []
        queue = deque(self.prerequisites(concept_id))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.append(current)
            queue.extend(self.prerequisites(current))
        return seen

    def dependents(self, concept_id: str) -> list[str]:
        """Concepts that directly need this one first."""
        return sorted(self.graph.successors(concept_id))


def load_pack(pack_id: str | None = None, packs_dir: Path | None = None) -> Pack:
    """Load and validate a pack. Cached per (pack id, folder)."""
    settings = get_settings()
    pack_id = pack_id or settings.default_pack
    folder = Path(packs_dir or settings.packs_dir).resolve()
    key = (pack_id, folder)
    stamp = _additions_stamp(pack_id, settings.db_path)
    if not stamp:
        if key not in _CACHE:
            _CACHE[key] = _read_pack(folder / pack_id / "pack.yaml")
        return _CACHE[key]
    merged = (*key, str(settings.db_path), stamp)
    if merged not in _MERGED:
        for old in [k for k in _MERGED if k[:3] == merged[:3]]:
            del _MERGED[old]
        _MERGED[merged] = _read_pack(folder / pack_id / "pack.yaml", _additions(pack_id, settings.db_path))
    return _MERGED[merged]


def _query(db_path: Path, sql: str, params: tuple) -> list[tuple]:
    """Read from the database without creating it. No file, or no such table yet, means no additions."""
    path = Path(db_path)
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(path, timeout=5)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def _additions_stamp(pack_id: str, db_path: Path) -> tuple:
    """Which additions are approved right now. Cheap, and it changes whenever one is approved or withdrawn."""
    return tuple(_query(db_path, "SELECT id, decided_at FROM curriculum_additions WHERE pack_id = ? AND status = 'approved' "
                                 "ORDER BY decided_at, id", (pack_id,)))


def _additions(pack_id: str, db_path: Path) -> list[dict]:
    found = []
    for row in _query(db_path, "SELECT id, title, approved, decided_by, decided_at FROM curriculum_additions "
                               "WHERE pack_id = ? AND status = 'approved' ORDER BY decided_at, id", (pack_id,)):
        try:
            body = json.loads(row[2])
        except (TypeError, ValueError):
            continue
        if isinstance(body, dict):
            found.append({**body, "id": row[0], "title": row[1], "decided_by": row[3], "decided_at": row[4]})
    return found


def apply_addition(data: dict, addition: dict) -> None:
    """Lay one addition over pack data, in place: a subject if it is new, new areas, new topics, and links
    from installed topics back to the new ones. Raises when it does not fit."""
    subject = addition["subject"]
    if subject["id"] not in {s["id"] for s in data["subjects"]}:
        data["subjects"].append({"id": subject["id"], "label": dict(subject["label"])})
    strands = {s["id"] for s in data["strands"]}
    for strand in addition.get("strands") or []:
        if strand["id"] in strands:
            raise ValueError(f"area '{strand['id']}' is already in the curriculum")
        data["strands"].append({"id": strand["id"], "label": dict(strand["label"]), "subject": subject["id"]})
        strands.add(strand["id"])
    by_id = {c["id"]: c for c in data["concepts"]}
    for concept in addition["concepts"]:
        if concept["id"] in by_id:
            raise ValueError(f"topic '{concept['id']}' is already in the curriculum")
        by_id[concept["id"]] = dict(concept)
        data["concepts"].append(by_id[concept["id"]])
    for link in addition.get("links") or []:
        target = by_id[link["concept"]]
        target["requires"] = list(dict.fromkeys(list(target.get("requires") or []) + list(link["requires"])))
    grades = [int(c["grade"]) for c in addition["concepts"]]
    if grades:
        data["grades"] = [min(int(data["grades"][0]), *grades), max(int(data["grades"][1]), *grades)]


def read_pack_data(path: Path) -> dict:
    """Read pack.yaml as plain data. A pack may `include` other packs (one per subject) and add
    cross-subject `links`; the result is one merged pack with every strand tagged with its subject."""
    if not path.exists():
        raise ValueError(f"Curriculum pack not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    own_subject = {"id": data["subject"], "label": data.get("subject_label") or {"en": str(data["subject"]).title()}}
    for strand in data.get("strands") or []:
        strand.setdefault("subject", own_subject["id"])
    data["subjects"] = [own_subject] if data.get("strands") else []
    for key in ("strands", "skills", "approaches", "concepts"):
        data[key] = list(data.get(key) or [])
    for included in data.get("includes") or []:
        part = read_pack_data(path.parent.parent / included / "pack.yaml")
        data["subjects"] += [s for s in part["subjects"] if s["id"] not in {x["id"] for x in data["subjects"]}]
        for key in ("strands", "skills", "approaches"):
            have = {item["id"] for item in data[key]}
            data[key] += [item for item in part[key] if item["id"] not in have]
        clash = {c["id"] for c in data["concepts"]} & {c["id"] for c in part["concepts"]}
        if clash:
            raise ValueError(f"Pack '{data['id']}': concept ids appear in more than one included pack: {sorted(clash)}")
        data["concepts"] += part["concepts"]
    by_id = {c["id"]: c for c in data["concepts"]}
    for link in data.get("links") or []:
        if link["concept"] not in by_id:
            raise ValueError(f"Pack '{data['id']}': link names unknown concept '{link['concept']}'")
        target = by_id[link["concept"]]
        target["requires"] = list(dict.fromkeys(list(target.get("requires") or []) + list(link["requires"])))
    return data


def _read_pack(path: Path, additions: list[dict] | tuple = ()) -> Pack:
    """Parse pack.yaml into a Pack and check it, then lay each approved addition over it. An addition that
    does not fit (a topic it leans on is gone, say) is left out and the rest still load."""
    data = read_pack_data(path)
    pack = build_pack(data)
    applied = []
    for addition in additions:
        trial = copy.deepcopy(data)
        try:
            apply_addition(trial, addition)
            built = build_pack(trial)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        data, pack = trial, built
        applied.append({"id": addition["id"], "title": addition.get("title"), "decided_by": addition.get("decided_by"),
                        "decided_at": addition.get("decided_at"), "concepts": [c["id"] for c in addition["concepts"]]})
    pack.additions = applied
    return pack


def build_pack(data: dict) -> Pack:
    """Turn pack data (as `read_pack_data` returns it) into a checked Pack."""
    concepts = {c["id"]: _concept(c) for c in data.get("concepts", [])}
    pack = Pack(
        id=data["id"],
        name=data["name"],
        subject=data["subject"],
        grades=tuple(data["grades"]),
        strands=_labels(data.get("strands", [])),
        skills=_labels(data.get("skills", [])),
        approaches=_labels(data.get("approaches", [])),
        concepts=concepts,
        graph=_build_graph(concepts),
        skill_kinds={s["id"]: s.get("kind", "thinking") for s in data.get("skills", [])},
        subjects={s["id"]: dict(s["label"]) for s in data["subjects"]},
        strand_subject={s["id"]: s["subject"] for s in data.get("strands", [])},
        terms=int(data.get("terms", 3)),
        names={"ar": data["name_ar"]} if data.get("name_ar") else {},
    )
    _validate(pack)
    return pack


def _concept(raw: dict) -> Concept:
    return Concept(
        id=raw["id"],
        label=_label(raw["label"], raw["id"]),
        strand=raw["strand"],
        grade=int(raw["grade"]),
        requires=tuple(raw.get("requires") or ()),
        skills=tuple(raw.get("skills") or ()),
        term=int(raw["term"]) if raw.get("term") else None,
        source=raw.get("source"),
    )


def _label(raw: dict, owner: str) -> dict[str, str]:
    """A label is {language code: text}. An unquoted comma in the pack file splits a label into extra
    keys and silently cuts the text, so anything that is not a language code is refused."""
    bad = [key for key, text in raw.items() if not (isinstance(key, str) and 2 <= len(key) <= 3 and isinstance(text, str))]
    if bad:
        raise ValueError(f"The label of '{owner}' is broken ({bad[0]!r}). Put the text in quotes if it has a comma.")
    return dict(raw)


def _labels(items: list[dict]) -> dict[str, dict[str, str]]:
    """Turn [{id, label}] into {id: label dict}."""
    return {item["id"]: _label(item["label"], item["id"]) for item in items}


def _build_graph(concepts: dict[str, Concept]) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(concepts)
    for concept in concepts.values():
        for prerequisite in concept.requires:
            graph.add_edge(prerequisite, concept.id)
    return graph


def _validate(pack: Pack) -> None:
    """Every reference must exist, every label needs English, and `requires` must be a DAG."""
    problems = []
    for group in (pack.strands, pack.skills, pack.approaches):
        problems += [f"'{item_id}' has no 'en' label" for item_id, label in group.items() if "en" not in label]
    problems += [f"skill '{sid}' has unknown kind '{kind}'" for sid, kind in pack.skill_kinds.items()
                 if kind not in SKILL_KINDS]
    for concept in pack.concepts.values():
        if "en" not in concept.label:
            problems.append(f"concept '{concept.id}' has no 'en' label")
        if concept.strand not in pack.strands:
            problems.append(f"concept '{concept.id}' uses unknown strand '{concept.strand}'")
        problems += [f"concept '{concept.id}' requires unknown concept '{r}'"
                     for r in concept.requires if r not in pack.concepts]
        problems += [f"concept '{concept.id}' uses unknown skill '{s}'"
                     for s in concept.skills if s not in pack.skills]
        if concept.term is not None and not 1 <= concept.term <= pack.terms:
            problems.append(f"concept '{concept.id}' is in term {concept.term}, but the year has {pack.terms} terms")
    if not problems and not nx.is_directed_acyclic_graph(pack.graph):
        problems.append("concept prerequisites contain a cycle")
    if problems:
        raise ValueError(f"Invalid pack '{pack.id}': " + "; ".join(problems))
