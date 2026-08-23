#!/usr/bin/env python3
"""
Sport-agnostic ESPN Core API helper. Originally this logic lived only in
espn_soccer_common.py; pulled out here so basketball (and whatever's
added after it) doesn't duplicate the fetch/retry/parse logic - only the
sport-specific bits (season date range, weekend/round labeling
conventions) live in each sport's own thin wrapper module.

See espn_soccer_common.py's original docstring for why this uses
sports.core.api.espn.com rather than site.api.espn.com (short version:
the Site API returns a uniform 403 from GitHub Actions runners; the
Core API is the same host this repo's NASCAR ESPN fallback already
uses successfully).

Core API URL shape: sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events
  e.g. sport="soccer", league="eng.1"
       sport="basketball", league="nba"
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, slugify, make_unique_id_assigner, write_output  # noqa: E402

CORE_API_ROOT = "https://sports.core.api.espn.com/v2/sports"

# Separators ESPN uses in an event's "name"/"shortName" between the two
# teams. "X vs Y" lists home team first; "X at Y" lists the away team
# first ("Away at Home"), so each pattern's (home, away) group order is
# flipped to match - both map to plain (home, away) below. Holds across
# every team sport ESPN covers (soccer, basketball, hockey, football),
# since it's the same underlying "Event" schema regardless of sport.
NAME_SPLIT_PATTERNS = [
    (re.compile(r"^(?P<home>.+?)\s+vs\.?\s+(?P<away>.+)$", re.IGNORECASE)),
    (re.compile(r"^(?P<away>.+?)\s+at\s+(?P<home>.+)$", re.IGNORECASE)),
]


def to_utc_iso(date_str: str) -> str | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _get_with_retries(url: str, params: dict | None = None, retries: int = 3, timeout: int = 15):
    """GET with retry/backoff on 429 and transient network errors. Returns
    (response_or_None, error_reason_or_None)."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        except requests.RequestException as err:
            last_error = f"request error: {err}"
            if attempt < retries:
                time.sleep(2.0 ** attempt)
            continue

        if res.status_code == 429:
            last_error = "HTTP 429 (rate limited)"
            if attempt < retries:
                retry_after = res.headers.get("Retry-After")
                sleep_for = float(retry_after) if retry_after else 2.0 ** attempt
                print(f"  Rate limited on {url}, waiting {sleep_for:.0f}s (attempt {attempt}/{retries})...", file=sys.stderr)
                time.sleep(sleep_for)
            continue

        if res.status_code != 200:
            return None, f"HTTP {res.status_code}"

        return res, None

    return None, last_error


def fetch_event_refs(sport: str, league_slug: str, date_from: str, date_to: str) -> tuple[list[str], str | None]:
    """All event $ref URLs for the league in the given date range, via the
    Core API's paginated events list. Returns (refs, error_reason)."""
    url = f"{CORE_API_ROOT}/{sport}/leagues/{league_slug}/events"
    params = {"dates": f"{date_from}-{date_to}", "limit": 1000}

    refs = []
    page = 1
    while True:
        params["page"] = page
        res, error = _get_with_retries(url, params=params)
        if error:
            return refs, error
        try:
            body = res.json()
        except ValueError as err:
            return refs, f"invalid JSON: {err}"

        for item in body.get("items", []):
            ref = item.get("$ref") if isinstance(item, dict) else None
            if ref:
                refs.append(ref)

        page_count = body.get("pageCount", 1)
        if page >= page_count:
            break
        page += 1

    return refs, None


def fetch_event(ref_url: str) -> tuple[dict | None, str | None]:
    """Fetches one event's full object from its $ref URL."""
    res, error = _get_with_retries(ref_url, timeout=10)
    if error:
        return None, error
    try:
        return res.json(), None
    except ValueError as err:
        return None, f"invalid JSON: {err}"


