"""Normalize MCP results and add planning metadata for spreadsheet authoring."""

# ruff: noqa: E501 -- long prose remains readable as one spreadsheet-cell value.

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

META = {
    "FNC": (
        "Madeira",
        "Portugal",
        10,
        8,
        9,
        10,
        7,
        "Moderate",
        "10–15",
        "16–25",
        "2–5",
        "Espetada; bolo do caco; black scabbardfish; passion-fruit pudding; pastel de nata",
        "PR1/PR8 trails, volcanic peaks, levada walks and dramatic Atlantic viewpoints.",
        "Funchal is compact and pleasant, with markets, pastry cafés and affordable Madeiran food.",
    ),
    "NCE": (
        "Nice",
        "France",
        7,
        9,
        9,
        9,
        5,
        "Moderate–expensive",
        "15–22",
        "25–40",
        "4–9",
        "Socca; pissaladière; salade niçoise; tarte tropézienne; artisanal ice cream",
        "Riviera coast, Castle Hill, Èze and coastal walks; Monaco is an easy rail day trip.",
        "A beautiful old town, markets, excellent bakeries and romantic promenades; restaurant prices require care.",
    ),
    "MXP": (
        "Milan",
        "Italy",
        5,
        10,
        8,
        8,
        6,
        "Moderate",
        "12–18",
        "20–32",
        "3–7",
        "Risotto alla Milanese; cotoletta; panzerotti; gelato; tiramisù",
        "Urban trip with possible Lake Como or Alpine day trip, though MXP transfers consume time.",
        "Superb pasta, aperitivo, pastries and gelato in elegant walkable neighbourhoods.",
    ),
    "BCN": (
        "Barcelona",
        "Spain",
        6,
        9,
        9,
        10,
        7,
        "Moderate",
        "12–18",
        "20–30",
        "3–7",
        "Pa amb tomàquet; bombas; crema catalana; churros; gelato",
        "Mediterranean coast, Montjuïc viewpoints and nearby Montserrat hiking.",
        "Atmospheric streets, markets, tapas and strong dessert/café options at varied prices.",
    ),
    "PRG": (
        "Prague",
        "Czechia",
        5,
        9,
        9,
        10,
        9,
        "Cheap–moderate",
        "8–13",
        "15–25",
        "3–6",
        "Svíčková; roast duck; koláče; větrník; medovník",
        "River viewpoints and parks rather than major wilderness; Bohemian day trips are possible.",
        "Fairytale streets, historic cafés, Central European cakes and strong value.",
    ),
    "BGY": (
        "Bergamo",
        "Italy",
        7,
        9,
        9,
        10,
        9,
        "Cheap–moderate",
        "10–15",
        "18–28",
        "3–6",
        "Casoncelli; polenta taragna; stracciatella gelato; tiramisù; pastries",
        "Hilltop old city, foothill scenery and access toward lakes and the Alps.",
        "Città Alta is highly romantic and photogenic, with excellent, reasonably priced Lombard food.",
    ),
    "BER": (
        "Berlin",
        "Germany",
        4,
        8,
        7,
        8,
        7,
        "Moderate",
        "12–18",
        "20–32",
        "3–7",
        "Currywurst; döner; Berliner Pfannkuchen; cheesecake; specialty coffee",
        "Mostly urban, with parks, lakes and day-trip nature around Brandenburg.",
        "Huge affordable international food scene, bakeries and characterful neighbourhood walks.",
    ),
    "MAD": (
        "Madrid",
        "Spain",
        5,
        9,
        8,
        9,
        9,
        "Cheap–moderate",
        "11–17",
        "18–28",
        "3–6",
        "Cocido; tortilla; bocadillo de calamares; churros; torrijas",
        "Large parks, viewpoints and possible Sierra de Guadarrama day trip.",
        "Lively, walkable centre with excellent tapas, pastries and late-night couple atmosphere.",
    ),
    "LHR": (
        "London",
        "United Kingdom",
        4,
        10,
        8,
        9,
        3,
        "Expensive",
        "18–27",
        "30–50",
        "4–10",
        "Sunday roast; pies; sticky toffee pudding; scones; international street food",
        "Urban parks and Thames walks; major scenery requires a longer day trip.",
        "World-class food and desserts with beautiful neighbourhoods, but meals and transport are costly.",
    ),
    "DUB": (
        "Dublin & west-coast day trip",
        "Ireland",
        9,
        7,
        8,
        9,
        5,
        "Moderate–expensive",
        "15–22",
        "25–40",
        "4–8",
        "Irish stew; seafood chowder; soda bread; apple tart; scones",
        "Best route for the Cliffs of Moher/Wild Atlantic Way, though the day trip is long from Dublin.",
        "Friendly compact centre, pubs and cafés; desserts are good but overall prices are not low.",
    ),
    "BRU": (
        "Brussels",
        "Belgium",
        4,
        10,
        8,
        9,
        6,
        "Moderate",
        "15–22",
        "25–40",
        "4–9",
        "Moules-frites; carbonnade; waffles; pralines; speculoos",
        "Primarily an architecture and city trip; forests and countryside sit outside the centre.",
        "One of the strongest dessert choices: waffles, chocolate, pastries and photogenic squares.",
    ),
    "RAK": (
        "Marrakech & Atlas",
        "Morocco",
        9,
        9,
        8,
        10,
        9,
        "Cheap",
        "4–8",
        "10–18",
        "2–5",
        "Tagine; tanjia; msemen; chebakia; orange-blossom pastries",
        "Atlas Mountains are realistic; a full Sahara tour needs more than a normal weekend.",
        "Colourful riads and souks, excellent affordable food, mint tea and pastries; bargaining is normal.",
    ),
    "FCO": (
        "Rome",
        "Italy",
        5,
        10,
        10,
        10,
        7,
        "Moderate",
        "10–16",
        "18–30",
        "3–7",
        "Carbonara; cacio e pepe; supplì; maritozzo; gelato",
        "Mostly urban archaeology and parks; coast and hill towns are possible side trips.",
        "Exceptional couple city for pasta, pizza, maritozzi, tiramisù and gelato.",
    ),
    "BUD": (
        "Budapest",
        "Hungary",
        5,
        9,
        9,
        10,
        10,
        "Cheap–moderate",
        "7–12",
        "14–22",
        "3–6",
        "Goulash; lángos; chimney cake; Dobos torte; rétes",
        "Danube and Buda Hills viewpoints give a scenic urban-nature mix.",
        "Romantic riverfront, thermal baths, grand cafés and excellent-value cakes.",
    ),
    "VIE": (
        "Vienna",
        "Austria",
        5,
        10,
        9,
        10,
        5,
        "Moderate–expensive",
        "12–18",
        "20–35",
        "4–8",
        "Schnitzel; tafelspitz; Sachertorte; apfelstrudel; Kaiserschmarrn",
        "Vienna Woods and Danube scenery complement an otherwise city-heavy trip.",
        "Perhaps the strongest classic café-and-cake culture, with elegant streets and Christmas markets.",
    ),
    "KEF": (
        "Reykjavík & south Iceland",
        "Iceland",
        10,
        6,
        9,
        10,
        2,
        "Very expensive",
        "20–30",
        "35–60",
        "6–12",
        "Lamb soup; fish; skyr; cinnamon buns; kleinur",
        "Waterfalls, black-sand coast, geothermal landscapes and aurora potential; daylight is limited.",
        "Cosy cafés and a charming centre, but food and tours are among the most expensive options.",
    ),
    "HEL": (
        "Helsinki",
        "Finland",
        6,
        8,
        8,
        8,
        4,
        "Expensive",
        "14–20",
        "25–40",
        "4–8",
        "Salmon soup; Karelian pies; korvapuusti; Runeberg torte; Fazer chocolate",
        "Coastal islands and snowy parks; Helsinki itself is not a dependable aurora base.",
        "Clean design city with excellent cinnamon buns, chocolate and cosy cafés.",
    ),
    "TOS": (
        "Tromsø",
        "Norway",
        10,
        7,
        9,
        10,
        2,
        "Very expensive",
        "20–30",
        "35–55",
        "6–10",
        "Reindeer; Arctic char; fish soup; skolebrød; waffles",
        "Best aurora base, with fjords, snowy mountains and winter excursions; polar-night conditions apply.",
        "Compact atmospheric centre and cosy cafés, though restaurant and tour costs are high.",
    ),
    "CPH": (
        "Copenhagen",
        "Denmark",
        4,
        10,
        9,
        10,
        2,
        "Very expensive",
        "18–28",
        "35–60",
        "6–12",
        "Smørrebrød; hot dogs; kanelsnegle; cardamom buns; flødeboller",
        "A city-first trip with harbour scenery and coastal walks.",
        "Outstanding bakeries, desserts, design streets and couple atmosphere, at high prices.",
    ),
    "RVN": (
        "Rovaniemi",
        "Finland",
        10,
        7,
        9,
        10,
        2,
        "Very expensive",
        "18–28",
        "30–50",
        "5–10",
        "Salmon soup; sautéed reindeer; leipäjuusto; pulla; cloudberry desserts",
        "Lapland snow, forests, frozen landscapes and good aurora potential.",
        "Festive winter atmosphere and cosy cafés, but Christmas-season pricing is extremely high.",
    ),
    "EDI": (
        "Edinburgh & Highlands gateway",
        "United Kingdom",
        9,
        8,
        9,
        10,
        4,
        "Moderate–expensive",
        "15–22",
        "25–40",
        "4–8",
        "Haggis; cullen skink; shortbread; cranachan; sticky toffee pudding",
        "Arthur's Seat, dramatic coast and access toward the Highlands make this the scenery-led city option.",
        "A highly walkable historic centre with atmospheric pubs, bakeries and cosy cafés.",
    ),
}

