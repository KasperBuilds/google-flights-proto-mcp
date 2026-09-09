"""Replace date-window routes for which Google returned no complete pair."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastmcp import Client

from google_flights_proto_mcp.server import mcp

REPLACEMENTS = {
    ("16–19 Oct", "STN"): "LHR",
    ("30 Oct–2 Nov", "EDI"): "LHR",
}


async def main() -> None:
    path = Path(__file__).resolve().parents[1] / "outputs" / "semester_search.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    async with Client(mcp, timeout=120) as client:
        for entry in payload["results"]:
            replacement = REPLACEMENTS.get((entry["weekend"], entry["destination"]))
            if not replacement:
                continue
            request = {**entry["request"], "destination": replacement}
            print(f"Replace {entry['weekend']} {entry['destination']} -> {replacement}")
            response = await client.call_tool("search_and_verify_top", {"request": request})
            entry["destination"] = replacement
            entry["request"] = request
            entry["result"] = response.data
            print(
                "  ->",
                bool(
                    response.data.get("shortlist")
                    and response.data["shortlist"][0]["verification"]["verified"]
                ),
            )
    payload["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
