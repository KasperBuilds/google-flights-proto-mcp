"""Playwright verification for the small ranked shortlist only."""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from datetime import date, datetime
from html import unescape
from pathlib import Path
from typing import Any

from .models import CompleteItinerary, FlightLeg

_CURRENCY_MARKERS = {
    "EUR": ("€", "EUR", "euros", "euro"),
    "USD": ("US$", "$", "USD", "US dollars", "dollars"),
    "GBP": ("£", "GBP", "pounds"),
    "CAD": ("CA$", "C$", "CAD"),
    "AUD": ("A$", "AUD"),
    "CHF": ("CHF",),
    "JPY": ("¥", "JPY"),
}


def _browser_executable() -> str | None:
    configured = os.getenv("GOOGLE_FLIGHTS_MCP_BROWSER_EXECUTABLE")
    if configured:
        return configured
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )
    elif sys.platform.startswith("win"):
        for root in filter(None, (os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"))):
            candidates.append(str(Path(root) / "Google/Chrome/Application/chrome.exe"))
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            executable = shutil.which(name)
            if executable:
                candidates.append(executable)
    return next((candidate for candidate in candidates if Path(candidate).is_file()), None)


def _amount(token: str) -> float:
    compact = re.sub(r"[\s\u00a0']", "", token)
    decimal = max(compact.rfind(","), compact.rfind("."))
    if decimal >= 0 and len(compact) - decimal - 1 == 2:
        compact = re.sub(r"[.,]", "", compact[:decimal]) + "." + compact[decimal + 1 :]
    else:
        compact = re.sub(r"[.,]", "", compact)
    value = float(compact)
    if value <= 0:
        raise ValueError("non-positive total")
    return value


def _extract_price(text: str, currency: str) -> float:
    for marker in sorted(_CURRENCY_MARKERS.get(currency, (currency,)), key=len, reverse=True):
        escaped = re.escape(marker)
        match = re.search(rf"{escaped}\s*([0-9][0-9.,\s\u00a0']*)", text)
        match = match or re.search(rf"([0-9][0-9.,\s\u00a0']*)\s*{escaped}", text)
        if match:
            return _amount(match.group(1))
    raise ValueError(f"could not read a {currency} total")


def _provider_price_visible(text: str, price: float, currency: str) -> bool:
    """Return whether a provider page visibly repeats the verified total.

    Google can show a numeric booking option even when its provider handoff is
    broken.  A fare is therefore checkout-verified only when the handoff lands
    outside Google and the same currency/total is visible there.
    """
    whole = int(price)
    decimals = round((price - whole) * 100)
    amount_forms = {f"{whole:,}", str(whole)}
    if decimals:
        amount_forms.update(
            {
                f"{price:,.2f}",
                f"{price:.2f}",
                f"{price:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
                f"{price:.2f}".replace(".", ","),
            }
        )
    for marker in _CURRENCY_MARKERS.get(currency, (currency,)):
        for amount in amount_forms:
            if re.search(
                rf"(?:{re.escape(marker)}\s*{re.escape(amount)}|"
                rf"{re.escape(amount)}\s*{re.escape(marker)})",
                text,
                re.I,
            ):
                return True
    return False


def _is_failed_provider_handoff(url: str, body: str) -> bool:
    """Detect Google's failed click-through page and common hard failures."""
    lowered = body.casefold()
    return (
        "google.com/travel/clk" in url
        or "connection was interrupted due to an error" in lowered
        or "page not found" in lowered
        or "access denied" in lowered
    )


def _date_visible(body: str, iso_date: str) -> bool:
    parsed = date.fromisoformat(iso_date)
    candidates = (iso_date, f"{parsed.day} {parsed:%b}", f"{parsed.day} {parsed:%B}")
    return any(value.casefold() in body.casefold() for value in candidates)


def _leg_visible(html: str, body: str, leg: FlightLeg) -> bool:
    raw = unescape(html)
    flight_number = leg.flight_number.upper().removeprefix(leg.airline.upper())
    # Google encodes a connection as one comma-separated ``data-itinerary``
    # attribute. Only the first physical leg is preceded by ``itinerary=``;
    # matching that prefix caused false negatives for every later leg.
    segment_identifier = (
        f"{leg.origin}-{leg.destination}-{leg.airline}-{flight_number}-{leg.departure:%Y%m%d}"
    )
    if segment_identifier.casefold() in raw.casefold():
        return True
    route = re.search(
        rf"\b{re.escape(leg.origin)}\s*[-–—]\s*{re.escape(leg.destination)}\b",
        body,
        re.I,
    )
    flight = re.search(rf"\b{re.escape(leg.airline)}\s*{re.escape(flight_number)}\b", raw, re.I)
    return bool(route and flight and _date_visible(body, leg.departure.date().isoformat()))


def _failure(item: CompleteItinerary, error: str) -> dict[str, Any]:
    return {
        "verified": False,
        "status": "unverified",
        "verified_price": None,
        "currency": item.currency,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "booking_url": item.booking_url,
        "error": error,
        "final_checkout_required": True,
    }


def verify_shortlist(
    items: list[CompleteItinerary], *, timeout_seconds: int = 35
) -> list[CompleteItinerary]:
    """Verify up to three exact booking pages in one headless browser session."""
    items = items[:3]
    if not items:
        return items
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        for item in items:
            item.verification = _failure(item, "Playwright is not installed")
        return items

    timeout_ms = max(5, min(timeout_seconds, 90)) * 1000
    with sync_playwright() as playwright:
        launch: dict[str, Any] = {"headless": True}
        executable = _browser_executable()
        if executable:
            launch["executable_path"] = executable
        else:
            channel = os.getenv("GOOGLE_FLIGHTS_MCP_BROWSER_CHANNEL")
            if channel:
                launch["channel"] = channel
        try:
            browser = playwright.chromium.launch(**launch)
        except PlaywrightError as exc:
            for item in items:
                item.verification = _failure(
                    item,
                    "Could not launch Chrome/Chromium. Set "
                    f"GOOGLE_FLIGHTS_MCP_BROWSER_EXECUTABLE: {exc}",
                )
            return items

        context = browser.new_context(locale="en-GB")
        try:
            for item in items:
                page = context.new_page()
                try:
                    page.goto(item.booking_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    accept = page.get_by_role("button", name="Accept all", exact=True)
                    if accept.count() == 1:
                        accept.click(timeout=min(10_000, timeout_ms))
                    label = page.get_by_text("Lowest total price", exact=True).first
                    label.wait_for(state="visible", timeout=timeout_ms)
                    panel = label.locator("xpath=..").inner_text(timeout=timeout_ms)
                    body = page.locator("body").inner_text(timeout=timeout_ms)
                    html = page.content()
                    observed = _extract_price(panel, item.currency)
                    legs = item.outbound.legs + (item.inbound.legs if item.inbound else [])
                    passenger_visible = bool(
                        re.search(
                            rf"\b{item.passenger_count}\s+"
                            r"(?:passengers?|travell?ers?)\b",
                            body,
                            re.I,
                        )
                    )
                    cabin_visible = item.cabin.casefold() in body[:6000].casefold()
                    leg_checks = [_leg_visible(html, body, leg) for leg in legs]
                    date_checks = [
                        _date_visible(body, leg.departure.date().isoformat())
                        or leg.departure.strftime("%Y%m%d") in html
                        for leg in legs
                    ]
                    taxes_visible = bool(
                        re.search(r"prices include required taxes\s*\+\s*fees", body, re.I)
                    )
                    google_page_verified = (
                        passenger_visible
                        and cabin_visible
                        and taxes_visible
                        and all(leg_checks)
                        and all(date_checks)
                    )

                    booking_buttons = page.locator(
                        'button[aria-label^="Continue to book with "]'
                    )
                    matching_button = None
                    provider = None
                    for index in range(booking_buttons.count()):
                        candidate = booking_buttons.nth(index)
                        label_text = candidate.get_attribute("aria-label") or ""
                        try:
                            option_price = _extract_price(label_text, item.currency)
                        except ValueError:
                            continue
                        if abs(option_price - observed) <= 0.01:
                            matching_button = candidate
                            provider_match = re.match(
                                r"Continue to book with (.+?)(?: airline)? for ",
                                label_text,
                                re.I,
                            )
                            provider = provider_match.group(1) if provider_match else None
                            break

                    booking_option_matches = matching_button is not None
                    provider_handoff_loaded = False
                    provider_price_matches = False
                    provider_final_url = None
                    provider_error = None
                    if google_page_verified and matching_button is not None:
                        pages_before = set(context.pages)
                        matching_button.click(timeout=timeout_ms)
                        deadline = time.monotonic() + min(timeout_seconds, 15)
                        provider_page = None
                        while time.monotonic() < deadline:
                            new_pages = [p for p in context.pages if p not in pages_before]
                            if new_pages:
                                provider_page = new_pages[-1]
                                break
                            if page.url != item.booking_url:
                                provider_page = page
                                break
                            page.wait_for_timeout(250)
                        if provider_page is None:
                            provider_error = "Booking option did not open a provider page"
                        else:
                            try:
                                provider_page.wait_for_load_state(
                                    "domcontentloaded", timeout=timeout_ms
                                )
                            except PlaywrightTimeoutError:
                                pass
                            provider_final_url = provider_page.url
                            try:
                                provider_body = provider_page.locator("body").inner_text(
                                    timeout=timeout_ms
                                )
                            except PlaywrightError:
                                provider_body = ""
                            provider_handoff_loaded = not _is_failed_provider_handoff(
                                provider_final_url, provider_body
                            )
                            provider_price_matches = provider_handoff_loaded and (
                                _provider_price_visible(
                                    provider_body, observed, item.currency
                                )
                            )
                            if not provider_handoff_loaded:
                                provider_error = "Provider handoff returned an error page"
                            elif not provider_price_matches:
                                provider_error = (
                                    "Provider page loaded but did not show the same total"
                                )
                            if provider_page is not page:
                                provider_page.close()

                    verified = (
                        google_page_verified
                        and booking_option_matches
                        and provider_handoff_loaded
                        and provider_price_matches
                    )
                    item.verification = {
                        "verified": verified,
                        "status": "verified" if verified else "checkout_unverified",
                        "verified_price": observed if verified else None,
                        "observed_price": observed,
                        "currency": item.currency,
                        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "source": (
                            "Rendered Google Flights exact booking page plus provider "
                            "checkout handoff"
                        ),
                        "final_url": page.url,
                        "booking_url": item.booking_url,
                        "checks": {
                            "lowest_total_price_visible": True,
                            "passenger_control_visible": passenger_visible,
                            "cabin_visible": cabin_visible,
                            "required_taxes_and_fees_included": taxes_visible,
                            "google_page_verified": google_page_verified,
                            "booking_option_price_matches": booking_option_matches,
                            "booking_provider": provider,
                            "provider_handoff_loaded": provider_handoff_loaded,
                            "provider_price_matches": provider_price_matches,
                            "provider_final_url": provider_final_url,
                            "legs": leg_checks,
                            "dates": date_checks,
                        },
                        "price_changed_since_discovery": (
                            item.discovered_price is not None and observed != item.discovered_price
                        ),
                        "final_checkout_required": True,
                    }
                    if not verified:
                        item.verification["error"] = provider_error or (
                            "A price was visible, but every exact-itinerary check did not pass"
                        )
                except (PlaywrightTimeoutError, PlaywrightError, ValueError) as exc:
                    item.verification = _failure(item, str(exc))
                finally:
                    page.close()
        finally:
            context.close()
            browser.close()
    return items
