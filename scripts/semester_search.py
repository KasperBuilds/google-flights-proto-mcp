"""Run the Lisbon autumn 2026 shortlist through the MCP tool interface."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastmcp import Client

from google_flights_proto_mcp.server import mcp

WINDOWS = [
    ("19–21 Sep", "2026-09-19", "2026-09-21", 6, 16, ["FNC", "NCE", "MXP"]),
    ("25–28 Sep", "2026-09-25", "2026-09-28", 16, 16, ["FNC", "BCN", "NCE"]),
    ("2–5 Oct", "2026-10-02", "2026-10-05", 16, 16, ["NCE", "MXP", "PRG"]),
    ("9–12 Oct", "2026-10-09", "2026-10-12", 16, 16, ["BGY", "NCE", "BER"]),
    ("16–19 Oct", "2026-10-16", "2026-10-19", 20, 16, ["BCN", "MAD", "STN"]),
    ("23–25 Oct", "2026-10-23", "2026-10-25", 16, 14, ["DUB", "NCE", "BRU"]),
    ("30 Oct–2 Nov", "2026-10-30", "2026-11-02", 20, 16, ["DUB", "EDI", "RAK"]),
    ("6–9 Nov", "2026-11-06", "2026-11-09", 16, 16, ["RAK", "FCO", "PRG"]),
    ("20–23 Nov", "2026-11-20", "2026-11-23", 16, 16, ["RAK", "BUD", "VIE"]),
    ("27–30 Nov", "2026-11-27", "2026-11-30", 16, 16, ["KEF", "HEL", "TOS"]),
    ("4–7 Dec", "2026-12-04", "2026-12-07", 16, 16, ["KEF", "HEL", "TOS"]),
    ("11–14 Dec", "2026-12-11", "2026-12-14", 11, 14, ["TOS", "KEF", "CPH"]),
    ("17–23 Dec", "2026-12-17", "2026-12-23", 17, 12, ["TOS", "RVN", "KEF"]),
]


async def main() -> None:
    results: list[dict] = []
    async with Client(mcp, timeout=120) as client:
        for weekend, departure, return_date, out_hour, return_hour, destinations in WINDOWS:
            for destination in destinations:
                request = {
                    "origin": "LIS",
                    "destination": destination,
                    "departure_date": departure,
                    "return_date": return_date,
                    "adults": 1,
                    "cabin": "ECONOMY",
                    "max_stops": 1,
                    "outbound_earliest_departure_hour": out_hour,
                    "return_earliest_departure_hour": return_hour,
                    "hide_separate_and_self_transfer": True,
                    "currency": "EUR",
                    "language": "en-GB",
                    "country": "PT",
                    "max_outbounds_to_expand": 3,
                    "max_return_options_per_outbound": 6,
                    "top_n": 1,
                }
                print(f"[{datetime.now():%H:%M:%S}] {weekend} LIS-{destination}", flush=True)
                try:
                    response = await client.call_tool("search_and_verify_top", {"request": request})
                    payload = response.data
                except Exception as exc:
                    payload = {"success": False, "error": str(exc), "shortlist": []}
                results.append(
                    {
                        "weekend": weekend,
                        "departure_date": departure,
                        "return_date": return_date,
                        "destination": destination,
                        "request": request,
                        "result": payload,
                    }
                )
                status = "ok" if payload.get("success") else payload.get("error", "failed")
                print(f"  -> {status}", flush=True)

    output = Path(__file__).resolve().parents[1] / "outputs" / "semester_search.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved {output}")


if __name__ == "__main__":
    asyncio.run(main())
