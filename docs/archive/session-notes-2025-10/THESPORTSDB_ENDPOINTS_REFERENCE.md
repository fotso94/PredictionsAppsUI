# TheSportsDB API Endpoints - Quick Reference

## 🔗 Base URL
```
https://www.thesportsdb.com/api/v1/json/{API_KEY}/
```

**Free API Keys:**
- Test: `3`
- Production: `1`

---

## 📋 Leagues

### Get All Leagues
```
GET /all_leagues.php
```
**Returns:** All leagues across all sports

**Example:**
```javascript
fetch('https://www.thesportsdb.com/api/v1/json/3/all_leagues.php')
  .then(r => r.json())
  .then(data => console.log(data.leagues))
```

### Lookup League by ID
```
GET /lookupleague.php?id={league_id}
```
**Parameters:**
- `id` - League ID (e.g., 4328 for Premier League)

**Example:**
```javascript
fetch('https://www.thesportsdb.com/api/v1/json/3/lookupleague.php?id=4328')
  .then(r => r.json())
  .then(data => console.log(data.leagues[0]))
```

### Search League by Name
```
GET /searchleagues.php?s={sport}&c={country}
```
**Parameters:**
- `s` - Sport name (e.g., "Soccer")
- `c` - Country name (e.g., "England")

---

## 👥 Teams

### Search All Teams in League
```
GET /search_all_teams.php?l={league_name}
```
**Parameters:**
- `l` - League name (e.g., "English Premier League")

**Example:**
```javascript
fetch('https://www.thesportsdb.com/api/v1/json/3/search_all_teams.php?l=English Premier League')
  .then(r => r.json())
  .then(data => console.log(data.teams))
```

### Search Team by Name
```
GET /searchteams.php?t={team_name}
```
**Parameters:**
- `t` - Team name (e.g., "Arsenal")

**Example:**
```javascript
fetch('https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t=Arsenal')
  .then(r => r.json())
  .then(data => console.log(data.teams[0]))
```

### Lookup Team by ID
```
GET /lookupteam.php?id={team_id}
```
**Parameters:**
- `id` - Team ID (e.g., 133604 for Arsenal)

---

## ⚽ Events (Matches/Fixtures)

### Get Next 5 Events for League
```
GET /eventsnextleague.php?id={league_id}
```
**Parameters:**
- `id` - League ID (e.g., 4328 for Premier League)

**Example:**
```javascript
fetch('https://www.thesportsdb.com/api/v1/json/3/eventsnextleague.php?id=4328')
  .then(r => r.json())
  .then(data => console.log(data.events))
```

### Get Last 15 Events for League
```
GET /eventspastleague.php?id={league_id}
```
**Parameters:**
- `id` - League ID

**Example:**
```javascript
fetch('https://www.thesportsdb.com/api/v1/json/3/eventspastleague.php?id=4328')
  .then(r => r.json())
  .then(data => console.log(data.events))
```

### Get Next 5 Events for Team
```
GET /eventsnext.php?id={team_id}
```
**Parameters:**
- `id` - Team ID (e.g., 133604 for Arsenal)

### Get Last 5 Events for Team
```
GET /eventslast.php?id={team_id}
```
**Parameters:**
- `id` - Team ID

### Search Events by Name
```
GET /searchevents.php?e={event_name}
```
**Parameters:**
- `e` - Event name (e.g., "Arsenal_vs_Chelsea")

### Lookup Event by ID
```
GET /lookupevent.php?id={event_id}
```
**Parameters:**
- `id` - Event ID

---

## 📊 League Tables (Standings)

### Get League Table
```
GET /lookuptable.php?l={league_id}&s={season}
```
**Parameters:**
- `l` - League ID (e.g., 4328)
- `s` - Season (e.g., "2024-2025")

**Example:**
```javascript
fetch('https://www.thesportsdb.com/api/v1/json/3/lookuptable.php?l=4328&s=2024-2025')
  .then(r => r.json())
  .then(data => console.log(data.table))
```

---

## 🏆 Key League IDs

| League | ID | Country |
|--------|-----|---------|
| English Premier League | 4328 | England |
| English Championship | 4329 | England |
| Spanish La Liga | 4335 | Spain |
| Italian Serie A | 4332 | Italy |
| German Bundesliga | 4331 | Germany |
| French Ligue 1 | 4334 | France |
| Scottish Premier League | 4330 | Scotland |
| Dutch Eredivisie | 4337 | Netherlands |
| Portuguese Primeira Liga | 4344 | Portugal |
| American MLS | 4346 | USA |
| Brazilian Serie A | 4351 | Brazil |
| Argentinian Primera Division | 4406 | Argentina |

