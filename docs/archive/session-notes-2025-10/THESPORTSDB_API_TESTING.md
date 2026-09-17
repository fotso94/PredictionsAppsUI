# TheSportsDB API Testing Documentation

## 🎯 Overview

This document outlines the testing of **TheSportsDB API** as a replacement for API-Football due to free plan limitations.

---

## 📋 Why Switch from API-Football?

### API-Football Issues:
- ❌ **Free plan limitation**: Only seasons 2021-2023 available
- ❌ **No current season data**: Cannot access 2024/25 season on free tier
- ❌ **Rate limits**: Limited requests per day
- ❌ **Requires API key**: Authentication required via RapidAPI

### TheSportsDB Advantages:
- ✅ **Completely FREE**: No API key required for basic tier (uses test key "3")
- ✅ **Current season data**: Access to current 2024/25 season
- ✅ **No authentication**: Simple HTTP GET requests
- ✅ **Rich data**: Team details, league info, events, standings
- ✅ **Good documentation**: Clear API endpoints
- ✅ **Artwork included**: Team badges, league logos, player photos

---

## 🔑 API Information

### Base URL:
```
https://www.thesportsdb.com/api/v1/json/{API_KEY}/
```

### API Keys:
- **Free Test Key**: `3` (for testing)
- **Free Production Key**: `1` (for production)
- **Premium Key**: Custom key ($9/month subscription)

### Documentation:
- **Main Docs**: https://www.thesportsdb.com/api.php
- **Free API Page**: https://www.thesportsdb.com/free_sports_api

---

## 📊 Available Endpoints (Free Tier)

### 1. **Leagues**

#### Get All Leagues
```
GET /all_leagues.php
```
Returns all leagues across all sports.

**Response:**
```json
{
  "leagues": [
    {
      "idLeague": "4328",
      "strLeague": "English Premier League",
      "strSport": "Soccer",
      "strLeagueAlternate": "Premier League, EPL"
    }
  ]
}
```

#### Lookup League Details
```
GET /lookupleague.php?id={league_id}
```
Returns detailed information about a specific league.

---

### 2. **Teams**

#### Search All Teams in a League
```
GET /search_all_teams.php?l={league_name}
```
Example: `/search_all_teams.php?l=English Premier League`

**Response:**
```json
{
  "teams": [
    {
      "idTeam": "133604",
      "strTeam": "Arsenal",
      "strTeamShort": "ARS",
      "intFormedYear": "1892",
      "strStadium": "Emirates Stadium",
      "intStadiumCapacity": "60338",
      "strBadge": "https://...",
      "strDescriptionEN": "Arsenal Football Club is...",
      "strWebsite": "www.arsenal.com"
    }
  ]
}
```

#### Search Team by Name
```
GET /searchteams.php?t={team_name}
```
Example: `/searchteams.php?t=Arsenal`

---

### 3. **Events (Matches/Fixtures)**

#### Get Next Events for a League
```
GET /eventsnextleague.php?id={league_id}
```
Example: `/eventsnextleague.php?id=4328` (Premier League)

**Response:**
```json
{
  "events": [
    {
      "idEvent": "123456",
      "strEvent": "Arsenal vs Chelsea",
      "strHomeTeam": "Arsenal",
      "strAwayTeam": "Chelsea",
      "intHomeScore": null,
      "intAwayScore": null,
      "dateEvent": "2025-01-10",
      "strTime": "15:00:00",
      "strSeason": "2024-2025",
      "intRound": "20"
    }
  ]
}
```

#### Get Past Events for a League
```
GET /eventspastleague.php?id={league_id}
```
Returns last 15 events for the league.

---

### 4. **League Table (Standings)**

```
GET /lookuptable.php?l={league_id}&s={season}
```
Example: `/lookuptable.php?l=4328&s=2024-2025`

**Response:**
```json
{
  "table": [
    {
      "strTeam": "Arsenal",
      "intPlayed": 20,
      "intWin": 15,
      "intDraw": 3,
      "intLoss": 2,
      "intPoints": 48
    }
  ]
}
```

---

## 🏆 Key League IDs

| League | TheSportsDB ID | API-Football ID |
|--------|----------------|-----------------|
| English Premier League | 4328 | 39 |
| Spanish La Liga | 4335 | 140 |
| Italian Serie A | 4332 | 135 |
| German Bundesliga | 4331 | 78 |
| French Ligue 1 | 4334 | 61 |

---

## 🧪 Test File: `test.html`

### What Was Changed:

1. **Replaced API-Football with TheSportsDB**
   - Changed base URL from `https://v3.football.api-sports.io` to `https://www.thesportsdb.com/api/v1/json/3/`
   - Removed RapidAPI authentication headers
   - Updated all endpoint calls

