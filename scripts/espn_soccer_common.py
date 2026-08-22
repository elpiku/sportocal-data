#!/usr/bin/env python3
"""
Shared helper for the football/soccer scrapers in this repo (Premier
League, Champions League, La Liga, Serie A, Bundesliga, MLS).

Uses ESPN's public "Site API" scoreboard endpoint, one call per calendar
day in the season:
  GET site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates=YYYYMMDD
This returns every match on that day fully expanded (kickoff time,
home/away team names, matchweek/round where available) in a single
response - no follow-up calls needed per match.

This replaces an earlier version that used the Core API's
leagues/{league}/events list + per-event "$ref" follow-up (the same
pattern already working for this repo's NASCAR/MotoGP scrapers). That
turned out not to translate to soccer: a real run showed the Core API's
event list returned the right *count* of matches, but each individual
event's own "competitions" field was itself just another {"$ref": ...}
stub, and each competitor inside that was *also* just a stub - reaching
an actual team name would have meant a 4-5-deep ref chain per match
(event -> competition -> competitor -> team), multiplying the API calls
per league from ~380 to well over 1500 and making the already-real risk
of hitting ESPN's rate limit (shared across every GitHub Actions runner
IP, not just this scraper) much worse. The Site API's scoreboard
endpoint returns fully expanded data directly, so this rewrite needs
only one call per calendar day instead of several calls per match.

Run any of the per-league scripts from the repo root, e.g.:
  python scripts/premier_league.py
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, slugify, make_unique_id_assigner, write_output  # noqa: E402

SITE_API_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# site.api.espn.com directly powers espn.com's own website widgets and
# appears to reject requests without a browser-like Referer/Origin - a
# uniform, immediate 403 on every single call (not a gradual/intermittent
# failure) is the signature of that kind of edge/CDN check, as opposed to
# rate limiting (which responds 429, not 403) or a broader IP block
# (which tends to be inconsistent, not literally 100%). This is scoped to
# just these soccer scrapers rather than added to common.HEADERS globally,
# since every other scraper in this repo is already working fine without it.
ESPN_SITE_HEADERS = {
    **HEADERS,
    "Referer": "https://www.espn.com/",
    "Origin": "https://www.espn.com",
    "Accept": "application/json, text/plain, */*",
}


def to_utc_iso(date_str: str) -> str | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def daterange(date_from: str, date_to: str):
    """Yields every 'YYYYMMDD' string from date_from to date_to inclusive."""
    start = datetime.strptime(date_from, "%Y%m%d")
    end = datetime.strptime(date_to, "%Y%m%d")
    d = start
    while d <= end:
        yield d.strftime("%Y%m%d")
        d += timedelta(days=1)


def fetch_day_scoreboard(league_slug: str, yyyymmdd: str, retries: int = 3) -> tuple[list[dict], str | None]:
    """One day's fully-expanded events from the Site API scoreboard.
    Returns (events, error_reason). Retries on HTTP 429 (rate limited),
    respecting ESPN's Retry-After header when present - see module
    docstring for why this matters more here than it might seem to."""
    url = f"{SITE_API_BASE}/{league_slug}/scoreboard"
    params = {"dates": yyyymmdd, "limit": 1000}

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, headers=ESPN_SITE_HEADERS, params=params, timeout=15)
        except requests.RequestException as err:
            last_error = f"request error: {err}"
            continue

        if res.status_code == 429:
            last_error = "HTTP 429 (rate limited)"
            if attempt < retries:
                retry_after = res.headers.get("Retry-After")
                sleep_for = float(retry_after) if retry_after else 2.0 ** attempt
                print(
                    f"  Rate limited fetching {yyyymmdd}, waiting {sleep_for:.0f}s "
                    f"(attempt {attempt}/{retries})...",
                    file=sys.stderr,
                )
                time.sleep(sleep_for)
            continue

        if res.status_code != 200:
            return [], f"HTTP {res.status_code}"

        try:
            return res.json().get("events", []), None
        except ValueError as err:
            return [], f"invalid JSON: {err}"

    return [], last_error


def extract_teams(event: dict) -> tuple[str, str] | None:
    """(home_name, away_name) from an ESPN event's competitors list."""
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    competitors = competitions[0].get("competitors") or []

    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None

    def team_name(c: dict) -> str | None:
        team = c.get("team")
        if isinstance(team, dict):
            return team.get("displayName") or team.get("name")
        return None

    home_name, away_name = team_name(home), team_name(away)
    if not home_name or not away_name:
        return None
    return home_name, away_name


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

    competitions = event.get("competitions") or []
    for comp in competitions:
        for note in comp.get("notes") or []:
            headline = note.get("headline")
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
    days = list(daterange(date_from, date_to))
    print(f"Fetching {sport_key} scoreboard for {len(days)} days ({date_from} to {date_to})...", file=sys.stderr)

    assign_id = make_unique_id_assigner()
    events = []
    fetch_failures = 0
    extract_failures = 0
    debug_printed = 0
    total_matches_seen = 0

    for i, day in enumerate(days, 1):
        day_events, error = fetch_day_scoreboard(league_slug, day)
        if error:
            fetch_failures += 1
            if fetch_failures <= 3:
                print(f"  DEBUG: fetch failed for {day}: {error}", file=sys.stderr)
            continue

        for event in day_events:
            total_matches_seen += 1
            utc_iso = to_utc_iso(event.get("date"))
            teams = extract_teams(event)
            if not utc_iso or not teams:
                extract_failures += 1
                if debug_printed < 2:
                    print(
                        f"  DEBUG: couldn't extract utc/teams from a {day} event. "
                        f"Top-level keys: {sorted(event.keys())}",
                        file=sys.stderr,
                    )
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

        if i % 30 == 0:
            print(f"  ...{i}/{len(days)} days checked, {len(events)} matches so far", file=sys.stderr)

    print(f"Checked {len(days)} days, saw {total_matches_seen} matches total.", file=sys.stderr)
    if fetch_failures or extract_failures:
        print(
            f"  {fetch_failures} day(s) failed to fetch, "
            f"{extract_failures} match(es) fetched but couldn't be parsed",
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
