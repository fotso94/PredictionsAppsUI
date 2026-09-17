# ⚠️ TheSportsDB Free Tier (V1 API) - Complete Limitations

## 🔑 API Key Information

- **Free Test Key**: `3` (for testing)
- **Free Production Key**: `123` (for production)
- **Premium Key**: Custom key ($9/month)

---

## 🚦 Rate Limits

| Tier | Requests Per Minute |
|------|---------------------|
| **Free** | 30 requests/minute |
| **Premium** | 100 requests/minute |
| **Business** | 120 requests/minute |

**Important**: You'll receive a `429` HTTP status code if you exceed the limit. Wait 1 minute before making more requests.

---

## 📊 Endpoint Limitations (Free vs Premium)

### 🔍 **Search Endpoints**

| Endpoint | Free Limit | Premium Limit | Notes |
|----------|------------|---------------|-------|
| Search Teams | 2 results | 10 results | `/searchteams.php?t=Arsenal` |
| Search Events | 2 results | 10 results | `/searchevents.php?e=Arsenal_vs_Chelsea` |
| Search Players | 2 results | 10 results | `/searchplayers.php?p=Danny_Welbeck` |
| Search Venues | 2 results | 10 results | `/searchvenues.php?v=Wembley` |

**Impact**: ⚠️ **CRITICAL** - Only 2 results per search on free tier!

---

### 🔎 **Lookup Endpoints**

| Endpoint | Free Limit | Premium Limit | Notes |
|----------|------------|---------------|-------|
| Lookup League | 1 result | 1 result | ✅ Same for both |
| Lookup Team | 1 result | 1 result | ✅ Same for both |
| Lookup Player | 1 result | 1 result | ✅ Same for both |
| Lookup Event | 1 result | 1 result | ✅ Same for both |
| Lookup Venue | 1 result | 1 result | ✅ Same for both |
| **Lookup League Table** | **5 results** | **100 results** | ⚠️ Limited to 5 teams on free! |
| Lookup Team Equipment | 2 results | 100 results | |
| Lookup Player Honours | 5 results | 500 results | |
| Lookup Player Former Teams | 5 results | 100 results | |
| Lookup Player Milestones | 5 results | 100 results | |
| Lookup Player Contracts | 1 result | 100 results | |
| Lookup Player Results | 5 results | 500 results | |
| Lookup Event Results | 5 results | 100 results | |
| Lookup Event Lineup | 5 results | 100 results | |
| Lookup Event Timeline | 5 results | 100 results | |
| Lookup Event Statistics | 5 results | 100 results | |
| Lookup Event TV Broadcasts | 2 results | 100 results | |

**Impact**: ⚠️ **CRITICAL** - League tables only show 5 teams on free tier!

---

### 📋 **List Endpoints**

| Endpoint | Free Limit | Premium Limit | Notes |
|----------|------------|---------------|-------|
| All Sports | 2 results | 50 results | `/all_sports.php` |
| All Countries | 50 results | 500 results | ✅ Decent for free |
| **All Leagues** | **10 results** | **3000 results** | ⚠️ Only 10 leagues on free! |
| List Leagues | 10 results | 100 results | `/search_all_leagues.php?c=England&s=Soccer` |
| List Seasons | 5 results | 500 results | |
| **List Teams** | **10 results** | **3000 results** | ⚠️ Only 10 teams on free! |
| List Players | 10 results | 100 results | |

**Impact**: 🔴 **CRITICAL** - Major limitations:
- Only 10 leagues returned (not all leagues!)
- Only 10 teams per league (Premier League has 20 teams!)

---

### 📅 **Schedule Endpoints**

| Endpoint | Free Limit | Premium Limit | Notes |
|----------|------------|---------------|-------|
| **Schedule Team Next** | **1 event (home only)** | **10 events** | ⚠️ Only shows HOME events on free! |
| **Schedule Team Previous** | **1 event (home only)** | **10 events** | ⚠️ Only shows HOME events on free! |
| **Schedule League Next** | **1 event** | **20 events** | ⚠️ Only 1 upcoming match! |
| **Schedule League Previous** | **1 event** | **20 events** | ⚠️ Only 1 past match! |
| Schedule Day | 5 results | 1500 results | `/eventsday.php?d=2014-10-10` |
| **Schedule Season** | **15 results** | **3000 results** | ⚠️ Only 15 matches per season! |
| Schedule TV | 1 result | 500 results | |

**Impact**: 🔴 **CRITICAL** - Major limitations:
- Only 1 next/previous event per league (not useful for fixtures list!)
- Only 15 matches per season (a season has 380+ matches!)
- Team schedules only show HOME events

---

### 🎥 **Video Endpoints**

| Endpoint | Free Limit | Premium Limit | Notes |
|----------|------------|---------------|-------|
| Video YouTube Highlights | 2 results | 50 results | `/eventshighlights.php?d=2024-07-07` |

**Impact**: ⚠️ Limited highlights on free tier

---

## 🚨 **CRITICAL LIMITATIONS FOR YOUR USE CASE**

### ❌ **What WON'T Work on Free Tier:**

1. **League Tables (Standings)**
   - ❌ Only shows **5 teams** (need 20 for full table)
   - **Workaround**: None - need Premium

2. **All Teams in League**
   - ❌ Only shows **10 teams** (Premier League has 20)
   - **Workaround**: None - need Premium

3. **All Leagues**
   - ❌ Only shows **10 leagues** (you want 5, so this is OK)
   - ✅ **This works** for your use case

4. **Upcoming Fixtures**
   - ❌ Only shows **1 next event** per league
   - ❌ Only shows **HOME events** for teams
   - **Workaround**: Use "Schedule Day" endpoint (5 events per day)