2. **New Test Functions:**
   - `getAllLeagues()` - Get all soccer leagues
   - `getTopLeagues()` - Get top 5 European leagues with details
   - `getPremierLeagueTeams()` - Get all Premier League teams
   - `getNextPremierLeagueEvents()` - Get upcoming Premier League matches
   - `getLast15PremierLeagueEvents()` - Get recent Premier League matches
   - `searchTeam()` - Search for Arsenal as example
   - `getLeagueTable()` - Get Premier League standings

3. **UI Improvements:**
   - Added info box explaining API details
   - Added warning messages for limited free tier features
   - Better error handling
   - Clearer button labels

---

## ✅ Testing Checklist

### Step 1: Open test.html
```bash
open test.html
# or
# Double-click test.html in your file browser
```

### Step 2: Test Each Endpoint

- [ ] **Get All Soccer Leagues** - Should return 20+ leagues
- [ ] **Get Top European Leagues** - Should return 5 leagues with badges
- [ ] **Get Premier League Teams** - Should return 20 teams
- [ ] **Get Next Premier League Events** - May be limited on free tier
- [ ] **Get Last 15 Premier League Events** - Should return recent matches
- [ ] **Search Team (Arsenal)** - Should return detailed team info
- [ ] **Get League Table** - May be limited on free tier

### Step 3: Check Console Logs

Open browser DevTools (F12) and check:
- ✅ No CORS errors
- ✅ HTTP 200 responses
- ✅ Valid JSON data
- ✅ No authentication errors

---

## ⚠️ Free Tier Limitations

### What's Available (FREE):
- ✅ All leagues list
- ✅ League details
- ✅ Team search and details
- ✅ Team rosters
- ✅ Past events (last 15)
- ✅ Next events (limited)
- ✅ Team badges and logos
- ✅ League standings (may be limited)

### What Requires Premium ($9/month):
- ❌ **2-minute livescores** - Real-time match updates
- ❌ **Video highlights** - Match highlights and clips
- ❌ **More API calls** - Higher rate limits
- ❌ **Additional endpoints** - More detailed statistics
- ❌ **Faster updates** - More frequent data refreshes

---

## 🔄 Data Structure Comparison

### API-Football vs TheSportsDB

#### League Data:
```javascript
// API-Football
{
  league: { id: 39, name: "Premier League", logo: "..." },
  country: { name: "England", flag: "..." }
}

// TheSportsDB
{
  idLeague: "4328",
  strLeague: "English Premier League",
  strBadge: "...",
  strCountry: "England"
}
```

#### Team Data:
```javascript
// API-Football
{
  team: { id: 42, name: "Arsenal", logo: "..." },
  venue: { name: "Emirates Stadium", capacity: 60338 }
}

// TheSportsDB
{
  idTeam: "133604",
  strTeam: "Arsenal",
  strBadge: "...",
  strStadium: "Emirates Stadium",
  intStadiumCapacity: "60338"
}
```

#### Match/Event Data:
```javascript
// API-Football
{
  fixture: { id: 123, date: "2025-01-10T15:00:00Z" },
  teams: { home: {...}, away: {...} },
  goals: { home: 2, away: 1 }
}

// TheSportsDB
{
  idEvent: "123456",
  dateEvent: "2025-01-10",
  strTime: "15:00:00",
  strHomeTeam: "Arsenal",
  strAwayTeam: "Chelsea",
  intHomeScore: "2",
  intAwayScore: "1"
}
```

---

## 📝 Next Steps

### If Testing is Successful:

1. **Create new service layer:**
   - `frontend/src/services/thesportsdb.service.ts` - Low-level HTTP client
   - `frontend/src/services/thesportsdb-mapper.service.ts` - Data transformation
   - Update `frontend/src/services/football-data.service.ts` - Use TheSportsDB instead

2. **Update type definitions:**
   - Map TheSportsDB data to existing `Match`, `League`, `Team` types
   - Ensure backward compatibility with existing components

3. **Test integration:**
   - Update one page at a time
   - Start with LeaguesPage
   - Then TodayPredictionsPage, TomorrowPredictionsPage
   - Finally LeagueDetailPage

4. **Handle limitations:**
   - Add fallback for missing data
   - Show appropriate messages for premium features
   - Consider caching strategy

---

## 🚀 Recommendation

**PROCEED WITH THESPORTSDB** if:
- ✅ All test endpoints return valid data
- ✅ Current season data is available
- ✅ Team and league information is complete
- ✅ Events/fixtures are accessible

**STICK WITH API-FOOTBALL** if:
- ❌ Critical data is missing
- ❌ Free tier is too limited
- ❌ Data quality is poor
- ❌ API is unreliable

---

## 📞 Support

- **TheSportsDB Forum**: https://www.thesportsdb.com/forum
- **Discord**: Available via website
- **Email**: [email protected]

---

**Last Updated**: 2025-01-03
**Status**: ⏳ TESTING IN PROGRESS

