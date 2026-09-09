from urllib.parse import parse_qs, urlparse

from google_flights_proto_mcp.models import Direction, FlightLeg, SearchRequest
from google_flights_proto_mcp.proto import build_booking_url, build_search_url, build_tfs


def test_search_token_matches_reference_implementation() -> None:
    request = SearchRequest(
        origin="LIS",
        destination="FNC",
        departure_date="2026-09-19",
        return_date="2026-09-21",
        adults=2,
        max_stops=0,
    )
    assert build_tfs(request) == (
        "GhwSCjIwMjYtMDktMTkoAGoFEgNMSVNyBRIDRk5DGhwSCjIwMjYtMDktMjEoAGoF"
        "EgNGTkNyBRIDTElTQgIBAUgBmAEB"
    )


def test_booking_url_is_exact_and_locale_specific() -> None:
    request = SearchRequest(
        origin="LIS",
        destination="FNC",
        departure_date="2026-09-19",
        return_date="2026-09-21",
        adults=2,
    )
    outbound = Direction(
        legs=[
            FlightLeg(
                airline="FR",
                flight_number="123",
                origin="LIS",
                destination="FNC",
                departure="2026-09-19T07:30:00",
                arrival="2026-09-19T09:15:00",
                duration_minutes=105,
            )
        ],
        duration_minutes=105,
        stops=0,
    )
    inbound = Direction(
        legs=[
            FlightLeg(
                airline="FR",
                flight_number="124",
                origin="FNC",
                destination="LIS",
                departure="2026-09-21T20:00:00",
                arrival="2026-09-21T21:45:00",
                duration_minutes=105,
            )
        ],
        duration_minutes=105,
        stops=0,
    )
    url = build_booking_url(request, outbound, inbound)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.path == "/travel/flights/booking"
    assert query["curr"] == ["EUR"]
    assert query["hl"] == ["en-GB"]
    assert len(query["tfs"][0]) > 50


def test_search_url_is_not_mislabelled_as_booking_url() -> None:
    request = SearchRequest(origin="LIS", destination="FNC", departure_date="2026-09-19")
    assert urlparse(build_search_url(request)).path == "/travel/flights/search"
