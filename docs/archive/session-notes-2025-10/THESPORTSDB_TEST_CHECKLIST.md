# TheSportsDB V1 API Integration - Test Checklist

## 🧪 Testing Guide

The frontend is now running at **http://localhost:3000**

Please test the following pages and features to verify the TheSportsDB V1 API integration is working correctly.

---

## ✅ Test Checklist

### 1. **Home Page** (`http://localhost:3000/`)

**Expected Behavior:**
- [ ] Page loads without errors
- [ ] "Featured Predictions" section displays matches (if available today)
- [ ] "Today's Matches" section displays up to 6 matches
- [ ] Loading spinners appear while fetching data
- [ ] If no matches today, shows appropriate message
- [ ] All team logos display correctly
- [ ] Match cards show correct information (teams, date, time, league)

**What to Check:**
- Open browser console (F12) and check for:
  - ✅ No CORS errors
  - ✅ API calls to `thesportsdb.com/api/v1/json/<THESPORTSDB_KEY_REDACTED>/eventsday.php`
  - ✅ Successful responses (Status 200)
  - ✅ Console logs showing "Fetching today's fixtures from TheSportsDB..."

---

### 2. **Today's Predictions Page** (`http://localhost:3000/predictions/today`)

**Expected Behavior:**
- [ ] Page loads without errors
- [ ] Displays all today's matches
- [ ] League filter shows top 5 European leagues
- [ ] Can filter matches by league
- [ ] Can filter matches by confidence level
- [ ] Match cards display predictions with confidence levels
- [ ] Loading state shows while fetching data

**What to Check:**
- Open browser console and verify:
  - ✅ API call to `/eventsday.php?d=YYYY-MM-DD&s=Soccer`
  - ✅ API call to `/lookupleague.php` for each league
  - ✅ Console logs showing match count
  - ✅ No errors in console

**Test Filters:**
- [ ] Click on a league filter → Only matches from that league show
- [ ] Click on confidence filter → Only matches with that confidence show
- [ ] Clear filters → All matches show again

---

### 3. **Tomorrow's Predictions Page** (`http://localhost:3000/predictions/tomorrow`)

**Expected Behavior:**
- [ ] Page loads without errors
- [ ] Displays all tomorrow's matches
- [ ] League filter shows top 5 European leagues
- [ ] Can filter matches by league
- [ ] Can filter matches by confidence level
- [ ] Match cards display predictions with confidence levels
- [ ] Loading state shows while fetching data

