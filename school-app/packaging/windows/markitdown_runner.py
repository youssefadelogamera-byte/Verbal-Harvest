r"""Start the borrowed document reader (Microsoft's markitdown MCP server) from the package.

It needs a newer `mcp` library than the app does, so it has a library folder of its own:
`runtime\markitdown`. This file is started with `python -S`, which leaves the app's libraries
out, and then adds that one folder. Nothing is fetched from the internet.
"""
import runpy
import site
import sys
from pathlib import Path

LIBRARIES = Path(__file__).resolve().parents[2] / "runtime" / "markitdown"

if __name__ == "__main__":
    site.addsitedir(str(LIBRARIES))  # also reads the .pth files that pywin32 needs
    sys.argv = ["markitdown-mcp"]
    runpy.run_module("markitdown_mcp", run_name="__main__")
