"""FastMCP tools and STDIO/HTTP entry points."""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

from .models import SearchRequest
from .pipeline import discover_complete_itineraries, search_rank_verify
from .proto import build_search_url

mcp = FastMCP("Google Flights Protobuf MCP")


@mcp.tool(
    annotations={"title": "Build Google Flights Protobuf URL", "readOnlyHint": True},
)
def build_protobuf_search_url(request: SearchRequest) -> dict[str, Any]:
    """Build a real ``tfs`` protobuf search URL without making a network request."""
    return {
        "success": True,
        "search_url": build_search_url(request),
        "exact_itinerary": False,
        "note": "Search URLs choose flights; exact results use /booking?tfs= links.",
    }


@mcp.tool(
    annotations={"title": "Discover and Rank Complete Itineraries", "readOnlyHint": True},
)
def discover_and_rank_complete(request: SearchRequest) -> dict[str, Any]:
    """Use protobuf+HTTP to pair full itineraries, rank them, and return top 1-3."""
    try:
        return discover_complete_itineraries(request)
    except Exception as exc:  # stable MCP envelope; server logs still retain tool errors
        return {"success": False, "error": str(exc), "shortlist": []}


@mcp.tool(
    annotations={"title": "Search and Verify Top Itineraries", "readOnlyHint": True},
)
def search_and_verify_top(request: SearchRequest) -> dict[str, Any]:
    """Run protobuf → HTTP → pairing → ranking → top 1-3 → Playwright verification."""
    try:
        return search_rank_verify(request)
    except Exception as exc:
        return {"success": False, "error": str(exc), "shortlist": []}


def run() -> None:
    """Run the standalone MCP over STDIO."""
    mcp.run(transport="stdio")


def run_http() -> None:
    """Run streamable HTTP MCP; clients must accept JSON and event streams."""
    mcp.run(
        transport="http",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8010")),
    )


if __name__ == "__main__":
    run()
