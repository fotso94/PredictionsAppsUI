# Football Data Sources Evaluation (September 2026)

**Purpose:** find data sources that are better than the current API-Football + TheSportsDB setup for this product, affordable or free, and legally usable in a commercial subscription app.
**Method:** web research on 2026-09-17 against provider pricing/terms pages and independent comparisons, then scored against what this codebase actually needs. Prices are the providers' published list prices on the day of research; where a provider's own page could not be fetched, the figure is marked *third-party*.
**Scope note:** this is a research document; no code was changed. The recommendation feeds Phase 2 of `CLAUDE_PROJECT_STATUS_AND_NEXT_STEPS.md` (server-side data proxy).

---

> **Correction (2026-09-17, after review and Phase 1 implementation).**
> 1. **football-data.co.uk must not be used for training or commercial use.** Its terms restrict the data to personal, non-commercial use and prohibit use for machine-learning/AI training. Every recommendation below that relies on it for an in-house model (§2.2, §3 item 4, §4 baseline row, §5 step 4) is withdrawn. No internal prediction model is built in Phase 1.
> 2. **Providers adopted for Phase 1:** Live Score API (14-day trial, 1,500 requests/day, no pre-match odds) for fixtures/live/results/standings and **GameForecastAPI** (RapidAPI, free plan 10 requests/day, Pro $19/month for 5,000 requests; 1X2, BTTS, O/U 2.5 and, when published, O/U 3.5, exact score, reasoning) for model forecasts. API-Football and TheSportsDB are retained as fallbacks. See `README.md` ("Data providers") and Addendum D of the status report.
> 3. Missing from the comparison: GameForecastAPI (above) and BSD/Bzzoiro-style prediction feeds; neither was evaluated when this document was written.

## 1. What the application actually needs

Derived from `docs/requirements/COMPREHENSIVE_REQUIREMENTS_DOCUMENT.md` (FR-DATA-001/002, FR-PRED-001) and the current frontend/backend code:

| Need | Today | Gap |
|---|---|---|
| Fixtures, results, standings, team/league metadata and logos for the six covered competitions (Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Champions League) | API-Football v3 called **from the browser** (`frontend/src/services/football-data.service.ts`) | Must move behind the backend proxy with caching; any provider must be licensed for display in a commercial app |
| Live status and scores (docs: 1-minute refresh for live matches, 15-minute for upcoming) | API-Football (15 s refresh on paid plans) | Fine; needs caching to stay inside quotas |
| Baseline predictions for 1X2, BTTS, Over/Under (FR-PRED-001) | API-Football `/predictions` for the first 5 fixtures per page; **random numbers** for everything else (`api-mapper.service.ts`) | Need a real baseline for every fixture; ideally our own model, since "hybrid ML + expert" is the product |
| Odds shown on cards and detail pages | **Fabricated** (`generateMockOdds`) | Need a real odds feed, or stop showing odds |
| Historical results, odds and stats for training/backtesting the ML baseline | none | Need multi-season history (free sources exist) |
| Match results for settlement and accuracy tracking (FR-PRED-006) | none | Same feed as fixtures/results |
| Expert-facing context (form, H2H, injuries, xG) | none (placeholders) | Nice-to-have for Phase 4 |

Volume at MVP scale is small: six competitions produce roughly 40–70 fixtures per week. With a server-side cache (fixtures every 15 min, live matches every 60 s, standings hourly) the backend needs on the order of **1,000–3,000 provider requests per day**, most of them during live windows. Any plan above ~5,000 requests/day is sufficient; per-minute burst limits matter more than daily totals.

---

## 2. Providers compared

### 2.1 Summary table

