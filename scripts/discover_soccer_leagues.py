#!/usr/bin/env python3
"""
Discovers every soccer competition slug ESPN's Core API currently lists,
so the "scrape everything" workflow doesn't need a hand-maintained list.

GET sports.core.api.espn.com/v2/sports/soccer/leagues?limit=1000
returns a paginated collection of {"$ref": ".../leagues/{slug}?..."}
stubs - one per competition. The slug is embedded in the $ref URL
itself, so slug discovery needs zero follow-up calls; it's one cheap,
paginated request regardless of how many hundred competitions ESPN has.

Getting each competition's real display name (--with-names) DOES need a
follow-up call per league, since the stub only has the $ref, not the
name - that's one extra request per competition (~250 total), still
cheap, just not free the way the slug itself is.

Usage:
  python scripts/discover_soccer_leagues.py                          # prints one slug per line
  python scripts/discover_soccer_leagues.py --with-names             # prints "slug<TAB>name" per line
  python scripts/discover_soccer_leagues.py --batch-size 15          # prints JSON: list of slug-batches
  python scripts/discover_soccer_leagues.py --batch-size 15 --with-names --names-output scripts/soccer_league_names.json
      # batches (slugs only, for the scrape matrix) go to stdout as before;
      # real names get written separately to the given JSON file
  python scripts/discover_soccer_leagues.py --github-output batches  # also writes
      `batches=<json>` to $GITHUB_OUTPUT for a workflow matrix step
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS  # noqa: E402
import requests

LEAGUES_URL = "https://sports.core.api.espn.com/v2/sports/soccer/leagues"
REF_SLUG_RE = re.compile(r"/leagues/([^/?]+)")

# Already covered by their own curated, full-season scripts (premier_league.py,
# la_liga.py, bundesliga.py, serie_a.py, mls.py) - skip here so they're not
# scraped twice under two different shapes. See champions_league.py, which
# is NOT excluded: uefa.champions is curated too, but its curated script
# only writes when there's actual league-phase data, same as this one would.
CURATED_ELSEWHERE = {"eng.1", "esp.1", "ger.1", "ita.1", "usa.1"}


def discover_slugs() -> list[str]:
    slugs = []
    page = 1
    while True:
        res = requests.get(
            LEAGUES_URL, headers=HEADERS, params={"limit": 1000, "page": page}, timeout=20
        )
        res.raise_for_status()
        body = res.json()

        for item in body.get("items", []):
            ref = item.get("$ref") if isinstance(item, dict) else None
            if not ref:
                continue
            m = REF_SLUG_RE.search(ref)
            if m:
                slugs.append(m.group(1))

        page_count = body.get("pageCount", 1)
        if page >= page_count:
            break
        page += 1

    # Stable order, de-duplicated (a slug could theoretically repeat across pages
    # if ESPN's collection shifts under us mid-pagination).
    seen = set()
    unique = []
    for s in slugs:
        if s not in seen and s not in CURATED_ELSEWHERE:
            seen.add(s)
            unique.append(s)
    return unique


def chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def fetch_league_names(slugs: list[str], retries: int = 3) -> dict[str, str]:
    """One GET per slug for its real "name"/"displayName" - see module
    docstring for why this isn't folded into discover_slugs() by default."""
    names = {}
    for i, slug in enumerate(slugs, 1):
        url = f"{LEAGUES_URL}/{slug}"
        name = None
        for attempt in range(1, retries + 1):
            try:
                res = requests.get(url, headers=HEADERS, params={"lang": "en", "region": "us"}, timeout=15)
            except requests.RequestException as err:
                if attempt < retries:
                    time.sleep(2.0 ** attempt)
                    continue
                print(f"  WARNING: {slug} failed after {retries} attempts ({err}), keeping slug as name.", file=sys.stderr)
                break

            if res.status_code == 429:
                retry_after = res.headers.get("Retry-After")
                sleep_for = float(retry_after) if retry_after else 2.0 ** attempt
                if attempt < retries:
                    time.sleep(sleep_for)
                    continue
                print(f"  WARNING: {slug} rate-limited after {retries} attempts, keeping slug as name.", file=sys.stderr)
                break

            if res.status_code != 200:
                print(f"  WARNING: {slug} returned HTTP {res.status_code}, keeping slug as name.", file=sys.stderr)
                break

            try:
                body = res.json()
            except ValueError:
                print(f"  WARNING: {slug} returned invalid JSON, keeping slug as name.", file=sys.stderr)
                break

            name = body.get("name") or body.get("displayName") or body.get("shortName")
            break

        names[slug] = name.strip() if isinstance(name, str) and name.strip() else slug

        if i % 25 == 0:
            print(f"  ...fetched {i}/{len(slugs)} league names", file=sys.stderr)

    return names


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=None,
                         help="If set, output JSON batches of this many slugs each instead of one-per-line.")
    parser.add_argument("--github-output", metavar="VAR_NAME", default=None,
                         help="Also write '<VAR_NAME>=<json>' to $GITHUB_OUTPUT (requires --batch-size).")
    parser.add_argument("--with-names", action="store_true",
                         help="Fetch each competition's real name from ESPN (one extra request per league) "
                              "instead of a slug-derived guess.")
    parser.add_argument("--names-output", metavar="PATH", default=None,
                         help="Write the {slug: name} mapping to this JSON file (implies --with-names).")
    args = parser.parse_args()
    if args.names_output:
        args.with_names = True

    slugs = discover_slugs()
    print(f"Discovered {len(slugs)} soccer competition slugs.", file=sys.stderr)

    names = None
    if args.with_names:
        print(f"Fetching real names for {len(slugs)} competitions (one request each)...", file=sys.stderr)
        names = fetch_league_names(slugs)
        if args.names_output:
            Path(args.names_output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.names_output).write_text(json.dumps(names, indent=2, sort_keys=True) + "\n")
            print(f"  Wrote names to {args.names_output}", file=sys.stderr)

    if args.batch_size:
        batches = chunk(slugs, args.batch_size)
        payload = json.dumps(batches)
        print(payload)
        if args.github_output:
            gh_out = os.environ.get("GITHUB_OUTPUT")
            if not gh_out:
                print("  WARNING: --github-output given but $GITHUB_OUTPUT is not set; skipping.", file=sys.stderr)
            else:
                with open(gh_out, "a") as f:
                    f.write(f"{args.github_output}={payload}\n")
    else:
        for s in slugs:
            if names:
                print(f"{s}\t{names[s]}")
            else:
                print(s)


if __name__ == "__main__":
    main()
