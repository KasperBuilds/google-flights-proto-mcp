"""Public request and result models for the standalone MCP."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SearchRequest(BaseModel):
    """One Google Flights search and the controls used by the ranking pipeline."""

    origin: str = Field(description="Origin IATA code, for example LIS")
    destination: str = Field(description="Destination IATA code, for example FNC")
    departure_date: str = Field(description="Outbound date in YYYY-MM-DD format")
    return_date: str | None = Field(None, description="Return date; omit for one-way")
    adults: int = Field(1, ge=1, le=9)
    children: int = Field(0, ge=0, le=8)
    infants_in_seat: int = Field(0, ge=0, le=8)
    infants_on_lap: int = Field(0, ge=0, le=8)
    cabin: Literal["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"] = "ECONOMY"
    max_stops: int | None = Field(None, ge=0, le=2, description="0 means nonstop")
    airlines: list[str] = Field(default_factory=list)
    outbound_earliest_departure_hour: int | None = Field(None, ge=0, le=23)
    outbound_latest_departure_hour: int | None = Field(None, ge=0, le=23)
    return_earliest_departure_hour: int | None = Field(None, ge=0, le=23)
    return_latest_departure_hour: int | None = Field(None, ge=0, le=23)
    max_duration_minutes: int | None = Field(None, gt=0)
    connecting_airports: list[str] = Field(default_factory=list)
    min_layover_minutes: int | None = Field(None, gt=0)
    max_layover_minutes: int | None = Field(None, gt=0)
    less_emissions: bool = False
    max_price: int | None = Field(None, gt=0)
    carry_on_bags: int | None = Field(None, ge=0, le=2)
    checked_bags: int | None = Field(None, ge=0, le=2)
    hide_separate_and_self_transfer: bool | None = None
    exclude_basic_economy: bool | None = None
    currency: str = "EUR"
    language: str = "en-GB"
    country: str = "PT"
    max_outbounds_to_expand: int = Field(5, ge=1, le=10)
    max_return_options_per_outbound: int = Field(10, ge=1, le=30)
    top_n: int = Field(3, ge=1, le=3)

    @field_validator("origin", "destination", "currency", "country")
    @classmethod
    def uppercase_codes(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("airlines", "connecting_airports")
    @classmethod
    def uppercase_code_lists(cls, values: list[str]) -> list[str]:
        return [value.strip().upper() for value in values]

    @field_validator("departure_date", "return_date")
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def validate_search(self) -> SearchRequest:
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        if self.return_date and self.return_date < self.departure_date:
            raise ValueError("return_date must be on or after departure_date")
        if self.infants_on_lap > self.adults:
            raise ValueError("infants_on_lap cannot exceed adults")
        return self


class FlightLeg(BaseModel):
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    duration_minutes: int


class Direction(BaseModel):
    legs: list[FlightLeg]
    duration_minutes: int
    stops: int
    self_transfer: bool | None = None


class CompleteItinerary(BaseModel):
    outbound: Direction
    inbound: Direction | None = None
    discovered_price: float | None
    currency: str
    useful_destination_hours: float | None = None
    total_flight_minutes: int
    total_stops: int
    passenger_count: int
    cabin: str
    ranking_score: float = 0
    ranking_reasons: list[str] = Field(default_factory=list)
    booking_url: str
    discovery_checked_at: datetime
    verification: dict | None = None
