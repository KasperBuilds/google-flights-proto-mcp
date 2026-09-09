"""Retry routes whose prior exact itinerary did not pass browser checks."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastmcp import Client

from google_flights_proto_mcp.server import mcp


async def main() -> None:
    path = Path(__file__).resolve().parents[1] / "outputs" / "semester_search.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    async with Client(mcp, timeout=120) as client:
        for entry in payload["results"]:
            shortlist = entry["result"].get("shortlist") or []
            verified = bool(shortlist and shortlist[0].get("verification", {}).get("verified"))
            if verified or not shortlist:
                continue
            print(f"Retry {entry['weekend']} LIS-{entry['destination']}", flush=True)
            response = await client.call_tool(
                "search_and_verify_top", {"request": entry["request"]}
            )
            entry["result"] = response.data
            current = entry["result"].get("shortlist") or []
            status = bool(current and current[0].get("verification", {}).get("verified"))
            print(f"  -> verified={status}", flush=True)
    payload["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
