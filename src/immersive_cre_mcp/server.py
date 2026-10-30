"""Entry point: immersive Cyber Ranges MCP server."""
from __future__ import annotations

import argparse
import logging
import os

from . import tools  # noqa: F401 - registers tools
from .app import mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="immersive Cyber Ranges MCP server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http", "sse"], default="stdio")
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
