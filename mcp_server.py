"""
Spotter MCP Server — screen context for AI tools.

Add to Claude Code config (~/.claude.json or project .mcp.json):

    {
        "mcpServers": {
            "spotter": {
                "command": "/path/to/venv/bin/python",
                "args": ["/path/to/spotter/mcp_server.py"]
            }
        }
    }
"""

import logging

from fastmcp import FastMCP
from mcp.types import ImageContent

import core

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

mcp = FastMCP("spotter")


@mcp.tool
def see_screen() -> dict:
    """
    See what's on the user's screen right now.

    Takes a screenshot, analyzes it with a local vision model,
    and returns a text description of what the user is doing,
    what app they're in, and what they might be stuck on.

    Everything runs locally. The screenshot is deleted after analysis.
    """
    try:
        return core.get_screen_context()
    except RuntimeError as e:
        return {"error": str(e)}


@mcp.tool
def get_screenshot() -> list:
    """
    Get a screenshot of the user's screen as a PNG image.

    Returns the raw screenshot. Use see_screen instead if you
    just need to know what the user is doing -- it's faster and
    doesn't send pixel data.
    """
    try:
        result = core.get_screenshot_bytes()
        return [
            ImageContent(
                type="image",
                data=result["image_base64"],
                mimeType="image/png",
            )
        ]
    except RuntimeError as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
