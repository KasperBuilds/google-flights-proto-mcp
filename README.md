# Google Flights Protobuf MCP

Reverse engineered Google Flights and coded a lil smth to help plan my flights across Europe! 

A standalone MCP server for this deliberately bounded pipeline:

```text
protobuf tfs query
  -> browser-impersonating HTTP discovery
  -> outbound/return pairing
  -> deterministic ranking
  -> top 1-3 exact /booking?tfs= links
  -> Playwright price + itinerary verification
```

## How the protobuf reverse-engineering works

Google Flights does not expose a supported public shopping API. Its web UI
stores the search state in the `tfs` query parameter used by URLs such as:

```text
https://www.google.com/travel/flights/search?tfs=<URL_SAFE_BASE64>&hl=en&gl=PT&curr=EUR
```

The `tfs` value is a serialized Protocol Buffers message encoded with URL-safe
Base64 and stripped of trailing `=` padding. The schema in
[`flights.proto`](src/google_flights_proto_mcp/flights.proto) is inferred from
the web application; it is not published or guaranteed by Google.

The encoder follows this path:

```text
SearchRequest
  -> Info protobuf
      -> FlightData for each direction
      -> airports, dates, stops, airlines and time filters
      -> passengers, cabin, baggage, trip type and maximum price
  -> SerializeToString()
  -> URL-safe Base64 without padding
  -> /travel/flights/search?tfs=...
```

Important inferred fields include:

| Message | Field | Meaning used here |
| --- | ---: | --- |
| `Info` | 3 | Repeated outbound/inbound `FlightData` directions |
| `Info` | 8 | Repeated passenger types |
| `Info` | 9 | Cabin/seat class |
| `Info` | 12 | Maximum fare filter |
| `Info` | 13 | Baggage filters |
| `Info` | 19 | Round trip or one way |
| `FlightData` | 2 | Travel date |
| `FlightData` | 4 | Selected physical flight legs |
| `FlightData` | 5 | Maximum stops |
| `FlightData` | 6 | Airline filters |
| `FlightData` | 13 / 14 | Origin and destination airports |

The schema was reconstructed by changing one Google Flights control at a
time, decoding the resulting Base64 tokens, comparing protobuf wire tags, and
then validating the inferred type and field number by generating a new URL.
Unknown booking-only fields retain neutral names such as `marker_one`; the
project does not claim semantics that have not been demonstrated.

### Why complete itinerary pairing takes two searches

A return fare cannot safely be produced by adding the cheapest outbound and
cheapest inbound. Google reprices the trip after the outbound is selected.
This project therefore:

1. searches and parses the available outbound directions;
2. embeds one selected outbound in field 4 of the outbound `FlightData`;
3. requests the repriced inbound choices for that selection;
4. pairs each inbound with that outbound and keeps Google's combined total;
5. embeds every physical leg from both directions in a booking `tfs` token.

This creates a deep link for one complete itinerary instead of a generic
route/date search. Search-page prices are still discovery quotes until the
Playwright verifier confirms the rendered total and provider handoff.

### HTTP discovery is not an API

The fast discovery layer requests the normal Google Flights HTML using a
browser-compatible TLS fingerprint. It extracts the embedded `ds:1` data from
`AF_initDataCallback`, parses both the top and other-flight groups, and rejects
consent pages, CAPTCHA responses, malformed payloads, and airport
substitutions. There is no stable JSON endpoint involved.

Google can change the protobuf schema, the embedded array layout, consent
handling, or anti-automation policy at any time. The parsers are defensive,
but this integration requires monitoring and should not be treated as a
contracted production API. Use it responsibly and comply with Google's terms
and applicable law.

