from google_flights_proto_mcp.models import FlightLeg
from google_flights_proto_mcp.verification import (
    _is_failed_provider_handoff,
    _leg_visible,
    _provider_price_visible,
)


def test_connection_leg_matches_inside_combined_itinerary_attribute() -> None:
    leg = FlightLeg(
        airline="LX",
        flight_number="562",
        origin="ZRH",
        destination="NCE",
        departure="2026-10-03T09:00:00",
        arrival="2026-10-03T10:00:00",
        duration_minutes=60,
    )
    html = 'data-itinerary="LIS-ZRH-LX-2087-20261002,ZRH-NCE-LX-562-20261003"'
    assert _leg_visible(html, "", leg)


def test_provider_price_visible_accepts_european_and_symbol_formats() -> None:
    assert _provider_price_visible("Total €809", 809, "EUR")
    assert _provider_price_visible("Total 394,50 EUR", 394.5, "EUR")
    assert not _provider_price_visible("Total €394", 809, "EUR")


def test_failed_google_handoff_is_not_checkout_verified() -> None:
    assert _is_failed_provider_handoff(
        "https://www.google.com/travel/clk/f?t=123",
        "Sorry! The connection was interrupted due to an error.",
    )
