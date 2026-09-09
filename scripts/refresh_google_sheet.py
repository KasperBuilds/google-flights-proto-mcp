"""Refresh the three-per-weekend Google Sheet from live search-page quotes.

The job intentionally publishes only after a complete scan and deterministic
rerank succeed. Google search-page quotes are not provider-checkout verification.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPREADSHEET_ID = "1lhZKd4rArPltnn5wynoIbZH9uw3HvoMcv3w1TMZosLU"
DEFAULT_SHEET_NAME = "3 per Weekend"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spreadsheet-id",
        default=os.environ.get("FLI_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID),
    )
    parser.add_argument(
        "--sheet-name",
        default=os.environ.get("FLI_SHEET_NAME", DEFAULT_SHEET_NAME),
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=(
            Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
            if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            else None
        ),
        help="Service-account JSON. Otherwise use Google Application Default Credentials.",
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retry-passes", type=int, default=6)
    parser.add_argument("--retry-delay-seconds", type=float, default=10)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("FLI_DATA_DIR", ROOT / "outputs")),
        help="Directory for the last successfully published JSON and CSV snapshots.",
    )
    parser.add_argument(
        "--no-sheet",
        action="store_true",
        help="Publish local snapshot files only; used by the Railway website.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan, rerank, and validate without updating Google Sheets.",
    )
    return parser.parse_args()


def _run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def _error_count(payload: dict[str, Any]) -> int:
    return sum(len(weekend.get("errors", [])) for weekend in payload["weekends"])


def _validate_ranked(payload: dict[str, Any], expected_weekends: list[str]) -> None:
    if payload.get("passengers") != 1:
        raise RuntimeError("Refusing to publish a scan that is not for exactly one adult")

    options = payload.get("weekend_options", [])
    counts = Counter(item["weekend"] for item in options)
    unknown = set(counts) - set(expected_weekends)
    if unknown:
        raise RuntimeError(f"Invalid weekend ranking labels: unknown={unknown}")

    ranks_by_weekend: dict[str, list[int]] = {weekend: [] for weekend in expected_weekends}

    seen: set[tuple[str, str]] = set()
    for item in options:
        key = (item["weekend"], item["destination"]["code"])
        if key in seen:
            raise RuntimeError(f"Duplicate weekend/airport ranking: {key}")
        seen.add(key)
        if not item.get("google_search_url", "").startswith(
            "https://www.google.com/travel/flights/search?tfs="
        ):
            raise RuntimeError(f"Invalid Google Flights search URL for {key}")
        if item.get("passengers") != 1:
            raise RuntimeError(f"Non-single-passenger quote found for {key}")
        if float(item["google_total"]) > float(payload.get("max_return_price", 250)):
            raise RuntimeError(f"Over-budget quote found for {key}: {item['google_total']}")
        ranks_by_weekend[item["weekend"]].append(int(item["option"]))

    for weekend, ranks in ranks_by_weekend.items():
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise RuntimeError(f"Non-consecutive option ranks for {weekend}: {ranks}")


def _sheet_rows(payload: dict[str, Any]) -> list[list[Any]]:
    rows = []
    limit = int(payload.get("sheet_options_per_weekend", 3))
    for item in payload["weekend_options"]:
        if int(item["option"]) > limit:
            continue
        categories = ", ".join(item["categories"]) or "Value discovery"
        preferred = ", ".join(item["preferred_timing_categories"]) or "—"
        url = item["google_search_url"]
        link = f'=HYPERLINK("{url}","Open exact search")'
        rows.append(
            [
                item["weekend"],
                item["option"],
                item["destination"]["name"],
                item["destination"]["code"],
                categories,
                item["google_total"],
                item["semester_window_median"],
                item["percent_below_median"],
                item["action"],
                preferred,
                item["outbound_example"],
                item["outbound_stops"],
                link,
                item["checked_at"],
            ]
        )
    return rows


def _authorized_session(credentials_path: Path | None) -> AuthorizedSession:
    if credentials_path:
        if not credentials_path.is_file():
            raise FileNotFoundError(f"Credentials file not found: {credentials_path}")
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=[SHEETS_SCOPE],
        )
    else:
        credentials, _ = google.auth.default(scopes=[SHEETS_SCOPE])
    return AuthorizedSession(credentials)


def _request_json(
    session: AuthorizedSession,
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = session.request(method, url, json=body, timeout=60)
    if not response.ok:
        raise RuntimeError(f"Google Sheets API {response.status_code}: {response.text[:1000]}")
    return response.json()


def _quote_sheet_name(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _update_sheet(
    *,
    spreadsheet_id: str,
    sheet_name: str,
    credentials_path: Path | None,
    ranked: dict[str, Any],
) -> None:
    session = _authorized_session(credentials_path)
    encoded_id = quote(spreadsheet_id, safe="")
    api_root = f"https://sheets.googleapis.com/v4/spreadsheets/{encoded_id}"

    metadata = _request_json(
        session,
        "GET",
        f"{api_root}?fields=sheets.properties(sheetId,title,gridProperties)",
    )
    sheets = {sheet["properties"]["title"]: sheet["properties"] for sheet in metadata["sheets"]}
    if sheet_name not in sheets:
        raise RuntimeError(f"Sheet tab {sheet_name!r} not found; available: {sorted(sheets)}")

    rows = _sheet_rows(ranked)
    if len(rows) > 39 or any(len(row) != 14 for row in rows):
        raise RuntimeError("Expected at most 39 rows by 14 columns before Sheets update")
    sheet_rows = rows + [[""] * 14 for _ in range(39 - len(rows))]
    if sheets[sheet_name]["gridProperties"]["rowCount"] < 43:
        raise RuntimeError(f"Sheet tab {sheet_name!r} is too short for A5:N43")

    quoted_sheet = _quote_sheet_name(sheet_name)
    checked = ranked["generated_at"]
    subtitle = (
        f"One adult · Google Flights search-page quotes · refreshed {checked} · "
        "prices are not provider-checkout verified"
    )
    update = _request_json(
        session,
        "POST",
        f"{api_root}/values:batchUpdate",
        body={
            "valueInputOption": "USER_ENTERED",
            "includeValuesInResponse": False,
            "data": [
                {"range": f"{quoted_sheet}!A2", "values": [[subtitle]]},
                {"range": f"{quoted_sheet}!A5:N43", "values": sheet_rows},
            ],
        },
    )
    if update.get("totalUpdatedRows", 0) < 40:
        raise RuntimeError(f"Unexpected Sheets update response: {update}")

    verify_range = quote(f"{quoted_sheet}!A4:N43", safe="")
    verified = _request_json(
        session,
        "GET",
        f"{api_root}/values/{verify_range}?valueRenderOption=FORMATTED_VALUE",
    )
    values = verified.get("values", [])
    if len(values) < len(rows) + 1 or len(values[0]) != 14:
        raise RuntimeError("Post-write verification did not return the updated rows")
    flattened = [str(value) for row in values for value in row]
    formula_errors = {"#REF!", "#VALUE!", "#DIV/0!", "#N/A"}
    found_errors = sorted(formula_errors.intersection(flattened))
    if found_errors:
        raise RuntimeError(f"Formula errors found after Sheets update: {found_errors}")


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copy2(source, temporary)
    temporary.replace(destination)


def main() -> None:
    args = _arguments()
    semester_config_path = ROOT / "config" / "semester_2026.json"
    semester_config = json.loads(semester_config_path.read_text(encoding="utf-8"))
    expected_weekends = [weekend["label"] for weekend in semester_config["weekends"]]
    airports = sorted({item["code"] for item in semester_config["destinations"]})

    lock_path = args.data_dir / ".refresh.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another refresh is still running; skipping this invocation", flush=True)
            return

        with tempfile.TemporaryDirectory(prefix="fli-sheet-refresh-") as temp_dir:
            temp = Path(temp_dir)
            initial = temp / "bucket_quotes.initial.json"
            retried = temp / "bucket_quotes.json"
            ranked_path = temp / "bucket_deals.json"

            scanner = [
                sys.executable,
                "scripts/search_weekend_prices.py",
                "--destinations",
                ",".join(airports),
                "--top",
                str(len(airports)),
                "--workers",
                str(args.workers),
                "--adults",
                "1",
                "--output",
                str(initial),
            ]
            _run(scanner)
            scan_payload = json.loads(initial.read_text(encoding="utf-8"))

            final_quotes = initial
            if _error_count(scan_payload):
                _run(
                    [
                        sys.executable,
                        "scripts/search_weekend_prices.py",
                        "--retry-errors-from",
                        str(initial),
                        "--retry-passes",
                        str(args.retry_passes),
                        "--workers",
                        str(args.workers),
                        "--retry-delay-seconds",
                        str(args.retry_delay_seconds),
                        "--output",
                        str(retried),
                    ]
                )
                final_quotes = retried
                scan_payload = json.loads(retried.read_text(encoding="utf-8"))

            errors = _error_count(scan_payload)
            if errors:
                raise RuntimeError(
                    f"Refusing to publish: {errors} Google queries still failed after retries"
                )
            if scan_payload["filters"]["adults"] != 1:
                raise RuntimeError("Refusing to publish a non-single-passenger scan")

            _run(
                [
                    sys.executable,
                    "scripts/rank_bucket_deals.py",
                    "--quotes",
                    str(final_quotes),
                    "--output",
                    str(ranked_path),
                ]
            )
            ranked = json.loads(ranked_path.read_text(encoding="utf-8"))
            _validate_ranked(ranked, expected_weekends)

            if args.dry_run:
                print(
                    f"Dry run passed: {len(ranked['weekend_options'])} ranked options; "
                    "Google Sheet not changed",
                    flush=True,
                )
                return

            if not args.no_sheet:
                _update_sheet(
                    spreadsheet_id=args.spreadsheet_id,
                    sheet_name=args.sheet_name,
                    credentials_path=args.credentials,
                    ranked=ranked,
                )

            _atomic_copy(final_quotes, args.data_dir / "bucket_quotes.json")
            _atomic_copy(final_quotes.with_suffix(".csv"), args.data_dir / "bucket_quotes.csv")
            _atomic_copy(ranked_path, args.data_dir / "bucket_deals.json")
            _atomic_copy(ranked_path.with_suffix(".csv"), args.data_dir / "bucket_deals.csv")
            target = "local web snapshot" if args.no_sheet else repr(args.sheet_name)
            print(
                f"Published {len(ranked['weekend_options'])} options to {target} "
                f"at {ranked['generated_at']}",
                flush=True,
            )


if __name__ == "__main__":
    main()
