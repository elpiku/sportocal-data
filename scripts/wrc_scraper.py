"""
WRC (World Rally Championship) Data Scraper
Scrapes official WRC API and outputs to motorsport/wrc/ folder.
Designed to run every 6 hours via GitHub Actions.
"""

import requests
import json
import os
from datetime import datetime
from pathlib import Path


class WRCScraper:
    """Scraper for WRC official API data."""
    
    BASE_URL = "https://api.wrc.com"
    RESULTS_API = "https://api.wrc.com/results-api"
    
    def __init__(self, output_dir: str = "motorsport/wrc"):
        """
        Initialize WRC scraper.
        
        Args:
            output_dir: Directory to save scraped data (default: motorsport/wrc)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        })
    
    def get_active_season(self) -> dict:
        """Get the current active WRC season calendar."""
        try:
            url = f"{self.BASE_URL}/contel-page/83388/calendar/active-season/"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching active season: {e}")
            return {}
    
    def get_season_calendar(self, year: int) -> dict:
        """Get WRC calendar for a specific year."""
        try:
            url = f"{self.BASE_URL}/contel-page/83388/calendar/{year}/"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching season {year} calendar: {e}")
            return {}
    
    def get_event_details(self, event_id: int) -> dict:
        """Get detailed information about a specific rally event."""
        try:
            url = f"{self.RESULTS_API}/rally-event/{event_id}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching event {event_id} details: {e}")
            return {}
    
    def get_event_itinerary(self, event_id: int) -> list:
        """Get rally itinerary (stages/legs) for an event."""
        try:
            url = f"{self.RESULTS_API}/rally-event/{event_id}/itinerary"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("itineraryLegs", [])
        except Exception as e:
            print(f"Error fetching event {event_id} itinerary: {e}")
            return []
    
    def get_stage_times(self, event_id: int) -> list:
        """Get stage times for all competitors in a rally."""
        try:
            url = f"{self.RESULTS_API}/rally-event/{event_id}/stage-times"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("stageTimes", [])
        except Exception as e:
            print(f"Error fetching event {event_id} stage times: {e}")
            return []
    
    def get_overall_standings(self, event_id: int) -> list:
        """Get overall standings/results for a rally event."""
        try:
            url = f"{self.RESULTS_API}/rally-event/{event_id}/overall-standings"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("standings", [])
        except Exception as e:
            print(f"Error fetching event {event_id} standings: {e}")
            return []
    
    def get_championship_standings(self, year: int, category: str = "drivers") -> list:
        """Get championship standings for a season."""
        try:
            url = f"{self.RESULTS_API}/championship/{year}/{category}/standings"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("standings", [])
        except Exception as e:
            print(f"Error fetching {year} {category} standings: {e}")
            return []
    
    def get_entry_list(self, event_id: int) -> list:
        """Get entry list (competitors) for a rally event."""
        try:
            url = f"{self.RESULTS_API}/rally-event/{event_id}/entries"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("entries", [])
        except Exception as e:
            print(f"Error fetching event {event_id} entry list: {e}")
            return []
    
    def scrape_schedule(self, year: int = None) -> dict:
        """
        Scrape WRC schedule/calendar.
        
        Args:
            year: Season year (default: current year)
        """
        if year is None:
            year = datetime.now().year
        
        print(f"Scraping WRC {year} schedule...")
        calendar = self.get_season_calendar(year)
        
        if not calendar:
            calendar = self.get_active_season()
        
        schedule_data = {
            "scraped_at": datetime.now().isoformat(),
            "season": year,
            "calendar": calendar
        }
        
        # Save schedule
        self._save_json(schedule_data, "schedule.json")
        print("  - Saved schedule.json")
        
        return schedule_data
    
    def scrape_event(self, event_id: int, event_name: str = None) -> dict:
        """
        Scrape all data for a single rally event.
        
        Args:
            event_id: WRC event ID
            event_name: Optional event name for filename
        """
        print(f"Scraping event {event_id}...")
        
        event_data = {
            "event_id": event_id,
            "scraped_at": datetime.now().isoformat(),
            "details": self.get_event_details(event_id),
            "itinerary": self.get_event_itinerary(event_id),
            "stage_times": self.get_stage_times(event_id),
            "standings": self.get_overall_standings(event_id),
            "entries": self.get_entry_list(event_id)
        }
        
        # Create filename from event name or ID
        if event_name:
            safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in event_name)
            filename = f"event_{safe_name.lower().replace(' ', '_')}.json"
        else:
            filename = f"event_{event_id}.json"
        
        self._save_json(event_data, filename)
        print(f"  - Saved {filename}")
        
        return event_data
    
    def scrape_championship(self, year: int = None) -> dict:
        """
        Scrape championship standings.
        
        Args:
            year: Championship year (default: current year)
        """
        if year is None:
            year = datetime.now().year
        
        print(f"Scraping WRC {year} championship standings...")
        
        standings_data = {
            "scraped_at": datetime.now().isoformat(),
            "season": year,
            "standings": {
                "drivers": self.get_championship_standings(year, "drivers"),
                "co_drivers": self.get_championship_standings(year, "co-drivers"),
                "manufacturers": self.get_championship_standings(year, "manufacturers")
            }
        }
        
        self._save_json(standings_data, "championship.json")
        print("  - Saved championship.json")
        
        return standings_data
    
    def scrape_upcoming_events(self) -> list:
        """
        Scrape upcoming events from calendar.
        
        Returns:
            List of upcoming event data
        """
        print("Scraping upcoming WRC events...")
        
        calendar = self.get_active_season()
        events = calendar.get("events", [])
        
        today = datetime.now().strftime("%Y-%m-%d")
        upcoming = []
        
        for event in events:
            start_date = event.get("startDate", "")
            if start_date >= today:
                event_id = event.get("id")
                if event_id:
                    event_data = self.scrape_event(event_id, event.get("name"))
                    upcoming.append(event_data)
        
        print(f"  - Scraped {len(upcoming)} upcoming events")
        return upcoming
    
    def _save_json(self, data: dict, filename: str):
        """Save data to JSON file in output directory."""
        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def run_full_scrape(self, year: int = None):
        """Run complete scrape: schedule, championship, and upcoming events."""
        print("=" * 60)
        print("WRC Full Data Scrape")
        print("=" * 60)
        
        self.scrape_schedule(year)
        self.scrape_championship(year)
        self.scrape_upcoming_events()
        
        print("=" * 60)
        print("Scrape complete!")
        print(f"Output directory: {self.output_dir}")
        print("=" * 60)


def main():
    """Main entry point for scraper."""
    # Determine output directory
    # When running from repo root: motorsport/wrc
    # When running from scripts folder: ../motorsport/wrc
    if Path("motorsport/wrc").exists():
        output_dir = "motorsport/wrc"
    elif Path("../motorsport/wrc").exists():
        output_dir = "../motorsport/wrc"
    else:
        output_dir = "motorsport/wrc"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    scraper = WRCScraper(output_dir=output_dir)
    scraper.run_full_scrape()


if __name__ == "__main__":
    main()
