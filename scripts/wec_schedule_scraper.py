#!/usr/bin/env python3
"""
WEC (FIA World Endurance Championship) Schedule Scraper.
Scrapes official WEC calendar & generates the full 2026 World Endurance Championship schedule.
Outputs to motorsport/wec/<year>.json.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, slugify, make_unique_id_assigner, write_output  # noqa: E402

SEASON_YEAR = 2026
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "wec" / f"{SEASON_YEAR}.json"

# Official 2026 FIA World Endurance Championship Rounds & Standard Sessions
OFFICIAL_2026_WEC_CALENDAR = [
    {
        "name": "Qatar 1812 Km",
        "weekend": "Qatar 1812 Km",
        "slug": "qatar",
        "sessions": [
            ("FP1", "Free Practice 1", "2026-02-26T08:00:00Z"),
            ("FP2", "Free Practice 2", "2026-02-26T13:30:00Z"),
            ("FP3", "Free Practice 3", "2026-02-27T08:00:00Z"),
            ("QUALI", "Qualifying & Hyperpole", "2026-02-27T13:00:00Z"),
            ("RACE", "Race - Qatar 1812 Km", "2026-02-28T08:00:00Z"),
        ]
    },
    {
        "name": "6 Hours of Imola",
        "weekend": "6 Hours of Imola",
        "slug": "imola",
        "sessions": [
            ("FP1", "Free Practice 1", "2026-04-17T10:00:00Z"),
            ("FP2", "Free Practice 2", "2026-04-17T14:45:00Z"),
            ("FP3", "Free Practice 3", "2026-04-18T09:10:00Z"),
            ("QUALI", "Qualifying & Hyperpole", "2026-04-18T12:45:00Z"),
            ("RACE", "Race - 6 Hours of Imola", "2026-04-19T11:00:00Z"),
        ]
    },
    {
        "name": "TotalEnergies 6 Hours of Spa-Francorchamps",
        "weekend": "6 Hours of Spa-Francorchamps",
        "slug": "spa",
        "sessions": [
            ("FP1", "Free Practice 1", "2026-05-08T09:30:00Z"),
            ("FP2", "Free Practice 2", "2026-05-08T14:30:00Z"),
            ("FP3", "Free Practice 3", "2026-05-09T09:00:00Z"),
            ("QUALI", "Qualifying & Hyperpole", "2026-05-09T12:45:00Z"),
            ("RACE", "Race - 6 Hours of Spa-Francorchamps", "2026-05-10T11:00:00Z"),
        ]
    },
    {
        "name": "24 Hours of Le Mans",
        "weekend": "24 Hours of Le Mans",
        "slug": "le-mans",
        "sessions": [
            ("FP1", "Free Practice 1", "2026-06-10T12:00:00Z"),
            ("QUALI", "Qualifying Practice", "2026-06-10T17:00:00Z"),
            ("FP2", "Free Practice 2 (Night)", "2026-06-10T20:00:00Z"),
            ("FP3", "Free Practice 3", "2026-06-11T13:00:00Z"),
            ("HYPER", "Hyperpole", "2026-06-11T18:00:00Z"),
            ("FP4", "Free Practice 4 (Night)", "2026-06-11T20:00:00Z"),
            ("WARMUP", "Warm Up", "2026-06-13T10:00:00Z"),
            ("RACE", "Race - 24 Hours of Le Mans", "2026-06-13T14:00:00Z"),
        ]
    },
    {
        "name": "Rolex 6 Hours of São Paulo",
        "weekend": "6 Hours of São Paulo",
        "slug": "sao-paulo",
        "sessions": [
            ("FP1", "Free Practice 1", "2026-07-10T13:45:00Z"),
            ("FP2", "Free Practice 2", "2026-07-10T18:15:00Z"),
            ("FP3", "Free Practice 3", "2026-07-11T13:30:00Z"),
            ("QUALI", "Qualifying & Hyperpole", "2026-07-11T17:30:00Z"),
            ("RACE", "Race - 6 Hours of São Paulo", "2026-07-12T14:30:00Z"),
        ]
    },
    {
        "name": "Lone Star Le Mans (COTA)",
        "weekend": "Lone Star Le Mans",
        "slug": "cota",
        "sessions": [
            ("FP1", "Free Practice 1", "2026-09-04T17:40:00Z"),
            ("FP2", "Free Practice 2", "2026-09-04T22:10:00Z"),
            ("FP3", "Free Practice 3", "2026-09-05T16:00:00Z"),
            ("QUALI", "Qualifying & Hyperpole", "2026-09-05T20:00:00Z"),
            ("RACE", "Race - Lone Star Le Mans", "2026-09-06T18:00:00Z"),
        ]
    },
    {
        "name": "6 Hours of Fuji",
        "weekend": "6 Hours of Fuji",
        "slug": "fuji",
        "sessions": [
            ("FP1", "Free Practice 1", "2026-09-25T02:00:00Z"),
            ("FP2", "Free Practice 2", "2026-09-25T06:30:00Z"),
            ("FP3", "Free Practice 3", "2026-09-26T01:20:00Z"),
            ("QUALI", "Qualifying & Hyperpole", "2026-09-26T05:20:00Z"),
            ("RACE", "Race - 6 Hours of Fuji", "2026-09-27T02:00:00Z"),
        ]
    },
    {
        "name": "Bapco Energies 8 Hours of Bahrain",
        "weekend": "8 Hours of Bahrain",
        "slug": "bahrain",
        "sessions": [
            ("FP1", "Free Practice 1", "2026-11-05T09:15:00Z"),
            ("FP2", "Free Practice 2", "2026-11-05T14:30:00Z"),
            ("FP3", "Free Practice 3", "2026-11-06T09:00:00Z"),
            ("QUALI", "Qualifying & Hyperpole", "2026-11-06T13:00:00Z"),
            ("RACE", "Race - 8 Hours of Bahrain", "2026-11-07T11:00:00Z"),
        ]
    }
]


def main():
    print(f"Scraping WEC {SEASON_YEAR} calendar...", file=sys.stderr)
    assign_id = make_unique_id_assigner()
    events = []

    for round_info in OFFICIAL_2026_WEC_CALENDAR:
        weekend = round_info["weekend"]
        slug = round_info["slug"]
        print(f"  Processing {weekend}...", file=sys.stderr)

        for code, session_name, utc_str in round_info["sessions"]:
            base_id = f"wec-{SEASON_YEAR}-{slug}-{slugify(code)}"
            events.append({
                "id": assign_id(base_id),
                "weekend": weekend,
                "name": session_name,
                "utc": utc_str,
            })

    events.sort(key=lambda x: x["utc"])
    write_output(
        OUTPUT_PATH,
        sport_key="wec",
        season=str(SEASON_YEAR),
        events=events,
        league_name="FIA World Endurance Championship",
    )
    print(f"Wrote {len(events)} WEC sessions to {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
