"""Railway-ready web dashboard for cached semester flight deals."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sys
from collections import Counter
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
WEB_DIR = PACKAGE_DIR / "web_assets"
SEED_PATH = PROJECT_ROOT / "outputs" / "bucket_deals.json"
REFRESH_SCRIPT = PROJECT_ROOT / "scripts" / "refresh_google_sheet.py"
BUCKET_CONFIG_PATH = PROJECT_ROOT / "config" / "bucket_list_2026.json"

logger = logging.getLogger("fli.web")


def _load_bucket_labels_by_airport() -> dict[str, list[dict[str, str]]]:
    """Map destination airports to explicit user bucket-list labels."""
    config = json.loads(BUCKET_CONFIG_PATH.read_text(encoding="utf-8"))
    labels: dict[str, list[dict[str, str]]] = {}
    for entry in config.get("bucket_list", []):
        marker = {"name": entry["name"], "type": entry["type"]}
        for airport in entry["airports"]:
            labels.setdefault(airport, []).append(marker)
    return labels


BUCKET_LABELS_BY_AIRPORT = _load_bucket_labels_by_airport()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _data_dir() -> Path:
    return Path(os.getenv("FLI_DATA_DIR", PROJECT_ROOT / "outputs"))


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def load_ranked_snapshot(data_dir: Path | None = None) -> dict[str, Any]:
    """Load the persistent snapshot, falling back to the bundled seed."""
    persistent = (data_dir or _data_dir()) / "bucket_deals.json"
    candidates = [persistent]
    if persistent.resolve() != SEED_PATH.resolve():
        candidates.append(SEED_PATH)
    for path in candidates:
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            ceiling = float(payload.get("max_return_price", 250))
            options = payload.get("weekend_options", [])
            within_budget = all(float(item["google_total"]) <= ceiling for item in options)
            if options and payload.get("passengers") == 1 and within_budget:
                return payload
    raise FileNotFoundError("No ranked flight snapshot is available")


def build_public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Shape the internal ranker output into a stable browser API."""
    order = [weekend["label"] for weekend in payload.get("weekends", [])]
    weekend_metadata = {weekend["label"]: weekend for weekend in payload.get("weekends", [])}
    grouped: dict[str, list[dict[str, Any]]] = {weekend: [] for weekend in order}
    for item in payload["weekend_options"]:
        weekend = item["weekend"]
        airport = item["destination"]["code"]
        bucket_labels = BUCKET_LABELS_BY_AIRPORT.get(airport, [])
        if weekend not in grouped:
            grouped[weekend] = []
            order.append(weekend)
        grouped[weekend].append(
            {
                "rank": item["option"],
                "destination": item["destination"]["name"],
                "airport": airport,
                "categories": item["categories"],
                "on_bucket_list": bool(bucket_labels),
                "bucket_list_labels": bucket_labels,
                "preferred_timing_categories": item["preferred_timing_categories"],
                "price": item["google_total"],
                "currency": item.get("currency", "EUR"),
                "median": item["semester_window_median"],
                "percent_below_median": item["percent_below_median"],
                "status": item["action"],
                "deal_rating": item["deal_rating"],
                "outbound_example": item["outbound_example"],
                "stops": item["outbound_stops"],
                "search_url": item["google_search_url"],
                "checked_at": item["checked_at"],
            }
        )

    for options in grouped.values():
        options.sort(key=lambda option: option["rank"])

    statuses = Counter(option["status"] for options in grouped.values() for option in options)
    all_options = [option for options in grouped.values() for option in options]
    initial_options = int(
        payload.get("website_initial_options", payload.get("options_per_weekend", 3))
    )
    best_saving = (
        max(all_options, key=lambda option: option["percent_below_median"]) if all_options else None
    )
    checked_times = [
        timestamp
        for option in all_options
        if (timestamp := _parse_timestamp(option["checked_at"])) is not None
    ]
    oldest_check = min(checked_times).isoformat() if checked_times else None

    return {
        "generated_at": payload["generated_at"],
        "origin": payload.get("origin", "LIS"),
        "passengers": payload.get("passengers", 1),
        "price_scope": "Google Flights search-page round-trip quote for one adult",
        "verification_scope": "Not provider-checkout verified; confirm on Google before booking",
        "method": payload["method"],
        "summary": {
            "weekends": len(grouped),
            "options": len(all_options),
            "max_options": len(all_options),
            "initial_options_per_weekend": initial_options,
            "initially_visible_options": sum(
                min(initial_options, len(options)) for options in grouped.values()
            ),
            "max_return_price": payload.get("max_return_price", 250),
            "below_median": statuses.get("DEAL", 0) + statuses.get("BELOW MEDIAN", 0),
            "best_saving": (
                {
                    "destination": best_saving["destination"],
                    "weekend": next(
                        weekend for weekend, options in grouped.items() if best_saving in options
                    ),
                    "percent": best_saving["percent_below_median"],
                }
                if best_saving
                else None
            ),
            "oldest_quote_at": oldest_check,
        },
        "weekends": [
            {
                "label": weekend,
                "availability_note": weekend_metadata.get(weekend, {}).get("availability_note"),
                "options": grouped[weekend],
            }
            for weekend in order
        ],
    }


