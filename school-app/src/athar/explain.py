"""Why a finding says what it says, in plain sentences and in numbers a picture can be drawn from.

Everything here is computed from the records a finding cites. No model is involved, so the
explanation cannot say more than the evidence does. The teacher app and the printable report draw the
same two pictures from it: results term by term, and for a root cause the chain of topics from where
the difficulty began to where it shows today."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import db
from .curriculum import Pack

MAX_TOPICS_NAMED = 4


def _pct(mean: float) -> str:
    return f"{round(mean * 100)}%"


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _records(n: int) -> str:
    return "1 record" if n == 1 else f"{n} records"


def explain(finding: dict[str, Any], pack: Pack) -> dict[str, Any]:
    """`finding` is an expanded finding: kind, path, concept_ids and its cited `evidence` rows."""
    rows = finding.get("evidence") or []
    scored = [r for r in rows if r["score"] is not None]
    by_period: dict[int, list[float]] = defaultdict(list)
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for row in scored:
        by_period[row["period_ord"]].append(row["score"])
        if row["concept_id"]:
            by_topic[row["concept_id"]].append(row)
    series = [{"period": db.period_label(o), "mean": _mean(v), "records": len(v)} for o, v in sorted(by_period.items())]
    absent = [r for r in rows if r["kind"] == "attendance" and r["absent_days"]]
    days_absent = sum(r["absent_days"] for r in absent)
    absent_terms = sorted({db.period_label(r["period_ord"]) for r in absent})

    def topic(concept_id: str) -> dict[str, Any]:
        mine = by_topic.get(concept_id, [])
        known = concept_id in pack.concepts
        return {"id": concept_id, "label": pack.label(concept_id), "grade": pack.concepts[concept_id].grade if known else None,
                "mean": _mean([r["score"] for r in mine]), "records": len(mine),
                "first_period": db.period_label(min(r["period_ord"] for r in mine)) if mine else None}

    path = finding.get("path") or []
    # Drawn from where it began (left) to where it shows now (right): the order a teacher would act in.
    chain = [topic(c) for c in reversed(path)] if finding.get("kind") == "root_cause" and len(path) > 1 else []
    facts: list[str] = []
    kind = finding.get("kind")
    if chain:
        start, now = chain[0], chain[-1]
        if now["mean"] is not None:
            facts.append(f"Results in {now['label']} are low now: {_pct(now['mean'])} over {_records(now['records'])}.")
        between = [t["label"] for t in chain[1:-1]]
        link = f"{now['label']} builds on {start['label']}"
        facts.append(link + (f", through {' and '.join(between)}." if between else "."))
        if start["mean"] is not None:
            facts.append(f"Results in {start['label']} were {_pct(start['mean'])} over {_records(start['records'])}, "
                         f"first recorded in {start['first_period']}.")
        if days_absent:
            facts.append(f"{days_absent} days of absence were recorded in {', '.join(absent_terms)}.")
        facts.append(f"So {start['label']} is the earliest low point the records show. It is a place to check, not a verdict.")
    elif kind == "root_cause":
        concepts = finding.get("concept_ids") or []
        here = topic(concepts[0]) if concepts else None
        if here and here["mean"] is not None:
            facts.append(f"Results in {here['label']} are low: {_pct(here['mean'])} over {_records(here['records'])}.")
        facts.append("The topics it builds on do not show low results in the records, so the difficulty seems to start here.")
    elif scored:
        facts.append(f"{_records(len(scored)).capitalize()} across {len(series)} "
                     f"{'term' if len(series) == 1 else 'terms'}, from {series[0]['period']} to {series[-1]['period']}.")
        means = [point["mean"] for point in series]
        overall = _mean([r["score"] for r in scored])
        spread = f" Term averages ran from {_pct(min(means))} to {_pct(max(means))}." if len(means) > 1 else ""
        facts.append(f"They average {_pct(overall)}.{spread}")
        names = [pack.label(c) for c in by_topic]
        if names:
            more = f" and {len(names) - MAX_TOPICS_NAMED} more" if len(names) > MAX_TOPICS_NAMED else ""
            facts.append(f"Topics: {', '.join(names[:MAX_TOPICS_NAMED])}{more}.")
        if kind == "what_worked":
            facts.append("The finding compares results before and after units taught this way, against this "
                         "learner's own earlier average.")
        if days_absent:
            facts.append(f"{days_absent} days of absence were recorded in {', '.join(absent_terms)}.")
    return {"facts": facts, "series": series, "chain": chain, "days_absent": days_absent, "records": len(rows)}
