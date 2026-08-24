#!/usr/bin/env python3
"""
Targeted Basketball Scraper for sportocal-data.
Fetches top-tier professional leagues, college basketball, and international tournaments.
Outputs to basketball/espn-all/<slug>.json.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_core_api_common import build_events, fetch_league_name  # noqa: E402

SPORT = "basketball"
PAST_DAYS = 14
FUTURE_DAYS = 270
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "basketball" / "espn-all"
MIN_EVENTS_THRESHOLD = 5

TARGET_LEAGUES = {
    # Top Professional & Developmental
    "wnba": "WNBA",
    "nba-g-league": "NBA G League",

    # College Basketball
    "mens-college-basketball": "NCAA Men's Basketball",
    "womens-college-basketball": "NCAA Women's Basketball",

    # Top International & European
    "fiba": "FIBA Basketball World Cup",
    "fiba-americup": "FIBA AmeriCup",
    "fiba-eurobasket": "FIBA EuroBasket",
    "nbl": "NBL (Australia)",
}

BLOCKED_KEYWORDS = ("friendly", "exhibition", ".u20", ".u19", ".u18", ".u17")


def is_valid_slug(slug: str) -> bool:
    if slug == "nba":
        return False  # Handled by standalone nba.py
    if any(kw in slug.lower() for kw in BLOCKED_KEYWORDS):
        return False
    return True


def get_target_leagues() -> dict[str, str]:
    if len(sys.argv) > 1:
        raw = sys.argv[1]
        slugs = [s.strip() for s in raw.split(",") if s.strip()]
        return {s: TARGET_LEAGUES.get(s, s) for s in slugs}
    env_slugs = os.environ.get("SPORT_LEAGUE_SLUGS", "")
    if env_slugs:
        slugs = [s.strip() for s in env_slugs.split(",") if s.strip()]
        return {s: TARGET_LEAGUES.get(s, s) for s in slugs}
    return TARGET_LEAGUES


def main():
    targets = get_target_leagues()
    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=PAST_DAYS)).strftime("%Y%m%d")
    date_to = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y%m%d")

    print(f"Scraping {len(targets)} basketball league(s) ({date_from} to {date_to})...", file=sys.stderr)
    written, skipped = 0, 0

    for slug, preferred_name in targets.items():
        if not is_valid_slug(slug):
            continue

        print(f"Fetching: {preferred_name} [{slug}]", file=sys.stderr)
        try:
            events = build_events(
                sport=SPORT,
                league_slug=slug,
                id_prefix=slug,
                sport_key=f"basketball-{slug}",
                date_from=date_from,
                date_to=date_to,
                round_prefix="Week",
            )
        except Exception as err:
            print(f"  ERROR: {slug} failed ({err!r}), skipping.", file=sys.stderr)
            continue

        if len(events) < MIN_EVENTS_THRESHOLD:
            print(f"  {slug}: only {len(events)} events, skipping.", file=sys.stderr)
            skipped += 1
            continue

        league_name = fetch_league_name(SPORT, slug)
        display_name = preferred_name if league_name == slug else league_name

        output_path = OUTPUT_DIR / f"{slug}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "sportKey": f"basketball-{slug}",
                    "leagueName": display_name,
                    "windowFrom": date_from,
                    "windowTo": date_to,
                    "events": events,
                },
                indent=2,
            )
            + "\n"
        )
        print(f"  Wrote {len(events)} events to {output_path.name}", file=sys.stderr)
        written += 1

    print(f"\nCompleted: {written} written, {skipped} skipped.", file=sys.stderr)


if __name__ == "__main__":
    main()
