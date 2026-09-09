"""Fast HTTP discovery and complete-itinerary expansion."""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from .models import Direction, FlightLeg, SearchRequest
from .proto import build_search_url

_DS_BLOB = re.compile(r"AF_initDataCallback\((\{.*?\})\);", re.S)
_DS_KEY = re.compile(r"key:\s*'([^']+)'")
_DS_DATA = re.compile(r"data:(.*?), sideChannel", re.S)
_DEFAULT_SOCS = (
    "CAISNQgQEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjQwMzE3LjA5X3AwGgJlbiADGgYIgLC_rwY"
)
_thread_local = threading.local()


class DiscoveryError(RuntimeError):
    """Google returned an HTTP page that cannot be treated as flight data."""


class DiscoveredDirection(Direction):
    """A direction plus Google's aggregate price for the current selection step."""

    price: float | None = None
    currency: str | None = None


def _session() -> Any:
    session = getattr(_thread_local, "session", None)
    if session is None:
        from curl_cffi import requests

        session = requests.Session()
        session.headers.update(
            {
                "accept-language": "en-GB,en;q=0.9",
                "user-agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145 Safari/537.36"
                ),
            }
        )
        socs = os.getenv("GOOGLE_FLIGHTS_MCP_SOCS_COOKIE", _DEFAULT_SOCS)
        if socs:
            session.cookies.set("SOCS", socs, domain=".google.com")
        _thread_local.session = session
    return session


def fetch_html(url: str, *, timeout_seconds: int = 30, attempts: int = 3) -> str:
    """Fetch Google Flights with browser TLS impersonation and bounded retries."""
    last_error: Exception | None = None
    for attempt in range(max(1, min(attempts, 3))):
        try:
            response = _session().get(
                url,
                impersonate="chrome",
                allow_redirects=True,
                timeout=max(5, min(timeout_seconds, 90)),
            )
            response.raise_for_status()
            if "/consent" in str(response.url):
                raise DiscoveryError("Google redirected the HTTP client to its consent page")
            return response.text
        except Exception as exc:  # curl-cffi has several backend-specific errors
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.25 * (2**attempt))
    raise DiscoveryError(f"Google Flights HTTP discovery failed: {last_error}") from last_error


def extract_payload(html: str) -> Any:
    """Extract the ``ds:1`` JSON payload embedded in the Google Flights HTML."""
    for match in _DS_BLOB.finditer(html):
        blob = match.group(1)
        key = _DS_KEY.search(blob)
        data = _DS_DATA.search(blob)
        if key and key.group(1) == "ds:1" and data:
            try:
                return json.loads(data.group(1))
            except json.JSONDecodeError as exc:
                raise DiscoveryError("Google Flights ds:1 payload is malformed") from exc
    if re.search(r"unusual traffic|not a robot|captcha", html, re.I):
        raise DiscoveryError("Google blocked HTTP discovery with an anti-automation challenge")
    raise DiscoveryError("Google Flights page contains no ds:1 flight payload")


def _safe_get(value: Any, index: int, default: Any = None) -> Any:
    return value[index] if isinstance(value, list) and len(value) > index else default


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise ValueError("truncated varint")


def _currency_from_token(token: Any) -> str | None:
    """Read the nested ISO currency from Google's per-row protobuf token."""
    if not isinstance(token, str):
        return None
    try:
        data = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        offset = 0
        while offset < len(data):
            tag, offset = _read_varint(data, offset)
            wire = tag & 7
            number = tag >> 3
            if wire == 0:
                _, offset = _read_varint(data, offset)
            elif wire == 2:
                length, offset = _read_varint(data, offset)
                value, offset = data[offset : offset + length], offset + length
                if number == 3:
                    nested_offset = 0
                    while nested_offset < len(value):
                        nested_tag, nested_offset = _read_varint(value, nested_offset)
                        nested_wire = nested_tag & 7
                        nested_number = nested_tag >> 3
                        if nested_wire == 0:
                            _, nested_offset = _read_varint(value, nested_offset)
                        elif nested_wire == 2:
                            nested_length, nested_offset = _read_varint(value, nested_offset)
                            nested_value = value[nested_offset : nested_offset + nested_length]
                            nested_offset += nested_length
                            if nested_number == 3:
                                code = nested_value.decode("ascii").upper()
                                return code if len(code) == 3 else None
                        else:
                            return None
            else:
                return None
    except (ValueError, UnicodeDecodeError):
        return None
    return None


def _datetime(date_value: Any, time_value: Any) -> datetime:
    if not isinstance(date_value, list) or not isinstance(time_value, list):
        raise ValueError("missing date or time")
    if len(date_value) < 3 or not time_value:
        raise ValueError("incomplete date or time")
    return datetime(
        int(date_value[0]),
        int(date_value[1]),
        int(date_value[2]),
        int(time_value[0] or 0),
        int(time_value[1] or 0) if len(time_value) > 1 else 0,
    )


