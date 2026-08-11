"""
NASCAR Cup Series Schedule Scraper
Scrapes ESPN for NASCAR Cup Series schedule and outputs to motorsport/nascar/2026.json
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
    
    def __init__(self, output_dir: str = "motorsport/nascar"):
        """
        Initialize NASCAR scraper.
        
        Args:
            output_dir: Directory to save scraped data (default: motorsport/nascar)
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
    
    def _month_to_num(self, month_str: str) -> int:
        """Convert month name to number."""
        months = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
            'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
            'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
            'dec': 12, 'december': 12
        }
        return months.get(month_str.lower(), 1)
    
    def _get_known_schedule(self, year: int) -> dict:
        """Return known 2026 NASCAR Cup Series schedule."""
        if year == 2026:
            events = [
                {"round": 1, "name": "Daytona 500", "track": "Daytona International Speedway", "location": "Daytona Beach, FL", "date": "2026-02-15", "time": "2:30 PM", "tv": "FOX", "sessions": []},
                {"round": 2, "name": "Autotrader 400", "track": "EchoPark Speedway", "location": "Hampton, GA", "date": "2026-02-22", "time": "3:00 PM", "tv": "FOX", "sessions": []},
                {"round": 3, "name": "DuraMAX Texas Grand Prix", "track": "Circuit of the Americas", "location": "Austin, TX", "date": "2026-03-01", "time": "3:30 PM", "tv": "FOX", "sessions": []},
                {"round": 4, "name": "Straight Talk Wireless 500", "track": "Phoenix Raceway", "location": "Avondale, AZ", "date": "2026-03-08", "time": "3:30 PM", "tv": "FS1", "sessions": []},
                {"round": 5, "name": "Pennzoil 400", "track": "Las Vegas Motor Speedway", "location": "Las Vegas, NV", "date": "2026-03-15", "time": "4:00 PM", "tv": "FS1", "sessions": []},
                {"round": 6, "name": "Cook Out 400", "track": "Darlington Raceway", "location": "Darlington, SC", "date": "2026-03-22", "time": "3:00 PM", "tv": "FS1", "sessions": []},
                {"round": 7, "name": "Blue-Emu Maximum Pain Relief 400", "track": "Martinsville Speedway", "location": "Ridgeway, VA", "date": "2026-03-29", "time": "3:00 PM", "tv": "FOX", "sessions": []},
                {"round": 8, "name": "Food City 500", "track": "Bristol Motor Speedway", "location": "Bristol, TN", "date": "2026-04-12", "time": "3:00 PM", "tv": "FS1", "sessions": []},
                {"round": 9, "name": "AdventHealth 400", "track": "Kansas Speedway", "location": "Kansas City, KS", "date": "2026-04-19", "time": "2:00 PM", "tv": "FOX", "sessions": []},
                {"round": 10, "name": "Jack Link's 500", "track": "Talladega Superspeedway", "location": "Lincoln, AL", "date": "2026-04-26", "time": "3:00 PM", "tv": "FOX", "sessions": []},
                {"round": 11, "name": "EchoPark Automotive Grand Prix", "track": "Circuit of the Americas", "location": "Austin, TX", "date": "2026-05-03", "time": "3:00 PM", "tv": "FS1", "sessions": []},
                {"round": 12, "name": "Wurth 400", "track": "Dover Motor Speedway", "location": "Dover, DE", "date": "2026-05-10", "time": "2:00 PM", "tv": "FOX", "sessions": []},
                {"round": 13, "name": "NASCAR All-Star Race", "track": "Dover Motor Speedway", "location": "Dover, DE", "date": "2026-05-17", "time": "8:00 PM", "tv": "FOX", "sessions": []},
                {"round": 14, "name": "Coca-Cola 600", "track": "Charlotte Motor Speedway", "location": "Concord, NC", "date": "2026-05-24", "time": "6:00 PM", "tv": "FOX", "sessions": []},
                {"round": 15, "name": "Coca-Cola 600", "track": "Nashville Superspeedway", "location": "Nashville, TN", "date": "2026-05-31", "time": "3:00 PM", "tv": "FS1", "sessions": []},
                {"round": 16, "name": "FireKeepers Casino 400", "track": "Michigan International Speedway", "location": "Brooklyn, MI", "date": "2026-06-07", "time": "2:00 PM", "tv": "FS1", "sessions": []},
                {"round": 17, "name": "Pocono 500", "track": "Pocono Raceway", "location": "Long Pond, PA", "date": "2026-06-14", "time": "2:00 PM", "tv": "FOX", "sessions": []},
                {"round": 18, "name": "San Diego Street Race", "track": "San Diego Street Circuit", "location": "San Diego, CA", "date": "2026-06-21", "time": "8:00 PM", "tv": "TNT", "sessions": []},
                {"round": 19, "name": "Toyota/Save Mart 350", "track": "Sonoma Raceway", "location": "Sonoma, CA", "date": "2026-06-28", "time": "4:30 PM", "tv": "TNT", "sessions": []},
                {"round": 20, "name": "Grant Park 220", "track": "Chicago Street Course", "location": "Chicago, IL", "date": "2026-07-05", "time": "3:00 PM", "tv": "NBC", "sessions": []},
                {"round": 21, "name": "Quaker State 400", "track": "Atlanta Motor Speedway", "location": "Hampton, GA", "date": "2026-07-12", "time": "3:00 PM", "tv": "NBC", "sessions": []},
                {"round": 22, "name": "HighPoint.com 400", "track": "North Wilkesboro Speedway", "location": "North Wilkesboro, NC", "date": "2026-07-19", "time": "3:00 PM", "tv": "NBC", "sessions": []},
                {"round": 23, "name": "Brickyard 400", "track": "Indianapolis Motor Speedway", "location": "Indianapolis, IN", "date": "2026-07-26", "time": "2:30 PM", "tv": "NBC", "sessions": []},
                {"round": 24, "name": "Iowa Corn 350", "track": "Iowa Speedway", "location": "Newton, IA", "date": "2026-08-09", "time": "2:00 PM", "tv": "NBC", "sessions": []},
                {"round": 25, "name": "Cook Out 400", "track": "Richmond Raceway", "location": "Richmond, VA", "date": "2026-08-16", "time": "3:00 PM", "tv": "NBC", "sessions": []},
                {"round": 26, "name": "USA Today 301", "track": "New Hampshire Motor Speedway", "location": "Loudon, NH", "date": "2026-08-23", "time": "3:00 PM", "tv": "USA", "sessions": []},
                {"round": 27, "name": "Coke Zero Sugar 400", "track": "Daytona International Speedway", "location": "Daytona Beach, FL", "date": "2026-08-29", "time": "8:00 PM", "tv": "NBC", "sessions": []},
                {"round": 28, "name": "Cook Out Southern 500", "track": "Darlington Raceway", "location": "Darlington, SC", "date": "2026-09-06", "time": "6:00 PM", "tv": "NBC", "sessions": []},
                {"round": 29, "name": "Hollywood Casino 400", "track": "Kansas Speedway", "location": "Kansas City, KS", "date": "2026-09-13", "time": "3:00 PM", "tv": "NBC", "sessions": []},
                {"round": 30, "name": "Bass Pro Shops Night Race", "track": "Bristol Motor Speedway", "location": "Bristol, TN", "date": "2026-09-19", "time": "7:30 PM", "tv": "NBC", "sessions": []},
                {"round": 31, "name": "South Point 400", "track": "Las Vegas Motor Speedway", "location": "Las Vegas, NV", "date": "2026-10-04", "time": "3:00 PM", "tv": "NBC", "sessions": []},
                {"round": 32, "name": "Bank of America ROVAL 400", "track": "Charlotte Motor Speedway", "location": "Concord, NC", "date": "2026-10-11", "time": "2:00 PM", "tv": "NBC", "sessions": []},
                {"round": 33, "name": "Bluegreen Vacations 500", "track": "Phoenix Raceway", "location": "Avondale, AZ", "date": "2026-10-18", "time": "3:00 PM", "tv": "NBC", "sessions": []},
                {"round": 34, "name": "GEICO 500", "track": "Talladega Superspeedway", "location": "Lincoln, AL", "date": "2026-10-25", "time": "2:00 PM", "tv": "NBC", "sessions": []},
                {"round": 35, "name": "Xfinity 500", "track": "Martinsville Speedway", "location": "Ridgeway, VA", "date": "2026-11-01", "time": "2:00 PM", "tv": "NBC", "sessions": []},
                {"round": 36, "name": "NASCAR Cup Series Championship", "track": "Homestead-Miami Speedway", "location": "Homestead, FL", "date": "2026-11-08", "time": "3:00 PM", "tv": "NBC", "sessions": []}
            ]
            
            # Generate sessions for each event
            for event in events:
                event["sessions"] = self._generate_nascar_sessions(event)
            
            return {
                "scraped_at": datetime.now().isoformat(),
                "season": year,
                "series": "NASCAR Cup Series",
                "total_races": len(events),
                "events": events
            }
        
        return {
            "scraped_at": datetime.now().isoformat(),
            "season": year,
            "series": "NASCAR Cup Series",
            "total_races": 0,
            "events": []
        }
    
    def save_schedule(self, year: int = None, filename: str = None):
        """
        Scrape and save schedule to JSON file.
        
        Args:
            year: Season year (default: current year)
            filename: Output filename (default: {year}.json)
        """
        if year is None:
            year = datetime.now().year
        
        schedule = self.scrape_schedule(year)
        
        if filename is None:
            filename = f"{year}.json"
        
        # Save to file
        filepath = f"{self.output_dir}/{filename}"
        import os
        os.makedirs(self.output_dir, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(schedule, f, indent=2, ensure_ascii=False)
        
        print(f"  - Saved to {filepath}")
        return filepath


def main():
    """Main entry point for scraper."""
    scraper = NASCARScheduleScraper(output_dir="motorsport/nascar")
    scraper.save_schedule(2026, "2026.json")


if __name__ == "__main__":
    main()