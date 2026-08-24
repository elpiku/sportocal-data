#!/usr/bin/env python3
"""
Targeted Soccer Scraper for sportocal-data.
Fetches only curated top-tier leagues, secondary divisions, major continental tournaments,
national cups, and premier women's competitions. Filters out low-event friendlies,
college athletics (NCAA), and preliminary qualifiers.
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
MIN_EVENTS_THRESHOLD = 15  # Drops single-match exhibitions and dead feeds

# Targeted catalog mapped by category for maintenance clarity
TARGET_LEAGUES = {
    # Tier 1 Global Core
    "fra.1": "Ligue 1",
    "bra.1": "Brasileirão Série A",
    "mex.1": "Liga MX",
    "por.1": "Primeira Liga",
    "ned.1": "Eredivisie",
    "ksa.1": "Saudi Pro League",
    "tur.1": "Süper Lig",
    "arg.1": "Argentine Primera División",
    "sco.1": "Scottish Premiership",
    "bel.1": "Belgian Pro League",
    "jpn.1": "J1 League",
    "col.1": "Categoría Primera A",
    "gre.1": "Greek Super League",
    "aut.1": "Austrian Bundesliga",
    "den.1": "Danish Superliga",
    "nor.1": "Norwegian Eliteserien",
    "swe.1": "Swedish Allsvenskan",
    "chn.1": "Chinese Super League",
    
    # Tier 2 Popular Divisions
    "eng.2": "EFL Championship",
    "ger.2": "2. Bundesliga",
    "esp.2": "LaLiga 2",
    "fra.2": "Ligue 2",
    "ita.2": "Serie B",
    "ned.2": "Eerste Divisie",
    "bra.2": "Série B (Brazil)",
    "usa.usl.1": "USL Championship",
    
    # Major Domestic Cups
    "eng.fa": "FA Cup",
    "eng.league_cup": "Carabao Cup",
    "esp.copa_del_rey": "Copa del Rey",
    "ita.coppa_italia": "Coppa Italia",
    "ger.dfb_pokal": "DFB-Pokal",
    "ned.cup": "KNVB Beker",
    "por.taca.portugal": "Taça de Portugal",
    "bra.copa_do_brazil": "Copa do Brasil",
    "arg.copa": "Copa Argentina",
    "usa.open": "U.S. Open Cup",
    "ksa.kings.cup": "Saudi King's Cup",

    # Continental & International Tournaments
    "uefa.champions": "UEFA Champions League",
    "uefa.europa": "UEFA Europa League",
    "uefa.europa.conf": "UEFA Conference League",
    "conmebol.libertadores": "Copa Libertadores",
    "conmebol.sudamericana": "Copa Sudamericana",
    "caf.champions": "CAF Champions League",
    "caf.confed": "CAF Confederation Cup",
    "afc.champions": "AFC Champions League Elite",
    "afc.cup": "AFC Champions League Two",
    "uefa.nations": "UEFA Nations League",
    "concacaf.nations.league": "CONCACAF Nations League",
    "concacaf.central.american.cup": "CONCACAF Central American Cup",
    "fifa.worldq.uefa": "FIFA World Cup Qualifiers - UEFA",
    "fifa.worldq.conmebol": "FIFA World Cup Qualifiers - CONMEBOL",

    # Top Women's Football
    "usa.nwsl": "NWSL",
    "eng.w.1": "Barclays Women's Super League",
    "esp.w.1": "Liga F",
    "fra.w.1": "Première Ligue",
    "ned.w.1": "Vrouwen Eredivisie",
    "aus.w.1": "A-League Women",
    "can.w.nsl": "Northern Super League",
    "usa.w.usl.1": "USL Super League",
    "uefa.wchampions": "UEFA Women's Champions League",
}

# Exclusion rules for automated sanity checks
BLOCKED_KEYWORDS = (".ncaa.", "_qual", "friendly", "supercopa", ".u20", "trophy", "challenge")

def is_valid_slug(slug: str) -> bool:
    """Verifies slug belongs to the target set and passes blacklist checks."""
    if slug not in TARGET_LEAGUES:
        return False
    if any(keyword in slug.lower() for keyword in BLOCKED_KEYWORDS):
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
            print(f"  {slug}: only {len(events)} events (below {MIN_EVENTS_THRESHOLD}), skipping.", file=sys.stderr)
            skipped += 1
            continue

        # Use clean curated name fallback if remote ESPN fetch is generic
        league_name = fetch_league_name(slug)
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
