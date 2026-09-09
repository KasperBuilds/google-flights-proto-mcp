"""Deterministic ranking for complete flight itineraries."""

from __future__ import annotations

from .models import CompleteItinerary


def _normalise(values: list[float], value: float, *, lower_is_better: bool) -> float:
    low, high = min(values), max(values)
    if high == low:
        return 1.0
    score = (value - low) / (high - low)
    return 1.0 - score if lower_is_better else score


def rank_itineraries(itineraries: list[CompleteItinerary]) -> list[CompleteItinerary]:
    """Rank by total price, useful destination time, travel burden, and stops."""
    if not itineraries:
        return []
    known_prices = [
        item.discovered_price for item in itineraries if item.discovered_price is not None
    ]
    useful_hours = [item.useful_destination_hours or 0 for item in itineraries]
    durations = [float(item.total_flight_minutes) for item in itineraries]
    stops = [float(item.total_stops) for item in itineraries]

    for item in itineraries:
        if item.discovered_price is None or not known_prices:
            price_score = 0.0
        else:
            price_score = _normalise(known_prices, item.discovered_price, lower_is_better=True)
        time_score = _normalise(
            useful_hours, item.useful_destination_hours or 0, lower_is_better=False
        )
        duration_score = _normalise(
            durations, float(item.total_flight_minutes), lower_is_better=True
        )
        stops_score = _normalise(stops, float(item.total_stops), lower_is_better=True)
        score = 100 * (
            0.50 * price_score + 0.25 * time_score + 0.15 * duration_score + 0.10 * stops_score
        )
        item.ranking_score = round(score, 2)
        reasons = []
        if price_score >= 0.75:
            reasons.append("low total price among complete itinerary pairs")
        if time_score >= 0.75:
            reasons.append("strong useful time at destination")
        if item.total_stops == 0:
            reasons.append("nonstop both ways")
        if duration_score >= 0.75:
            reasons.append("low total travel time")
        item.ranking_reasons = reasons or ["balanced complete-itinerary value"]
    return sorted(
        itineraries,
        key=lambda item: (
            -item.ranking_score,
            item.discovered_price is None,
            item.discovered_price or float("inf"),
        ),
    )
