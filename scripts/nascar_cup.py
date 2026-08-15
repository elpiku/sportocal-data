#!/usr/bin/env python3
"""
NASCAR Cup Series schedule scraper for the sportocal-data repo -- ESPN edition.

Source: ESPN's public "Core API" for racing/nascar-premier
(sports.core.api.espn.com), which lists every event for the season and
links out to per-event and per-competition detail pages (practice,
qualifying, duels, race, ...). If that returns nothing (e.g. ESPN changes
the endpoint shape), this falls back to ESPN's simpler public Scoreboard
API, which is less detailed (usually just gives a single "race" session
per event) but more resilient.

Run this from the repo root: python scripts/nascar_cup.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, slugify, make_unique_id_assigner, write_output  # noqa: E402

SEASON_YEAR = 2026  # bump each year
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "nascar" / "cup" / f"{SEASON_YEAR}.json"

CORE_API_URL = (
    f"https://sports.core.api.espn.com/v2/sports/racing/leagues/nascar-premier/"
    f"seasons/{SEASON_YEAR}/types/2/events?limit=100"
)
SCOREBOARD_URL = (
    f"https://site.api.espn.com/apis/site/v2/sports/racing/nascar-premier/"
    f"scoreboard?limit=100&dates={SEASON_YEAR}"
)

# ESPN's competition "type.text" strings -> this repo's session-naming
# convention (id slug, display name). Same idea as scrape_f1.py's
# SESSION_NAME_MAP, just matched against ESPN's vocabulary instead of
# Sky Sports'.
SESSION_PATTERNS = [
    (("practice 1", "first practice"), ("fp1", "Practice 1")),
    (("practice 2", "final practice"), ("fp2", "Practice 2")),
    (("practice",), ("fp1", "Practice")),
    (("qualifying", "pole", "time trials"), ("qualifying", "Qualifying")),
    (("duel", "heat"), ("duels", None)),  # None -> keep ESPN's own label
    (("race", "400", "500"), ("race", "Race")),
]


def normalize_session(raw_name: str) -> tuple[str, str]:
    """ESPN competition-type text -> (id slug, repo display name)."""
    n = raw_name.lower().strip()
    for keywords, (id_slug, display_name) in SESSION_PATTERNS:
        if any(k in n for k in keywords):
            return id_slug, display_name or raw_name
    return slugify(raw_name), raw_name


def to_utc_iso(date_str: str) -> str | None:
    """Normalizes an ESPN date string to this repo's 'YYYY-MM-DDTHH:MM:SSZ' form."""
    if not date_str:
        return None
    d = date_str.strip()
    if d.endswith("Z"):
        d = d[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(d)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_sessions(competitions: list, weekend_name: str, fallback_date: str):
    """Yields (session_key, display_name, utc_iso) for one ESPN event,
    resolving each competition's own detail page ($ref) for its date/type
    where needed. Falls back to a single "race" session at the event's own
    date if no competition yielded one (mirrors this script's original
    behavior)."""
    found_race = False
    for comp in competitions:
        comp_data = comp
        comp_url = comp.get("$ref") if isinstance(comp, dict) else None
        if comp_url:
            try:
                r = requests.get(comp_url, headers=HEADERS, timeout=10)
                if r.status_code == 200:
                    comp_data = r.json()
            except requests.RequestException:
                pass

        c_type = comp_data.get("type", {}).get("text", "")
        utc_iso = to_utc_iso(comp_data.get("date"))
        if not utc_iso:
            continue

        session_key, display_name = normalize_session(c_type or weekend_name)
        found_race = found_race or session_key == "race"
        yield session_key, display_name, utc_iso

    if not found_race:
        fallback_utc = to_utc_iso(fallback_date)
        if fallback_utc:
            yield "race", "Race", fallback_utc


def weekend_events(name: str, competitions: list, fallback_date: str) -> list:
    """Flattens one NASCAR weekend into this repo's per-session event schema."""
    assign_id = make_unique_id_assigner()
    events = []
    for session_key, display_name, utc_iso in event_sessions(competitions, name, fallback_date):
        base_id = f"cup-{SEASON_YEAR}-{slugify(name)}-{session_key}"
        events.append({
            "id": assign_id(base_id),
            "weekend": name,
            "name": display_name,
            "utc": utc_iso,
        })
    return events


def parse_core_api() -> list:
    res = requests.get(CORE_API_URL, headers=HEADERS, timeout=15)
    res.raise_for_status()
    items = res.json().get("items", [])

    events = []
    for item in items:
        event_url = item.get("$ref") if isinstance(item, dict) else item
        if not event_url:
            continue
        try:
            ev_res = requests.get(event_url, headers=HEADERS, timeout=10)
            if ev_res.status_code != 200:
                continue
            ev = ev_res.json()
        except requests.RequestException:
            continue

        name = ev.get("name") or ev.get("shortName") or "NASCAR Cup Race"
        events.extend(weekend_events(name, ev.get("competitions", []), ev.get("date")))

    return events


def parse_scoreboard_fallback() -> list:
    res = requests.get(SCOREBOARD_URL, headers=HEADERS, timeout=15)
    res.raise_for_status()
    data = res.json()

    events = []
    for ev in data.get("events", []):
        name = ev.get("name") or ev.get("shortName") or "NASCAR Cup Race"
        events.extend(weekend_events(name, ev.get("competitions", []), ev.get("date")))

    return events


def fetch_schedule() -> list:
    try:
        events = parse_core_api()
    except requests.RequestException as err:
        print(f"ESPN Core API error: {err}", file=sys.stderr)
        events = []

    if not events:
        print("Core API returned nothing, falling back to Scoreboard endpoint...", file=sys.stderr)
        try:
            events = parse_scoreboard_fallback()
        except requests.RequestException as err:
            print(f"Scoreboard fallback error: {err}", file=sys.stderr)
            events = []

    events.sort(key=lambda e: e["utc"])
    return events


def main():
    print("Fetching NASCAR Cup schedule from ESPN...", file=sys.stderr)
    events = fetch_schedule()
    print(f"Parsed {len(events)} sessions", file=sys.stderr)

    output = {
        "sportKey": "nascar-cup",
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, output, min_events=5)


if __name__ == "__main__":
    main()