**What to Check:**
- Open browser console and verify:
  - ✅ API call to `/eventsday.php?d=YYYY-MM-DD&s=Soccer` (tomorrow's date)
  - ✅ API call to `/lookupleague.php` for each league
  - ✅ Console logs showing match count
  - ✅ No errors in console

---

### 4. **Leagues Page** (`http://localhost:3000/leagues`)

**Expected Behavior:**
- [ ] Page loads without errors
- [ ] Displays 5 top European leagues:
  - English Premier League
  - Spanish La Liga
  - Italian Serie A
  - German Bundesliga
  - French Ligue 1
- [ ] Each league card shows:
  - League logo
  - League name
  - Country
  - Season (2024/25)
- [ ] Can click on a league to view details

**What to Check:**
- Open browser console and verify:
  - ✅ API calls to `/lookupleague.php?id=4328` (Premier League)
  - ✅ API calls to `/lookupleague.php?id=4335` (La Liga)
  - ✅ API calls to `/lookupleague.php?id=4332` (Serie A)
  - ✅ API calls to `/lookupleague.php?id=4331` (Bundesliga)
  - ✅ API calls to `/lookupleague.php?id=4334` (Ligue 1)
  - ✅ Console logs showing "5 leagues"
  - ✅ No errors in console

---

### 5. **League Detail Page - Premier League** (`http://localhost:3000/leagues/4328`)

**Expected Behavior:**
- [ ] Page loads without errors
- [ ] League header shows:
  - Premier League logo
  - League name
  - Country (England)
  - Season (2024-2025)
- [ ] **Standings Table** displays:
  - [ ] 20 teams (full Premier League table)
  - [ ] Columns: Position, Team, P, W, D, L, GF, GA, GD, Pts
  - [ ] Team logos display correctly
  - [ ] Data is sorted by position (1-20)
  - [ ] Points, wins, draws, losses are correct
- [ ] **Teams Section** displays:
  - [ ] All 20 Premier League teams
  - [ ] Team logos display correctly
  - [ ] Team names are correct
- [ ] **Upcoming Matches Section** displays:
  - [ ] Upcoming Premier League fixtures
  - [ ] Match cards with correct information
  - [ ] Dates and times are correct

**What to Check:**
- Open browser console and verify:
  - ✅ API call to `/lookupleague.php?id=4328`
  - ✅ API call to `/lookuptable.php?l=4328&s=2024-2025` (standings)
  - ✅ API call to `/search_all_teams.php?l=English_Premier_League` (teams)
  - ✅ API call to `/eventsseason.php?id=4328&s=2024-2025` (fixtures)
  - ✅ Console logs showing:
    - "Teams received: 20 teams"
    - "Standings received: 20 standings"
    - "Matches received: X matches"
  - ✅ No errors in console

**Critical Test:**
- [ ] Verify standings table shows **exactly 20 teams**
- [ ] Verify team at position 1 has the most points
- [ ] Verify goal difference calculations are correct
- [ ] Verify form data is displayed (if available)

---

## 🔍 Common Issues to Check

### **Issue 1: No Matches Displayed**
**Possible Causes:**
- No matches scheduled for today/tomorrow
- API returned empty response
- Date format issue

**How to Verify:**
- Check browser console for API response
- Look for `events: []` in the response
- Try testing on a different date (when matches are scheduled)

### **Issue 2: CORS Errors**
**Expected:** ✅ **NO CORS ERRORS** (V1 API works in browsers)

**If you see CORS errors:**
- ❌ Something is wrong with the API configuration
- Check if the API key is correct in `thesportsdb.service.ts`
- Verify the base URL is using V1 API path

### **Issue 3: Rate Limit Errors**
**Error Message:** "API rate limit exceeded (100 req/min)"

**Solution:**
- Wait 1 minute before retrying
- Premium account allows 100 requests/minute
- Check if multiple pages are making requests simultaneously

### **Issue 4: Missing Team Logos**
**Possible Causes:**
- Logo URL is incorrect
- Team logo not available in TheSportsDB

**Expected Behavior:**
- Fallback to default logo (`/teams/default.svg`)
- No broken image icons

### **Issue 5: Empty Standings Table**
**Possible Causes:**
- Season parameter is incorrect
- League ID is incorrect
- API returned empty response

**How to Verify:**
- Check browser console for API response
- Look for `table: []` in the response
- Verify season is "2024-2025"
- Verify league ID is "4328" for Premier League

---

## 📊 Expected API Responses

### **Today's Fixtures** (`/eventsday.php?d=2025-10-03&s=Soccer`)
```json
{
  "events": [
    {
      "idEvent": "441613",
      "strEvent": "Arsenal vs Chelsea",
      "strHomeTeam": "Arsenal",
      "strAwayTeam": "Chelsea",
      "dateEvent": "2025-10-03",
      "strTime": "15:00:00",
      "strLeague": "English Premier League",
      "idLeague": "4328",
      ...
    }
  ]
}
```

### **Premier League Standings** (`/lookuptable.php?l=4328&s=2024-2025`)
```json
{
  "table": [
    {
      "idStanding": "1",
      "intRank": "1",
      "idTeam": "133604",
      "strTeam": "Arsenal",
      "strTeamBadge": "https://...",
      "intPlayed": "38",
      "intWin": "28",
      "intDraw": "5",
      "intLoss": "5",
      "intGoalsFor": "88",
      "intGoalsAgainst": "43",
      "intGoalDifference": "45",
      "intPoints": "89",
      "strForm": "WWDWL",
      ...
    },
    // ... 19 more teams
  ]
}
```

---

## ✅ Success Criteria

The integration is successful if:

1. ✅ All 5 pages load without errors
2. ✅ No CORS errors in browser console
3. ✅ API calls to TheSportsDB V1 API are successful (Status 200)
4. ✅ Premier League standings show **20 teams**
5. ✅ Today's/Tomorrow's matches display correctly
6. ✅ Team logos display correctly (or fallback to default)
7. ✅ League filters work on predictions pages
8. ✅ Loading states appear while fetching data
9. ✅ Error messages display when API fails
10. ✅ No mock data is used (all data from API)

---

## 🐛 Debugging Tips

### **Enable Detailed Logging:**
Open browser console (F12) and look for:
- `TheSportsDBDataService:` logs
- `TheSportsDBService:` logs
- API request URLs
- API response data

### **Check Network Tab:**
1. Open browser DevTools (F12)
2. Go to "Network" tab
3. Filter by "Fetch/XHR"
4. Look for requests to `thesportsdb.com`
5. Check:
   - Request URL
   - Request Method (should be GET)
   - Status Code (should be 200)
   - Response data

### **Test Individual API Endpoints:**
You can test API endpoints directly in the browser:

1. **Get Premier League Standings:**
   ```
   https://www.thesportsdb.com/api/v1/json/<THESPORTSDB_KEY_REDACTED>/lookuptable.php?l=4328&s=2024-2025
   ```

2. **Get Today's Matches:**
   ```
   https://www.thesportsdb.com/api/v1/json/<THESPORTSDB_KEY_REDACTED>/eventsday.php?d=2025-10-03&s=Soccer
   ```

3. **Get Premier League Teams:**
   ```
   https://www.thesportsdb.com/api/v1/json/<THESPORTSDB_KEY_REDACTED>/search_all_teams.php?l=English_Premier_League
   ```

---

## 📝 Test Results Template

Copy this template and fill in your test results:

```
## Test Results - [Date: YYYY-MM-DD]

### Home Page
- [ ] PASS / [ ] FAIL
- Notes: _______________

### Today's Predictions Page
- [ ] PASS / [ ] FAIL
- Notes: _______________

### Tomorrow's Predictions Page
- [ ] PASS / [ ] FAIL
- Notes: _______________

### Leagues Page
- [ ] PASS / [ ] FAIL
- Notes: _______________

### League Detail Page (Premier League)
- [ ] PASS / [ ] FAIL
- Standings Count: ___ teams
- Teams Count: ___ teams
- Fixtures Count: ___ matches
- Notes: _______________

### Overall Integration
- [ ] PASS / [ ] FAIL
- Issues Found: _______________
- Recommendations: _______________
```

---

**Happy Testing! 🚀**

