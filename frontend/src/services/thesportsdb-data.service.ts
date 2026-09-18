/**
 * TheSportsDB Data Service
 * 
 * High-level service that combines TheSportsDB V1 API calls with data mapping
 * This is the main service that the frontend components should use
 */

import { Team, League, Match, LeagueStanding } from '@/types';
import theSportsDBService from './thesportsdb.service';
import {
  mapLeague,
  mapTeam,
  mapEvent,
  mapStanding,
} from './thesportsdb-mapper.service';

// Popular league IDs from TheSportsDB
export const POPULAR_LEAGUES = {
  PREMIER_LEAGUE: '4328',
  LA_LIGA: '4335',
  SERIE_A: '4332',
  BUNDESLIGA: '4331',
  LIGUE_1: '4334',
  CHAMPIONS_LEAGUE: '4480',
} as const;

// League name mappings for API calls
const LEAGUE_NAMES = {
  '4328': 'English Premier League',
  '4335': 'Spanish La Liga',
  '4332': 'Italian Serie A',
  '4331': 'German Bundesliga',
  '4334': 'French Ligue 1',
  '4480': 'UEFA Champions League',
} as const;

// Cache for frequently accessed data
const cache = {
  leagues: new Map<string, { data: League[]; timestamp: number }>(),
  teams: new Map<string, { data: Team[]; timestamp: number }>(),
  matches: new Map<string, { data: Match[]; timestamp: number }>(),
  standings: new Map<string, { data: LeagueStanding[]; timestamp: number }>(),
};

const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

class TheSportsDBDataService {
  /**
   * Get current season string
   */
  private getCurrentSeason(): string {
    return '2025-2026';
  }

  /**
   * Check if cached data is still valid
   */
  private isCacheValid(timestamp: number): boolean {
    return Date.now() - timestamp < CACHE_DURATION;
  }