def parse_flight_row(row: Any, fallback_currency: str) -> DiscoveredDirection:
    """Decode one flight row from either Google's top or other flights group."""
    if not isinstance(row, list) or not isinstance(_safe_get(row, 0), list):
        raise ValueError("not a flight row")
    detail = row[0]
    raw_legs = _safe_get(detail, 2, [])
    if not isinstance(raw_legs, list) or not raw_legs:
        raise ValueError("flight row has no physical legs")

    legs: list[FlightLeg] = []
    for raw in raw_legs:
        airline_info = _safe_get(raw, 22, [])
        airline = _safe_get(airline_info, 0)
        flight_number = _safe_get(airline_info, 1)
        if not isinstance(airline, str) or not isinstance(flight_number, str):
            raise ValueError("flight row lacks an airline or flight number")
        legs.append(
            FlightLeg(
                airline=airline.upper(),
                flight_number=flight_number.upper().removeprefix(airline.upper()),
                origin=str(_safe_get(raw, 3)).upper(),
                destination=str(_safe_get(raw, 6)).upper(),
                departure=_datetime(_safe_get(raw, 20), _safe_get(raw, 8)),
                arrival=_datetime(_safe_get(raw, 21), _safe_get(raw, 10)),
                duration_minutes=int(_safe_get(raw, 11)),
            )
        )

    price = None
    currency = fallback_currency
    price_block = _safe_get(row, 1)
    if isinstance(price_block, list):
        head = _safe_get(price_block, 0)
        raw_price = head[-1] if isinstance(head, list) and head else None
        if isinstance(raw_price, (int, float)) and not isinstance(raw_price, bool):
            price = float(raw_price)
        currency = _currency_from_token(_safe_get(price_block, 1)) or fallback_currency

    return DiscoveredDirection(
        legs=legs,
        price=price,
        currency=currency,
        duration_minutes=int(_safe_get(detail, 9)),
        stops=max(0, len(legs) - 1),
        self_transfer=_safe_get(detail, 12) if isinstance(_safe_get(detail, 12), bool) else None,
    )


def _rows(payload: Any) -> Iterable[Any]:
    """Yield both 'Top departing flights' and 'Other departing flights' rows."""
    if not isinstance(payload, list):
        return
    for index in (2, 3):
        group = _safe_get(payload, index)
        first = _safe_get(group, 0)
        if isinstance(first, list):
            yield from first


def parse_directions(html: str, fallback_currency: str) -> list[DiscoveredDirection]:
    parsed: list[DiscoveredDirection] = []
    seen: set[tuple] = set()
    failures: list[str] = []
    raw_rows = list(_rows(extract_payload(html)))
    for row in raw_rows:
        try:
            direction = parse_flight_row(row, fallback_currency)
        except (TypeError, ValueError) as exc:
            if len(failures) < 3:
                failures.append(str(exc))
            continue
        key = tuple(
            (leg.airline, leg.flight_number, leg.origin, leg.destination, leg.departure)
            for leg in direction.legs
        )
        if key not in seen:
            seen.add(key)
            parsed.append(direction)
    if raw_rows and not parsed:
        raise DiscoveryError(
            f"Google returned {len(raw_rows)} rows but none parsed: {'; '.join(failures)}"
        )
    return parsed


def discover_directions(
    request: SearchRequest, *, selected_outbound: Direction | None = None
) -> list[DiscoveredDirection]:
    url = build_search_url(request, selected_outbound=selected_outbound)
    return parse_directions(fetch_html(url), request.currency)


def candidate_sort_key(direction: DiscoveredDirection) -> tuple:
    """Bound expansion cost without considering an incomplete trip to be final."""
    return (
        direction.price is None,
        direction.price if direction.price is not None else float("inf"),
        direction.stops,
        direction.duration_minutes,
    )


def expand_returns(
    request: SearchRequest, outbounds: list[DiscoveredDirection]
) -> list[tuple[DiscoveredDirection, DiscoveredDirection]]:
    """Pin each outbound in protobuf and fetch compatible, fully priced returns."""
    candidates = sorted(outbounds, key=candidate_sort_key)[: request.max_outbounds_to_expand]

    def expand(
        outbound: DiscoveredDirection,
    ) -> tuple[DiscoveredDirection, list[DiscoveredDirection]]:
        returns = discover_directions(request, selected_outbound=outbound)
        return outbound, sorted(returns, key=candidate_sort_key)[
            : request.max_return_options_per_outbound
        ]

    workers = min(4, len(candidates))
    if not workers:
        return []
    pairs: list[tuple[DiscoveredDirection, DiscoveredDirection]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for outbound, returns in executor.map(expand, candidates):
            pairs.extend((outbound, inbound) for inbound in returns)
    return pairs
