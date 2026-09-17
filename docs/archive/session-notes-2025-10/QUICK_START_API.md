# 🚀 Quick Start - API Integration

## 🎯 Test the API Right Now

### Option 1: Standalone HTML Test
**File:** `test.html` (already open in your browser)
- Click buttons to test API endpoints
- Verify data loads with logos and information

### Option 2: React Test Page
**URL:** http://localhost:3000/api-test (already open in your browser)
- Click "Get Top Leagues" to test
- Click "Get Premier League Teams" to test
- Click "Get Today's Matches" to test

## 📝 Quick Integration Examples

### Get Today's Matches
```typescript
import { footballDataService } from '@/services/football-data.service';

const matches = await footballDataService.getTodayFixtures();
```

### Get Tomorrow's Matches
```typescript
const matches = await footballDataService.getTomorrowFixtures();
```

### Get Top European Leagues
```typescript
const leagues = await footballDataService.getTopLeagues();
```

### Get Teams in a League
```typescript
import { POPULAR_LEAGUES } from '@/services/football-data.service';

const teams = await footballDataService.getTeamsByLeague(
  POPULAR_LEAGUES.PREMIER_LEAGUE
);
```

### Get League Fixtures
```typescript
const fixtures = await footballDataService.getFixturesByLeague(
  POPULAR_LEAGUES.PREMIER_LEAGUE,
  undefined,
  { next: 10 } // Next 10 matches
);
```

### Get Head-to-Head
```typescript
const h2h = await footballDataService.getHeadToHead(
  homeTeamId,
  awayTeamId
);
```

## 🎨 Component Integration Pattern

```typescript
import { useState, useEffect } from 'react';
import { footballDataService } from '@/services/football-data.service';
import { Match } from '@/types';

function MyComponent() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const data = await footballDataService.getTodayFixtures();
        setMatches(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
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

## 🔑 Popular League IDs

```typescript
POPULAR_LEAGUES.PREMIER_LEAGUE    // 39
POPULAR_LEAGUES.LA_LIGA           // 140
POPULAR_LEAGUES.SERIE_A           // 135
POPULAR_LEAGUES.BUNDESLIGA        // 78
POPULAR_LEAGUES.LIGUE_1           // 61
POPULAR_LEAGUES.CHAMPIONS_LEAGUE  // 2
```

## ⚡ Key Features

✅ **Automatic Caching** - 5-minute cache reduces API calls
✅ **Error Handling** - Comprehensive error messages
✅ **Type Safety** - Full TypeScript support
✅ **Rate Limit Protection** - Built-in error handling
✅ **Mock Data Fallback** - Easy to switch between real/mock data

## 📊 API Status

Check remaining requests:
```typescript
import apiFootballService from '@/services/api-football.service';

const status = await apiFootballService.getStatus();
console.log('Requests remaining:', status.response.requests);
```

## 🐛 Quick Troubleshooting

**No data showing?**
- Check browser console for errors
- Verify API key is correct
- Check if fixtures exist for the date

**Rate limit error?**
- Check usage via status endpoint
- Wait for reset
- Verify caching is working

**CORS error?**
- Should not happen with API-Football
- Check browser console for details

## 📚 Full Documentation

- **Detailed Guide**: `API_INTEGRATION_GUIDE.md`
- **Summary**: `API_INTEGRATION_SUMMARY.md`
- **Service Files**: `frontend/src/services/`

## ✅ Next Steps

1. ✅ Test API using test pages
2. ⏳ Update `TodayPredictionsPage.tsx`
3. ⏳ Update `TomorrowPredictionsPage.tsx`
4. ⏳ Update `LeaguesPage.tsx`
5. ⏳ Update other components as needed

---

**Ready to integrate!** Start with the test pages to verify everything works.