  /**
   * Get top European leagues
   */
  async getTopLeagues(): Promise<League[]> {
    const cacheKey = 'top-leagues';
    const cached = cache.leagues.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp)) {
      console.log('TheSportsDBDataService: Returning cached top leagues:', cached.data.length);
      return cached.data;
    }

    try {
      console.log('TheSportsDBDataService: Fetching top leagues');

      const topLeagueIds = [
        POPULAR_LEAGUES.PREMIER_LEAGUE,
        POPULAR_LEAGUES.LA_LIGA,
        POPULAR_LEAGUES.SERIE_A,
        POPULAR_LEAGUES.BUNDESLIGA,
        POPULAR_LEAGUES.LIGUE_1,
      ];

      const leaguePromises = topLeagueIds.map(id =>
        theSportsDBService.lookupLeague(id)
      );

      const responses = await Promise.all(leaguePromises);
      console.log('TheSportsDBDataService: Received responses:', responses.length);

      const leagues = responses
        .filter(r => r.leagues && r.leagues.length > 0)
        .map(r => mapLeague(r.leagues[0]));

      console.log('TheSportsDBDataService: Mapped leagues:', leagues.length);

      cache.leagues.set(cacheKey, {
        data: leagues,
        timestamp: Date.now(),
      });

      return leagues;
    } catch (error) {
      console.error('TheSportsDBDataService: Error fetching top leagues:', error);
      throw error;
    }
  }

  /**
   * Get teams for a specific league
   */
  async getTeamsByLeague(leagueId: string): Promise<Team[]> {
    const cacheKey = `teams-${leagueId}`;
    const cached = cache.teams.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp)) {
      console.log('TheSportsDBDataService: Returning cached teams for league:', leagueId);
      return cached.data;
    }

    try {
      const leagueName = LEAGUE_NAMES[leagueId as keyof typeof LEAGUE_NAMES] || 'English Premier League';
      console.log('TheSportsDBDataService: Fetching teams for league:', leagueName);

      const response = await theSportsDBService.getTeamsByLeagueName(leagueName);
      
      if (!response.teams || response.teams.length === 0) {
        console.warn('TheSportsDBDataService: No teams found for league:', leagueName);
        return [];
      }

      const teams = response.teams.map((team) => mapTeam(team));
      console.log('TheSportsDBDataService: Mapped teams:', teams.length);

      cache.teams.set(cacheKey, {
        data: teams,
        timestamp: Date.now(),
      });

      return teams;
    } catch (error) {
      console.error('TheSportsDBDataService: Error fetching teams:', error);
      throw error;
    }
  }

  /**
   * Get league standings
   */
  async getStandings(leagueId: string, season?: string): Promise<LeagueStanding[]> {
    const currentSeason = season || this.getCurrentSeason();
    const cacheKey = `standings-${leagueId}-${currentSeason}`;
    const cached = cache.standings.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp)) {
      console.log('TheSportsDBDataService: Returning cached standings');
      return cached.data;
    }

    try {
      console.log('TheSportsDBDataService: Fetching standings for league:', leagueId, 'season:', currentSeason);

      const response = await theSportsDBService.getStandings(leagueId, currentSeason);
      
      if (!response.table || response.table.length === 0) {
        console.warn('TheSportsDBDataService: No standings found');
        return [];
      }

      const standings = response.table.map(mapStanding);
      console.log('TheSportsDBDataService: Mapped standings:', standings.length);

      cache.standings.set(cacheKey, {
        data: standings,
        timestamp: Date.now(),
      });

      return standings;
    } catch (error) {
      console.error('TheSportsDBDataService: Error fetching standings:', error);
      throw error;
    }
  }

  /**
   * Get fixtures for a specific date
   */
  async getFixturesByDate(date: string): Promise<Match[]> {
    const cacheKey = `fixtures-${date}`;
    const cached = cache.matches.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp)) {
      console.log('TheSportsDBDataService: Returning cached fixtures for', date);
      return cached.data;
    }

    try {
      console.log('TheSportsDBDataService: Fetching fixtures for date:', date);
      const response = await theSportsDBService.getEventsByDate(date, 'Soccer');

      if (!response.events || response.events.length === 0) {
        console.log('TheSportsDBDataService: No fixtures found for', date);
        return [];
      }

      console.log(`TheSportsDBDataService: Found ${response.events.length} fixtures`);

      const matches = response.events.map(event => mapEvent(event));

      cache.matches.set(cacheKey, {
        data: matches,
        timestamp: Date.now(),
      });

      console.log(`TheSportsDBDataService: Cached ${matches.length} matches for ${date}`);
      return matches;
    } catch (error) {
      console.error('TheSportsDBDataService: Error fetching fixtures:', error);
      throw error;
    }
  }

  /**
   * Get today's fixtures
   */
  async getTodayFixtures(): Promise<Match[]> {
    const today = new Date().toISOString().split('T')[0];
    return this.getFixturesByDate(today);
  }

  /**
   * Get tomorrow's fixtures
   */
  async getTomorrowFixtures(): Promise<Match[]> {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];
    return this.getFixturesByDate(tomorrowStr);
  }

  /**
   * Get fixtures for a specific league
   */
  async getFixturesByLeague(leagueId: string, season?: string): Promise<Match[]> {
    const currentSeason = season || this.getCurrentSeason();
    const cacheKey = `league-fixtures-${leagueId}-${currentSeason}`;
    const cached = cache.matches.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp)) {
      console.log('TheSportsDBDataService: Returning cached league fixtures');
      return cached.data;
    }

    try {
      console.log(`TheSportsDBDataService: Fetching fixtures for league ${leagueId}, season ${currentSeason}`);
      const response = await theSportsDBService.getSeasonSchedule(leagueId, currentSeason);

      if (!response.events || response.events.length === 0) {
        console.log('TheSportsDBDataService: No fixtures found for league');
        return [];
      }

      console.log(`TheSportsDBDataService: Found ${response.events.length} fixtures for league ${leagueId}`);

      // Limit to first 50 matches to avoid overwhelming the UI
      const matches = response.events.slice(0, 50).map(event => mapEvent(event));

      cache.matches.set(cacheKey, {
        data: matches,
        timestamp: Date.now(),
      });

      return matches;
    } catch (error) {
      console.error('TheSportsDBDataService: Error fetching league fixtures:', error);
      throw error;
    }
  }

  /**
   * Get next fixtures for a league
   */
  async getNextLeagueFixtures(leagueId: string): Promise<Match[]> {
    try {
      console.log(`TheSportsDBDataService: Fetching next fixtures for league ${leagueId}`);
      const response = await theSportsDBService.getNextLeagueEvents(leagueId);

      if (!response.events || response.events.length === 0) {
        console.log('TheSportsDBDataService: No next fixtures found');
        return [];
      }

      const matches = response.events.map(event => mapEvent(event));
      return matches;
    } catch (error) {
      console.error('TheSportsDBDataService: Error fetching next league fixtures:', error);
      throw error;
    }
  }

  /**
   * Clear all caches
   */
  clearCache() {
    cache.leagues.clear();
    cache.teams.clear();
    cache.matches.clear();
    cache.standings.clear();
  }
}

// Export singleton instance
export const theSportsDBDataService = new TheSportsDBDataService();
export default theSportsDBDataService;

// Expose cache clearing function to window for debugging
if (typeof window !== 'undefined') {
  (window as any).clearSportsDBCache = () => {
    theSportsDBDataService.clearCache();
    console.log('✅ TheSportsDB cache cleared! Refresh the page to see updated data.');
  };
}

