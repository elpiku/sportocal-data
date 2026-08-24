#!/usr/bin/env python3
"""
F1 schedule scraper for the sportocal-data repo -- Sky Sports edition.

Why Sky Sports instead of formula1.com:
  - ONE page (skysports.com/f1/schedule) covers the entire remaining season,
    vs. needing to fetch a main page + a separate timetable article for
    every single round on formula1.com (~2 requests x 23 rounds).
  - Times are given as plain, unambiguous UK local time. No client-side
    "My time / Track time" toggle to worry about (see the formula1.com
    version of this script, kept for reference, for why that mattered).
  - Cross-checked against formula1.com's official per-round timetable
    article for the Dutch GP: converting Sky's UK times to UTC produced
    the exact same UTC timestamps as formula1.com's explicit "N hours
    ahead of/behind UTC" note. Good agreement between two independent
    sources.

Trade-off to know about: this page only lists the *current and upcoming*
rounds, not ones that already happened. Since this data feeds reminders
for upcoming sessions, that's arguably the right behavior (nothing to
remind about for a session that's already over) -- but it does mean a
completed round will disappear from motorsport/f1/2026.json after its
weekend passes, rather than staying in the file as history.

Run this from the repo root: python scripts/scrape_f1.py
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import fetch, make_unique_id_assigner, write_output  # noqa: E402

SCHEDULE_URL = "https://www.skysports.com/f1/schedule"
SEASON_YEAR = 2026  # bump each year
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "f1" / f"{SEASON_YEAR}.json"
UK_TZ = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")

ROUND_LINK_RE = re.compile(r"/f1/grandprix/([a-z-]+)$")
SESSION_LINE_RE = re.compile(
    r"Starting\s+\w+\s+(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s*,\s*(\d{1,2}):(\d{2})\s*(am|pm)",
    re.IGNORECASE,
)

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Site slug (from the /f1/grandprix/<slug> URL) -> repo track key.
# Same convention as scripts/scrape_indycar.py's TRACK_KEY_MAP: add an
# entry here if a new round's slug doesn't already match the repo key
# you want. Pre-filled from this repo's existing motorsport/f1/2026.json.
TRACK_KEY_MAP = {
    "great-britain": "greatbritain",
    "united-states": "usa",
    "las-vegas": "lasvegas",
    "united-arab-emirates": "abudhabi",
}

# Sky shows just the country/location name (e.g. "Netherlands", "Abu
# Dhabi"). Map that to this repo's "<X> Grand Prix" weekend-name
# convention. Add an entry here if Sky's display name for a new round
# doesn't already produce the name you want via the default
# f"{name} Grand Prix" fallback.
GP_NAME_OVERRIDES = {
    "Netherlands": "Dutch Grand Prix",
    "United States": "United States Grand Prix",
    "Mexico": "Mexico City Grand Prix",
    "Brazil": "São Paulo Grand Prix",
    "United Arab Emirates": "Abu Dhabi Grand Prix",
    "Abu Dhabi": "Abu Dhabi Grand Prix",
    "Italy": "Italian Grand Prix",
    "Spain": "Spanish Grand Prix",
    "Great Britain": "British Grand Prix",
    "United Kingdom": "British Grand Prix",
}

# Sky's session names are already close to this repo's convention but not
# identical (e.g. "Practice 1" vs repo's "Free Practice 1"). Map display
# name -> (repo display name, id slug).
SESSION_NAME_MAP = {
    "practice 1": ("Free Practice 1", "fp1"),
    "practice 2": ("Free Practice 2", "fp2"),
    "practice 3": ("Free Practice 3", "fp3"),
    "sprint qualifying": ("Sprint Qualifying", "sprint-quali"),
    "sprint": ("Sprint", "sprint"),
    "qualifying": ("Qualifying", "quali"),
    "race": ("Race", "race"),
}


def repo_track_key(site_slug: str) -> str:
    return TRACK_KEY_MAP.get(site_slug, site_slug)


def gp_weekend_name(display_name: str) -> str:
    return GP_NAME_OVERRIDES.get(display_name, f"{display_name} Grand Prix")


def parse_schedule():
    html = fetch(SCHEDULE_URL)
    soup = BeautifulSoup(html, "html.parser")

    # Strategy: find every link to a session results page
    # (/f1/grandprix/<slug>/results/...) directly -- the slug is embedded
    # right in the URL, so we don't need to track "current round" state
    # across the page in document order (which is what broke before if
    # text was split across sibling elements).
    #
    # For each such link, we merge ALL text within its nearest enclosing
    # list item (or block-level ancestor) into one string via get_text(),
    # so the "Starting <date>, <time>" text is found regardless of
    # whether it's a single text node or split across several inline
    # elements (e.g. a <span> around the date) -- get_text() flattens
    # that automatically.
    round_names = {}  # slug -> display name, from round header links
    for a in soup.find_all("a", href=True):
        m = ROUND_LINK_RE.search(a["href"])
        if m and "/results/" not in a["href"]:
            round_names[m.group(1)] = a.get_text(strip=True)

    assigners = {}  # slug -> unique id assigner, one per round
    events = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        results_match = re.search(r"/f1/grandprix/([a-z-]+)/results/", href)
        if not results_match:
            continue

        slug = results_match.group(1)
        session_display = a.get_text(strip=True)
        if session_display.lower() not in SESSION_NAME_MAP:
            continue

        # Walk up to the nearest <li> (or fall back to the immediate
        # parent) so we capture any sibling text/spans around this link,
        # e.g. "Starting Fri 21 Aug, 11:30am" that live outside the <a>
        # tag itself.
        container = a.find_parent("li") or a.parent
        row_text = container.get_text(" ", strip=True) if container else a.get_text(" ", strip=True)

        time_match = SESSION_LINE_RE.search(row_text)
        if not time_match:
            continue

        day, mon, hh, mm, ampm = time_match.groups()
        day, hh, mm = int(day), int(hh), int(mm)
        month = MONTH_MAP.get(mon.title())
        if not month:
            continue
        if ampm.lower() == "pm" and hh != 12:
            hh += 12
        if ampm.lower() == "am" and hh == 12:
            hh = 0

        local_dt = datetime(SEASON_YEAR, month, day, hh, mm, tzinfo=UK_TZ)
        utc_dt = local_dt.astimezone(UTC)

        track_key = repo_track_key(slug)
        weekend_name = gp_weekend_name(round_names.get(slug, slug.replace("-", " ").title()))
        repo_name, id_slug = SESSION_NAME_MAP[session_display.lower()]

        if slug not in assigners:
            assigners[slug] = make_unique_id_assigner()
        base_id = f"f1-{SEASON_YEAR}-{track_key}-{id_slug}"
        events.append({
            "id": assigners[slug](base_id),
            "weekend": weekend_name,
            "name": repo_name,
            "utc": utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    events.sort(key=lambda e: e["utc"])
    return events


def main():
    print("Fetching Sky Sports F1 schedule...", file=sys.stderr)
    events = parse_schedule()
    print(f"Parsed {len(events)} sessions", file=sys.stderr)

    output = {
        "sportKey": "f1",
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, output, min_events=5)


if __name__ == "__main__":
    main()
