# API-Football Integration Guide

## 🎯 Overview

This guide explains how to integrate the API-Football API into the PredictionsAppsUI frontend to replace mock data with real live soccer data.

## 📋 What Was Fixed in test.html

### Issues Found:
1. **Wrong Base URL**: Was using `https://v3.football.api-sports.io` directly instead of RapidAPI endpoint
2. **Wrong Header Name**: Was using `x-api-key` instead of `x-rapidapi-key`
3. **Missing RapidAPI Host Header**: RapidAPI requires `x-rapidapi-host` header
4. **No Error Handling**: No visual feedback when API calls failed

### Fixes Applied:
```javascript
// BEFORE (Wrong)
const BASE_URL = 'https://v3.football.api-sports.io';
headers: {
    'x-api-key': API_KEY
}

// AFTER (Correct)
const BASE_URL = 'https://v3.football.api-sports.io';
const RAPIDAPI_HOST = 'v3.football.api-sports.io';
headers: {
    'x-rapidapi-key': API_KEY,
    'x-rapidapi-host': RAPIDAPI_HOST
}
```

## 🏗️ Architecture

### Service Layer Structure

```
frontend/src/services/
├── api-football.service.ts      # Low-level API client
├── api-mapper.service.ts        # Data transformation layer
└── football-data.service.ts     # High-level business logic
```

### Data Flow

```
API-Football API
      ↓
api-football.service.ts (Raw API calls)
      ↓
api-mapper.service.ts (Transform to frontend types)
      ↓
football-data.service.ts (Business logic + caching)
      ↓
React Components
```

## 🔧 Services Created

### 1. api-football.service.ts
**Purpose**: Low-level HTTP client for API-Football API

**Features**:
- Axios-based HTTP client with proper headers
- Error handling and retry logic
- Type-safe API responses
- All major endpoints covered

**Key Methods**:
```typescript
- getStatus()                    // Check API status
- getLeagues(params)             // Get leagues
- getTeams(params)               // Get teams
- getFixtures(params)            // Get matches/fixtures
- getTeamStatistics(params)      // Get team stats
- getPredictions(fixtureId)      // Get match predictions
- getHeadToHead(params)          // Get H2H data
- getStandings(params)           // Get league standings
```

### 2. api-mapper.service.ts
**Purpose**: Transform API-Football data to frontend types

**Features**:
- Maps API responses to TypeScript interfaces
- Handles missing/optional data gracefully
- Generates default values when needed
- Type-safe transformations

**Key Functions**:
```typescript
- mapLeague(apiLeague)           // APILeague → League
- mapTeam(apiTeam, stats?)       // APITeam → Team
- mapFixture(...)                // APIFixture → Match
- mapPredictions(apiPrediction)  // APIPrediction → MatchPredictions
- mapHeadToHead(fixtures)        // APIFixture[] → HeadToHead
- mapMatchStatus(apiStatus)      // String → MatchStatus
```

### 3. football-data.service.ts
**Purpose**: High-level service with business logic

**Features**:
- Caching layer (5-minute cache)
- Combines multiple API calls
- Simplified interface for components
- Popular league constants

**Key Methods**:
```typescript
- getLeagues(params?)            // Get all/filtered leagues
- getTopLeagues()                // Get top 5 European leagues
- getTeamsByLeague(leagueId)     // Get teams in a league
- getFixturesByDate(date)        // Get matches on a date
- getTodayFixtures()             // Get today's matches
- getTomorrowFixtures()          // Get tomorrow's matches
- getFixturesByLeague(leagueId)  // Get league fixtures
- getHeadToHead(team1, team2)    // Get H2H data
- clearCache()                   // Clear all caches
```

## 🚀 How to Use in Components

### Example 1: Get Today's Matches

```typescript
import { footballDataService } from '@/services/football-data.service';
import { Match } from '@/types';

function TodayMatches() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchMatches() {
      try {
        setLoading(true);
        const data = await footballDataService.getTodayFixtures();
        setMatches(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch matches');
      } finally {
        setLoading(false);
      }
    }

    fetchMatches();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      {matches.map(match => (
        <div key={match.id}>
          {match.homeTeam.name} vs {match.awayTeam.name}
        </div>
      ))}
    </div>
  );
}
```

### Example 2: Get Top Leagues

```typescript
import { footballDataService } from '@/services/football-data.service';
import { League } from '@/types';

function TopLeagues() {
  const [leagues, setLeagues] = useState<League[]>([]);

  useEffect(() => {
    async function fetchLeagues() {
      try {
        const data = await footballDataService.getTopLeagues();
        setLeagues(data);
      } catch (err) {
        console.error('Error fetching leagues:', err);
      }
    }

    fetchLeagues();
  }, []);

  return (
    <div>
      {leagues.map(league => (
        <div key={league.id}>
          <img src={league.logo} alt={league.name} />
          <h3>{league.name}</h3>
          <p>{league.country}</p>
        </div>
      ))}
    </div>
  );
}
```

### Example 3: Get Teams in Premier League

```typescript
import { footballDataService, POPULAR_LEAGUES } from '@/services/football-data.service';

async function getPremierLeagueTeams() {
  const teams = await footballDataService.getTeamsByLeague(
    POPULAR_LEAGUES.PREMIER_LEAGUE
  );
  return teams;
}
```

## 🔑 API Key Management

