#!/usr/bin/env python3
"""
Targeted Soccer Scraper for sportocal-data.
Fetches only curated Top-Tier leagues, popular Secondary Divisions,
Major Continental/International tournaments, Primary Domestic Cups,
and Top Women's competitions.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_soccer_common import build_events, fetch_league_name  # noqa: E402

PAST_DAYS = 14
FUTURE_DAYS = 270
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "football" / "espn-all"
MIN_EVENTS_THRESHOLD = 5

# Curated catalog: Top Tier, Tier 2, Major Cups, Continental, & Women's
TARGET_LEAGUES = {
    # Tier 1 Domestic Leagues (excluding PL, La Liga, Serie A, Bundesliga, MLS which have standalone scripts)
    "fra.1": "Ligue 1",
    "bra.1": "Brasileirao Serie A",
    "mex.1": "Liga MX",
    "por.1": "Primeira Liga",
    "ned.1": "Eredivisie",
    "ksa.1": "Saudi Pro League",
    "tur.1": "Super Lig",
    "arg.1": "Argentine Primera Division",
    "sco.1": "Scottish Premiership",
    "bel.1": "Belgian Pro League",
    "jpn.1": "J1 League",

    # Tier 2 Popular Leagues
    "eng.2": "EFL Championship",
    "ger.2": "2. Bundesliga",
    "esp.2": "LaLiga 2",
    "fra.2": "Ligue 2",
    "ita.2": "Serie B",
    "ned.2": "Eerste Divisie",
    "bra.2": "Serie B (Brazil)",

    # Major Continental & International Tournaments
    "uefa.champions": "UEFA Champions League",
    "uefa.europa": "UEFA Europa League",
    "uefa.europa.conf": "UEFA Conference League",
    "conmebol.libertadores": "Copa Libertadores",
    "conmebol.sudamericana": "Copa Sudamericana",
    "caf.champions": "CAF Champions League",
    "afc.champions": "AFC Champions League Elite",
    "uefa.nations": "UEFA Nations League",
    "concacaf.nations.league": "CONCACAF Nations League",
    "fifa.worldq.uefa": "FIFA World Cup Qualifiers - UEFA",
    "fifa.worldq.conmebol": "FIFA World Cup Qualifiers - CONMEBOL",

    # Primary Domestic Cups
    "eng.fa": "FA Cup",
    "eng.league_cup": "Carabao Cup",
    "esp.copa_del_rey": "Copa del Rey",
    "ita.coppa_italia": "Coppa Italia",
    "ger.dfb_pokal": "DFB-Pokal",
    "ned.cup": "KNVB Beker",
    "por.taca.portugal": "Taca de Portugal",
    "bra.copa_do_brazil": "Copa do Brasil",
    "arg.copa": "Copa Argentina",
    "usa.open": "U.S. Open Cup",
    "fra.coupe_de_france": "Coupe de France",

    # Top Women's Leagues & Competitions
    "usa.nwsl": "NWSL",
    "eng.w.1": "Barclays Women's Super League",
    "esp.w.1": "Liga F",
    "fra.w.1": "Premiere Ligue",
    "ger.w.1": "Frauen-Bundesliga",
    "uefa.wchampions": "UEFA Women's Champions League",
}

# Slugs covered by their own curated scripts
CURATED_ELSEWHERE = {"eng.1", "esp.1", "ger.1", "ita.1", "usa.1"}

# Strict keyword filters
BLOCKED_KEYWORDS = (
    ".ncaa.",
    "_qual",
    "friendly",
    "supercopa",
    "super_cup",
    ".u20",
    ".u17",
    "trophy",
    "challenge",
    "charity",
)

def is_valid_slug(slug: str) -> bool:
    if slug in CURATED_ELSEWHERE:
        return False
    if slug not in TARGET_LEAGUES:
        return False
    if any(kw in slug.lower() for kw in BLOCKED_KEYWORDS):
        return False
    return True

def main():
    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=PAST_DAYS)).strftime("%Y%m%d")
    date_to = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y%m%d")

    print(f"Scraping {len(TARGET_LEAGUES)} targeted leagues ({date_from} to {date_to})...", file=sys.stderr)
    written = 0
    skipped = 0

    for slug, preferred_name in TARGET_LEAGUES.items():
        if not is_valid_slug(slug):
            continue

        print(f"Fetching: {preferred_name} [{slug}]", file=sys.stderr)
        try:
            events = build_events(
                sport="soccer",
                league_slug=slug,
                id_prefix=slug,
                sport_key=f"soccer-{slug}",
                date_from=date_from,
                date_to=date_to,
            )
        except Exception as err:
            print(f"  ERROR: {slug} failed ({err!r}), skipping.", file=sys.stderr)
            continue

        if len(events) < MIN_EVENTS_THRESHOLD:
            print(f"  {slug}: only {len(events)} events, skipping.", file=sys.stderr)
            skipped += 1
            continue

        league_name = fetch_league_name("soccer", slug)
        display_name = preferred_name if league_name == slug else league_name

        output_path = OUTPUT_DIR / f"{slug}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "sportKey": f"soccer-{slug}",
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
