"""
NASCAR Cup Series Schedule Scraper
Scrapes directly from https://www.nascar.com/nascar-cup-series/2026/schedule/
Extracts weekend sessions (Practice, Qualifying, Duels, Race) and outputs
the exact sportocal F1 JSON format.
"""

import json
import re
import os
import sys
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dt_parser
import pytz

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "../motorsport/nascar/cup/2026.json")
SCHEDULE_PAGE_URL = "https://www.nascar.com/nascar-cup-series/2026/schedule/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nascar.com/"
}

def slugify(text: str) -> str:
    """Transforms race/track names into URL-friendly identifiers."""
    if not text:
        return "event"
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)

def parse_iso_utc(date_str: str) -> str:
    """Parses date string into UTC ISO-8601 string."""
    if not date_str:
        return None
    try:
        dt = dt_parser.parse(str(date_str))
        if dt.tzinfo is None:
            local_tz = pytz.timezone("America/New_York")
            dt = local_tz.localize(dt)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def normalize_session_type(raw_name: str) -> tuple[str, str]:
    """Standardizes session naming to match F1 conventions (fp1, fp2, qualifying, race)."""
    n = raw_name.lower().strip()
    if "practice 1" in n or "first practice" in n:
        return "fp1", "Practice 1"
    elif "practice 2" in n or "final practice" in n:
        return "fp2", "Practice 2"
    elif "practice" in n:
        return "fp1", "Practice"
    elif "qualifying" in n or "pole" in n or "time trials" in n:
        return "qualifying", "Qualifying"
    elif "duel" in n or "heat" in n:
        return "duels", raw_name
    elif "race" in n or "500" in n or "400" in n:
        return "race", "Race"
    return slugify(raw_name).replace("-", "_"), raw_name

def parse_from_next_data(html_text: str, season_year: int) -> list:
    """Extracts schedule data directly from embedded Next.js __NEXT_DATA__ JSON script if present."""
    soup = BeautifulSoup(html_text, "html.parser")
    next_script = soup.find("script", id="__NEXT_DATA__")
    
    if not next_script or not next_script.string:
        return []
    
    events_output = []
    try:
        payload = json.loads(next_script.string)
        page_props = payload.get("props", {}).get("pageProps", {})
        races = page_props.get("scheduleData", {}).get("races", []) or page_props.get("races", [])

        for idx, r in enumerate(races, start=1):
            name = r.get("race_name") or r.get("event_name", f"NASCAR Cup Race {idx}")
            track_name = r.get("track_name", "Unknown Track")
            city = r.get("city", "")
            state = r.get("state", "")
            country = r.get("country", "USA")

            sessions = {}
            for s in r.get("weekend_schedule", []) or r.get("schedule", []):
                s_name = s.get("session_name") or s.get("name", "")
                s_start = s.get("start_time_utc") or s.get("start_time")
                if s_start:
                    s_key, display_name = normalize_session_type(s_name)
                    sessions[s_key] = {
                        "name": display_name,
                        "start": parse_iso_utc(s_start),
                        "status": "scheduled"
                    }

            if "race" not in sessions and (r.get("race_date") or r.get("start_time")):
                sessions["race"] = {
                    "name": name,
                    "start": parse_iso_utc(r.get("race_date") or r.get("start_time")),
                    "status": "scheduled"
                }

            events_output.append({
                "id": f"{season_year}-{slugify(name)}",
                "round": idx,
                "name": name,
                "circuit": {
                    "name": track_name,
                    "city": f"{city}, {state}".strip(", "),
                    "country": country
                },
                "sessions": sessions
            })
    except Exception as e:
        print(f"Failed parsing __NEXT_DATA__: {e}")

    return events_output

def parse_from_html_dom(html_text: str, season_year: int) -> list:
    """Parses standard schedule card/row elements from NASCAR DOM structure."""
    soup = BeautifulSoup(html_text, "html.parser")
    race_cards = soup.select(".schedule-row, .race-card, [data-event-id], .event-card")
    
    events_output = []
    round_counter = 1

    for card in race_cards:
        name_el = card.select_one(".race-name, .event-title, h3, h4")
        if not name_el:
            continue
        race_name = name_el.get_text(strip=True)

        track_el = card.select_one(".track-name, .venue-name, .circuit-name")
        track_name = track_el.get_text(strip=True) if track_el else "Unknown Track"

        location_el = card.select_one(".track-location, .location")
        location_text = location_el.get_text(strip=True) if location_el else ""

        date_el = card.select_one(".date, .race-date, time")
        date_str = date_el.get("datetime") or date_el.get_text(strip=True) if date_el else None

        sessions = {}
        sub_sessions = card.select(".session-row, .weekend-activity, .schedule-session")
        for sub in sub_sessions:
            s_name_el = sub.select_one(".session-name, .title")
            s_time_el = sub.select_one(".session-time, time")
            if s_name_el and s_time_el:
                s_name = s_name_el.get_text(strip=True)
                s_time = s_time_el.get("datetime") or s_time_el.get_text(strip=True)
                s_key, display_name = normalize_session_type(s_name)
                sessions[s_key] = {
                    "name": display_name,
                    "start": parse_iso_utc(s_time),
                    "status": "scheduled"
                }

        if "race" not in sessions and date_str:
            sessions["race"] = {
                "name": race_name,
                "start": parse_iso_utc(date_str),
                "status": "scheduled"
            }

        events_output.append({
            "id": f"{season_year}-{slugify(race_name)}",
            "round": round_counter,
            "name": race_name,
            "circuit": {
                "name": track_name,
                "city": location_text,
                "country": "USA"
            },
            "sessions": sessions
        })
        round_counter += 1

    return events_output

def scrape_nascar_schedule(season_year: int = 2026) -> dict:
    print(f"Fetching official web schedule: {SCHEDULE_PAGE_URL}")
    res = requests.get(SCHEDULE_PAGE_URL, headers=HEADERS, timeout=20)
    res.raise_for_status()

    # Strategy 1: Hydrated Next.js JSON extraction (Most accurate)
    events = parse_from_next_data(res.text, season_year)

    # Strategy 2: DOM markup parsing fallback
    if not events:
        print("Fallback to DOM HTML parsing...")
        events = parse_from_html_dom(res.text, season_year)

    return {
        "sport": "nascar-cup",
        "season": season_year,
        "events": events
    }

def main():
    season_year = 2026
    data = scrape_nascar_schedule(season_year)

    target_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Successfully scraped {len(data['events'])} events to {target_path}")

if __name__ == "__main__":
    main()
