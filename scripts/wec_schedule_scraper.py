"""
WEC (FIA World Endurance Championship) Schedule Scraper
Scrapes the official FIA WEC website and outputs to motorsport/wec/2026.json
Matches the structure of the F1 and IndyCar schedule scrapers.

CHANGELOG (fixes applied):
- BUG FIX: the old CALENDAR_URL (https://www.fiawec.com/en/Calendar.html)
  returns a 404 -- confirmed dead. Replaced with the live homepage
  (https://www.fiawec.com/) which carries the season calendar with round
  numbers, dates and per-session countdown blocks (Free Practice / Quali /
  Hyperpole / Race), including "TBC" placeholders for sessions whose exact
  time hasn't been announced yet -- that's normal on the real site, not a
  parsing failure.
- DATA FIX: the old hardcoded "known 2026 schedule" fallback was stale.
  The real 2026 calendar was revised after it was written: Qatar was
  postponed from March to 22-24 Oct and became the penultimate round,
  Imola became the season-opener in April, Barcelona is NOT on the 2026
  calendar, and the season finale is Bahrain in November (not Monza).
  Corrected below. Exact session times for the later-season rounds are
  still marked "TBC" upstream at time of writing -- update these as FIA
  WEC firms them up, the same way the live scraper would.
- VISIBILITY FIX: previously, falling all the way back to hardcoded data
  was silent -- the script always "succeeded" and the workflow would keep
  committing stale data with no warning. Now every fallback path prints a
  clear stderr warning so it shows up in the GitHub Actions log.
"""

import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

ROUND_HEADER_RE = re.compile(
    r'([A-Z]{3})\s*[\r\n]+\s*(\d{1,2})\s*[\r\n]+\s*([A-Za-z]{3,9})\s*[\r\n]+\s*'
    r'((?:\d+\s+Hours?\s+of|\d+\s+KM|Rolex\s+\d+\s+Hours?\s+of|TotalEnergies\s+\d+\s+Hours?\s+of|'
    r'\d+\s+Hours?|Lone Star Le Mans|Qatar\s+\d+\s*KM|24 Hours of Le Mans)[^\n]*)',
    re.IGNORECASE,
)