---

## 📦 Response Structures

### League Object
```json
{
  "idLeague": "4328",
  "strLeague": "English Premier League",
  "strSport": "Soccer",
  "strLeagueAlternate": "Premier League, EPL",
  "strCountry": "England",
  "strBadge": "https://...",
  "strLogo": "https://...",
  "strDescriptionEN": "The Premier League is..."
}
```

### Team Object
```json
{
  "idTeam": "133604",
  "strTeam": "Arsenal",
  "strTeamShort": "ARS",
  "strAlternate": "Arsenal FC, AFC",
  "intFormedYear": "1892",
  "strSport": "Soccer",
  "strLeague": "English Premier League",
  "idLeague": "4328",
  "strStadium": "Emirates Stadium",
  "intStadiumCapacity": "60338",
  "strLocation": "Holloway, London, England",
  "strBadge": "https://...",
  "strLogo": "https://...",
  "strDescriptionEN": "Arsenal Football Club is...",
  "strWebsite": "www.arsenal.com",
  "strFacebook": "www.facebook.com/Arsenal",
  "strTwitter": "twitter.com/arsenal",
  "strInstagram": "instagram.com/arsenal"
}
```

### Event Object
```json
{
  "idEvent": "123456",
  "strEvent": "Arsenal vs Chelsea",
  "strEventAlternate": "Arsenal v Chelsea",
  "strFilename": "Arsenal_vs_Chelsea",
  "strSport": "Soccer",
  "idLeague": "4328",
  "strLeague": "English Premier League",
  "strSeason": "2024-2025",
  "strHomeTeam": "Arsenal",
  "strAwayTeam": "Chelsea",
  "intHomeScore": "2",
  "intAwayScore": "1",
  "intRound": "20",
  "dateEvent": "2025-01-10",
  "strTime": "15:00:00",
  "strTimeLocal": "15:00:00",
  "idHomeTeam": "133604",
  "idAwayTeam": "133613",
  "strResult": "Arsenal Win",
  "strVenue": "Emirates Stadium",
  "strCountry": "England",
  "strCity": "London",
  "strPoster": "https://...",
  "strThumb": "https://...",
  "strVideo": "https://..." // Premium only
}
```

### Table Entry Object
```json
{
  "name": "Arsenal",
  "teamid": "133604",
  "played": "20",
  "goalsfor": "45",
  "goalsagainst": "18",
  "goalsdifference": "27",
  "win": "15",
  "draw": "3",
  "loss": "2",
  "total": "48"
}
```

---

## 🎨 Artwork URLs

### Team Badge
```
team.strBadge
// Example: https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png
```

### Team Logo
```
team.strLogo
// Example: https://r2.thesportsdb.com/images/media/team/logo/q2mxlz1512644512.png
```

### League Badge
```
league.strBadge
// Example: https://r2.thesportsdb.com/images/media/league/badge/...
```

### Event Poster
```
event.strPoster
// Example: https://r2.thesportsdb.com/images/media/event/poster/...
```

---

## ⚠️ Free Tier Limitations

### Available on Free Tier:
- ✅ All leagues
- ✅ All teams
- ✅ Team details
- ✅ Next 5 events per league
- ✅ Last 15 events per league
- ✅ Next 5 events per team
- ✅ Last 5 events per team
- ✅ League tables (may be limited)
- ✅ All artwork (badges, logos)

### Premium Only ($9/month):
- ❌ 2-minute livescores
- ❌ Video highlights
- ❌ More events per request
- ❌ Player statistics
- ❌ Faster data updates

---

## 🔧 Usage Tips

### 1. URL Encoding
Always encode parameters:
```javascript
const leagueName = 'English Premier League';
const url = `${BASE_URL}/search_all_teams.php?l=${encodeURIComponent(leagueName)}`;
```

### 2. Error Handling
Check for null responses:
```javascript
const data = await fetch(url).then(r => r.json());
if (!data.teams) {
  console.error('No teams found');
  return;
}
```

### 3. Caching
Cache responses to reduce API calls:
```javascript
const cache = new Map();
const cacheKey = `teams_${leagueId}`;
if (cache.has(cacheKey)) {
  return cache.get(cacheKey);
}
const data = await fetchTeams(leagueId);
cache.set(cacheKey, data);
```

---

## 📚 Additional Resources

- **Main Documentation**: https://www.thesportsdb.com/api.php
- **Forum**: https://www.thesportsdb.com/forum
- **Discord**: Available via website
- **GitHub Examples**: Search for "thesportsdb" on GitHub

---

**Last Updated**: 2025-01-03

