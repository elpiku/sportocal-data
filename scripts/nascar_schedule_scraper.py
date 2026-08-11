"""
NASCAR Cup Series Schedule Scraper
Scrapes ESPN for NASCAR Cup Series schedule and outputs to motorsport/nascar/cup/2026.json
Matches the structure of F1, IndyCar, and WEC schedule scrapers.
"""

import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
import re


class NASCARScheduleScraper:
    """Scraper for NASCAR Cup Series schedule from ESPN."""
    
    ESPN_URL = "https://www.espn.com/racing/schedule"
    
    def __init__(self, output_dir: str = "motorsport/nascar/cup"):
        """
        Initialize NASCAR scraper.
        
        Args:
            output_dir: Directory to save scraped data (default: motorsport/nascar/cup)
        """
        self.output_dir = output_dir
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/json"
        })
    
    def scrape_schedule(self, year: int = None) -> dict:
        """
        Scrape NASCAR Cup Series schedule.
        
        Args:
            year: Season year (default: current year)
        
        Returns:
            Dictionary with season schedule
        """
        if year is None:
            year = datetime.now().year
        
        print(f"Scraping NASCAR Cup Series {year} schedule...")
        
        # Try ESPN scraping first
        try:
            schedule_data = self._scrape_espn(year)
            if schedule_data and schedule_data.get('events'):
                print(f"  - Scraped {len(schedule_data['events'])} races from ESPN")
                return schedule_data
        except Exception as e:
            print(f"  - ESPN scraping failed: {e}")
        
        # Fallback to known 2026 schedule
        return self._get_known_schedule(year)
    
    def _scrape_espn(self, year: int) -> dict:
        """Scrape NASCAR schedule from ESPN."""
        url = f"{self.ESPN_URL}/_/series/nascar"
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        events = []
        
        # ESPN uses table format for schedules
        # Find all table rows with race data
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')[1:]  # Skip header row
            
            for row in rows:
                event = self._parse_espn_row(row, year)
                if event:
                    events.append(event)
        
        # If table parsing didn't work, try alternative approach
        if not events:
            # Look for race cards or list items
            race_items = soup.find_all('div', class_=re.compile(r'schedule|race|event', re.I))
            for item in race_items:
                event = self._parse_race_item(item, year)
                if event:
                    events.append(event)
        
        return {
            "scraped_at": datetime.now().isoformat(),
            "season": year,
            "series": "NASCAR Cup Series",
            "total_races": len(events),
            "events": events
        }
    
    def _parse_espn_row(self, row, year: int) -> dict:
        """Parse ESPN table row into event."""
        event = {
            "round": None,
            "name": None,
            "track": None,
            "location": None,
            "date": None,
            "time": None,
            "tv": None,
            "sessions": []
        }
        
        try:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 3:
                return None
            
            # First cell usually has date/time
            date_cell = cells[0].get_text(strip=True)
            date_time = self._parse_date_time(date_cell, year)
            if date_time:
                event["date"] = date_time["date"]
                event["time"] = date_time["time"]
            
            # Second cell has race name and track
            race_cell = cells[1].get_text(strip=True)
            race_info = self._parse_race_info(race_cell)
            event["name"] = race_info.get("name")
            event["track"] = race_info.get("track")
            event["location"] = race_info.get("location")
            
            # Third cell has TV info
            if len(cells) > 2:
                event["tv"] = cells[2].get_text(strip=True)
            
            # Generate sessions (NASCAR standard format)
            if event["date"]:
                event["sessions"] = self._generate_nascar_sessions(event)
            
        except Exception as e:
            print(f"Error parsing row: {e}")
        
        return event if event["name"] else None
    
    def _parse_date_time(self, text: str, year: int) -> dict:
        """Parse date and time from ESPN format."""
        # ESPN format: "Sun, Feb 22 3:00 PM ET"
        pattern = r'([A-Za-z]+),\s*([A-Za-z]+\s+\d{1,2})\s+(\d{1,2}:\d{2}\s*[AP]M)\s*(ET|PT|CT|MT)?'
        match = re.search(pattern, text)
        
        if match:
            day_str = match.group(2)
            time_str = match.group(3)
            
            # Parse date
            date_obj = self._parse_date_string(day_str, year)
            
            return {
                "date": date_obj,
                "time": time_str
            }
        
        return None
    
    def _parse_date_string(self, date_str: str, year: int) -> str:
        """Convert date string to YYYY-MM-DD format."""
        months = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
            'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
            'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
            'dec': 12, 'december': 12
        }
        
        # Parse "Feb 22" or "February 22"
        pattern = r'([A-Za-z]+)\s+(\d{1,2})'
        match = re.search(pattern, date_str)
        
        if match:
            month_str = match.group(1).lower()
            day = int(match.group(2))
            month = months.get(month_str, 1)
            
            return f"{year}-{month:02d}-{day:02d}"
        
        return None
    
    def _parse_race_info(self, text: str) -> dict:
        """Parse race name and track from text."""
        info = {
            "name": None,
            "track": None,
            "location": None
        }
        
        # Remove "NASCAR Cup Series at" prefix
        text = re.sub(r'NASCAR Cup Series at\s+', '', text, flags=re.I)
        
        # Extract track name (usually after race name)
        # Pattern: "Race Name" Track Name
        if '**' in text:
            # Bold text is race name
            parts = text.split('**')
            if len(parts) >= 2:
                info["name"] = parts[1].strip()
                if len(parts) > 2:
                    info["track"] = parts[2].strip()
        else:
            info["name"] = text
        
        return info
    
    def _generate_nascar_sessions(self, event: dict) -> list:
        """Generate NASCAR session schedule based on race date."""
        sessions = []
        race_date = event.get("date")
        race_time = event.get("time", "3:00 PM")
        
        if not race_date:
            return sessions
        
        # Calculate session dates (typical NASCAR weekend format)
        from datetime import timedelta, datetime as dt
        
        try:
            race_dt = dt.strptime(race_date, "%Y-%m-%d")
            saturday = race_dt - timedelta(days=1)
            friday = race_dt - timedelta(days=2)
            
            # Friday: Practice
            sessions.append({
                "type": "Practice",
                "date": friday.strftime("%Y-%m-%d"),
                "time": "12:00 PM"
            })
            
            # Saturday: Qualifying
            sessions.append({
                "type": "Qualifying",
                "date": saturday.strftime("%Y-%m-%d"),
                "time": "10:00 AM"
            })
            
            # Sunday: Race
            sessions.append({
                "type": "Race",
                "date": race_date,
                "time": race_time
            })
            
        except Exception:
            # Fallback if date parsing fails
            pass
        
        return sessions
    
    def _parse_race_item(self, item, year: int) -> dict:
        """Parse race item from alternative HTML structure."""
        event = {
            "round": None,
            "name": None,
            "track": None,
            "location": None,
            "date": None,
            "time": None,
            "tv": None,
            "sessions": []
        }
        
        try:
            text = item.get_text(separator=' ', strip=True)
            
            # Extract date
            date_match = re.search(r'([A-Za-z]+)\.?\s+(\d{1,2})', text)
            if date_match:
                month_str = date_match.group(1)
                day = int(date_match.group(2))
                month = self._month_to_num(month_str)
                event["date"] = f"{year}-{month:02d}-{day:02d}"
            
            # Extract race name
            name_match = re.search(r'(Daytona 500|Coca-Cola 600|All-Star Race|Clash|Duel|Brickyard 400|Southern 500)', text, re.I)
            if name_match:
                event["name"] = name_match.group(1)
            
            # Extract track
            track_match = re.search(r'(Daytona|Atlanta|COTA|Phoenix|Las Vegas|Darlington|Martinsville|Bristol|Kansas|Talladega|Texas|Watkins Glen|Dover|Charlotte|Nashville|Michigan|Pocono|Sonoma|Chicagoland|New Hampshire|Iowa|Richmond|Gateway|Homestead)', text, re.I)
            if track_match:
                event["track"] = track_match.group(1)
            
            if event["name"] and event["date"]:
                event["sessions"] = self._generate_nascar_sessions(event)
            
        except Exception as e:
            print(f"Error parsing item: {e}")
        
        return event if event["name"] else None
    
    def _month_to_num(s