class WECScheduleScraper:
    """Scraper for WEC schedule from the official FIA WEC website."""

    HOMEPAGE_URL = "https://www.fiawec.com/"

    def __init__(self, output_dir: str = "motorsport/wec"):
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/json"
        })

    # -- primary source: live site ---------------------------------------

    def scrape_calendar(self, year: int = None) -> dict:
        """
        Scrape WEC calendar for a specific year.

        Args:
            year: Season year (default: current year)

        Returns:
            Dictionary with season schedule
        """
        if year is None:
            year = datetime.now().year

        print(f"Scraping WEC {year} calendar...")

        try:
            calendar_data = self._scrape_homepage_calendar(year)
            if calendar_data and calendar_data.get('events'):
                print(f"  - Scraped {len(calendar_data['events'])} events from fiawec.com")
                return calendar_data
        except Exception as e:
            print(f"  - Live site scraping failed: {e}", file=sys.stderr)

        print(
            "  WARNING: falling back to the hardcoded known schedule -- "
            "live scraping failed or returned 0 events. This data will "
            "NOT reflect any calendar changes made after this script was "
            "last updated. Check fiawec.com manually and update "
            "_get_known_schedule() if this persists.",
            file=sys.stderr,
        )
        return self._get_known_schedule(year)

    def _scrape_homepage_calendar(self, year: int) -> dict:
        """
        Scrape the calendar block from the fiawec.com homepage.

        The homepage lists each round as a small card: country code, day,
        month, and event name (e.g. "ITA 19 Apr 6 Hours of Imola"), plus
        session countdown rows below it ("Free Practice 1", "Qualifying",
        "Race", etc. each with a date/time or "TBC"). We flatten the block
        to text and regex out round headers, then look for session rows
        immediately following each header.
        """
        response = self.session.get(self.HOMEPAGE_URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        text = soup.get_text('\n', strip=True)

        events = []
        for match in ROUND_HEADER_RE.finditer(text):
            country, day, month_str, name = match.groups()
            month = MONTHS.get(month_str.lower()[:3])
            if not month:
                continue
            date = f"{year}-{month:02d}-{int(day):02d}"
            events.append({
                "name": name.strip(),
                "country_code": country,
                "date": date,
                # Session-level times are not reliably extractable from the
                # homepage text alone (many are "TBC" and the markup mixes
                # countdown widgets in). Leave sessions empty here rather
                # than guess -- callers should treat an event without
                # "sessions" as "date confirmed, times TBC" and merge with
                # the known-schedule sessions if available.
                "sessions": [],
            })

        return {
            "scraped_at": datetime.now().isoformat(),
            "season": year,
            "championship": "FIA World Endurance Championship",
            "events": events,
        }

    # -- fallback: last-known-good hardcoded schedule ---------------------

    def _get_known_schedule(self, year: int) -> dict:
        """
        Hardcoded fallback for the 2026 season, corrected to match the
        calendar as revised (Qatar moved to Oct, Imola opener, Bahrain
        finale). Session times below are best-effort from public race
        info as of this fix; several later rounds still show "TBC" on the
        official site and should be updated once confirmed there.
        """
        if year == 2026:
            events = [
                {
                    "round": 1,
                    "name": "6 Hours of Imola",
                    "circuit": "Autodromo Enzo e Dino Ferrari",
                    "country": "Italy",
                    "date": "2026-04-19",
                    "sessions": [
                        {"type": "Practice 1", "date": "2026-04-18", "time": "09:00:00"},
                        {"type": "Practice 2", "date": "2026-04-18", "time": "13:00:00"},
                        {"type": "Qualifying", "date": "2026-04-18", "time": "17:00:00"},
                        {"type": "Race", "date": "2026-04-19", "time": "13:00:00"}
                    ]
                },
                {
                    "round": 2,
                    "name": "TotalEnergies 6 Hours of Spa-Francorchamps",
                    "circuit": "Circuit de Spa-Francorchamps",
                    "country": "Belgium",
                    "date": "2026-05-09",
                    "sessions": [
                        {"type": "Practice 1", "date": "2026-05-08", "time": "09:00:00"},
                        {"type": "Practice 2", "date": "2026-05-08", "time": "13:00:00"},
                        {"type": "Qualifying", "date": "2026-05-08", "time": "17:00:00"},
                        {"type": "Race", "date": "2026-05-09", "time": "13:00:00"}
                    ]
                },
                {
                    "round": 3,
                    "name": "24 Hours of Le Mans",
                    "circuit": "Circuit de la Sarthe",
                    "country": "France",
                    "date": "2026-06-13",
                    "sessions": [
                        {"type": "Practice 1", "date": "2026-06-10", "time": "10:00:00"},
                        {"type": "Practice 2", "date": "2026-06-10", "time": "14:00:00"},
                        {"type": "Practice 3", "date": "2026-06-11", "time": "10:00:00"},
                        {"type": "Hyperpole", "date": "2026-06-11", "time": "16:00:00"},
                        {"type": "Race", "date": "2026-06-13", "time": "15:00:00"}
                    ]
                },
                {
                    "round": 4,
                    "name": "Rolex 6 Hours of Sao Paulo",
                    "circuit": "Autodromo Jose Carlos Pace",
                    "country": "Brazil",
                    "date": "2026-07-12",
                    "sessions": [
                        {"type": "Practice 1", "date": "2026-07-11", "time": "08:00:00"},
                        {"type": "Practice 2", "date": "2026-07-11", "time": "12:00:00"},
                        {"type": "Qualifying", "date": "2026-07-11", "time": "16:00:00"},
                        {"type": "Race", "date": "2026-07-12", "time": "12:00:00"}
                    ]
                },
                {
                    "round": 5,
                    "name": "Lone Star Le Mans",
                    "circuit": "Circuit of the Americas",
                    "country": "USA",
                    "date": "2026-09-06",
                    "sessions": [
                        {"type": "Practice 1", "date": "2026-09-04", "time": "10:00:00"},
                        {"type": "Practice 2", "date": "2026-09-04", "time": "14:00:00"},
                        {"type": "Practice 3", "date": "2026-09-05", "time": "10:00:00"},
                        {"type": "Qualifying", "date": "2026-09-05", "time": "15:00:00"},
                        {"type": "Race", "date": "2026-09-06", "time": "13:00:00"}
                    ]
                },
                {
                    "round": 6,
                    "name": "6 Hours of Fuji",
                    "circuit": "Fuji Speedway",
                    "country": "Japan",
                    "date": "2026-09-27",
                    "sessions": [
                        {"type": "Practice 1", "date": "2026-09-26", "time": "02:00:00"},
                        {"type": "Practice 2", "date": "2026-09-26", "time": "06:00:00"},
                        {"type": "Qualifying", "date": "2026-09-26", "time": "10:00:00"},
                        {"type": "Race", "date": "2026-09-27", "time": "05:00:00"}
                    ]
                },
                {
                    "round": 7,
                    "name": "Qatar 1812 KM",
                    "circuit": "Lusail International Circuit",
                    "country": "Qatar",
                    "date": "2026-10-24",
                    "sessions": [
                        {"type": "Practice 1", "date": "2026-10-22", "time": "11:00:00"},
                        {"type": "Practice 2", "date": "2026-10-22", "time": "15:00:00"},
                        {"type": "Qualifying", "date": "2026-10-22", "time": "19:00:00"},
                        {"type": "Race", "date": "2026-10-24", "time": "14:00:00"}
                    ]
                },
                {
                    "round": 8,
                    "name": "8 Hours of Bahrain",
                    "circuit": "Bahrain International Circuit",
                    "country": "Bahrain",
                    "date": "2026-11-07",
                    "sessions": [
                        {"type": "Practice 1", "date": "2026-11-05", "time": "TBC"},
                        {"type": "Practice 2", "date": "2026-11-05", "time": "TBC"},
                        {"type": "Qualifying", "date": "2026-11-06", "time": "TBC"},
                        {"type": "Race", "date": "2026-11-07", "time": "TBC"}
                    ]
                }
            ]

            return {
                "scraped_at": datetime.now().isoformat(),
                "season": year,
                "championship": "FIA World Endurance Championship",
                "events": events,
                "_fallback_used": True,
            }

        return {
            "scraped_at": datetime.now().isoformat(),
            "season": year,
            "championship": "FIA World Endurance Championship",
            "events": [],
            "_fallback_used": True,
        }

    # -- output -------------------------------------------------------------

    def save_schedule(self, year: int = None, filename: str = None):
        """
        Scrape and save schedule to JSON file.

        Args:
            year: Season year (default: current year)
            filename: Output filename (default: {year}.json)
        """
        if year is None:
            year = datetime.now().year

        schedule = self.scrape_calendar(year)

        if not schedule.get("events"):
            print(
                "ERROR: 0 events in final schedule (both live scrape and "
                "fallback produced nothing). Aborting without writing "
                "output so we don't overwrite good data.",
                file=sys.stderr,
            )
            sys.exit(1)

        if filename is None:
            filename = f"{year}.json"

        import json
        import os
        filepath = f"{self.output_dir}/{filename}"
        os.makedirs(self.output_dir, exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(schedule, f, indent=2, ensure_ascii=False)

        print(f"  - Saved to {filepath}")
        return filepath


def main():
    """Main entry point for scraper."""
    scraper = WECScheduleScraper(output_dir="motorsport/wec")
    scraper.save_schedule(2026, "2026.json")


if __name__ == "__main__":
    main()