### Current Setup (Development)
The API key is currently hardcoded in `api-football.service.ts`:

```typescript
const API_CONFIG = {
  rapidApiKey: '<API_FOOTBALL_KEY_REDACTED>',
  // ...
};
```

### Recommended: Environment Variables

1. Create `.env` file in frontend directory:
```bash
VITE_RAPIDAPI_KEY=<API_FOOTBALL_KEY_REDACTED>
VITE_RAPIDAPI_HOST=v3.football.api-sports.io
```

2. Update `api-football.service.ts`:
```typescript
const API_CONFIG = {
  baseURL: 'https://v3.football.api-sports.io',
  rapidApiKey: import.meta.env.VITE_RAPIDAPI_KEY,
  rapidApiHost: import.meta.env.VITE_RAPIDAPI_HOST,
  timeout: 10000,
};
```

3. Add `.env` to `.gitignore`:
```bash
echo ".env" >> .gitignore
```

## 📊 Popular League IDs

```typescript
export const POPULAR_LEAGUES = {
  PREMIER_LEAGUE: 39,      // England
  LA_LIGA: 140,            // Spain
  SERIE_A: 135,            // Italy
  BUNDESLIGA: 78,          // Germany
  LIGUE_1: 61,             // France
  CHAMPIONS_LEAGUE: 2,     // UEFA
  EUROPA_LEAGUE: 3,        // UEFA
  WORLD_CUP: 1,            // FIFA
};
```

## 🎨 Migration Strategy

### Phase 1: Test API Connection ✅
- [x] Fix test.html
- [x] Verify API credentials
- [x] Test basic endpoints

### Phase 2: Create Service Layer ✅
- [x] Create api-football.service.ts
- [x] Create api-mapper.service.ts
- [x] Create football-data.service.ts

### Phase 3: Update Components (Next Steps)
1. Update `TodayPredictionsPage.tsx` to use `getTodayFixtures()`
2. Update `TomorrowPredictionsPage.tsx` to use `getTomorrowFixtures()`
3. Update `LeaguesPage.tsx` to use `getTopLeagues()`
4. Update `LeagueDetailPage.tsx` to use `getTeamsByLeague()` and `getFixturesByLeague()`
5. Update `MatchDetailPage.tsx` to use `getHeadToHead()`

### Phase 4: Remove Mock Data
1. Keep `mockData.ts` as fallback
2. Add feature flag to switch between mock and real data
3. Gradually phase out mock data

## ⚠️ Important Notes

### API Rate Limits
- **Free Tier**: 100 requests/day
- **Basic Tier**: 1,000 requests/day
- **Pro Tier**: 10,000 requests/day

**Mitigation Strategies**:
1. ✅ Caching implemented (5-minute cache)
2. ✅ Batch requests where possible
3. Consider implementing request queue
4. Monitor usage via `/status` endpoint

### Data Availability
- **Fixtures**: Available for current season
- **Predictions**: Only available 24-48 hours before match
- **Odds**: Requires separate subscription
- **Live Scores**: Real-time updates available

### Error Handling
All services include comprehensive error handling:
- Network errors
- API rate limits (429)
- Authentication errors (401/403)
- Invalid parameters
- Missing data

## 🧪 Testing the Integration

### 1. Test HTML File
Open `test.html` in your browser and click the buttons:
- ✅ Test API Status
- ✅ Get Leagues
- ✅ Get Top European Leagues
- ✅ Get Premier League Teams
- ✅ Get Today's Fixtures

### 2. Browser Console Testing
```javascript
// In browser console (with React app running)
import { footballDataService } from './services/football-data.service';

// Test getting today's fixtures
const matches = await footballDataService.getTodayFixtures();
console.log(matches);

// Test getting top leagues
const leagues = await footballDataService.getTopLeagues();
console.log(leagues);
```

### 3. Component Testing
Create a test component to verify integration:
```typescript
// src/pages/APITestPage.tsx
import { footballDataService } from '@/services/football-data.service';

export function APITestPage() {
  const [data, setData] = useState(null);

  const testAPI = async () => {
    const matches = await footballDataService.getTodayFixtures();
    setData(matches);
  };

  return (
    <div>
      <button onClick={testAPI}>Test API</button>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
```

## 📚 Next Steps

1. **Test the API**: Open `test.html` and verify all buttons work
2. **Review Services**: Check the three service files created
3. **Update Components**: Start integrating into React components
4. **Environment Variables**: Move API key to `.env` file
5. **Error Boundaries**: Add React error boundaries for API failures
6. **Loading States**: Implement proper loading UI
7. **Monitoring**: Track API usage and errors

## 🆘 Troubleshooting

### Issue: "API authentication failed"
- Check API key is correct
- Verify headers include both `x-rapidapi-key` and `x-rapidapi-host`

### Issue: "Rate limit exceeded"
- Check `/status` endpoint for current usage
- Implement request throttling
- Consider upgrading API plan

### Issue: "No data returned"
- Check if fixtures exist for the requested date
- Verify league/team IDs are correct
- Check API documentation for parameter requirements

### Issue: CORS errors
- API-Football should handle CORS
- If issues persist, may need backend proxy

## 📞 Support

- **API Documentation**: https://www.api-football.com/documentation-v3
- **RapidAPI Dashboard**: https://rapidapi.com/api-sports/api/api-football
- **Support**: Check API status page for outages

