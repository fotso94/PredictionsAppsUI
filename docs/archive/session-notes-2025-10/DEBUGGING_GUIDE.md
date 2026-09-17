# 🔍 Debugging Guide - API Integration Issues

## Issue Report

**Problem:** LeaguesPage (`/leagues`) not displaying data
**Status:** Under Investigation
**Date:** 2025-01-03

---

## Changes Made for Debugging

### 1. Enhanced LeaguesPage Logging

**File:** `frontend/src/pages/LeaguesPage.tsx`

**Added:**
- Detailed console logging at each step
- Check for empty array from API
- Automatic fallback to mock data if API returns empty
- New "No leagues available" state with retry button
- Logs service object to verify it's loaded correctly

**Console Logs to Expect:**
```
LeaguesPage: Fetching top leagues...
LeaguesPage: footballDataService = [object]
LeaguesPage: Leagues received: X leagues
LeaguesPage: Leagues data: [array of league objects]
LeaguesPage: Loading complete. Leagues count: X
```

### 2. Created Debug API Page

**File:** `frontend/src/pages/DebugAPIPage.tsx`
**Route:** `/debug-api`

**Purpose:**
- Test all API service methods independently
- Display detailed output and errors
- Verify each method works correctly
- Compare results with actual pages

**How to Use:**
1. Navigate to http://localhost:3000/debug-api
2. Click "Test getTopLeagues()" button
3. Check the output panel for results
4. Check browser console for detailed logs
5. Test other methods as needed

---

## Debugging Steps

### Step 1: Check Browser Console

1. Navigate to http://localhost:3000/leagues
2. Open DevTools (F12)
3. Go to Console tab
4. Look for logs starting with "LeaguesPage:"

**Expected Logs:**
```
LeaguesPage: Fetching top leagues...
LeaguesPage: footballDataService = FootballDataService {...}
LeaguesPage: Leagues received: 5 leagues
LeaguesPage: Leagues data: [{...}, {...}, ...]
LeaguesPage: Loading complete. Leagues count: 5
```

**If You See:**
- "Leagues received: 0 leagues" → API returned empty array
- "Error fetching leagues:" → API call failed
- "Falling back to mock data" → Using mock data fallback
- No logs at all → Component not mounting or useEffect not running

### Step 2: Check Network Tab

1. Open DevTools (F12)
2. Go to Network tab
3. Filter by "Fetch/XHR"
4. Refresh the page
5. Look for requests to `v3.football.api-sports.io`

**Expected Requests:**
- 5 requests to `/leagues?id=X&season=2024`
  - One for each league: 39, 140, 135, 78, 61

**Check:**
- Status codes (should be 200)
- Response data (should have league info)
- Request headers (should have API key)
- Response time (should be < 2 seconds each)

### Step 3: Use Debug API Page

1. Navigate to http://localhost:3000/debug-api
2. Click "Test getTopLeagues()"
3. Check output panel
4. Check browser console

**Expected Output:**
```
=== Testing getTopLeagues() ===
Calling footballDataService.getTopLeagues()...
✅ Success! Received 5 leagues

League 1:
  ID: 39
  Name: Premier League
  Country: England
  Logo: https://...
  Season: 2024/25

[... 4 more leagues ...]
```

**If Error:**
- Check error message
- Check stack trace
- Compare with working pages (Today/Tomorrow Predictions)

### Step 4: Compare with Working Pages

**Pages that ARE working:**
- `/predictions/today` - Uses `getTopLeagues()` ✅
- `/predictions/tomorrow` - Uses `getTopLeagues()` ✅

**Pages to test:**
- `/leagues` - Uses `getTopLeagues()` ❓
- `/league/39` - Uses `getTeamsByLeague()` and `getFixturesByLeague()` ❓

**Action:**
1. Navigate to `/predictions/today`
2. Open console
3. Look for "Leagues received: X leagues"
4. If this works but `/leagues` doesn't, it's a page-specific issue

### Step 5: Check for TypeScript Errors

Run in terminal:
```bash
cd frontend
npm run build
```

Look for any TypeScript compilation errors.

---

## Possible Root Causes

### 1. Empty API Response
**Symptom:** API returns `[]` instead of league data
**Cause:** Season parameter issue (2024 vs 2025)
**Solution:** Already fixed - hardcoded to 2024

### 2. Caching Issue
**Symptom:** First load works, subsequent loads fail
**Cause:** Cached empty result
**Solution:** Clear cache or wait 5 minutes

### 3. Component State Issue
**Symptom:** Data fetched but not displayed
**Cause:** State not updating correctly
**Solution:** Check React DevTools for state values

### 4. Rendering Condition Issue
**Symptom:** Data exists but grid not showing
**Cause:** Conditional rendering logic
**Solution:** Check if `leagues.length === 0` when it shouldn't be

