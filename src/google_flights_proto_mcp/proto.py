"""Real protobuf construction for Google Flights ``tfs`` URLs.

The descriptor mirrors ``flights.proto`` and is built at import time so the
package does not need ``protoc`` or a checked-in generated file at runtime.
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlencode

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from .models import Direction, SearchRequest

_PACKAGE = "google_flights_proto_mcp"


def _field(
    message: Any,
    name: str,
    number: int,
    field_type: int,
    *,
    label: int = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type_name: str | None = None,
    proto3_optional: bool = False,
) -> None:
    item = message.field.add(name=name, number=number, type=field_type, label=label)
    if type_name:
        item.type_name = f".{_PACKAGE}.{type_name}"
    if proto3_optional:
        message.oneof_decl.add(name=f"_{name}")
        item.oneof_index = len(message.oneof_decl) - 1
        item.proto3_optional = True


def _message(file: Any, name: str) -> Any:
    return file.message_type.add(name=name)


def _enum(file: Any, name: str, values: list[tuple[str, int]]) -> None:
    enum = file.enum_type.add(name=name)
    for value_name, number in values:
        enum.value.add(name=value_name, number=number)


def _build_types() -> tuple[type, type]:
    f = descriptor_pb2.FileDescriptorProto(
        name="google_flights_proto_mcp/flights.proto",
        package=_PACKAGE,
        syntax="proto3",
    )
    _enum(f, "Emissions", [("UNKNOWN_EMISSIONS", 0), ("LESS_EMISSIONS", 1)])
    _enum(
        f,
        "Seat",
        [
            ("UNKNOWN_SEAT", 0),
            ("ECONOMY", 1),
            ("PREMIUM_ECONOMY", 2),
            ("BUSINESS", 3),
            ("FIRST", 4),
        ],
    )
    _enum(f, "Trip", [("UNKNOWN_TRIP", 0), ("ROUND_TRIP", 1), ("ONE_WAY", 2), ("MULTI_CITY", 3)])
    _enum(
        f,
        "Passenger",
        [
            ("UNKNOWN_PASSENGER", 0),
            ("ADULT", 1),
            ("CHILD", 2),
            ("INFANT_IN_SEAT", 3),
            ("INFANT_ON_LAP", 4),
        ],
    )

    airport = _message(f, "Airport")
    _field(airport, "airport", 2, descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
    selected = _message(f, "SelectedFlight")
    for name, number in (
        ("origin", 1),
        ("date", 2),
        ("destination", 3),
        ("airline", 5),
        ("flight_number", 6),
    ):
        _field(selected, name, number, descriptor_pb2.FieldDescriptorProto.TYPE_STRING)

    data = _message(f, "FlightData")
    _field(data, "date", 2, descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
    _field(
        data,
        "selected_flights",
        4,
        descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        label=3,
        type_name="SelectedFlight",
    )
    for name, number in (
        ("max_stops", 5),
        ("earliest_departure_hour", 8),
        ("latest_departure_hour", 9),
        ("earliest_arrival_hour", 10),
        ("latest_arrival_hour", 11),
        ("max_duration_minutes", 12),
        ("min_layover_minutes", 17),
        ("max_layover_minutes", 18),
    ):
        _field(
            data, name, number, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, proto3_optional=True
        )
    _field(data, "airlines", 6, descriptor_pb2.FieldDescriptorProto.TYPE_STRING, label=3)
    _field(
        data,
        "from_airport",
        13,
        descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        label=3,
        type_name="Airport",
    )
    _field(
        data,
        "to_airport",
        14,
        descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        label=3,
        type_name="Airport",
    )
    _field(
        data, "connecting_airports", 15, descriptor_pb2.FieldDescriptorProto.TYPE_STRING, label=3
    )
    _field(
        data,
        "emissions",
        19,
        descriptor_pb2.FieldDescriptorProto.TYPE_ENUM,
        label=3,
        type_name="Emissions",
    )

    baggage = _message(f, "Baggage")
    _field(
        baggage,
        "carry_on_bags",
        2,
        descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
        proto3_optional=True,
    )
    _field(
        baggage,
        "checked_bags",
        3,
        descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
        proto3_optional=True,
    )
    pin = _message(f, "MaxPin")
    _field(pin, "value", 1, descriptor_pb2.FieldDescriptorProto.TYPE_UINT64)

    info = _message(f, "Info")
    for name, number in (
        ("marker_one", 1),
        ("marker_two", 2),
        ("max_price", 12),
        ("marker_fourteen", 14),
    ):
        _field(
            info, name, number, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, proto3_optional=True
        )
    _field(
        info,
        "data",
        3,
        descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
        label=3,
        type_name="FlightData",
    )
    _field(
        info,
        "passengers",
        8,
        descriptor_pb2.FieldDescriptorProto.TYPE_ENUM,
        label=3,
        type_name="Passenger",
    )
    _field(info, "seat", 9, descriptor_pb2.FieldDescriptorProto.TYPE_ENUM, type_name="Seat")
    _field(
        info, "baggage", 13, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name="Baggage"
    )
    _field(info, "pin", 16, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, type_name="MaxPin")
    _field(
        info,
        "hide_separate_and_self_transfer",
        17,
        descriptor_pb2.FieldDescriptorProto.TYPE_BOOL,
        proto3_optional=True,
    )
    _field(info, "trip", 19, descriptor_pb2.FieldDescriptorProto.TYPE_ENUM, type_name="Trip")
    _field(
        info,
        "exclude_basic_economy",
        25,
        descriptor_pb2.FieldDescriptorProto.TYPE_BOOL,
        proto3_optional=True,
    )

    pool = descriptor_pool.DescriptorPool()
    pool.Add(f)
    return (
        message_factory.GetMessageClass(pool.FindMessageTypeByName(f"{_PACKAGE}.Info")),
        message_factory.GetMessageClass(pool.FindMessageTypeByName(f"{_PACKAGE}.SelectedFlight")),
    )


Info, SelectedFlight = _build_types()

_CABINS = {"ECONOMY": 1, "PREMIUM_ECONOMY": 2, "BUSINESS": 3, "FIRST": 4}


def _passengers(request: SearchRequest) -> list[int]:
    return (
        [1] * request.adults
        + [2] * request.children
        + [3] * request.infants_in_seat
        + [4] * request.infants_on_lap
    )


def _direction_legs(direction: Direction | None) -> list[Any]:
    if direction is None:
        return []
    return [
        SelectedFlight(
            origin=leg.origin,
            date=leg.departure.date().isoformat(),
            destination=leg.destination,
            airline=leg.airline,
            flight_number=leg.flight_number,
        )
        for leg in direction.legs
    ]


def build_tfs(
    request: SearchRequest,
    *,
    selected_outbound: Direction | None = None,
    selected_inbound: Direction | None = None,
    booking: bool = False,
) -> str:
    """Encode a search or complete itinerary using Google Flights protobuf fields."""
    info = Info()
    directions = [
        (
            request.departure_date,
            request.origin,
            request.destination,
            selected_outbound,
            request.outbound_earliest_departure_hour,
            request.outbound_latest_departure_hour,
        )
    ]
    if request.return_date:
        directions.append(
            (
                request.return_date,
                request.destination,
                request.origin,
                selected_inbound,
                request.return_earliest_departure_hour,
                request.return_latest_departure_hour,
            )
        )
    for travel_date, origin, destination, selected_direction, earliest, latest in directions:
        segment = info.data.add(date=travel_date)
        segment.from_airport.add(airport=origin)
        segment.to_airport.add(airport=destination)
        segment.selected_flights.extend(_direction_legs(selected_direction))
        if request.max_stops is not None:
            segment.max_stops = request.max_stops
        segment.airlines.extend(request.airlines)
        if earliest is not None:
            segment.earliest_departure_hour = earliest
        if latest is not None:
            segment.latest_departure_hour = latest
        if request.max_duration_minutes is not None:
            segment.max_duration_minutes = request.max_duration_minutes
        segment.connecting_airports.extend(request.connecting_airports)
        if request.min_layover_minutes is not None:
            segment.min_layover_minutes = request.min_layover_minutes
        if request.max_layover_minutes is not None:
            segment.max_layover_minutes = request.max_layover_minutes
        if request.less_emissions:
            segment.emissions.append(1)

    info.passengers.extend(_passengers(request))
    info.seat = _CABINS[request.cabin]
    info.trip = 1 if request.return_date else 2
    if request.max_price is not None:
        info.max_price = request.max_price
    if request.carry_on_bags is not None:
        info.baggage.carry_on_bags = request.carry_on_bags
    if request.checked_bags is not None:
        info.baggage.checked_bags = request.checked_bags
    if request.hide_separate_and_self_transfer is not None:
        info.hide_separate_and_self_transfer = request.hide_separate_and_self_transfer
    if request.exclude_basic_economy is not None:
        info.exclude_basic_economy = request.exclude_basic_economy
    if booking:
        if selected_outbound is None or (request.return_date and selected_inbound is None):
            raise ValueError("booking links require every direction to be selected")
        info.marker_one = 28
        info.marker_two = 2
        info.marker_fourteen = 1
        info.pin.value = (1 << 64) - 1
    return base64.urlsafe_b64encode(info.SerializeToString()).decode("ascii").rstrip("=")


def _url(path: str, token: str, request: SearchRequest) -> str:
    query = urlencode(
        {"tfs": token, "hl": request.language, "gl": request.country, "curr": request.currency}
    )
    return f"https://www.google.com/travel/flights/{path}?{query}"


def build_search_url(request: SearchRequest, *, selected_outbound: Direction | None = None) -> str:
    return _url("search", build_tfs(request, selected_outbound=selected_outbound), request)


def build_booking_url(
    request: SearchRequest, outbound: Direction, inbound: Direction | None = None
) -> str:
    token = build_tfs(
        request,
        selected_outbound=outbound,
        selected_inbound=inbound,
        booking=True,
    )
    return _url("booking", token, request)
