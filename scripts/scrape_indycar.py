#!/usr/bin/env python3
"""
IndyCar schedule scraper for the sportocal-data repo.

Scrapes indycar.com and writes output directly into this repo's existing schema:

  motorsport/indycar/ntt/<season>.json

  {
    "sportKey": "ntt-indycar",
    "season": "2026",
    "events": [
      { "id": "indycar-2026-markham-practice-1",
        "weekend": "Ontario Honda Dealers Indy at Markham",
        "name": "Practice 1",
        "utc": "2026-08-14T19:00:00Z" },
      ...
    ]
  }

Run this from the repo root:  python scrape_indycar.py
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

BASE_URL = "https://www.indycar.com"
SCHEDULE_URL = f"{BASE_URL}/Schedule"
SEASON_YEAR = 2026  # bump each year
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "indycar" / "ntt" / f"{SEASON_YEAR}.json"
EASTERN = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
REQUEST_DELAY_SECONDS = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

EVENT_LINK_RE = re.compile(rf"/Schedule/{SEASON_YEAR}/([A-Za-z0-9\-]+)")
DAY_HEADER_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Za-z]{3,9})\s+(\d{1,2})$"
)
TIME_RE = re.compile(r"^(\d{1,2}:\d{2}\s*[AP]M)\s*ET$", re.IGNORECASE)
SESSION_RE = re.compile(r"NTT INDYCAR SERIES\s*-\s*(.+)")

# --- Track-slug mapping -----------------------------------------------------
# indycar.com uses its own URL slugs (e.g. "WWTR", "Washington-DC",
# "Milwaukee-Race1"), but this repo uses its own short track keys for IDs
# (e.g. "gateway", "washington", "milwaukee"). Map site slug -> repo key here.
# Multiple site slugs can map to the same repo key (e.g. Milwaukee's two
# race pages both feed the "milwaukee" weekend).
#
# ADD NEW ENTRIES HERE as new races/slugs appear on indycar.com that aren't
# yet in this map — the scraper will otherwise fall back to a lowercased,
# hyphen-stripped version of the site slug (see slugify_track()).
TRACK_KEY_MAP = {
    "St-Petersburg": "st-petersburg",
    "Phoenix": "phoenix",
    "Arlington": "arlington",
    "Barber": "barber",
    "Long-Beach": "long-beach",
    "Indianapolis": "indianapolis-gp",
    "Indianapolis-500": "indy500",
    "Detroit": "detroit",
    "WWTR": "gateway",
    "Road-America": "road-america",
    "Mid-Ohio": "mid-ohio",
    "Nashville": "nashville",
    "Portland": "portland",
    "Markham": "markham",
    "Washington-DC": "washington",
    "Milwaukee-Race1": "milwaukee",
    "Milwaukee-Race2": "milwaukee",
    "Laguna-Seca": "laguna-seca",
}


def slugify_track(site_slug: str) -> str:
    if site_slug in TRACK_KEY_MAP:
        return TRACK_KEY_MAP[site_slug]
    # Fallback: best-effort guess. Flagged in logs so you notice and can add
    # a proper mapping entry above.
    guess = site_slug.lower()
    print(f"  NOTE: no TRACK_KEY_MAP entry for site slug '{site_slug}', "
          f"guessing repo key '{guess}'. Add a mapping if this looks wrong.",
          file=sys.stderr)
    return guess


def slugify_session(session_name: str) -> str:
    s = session_name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def get_event_list() -> list[dict]:
    html = fetch(SCHEDULE_URL)
    soup = BeautifulSoup(html, "html.parser")
    events = {}
    for a in soup.find_all("a", href=True):
        m = EVENT_LINK_RE.search(a["href"])
        if not m:
            continue
        slug = m.group(1)
        text = a.get_text(strip=True)
        if slug not in events or len(text) > len(events[slug]):
            events[slug] = text
    return [{"slug": slug, "name": name} for slug, name in sorted(events.items())]


def parse_event_page(slug: str) -> dict:
    url = f"{BASE_URL}/Schedule/{SEASON_YEAR}/{slug}"
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1")
    event_name = title_tag.get_text(strip=True) if title_tag else slug

    texts = [t.strip() for t in soup.stripped_strings if t.strip()]

    sessions = []
    current_day = None
    pending_time = None

    for line in texts:
        day_match = DAY_HEADER_RE.match(line)
        if day_match:
            current_day = day_match.groups()
            pending_time = None
            continue

        time_match = TIME_RE.match(line)
        if time_match:
            pending_time = time_match.group(1).upper().replace(" ", "")
            continue

        session_match = SESSION_RE.search(line)
        if session_match and current_day and pending_time:
            weekday, month_str, day_num = current_day
            session_name = session_match.group(1).strip()

            dt_str = f"{month_str} {day_num} {SEASON_YEAR} {pending_time}"
            try:
                naive_dt = dateparser.parse(dt_str)
                start_et = naive_dt.replace(tzinfo=EASTERN)
                start_utc = start_et.astimezone(UTC)
            except Exception:
                start_utc = None

            sessions.append({
                "session_name": session_name,
                "start_utc": start_utc,
            })
            pending_time = None

    return {"slug": slug, "event_name": event_name, "sessions": sessions}


def build_repo_events(scraped_events: list[dict]) -> list[dict]:
    """Convert raw scraped data into this repo's event schema, merging
    same-weekend site slugs (e.g. Milwaukee-Race1 + Milwaukee-Race2) under
    one track key, and disambiguating duplicate session names within a
    weekend (e.g. two "Race" sessions -> Race 1 / Race 2)."""

    # Group scraped pages by repo track key, preserving first-seen event_name
    grouped = {}  # track_key -> {"weekend_name": str, "raw_sessions": [(session_name, dt)]}
    for ev in scraped_events:
        track_key = slugify_track(ev["slug"])
        bucket = grouped.setdefault(track_key, {"weekend_name": ev["event_name"], "raw_sessions": []})
        for s in ev["sessions"]:
            bucket["raw_sessions"].append((s["session_name"], s["start_utc"]))

    repo_events = []
    for track_key, data in grouped.items():
        weekend_name = data["weekend_name"]
        raw_sessions = data["raw_sessions"]

        # De-duplicate identical (name, time) pairs that can occur if two
        # site pages for the same weekend both listed a shared session
        # (e.g. a shared Practice session shown on both Milwaukee race pages).
        seen = set()
        deduped = []
        for name, dt in raw_sessions:
            key = (name, dt.isoformat() if dt else None)
            if key in seen:
                continue
            seen.add(key)
            deduped.append((name, dt))

        # Sort by time first so numbering/ordering follows chronological order.
        deduped.sort(key=lambda x: (x[1] is None, x[1]))

        # Build (display_name, dt, id) for every session, guaranteeing the
        # final id is always unique even if:
        #  - the same session name occurs on genuinely different days/times
        #    on IndyCar's own page (e.g. Indy 500's "Practice 1" listed twice
        #    on the same day for a morning + evening window), or
        #  - two different-but-similarly-named sessions slugify to the same
        #    string.
        # We never skip disambiguation just because a name already ends in a
        # digit (e.g. "Qualifying 1") -- instead we always check the *final
        # id* for collisions and only append a suffix when one actually
        # occurs, which handles both cases correctly.
        # Count how many sessions share each base slug so numbering is
        # applied consistently: when there's a genuine collision, every
        # occurrence gets numbered ("Race 1" / "Race 2"), not just the
        # second one onward.
        base_slug_counts = {}
        for name, dt in deduped:
            if dt is None:
                continue
            base_slug_counts[slugify_session(name)] = base_slug_counts.get(slugify_session(name), 0) + 1

        used_ids = set()
        occurrence = {}
        for name, dt in deduped:
            if dt is None:
                continue  # skip anything we failed to parse a time for

            base_slug = slugify_session(name)
            base_id = f"indycar-{SEASON_YEAR}-{track_key}-{base_slug}"
            already_numbered = bool(re.search(r"\d$", name))

            if base_slug_counts[base_slug] > 1 and not already_numbered:
                occurrence[base_slug] = occurrence.get(base_slug, 0) + 1
                n = occurrence[base_slug]
                display_name = f"{name} {n}"
                candidate_id = f"{base_id}-{n}"
            else:
                display_name = name
                candidate_id = base_id

            # Final safety net: guarantee uniqueness no matter what
            # (handles cases like two already-numbered names, e.g. two
            # separate "Practice 1" sessions on the same day, that still
            # collide after the logic above).
            final_id = candidate_id
            dedupe_suffix = 1
            while final_id in used_ids:
                dedupe_suffix += 1
                final_id = f"{candidate_id}-{dedupe_suffix}"
                display_name = f"{name} ({dedupe_suffix})"
            candidate_id = final_id
            used_ids.add(candidate_id)

            repo_events.append({
                "id": candidate_id,
                "weekend": weekend_name,
                "name": display_name,
                "utc": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "_sort_key": dt,  # stripped before writing
            })

    repo_events.sort(key=lambda e: e["_sort_key"])
    for e in repo_events:
        del e["_sort_key"]
    return repo_events


def main():
    print("Fetching event list from schedule page...", file=sys.stderr)
    events = get_event_list()
    print(f"Found {len(events)} event pages for {SEASON_YEAR}", file=sys.stderr)

    scraped_events = []
    for i, ev in enumerate(events):
        slug = ev["slug"]
        print(f"[{i+1}/{len(events)}] Scraping {slug}...", file=sys.stderr)
        try:
            scraped_events.append(parse_event_page(slug))
        except Exception as e:
            print(f"  WARNING: failed to scrape {slug}: {e}", file=sys.stderr)
        time.sleep(REQUEST_DELAY_SECONDS)

    repo_events = build_repo_events(scraped_events)

    if not repo_events:
        print("ERROR: parsed 0 sessions. Site structure may have changed. "
              "Aborting without writing output.", file=sys.stderr)
        sys.exit(1)

    output = {
        "sportKey": "ntt-indycar",
        "season": str(SEASON_YEAR),
        "events": repo_events,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Wrote {len(repo_events)} sessions to {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