### 5. Import Issue
**Symptom:** Service not found or undefined
**Cause:** Import path or export issue
**Solution:** Verify import statement and service export

---

## Quick Fixes to Try

### Fix 1: Clear Browser Cache
```
1. Open DevTools (F12)
2. Right-click refresh button
3. Select "Empty Cache and Hard Reload"
```

### Fix 2: Clear Service Cache
Add this to LeaguesPage temporarily:
```typescript
useEffect(() => {
  // Clear cache before fetching
  footballDataService.clearCache()
  
  async function fetchLeagues() {
    // ... rest of code
  }
  fetchLeagues()
}, [])
```

### Fix 3: Force Mock Data (Temporary)
To verify rendering works:
```typescript
useEffect(() => {
  // Skip API, use mock data
  setLeagues(mockLeagues)
  setLoading(false)
}, [])
```

If this shows leagues, the issue is with the API call, not rendering.

### Fix 4: Add Timeout
Sometimes the API is slow:
```typescript
const data = await Promise.race([
  footballDataService.getTopLeagues(),
  new Promise((_, reject) => 
    setTimeout(() => reject(new Error('Timeout')), 10000)
  )
])
```

---

## Testing Checklist

### LeaguesPage (`/leagues`)
- [ ] Page loads without errors
- [ ] Loading spinner appears briefly
- [ ] Console shows "Fetching top leagues..."
- [ ] Console shows "Leagues received: X leagues"
- [ ] League cards display (5 cards)
- [ ] League logos load correctly
- [ ] No "Using Mock Data" badge (unless API failed)
- [ ] Clicking a league navigates to detail page

### Debug API Page (`/debug-api`)
- [ ] Page loads without errors
- [ ] "Test getTopLeagues()" button works
- [ ] Output shows success message
- [ ] Output shows 5 leagues
- [ ] Console shows detailed logs
- [ ] No errors in console

### TodayPredictionsPage (`/predictions/today`)
- [ ] Page loads without errors
- [ ] Matches display (if any today)
- [ ] League filter shows leagues
- [ ] Console shows "Leagues received: X leagues"

### TomorrowPredictionsPage (`/predictions/tomorrow`)
- [ ] Page loads without errors
- [ ] Matches display (if any tomorrow)
- [ ] League filter shows leagues
- [ ] Console shows "Leagues received: X leagues"

### LeagueDetailPage (`/league/39`)
- [ ] Page loads without errors
- [ ] League header displays
- [ ] Teams grid displays (20 teams)
- [ ] Upcoming matches display
- [ ] Console shows "Teams received: X teams"
- [ ] Console shows "Matches received: X matches"

---

## Expected vs Actual

### Expected Behavior (LeaguesPage):
1. Page loads
2. Loading spinner shows
3. API calls made (5 requests)
4. Data received
5. 5 league cards display
6. Each card shows logo, name, country, season
7. Cards are clickable

### Actual Behavior (Report from User):
1. Page loads ✅
2. Loading spinner shows (?) 
3. API calls made (?)
4. Data received (?)
5. No league cards display ❌
6. Page appears empty ❌

### Questions to Answer:
- Does loading spinner appear?
- Does it disappear (loading complete)?
- Are there any error messages?
- Is "Using Mock Data" badge visible?
- What do console logs show?
- What do network requests show?

---

## Next Steps

### For User:
1. **Navigate to `/debug-api`**
   - Click "Test getTopLeagues()"
   - Copy the output
   - Share the results

2. **Navigate to `/leagues`**
   - Open browser console (F12)
   - Copy all console logs
   - Share the logs

3. **Check Network Tab**
   - Open DevTools → Network
   - Filter by "Fetch/XHR"
   - Refresh `/leagues` page
   - Screenshot the requests
   - Share the screenshot

4. **Compare with Working Page**
   - Navigate to `/predictions/today`
   - Check if leagues show in filter
   - Share if this works

### For Developer:
1. Review console logs from user
2. Review network requests from user
3. Review debug page output from user
4. Identify root cause
5. Implement fix
6. Test fix
7. Deploy fix

---

## Files Modified

1. ✅ `frontend/src/pages/LeaguesPage.tsx`
   - Added detailed logging
   - Added empty array check
   - Added "No leagues" state

2. ✅ `frontend/src/pages/DebugAPIPage.tsx`
   - Created new debug page
   - Tests all API methods

3. ✅ `frontend/src/App.tsx`
   - Added route for debug page

---

## URLs for Testing

- **LeaguesPage:** http://localhost:3000/leagues
- **Debug API Page:** http://localhost:3000/debug-api
- **Today Predictions:** http://localhost:3000/predictions/today
- **Tomorrow Predictions:** http://localhost:3000/predictions/tomorrow
- **Premier League Detail:** http://localhost:3000/league/39

---

**Status:** Debugging tools deployed, awaiting user feedback
**Action Required:** User needs to test and report findings

