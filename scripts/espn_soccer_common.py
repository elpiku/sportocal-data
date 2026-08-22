#!/usr/bin/env python3
"""
Shared helper for the football/soccer scrapers in this repo (Premier
League, Champions League, La Liga, Serie A, Bundesliga, MLS).

Uses ESPN's "Core API" (sports.core.api.espn.com), the same ESPN host
this repo's nascar_cup.py already calls successfully as its ESPN
fallback - see ESPN_CORE_API_URL there. This is a deliberate move away
from the "Site API" (site.api.espn.com) this file used previously:
that host returned a uniform HTTP 403 on every single request when run
from GitHub Actions (confirmed from an actual failed run - all 365
days failed identically, which is the signature of an IP/CDN-level
block on GitHub's runner ranges, not rate limiting or a header
problem - a 429 or an inconsistent failure pattern would look
different, and adding a Referer/Origin header to mimic a browser made
no difference). sports.core.api.espn.com is a different backend behind
what's apparently a different bot-protection policy, and it's already
proven to work from this repo's GitHub Actions runners via NASCAR.

Two calls per match instead of one:
  1. GET .../leagues/{league}/events?dates=YYYYMMDD-YYYYMMDD&limit=1000
     Lists every match in the range. Paginated (follows pageCount),
     but each item here is only an {"id", "$ref"} stub.
  2. GET the event's own $ref URL for the full object.
This is more calls than the single-request-per-day Site API approach
this file used before, but that approach doesn't work from CI at all,
so more-but-working beats fewer-but-blocked. A full 380-game Premier
League season is ~381 requests (1 list + 380 events) instead of 365 -
similar order of magnitude, not the 1500+ deep-ref-chain worst case
an earlier version of this file hit when it tried resolving team names
via the event -> competition -> competitor -> team ref chain: this
version reads team names from the event object's own top-level "name"
field instead (e.g. "Chelsea vs Arsenal"), which requires no further
calls, per the pattern ESPN uses across its "Event" schema regardless
of sport. If a particular event's "name" is ever missing or doesn't
parse into two teams, it's skipped and logged rather than guessed at.

Run any of the per-league scripts from the repo root, e.g.:
  python scripts/premier_league.py
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

CORE_API_BASE = "https://sports.core.api.espn.com/v2/sports/soccer/leagues"

# Separators ESPN uses in an event's "name"/"shortName" between the two
# teams. "X vs Y" lists home team first; "X at Y" lists the away team
# first ("Away at Home"), so each pattern's (home, away) group order is
# flipped to match - both map to plain (home, away) below.
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


def fetch_event_refs(league_slug: str, date_from: str, date_to: str) -> tuple[list[str], str | None]:
    """All event $ref URLs for the league in the given date range, via the
    Core API's paginated events list. Returns (refs, error_reason)."""
    url = f"{CORE_API_BASE}/{league_slug}/events"
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


def extract_weekend_label(event: dict, round_prefix: str = "Matchweek") -> str | None:
    """Best-effort matchweek/round label - ESPN's soccer events sometimes
    carry a numbered week, sometimes a named round (e.g. Champions League
    group/knockout stage) depending on the competition. Tries a few
    plausible field locations; returns None if nothing usable is found
    (caller should fall back to something date-based rather than guess)."""
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
    league_slug: str,
    id_prefix: str,
    sport_key: str,
    date_from: str,
    date_to: str,
    round_prefix: str = "Matchweek",
) -> list[dict]:
    """Fetches and flattens one league's full schedule for the given date
    range into this repo's standard {id, weekend, name, utc} shape."""
    print(f"Fetching {sport_key} event list for {date_from}-{date_to}...", file=sys.stderr)
    refs, list_error = fetch_event_refs(league_slug, date_from, date_to)
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
    league_slug: str,
    id_prefix: str,
    sport_key: str,
    season_label: str,
    output_path: Path,
    date_from: str,
    date_to: str,
    round_prefix: str = "Matchweek",
    min_events: int = 20,
):
    """Shared entrypoint for each per-league script's main()."""
    events = build_events(league_slug, id_prefix, sport_key, date_from, date_to, round_prefix)
    output = {
        "sportKey": sport_key,
        "season": season_label,
        "events": events,
    }
    write_output(output_path, output, min_events=min_events)
