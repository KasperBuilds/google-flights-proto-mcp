import json
from copy import deepcopy
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
    assert payload["summary"]["initial_options_per_weekend"] == 3
    assert payload["summary"]["initially_visible_options"] == sum(
        min(3, len(weekend["options"])) for weekend in payload["weekends"]
    )
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


def test_public_payload_keeps_options_beyond_initial_three() -> None:
    ranked = deepcopy(load_ranked_snapshot(SEED_PATH.parent))
    first_weekend = ranked["weekends"][0]["label"]
    existing = [item for item in ranked["weekend_options"] if item["weekend"] == first_weekend]
    extra = deepcopy(existing[0])
    extra["option"] = 4
    extra["destination"] = {"code": "ZZZ", "name": "Additional option"}
    ranked["weekend_options"].append(extra)
    ranked["website_initial_options"] = 3
    ranked["weekends"][0]["availability_note"] = "Exam buffer applies"

    payload = build_public_payload(ranked)
    weekend = next(item for item in payload["weekends"] if item["label"] == first_weekend)

    assert len(weekend["options"]) == 4
    assert [option["rank"] for option in weekend["options"]] == [1, 2, 3, 4]
    assert weekend["availability_note"] == "Exam buffer applies"
    assert payload["summary"]["initial_options_per_weekend"] == 3


def test_exam_windows_include_realistic_airport_buffers() -> None:
    config_path = SEED_PATH.parents[1] / "config" / "semester_2026.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    weekends = {weekend["label"]: weekend for weekend in config["weekends"]}

    assert weekends["16–19 Oct"]["outbound_earliest_hour"] == 23
    assert weekends["30 Oct–2 Nov"]["outbound_earliest_hour"] == 23
    assert weekends["11–14 Dec"]["outbound_earliest_hour"] == 14
    assert all(
        weekends[label].get("availability_note")
        for label in ("19–21 Sep", "16–19 Oct", "30 Oct–2 Nov", "11–14 Dec")
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
    assert 'data-view="top"' in homepage.text
    assert 'data-view="all"' in homepage.text
    assert deals.status_code == 200
    assert deals.json()["data"]["summary"]["options"] > 0
    assert health.status_code == 200
    assert manual.status_code == 403
