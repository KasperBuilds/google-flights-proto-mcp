from pathlib import Path

from fastapi.testclient import TestClient

from google_flights_proto_mcp.web import (
    BUCKET_LABELS_BY_AIRPORT,
    SEED_PATH,
    app,
    build_public_payload,
    load_ranked_snapshot,
)


def test_public_payload_respects_budget_cap() -> None:
    payload = build_public_payload(load_ranked_snapshot(SEED_PATH.parent))

    assert payload["passengers"] == 1
    assert payload["summary"]["weekends"] == 13
    assert payload["summary"]["options"] <= 39
    assert all(len(weekend["options"]) <= 3 for weekend in payload["weekends"])
    assert all(
        option["price"] <= 250 for weekend in payload["weekends"] for option in weekend["options"]
    )
    assert all(
        option["search_url"].startswith("https://www.google.com/travel/flights/search?tfs=")
        for weekend in payload["weekends"]
        for option in weekend["options"]
    )
    assert BUCKET_LABELS_BY_AIRPORT["FCO"] == [{"name": "Italy", "type": "country"}]
    assert BUCKET_LABELS_BY_AIRPORT["TOS"] == [{"name": "Norway", "type": "country"}]
    assert any(
        option["on_bucket_list"] for weekend in payload["weekends"] for option in weekend["options"]
    )
    assert all(
        option["on_bucket_list"] == bool(option["bucket_list_labels"])
        for weekend in payload["weekends"]
        for option in weekend["options"]
    )


def test_web_routes_serve_snapshot(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLI_REFRESH_ENABLED", "false")
    monkeypatch.setenv("FLI_DATA_DIR", str(tmp_path))

    with TestClient(app) as client:
        homepage = client.get("/")
        deals = client.get("/api/deals")
        health = client.get("/healthz")
        manual = client.post("/api/refresh")

    assert homepage.status_code == 200
    assert "Weekend flights" in homepage.text
    assert 'data-filter="bucket"' in homepage.text
    assert deals.status_code == 200
    assert deals.json()["data"]["summary"]["options"] <= 39
    assert health.status_code == 200
    assert manual.status_code == 403
