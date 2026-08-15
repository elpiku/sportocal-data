"""
NASCAR Cup Series Schedule Scraper
Scrapes complete weekend schedules (Practice, Qualifying, Race) from motorsport.com
and writes to motorsport/nascar/cup/2026.json matching the Sportocal F1 format.
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
SOURCE_URL = "https://www.motorsport.com/nascar-cup/schedule/2026/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.motorsport.com/"
}

def slugify(text: str) -> str:
    """Transforms race/track names into URL-friendly identifiers."""
    if not text:
        return "event"
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)

def parse_iso_utc(date_str: str) -> str:
    """Converts string dates to UTC ISO-8601 strings."""
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

def normalize_session_key(raw_name: str) -> tuple[str, str]:
    """Standardizes session names to match F1 conventions (fp1, fp2, qualifying, race)."""
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
    elif "race" in n or "400" in n or "500" in n:
        return "race", "Race"
    return slugify(raw_name).replace("-", "_"), raw_name

def parse_json_ld(soup: BeautifulSoup, season_year: int) -> list:
    """Extracts structured SportsEvent JSON-LD data from motorsport.com."""
    events = []
    scripts = soup.find_all("script", type="application/ld+json")
    
    round_idx = 1
    for s in scripts:
        if not s.string:
            continue
        try:
            data = json.loads(s.string)
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                # Target SportsEvent or Event types
                if item.get("@type") in ["SportsEvent", "Event"]:
                    name = item.get("name", f"NASCAR Cup Race {round_idx}")
                    location = item.get("location", {})
                    circuit_name = location.get("name", "Unknown Circuit")
                    address = location.get("address", {})
                    
                    city = address.get("addressLocality", "") if isinstance(address, dict) else ""
                    country = address.get("addressCountry", "USA") if isinstance(address, dict) else "USA"
                    
                    sessions = {}
                    # Check sub-events for Practice / Qualifying
                    sub_events = item.get("subEvent", [])
                    if isinstance(sub_events, dict):
                        sub_events = [sub_events]
                        
                    for sub in sub_events:
                        sub_name = sub.get("name", "")
                        sub_date = sub.get("startDate")
                        if sub_date:
                            s_key, display_name = normalize_session_key(sub_name)
                            sessions[s_key] = {
                                "name": display_name,
                                "start": parse_iso_utc(sub_date),
                                "status": "scheduled"
                            }
                            
                    # Main race start
                    main_start = item.get("startDate")
                    if "race" not in sessions and main_start:
                        sessions["race"] = {
                            "name": name,
                            "start": parse_iso_utc(main_start),
                            "status": "scheduled"
                        }

                    events.append({
                        "id": f"{season_year}-{slugify(name)}",
                        "round": round_idx,
                        "name": name,
                        "circuit": {
                            "name": circuit_name,
                            "city": city,
                            "country": country
                        },
                        "sessions": sessions
                    })
                    round_idx += 1
        except Exception:
            continue

    return events

def parse_html_table(soup: BeautifulSoup, season_year: int) -> list:
    """Fallback HTML table parser for motorsport.com schedule page."""
    events = []
    rows = soup.select(".ms-schedule-table-item, .ms-schedule-table tbody tr, .ms-grid-row, tr[data-race-id]")
    
    round_idx = 1
    for row in rows:
        title_el = row.select_one(".ms-schedule-table-item__title, .title, .event-title a, a[title]")
        if not title_el:
            continue
        race_name = title_el.get_text(strip=True)

        circuit_el = row.select_one(".ms-schedule-table-item__track, .track, .circuit")
        circuit_name = circuit_el.get_text(strip=True) if circuit_el else "Unknown Track"

        date_el = row.select_one(".ms-schedule-table-item__date, .date, time")
        date_val = date_el.get("datetime") or date_el.get_text(strip=True) if date_el else None

        sessions = {}
        if date_val:
            sessions["race"] = {
                "name": race_name,
                "start": parse_iso_utc(date_val),
                "status": "scheduled"
            }

        events.append({
            "id": f"{season_year}-{slugify(race_name)}",
            "round": round_idx,
            "name": race_name,
            "circuit": {
                "name": circuit_name,
                "city": "",
                "country": "USA"
            },
            "sessions": sessions
        })
        round_idx += 1

    return events

def scrape_motorsport_schedule(season_year: int = 2026) -> dict:
    print(f"Scraping schedule from: {SOURCE_URL}")
    res = requests.get(SOURCE_URL, headers=HEADERS, timeout=20)
    res.raise_for_status()
    
    soup = BeautifulSoup(res.text, "html.parser")
    
    # 1. Try structured JSON-LD (contains full session metadata)
    events = parse_json_ld(soup, season_year)
    
    # 2. Fallback to HTML table structure if JSON-LD is absent
    if not events:
        print("Falling back to HTML table parsing...")
        events = parse_html_table(soup, season_year)

    return {
        "sport": "nascar-cup",
        "season": season_year,
        "events": events
    }

def main():
    season_year = 2026
    data = scrape_motorsport_schedule(season_year)

    target_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Successfully scraped {len(data['events'])} events to {target_path}")

if __name__ == "__main__":
    main()
