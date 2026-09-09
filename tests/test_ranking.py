from datetime import datetime

from google_flights_proto_mcp.models import CompleteItinerary, Direction, FlightLeg
from google_flights_proto_mcp.ranking import rank_itineraries


def _itinerary(price: float, useful: float, stops: int) -> CompleteItinerary:
    leg = FlightLeg(
        airline="TP",
        flight_number="1",
        origin="LIS",
        destination="FNC",
        departure="2026-09-19T08:00:00",
        arrival="2026-09-19T10:00:00",
        duration_minutes=120,
    )
    direction = Direction(legs=[leg], duration_minutes=120, stops=stops)
    return CompleteItinerary(
        outbound=direction,
        inbound=direction,
        discovered_price=price,
        currency="EUR",
        useful_destination_hours=useful,
        total_flight_minutes=240,
        total_stops=stops,
        passenger_count=2,
        cabin="Economy",
        booking_url="https://www.google.com/travel/flights/booking?tfs=x",
        discovery_checked_at=datetime.now(),
    )


def test_ranking_uses_complete_price_and_useful_time() -> None:
    cheap = _itinerary(80, 20, 0)
    expensive = _itinerary(180, 60, 0)
    ranked = rank_itineraries([expensive, cheap])
    assert ranked[0] is cheap
    assert ranked[0].ranking_score > ranked[1].ranking_score
