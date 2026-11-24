"""MCP connections used by the agent.

Two servers:
- `athar`: our own server (src/athar/server.py), started over stdio. Every learner-data
  action the agent takes goes through it, so every action is in the audit log.
- `markitdown`: Microsoft's document-conversion server, which we did not write. It turns PDFs,
  Office files, images and HTML into markdown. Writing and maintaining those parsers ourselves
  would be weeks of work for a worse result.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Self

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..config import get_settings

MARKITDOWN_COMMAND = os.environ.get("ATHAR_MARKITDOWN_CMD", "uvx")
MARKITDOWN_ARGS = os.environ.get("ATHAR_MARKITDOWN_ARGS", "markitdown-mcp").split()


class ToolError(RuntimeError):
    """An MCP tool reported an error. The message is the tool's own explanation."""


def _payload(result) -> Any:
    """Return a tool result as plain data. Prefers structured content, falls back to JSON text."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        if set(structured) == {"result"}:
            return structured["result"]
        return structured
    text = "".join(getattr(block, "text", "") for block in result.content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


class McpHub:
    """Holds the open MCP sessions for one agent run."""

    def __init__(self, run_id: str, db_path: Path | None = None, with_converter: bool = False):
        self.run_id = run_id
        self.db_path = Path(db_path) if db_path else get_settings().db_path
        self.with_converter = with_converter
        self._stack = AsyncExitStack()
        self.server: ClientSession | None = None
        self._markitdown: ClientSession | None = None

    async def __aenter__(self) -> Self:
        env = {
            **os.environ,
            "ATHAR_DB": str(self.db_path),
            "ATHAR_ACTOR": "agent",
            "ATHAR_RUN_ID": self.run_id,
            "FASTMCP_LOG_LEVEL": "WARNING",
            "PYTHONIOENCODING": "utf-8",
        }
        params = StdioServerParameters(command=sys.executable, args=["-m", "athar.server"], env=env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.server = await self._stack.enter_async_context(ClientSession(read, write))
        await self.server.initialize()
        if self.with_converter:
            # Both servers are opened here, in the same task that will close them: anyio does
            # not allow a connection opened inside one task to be closed from another.
            try:
                params = StdioServerParameters(command=MARKITDOWN_COMMAND, args=MARKITDOWN_ARGS,
                                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                read, write = await self._stack.enter_async_context(stdio_client(params))
                self._markitdown = await self._stack.enter_async_context(ClientSession(read, write))
                await self._markitdown.initialize()
            except Exception:  # noqa: BLE001 - the agent recovers by reading text files directly
                self._markitdown = None
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()

    async def call(self, tool: str, **arguments) -> dict:
        """Call one of our own tools. Raises ToolError with the tool's message on failure."""
        arguments = {k: v for k, v in arguments.items() if v is not None}
        result = await self.server.call_tool(tool, arguments)
        if result.isError:
            raise ToolError("".join(getattr(b, "text", "") for b in result.content) or f"{tool} failed")
        return _payload(result)

    async def tool_specs(self, names: list[str]) -> list[dict]:
        """Tool definitions in the OpenAI function format, for the model to choose from."""
        listed = await self.server.list_tools()
        return [
            {"type": "function",
             "function": {"name": t.name, "description": t.description or "", "parameters": t.inputSchema}}
            for t in listed.tools if t.name in names
        ]

    async def convert_document(self, path: Path) -> str:
        """Convert a file to markdown with the borrowed markitdown server."""
        if self._markitdown is None:
            raise ToolError("the markitdown server is not available")
        result = await self._markitdown.call_tool("convert_to_markdown", {"uri": Path(path).resolve().as_uri()})
        text = "".join(getattr(b, "text", "") for b in result.content)
        if result.isError or not text.strip():
            raise ToolError(f"markitdown could not convert {Path(path).name}: {text[:200]}")
        return text
