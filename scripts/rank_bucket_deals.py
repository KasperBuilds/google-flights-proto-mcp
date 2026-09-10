"""Rank bucket-list fares against each route's semester-window median.

The baseline is deliberately local and auditable: the median Google Flights
search-page quote for the same airport across the configured travel windows.
It is not Google's historical "typical price" signal and is not checkout
verification.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quotes", type=Path, default=ROOT / "outputs" / "bucket_quotes.json")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "bucket_list_2026.json")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "bucket_deals.json")
    parser.add_argument("--csv", type=Path)
    return parser.parse_args()


def _rating(ratio: float, thresholds: dict[str, float]) -> str:
    if ratio <= thresholds["exceptional_max_ratio"]:
        return "Exceptional vs semester median"
    if ratio <= thresholds["unusually_cheap_max_ratio"]:
        return "Unusually cheap vs semester median"
    if ratio <= thresholds["good_max_ratio"]:
        return "Good vs semester median"
    if ratio <= thresholds["normal_max_ratio"]:
        return "Around semester median"
    return "Above semester median"


def _flatten(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for weekend_index, weekend in enumerate(payload["weekends"]):
        for quote in weekend["cheapest"]:
            records.append(
                {
                    **quote,
                    "weekend": weekend["label"],
                    "weekend_index": weekend_index,
                    "departure_date": weekend["departure_date"],
                    "return_date": weekend["return_date"],
                }
            )
    return records


def rank(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    records = _flatten(payload)
    by_airport: dict[str, list[float]] = {}
    for record in records:
        code = record["destination"]["code"]
        by_airport.setdefault(code, []).append(float(record["google_total"]))

    medians = {code: statistics.median(prices) for code, prices in by_airport.items()}
    thresholds = config["deal_thresholds"]
    category_by_airport: dict[str, list[str]] = {}
    preferred_weekends_by_category: dict[str, set[str]] = {}
    airport_order: dict[str, int] = {}
    for category in config["categories"]:
        preferred_weekends_by_category[category["name"]] = set(
            category.get("preferred_weekends", [])
        )
        for airport_index, airport in enumerate(category["airports"]):
            category_by_airport.setdefault(airport, []).append(category["name"])
            airport_order[airport] = min(airport_order.get(airport, 999), airport_index)

    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    enriched = []
    for record in records:
        code = record["destination"]["code"]
        median = medians[code]
        ratio = float(record["google_total"]) / median
        item = {
            **record,
            "categories": category_by_airport.get(code, []),
            "semester_window_median": median,
            "observed_windows": len(by_airport[code]),
            "deal_ratio": ratio,
            "percent_below_median": 1 - ratio,
            "savings_vs_median": median - float(record["google_total"]),
            "deal_rating": _rating(ratio, thresholds),
            "is_deal": ratio <= thresholds["good_max_ratio"],
        }
        item["preferred_timing_categories"] = [
            category
            for category in item["categories"]
            if item["weekend"] in preferred_weekends_by_category[category]
        ]
        enriched.append(item)
        indexed[(item["weekend"], code)] = item

    coverage_plan = []
    missing_coverage = []
    for choice in config["coverage_plan"]:
        item = indexed.get((choice["weekend"], choice["airport"]))
        if item is None:
            missing_coverage.append(choice)
            continue
        coverage_plan.append({**item, "selection_reason": choice["reason"]})

    best_by_category = []
    for category in config["categories"]:
        category_airport_priority = {code: index for index, code in enumerate(category["airports"])}
        candidates = [
            item for item in enriched if item["destination"]["code"] in category["airports"]
        ]
        if not candidates:
            continue
        preferred = category.get("preferred_weekends")
        preferred_candidates = (
            [item for item in candidates if item["weekend"] in preferred]
            if preferred
            else candidates
        )
        pool = preferred_candidates or candidates
        best = min(
            pool,
            key=lambda item: (
                item["deal_ratio"],
                item["google_total"],
                item["outbound_stops"],
                category_airport_priority[item["destination"]["code"]],
            ),
        )
        best_any = min(
            candidates,
            key=lambda item: (
                item["deal_ratio"],
                item["google_total"],
                item["outbound_stops"],
                category_airport_priority[item["destination"]["code"]],
            ),
        )
        best_by_category.append(
            {
                **best,
                "bucket_category": category["name"],
                "timing_scope": "Preferred timing" if preferred else "Any weekend",
                "better_flexible_option": (
                    {
                        "weekend": best_any["weekend"],
                        "airport": best_any["destination"]["code"],
                        "google_total": best_any["google_total"],
                        "percent_below_median": best_any["percent_below_median"],
                        "google_search_url": best_any["google_search_url"],
                    }
                    if best_any["deal_ratio"] < best["deal_ratio"]
                    else None
                ),
            }
        )

    weekend_options = []
    max_return_price = float(config.get("max_return_price", 250))
    website_initial_options = int(config.get("website_initial_options", 3))
    sheet_options_per_weekend = int(config.get("sheet_options_per_weekend", 3))
    for weekend in payload["weekends"]:
        candidates = [
            item
            for item in enriched
            if item["weekend"] == weekend["label"]
            and float(item["google_total"]) <= max_return_price
        ]

        def option_key(item: dict[str, Any]) -> tuple[float, ...]:
            # Always prefer a price below the route median. Within that group,
            # give the user's requested seasonal timing a modest boost without
            # allowing it to turn an above-median fare into a supposed deal.
            timing_bonus = 0.16 if item["preferred_timing_categories"] else 0
            return (
                0 if item["is_deal"] else (1 if item["deal_ratio"] < 1 else 2),
                item["deal_ratio"] - timing_bonus,
                item["google_total"],
                item["outbound_stops"],
                airport_order.get(item["destination"]["code"], 999),
            )

        selected = sorted(candidates, key=option_key)

        for option, item in enumerate(selected, 1):
            if item["is_deal"]:
                action = "DEAL"
            elif item["deal_ratio"] < 1:
                action = "BELOW MEDIAN"
            else:
                action = "HOLD / WATCH"
            weekend_options.append({**item, "option": option, "action": action})

    return {
        "generated_at": payload["generated_at"],
        "method": (
            "Each fare is compared with the median Google Flights search-page quote for "
            "that exact destination airport across the observed semester travel windows. "
            f"Only return quotes at or below €{max_return_price:.0f} are eligible for the "
            "weekend results. This is not Google's historical typical-fare signal or "
            "checkout verification."
        ),
        "origin": payload["origin"],
        "passengers": payload["filters"]["adults"],
        "max_return_price": max_return_price,
        "website_initial_options": website_initial_options,
        "sheet_options_per_weekend": sheet_options_per_weekend,
        "weekends": [
            {
                "label": weekend["label"],
                "departure_date": weekend["departure_date"],
                "return_date": weekend["return_date"],
                "availability_note": weekend.get("availability_note"),
            }
            for weekend in payload["weekends"]
        ],
        "deal_thresholds": thresholds,
        "coverage_summary": {
            "categories_total": len(config["categories"]),
            "categories_covered": len(
                {category for item in coverage_plan for category in item["categories"]}
            ),
            "deal_rows": sum(item["is_deal"] for item in coverage_plan),
            "hold_rows": sum(not item["is_deal"] for item in coverage_plan),
            "missing_rows": len(missing_coverage),
        },
        "coverage_plan": coverage_plan,
        "best_by_category": best_by_category,
        "weekend_options": weekend_options,
    }


def _write_csv(path: Path, payload: dict[str, Any]) -> None:
    fields = [
        "section",
        "weekend",
        "bucket_category",
        "destination",
        "airport",
        "google_total",
        "semester_window_median",
        "percent_below_median",
        "deal_rating",
        "outbound_example",
        "outbound_stops",
        "google_search_url",
        "checked_at",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for section, rows in (
            ("Coverage plan", payload["coverage_plan"]),
            ("Best by bucket", payload["best_by_category"]),
        ):
            for item in rows:
                writer.writerow(
                    {
                        "section": section,
                        "weekend": item["weekend"],
                        "bucket_category": item.get(
                            "bucket_category", ", ".join(item["categories"])
                        ),
                        "destination": item["destination"]["name"],
                        "airport": item["destination"]["code"],
                        "google_total": item["google_total"],
                        "semester_window_median": item["semester_window_median"],
                        "percent_below_median": item["percent_below_median"],
                        "deal_rating": item["deal_rating"],
                        "outbound_example": item["outbound_example"],
                        "outbound_stops": item["outbound_stops"],
                        "google_search_url": item["google_search_url"],
                        "checked_at": item["checked_at"],
                        "notes": item.get("selection_reason", item.get("timing_scope", "")),
                    }
                )


def main() -> None:
    args = _arguments()
    payload = json.loads(args.quotes.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    ranked = rank(payload, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ranked, indent=2), encoding="utf-8")
    csv_path = args.csv or args.output.with_suffix(".csv")
    _write_csv(csv_path, ranked)
    print(f"Saved {args.output}")
    print(f"Saved {csv_path}")


if __name__ == "__main__":
    main()