def extract_teams(event: dict) -> tuple[str, str] | None:
    """(home_name, away_name) parsed from the event's own "name" (falling
    back to "shortName"), splitting on ESPN's "X vs Y" / "X at Y"
    convention. No follow-up calls - see module docstring."""
    for field in ("name", "shortName"):
        raw = event.get(field)
        if not isinstance(raw, str) or not raw.strip():
            continue
        for pattern in NAME_SPLIT_PATTERNS:
            m = pattern.match(raw.strip())
            if m:
                home, away = m.group("home").strip(), m.group("away").strip()
                if home and away:
                    return home, away
    return None


def extract_weekend_label(event: dict, round_prefix: str = "Week") -> str | None:
    """Best-effort round/week label - tries a few plausible field
    locations that hold across sports; returns None if nothing usable is
    found (caller should fall back to something date-based rather than
    guess)."""
    week = event.get("week")
    if isinstance(week, dict) and week.get("number"):
        return f"{round_prefix} {week['number']}"

    season = event.get("season")
    if isinstance(season, dict):
        for key in ("displayName", "slug", "type"):
            val = season.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    for note in event.get("notes") or []:
        headline = note.get("headline") if isinstance(note, dict) else None
        if headline:
            return headline.strip()

    return None


def build_events(
    sport: str,
    league_slug: str,
    id_prefix: str,
    sport_key: str,
    date_from: str,
    date_to: str,
    round_prefix: str = "Week",
) -> list[dict]:
    """Fetches and flattens one league's full schedule for the given date
    range into this repo's standard {id, weekend, name, utc} shape."""
    print(f"Fetching {sport_key} event list for {date_from}-{date_to}...", file=sys.stderr)
    refs, list_error = fetch_event_refs(sport, league_slug, date_from, date_to)
    if list_error:
        print(f"  ERROR: couldn't fetch event list: {list_error}", file=sys.stderr)
        return []
    print(f"  Found {len(refs)} events, fetching each one...", file=sys.stderr)

    assign_id = make_unique_id_assigner()
    events = []
    fetch_failures = 0
    extract_failures = 0
    debug_printed = 0

    for i, ref in enumerate(refs, 1):
        event, error = fetch_event(ref)
        if error:
            fetch_failures += 1
            if fetch_failures <= 3:
                print(f"  DEBUG: fetch failed for {ref}: {error}", file=sys.stderr)
            continue

        utc_iso = to_utc_iso(event.get("date"))
        teams = extract_teams(event)
        if not utc_iso or not teams:
            extract_failures += 1
            if debug_printed < 2:
                print(f"  DEBUG: couldn't extract utc/teams from {ref}. Top-level keys: {sorted(event.keys())}", file=sys.stderr)
                print(f"  DEBUG: raw event JSON (first 2000 chars):", file=sys.stderr)
                print(f"    {json.dumps(event)[:2000]}", file=sys.stderr)
                debug_printed += 1
            continue
        home, away = teams

        weekend = extract_weekend_label(event, round_prefix) or utc_iso[:10]
        match_name = f"{home} v {away}"
        base_id = f"{id_prefix}-{utc_iso[:10]}-{slugify(home)}-{slugify(away)}"

        events.append({
            "id": assign_id(base_id),
            "weekend": weekend,
            "name": match_name,
            "utc": utc_iso,
        })

        if i % 50 == 0:
            print(f"  ...{i}/{len(refs)} events checked, {len(events)} matches so far", file=sys.stderr)

    print(f"Checked {len(refs)} events, kept {len(events)} matches.", file=sys.stderr)
    if fetch_failures or extract_failures:
        print(
            f"  {fetch_failures} event(s) failed to fetch, "
            f"{extract_failures} event(s) fetched but couldn't be parsed",
            file=sys.stderr,
        )

    events.sort(key=lambda e: e["utc"])
    return events


def run_league_scraper(
    sport: str,
    league_slug: str,
    id_prefix: str,
    sport_key: str,
    season_label: str,
    output_path: Path,
    date_from: str,
    date_to: str,
    round_prefix: str = "Week",
    min_events: int = 20,
):
    """Shared entrypoint for each per-league script's main()."""
    events = build_events(sport, league_slug, id_prefix, sport_key, date_from, date_to, round_prefix)
    output = {
        "sportKey": sport_key,
        "season": season_label,
        "events": events,
    }
    write_output(output_path, output, min_events=min_events)