The original public demonstration of this general `tfs` protobuf technique is
the [`AWeirdDev/flights`](https://github.com/AWeirdDev/flights) project. This
repository reimplements the schema and adds complete itinerary pairing,
ranking, explicit verification states, MCP tools, the semester scanner, and
the Railway dashboard.

## Install and run

```bash
cd google-flights-proto-mcp
uv sync --all-extras
uv run google-flights-proto-mcp
```

For streamable HTTP MCP:

```bash
uv run google-flights-proto-mcp-http
```

The default endpoint is `http://127.0.0.1:8010/mcp/`. HTTP clients must send:

```text
Accept: application/json, text/event-stream
```

Set `HOST` and `PORT` to change the bind address. Browser discovery prefers an
installed Chrome/Chromium automatically. Override it with:

```bash
export GOOGLE_FLIGHTS_MCP_BROWSER_EXECUTABLE=/path/to/chrome
```

If Google rotates its EU consent cookie, set
`GOOGLE_FLIGHTS_MCP_SOCS_COOKIE`. The default is a consent-choice cookie, not
an account/session credential.

## MCP tools

- `build_protobuf_search_url`: builds a search URL without network access.
- `discover_and_rank_complete`: fast HTTP discovery, full round-trip pairing,
  ranking, and top 1-3 exact booking links. Its prices are explicitly marked as
  discovery prices.
- `search_and_verify_top`: the full pipeline. A price is verified only at
  `shortlist[].verification.verified_price` when `verified` is true.

The `discovered_price` is Google Flights' HTTP shopping price for a fully
paired itinerary. It must never be relabelled as browser-verified. Exact
booking URLs pin dates, airports, passengers, cabin, airlines, and flight
numbers in protobuf; they do not freeze inventory or price.

## Ranking

Ranking operates only on completed itinerary pairs:

- 50% total price
- 25% useful time at the destination
- 15% total flight time
- 10% stops

The initial outbound list is trimmed by price/stops/duration only to bound HTTP
fan-out. That preliminary trim is not presented as the final ranking.

## Verification contract

Playwright opens the exact `/travel/flights/booking?tfs=...` page and requires:

- the rendered `Lowest total price` amount;
- the encoded passenger count and cabin;
- all encoded flight legs and dates;
- Google's required-taxes-and-fees notice;
- a same-priced booking option and a successful provider handoff that repeats
  the same total.

On any mismatch or anti-automation challenge, `verified_price` remains null.
Even a provider-confirmed price can change before purchase, and optional
baggage or payment charges may still apply.

## Fast weekend price scanner (no MCP, no Playwright)

For broad destination discovery, use the search-page scanner directly:

```bash
uv run python scripts/search_weekend_prices.py --top 5 --workers 4
```

The scanner defaults to one adult. Override it explicitly with `--adults N`
when a different passenger count is needed.

It reads `config/semester_2026.json`, generates one
`/travel/flights/search?tfs=<protobuf>` URL per airport/weekend, fetches the
embedded Google search results, rejects alternate-airport substitutions, and
writes ranked JSON and CSV files under `outputs/`.

Useful overrides:

```bash
uv run python scripts/search_weekend_prices.py \
  --weekend '25–28 Sep' \
  --destinations BCN,FNC,NCE,MAD \
  --max-stops 1 \
  --max-price 500 \
  --airlines U2,VY,FR
```

These are live Google **search-page quotes**, not checkout-verified prices.
The scanner records anti-automation failures separately and never converts a
blocked query into a false “no flights” result.

Travel windows can include an `availability_note` plus earliest outbound and
return hours. Exam-day windows use a realistic airport buffer: an assessment
ending at 19:30 does not permit a 21:00 departure.
When Friday has no exam, the corresponding search window starts at 23:00 on
Thursday so a useful extra evening flight is eligible without assuming the
traveller is free earlier that day.

## Bucket-list deal ranking

After scanning the bucket-list airport universe, compare every destination
with its own median quote across the semester windows and build the
coverage-first plan:

```bash
uv run python scripts/rank_bucket_deals.py
```

The output calls this baseline `semester_window_median`. It is an auditable
comparison within this scan, not Google's historical “typical price” signal.

## Hourly Google Sheet refresh on macOS

`scripts/refresh_google_sheet.py` runs the bucket-airport scan for one adult,
retries transient failures, recalculates route medians, ranks every eligible
option, publishes the top three per weekend to the Sheet, and overwrites only
the values in `3 per Weekend!A2` and
`3 per Weekend!A5:N43`. Existing formatting and conditional-format rules are
preserved. The last good Sheet remains untouched if the scan is incomplete.
The default retry policy uses two workers and paced backoff because a complete
104-destination scan across 13 windows makes 1,352 Google searches and can
encounter HTTP 429 responses.

The job uses the official Google Sheets API for workbook writes. Create a
Google Cloud service account, enable the Google Sheets API, download its JSON
key outside this repository, and share the workbook with the service account's
`client_email` as an editor. Then test without changing the Sheet:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json \
  uv run python scripts/refresh_google_sheet.py --dry-run
```

Run one real refresh:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json \
  uv run python scripts/refresh_google_sheet.py
```

For an hourly macOS job, copy
`com.kasperhong.fli-sheet-refresh.plist.example` to
`/Users/kasperhong/Library/LaunchAgents/com.kasperhong.fli-sheet-refresh.plist`,
change the credentials path if needed, and load it:

```bash
launchctl bootstrap gui/$(id -u) \
  /Users/kasperhong/Library/LaunchAgents/com.kasperhong.fli-sheet-refresh.plist
```

Inspect the log at `outputs/hourly-refresh.log`. To reload after editing the
plist, boot it out first and then bootstrap it again:

```bash
launchctl bootout gui/$(id -u) \
  /Users/kasperhong/Library/LaunchAgents/com.kasperhong.fli-sheet-refresh.plist
```

The hourly rows remain Google search-page quotes. Provider-checkout Playwright
verification is intentionally not run across the full route universe each
hour; that should be limited to the current top one to three candidates.

## Railway website

The Railway-ready FastAPI dashboard serves the last successful snapshot
immediately and refreshes prices in the background. It includes:

- every realistic option found under the hard €250 return ceiling, with the
  top three shown by default, a global Top 3 / All options switch, and
  per-weekend expansion;
- exact one-adult protobuf Google Flights links;
- hourly scanning, median recalculation, and reranking;
- atomic snapshot publishing so blocked scans never replace good data;
- `/healthz`, `/api/status`, and `/api/deals` endpoints;
- an optional token-protected `POST /api/refresh` endpoint.

Run it locally without starting background Google searches:

```bash
FLI_REFRESH_ENABLED=false uv run google-flights-proto-web
```

Then open `http://127.0.0.1:8000`.

For Railway, deploy this directory as the service root. Railway detects the
included `Dockerfile`, starts the server on its injected `PORT`, and checks
`/healthz`. Add a persistent volume mounted at `/data` so successful snapshots
survive deployments. Use one replica; multiple replicas would each run their
own scanner.

Optional Railway variables:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `FLI_REFRESH_ENABLED` | `true` | Enable the background worker |
| `FLI_REFRESH_ON_STARTUP` | `true` | Start a refresh after boot |
| `FLI_REFRESH_INTERVAL_SECONDS` | `3600` | Refresh interval |
| `FLI_REFRESH_WORKERS` | `2` | Concurrent Google requests |
| `FLI_REFRESH_RETRY_PASSES` | `6` | Maximum retry passes |
| `FLI_REFRESH_RETRY_DELAY_SECONDS` | `10` | Linear retry backoff |
| `FLI_ADMIN_TOKEN` | unset | Enables authenticated manual refresh |

Manual refresh, when `FLI_ADMIN_TOKEN` is configured:

```bash
curl -X POST -H "X-Refresh-Token: YOUR_TOKEN" \
  https://YOUR-DOMAIN/api/refresh
```

The website intentionally labels prices as search-page quotes. Hosting does
not turn them into checkout-verified fares, and Railway datacenter IPs may be
rate-limited more often than a residential connection.
