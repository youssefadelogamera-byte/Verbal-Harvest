"""MCP server "athar". Exposes the twelve functions in tools.py and nothing else: approving
and answering (review.py) are deliberately not reachable over MCP.

Calls are attributed in the audit log to ATHAR_ACTOR (default "mcp-client") and ATHAR_RUN_ID, which
the agent sets when it spawns this server over stdio.

Run: `python -m athar.server` (stdio) or `python -m athar.server --http`."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import audit, tools
from .config import get_settings

mcp = FastMCP("athar", instructions=(
    "A cited learning map per learner. Read tools describe patterns in the evidence; write tools only "
    "store evidence, proposed findings, summary drafts and questions about missing records. A named "
    "teacher approves and answers everything elsewhere."))

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
WRITE_IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                   openWorldHint=False)


def _call(fn: Callable[..., dict], **kwargs: Any) -> dict:
    """Run a tool with the actor and run id from the environment, so the audit log names the caller."""
    actor = audit.current_actor.set(os.environ.get("ATHAR_ACTOR") or "mcp-client")
    run_id = audit.current_run_id.set(os.environ.get("ATHAR_RUN_ID") or None)
    try:
        return fn(**kwargs)
    finally:
        audit.current_actor.reset(actor)
        audit.current_run_id.reset(run_id)


@mcp.tool(annotations=READ_ONLY, description=(
    "List every learner with their alias, current grade, home language and number of evidence rows. "
    "Call this first to get valid learner ids. Learners have aliases, never names."))
def list_learners() -> dict:
    return _call(tools.list_learners)


@mcp.tool(annotations=READ_ONLY, description=(
    "Return a learner's evidence (quiz items, assignments, projects, observations, attendance) grouped by "
    "period, oldest first, keeping the most recent `limit` rows. Filter by `since_year` or `concept_id` to "
    "read the evidence behind a pattern. Returns the learner row, periods with items, and counts."))
def get_learner_timeline(learner_id: str, since_year: int | None = None, concept_id: str | None = None,
                         limit: int = 200) -> dict:
    return _call(tools.get_learner_timeline, learner_id=learner_id, since_year=since_year,
                 concept_id=concept_id, limit=limit)


@mcp.tool(annotations=WRITE_IDEMPOTENT, description=(
    "Store one evidence row for a learner, citing where it came from in `source_ref`. Call this when "
    "ingesting a document; scores are 0 to 1 and raw_text may be in any language. Unknown concept or skill "
    "ids are kept as needs_review, and a repeated source_ref returns the existing id with a warning. "
    "Returns evidence_id, status and warnings."))
def record_evidence(learner_id: str, kind: str, year: int, term: int, grade: int, source_ref: str,
                    concept_id: str | None = None, skill_id: str | None = None, score: float | None = None,
                    absent_days: int | None = None, raw_text: str | None = None, language: str = "en",
                    teacher_id: str | None = None, unit_id: str | None = None,
                    logged_late: bool = False) -> dict:
    return _call(tools.record_evidence, learner_id=learner_id, kind=kind, year=year, term=term, grade=grade,
                 source_ref=source_ref, concept_id=concept_id, skill_id=skill_id, score=score,
                 absent_days=absent_days, raw_text=raw_text, language=language, teacher_id=teacher_id,
                 unit_id=unit_id, logged_late=logged_late)


@mcp.tool(annotations=READ_ONLY, description=(
    "Find strengths (mean above 0.8) and struggles (mean below 0.5) that held for at least `min_periods` "
    "periods with data (3 or more), by strand, cross-subject skill and concept. Call this to see where to "
    "look before tracing a root. Returns patterns with periods, means, evidence ids and the concepts behind "
    "each one, plus data gaps."))
def find_patterns(learner_id: str, min_periods: int = 3) -> dict:
    return _call(tools.find_patterns, learner_id=learner_id, min_periods=min_periods)


@mcp.tool(annotations=READ_ONLY, description=(
    "Walk the curriculum's prerequisite links back from a struggling concept to the deepest low "
    "prerequisite, the likely root. Call this after find_patterns reports a struggle. Returns the path, the "
    "root with its evidence, absences in the term it was taught, concepts with no evidence (unknowns, never "
    "guessed), alternatives, confidence and a plain reason."))
def trace_root(learner_id: str, concept_id: str) -> dict:
    return _call(tools.trace_root, learner_id=learner_id, concept_id=concept_id)


@mcp.tool(annotations=READ_ONLY, description=(
    "Compare this learner's scores before and after each teaching unit, grouped by teaching approach. Call "
    "this to suggest an approach that has helped this learner before. It describes approaches, never rates "
    "teachers. Returns improved and not-improved counts, mean gain and each instance with evidence ids."))
def what_worked(learner_id: str) -> dict:
    return _call(tools.what_worked, learner_id=learner_id)


@mcp.tool(annotations=READ_ONLY, description=(
    "List a learner's findings and what a teacher decided about each: status (proposed, approved, edited, "
    "rejected), the deciding teacher's name, time and note. Call this to check whether a proposal has been "
    "reviewed before drafting a summary; filter by `finding_ids` or `status`. Returns findings with their "
    "statement, cited evidence ids and confidence."))
def get_findings(learner_id: str, finding_ids: list[str] | None = None, status: str | None = None) -> dict:
    return _call(tools.get_findings, learner_id=learner_id, finding_ids=finding_ids, status=status)


@mcp.tool(annotations=READ_ONLY, description=(
    "List a learner's summary drafts and what a teacher decided about each: status (draft, approved, "
    "rejected), the deciding teacher's name and time. Call this to see whether a summary may be shared; "
    "filter by `summary_ids` or `status`. Returns summaries with audience, language, text and the findings "
    "they were built from."))
def get_summaries(learner_id: str, summary_ids: list[str] | None = None, status: str | None = None) -> dict:
    return _call(tools.get_summaries, learner_id=learner_id, summary_ids=summary_ids, status=status)


@mcp.tool(annotations=WRITE, description=(
    "Propose a finding (root_cause, strength, struggle or what_worked) for a teacher to review. It must cite "
    "evidence ids of this learner (at least 2 for root_cause, strength and struggle) and describe a pattern, "
    "never label the child or compare with classmates. Returns finding_id with status 'proposed'; only a "
    "named teacher can approve it."))
def propose_finding(learner_id: str, kind: str, statement: str, evidence_ids: list[str],
                    concept_ids: list[str] | None = None, path: list[str] | None = None,
                    confidence: float = 0.5) -> dict:
    return _call(tools.propose_finding, learner_id=learner_id, kind=kind, statement=statement,
                 evidence_ids=evidence_ids, concept_ids=concept_ids, path=path, confidence=confidence)


@mcp.tool(annotations=WRITE, description=(
    "Draft a plain-language summary for a 'teacher_handover' or 'guardian' audience from findings a teacher "
    "has already approved. Call this only after approval; unapproved findings are refused. Returns "
    "summary_id with status 'draft', which needs its own teacher approval before sharing."))
def draft_summary(learner_id: str, finding_ids: list[str], audience: str, language: str, text: str) -> dict:
    return _call(tools.draft_summary, learner_id=learner_id, finding_ids=finding_ids, audience=audience,
                 language=language, text=text)


@mcp.tool(annotations=READ_ONLY, description=(
    "List the questions asked about holes in a learner's record and what a teacher answered: status (open, "
    "provided, no_record), the answering teacher's name and time, and the text or file they supplied. Call "
    "this before request_record so a teacher is never asked the same thing twice; filter by `request_ids` or "
    "`status`."))
def get_record_requests(learner_id: str, request_ids: list[str] | None = None, status: str | None = None) -> dict:
    return _call(tools.get_record_requests, learner_id=learner_id, request_ids=request_ids, status=status)


@mcp.tool(annotations=WRITE_IDEMPOTENT, description=(
    "Ask a teacher for a record of one topic (`concept_id`) the learner has no scored evidence for, when "
    "trace_root reports that the missing topic stops it from telling where a difficulty began. Give a short "
    "plain `question` and the struggling topic in `about_concept_id`. Refused when records already exist or a "
    "teacher has already answered; an open request is returned as is. Returns request_id with status 'open'; "
    "only a named teacher can answer it."))
def request_record(learner_id: str, concept_id: str, question: str, about_concept_id: str | None = None) -> dict:
    return _call(tools.request_record, learner_id=learner_id, concept_id=concept_id, question=question,
                 about_concept_id=about_concept_id)


def main(argv: list[str] | None = None) -> None:
    """Run over stdio, or over streamable HTTP on 127.0.0.1:<ATHAR_MCP_PORT> with --http."""
    parser = argparse.ArgumentParser(prog="athar.server", description="Athar MCP server")
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    args = parser.parse_args(argv)
    if args.http:
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = get_settings().mcp_port
        mcp.run("streamable-http")
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
