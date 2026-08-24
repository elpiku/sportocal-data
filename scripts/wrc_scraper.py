#!/usr/bin/env python3
"""
WRC (World Rally Championship) Data Scraper.
Scrapes official WRC calendar and rally itineraries from www.wrc.com.
Outputs to motorsport/wrc/<year>.json and motorsport/wrc/schedule.json.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def parse_date_range(date_text: str, default_year: int) -> tuple[datetime | None, datetime | None]:
    """Parse date text like '27 - 30 AUGUST 2026' or '30 JULY - 02 AUGUST 2026'."""
    date_text = date_text.strip().upper()
    try:
        # Pattern 1: DD - DD MONTH YYYY
        m1 = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Z]+)\s+(\d{4})", date_text)
        if m1:
            start_day = int(m1.group(1))
            end_day = int(m1.group(2))
            month = MONTHS.get(m1.group(3), 1)
            year = int(m1.group(4))
            start_dt = datetime(year, month, start_day, 8, 0, tzinfo=timezone.utc)
            end_dt = datetime(year, month, end_day, 16, 0, tzinfo=timezone.utc)
            return start_dt, end_dt

        # Pattern 2: DD MONTH - DD MONTH YYYY
        m2 = re.search(r"(\d{1,2})\s+([A-Z]+)\s*-\s*(\d{1,2})\s+([A-Z]+)\s+(\d{4})", date_text)
        if m2:
            start_day = int(m2.group(1))
            start_month = MONTHS.get(m2.group(2), 1)
            end_day = int(m2.group(3))
            end_month = MONTHS.get(m2.group(4), 1)
            year = int(m2.group(5))
            start_dt = datetime(year, start_month, start_day, 8, 0, tzinfo=timezone.utc)
            end_dt = datetime(year, end_month, end_day, 16, 0, tzinfo=timezone.utc)
            return start_dt, end_dt
    except Exception:
        pass

    return None, None


def scrape_calendar(year: int) -> list[dict]:
    """Scrape all rally events for the given year from wrc.com."""
    url = "https://www.wrc.com/en/calendar"
    print(f"Fetching WRC calendar from {url}...", file=sys.stderr)
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    events = []

    # Look for links to events
    event_links = soup.find_all("a", href=re.compile(r"/en/events/wrc-"))
    seen_urls = set()

    for link in event_links:
        href = link.get("href", "")
        full_url = href if href.startswith("http") else f"https://www.wrc.com{href}"
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Get event name
        title = link.get_text(separator=" ", strip=True)
        if not title or "Calendar" in title:
            continue

        # Extract round and dates from surrounding container or parent table/list
        parent = link.find_parent(["tr", "div", "li"])
        parent_text = parent.get_text(separator=" ", strip=True) if parent else ""

        # Remove flag emoji / extra tokens from name
        clean_name = re.sub(r"^[^\w\s]+", "", title).strip()
        if clean_name.startswith("WRC "):
            clean_name = clean_name[4:].strip()

        start_dt, end_dt = parse_date_range(parent_text, year)
        utc_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if start_dt else f"{year}-01-01T08:00:00Z"

        events.append({
            "name": clean_name,
            "url": full_url,
            "raw_text": parent_text,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "utc": utc_str,
        })

    print(f"Found {len(events)} rally events in calendar.", file=sys.stderr)
    return events


def scrape_event_itinerary(event_info: dict, year: int, round_idx: int) -> list[dict]:
    """Scrape specific stage times and itinerary if available on event page."""
    rally_name = event_info["name"]
    event_url = event_info["url"]
    rally_slug = slugify(rally_name)

    # Check if itinerary page exists
    stage_events = []
    try:
        res = requests.get(event_url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")

            # Look for itinerary links or embedded stages
            itin_link = soup.find("a", href=re.compile(r"/itinerary-"))
            if itin_link:
                itin_url = itin_link["href"]
                if not itin_url.startswith("http"):
                    itin_url = f"https://www.wrc.com{itin_url}"
                itin_res = requests.get(itin_url, headers=HEADERS, timeout=10)
                if itin_res.status_code == 200:
                    soup = BeautifulSoup(itin_res.text, "html.parser")

            # Extract stages (e.g. "SS1 Camp Moran 1", "Shakedown", "09:03: SS1 ...")
            stage_items = soup.find_all(["li", "p", "div"], text=re.compile(r"(Shakedown|SS\d+)", re.IGNORECASE))
            seen_stage_names = set()

            for item in stage_items:
                text = item.get_text(separator=" ", strip=True)
                m = re.search(r"(\d{1,2}:\d{2})?\s*[-:]?\s*(Shakedown|SS\d+[^(\n\r]+)", text, re.IGNORECASE)
                if m:
                    time_part = m.group(1) or "08:00"
                    stg_name = m.group(2).strip()
                    if stg_name in seen_stage_names:
                        continue
                    seen_stage_names.add(stg_name)

                    stg_slug = slugify(stg_name)
                    stage_events.append({
                        "id": f"wrc-{rally_slug}-{year}-{stg_slug}",
                        "weekend": rally_name,
                        "name": stg_name,
                        "utc": event_info["utc"],
                    })
    except Exception as e:
        print(f"  Note: could not fetch deep itinerary for {rally_name}: {e}", file=sys.stderr)

    # Fallback to placeholder event if no deep stages found
    if not stage_events:
        stage_events.append({
            "id": f"wrc-{year}-r{round_idx}-placeholder",
            "weekend": rally_name,
            "name": "Schedule coming soon" if event_info.get("start_dt") and event_info["start_dt"] > datetime.now(timezone.utc) else "Rally Event",
            "utc": event_info["utc"],
        })

    return stage_events


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
        print(f"Processing Round {idx}: {event['name']}...", file=sys.stderr)
        stages = scrape_event_itinerary(event, year, idx)
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