# STN is a London airport request; destination planning metadata is shared with LHR.
META["STN"] = META["LHR"]

WEATHER = {
    ("FNC", 9): "Typically 22–26°C; warm, humid and mostly pleasant, with brief showers possible.",
    ("NCE", 9): "Typically 20–25°C; warm Riviera weather, with occasional thunderstorms.",
    ("MXP", 9): "Typically 17–25°C; mild to warm, with some rain or haze.",
    ("NCE", 10): "Typically 15–22°C; mild coast, mixed sun and rain; sea swimming is less certain.",
    ("MXP", 10): "Typically 11–20°C; cooler and changeable, with rain/fog possible.",
    ("PRG", 10): "Typically 7–15°C; crisp autumn, rain and chilly evenings.",
    ("BGY", 10): "Typically 9–18°C; autumn colour, but rain and low cloud can affect views.",
    ("BER", 10): "Typically 7–15°C; cool, often cloudy and occasionally wet.",
    ("BCN", 10): "Typically 15–22°C; mild, with occasional heavy Mediterranean rain.",
    ("MAD", 10): "Typically 10–20°C; generally dry and pleasant, cooler at night.",
    ("LHR", 10): "Typically 9–16°C; cool, changeable and frequently showery.",
    ("STN", 10): "Typically 9–16°C; cool, changeable and frequently showery.",
    ("EDI", 10): "Typically 7–13°C; windy and showery, with short daylight and rapid changes.",
    ("DUB", 10): "Typically 8–14°C; windy and wet spells likely, especially on the Atlantic coast.",
    ("BRU", 10): "Typically 8–15°C; cool with frequent cloud and showers.",
    ("RAK", 10): "Typically 15–28°C; warm and mostly dry, with cooler Atlas evenings.",
    ("RAK", 11): "Typically 11–23°C; sunny days, cool nights; Atlas summits may have early snow.",
    ("FCO", 11): "Typically 10–18°C; mild but November is among Rome’s wetter periods.",
    ("PRG", 11): "Typically 2–9°C; cold, grey and sometimes frosty.",
    ("BUD", 11): "Typically 3–10°C; chilly with fog or rain possible.",
    ("VIE", 11): "Typically 3–10°C; cold and often cloudy; early Christmas-market season.",
    ("KEF", 11): "Typically 0–5°C; stormy, icy and only about 5–6 daylight hours; aurora possible.",
    ("HEL", 11): "Typically −1–5°C; dark, wet or snowy; aurora is uncommon in the city.",
    (
        "TOS",
        11,
    ): "Typically −4–2°C; snowy/icy with very short daylight and strong aurora potential.",
    (
        "KEF",
        12,
    ): "Typically −2–4°C; roughly 4–5 daylight hours, high wind/road-closure risk, aurora possible.",
    ("HEL", 12): "Typically −5–2°C; about 6 daylight hours, with snow or freeze-thaw conditions.",
    (
        "TOS",
        12,
    ): "Typically −6–1°C; polar night, snow/ice and excellent darkness for aurora when clear.",
    ("CPH", 12): "Typically 1–6°C; dark, windy and damp, with festive city atmosphere.",
    (
        "RVN",
        12,
    ): "Typically −15–−5°C; deep snow, very limited daylight and strong cold-weather risk.",
}