5. **Past Fixtures**
   - ❌ Only shows **1 past event** per league
   - ❌ Only shows **HOME events** for teams
   - **Workaround**: Use "Schedule Day" endpoint (5 events per day)

6. **Full Season Schedule**
   - ❌ Only shows **15 matches** (season has 380+ matches)
   - **Workaround**: None - need Premium

---

## ✅ **What WILL Work on Free Tier:**

1. **Get Top 5 European Leagues** ✅
   - Free limit: 10 leagues
   - You need: 5 leagues
   - **Status**: ✅ WORKS

2. **Get League Details** ✅
   - Free limit: 1 per request
   - **Status**: ✅ WORKS (make 5 requests for 5 leagues)

3. **Search Specific Team** ✅
   - Free limit: 2 results
   - **Status**: ✅ WORKS (searching "Arsenal" returns Arsenal)

4. **Get Team Details** ✅
   - Free limit: 1 per request
   - **Status**: ✅ WORKS

5. **Get Events by Date** ✅
   - Free limit: 5 events per day
   - **Status**: ⚠️ LIMITED but usable
   - Can get today's matches (up to 5)
   - Can get tomorrow's matches (up to 5)

---

## 🔄 **Workarounds for Free Tier**

### 1. **Get All Teams in League**
**Problem**: Only 10 teams returned, need 20

**Workaround**: 
- Use `/search_all_teams.php?l=English Premier League` (returns 10)
- Then manually search for missing teams by name
- **Complexity**: High
- **Feasibility**: ❌ Not practical

### 2. **Get League Table (Standings)**
**Problem**: Only 5 teams returned, need 20

**Workaround**: 
- None available
- **Feasibility**: ❌ Impossible on free tier

### 3. **Get Upcoming Fixtures**
**Problem**: Only 1 next event per league

**Workaround**: 
- Use `/eventsday.php?d=2025-01-10` for specific dates
- Make multiple requests for different dates
- **Complexity**: Medium
- **Feasibility**: ✅ Possible but requires multiple API calls

### 4. **Get Today's Matches**
**Problem**: Only 5 events per day

**Workaround**: 
- Filter by league: `/eventsday.php?d=2025-01-10&l=English Premier League`
- **Feasibility**: ✅ Works well

---

## 💰 **Premium Tier ($9/month)**

### What You Get:

1. **Higher Limits**
   - 100 requests/minute (vs 30)
   - Full league tables (100 teams vs 5)
   - All teams in league (3000 vs 10)
   - More events (20 next vs 1)

2. **V2 API Access**
   - Modern REST API
   - Better authentication (header-based)
   - Standard HTTP response codes
   - Cleaner naming

3. **Premium Features**
   - 2-minute livescores
   - Video highlight links
   - More detailed statistics

---

## 📊 **Comparison: API-Football vs TheSportsDB**

| Feature | API-Football (Free) | TheSportsDB (Free) | TheSportsDB (Premium) |
|---------|---------------------|--------------------|-----------------------|
| **Current Season** | ❌ No (2021-2023) | ✅ Yes | ✅ Yes |
| **Rate Limit** | 100/day | 30/minute | 100/minute |
| **All Teams** | ✅ Yes | ❌ No (10 only) | ✅ Yes (3000) |
| **League Table** | ❌ Limited | ❌ Very Limited (5) | ✅ Yes (100) |
| **Next Fixtures** | ✅ Yes | ❌ No (1 only) | ✅ Yes (20) |
| **Today's Fixtures** | ✅ Yes | ⚠️ Limited (5) | ✅ Yes (1500) |
| **Team Details** | ✅ Yes | ✅ Yes | ✅ Yes |
| **League Details** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Cost** | Free | Free | $9/month |

---

## 🎯 **Recommendation for Your Project**

### ❌ **TheSportsDB Free Tier is NOT Suitable** because:

1. **Can't get all teams** (only 10, need 20)
2. **Can't get full standings** (only 5 teams, need 20)
3. **Can't get upcoming fixtures** (only 1 event, need multiple)
4. **Can't get full season schedule** (only 15 matches, need 380+)

### ✅ **Options:**

#### **Option 1: Upgrade to TheSportsDB Premium ($9/month)**
- ✅ Current season data
- ✅ All teams (3000 limit)
- ✅ Full standings (100 teams)
- ✅ More fixtures (20 next events)
- ✅ Livescores
- ✅ V2 API access

#### **Option 2: Upgrade to API-Football Paid Plan**
- ✅ Current season data
- ✅ All teams
- ✅ Full standings
- ✅ All fixtures
- ✅ More reliable
- ❌ More expensive ($10-50/month)

#### **Option 3: Try Other Free APIs**
- **Football-Data.org** - Free tier with current season
- **Sportmonks** - Free tier available
- **API-Sports** - Different provider

#### **Option 4: Hybrid Approach**
- Use TheSportsDB Free for: League info, team details
- Use API-Football Free for: Historical data (2021-2023)
- Build your own database over time

---

## 📝 **Conclusion**

**TheSportsDB Free Tier is TOO LIMITED for your needs.**

The critical limitations are:
- 🔴 Only 10 teams per league (need 20)
- 🔴 Only 5 teams in standings (need 20)
- 🔴 Only 1 next/previous event (need multiple)
- 🔴 Only 15 matches per season (need 380+)

**Best Solution**: 
1. Test the free tier to verify data quality
2. If data quality is good → **Upgrade to Premium ($9/month)**
3. If not → **Try Football-Data.org or other alternatives**

---

**Last Updated**: 2025-01-03
**Status**: ⚠️ FREE TIER NOT RECOMMENDED FOR YOUR USE CASE

