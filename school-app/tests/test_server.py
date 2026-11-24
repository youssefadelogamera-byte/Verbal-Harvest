import json
import os
import sys
from pathlib import Path

from conftest import FIXTURE_PACKS
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from athar import db, server

TOOL_NAMES = {"list_learners", "get_learner_timeline", "record_evidence", "find_patterns", "trace_root",
              "what_worked", "propose_finding", "draft_summary", "get_findings", "get_summaries",
              "request_record", "get_record_requests"}
READ_ONLY = {"list_learners", "get_learner_timeline", "find_patterns", "trace_root", "what_worked",
             "get_findings", "get_summaries", "get_record_requests"}
ROOT = Path(__file__).resolve().parents[1]


def _payload(result) -> dict:
    assert not result.isError, result.content
    return json.loads(result.content[0].text)


async def test_stdio_server_lists_and_calls_tools(db_path):
    env = {**os.environ, "ATHAR_DB": str(db_path), "ATHAR_PACKS": str(FIXTURE_PACKS),
           "ATHAR_ACTOR": "agent", "ATHAR_RUN_ID": "run_srv", "PYTHONIOENCODING": "utf-8"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "athar.server"], env=env,
                                   cwd=str(ROOT))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listed = (await session.list_tools()).tools
        assert {t.name for t in listed} == TOOL_NAMES
        for tool in listed:
            assert not {"db_path", "_actor", "_run_id"} & set(tool.inputSchema.get("properties", {}))
            assert tool.description and tool.annotations.readOnlyHint == (tool.name in READ_ONLY)

        learners = _payload(await session.call_tool("list_learners", {}))["learners"]
        assert len(learners) == 5

        recorded = _payload(await session.call_tool("record_evidence", {
            "learner_id": "lrn_d", "kind": "observation", "year": 2023, "term": 2, "grade": 4,
            "source_ref": "note:2023-T2-amharic", "concept_id": "fractions",
            "raw_text": "ክፍልፋዮችን መረዳት ጀምሯል", "language": "am"}))
        assert recorded["status"] == "active"

        refused = await session.call_tool("propose_finding", {
            "learner_id": "lrn_a", "kind": "struggle", "statement": "Ratio items low.",
            "evidence_ids": ["evd_b01", "evd_b02"]})
        assert refused.isError

    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT raw_text FROM evidence WHERE id = ?", (recorded["evidence_id"],))
        audit_rows = db.rows(conn, "SELECT tool, actor, run_id, ok FROM audit_log ORDER BY id")
    assert row["raw_text"] == "ክፍልፋዮችን መረዳት ጀምሯል"
    assert [(r["tool"], r["ok"]) for r in audit_rows] == [
        ("list_learners", 1), ("record_evidence", 1), ("propose_finding", 0)]
    assert {(r["actor"], r["run_id"]) for r in audit_rows} == {("agent", "run_srv")}


def test_in_process_calls_default_to_mcp_client(db_path):
    assert len(server.list_learners()["learners"]) == 5
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT actor, run_id FROM audit_log ORDER BY id DESC LIMIT 1")
    assert (row["actor"], row["run_id"]) == ("mcp-client", None)
