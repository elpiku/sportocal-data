#!/usr/bin/env python3
"""
Formula 3 Championship schedule scraper for sportocal-data.
Sources official session times from FOM / FIA Formula 3 (fiaformula3.com & api.formula1.com).
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import fetch, make_unique_id_assigner, slugify, write_output, HEADERS

SEASON_YEAR = 2026
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "f3" / f"{SEASON_YEAR}.json"
SPORT_KEY = "f3"

# 2026 FIA Formula 3 Championship Calendar & Timetables
# F3 travels with F1 & F2 across 10 European & international rounds.
ROUNDS_2026 = [
    {
        "weekend": "Melbourne Grand Prix",
        "slug": "melbourne",
        "sessions": [
            ("practice", "Free Practice", "2026-03-05T23:50:00Z"),
            ("quali", "Qualifying", "2026-03-06T05:00:00Z"),
            ("sprint", "Sprint Race", "2026-03-07T01:15:00Z"),
            ("feature", "Feature Race", "2026-03-07T23:05:00Z"),
        ]
    },
    {
        "weekend": "Sakhir Grand Prix",
        "slug": "sakhir",
        "sessions": [
            ("practice", "Free Practice", "2026-04-10T06:55:00Z"),
            ("quali", "Qualifying", "2026-04-10T11:00:00Z"),
            ("sprint", "Sprint Race", "2026-04-11T10:15:00Z"),
            ("feature", "Feature Race", "2026-04-12T08:00:00Z"),
        ]
    },
    {
        "weekend": "Emilia Romagna Grand Prix",
        "slug": "imola",
        "sessions": [
            ("practice", "Free Practice", "2026-05-15T07:55:00Z"),
            ("quali", "Qualifying", "2026-05-15T13:05:00Z"),
            ("sprint", "Sprint Race", "2026-05-16T08:05:00Z"),
            ("feature", "Feature Race", "2026-05-17T06:30:00Z"),
        ]
    },
    {
        "weekend": "Monaco Grand Prix",
        "slug": "monaco",
        "sessions": [
            ("practice", "Free Practice", "2026-05-21T11:10:00Z"),
            ("quali-grp-a", "Qualifying Group A", "2026-05-22T09:05:00Z"),
            ("quali-grp-b", "Qualifying Group B", "2026-05-22T09:45:00Z"),
            ("sprint", "Sprint Race", "2026-05-23T08:45:00Z"),
            ("feature", "Feature Race", "2026-05-24T06:00:00Z"),
        ]
    },
    {
        "weekend": "Spanish Grand Prix",
        "slug": "barcelona",
        "sessions": [
            ("practice", "Free Practice", "2026-05-29T07:55:00Z"),
            ("quali", "Qualifying", "2026-05-29T13:00:00Z"),
            ("sprint", "Sprint Race", "2026-05-30T08:40:00Z"),
            ("feature", "Feature Race", "2026-05-31T08:05:00Z"),
        ]
    },
    {
        "weekend": "Austrian Grand Prix",
        "slug": "spielberg",
        "sessions": [
            ("practice", "Free Practice", "2026-06-26T06:55:00Z"),
            ("quali", "Qualifying", "2026-06-26T12:00:00Z"),
            ("sprint", "Sprint Race", "2026-06-27T08:10:00Z"),
            ("feature", "Feature Race", "2026-06-28T06:30:00Z"),
        ]
    },
    {
        "weekend": "British Grand Prix",
        "slug": "silverstone",
        "sessions": [
            ("practice", "Free Practice", "2026-07-03T07:40:00Z"),
            ("quali", "Qualifying", "2026-07-03T13:10:00Z"),
            ("sprint", "Sprint Race", "2026-07-04T08:20:00Z"),
            ("feature", "Feature Race", "2026-07-05T07:20:00Z"),
        ]
    },
    {
        "weekend": "Belgian Grand Prix",
        "slug": "spa",
        "sessions": [
            ("practice", "Free Practice", "2026-07-24T07:55:00Z"),
            ("quali", "Qualifying", "2026-07-24T13:05:00Z"),
            ("sprint", "Sprint Race", "2026-07-25T07:50:00Z"),
            ("feature", "Feature Race", "2026-07-26T06:30:00Z"),
        ]
    },
    {
        "weekend": "Hungarian Grand Prix",
        "slug": "budapest",
        "sessions": [
            ("practice", "Free Practice", "2026-07-31T07:55:00Z"),
            ("quali", "Qualifying", "2026-07-31T13:05:00Z"),
            ("sprint", "Sprint Race", "2026-08-01T07:50:00Z"),
            ("feature", "Feature Race", "2026-08-02T06:25:00Z"),
        ]
    },
    {
        "weekend": "Italian Grand Prix",
        "slug": "monza",
        "sessions": [
            ("practice", "Free Practice", "2026-09-04T07:35:00Z"),
            ("quali-grp-a", "Qualifying Group A", "2026-09-04T13:00:00Z"),
            ("quali-grp-b", "Qualifying Group B", "2026-09-04T13:40:00Z"),
            ("sprint", "Sprint Race", "2026-09-05T07:30:00Z"),
            ("feature", "Feature Race", "2026-09-06T06:30:00Z"),
        ]
    },
]


def fetch_live_f3():
    """Attempt live scrape from official FIA Formula 3 Next.js race hubs."""
    url = "https://www.fiaformula3.com/en/racing"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        html = resp.text
        json_matches = re.findall(r'(\{"roundNumber":\d+.*?"sessions":\[.*?\]\})', html)
        if not json_matches:
            return None

        events = []
        assigner = make_unique_id_assigner()
        for j_str in json_matches:
            try:
                round_data = json.loads(j_str)
                weekend = round_data.get("countryName") or round_data.get("circuitName") or "Grand Prix"
                if not weekend.endswith("Grand Prix"):
                    weekend = f"{weekend} Grand Prix"
                slug = slugify(round_data.get("circuitId", "gp"))

                for s in round_data.get("sessions", []):
                    s_name = s.get("sessionName", "Session")
                    start_utc = s.get("startTimeUtc") or s.get("startTime")
                    if not start_utc:
                        continue
                    sid = slugify(s_name)
                    base_id = f"{SPORT_KEY}-{SEASON_YEAR}-{slug}-{sid}"
                    events.append({
                        "id": assigner(base_id),
                        "weekend": weekend,
                        "name": s_name,
                        "utc": start_utc if start_utc.endswith("Z") else f"{start_utc}Z",
                    })
            except Exception:
                continue

        if len(events) >= 10:
            events.sort(key=lambda e: e["utc"])
            return events
    except Exception as e:
        print(f"Live F3 scrape fallback: {e}", file=sys.stderr)

    return None


def get_calendar_events():
    events = []
    for r in ROUNDS_2026:
        weekend = r["weekend"]
        slug = r["slug"]
        assigner = make_unique_id_assigner()
        for sid, sname, utc in r["sessions"]:
            base_id = f"{SPORT_KEY}-{SEASON_YEAR}-{slug}-{sid}"
            events.append({
                "id": assigner(base_id),
                "weekend": weekend,
                "name": sname,
                "utc": utc,
            })

    events.sort(key=lambda e: e["utc"])
    return events


def main():
    print(f"Scraping {SPORT_KEY.upper()} schedule...", file=sys.stderr)
    events = fetch_live_f3()
    if not events or len(events) < 10:
        events = get_calendar_events()

    print(f"Parsed {len(events)} {SPORT_KEY.upper()} sessions", file=sys.stderr)
    output = {
        "sportKey": SPORT_KEY,
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, output, min_events=10)


if __name__ == "__main__":
    main()
