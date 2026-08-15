#!/usr/bin/env python3
"""
NASCAR Cup Series schedule scraper for the sportocal-data repo.

Two sources, two different jobs:
  - ESPN's public Core API (sports.core.api.espn.com) is the source of
    truth for *when* each event happens. It lists every event for the
    season with an exact UTC timestamp per event. Unlike F1, it does not
    expose separate practice/qualifying/race sessions for NASCAR Cup - each
    ESPN "event" is effectively a single session, so unlike scrape_f1.py
    there's no per-session fan-out here, just one output event per ESPN
    event.
  - Jayski's schedule page (jayski.com) is scraped only to enrich *what
    to call* each event: ESPN's own event names are sometimes generic
    (e.g. "NASCAR Cup Series at Atlanta") where Jayski has the actual
    sponsor race name (e.g. "Autotrader 400"). Jayski's dates (just
    "Sun., Feb 22", no time) are matched against each ESPN event's
    Eastern-time calendar date to borrow its title; if nothing matches,
    the ESPN name is kept as-is.

Two other sources were considered and dropped:
  - motorsport.com/nascar-cup/schedule/2026 renders its whole schedule
    table client-side via JS after page load - the server-rendered HTML
    contains no event data (just column headers), so there's nothing to
    scrape without a headless browser.
  - nascar.com/nascar-cup-series/2026/schedule is the same story (its
    schedule widget literally ships a "Loading race information..."
    placeholder in the server HTML).
  If either of those starts server-rendering actual data, they'd be a
  good replacement for the Jayski enrichment step above.

Run this from the repo root: python scripts/nascar_cup.py
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, fetch, slugify, make_unique_id_assigner, write_output  # noqa: E402

SEASON_YEAR = 2026  # bump each year
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "nascar" / "cup" / f"{SEASON_YEAR}.json"

CORE_API_URL = (
    f"https://sports.core.api.espn.com/v2/sports/racing/leagues/nascar-premier/"
    f"seasons/{SEASON_YEAR}/types/2/events?limit=100"
)
JAYSKI_SCHEDULE_URL = f"https://www.jayski.com/nascar-cup-series/{SEASON_YEAR}-nascar-cup-series-schedule/"

ET_TZ = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
JAYSKI_DATE_RE = re.compile(r"([A-Za-z]{3,9})\.?,?\s+(\d{1,2})")

# ESPN's event "name"/"shortName" text -> this repo's session-naming
# convention (id slug, repo display name). Same idea as scrape_f1.py's
# SESSION_NAME_MAP, just matched against ESPN's vocabulary instead of
# Sky Sports'. Cup weekends are effectively single-session in ESPN's
# feed, so this is applied to the whole event name rather than a
# per-competition type.
NAME_PATTERNS = [
    (("practice 1", "first practice"), ("fp1", "Practice 1")),
    (("practice 2", "final practice"), ("fp2", "Practice 2")),
    (("practice",), ("fp1", "Practice")),
    (("qualifying", "pole", "time trials"), ("qualifying", "Qualifying")),
    (("duel", "heat"), ("duels", None)),  # None -> keep ESPN's own label
    (("race", "400", "500"), ("race", "Race")),
]


def match_name_pattern(text: str) -> tuple[str, str] | None:
    """Returns (id slug, repo display name) if `text` matches a known
    session keyword, else None."""
    n = text.lower().strip()
    for keywords, (id_slug, display_name) in NAME_PATTERNS:
        if any(k in n for k in keywords):
            return id_slug, display_name or text
    return None


def classify_session(espn_name: str, weekend_name: str) -> tuple[str, str]:
    """(id slug, repo display name) for one event. Tries ESPN's own event
    name first - this is what preserves distinct labels like "Duel #1" vs
    "Duel #2", which the (identical, per-duel) Jayski title can't. Falls
    back to the enriched Jayski weekend title, since ESPN's raw names are
    often too generic to contain a "400"/"500"/etc. keyword (e.g.
    "NASCAR Cup Series at Atlanta" vs Jayski's "Autotrader 400")."""
    return (
        match_name_pattern(espn_name)
        or match_name_pattern(weekend_name)
        or (slugify(weekend_name), weekend_name)
    )


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
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def et_month_day(utc_iso: str) -> tuple[int, int]:
    """The (month, day) an ISO UTC timestamp falls on in US Eastern time -
    used to match an ESPN event to its Jayski schedule row, since NASCAR
    dates/times are always communicated in ET and a late-night UTC
    timestamp can land on the *next* calendar day."""
    dt = datetime.strptime(utc_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    local = dt.astimezone(ET_TZ)
    return local.month, local.day


def fetch_espn_events() -> list[dict]:
    """Pulls every NASCAR Cup event for the season from ESPN's Core API.
    Each item is {"name": <espn event name>, "utc": <iso utc timestamp>}."""
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

        utc_iso = to_utc_iso(ev.get("date"))
        if not utc_iso:
            continue
        name = ev.get("name") or ev.get("shortName") or "NASCAR Cup Race"
        events.append({"name": name, "utc": utc_iso})

    return events


def fetch_jayski_titles() -> dict[tuple[int, int], str]:
    """Scrapes Jayski's schedule table -> {(month, day): official race title}.
    Skips off weeks (no linked race name) and non-date rows."""
    html = fetch(JAYSKI_SCHEDULE_URL)
    soup = BeautifulSoup(html, "html.parser")

    titles = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        date_match = JAYSKI_DATE_RE.search(cells[1].get_text(" ", strip=True))
        if not date_match:
            continue
        mon_text, day_text = date_match.groups()
        month = MONTH_MAP.get(mon_text[:3].title())
        if not month:
            continue

        title = cells[2].get_text(strip=True)
        if not title or "OFF WEEK" in row.get_text(" ", strip=True).upper():
            continue

        titles[(month, int(day_text))] = title

    return titles


def build_events(espn_events: list[dict], jayski_titles: dict) -> list[dict]:
    assign_id = make_unique_id_assigner()
    events = []
    for ev in espn_events:
        weekend_name = jayski_titles.get(et_month_day(ev["utc"]), ev["name"])
        session_slug, display_name = classify_session(ev["name"], weekend_name)
        base_id = f"cup-{SEASON_YEAR}-{slugify(weekend_name)}-{session_slug}"
        events.append({
            "id": assign_id(base_id),
            "weekend": weekend_name,
            "name": display_name,
            "utc": ev["utc"],
        })
    events.sort(key=lambda e: e["utc"])
    return events


def main():
    print("Fetching NASCAR Cup event dates from ESPN...", file=sys.stderr)
    espn_events = fetch_espn_events()
    print(f"Got {len(espn_events)} events from ESPN", file=sys.stderr)

    print("Fetching official race titles from Jayski...", file=sys.stderr)
    try:
        jayski_titles = fetch_jayski_titles()
        print(f"Got {len(jayski_titles)} titled dates from Jayski", file=sys.stderr)
    except requests.RequestException as err:
        print(f"Jayski fetch failed ({err}), falling back to ESPN names only", file=sys.stderr)
        jayski_titles = {}

    events = build_events(espn_events, jayski_titles)

    output = {
        "sportKey": "nascar-cup",
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, output, min_events=5)


if __name__ == "__main__":
    main()
