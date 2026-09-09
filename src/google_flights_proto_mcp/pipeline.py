"""End-to-end discovery, pairing, ranking, and browser verification pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .discovery import DiscoveredDirection, discover_directions, expand_returns
from .models import CompleteItinerary, SearchRequest
from .proto import build_booking_url, build_search_url
from .ranking import rank_itineraries
from .verification import verify_shortlist


def _complete(
    request: SearchRequest,
    outbound: DiscoveredDirection,
    inbound: DiscoveredDirection | None,
    checked_at: datetime,
) -> CompleteItinerary:
    useful_hours = None
    if inbound:
        useful_hours = max(
            0.0,
            (inbound.legs[0].departure - outbound.legs[-1].arrival).total_seconds() / 3600,
        )
    return CompleteItinerary(
        outbound=outbound,
        inbound=inbound,
        discovered_price=(inbound.price if inbound else outbound.price),
        currency=(inbound.currency if inbound else outbound.currency) or request.currency,
        useful_destination_hours=round(useful_hours, 2) if useful_hours is not None else None,
        total_flight_minutes=outbound.duration_minutes
        + (inbound.duration_minutes if inbound else 0),
        total_stops=outbound.stops + (inbound.stops if inbound else 0),
        passenger_count=(
            request.adults + request.children + request.infants_in_seat + request.infants_on_lap
        ),
        cabin=request.cabin.replace("_", " ").title(),
        booking_url=build_booking_url(request, outbound, inbound),
        discovery_checked_at=checked_at,
    )


def discover_complete_itineraries(request: SearchRequest) -> dict[str, Any]:
    """Run HTTP discovery, create full pairs, rank them, and return the shortlist."""
    started = datetime.now().astimezone()
    outbounds = discover_directions(request)
    if request.return_date:
        pairs = expand_returns(request, outbounds)
        complete = [_complete(request, outbound, inbound, started) for outbound, inbound in pairs]
    else:
        complete = [_complete(request, outbound, None, started) for outbound in outbounds]
    ranked = rank_itineraries(complete)
    shortlist = ranked[: request.top_n]
    return {
        "success": True,
        "pipeline": [
            "protobuf query generation",
            "HTTP discovery",
            "complete itinerary pairing",
            "ranking",
            f"top {request.top_n} shortlist",
        ],
        "search_url": build_search_url(request),
        "outbound_options_discovered": len(outbounds),
        "complete_itineraries_considered": len(complete),
        "shortlist": [item.model_dump(mode="json") for item in shortlist],
        "discovery_checked_at": started.isoformat(timespec="seconds"),
        "price_status": "discovered_not_browser_verified",
    }


def search_rank_verify(request: SearchRequest) -> dict[str, Any]:
    """Run the full pipeline and strictly browser-verify only its top 1-3 results."""
    discovery = discover_complete_itineraries(request)
    items = [CompleteItinerary.model_validate(item) for item in discovery["shortlist"]]
    verify_shortlist(items)
    discovery["pipeline"].append(
        "Playwright verification of the exact Google page and provider checkout handoff"
    )
    discovery["shortlist"] = [item.model_dump(mode="json") for item in items]
    discovery["verified_count"] = sum(
        bool(item.verification and item.verification.get("verified")) for item in items
    )
    discovery["price_status"] = (
        "provider-checkout-verified prices appear only in verification.verified_price; "
        "verification.observed_price is only Google's displayed quote, and "
        "discovered_price is not browser-verified"
    )
    return discovery
