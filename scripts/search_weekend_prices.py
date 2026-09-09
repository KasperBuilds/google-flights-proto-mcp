"""Scan a destination universe using Google Flights protobuf search URLs.

This intentionally does not use the MCP server and does not claim checkout
verification.  Each airport/weekend gets one Google Flights search request;
the lowest total displayed in the embedded search results is retained.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from google_flights_proto_mcp.discovery import discover_directions
from google_flights_proto_mcp.models import SearchRequest
from google_flights_proto_mcp.proto import build_search_url


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "semester_2026.json",
    )
    parser.add_argument("--weekend", action="append", help="Only scan this weekend label")
    parser.add_argument("--destinations", help="Comma-separated IATA override")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-price", type=int)
    parser.add_argument("--max-stops", type=int, choices=(0, 1, 2), default=1)
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--airlines", help="Comma-separated IATA airline filter")
    parser.add_argument(
        "--retry-errors-from",
        type=Path,
        help="Retry only blocked/error queries from a previous scanner JSON and merge them",
    )
    parser.add_argument("--retry-passes", type=int, default=1)
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=0,
        help="Linear backoff between retry passes (delay is multiplied by pass index)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "outputs" / "weekend_prices.json",
    )
    parser.add_argument("--csv", type=Path)
    return parser.parse_args()


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("weekends") or not payload.get("destinations"):
        raise ValueError("config must contain non-empty weekends and destinations")
    return payload


def _direction_summary(direction: Any) -> str:
    return " / ".join(
        f"{leg.airline}{leg.flight_number} {leg.origin}-{leg.destination} "
        f"{leg.departure:%H:%M}-{leg.arrival:%H:%M}"
        for leg in direction.legs
    )


def _scan_one(
    *,
    origin: str,
    destination: dict[str, str],
    weekend: dict[str, Any],
    adults: int,
    max_stops: int,
    max_price: int | None,
    airlines: list[str],
    currency: str,
    language: str,
    country: str,
) -> dict[str, Any]:
    code = destination["code"].upper()
    request = SearchRequest(
        origin=origin,
        destination=code,
        departure_date=weekend["departure_date"],
        return_date=weekend["return_date"],
        adults=adults,
        cabin="ECONOMY",
        max_stops=max_stops,
        airlines=airlines,
        outbound_earliest_departure_hour=weekend.get("outbound_earliest_hour"),
        outbound_latest_departure_hour=weekend.get("outbound_latest_hour"),
        return_earliest_departure_hour=weekend.get("return_earliest_hour"),
        return_latest_departure_hour=weekend.get("return_latest_hour"),
        max_price=max_price,
        hide_separate_and_self_transfer=True,
        currency=currency,
        language=language,
        country=country,
        top_n=1,
    )
    url = build_search_url(request)
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        directions = discover_directions(request)
    except Exception as exc:
        return {
            "status": "error",
            "destination": destination,
            "google_search_url": url,
            "checked_at": checked_at,
            "error": str(exc),
        }

    # Google occasionally returns a city-area alternate airport. This scanner
    # promises exact airport queries, so silently substituting another airport
    # is not allowed.
    candidates = [
        direction
        for direction in directions
        if direction.price is not None and direction.legs and direction.legs[-1].destination == code
    ]
    if not candidates:
        return {
            "status": "no_result",
            "destination": destination,
            "google_search_url": url,
            "checked_at": checked_at,
        }

    best = min(
        candidates,
        key=lambda direction: (
            direction.price,
            direction.stops,
            direction.duration_minutes,
            direction.legs[0].departure,
        ),
    )
    return {
        "status": "google_quote",
        "destination": destination,
        "google_total": best.price,
        "currency": best.currency or currency,
        "passengers": adults,
        "price_scope": (
            "Google Flights search-page round-trip total for all passengers; "
            "not provider-checkout-verified"
        ),
        "outbound_example": _direction_summary(best),
        "outbound_stops": best.stops,
        "outbound_duration_minutes": best.duration_minutes,
        "google_search_url": url,
        "checked_at": checked_at,
    }


def scan(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    selected_weekends = set(args.weekend or [])
    weekends = [
        weekend
        for weekend in config["weekends"]
        if not selected_weekends or weekend["label"] in selected_weekends
    ]
    if selected_weekends - {item["label"] for item in weekends}:
        missing = ", ".join(sorted(selected_weekends - {item["label"] for item in weekends}))
        raise ValueError(f"unknown weekend label(s): {missing}")

    if args.destinations:
        names = {item["code"].upper(): item["name"] for item in config["destinations"]}
        destinations = [
            {"code": code.strip().upper(), "name": names.get(code.strip().upper(), code.strip())}
            for code in args.destinations.split(",")
            if code.strip()
        ]
    else:
        destinations = config["destinations"]

    airlines = [code.strip().upper() for code in (args.airlines or "").split(",") if code]
    output_weekends = []
    for weekend in weekends:
        print(
            f"[{datetime.now():%H:%M:%S}] {weekend['label']}: {len(destinations)} destinations",
            flush=True,
        )
        results = []
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as executor:
            futures = [
                executor.submit(
                    _scan_one,
                    origin=config.get("origin", "LIS"),
                    destination=destination,
                    weekend=weekend,
                    adults=args.adults,
                    max_stops=args.max_stops,
                    max_price=args.max_price,
                    airlines=airlines,
                    currency=config.get("currency", "EUR"),
                    language=config.get("language", "en"),
                    country=config.get("country", "PT"),
                )
                for destination in destinations
            ]
            for future in as_completed(futures):
                results.append(future.result())

        quotes = sorted(
            (result for result in results if result["status"] == "google_quote"),
            key=lambda result: (
                result["google_total"],
                result["outbound_stops"],
                result["outbound_duration_minutes"],
            ),
        )
        for rank, quote in enumerate(quotes[: max(1, args.top)], 1):
            quote["rank"] = rank
        output_weekends.append(
            {
                **weekend,
                "cheapest": quotes[: max(1, args.top)],
                "quoted_destinations": len(quotes),
                "no_result_destinations": sum(r["status"] == "no_result" for r in results),
                "errors": [r for r in results if r["status"] == "error"],
            }
        )

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": (
            "One protobuf Google Flights /search URL and one fast HTTP request per "
            "airport/weekend. Prices are Google search-page quotes, not checkout verification."
        ),
        "origin": config.get("origin", "LIS"),
        "destination_universe_size": len(destinations),
        "top_n": max(1, args.top),
        "request_count": len(destinations) * len(weekends),
        "filters": {
            "adults": args.adults,
            "max_stops": args.max_stops,
            "max_price": args.max_price,
            "airlines": airlines,
        },
        "weekends": output_weekends,
    }


def retry_errors(
    payload: dict[str, Any], config: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    """Retry transient failures without repeating successful destination searches."""
    config_weekends = {weekend["label"]: weekend for weekend in config["weekends"]}
    filters = payload["filters"]
    top_n = int(payload.get("top_n", args.top))
    attempts_made = 0
    for retry_pass in range(1, max(1, args.retry_passes) + 1):
        pending = sum(len(weekend.get("errors", [])) for weekend in payload["weekends"])
        if not pending:
            break
        if retry_pass > 1 and args.retry_delay_seconds > 0:
            delay = args.retry_delay_seconds * (retry_pass - 1)
            print(f"Waiting {delay:g}s before retry pass {retry_pass}", flush=True)
            time.sleep(delay)
        print(f"Retry pass {retry_pass}: {pending} blocked/error queries", flush=True)
        for weekend_output in payload["weekends"]:
            previous_errors = weekend_output.get("errors", [])
            if not previous_errors:
                continue
            weekend = config_weekends[weekend_output["label"]]
            destinations = [error["destination"] for error in previous_errors]
            retried = []
            with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as executor:
                futures = [
                    executor.submit(
                        _scan_one,
                        origin=payload["origin"],
                        destination=destination,
                        weekend=weekend,
                        adults=filters["adults"],
                        max_stops=filters["max_stops"],
                        max_price=filters.get("max_price"),
                        airlines=filters.get("airlines", []),
                        currency=config.get("currency", "EUR"),
                        language=config.get("language", "en"),
                        country=config.get("country", "PT"),
                    )
                    for destination in destinations
                ]
                for future in as_completed(futures):
                    retried.append(future.result())
            attempts_made += len(retried)

            recovered = [item for item in retried if item["status"] == "google_quote"]
            existing = {item["destination"]["code"]: item for item in weekend_output["cheapest"]}
            for item in recovered:
                existing[item["destination"]["code"]] = item
            cheapest = sorted(
                existing.values(),
                key=lambda item: (
                    item["google_total"],
                    item["outbound_stops"],
                    item["outbound_duration_minutes"],
                ),
            )[:top_n]
            for rank, item in enumerate(cheapest, 1):
                item["rank"] = rank
            weekend_output["cheapest"] = cheapest
            weekend_output["quoted_destinations"] += len(recovered)
            weekend_output["no_result_destinations"] += sum(
                item["status"] == "no_result" for item in retried
            )
            weekend_output["errors"] = [item for item in retried if item["status"] == "error"]

    payload["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    payload["retry_request_count"] = payload.get("retry_request_count", 0) + attempts_made
    return payload


def _write_csv(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "weekend",
        "rank",
        "destination",
        "airport",
        "google_total",
        "currency",
        "passengers",
        "outbound_example",
        "outbound_stops",
        "checked_at",
        "google_search_url",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for weekend in payload["weekends"]:
            for result in weekend["cheapest"]:
                writer.writerow(
                    {
                        "weekend": weekend["label"],
                        "rank": result["rank"],
                        "destination": result["destination"]["name"],
                        "airport": result["destination"]["code"],
                        "google_total": result["google_total"],
                        "currency": result["currency"],
                        "passengers": result["passengers"],
                        "outbound_example": result["outbound_example"],
                        "outbound_stops": result["outbound_stops"],
                        "checked_at": result["checked_at"],
                        "google_search_url": result["google_search_url"],
                    }
                )


def main() -> None:
    args = _arguments()
    config = _load_config(args.config)
    if args.retry_errors_from:
        payload = retry_errors(
            json.loads(args.retry_errors_from.read_text(encoding="utf-8")), config, args
        )
    else:
        payload = scan(config, args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    csv_path = args.csv or args.output.with_suffix(".csv")
    _write_csv(csv_path, payload)
    print(f"Saved {args.output}")
    print(f"Saved {csv_path}")


if __name__ == "__main__":
    main()
