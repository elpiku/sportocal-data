#!/usr/bin/env python3
"""
F1 schedule scraper for the sportocal-data repo -- Sky Sports edition.

FIXED (2026-08-11): Sky Sports changed their schedule page markup. Session
rows used to render as a "Starting <Weekday> DD Mon, HH:MMam/pm" text node
paired with a separate "<Session Name>" link to a /results/ sub-page. Sky
has since dropped the word "Starting" entirely and now renders each row as
a single combined string, e.g.:

    "Practice 1 Fri 21 Aug, 11:30am"
    "Sprint Qualifying Fri 21 Aug, 3:30pm"
    "Race Sun 23 Aug, 2:00pm"

Because the scraper's SESSION_LINE_RE required the literal word "Starting",
every row failed to match, parse_schedule() returned 0 events, and
common.write_output()'s safety net (min_events=5) correctly aborted the
run rather than overwrite good data -- which is why the GitHub Action was
failing with "ERROR: only parsed 0 events".

This version matches the new combined "<Session Name> <Day> <DD> <Mon>,
<HH:MM><am|pm>" string directly, so it no longer depends on the word
"Starting" or on a separate /results/ link existing for each session.

RENAME THIS FILE to scripts/scrape_f1.py (overwriting the old one) before
committing -- the "_FIXED" suffix is only so you can tell it apart from
the broken original while reviewing it.

Why Sky Sports instead of formula1.com:
- ONE page (skysports.com/f1/schedule) covers the entire remaining season,
  vs. needing to fetch a main page + a separate timetable article for
  every single round on formula1.com (~2 requests x 23 rounds).
- Times are given as plain, unambiguous UK local time. No client-side
  "My time / Track time" toggle to worry about (see the formula1.com
  version of this script, kept for reference, for why that mattered).

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

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import fetch, make_unique_id_assigner, write_output  # noqa: E402

SCHEDULE_URL = "https://www.skysports.com/f1/schedule"
SEASON_YEAR = 2026  # bump each year
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "f1" / f"{SEASON_YEAR}.json"
UK_TZ = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")

ROUND_LINK_RE = re.compile(r"/f1/grandprix/([a-z-]+)$")

# Combined "<Session Name> <Day> <DD> <Mon>, <HH:MM><am|pm>" matcher.
# Longer/more-specific session names must come before their prefixes in
# the alternation (e.g. "Sprint Qualifying" before "Sprint") so re
# doesn't stop at a shorter match.
SESSION_NAMES_RE_PART = "|".join([
    "Free Practice 1", "Free Practice 2", "Free Practice 3",
    "Practice 1", "Practice 2", "Practice 3",
    "Sprint Qualifying", "Sprint", "Qualifying", "Race",
])
SESSION_LINE_RE = re.compile(
    rf"({SESSION_NAMES_RE_PART})\s+\w+\s+(\d{{1,2}})\s+([A-Za-z]{{3}})[a-z]*,\s*(\d{{1,2}}):(\d{{2}})\s*(am|pm)",
    re.IGNORECASE,
)

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Site slug (from the /f1/grandprix/ URL) -> repo track key.
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
# name -> (repo display name, id slug). Keys are lowercased for matching.
SESSION_NAME_MAP = {
    "free practice 1": ("Free Practice 1", "fp1"),
    "practice 1": ("Free Practice 1", "fp1"),
    "free practice 2": ("Free Practice 2", "fp2"),
    "practice 2": ("Free Practice 2", "fp2"),
    "free practice 3": ("Free Practice 3", "fp3"),
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

    # Walk the page in strict document order (soup.descendants), tracking:
    # - the current round, set whenever we pass a link to
    #   /f1/grandprix/<slug> (and it's not a session-result sub-link)
    # - as soon as we hit a text node matching SESSION_LINE_RE (session
    #   name + day/date/time all in one string -- Sky's current format),
    #   record an event for the current round.
    # This sequential approach doesn't depend on exact parent/child DOM
    # nesting, and no longer depends on a separate /results/ link or the
    # word "Starting" existing anywhere on the page.
    events = []
    current_slug = None
    current_track_key = None
    current_weekend_name = None
    assign_id = None

    for node in soup.descendants:
        if isinstance(node, Tag) and node.name == "a" and node.get("href"):
            href = node["href"]

            round_match = ROUND_LINK_RE.search(href)
            if round_match:
                slug = round_match.group(1)
                if slug != current_slug:
                    current_slug = slug
                    current_track_key = repo_track_key(slug)
                    current_weekend_name = gp_weekend_name(node.get_text(strip=True))
                    assign_id = make_unique_id_assigner()
                continue

        elif isinstance(node, NavigableString):
            text = str(node)
            if current_slug is None:
                continue

            for match in SESSION_LINE_RE.finditer(text):
                session_name_raw, day, mon, hh, mm, ampm = match.groups()
                normalized = SESSION_NAME_MAP.get(session_name_raw.strip().lower())
                if not normalized:
                    continue
                repo_name, id_slug = normalized

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

                base_id = f"f1-{SEASON_YEAR}-{current_track_key}-{id_slug}"
                events.append({
                    "id": assign_id(base_id),
                    "weekend": current_weekend_name,
                    "name": repo_name,
                    "utc": utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

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
