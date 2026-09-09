import json

from google_flights_proto_mcp.discovery import extract_payload, parse_directions


def _row(price: int, flight_number: str) -> list:
    leg = [None] * 23
    leg[3] = "LIS"
    leg[6] = "FNC"
    leg[8] = [7, 30]
    leg[10] = [9, 15]
    leg[11] = 105
    leg[20] = [2026, 9, 19]
    leg[21] = [2026, 9, 19]
    leg[22] = ["FR", flight_number]
    detail = [None] * 14
    detail[2] = [leg]
    detail[9] = 105
    return [detail, [[None, price], None]]


def _html(payload: list) -> str:
    return (
        "<script>AF_initDataCallback({key: 'ds:1', hash: 'x', data:"
        + json.dumps(payload, separators=(",", ":"))
        + ", sideChannel: {}});</script>"
    )


def test_parser_reads_top_and_other_groups_and_deduplicates() -> None:
    top = _row(100, "123")
    other = _row(120, "456")
    payload = [None, None, [[top]], [[top, other]]]
    directions = parse_directions(_html(payload), "EUR")
    assert [direction.price for direction in directions] == [100.0, 120.0]
    assert directions[0].legs[0].flight_number == "123"


def test_extract_payload_rejects_pages_without_flight_data() -> None:
    try:
        extract_payload("<html>consent</html>")
    except Exception as exc:
        assert "no ds:1" in str(exc)
    else:
        raise AssertionError("missing payload must fail")