| Provider | Entry price for commercial use | Free tier | Coverage | Live | Odds | Predictions | History for ML | Commercial licence | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **API-Football** (api-sports.io) — current | $19/mo Pro, 7,500 req/day; $29 Ultra 75k; $39 Mega 150k (*third-party; official page blocks fetch*) | 100 req/day, all endpoints | 1,200+ leagues | 15 s | yes | yes (6-algorithm model, no bookmaker input) | limited on free tier | display in apps allowed, resale prohibited | **Keep as backbone** behind the proxy |
| **football-data.org** | €49/mo Standard (30 comps, 60 req/min) is the first tier with commercial use; €12 livescores / €29 deep-data tiers exist for the 12 free comps | 12 comps, 10 req/min, delayed scores, **non-commercial + attribution** | 100 comps max | paid tiers real-time | €15 add-on (40 comps) | no | 10 seasons on "ML Pack" €29 | commercial on paid plans | Good European-only alternative; solo operator |
| **Sportmonks** | €29/mo Starter (any 5 leagues, 2,000 calls/entity/hour); €99 Growth (30 leagues) | 2 leagues only | 2,200+ | <15 s | €15 add-on | €15 add-on (1X2, BTTS, O/U 2.5/3.5, correct score, per-league model performance endpoint) | €29 one-time historical add-on; xG €24/mo | yes; 99.99% uptime published; SDKs | **Best upgrade path** when reliability/support matter |
| **5DollarFootballAPI** | $5/mo Pro (1,500+ comps, 10 req/min, Bet365 odds, 12 months history); $25 Ultra (40 req/min, 19 bookmakers, odds history to 2014) | Top-5 leagues, 60 req/hour, attribution required | 1,500+ | continuous | yes, incl. BTTS/O-U/AH/corners | no | 12 months (Pro) / full (Ultra) | explicitly allowed, caching allowed, attribution optional on paid | **Best value newcomer**; unproven track record |
| **Highlightly** | $9.49/mo Pro (7,500 req/day, 12 req/s); $20.99 Ultra 25k; $45.99 Mega 65k | 100 req/day | 950+ leagues | "1–5 min" | 100+ providers (paid) | no | n/a | not stated on site — must ask | Cheap, adds video highlights; slower live data; unknown licence |
| **TheSportsDB** — current fallback (code now removed) | $9/mo Patreon (v2, 2-min livescores, 100 req/min) | key `123`, 30 req/min, 1 result per search | broad, crowd-sourced | 2 min (paid) | no | no | n/a | commercial needs Patreon tier | Drop: accuracy concerns, tiny free limits |
| **APIfootball.com** (different vendor) | $21/mo European (60+ leagues, 1,000 calls/hour); $63 Premium adds predictions | 2 minor leagues, 180 calls/hour | 800+ | yes | +$15 odds | Premium only | n/a | **terms: personal, non-commercial use only** without written consent | Avoid unless a written commercial licence is obtained |
| **FootyStats** | £29.99/mo Hobby (40 leagues, 1,800 req/hour), £69.99 Serious (150 leagues) (*third-party*) | trial only | 200+ | yes | pre-match | yes (built for bettors: BTTS, O/U, HT/FT) | yes | not verified | Prediction-oriented alternative; page blocks fetch, verify terms |
| **TheStatsAPI** | $50/mo Starter (100k req/mo, 150 comps) | 7-day trial | 150–1,196 comps | yes | Bet365, Pinnacle, Betfair, Kambi | no | 10 years, xG included | permitted | Strong data (xG, odds) but young vendor and 2.5× the price |
| **GOAL API** | $0–$45/mo per its blog; free 1,000 req/day, all 1,019 leagues (*pricing page is JS-only; unverified*) | 1,000 req/day | 1,019 | WebSocket + webhooks | 3-hourly sync | limited leagues (not PL/UCL) | n/a | not verified | Interesting free tier; verify before relying on it |
| **OpenFootAPI** | $14/mo Developer (250k req/mo, live events, lineups, xG); $39 Pro "includes commercial use" | 5,000 req/mo, 120 comps | 120+ | SSE/webhooks | yes | no | 17 seasons | **aggregates ESPN and FotMob unofficial feeds** | Avoid for production: upstream provenance risk |
| **Live-Score-API** | €11/mo Starter (14,500 req/day); €26 Professional (50k) | 14-day trial | worldwide | yes | pre-match and live | no | 92 years | terms not reviewed | Cheap volume; verify data quality/terms |
| **Boggio Analytics Football Prediction API** (RapidAPI) | $14.99/mo (500 calls/day, 36 h window); $24.99 (3,000); $29.99 (12,000) | ~3 calls/day | 90+ countries | n/a | no | 1X2, BTTS, O/U 2.5/3.5, team O/U 0.5/1.5; 30-day accuracy monitoring | n/a | none stated | Cheap benchmark for our own model |
| **Betminer** (RapidAPI) | $99/mo unlimited | 5 req/day | 1,216 comps | n/a | no | 1X2, BTTS, O/U, xG, confidence; 1.6M-match history | yes | licensed for commercial use, no resale | Expensive for MVP; strong benchmark |
| **The Odds API** | Free 500 credits/mo; $30 for 20k; $59 for 100k | 500 credits/mo | 100+ sports; all top soccer leagues | live and pre-match | 100+ bookmakers; h2h, spreads, totals (BTTS/props for selected sports) | no | snapshots back to 2020 | display in apps allowed, resale prohibited, attribution optional | **Best odds feed** for the price |
| **Goalserve** | $150/mo per feed; $550 full soccer package | 30-day trial | 400+ leagues | 20 s | 20+ bookmakers, 50+ markets | no | yes | enterprise-style | Too expensive at this stage |
| **iSports API** | $299–$599/mo | 15-day trial | 2,000+ | yes | yes | no | 20 years | enterprise-style | Too expensive |
| **SportsDataIO / Sportradar / Stats Perform (Opta) / Genius Sports / Enetpulse** | ~$99–149 (SportsDataIO hobby, delayed) up to €1,300–4,990+/mo | trials | official/licensed | yes | licensed | some | yes | enterprise contracts | Not for an MVP |
| **SportScore** | free with a **dofollow "Powered by SportScore" link**; commercial by e-mail arrangement | ~10k req/day | multi-sport | yes | n/a | no | n/a | attribution-based | Only if the backlink is acceptable |

