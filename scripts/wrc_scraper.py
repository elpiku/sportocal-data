#!/usr/bin/env python3
"""
WRC (World Rally Championship) Data Scraper.
Scrapes official WRC calendar and rally itineraries from www.wrc.com.
Includes official FIA calendar fallback when wrc.com blocks Cloudflare/datacenter IPs with 403.
Outputs to motorsport/wrc/<year>.json and motorsport/wrc/schedule.json.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Official FIA 2026 World Rally Championship Calendar (World Motor Sport Council Approved)
OFFICIAL_2026_CALENDAR = [
    {
        "round": 1,
        "name": "Rallye Monte-Carlo",
        "url": "https://www.wrc.com/en/events/wrc-rallye-monte-carlo-2026",
        "start_dt": datetime(2026, 1, 22, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 1, 25, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 2,
        "name": "Rally Sweden",
        "url": "https://www.wrc.com/en/events/wrc-rally-sweden-2026",
        "start_dt": datetime(2026, 2, 12, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 2, 15, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 3,
        "name": "Safari Rally Kenya",
        "url": "https://www.wrc.com/en/events/wrc-safari-rally-kenya-2026",
        "start_dt": datetime(2026, 3, 12, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 3, 15, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 4,
        "name": "Croatia Rally",
        "url": "https://www.wrc.com/en/events/wrc-croatia-rally-2026",
        "start_dt": datetime(2026, 4, 9, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 4, 12, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 5,
        "name": "Rally Islas Canarias",
        "url": "https://www.wrc.com/en/events/wrc-rally-islas-canarias-2026",
        "start_dt": datetime(2026, 4, 23, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 4, 26, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 6,
        "name": "Vodafone Rally de Portugal",
        "url": "https://www.wrc.com/en/events/wrc-vodafone-rally-de-portugal-2026",
        "start_dt": datetime(2026, 5, 7, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 5, 10, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 7,
        "name": "FORUM8 Rally Japan",
        "url": "https://www.wrc.com/en/events/wrc-forum8-rally-japan-2026",
        "start_dt": datetime(2026, 5, 28, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 5, 31, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 8,
        "name": "EKO Acropolis Rally Greece",
        "url": "https://www.wrc.com/en/events/wrc-eko-acropolis-rally-greece-2026",
        "start_dt": datetime(2026, 6, 25, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 6, 28, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 9,
        "name": "Delfi Rally Estonia",
        "url": "https://www.wrc.com/en/events/wrc-delfi-rally-estonia-2026",
        "start_dt": datetime(2026, 7, 16, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 7, 19, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 10,
        "name": "Secto Rally Finland",
        "url": "https://www.wrc.com/en/events/wrc-secto-rally-finland-2026",
        "start_dt": datetime(2026, 7, 30, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 8, 2, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 11,
        "name": "ueno Rally del Paraguay",
        "url": "https://www.wrc.com/en/events/wrc-rally-del-paraguay-2026",
        "start_dt": datetime(2026, 8, 27, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 8, 30, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 12,
        "name": "Rally Chile Bio Bío",
        "url": "https://www.wrc.com/en/events/wrc-rally-chile-bio-bio-2026",
        "start_dt": datetime(2026, 9, 10, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 9, 13, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 13,
        "name": "Rally Italia Sardegna",
        "url": "https://www.wrc.com/en/events/wrc-rally-italia-sardegna-2026",
        "start_dt": datetime(2026, 10, 1, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 10, 4, 11, 15, tzinfo=timezone.utc),
    },
    {
        "round": 14,
        "name": "Rally Saudi Arabia",
        "url": "https://www.wrc.com/en/events/wrc-rally-saudi-arabia-2026",
        "start_dt": datetime(2026, 11, 11, 8, 1, tzinfo=timezone.utc),
        "end_dt": datetime(2026, 11, 14, 11, 15, tzinfo=timezone.utc),
    },
]


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def normalize_dashes(text: str) -> str:
    return text.replace("–", "-").replace("—", "-").replace("−", "-")


def parse_date_range(date_text: str, default_year: int) -> tuple[datetime | None, datetime | None]:
    date_text = normalize_dashes(date_text.strip().upper())
    try:
        m1 = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Z]+)\s+(\d{4})", date_text)
        if m1:
            start_day = int(m1.group(1))
            end_day = int(m1.group(2))
            month = MONTHS.get(m1.group(3), 1)
            year = int(m1.group(4))
            return (
                datetime(year, month, start_day, 8, 1, tzinfo=timezone.utc),
                datetime(year, month, end_day, 11, 15, tzinfo=timezone.utc),
            )

        m2 = re.search(r"(\d{1,2})\s+([A-Z]+)\s*-\s*(\d{1,2})\s+([A-Z]+)\s+(\d{4})", date_text)
        if m2:
            start_day = int(m2.group(1))
            start_month = MONTHS.get(m2.group(2), 1)
            end_day = int(m2.group(3))
            end_month = MONTHS.get(m2.group(4), 1)
            year = int(m2.group(5))
            return (
                datetime(year, start_month, start_day, 8, 1, tzinfo=timezone.utc),
                datetime(year, end_month, end_day, 11, 15, tzinfo=timezone.utc),
            )
    except Exception:
        pass

    return None, None


def scrape_calendar(year: int) -> list[dict]:
    url = "https://www.wrc.com/en/calendar"
    print(f"Fetching WRC calendar from {url}...", file=sys.stderr)
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            events = []
            seen_urls = set()

            rows = soup.find_all("tr")
            for row in rows:
                link = row.find("a", href=re.compile(r"/en/events/wrc-"))
                if not link:
                    continue
                href = link.get("href", "")
                full_url = href if href.startswith("http") else f"https://www.wrc.com{href}"
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                title = link.get_text(separator=" ", strip=True)
                row_text = row.get_text(separator=" ", strip=True)

                clean_name = re.sub(r"^[^\w\s]+", "", title).strip()
                if clean_name.startswith("WRC "):
                    clean_name = clean_name[4:].strip()

                start_dt, end_dt = parse_date_range(row_text, year)
                utc_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if start_dt else f"{year}-01-01T08:00:00Z"

                events.append({
                    "name": clean_name,
                    "url": full_url,
                    "raw_text": row_text,
                    "start_dt": start_dt,
                    "end_dt": end_dt,
                    "utc": utc_str,
                })

            if events:
                print(f"Scraped {len(events)} rally events from live calendar.", file=sys.stderr)
                return events
    except Exception as e:
        print(f"Note: Live calendar scrape returned {e}. Using official FIA championship calendar.", file=sys.stderr)

    # Fallback to official FIA 2026 Championship Calendar
    print(f"Using official 14-round FIA 2026 calendar.", file=sys.stderr)
    return [
        {
            "name": item["name"],
            "url": item["url"],
            "raw_text": item["name"],
            "start_dt": item["start_dt"],
            "end_dt": item["end_dt"],
            "utc": item["start_dt"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for item in OFFICIAL_2026_CALENDAR
    ]


def generate_standard_rally_sessions(event_info: dict, year: int, round_idx: int) -> list[dict]:
    rally_name = event_info["name"]
    start_dt = event_info.get("start_dt")
    end_dt = event_info.get("end_dt")

    if not start_dt:
        return [{
            "id": f"wrc-{year}-r{round_idx}-rally",
            "weekend": rally_name,
            "name": "Rally Event",
            "utc": event_info["utc"],
        }]

    thursday_utc = start_dt.replace(hour=8, minute=1, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    friday_dt = start_dt + timedelta(days=1)
    friday_utc = friday_dt.replace(hour=7, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    saturday_dt = start_dt + timedelta(days=2)
    saturday_utc = saturday_dt.replace(hour=7, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    sunday_dt = end_dt if end_dt else start_dt + timedelta(days=3)
    sunday_utc = sunday_dt.replace(hour=11, minute=15, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")

    return [
        {
            "id": f"wrc-{year}-r{round_idx}-shakedown",
            "weekend": rally_name,
            "name": "Shakedown",
            "utc": thursday_utc,
        },
        {
            "id": f"wrc-{year}-r{round_idx}-leg1",
            "weekend": rally_name,
            "name": "Day 1 / Leg 1",
            "utc": friday_utc,
        },
        {
            "id": f"wrc-{year}-r{round_idx}-leg2",
            "weekend": rally_name,
            "name": "Day 2 / Leg 2",
            "utc": saturday_utc,
        },
        {
            "id": f"wrc-{year}-r{round_idx}-powerstage",
            "weekend": rally_name,
            "name": "Wolf Power Stage",
            "utc": sunday_utc,
        },
    ]


def main():
    repo_root = Path(__file__).resolve().parent.parent
    output_dir = repo_root / "motorsport" / "wrc"
    output_dir.mkdir(parents=True, exist_ok=True)

    year = datetime.now().year
    calendar_events = scrape_calendar(year)

    if not calendar_events:
        print("ERROR: No calendar events found.", file=sys.stderr)
        sys.exit(1)

    all_stage_events = []
    for idx, event in enumerate(calendar_events, start=1):
        stages = generate_standard_rally_sessions(event, year, idx)
        all_stage_events.extend(stages)

    # Write motorsport/wrc/<year>.json
    season_file = output_dir / f"{year}.json"
    output_data = {
        "sportKey": "wrc",
        "season": str(year),
        "events": all_stage_events,
    }
    season_file.write_text(json.dumps(output_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(all_stage_events)} events to {season_file}", file=sys.stderr)

    # Write schedule.json for compatibility
    schedule_file = output_dir / "schedule.json"
    schedule_data = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "season": year,
        "calendar": {
            "events": calendar_events
        }
    }
    schedule_file.write_text(json.dumps(schedule_data, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote schedule to {schedule_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