def deal_label(total: float | None) -> str:
    if total is None:
        return "Google page not verified"
    per_person = total / 2
    if per_person <= 80:
        return "Excellent absolute value; no historical baseline"
    if per_person <= 125:
        return "Good absolute value; no historical baseline"
    if per_person <= 200:
        return "Fair; compare before booking"
    if per_person <= 350:
        return "High"
    return "Very high"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / "outputs" / "semester_search.json").read_text())
    rows = []
    for entry in source["results"]:
        shortlist = entry["result"].get("shortlist", [])
        item = shortlist[0] if shortlist else None
        verification = (item or {}).get("verification") or {}
        meta = META[entry["destination"]]
        out_legs = (item or {}).get("outbound", {}).get("legs", [])
        in_legs = (item or {}).get("inbound", {}).get("legs", [])
        checks = verification.get("checks") or {}
        google_page_matched = bool(
            checks.get("google_page_verified")
            and checks.get("booking_option_price_matches")
        )
        google_price = verification.get("observed_price") if google_page_matched else None
        checkout_price = verification.get("verified_price")
        month = int(entry["departure_date"][5:7])
        row = {
            "weekend": entry["weekend"],
            "departure_date": entry["departure_date"],
            "return_date": entry["return_date"],
            "destination_code": entry["destination"],
            "destination": meta[0],
            "country": meta[1],
            "verified": bool(verification.get("verified")),
            "verified_total_eur": checkout_price,
            "google_page_matched": google_page_matched,
            "google_displayed_total_eur": google_price,
            "price_per_person_eur": google_price / 2 if google_price is not None else None,
            "checked_at": verification.get("checked_at"),
            "provider_verification_result": verification.get("error"),
            "outbound": " / ".join(
                f"{leg['airline']}{leg['flight_number']} {leg['origin']}–{leg['destination']} "
                f"{leg['departure'][11:16]}–{leg['arrival'][11:16]}"
                for leg in out_legs
            ),
            "inbound": " / ".join(
                f"{leg['airline']}{leg['flight_number']} {leg['origin']}–{leg['destination']} "
                f"{leg['departure'][11:16]}–{leg['arrival'][11:16]}"
                for leg in in_legs
            ),
            "stops_total": (item or {}).get("total_stops"),
            "useful_hours": (item or {}).get("useful_destination_hours"),
            "booking_url": (item or {}).get("booking_url"),
            "nature_score": meta[2],
            "food_score": meta[3],
            "couple_score": meta[4],
            "photo_score": meta[5],
            "budget_score": meta[6],
            "food_cost": meta[7],
            "cheap_meal_eur": meta[8],
            "casual_meal_eur": meta[9],
            "dessert_cafe_eur": meta[10],
            "foods": meta[11],
            "for_me": meta[12],
            "for_girlfriend": meta[13],
            "weather": WEATHER.get(
                (entry["destination"], month),
                "Seasonal conditions vary; check the forecast before booking.",
            ),
            "deal_quality": deal_label(google_price),
        }
        rows.append(row)

    groups = defaultdict(list)
    for row in rows:
        groups[row["weekend"]].append(row)
    for group in groups.values():
        valid = [row for row in group if row["google_displayed_total_eur"] is not None]
        prices = [row["google_displayed_total_eur"] for row in valid]
        hours = [row["useful_hours"] for row in valid]
        for row in valid:
            price_component = (
                1
                if max(prices) == min(prices)
                else (max(prices) - row["google_displayed_total_eur"])
                / (max(prices) - min(prices))
            )
            hour_component = (
                1
                if max(hours) == min(hours)
                else (row["useful_hours"] - min(hours)) / (max(hours) - min(hours))
            )
            quality = (
                row["nature_score"]
                + row["food_score"]
                + row["couple_score"]
                + row["photo_score"]
                + row["budget_score"]
            ) / 50
            row["overall_score"] = round(
                100 * (0.45 * price_component + 0.15 * hour_component + 0.40 * quality), 1
            )
        valid.sort(
            key=lambda row: (-row["overall_score"], row["google_displayed_total_eur"])
        )
        for rank, row in enumerate(valid, 1):
            row["weekend_rank"] = rank
        for row in group:
            if row not in valid:
                row["overall_score"] = None
                row["weekend_rank"] = None

    rows.sort(
        key=lambda row: (
            row["departure_date"],
            row["weekend_rank"] is None,
            row["weekend_rank"] or 999,
        )
    )
    out = {
        "generated_at": source["generated_at"],
        "method": (
            "Google-displayed totals matched exact itineraries and same-priced Google booking "
            "options for one adult. Provider checkout confirmation is tracked separately; "
            "destination scores and meal ranges are planning estimates."
        ),
        "rows": rows,
    }
    output = root / "outputs" / "semester_ranked.json"
    output.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