### 2.2 Free and open data (for ML training, backtesting and enrichment)

| Source | What | Cost / licence | Fit |
|---|---|---|---|
| **football-data.co.uk** | CSV per league and season since 1993/94: results, half-time, shots, corners, fouls, cards, and odds from Bet365, Pinnacle, William Hill, Betfair etc., including closing odds, Asian handicap and Over/Under 2.5 | free download, no key; no explicit licence text (widely used in research) | **Primary training/backtest set** for the ML baseline (1X2, BTTS, O/U) |
| **Club Elo** (clubelo.com) | Elo ratings for thousands of clubs since 1939, daily; fixtures with win/draw/loss probabilities; CSV API over plain HTTP (`api.clubelo.com`) | free; no terms published; site could not be fetched over HTTPS during research | Cheap, strong feature for a baseline model |
| **StatsBomb Open Data** | event-level data incl. xG for selected competitions (mostly internationals, women's, a few historical club seasons) | free; attribution with logo required; intended for research (check the Public Data User Agreement before any commercial use) | Research/prototyping only; coverage does not match our six leagues season-by-season |
| **openfootball** (GitHub) | fixtures/results text/JSON datasets | public domain (CC0) | Backfill of historical fixtures |
| **OpenLigaDB** | community JSON API, no key: Bundesliga, 2./3. Liga, DFB-Pokal, UCL/UEL, more | free, ODbL | Backup for German competitions only |
| **Understat, FBref, SofaScore, WhoScored, ESPN hidden API, FotMob** | xG, ratings, live scores via scraping/unofficial endpoints | free but **unofficial**; FBref lost its Opta licence in January 2026 and no longer updates advanced stats | Not for production: terms-of-service and stability risk |

---

## 3. Findings that change the picture

1. **The cheapest "alternative" is not a legal alternative.** APIfootball.com ($21/mo) restricts use to personal, non-commercial purposes without written consent. football-data.org's free tier is also non-commercial with mandatory attribution; its first commercial tier is €49/mo. API-Football, Sportmonks, 5DollarFootballAPI and The Odds API all allow display in commercial apps and forbid only raw resale.
2. **API-Football is not the problem; the way we use it is.** Its Pro plan ($19/mo, 7,500 req/day, 15 s live refresh, predictions endpoint included, commercial display allowed) is competitive in 2026. The real defects are architectural: calling it from the browser with an embedded key, no caching, and fabricating predictions and odds for fixtures without data. Every independent comparison still ranks it the broadest low-cost all-in-one option; its weaknesses (daily caps, patchy stats outside the top leagues, community-only support) do not bite at our scale.
3. **Odds should come from a dedicated odds feed, not a general API.** The Odds API (free 500 credits/month for development, $30/month for 20k) covers all six competitions from 100+ bookmakers with explicit permission to display odds commercially. 5DollarFootballAPI bundles Bet365 odds (1X2, BTTS, O/U, Asian handicap, corners, cards) at $5/month.
4. **Prediction APIs are benchmarks, not the product.** API-Football's predictions ignore bookmaker odds; Sportmonks' add-on (€15) publishes per-league model performance; Boggio ($14.99) and Betminer ($99) sell probabilities for 1X2/BTTS/O-U. For a product whose value is "our model plus experts", the baseline should be ours: implied probabilities from closing odds plus Elo plus form, trained and backtested on football-data.co.uk (free, 30+ seasons with odds). Third-party predictions are useful as comparison sources (the `API_FOOTBALL_BASELINE` source and priority system already exist in the schema).
5. **Newer entrants offer more for less but have no track record.** 5DollarFootballAPI ($5), Highlightly ($9.49), GOAL API (free 1,000 req/day claimed), OpenFootAPI ($14) all undercut the incumbents. OpenFootAPI openly aggregates ESPN and FotMob feeds, which are unofficial upstreams, so it inherits their legal and stability risk. The others do not publish provenance; treat them as secondary sources until they have run beside a proven feed for a full season.
6. **Sportmonks is the credible upgrade, not the starting point.** €29/month covers only 5 leagues (we need 6 competitions, so Growth at €99/month or Starter plus an extra league at €4/month), plus €15 for odds/predictions and €24 for xG. It buys published uptime, SDKs and human support, which matter after launch, not before.
7. **Football-data.org is the best fit if we ever want a European-only, curated feed**, but it is a one-person company, the free tier cannot be used commercially, and odds/stats are add-ons. Not better than API-Football for our needs.

---

## 4. Recommendation

**Keep API-Football as the fixtures/live/standings backbone, add a dedicated odds feed, build the baseline model on free historical data, and trial 5DollarFootballAPI as a low-cost second source.** Concretely:

| Role | Choice | Monthly cost | Why |
|---|---|---|---|
| Fixtures, live scores, standings, teams, logos | **API-Football Pro** (already subscribed), moved behind the backend proxy with Redis caching | $19 | Licensed for commercial display, 15 s live refresh, broad coverage, existing integration and ID mapping; quota is ample once cached |
| Odds (replace fabricated odds) | **The Odds API** Starter (free, 500 credits/month) during development; 20K plan at launch | $0 → $30 | Explicit commercial display rights, 100+ bookmakers, all six competitions, historical snapshots for backtesting |
| Baseline predictions (1X2, BTTS, O/U) | **In-house model**: implied probabilities from odds + Club Elo + recent form; trained/backtested on football-data.co.uk CSVs; API-Football `/predictions` kept as a comparison source | $0 | Owning the baseline is the product; free data is sufficient for a competent model |
| Second source / fallback and odds redundancy | **5DollarFootballAPI Pro** | $5 | Commercial use allowed, Bet365 odds incl. BTTS/O-U, 12 months history; run in parallel for a season before promoting it |
| Retire | TheSportsDB premium (unused code already deleted), the Vite proxy for production, browser-side keys | −$9 | No longer needed |

**Total at MVP: about $24/month in development and about $54/month at launch**, versus roughly $28/month today for a setup that fabricates most of what users see.

**Upgrade trigger:** when real users depend on live data (or when support/SLA becomes a requirement), move the backbone to **Sportmonks Growth (€99) + odds/predictions add-on (€15)**, optionally + xG (€24). Budget ≈ €140/month. TheStatsAPI ($50) is the alternative if xG matters earlier than reliability.

**Do not use:** APIfootball.com (non-commercial terms), OpenFootAPI (unofficial upstreams), any scraped or hidden API (ESPN, SofaScore, FotMob, FBref, Understat) in production, enterprise feeds (Goalserve, iSports, Sportradar, Opta) at this stage.

---

## 5. How to switch safely (fits Phase 2 of the status report)

1. **Provider adapter in the backend** (`backend/app/services/providers/`): one interface (`get_fixtures(date)`, `get_fixture(id)`, `get_standings(league, season)`, `get_teams(league, season)`, `search`) with an `APIFootballProvider` first, keys read from `backend/.env`. The frontend calls `/api/v1/matches|leagues|teams` only (the routers already exist commented-out in `backend/app/api/v1/api.py`).
2. **Redis caching with TTLs** matching the requirements: fixtures 15 min, live matches 60 s, standings 60 min, teams/leagues 24 h. Log provider request counts per day to size the plan.
3. **Odds adapter** (`TheOddsAPIProvider`) storing snapshots in `predictions.prediction_markets`; remove `generateMockOdds` from the frontend.
4. **Historical import job**: download football-data.co.uk CSVs for the six competitions (E0, SP1, I1, D1, F1 plus UCL from openfootball or API-Football history), load into `predictions.matches`/`match_results`; add a Club Elo daily import.
5. **Baseline model v0**: logistic/Poisson model on odds-implied probabilities, Elo difference and rolling form; backtest on 5 seasons; publish as source `ML_BASELINE` with `priority_level` 40, compare against `API_FOOTBALL_BASELINE`.
6. **Bake-off (2 weeks)**: run `FiveDollarFootballProvider` in shadow mode, diff fixtures/status/scores against API-Football for the six competitions, record latency and mismatches, then decide whether it becomes the fallback.
7. **Label or hide** anything still without real data (no more randomized predictions).

---

## 6. Sources consulted

- API-Football pricing (official page blocked automated fetch; tiers from [TheStatsAPI comparison](https://www.thestatsapi.com/blog/best-football-api), [Highlightly comparison](https://highlightly.net/blogs/best-football-apis-in-2026), [dev.to survey](https://dev.to/leomarsh886/a-survey-of-public-apis-for-building-a-football-live-score-site-in-2026-part-3-football-data-api-16hi)); terms via [api-sports.io/terms](https://api-sports.io/terms); predictions method via [api-football.com news](https://www.api-football.com/news/post/predictions); status page [api-sports.betteruptime.com](https://api-sports.betteruptime.com/)
- football-data.org: [pricing](https://www.football-data.org/pricing), [coverage](https://www.football-data.org/coverage), [about](https://www.football-data.org/about), [API policies](https://docs.football-data.org/general/v4/policies.html)
- Sportmonks: [plans & pricing](https://www.sportmonks.com/football-api/plans-pricing/), [rate limits](https://docs.sportmonks.com/football/api/rate-limit), [predictions](https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/predictions), [alternatives page (self-promotional)](https://www.sportmonks.com/football-api/alternatives/)
- TheSportsDB: [API](https://www.thesportsdb.com/api.php), [documentation](https://www.thesportsdb.com/documentation)
- 5DollarFootballAPI: [site](https://5dollarfootballapi.com/)
- Highlightly: [football API](https://highlightly.net/football-api/)
- APIfootball.com: [site](https://apifootball.com/), [terms of use](https://apifootball.com/terms_of_use/)
- FootyStats: [API](https://footystats.org/api) (blocked fetch; pricing via search summary)
- TheStatsAPI: [best football API](https://www.thestatsapi.com/blog/best-football-api), [free alternatives](https://www.thestatsapi.com/blog/free-football-api-alternatives), [about](https://www.thestatsapi.com/about)
- GOAL API: [blog comparison](https://goal-api.com/blog/api-football-alternatives), [pricing (JS-only)](https://goal-api.com/pricing)
- OpenFootAPI: [docs](https://openfootapi.com/docs)
- Live-Score-API: [prices](https://live-score-api.com/prices)
- Boggio Analytics: [FP API](https://boggio-analytics.com/fp-api/); Betminer: [site](https://betminer.co.uk/)
- The Odds API: [site](https://the-odds-api.com/), [terms](https://the-odds-api.com/terms-and-conditions.html)
- Goalserve: [soccer prices](https://www.goalserve.com/en/sport-data-feeds/soccer-api/prices); iSports: [pricing via search](https://sportsapi.com/api-directory/isportsapi/)
- Open data: [football-data.co.uk notes](https://www.football-data.co.uk/notes.txt), [StatsBomb open data](https://github.com/statsbomb/open-data), [OpenLigaDB](https://www.openligadb.de/), [Club Elo](http://clubelo.com/API), [curated list, June 2026](https://gist.github.com/hungson175/b804219579b3c3f6deb53dd0421d071a), [Liam Henshaw, where to find football data](https://www.liamhenshaw.com/writing/where-to-find-football-data)
- Unofficial APIs risk: [ESPN hidden API guide](https://scrapecreators.com/blog/espn-api-sports-data), [SportScore developers](https://sportscore.com/developers/)