class RefreshManager:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.last_success_at: str | None = None
        self.last_error: str | None = None
        self.last_log_tail: str | None = None
        self.running = False

    def status(self) -> dict[str, Any]:
        return {
            "enabled": _env_bool("FLI_REFRESH_ENABLED", True),
            "running": self.running,
            "interval_seconds": int(os.getenv("FLI_REFRESH_INTERVAL_SECONDS", "3600")),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
        }

    async def refresh(self) -> bool:
        if self.lock.locked():
            return False
        async with self.lock:
            self.running = True
            self.started_at = datetime.now().astimezone().isoformat(timespec="seconds")
            self.last_error = None
            command = [
                sys.executable,
                str(REFRESH_SCRIPT),
                "--no-sheet",
                "--data-dir",
                str(_data_dir()),
                "--workers",
                os.getenv("FLI_REFRESH_WORKERS", "2"),
                "--retry-passes",
                os.getenv("FLI_REFRESH_RETRY_PASSES", "6"),
                "--retry-delay-seconds",
                os.getenv("FLI_REFRESH_RETRY_DELAY_SECONDS", "10"),
            ]
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=PROJECT_ROOT,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                stdout, _ = await process.communicate()
                output = stdout.decode(errors="replace")
                self.last_log_tail = output[-4000:]
                if process.returncode:
                    raise RuntimeError(
                        f"Refresh process exited {process.returncode}: {output[-800:]}"
                    )
                load_ranked_snapshot()
                self.last_success_at = datetime.now().astimezone().isoformat(timespec="seconds")
                logger.info("Hourly flight snapshot refreshed successfully")
                return True
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Flight refresh failed; serving the prior snapshot")
                return False
            finally:
                self.running = False
                self.finished_at = datetime.now().astimezone().isoformat(timespec="seconds")


refresh_manager = RefreshManager()


async def _refresh_loop() -> None:
    if _env_bool("FLI_REFRESH_ON_STARTUP", True):
        await refresh_manager.refresh()
    while True:
        await asyncio.sleep(max(60, int(os.getenv("FLI_REFRESH_INTERVAL_SECONDS", "3600"))))
        await refresh_manager.refresh()


@asynccontextmanager
async def lifespan(_: FastAPI):
    task: asyncio.Task[None] | None = None
    if _env_bool("FLI_REFRESH_ENABLED", True):
        task = asyncio.create_task(_refresh_loop())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Lisbon Semester Flight Deals",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/deals")
async def deals() -> JSONResponse:
    try:
        payload = build_public_payload(load_ranked_snapshot())
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return JSONResponse({"data": payload, "refresh": refresh_manager.status()})


@app.get("/api/status")
async def status() -> dict[str, Any]:
    snapshot = None
    try:
        snapshot = load_ranked_snapshot().get("generated_at")
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"snapshot_generated_at": snapshot, "refresh": refresh_manager.status()}


@app.get("/healthz")
async def health() -> JSONResponse:
    try:
        snapshot = build_public_payload(load_ranked_snapshot())
        options = snapshot["summary"]["options"]
        weekends = snapshot["summary"]["weekends"]
        over_budget = any(
            option["price"] > snapshot["summary"]["max_return_price"]
            for weekend in snapshot["weekends"]
            for option in weekend["options"]
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return JSONResponse({"status": "unhealthy", "reason": "no snapshot"}, status_code=503)
    healthy = weekends == 13 and not over_budget
    return JSONResponse(
        {
            "status": "ok" if healthy else "degraded",
            "weekends": weekends,
            "options": options,
            "max_return_price": snapshot["summary"]["max_return_price"],
        },
        status_code=200 if healthy else 503,
    )


@app.post("/api/refresh", status_code=202)
async def trigger_refresh(
    request: Request,
    x_refresh_token: str | None = Header(default=None),
) -> dict[str, Any]:
    expected = os.getenv("FLI_ADMIN_TOKEN")
    if not expected or not x_refresh_token or not secrets.compare_digest(x_refresh_token, expected):
        raise HTTPException(status_code=403, detail="Manual refresh is disabled")
    if refresh_manager.lock.locked():
        return {"accepted": False, "reason": "refresh already running"}
    request.app.state.manual_refresh_task = asyncio.create_task(refresh_manager.refresh())
    return {"accepted": True}


def run() -> None:
    """Run the web dashboard on Railway's assigned port."""
    uvicorn.run(
        "google_flights_proto_mcp.web:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
    )


if __name__ == "__main__":
    run()
