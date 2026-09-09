import pytest
from fastmcp import Client

from google_flights_proto_mcp.server import mcp


@pytest.mark.asyncio
async def test_mcp_lists_pipeline_tools_and_builds_url() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == {
            "build_protobuf_search_url",
            "discover_and_rank_complete",
            "search_and_verify_top",
        }
        result = await client.call_tool(
            "build_protobuf_search_url",
            {
                "request": {
                    "origin": "LIS",
                    "destination": "FNC",
                    "departure_date": "2026-09-19",
                    "return_date": "2026-09-21",
                    "adults": 2,
                    "max_stops": 0,
                }
            },
        )
        data = result.data
        assert data["success"] is True
        assert "/travel/flights/search?tfs=" in data["search_url"]
