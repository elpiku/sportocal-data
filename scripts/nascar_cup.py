"""
NASCAR Cup Series Schedule Scraper
Extracts all weekend sessions (Practice, Qualifying, Duels, Race)
matching the exact sportocal F1 JSON format and directory structure.
"""

import json
import re
import os
import sys
from datetime import datetime, timezone
import requests
from dateutil import parser as dt_parser
import pytz

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "../motorsport/nascar/cup/2026.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*"
}

def slugify(text: str) -> str:
    """Standardizes names into URL-friendly IDs."""
    if not text:
        return "event"
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)

def parse_iso_utc(date_str: str) -> str:
    """Converts date string to standard UTC ISO-8601 string."""
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
    elif "race" in n or "400" in n or "500" in n:
        return "race", "Race"
    return slugify(raw_name).replace("-", "_"), raw_name

def fetch_nascar_cup_season(season_year: int = 2026) -> dict:
    """Fetches NASCAR Cup schedule using ESPN Core REST event feeds."""
    base_url = f"https://sports.core.api.espn.com/v2/sports/racing/leagues/nascar-premier/seasons/{season_year}/types/2/events?limit=100"
    print(f"Querying NASCAR Core API: {base_url}")
    
    events_output = []

    try:
        res = requests.get(base_url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            items = res.json().get("items", [])
            for idx, item in enumerate(items, start=1):
                event_url = item.get("$ref") if isinstance(item, dict) else item
                if not event_url:
                    continue

                try:
                    ev_res = requests.get(event_url, headers=HEADERS, timeout=10)
                    if ev_res.status_code != 200:
                        continue
                    ev = ev_res.json()

                    name = ev.get("name") or ev.get("shortName", f"NASCAR Cup Race {idx}")
                    venue_data = ev.get("venues", [{}])[0] if ev.get("venues") else {}
                    
                    sessions = {}
                    for comp in ev.get("competitions", []):
                        comp_url = comp.get("$ref") if isinstance(comp, dict) else None
                        comp_data = comp
                        if comp_url:
                            try:
                                c_res = requests.get(comp_url, headers=HEADERS, timeout=10)
                                if c_res.status_code == 200:
                                    comp_data = c_res.json()
                            except Exception:
                                pass

                        c_type = comp_data.get("type", {}).get("text", "")
                        c_date = comp_data.get("date")
                        if c_date:
                            s_key, display_name = normalize_session_key(c_type or name)
                            sessions[s_key] = {
                                "name": display_name,
                                "start": parse_iso_utc(c_date),
                                "status": "scheduled"
                            }

                    if "race" not in sessions and ev.get("date"):
                        sessions["race"] = {
                            "name": name,
                            "start": parse_iso_utc(ev.get("date")),
                            "status": "scheduled"
                        }

                    events_output.append({
                        "id": f"{season_year}-{slugify(name)}",
                        "round": idx,
                        "name": name,
                        "circuit": {
                            "name": venue_data.get("fullName", "Unknown Track"),
                            "city": venue_data.get("address", {}).get("city", ""),
                            "country": venue_data.get("address", {}).get("country", "USA")
                        },
                        "sessions": sessions
                    })
                except Exception as err:
                    print(f"Error parsing event item {event_url}: {err}")

    except Exception as e:
        print(f"ESPN Core API error: {e}")

    # Fallback to Scoreboard endpoint if core items were empty
    if not events_output:
        alt_url = f"https://site.api.espn.com/apis/site/v2/sports/racing/nascar-premier/scoreboard?limit=100&dates={season_year}"
        print(f"Falling back to Scoreboard endpoint: {alt_url}")
        try:
            s_res = requests.get(alt_url, headers=HEADERS, timeout=15)
            s_data = s_res.json()
            for idx, ev in enumerate(s_data.get("events", []), start=1):
                name = ev.get("name") or ev.get("shortName", f"NASCAR Cup Race {idx}")
                venues = ev.get("competitions", [{}])[0].get("venue", {}) if ev.get("competitions") else {}
                
                sessions = {}
                for comp in ev.get("competitions", []):
                    c_name = comp.get("type", {}).get("text") or name
                    c_date = comp.get("date")
                    if c_date:
                        s_key, display_name = normalize_session_key(c_name)
                        sessions[s_key] = {
                            "name": display_name,
                            "start": parse_iso_utc(c_date),
                            "status": "scheduled"
                        }

                if "race" not in sessions and ev.get("date"):
                    sessions["race"] = {
                        "name": name,
                        "start": parse_iso_utc(ev.get("date")),
                        "status": "scheduled"
                    }

                events_output.append({
                    "id": f"{season_year}-{slugify(name)}",
                    "round": idx,
                    "name": name,
                    "circuit": {
                        "name": venues.get("fullName") or "Unknown Track",
                        "city": venues.get("address", {}).get("city", ""),
                        "country": venues.get("address", {}).get("country", "USA")
                    },
                    "sessions": sessions
                })
        except Exception as err:
            print(f"Scoreboard fallback error: {err}")

    return {
        "sport": "nascar-cup",
        "season": season_year,
        "events": events_output
    }

def main():
    season_year = 2026
    data = fetch_nascar_cup_season(season_year)

    target_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(data['events'])} events to {target_path}")

if __name__ == "__main__":
    main()
