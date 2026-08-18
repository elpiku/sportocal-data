# scripts/wec_schedule_scraper.py
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE_URL = "https://www.fiawec.com"
SEASON_YEAR = "2026"
OUTPUT_FILE = f"motorsport/wec/{SEASON_YEAR}.json"
MIN_EVENTS_THRESHOLD = 1


def fetch_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text


def discover_races():
    print(f"Discovering races from fiawec.com homepage nav...")
    html = fetch_html(BASE_URL)
    soup = BeautifulSoup(html, "html.parser")
    
    races = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/race/" in href or "/event/" in href or "/season-2026/" in href:
            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if full_url not in seen_urls:
                title = a.get_text(strip=True)
                if not title:
                    title = href.rstrip("/").split("/")[-1].replace("-", " ").title()
                seen_urls.add(full_url)
                races.append({"title": title, "url": full_url})

    # Fallback to hardcoded/known season events if nav discovery yields few/none
    if not races:
        nav_items = [
            ("Official Prologue - IMOLA", f"{BASE_URL}/en/race/result/4879"),
            ("6 Hours of Imola", f"{BASE_URL}/en/race/result/4880"),
            ("TotalEnergies 6 Hours of Spa-Francorchamps", f"{BASE_URL}/en/race/result/4881"),
            ("24 Hours of Le Mans", f"{BASE_URL}/en/race/result/4882"),
            ("ROLEX 6 Hours of São Paulo", f"{BASE_URL}/en/race/result/4883"),
            ("Lone Star Le Mans", f"{BASE_URL}/en/race/result/4884"),
            ("6 Hours of Fuji", f"{BASE_URL}/en/race/result/4885"),
            ("6 Hours of Barcelona", f"{BASE_URL}/en/race/result/4886"),
            ("6 Hours of Monza", f"{BASE_URL}/en/race/result/4887"),
        ]
        races = [{"title": name, "url": url} for name, url in nav_items]

    print(f"Found {len(races)} races for {SEASON_YEAR}")
    return races


def find_timetable_pdf(race_url):
    try:
        html = fetch_html(race_url)
        soup = BeautifulSoup(html, "html.parser")
        
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            if href.lower().endswith(".pdf") and ("timetable" in href.lower() or "timetable" in text or "schedule" in text):
                return href if href.startswith("http") else f"{BASE_URL}{href}"
    except Exception as e:
        print(f"    Error fetching race page {race_url}: {e}")
    return None


def parse_pdf_timetable(pdf_url):
    sessions = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(pdf_url, headers=headers, timeout=15)
        resp.raise_for_status()

        reader = PdfReader(io.BytesIO(resp.content))
        full_text = ""
        for page in reader.pages:
            full_text += (page.extract_text() or "") + "\n"

        # Regex heuristics for time extraction (HH:MM - HH:MM Session Name)
        pattern = re.compile(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\s+([A-Za-z0-9\s/]+)")
        for line in full_text.splitlines():
            match = pattern.search(line)
            if match:
                start_time, end_time, session_name = match.groups()
                sessions.append({
                    "session_name": session_name.strip(),
                    "start_time": start_time,
                    "end_time": end_time
                })
    except Exception as e:
        print(f"    Error parsing PDF {pdf_url}: {e}")
    return sessions


def main():
    races = discover_races()
    events_data = []

    for idx, race in enumerate(races, start=1):
        name = race["title"]
        url = race["url"]
        print(f"  [{idx}/{len(races)}] {name}: searching for Timetable...")

        pdf_url = find_timetable_pdf(url)
        if not pdf_url:
            print(f"  [{idx}/{len(races)}] {name}: no Timetable PDF link found, creating placeholder")
            events_data.append({
                "race_name": name,
                "url": url,
                "sessions": []
            })
            continue

        print(f"  [{idx}/{len(races)}] {name}: Found PDF at {pdf_url}")
        sessions = parse_pdf_timetable(pdf_url)
        events_data.append({
            "race_name": name,
            "url": url,
            "timetable_url": pdf_url,
            "sessions": sessions
        })

    if len(events_data) < MIN_EVENTS_THRESHOLD:
        print(f"ERROR: only parsed {len(events_data)} events (minimum {MIN_EVENTS_THRESHOLD}). Site structure may have changed. Aborting without writing output.")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "season": SEASON_YEAR,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "events": events_data
            },
            f,
            indent=2
        )
    print(f"Successfully scraped {len(events_data)} events to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
