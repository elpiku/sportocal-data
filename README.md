# sportocal-data

Central data repository for the [SportoCal](https://github.com/elpiku/sportocal) Android sports calendar application.

Automated scrapers run via GitHub Actions to fetch official fixtures and schedules across motorsport, football, basketball, american football, hockey, rugby, tennis, baseball, MMA, volleyball, and handball. Static JSON datasets are committed to this repository and published via GitHub Pages at `https://elpiku.github.io/sportocal-data/`.

---

## 📡 Primary Data Providers by Sport

| Sport | Primary Provider | Tier / Coverage | Endpoint / Package |
|---|---|---|---|
| **European Football (Top Tier)** | [football-data.org](https://www.football-data.org/) | Free tier (10 req/min) | Premier League, Champions League, Bundesliga, Serie A, La Liga, Ligue 1, Eredivisie, Primeira Liga, MLS, Championship |
| **Global Football / Secondary** | [API-Sports Football](https://api-sports.io/) | Free tier (100 req/day) | Brasileirão, Liga MX, Saudi Pro, Cup competitions, Women's leagues |
| **NBA (Basketball)** | [BALLDONTLIE](https://www.balldontlie.io/) | Free tier (30 req/min) | Full NBA regular season & playoffs schedule |
| **Global Basketball** | [API-Sports Basketball](https://api-sports.io/) | Free tier (100 req/day) | WNBA, FIBA, EuroLeague, NBL, College Basketball |
| **American Football** | [API-Sports NFL](https://api-sports.io/) | Free tier (100 req/day) | NFL, NCAA College Football |
| **Ice Hockey** | [API-Sports Hockey](https://api-sports.io/) | Free tier (100 req/day) | NHL, PWHL, IIHF World Championship |
| **Rugby** | [API-Sports Rugby](https://api-sports.io/) | Free tier (100 req/day) | Six Nations, Rugby Championship, Premiership, Champions Cup, Super Rugby, NRL |
| **Tennis** | [API-Sports Tennis](https://api-sports.io/) | Free tier (100 req/day) | ATP Tour, WTA Tour |
| **Baseball** | [API-Sports Baseball](https://api-sports.io/) | Free tier (100 req/day) | MLB, NPB, KBO, College Baseball |
| **MMA** | [API-Sports MMA](https://api-sports.io/) | Free tier (100 req/day) | UFC, PFL, Bellator |
| **Australian Football** | [API-Sports AFL](https://api-sports.io/) | Free tier (100 req/day) | Australian Football League (AFL) |
| **Volleyball** | [API-Sports Volleyball](https://api-sports.io/) | Free tier (100 req/day) | VNL, NCAA Volleyball |
| **Handball** | [API-Sports Handball](https://api-sports.io/) | Free tier (100 req/day) | EHF Champions League, Bundesliga, Liga ASOBAL |
| **Motorsport** | Official Timing & Series Sites | Free / Public | F1, F2, F3, FRECA, Italian F4, GB3, GB4, Super Formula, TCR Europe, IMSA, WEC, WRC, MotoGP, Moto2, Moto3, IndyCar, NASCAR |

---

## 🛡️ Quota Protection & Caching

All licensed provider requests pass through a shared caching and quota-tracking layer (`scripts/quota_cache.py`):

1. **TTLs:**
   - Fixtures and Schedules: **4 hours**
   - Standings: **8 hours**
   - Team rosters and Players: **24 hours**
   - Live data: **2 minutes** (never polled faster than every 60s)
2. **Quota Budgets:** Daily request counters track calls per provider and sport. When reaching the safety threshold (e.g. 90/100 for API-Sports), external calls halt and the pipeline serves cached data.
3. **Rate Limits & Backoff:** 429 responses and network errors trigger exponential backoff and polite sleep intervals (e.g. 6.5s between football-data.org calls; 2.1s between BALLDONTLIE calls).
4. **Graceful Fallbacks:** If an API key is missing or quota is exhausted, scrapers gracefully fall back to existing data without crashing.

---

## 🔑 Key Setup

API keys are read exclusively from environment variables or a gitignored `.env` file at the repository root. **Keys are never committed to version control.**

### 1. Local Development
Copy the `.env.example` template:
```bash
cp .env.example .env
```
Fill in your API keys in `.env`:
```ini
API_SPORTS_KEY=your_api_sports_key
FOOTBALL_DATA_KEY=your_football_data_key
BALLDONTLIE_KEY=your_balldontlie_key
```

### 2. GitHub Actions (CI)
Add the keys as Repository Secrets under **Settings > Secrets and variables > Actions**:
- `API_SPORTS_KEY`
- `FOOTBALL_DATA_KEY`
- `BALLDONTLIE_KEY`

---

## ⚖️ Licensing & Attribution

- **API-Sports**: Fixture data provided by [API-Sports](https://api-sports.io/).
- **football-data.org**: Football fixtures and standings powered by [football-data.org](https://www.football-data.org/).
- **BALLDONTLIE**: NBA schedules provided by [BALLDONTLIE](https://www.balldontlie.io/).
- **Visuals**: Team and league logos are not fetched or redistributed from third-party APIs; the app renders clean monogram badges to maintain license compliance.
