/**
 * Football Data Service
 * 
 * High-level service that combines API-Football calls with data mapping
 * This is the main service that the frontend components should use
 */

import { Team, League, Match, LeagueStanding } from '@/types';
import apiFootballService from './api-football.service';
import publicPredictionService, { PublicPrediction } from './public-prediction.service';
import {
  mapLeague,
  mapTeam,
  mapFixture,
  mapHeadToHead,
} from './api-mapper.service';

// Popular league IDs from API-Football
export const POPULAR_LEAGUES = {
  PREMIER_LEAGUE: 39,
  LA_LIGA: 140,
  SERIE_A: 135,
  BUNDESLIGA: 78,
  LIGUE_1: 61,
  CHAMPIONS_LEAGUE: 2,
  EUROPA_LEAGUE: 3,
  WORLD_CUP: 1,
} as const;

// Cache for frequently accessed data
const cache = {
  leagues: new Map<string, { data: League[]; timestamp: number }>(),
  teams: new Map<string, { data: Team[]; timestamp: number }>(),
  matches: new Map<string, { data: Match[]; timestamp: number }>(),
};

const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

class FootballDataService {
  /**
   * Get current season year
   * Pro API plan has access to current season data
   */
  private getCurrentSeason(): number {
    // Pro API Key - Access to current season
    const now = new Date();
    const year = now.getFullYear();
    // Football season runs from August to May
    // If before June, use previous year as season start
    return now.getMonth() < 6 ? year - 1 : year;
  }

  /**
   * Check if cached data is still valid
   */
  private isCacheValid(timestamp: number): boolean {
    return Date.now() - timestamp < CACHE_DURATION;
  }

  /**
   * Get all leagues or filter by criteria
   */
  async getLeagues(params?: {
    country?: string;
    season?: number;
    type?: string;
  }): Promise<League[]> {
    const cacheKey = JSON.stringify(params || {});
    const cached = cache.leagues.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp)) {
      console.log('Returning cached leagues');
      return cached.data;
    }

    try {
      const response = await apiFootballService.getLeagues({
        ...params,
        season: params?.season || this.getCurrentSeason(),
      });

      const leagues = response.response.map(mapLeague);
      
      cache.leagues.set(cacheKey, {
        data: leagues,
        timestamp: Date.now(),
      });

      return leagues;
    } catch (error) {
      console.error('Error fetching leagues:', error);
      throw error;
    }
  }

  /**
   * Get top European leagues
   */
  async getTopLeagues(): Promise<League[]> {
    const cacheKey = 'top-leagues';
    const cached = cache.leagues.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp)) {
      console.log('FootballDataService: Returning cached top leagues:', cached.data.length);
      return cached.data;
    }

    try {
      const season = this.getCurrentSeason();
      console.log('FootballDataService: Fetching top leagues for season:', season);

      const topLeagueIds = [
        POPULAR_LEAGUES.PREMIER_LEAGUE,
        POPULAR_LEAGUES.LA_LIGA,
        POPULAR_LEAGUES.SERIE_A,
        POPULAR_LEAGUES.BUNDESLIGA,
        POPULAR_LEAGUES.LIGUE_1,
      ];

      console.log('FootballDataService: Fetching leagues with IDs:', topLeagueIds);

      const leaguePromises = topLeagueIds.map(id =>
        apiFootballService.getLeagues({ id, season })
      );

      const responses = await Promise.all(leaguePromises);
      console.log('FootballDataService: Received responses:', responses.length);

      // Log each response
      responses.forEach((r, index) => {
        console.log(`FootballDataService: League ${topLeagueIds[index]} response:`, {
          results: r.results,
          responseLength: r.response.length,
          hasData: r.response.length > 0
        });
      });

      const leagues = responses
        .filter(r => {
          const hasData = r.response.length > 0;
          if (!hasData) {
            console.warn('FootballDataService: Empty response for league, skipping');
          }
          return hasData;
        })
        .map(r => mapLeague(r.response[0]));

      console.log('FootballDataService: Mapped leagues:', leagues.length);
      console.log('FootballDataService: League data:', leagues);

      cache.leagues.set(cacheKey, {
        data: leagues,
        timestamp: Date.now(),
      });

      return leagues;
    } catch (error) {
      console.error('FootballDataService: Error fetching top leagues:', error);
      throw error;
    }
  }

  /**
   * Get teams for a specific league
   */
  async getTeamsByLeague(leagueId: number, season?: number): Promise<Team[]> {
    const currentSeason = season || this.getCurrentSeason();
    const cacheKey = `teams-${leagueId}-${currentSeason}`;
    const cached = cache.teams.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp)) {
      return cached.data;
    }

    try {
      const response = await apiFootballService.getTeams({
        league: leagueId,
        season: currentSeason,
      });

      // Get league info for context
      const leagueResponse = await apiFootballService.getLeagues({
        id: leagueId,
        season: currentSeason,
      });
      const leagueName = leagueResponse.response[0]?.league.name || '';

      const teams = response.response.map(apiTeam => {
        const team = mapTeam(apiTeam);
        team.league = leagueName;
        return team;
      });

      cache.teams.set(cacheKey, {
        data: teams,
        timestamp: Date.now(),
      });

      return teams;
    } catch (error) {
      console.error('Error fetching teams:', error);
      throw error;
    }
  }

  /**
   * Fetch prediction for a single fixture
   * Returns null if prediction is not available
   */
  private async fetchPrediction(fixtureId: number): Promise<any | null> {
    try {
      const response = await apiFootballService.getPredictions(fixtureId);
      if (response.response && response.response.length > 0) {
        return response.response[0];
      }
      return null;
    } catch (error) {
      // Silently fail - predictions are optional
      return null;
    }
  }

  /**
   * Fetch predictions for multiple fixtures with rate limiting
   * Fetches predictions sequentially with delay to avoid rate limits
   */
  private async fetchPredictionsBatch(fixtureIds: number[]): Promise<Map<number, any>> {
    const predictions = new Map<number, any>();

    // Limit to first 5 fixtures to avoid excessive API calls
    const limitedIds = fixtureIds.slice(0, 5);

    for (const fixtureId of limitedIds) {
      const prediction = await this.fetchPrediction(fixtureId);
      if (prediction) {
        predictions.set(fixtureId, prediction);
      }
      // Small delay to avoid rate limiting (100ms between requests)
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    return predictions;
  }

  /**
   * Fetch expert predictions from backend for multiple fixtures
   * Returns a map of fixture ID to expert prediction
   */
  private async fetchExpertPredictionsBatch(fixtureIds: number[]): Promise<Map<number, PublicPrediction>> {
    const expertPredictions = new Map<number, PublicPrediction>();

    try {
      // Convert fixture IDs to strings
      const fixtureIdStrings = fixtureIds.map(id => String(id));

      // Fetch expert predictions in batch
      const predictions = await publicPredictionService.getPublishedPredictionsBatch(fixtureIdStrings);

      // Convert back to number keys for consistency
      predictions.forEach((prediction, matchId) => {
        expertPredictions.set(Number(matchId), prediction);
      });

      console.log(`Fetched ${expertPredictions.size} expert predictions from backend`);
    } catch (error) {
      console.error('Error fetching expert predictions:', error);
      // Return empty map on error - will fall back to API-Football predictions
    }

    return expertPredictions;
  }

  /**
   * Merge expert predictions with API-Football predictions
   * Expert predictions take priority over API-Football predictions
   */
  private mergePredictions(
    _fixtureId: number,
    apiFootballPrediction: any | null,
    expertPrediction: PublicPrediction | null
  ): any {
    // If expert prediction exists, use it (highest priority)
    if (expertPrediction) {
      const winner = this.getWinnerFromProbs(
        expertPrediction.home_win_prob,
        expertPrediction.draw_prob,
        expertPrediction.away_win_prob
      );

      // Return in API-Football prediction format for compatibility with mapPredictions
      return {
        predictions: {
          winner: winner,
          win_or_draw: true,
          under_over: null,
          goals: { home: null, away: null },
          advice: expertPrediction.reasoning || 'Expert prediction',
          percent: {
            home: `${Math.round(expertPrediction.home_win_prob * 100)}%`,
            draw: `${Math.round(expertPrediction.draw_prob * 100)}%`,
            away: `${Math.round(expertPrediction.away_win_prob * 100)}%`,
          },
        },
        comparison: {
          form: { home: '50%', away: '50%' },
          att: { home: '50%', away: '50%' },
          def: { home: '50%', away: '50%' },
          poisson_distribution: { home: '50%', away: '50%' },
          h2h: { home: '50%', away: '50%' },
          goals: { home: '50%', away: '50%' },
          total: { home: '50%', away: '50%' },
        },
        // Add metadata to indicate this is an expert prediction
        source: 'expert',
        source_type: expertPrediction.source,
        confidence_score: expertPrediction.confidence_score,
        priority_level: expertPrediction.priority_level,
      };
    }

    // Fall back to API-Football prediction
    if (apiFootballPrediction) {
      return {
        ...apiFootballPrediction,
        source: 'api-football',
      };
    }

    // No prediction available
    return null;
  }

  /**
   * Get winner from probabilities
   */
  private getWinnerFromProbs(homeProb: number, drawProb: number, awayProb: number): { id: number; name: string; comment: string } | null {
    const max = Math.max(homeProb, drawProb, awayProb);

    if (max === homeProb) {
      return { id: 1, name: 'Home', comment: 'Home team favored' };
    } else if (max === awayProb) {
      return { id: 2, name: 'Away', comment: 'Away team favored' };
    } else {
      return { id: 3, name: 'Draw', comment: 'Draw expected' };
    }
  }

  /**
   * Get fixtures for a specific date
   * Optimized to avoid excessive API calls
   * Integrates expert predictions from backend with API-Football predictions
   */
  async getFixturesByDate(date: string): Promise<Match[]> {
    const cacheKey = `fixtures-${date}`;
    const cached = cache.matches.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp)) {
      console.log('Returning cached fixtures for', date);
      return cached.data;
    }

    try {
      console.log('Fetching fixtures for date:', date);
      const response = await apiFootballService.getFixtures({ date });

      console.log(`Found ${response.response.length} fixtures`);

      // Get all fixture IDs
      const allFixtureIds = response.response.map(f => f.fixture.id);

      // Separate upcoming and past fixtures
      const now = new Date();
      const upcomingFixtures = response.response.filter(f => new Date(f.fixture.date) > now);
      const upcomingIds = upcomingFixtures.slice(0, 5).map(f => f.fixture.id);

      // Fetch both expert predictions and API-Football predictions in parallel
      const [expertPredictions, apiFootballPredictions] = await Promise.all([
        this.fetchExpertPredictionsBatch(allFixtureIds),
        this.fetchPredictionsBatch(upcomingIds),
      ]);

      console.log(`Fetched ${expertPredictions.size} expert predictions and ${apiFootballPredictions.size} API-Football predictions`);

      // Map all fixtures to matches
      const matches = response.response.map((fixture) => {
        const homeTeam = this.createBasicTeam(fixture.teams.home);
        homeTeam.venue = fixture.fixture.venue.name || 'Unknown Venue';

        const awayTeam = this.createBasicTeam(fixture.teams.away);
        const league = this.createBasicLeague(fixture.league);

        // Get expert prediction and API-Football prediction
        const expertPrediction = expertPredictions.get(fixture.fixture.id) || null;
        const apiFootballPrediction = apiFootballPredictions.get(fixture.fixture.id) || null;

        // Merge predictions (expert takes priority)
        const prediction = this.mergePredictions(fixture.fixture.id, apiFootballPrediction, expertPrediction);

        // Debug log for expert predictions
        if (expertPrediction) {
          console.log(`🎯 Expert prediction for fixture ${fixture.fixture.id}:`, {
            source: prediction?.source,
            home: fixture.teams.home.name,
            away: fixture.teams.away.name,
          });
        }

        return mapFixture(fixture, homeTeam, awayTeam, league, prediction);
      });

      cache.matches.set(cacheKey, {
        data: matches,
        timestamp: Date.now(),
      });

      console.log(`Cached ${matches.length} matches (${expertPredictions.size} expert + ${apiFootballPredictions.size} API-Football predictions) for ${date}`);
      return matches;
    } catch (error) {
      console.error('Error fetching fixtures:', error);
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
   * Optimized to avoid excessive API calls
   * Integrates expert predictions from backend with API-Football predictions
   */
  async getFixturesByLeague(
    leagueId: number,
    season?: number,
    options?: { next?: number; last?: number }
  ): Promise<Match[]> {
    const currentSeason = season || this.getCurrentSeason();

    try {
      console.log(`Fetching fixtures for league ${leagueId}, season ${currentSeason}`);
      const response = await apiFootballService.getFixtures({
        league: leagueId,
        season: currentSeason,
        ...options,
      });

      console.log(`Found ${response.response.length} fixtures for league ${leagueId}`);

      // Limit to 20 fixtures
      const limitedFixtures = response.response.slice(0, 20);

      // Get all fixture IDs
      const allFixtureIds = limitedFixtures.map(f => f.fixture.id);

      // Separate upcoming and past fixtures
      const now = new Date();
      const upcomingFixtures = limitedFixtures.filter(f => new Date(f.fixture.date) > now);
      const upcomingIds = upcomingFixtures.slice(0, 5).map(f => f.fixture.id);

      // Fetch both expert predictions and API-Football predictions in parallel
      const [expertPredictions, apiFootballPredictions] = await Promise.all([
        this.fetchExpertPredictionsBatch(allFixtureIds),
        this.fetchPredictionsBatch(upcomingIds),
      ]);

      console.log(`Fetched ${expertPredictions.size} expert predictions and ${apiFootballPredictions.size} API-Football predictions for league ${leagueId}`);

      // Map all fixtures to matches
      const matches = limitedFixtures.map((fixture) => {
        const homeTeam = this.createBasicTeam(fixture.teams.home);
        homeTeam.venue = fixture.fixture.venue.name || 'Unknown Venue';

        const awayTeam = this.createBasicTeam(fixture.teams.away);
        const league = this.createBasicLeague(fixture.league);

        // Get expert prediction and API-Football prediction
        const expertPrediction = expertPredictions.get(fixture.fixture.id) || null;
        const apiFootballPrediction = apiFootballPredictions.get(fixture.fixture.id) || null;

        // Merge predictions (expert takes priority)
        const prediction = this.mergePredictions(fixture.fixture.id, apiFootballPrediction, expertPrediction);

        return mapFixture(fixture, homeTeam, awayTeam, league, prediction);
      });

      console.log(`Mapped ${matches.length} matches (${expertPredictions.size} expert + ${apiFootballPredictions.size} API-Football predictions) for league ${leagueId}`);
      return matches;
    } catch (error) {
      console.error('Error fetching league fixtures:', error);
      throw error;
    }
  }

  /**
   * Get head-to-head data for two teams
   */
  async getHeadToHead(homeTeamId: number, awayTeamId: number) {
    try {
      const response = await apiFootballService.getHeadToHead({
        h2h: `${homeTeamId}-${awayTeamId}`,
        last: 10,
      });

      return mapHeadToHead(response.response, homeTeamId, awayTeamId);
    } catch (error) {
      console.error('Error fetching head-to-head:', error);
      throw error;
    }
  }

  /**
   * Get league standings
   */
  async getStandings(leagueId: number, season?: number): Promise<LeagueStanding[]> {
    const currentSeason = season || this.getCurrentSeason();

    try {
      console.log(`Fetching standings for league ${leagueId}, season ${currentSeason}`);
      const response = await apiFootballService.getStandings({
        league: leagueId,
        season: currentSeason,
      });

      if (!response.response || response.response.length === 0) {
        console.warn(`No standings data for league ${leagueId}`);
        return [];
      }

      // API-Football returns standings in a nested structure
      const standingsData = response.response[0]?.league?.standings?.[0] || [];

      const standings: LeagueStanding[] = standingsData.map((standing: any) => ({
        position: standing.rank,
        team: this.createBasicTeam({
          id: standing.team.id,
          name: standing.team.name,
          logo: standing.team.logo,
        }),
        matchesPlayed: standing.all.played,
        wins: standing.all.win,
        draws: standing.all.draw,
        losses: standing.all.lose,
        goalsFor: standing.all.goals.for,
        goalsAgainst: standing.all.goals.against,
        goalDifference: standing.goalsDiff,
        points: standing.points,
        form: standing.form ? standing.form.split('').slice(-5) : [],
      }));

      console.log(`Mapped ${standings.length} standings for league ${leagueId}`);
      return standings;
    } catch (error) {
      console.error('Error fetching standings:', error);
      throw error;
    }
  }

  /**
   * Create a basic team object when full data is not available
   */
  private createBasicTeam(teamData: { id: number; name: string; logo: string }): Team {
    return {
      id: teamData.id.toString(),
      name: teamData.name,
      shortName: teamData.name.substring(0, 3).toUpperCase(),
      logo: teamData.logo,
      country: '',
      league: '',
      founded: 0,
      venue: '',
      colors: { primary: '#000000', secondary: '#FFFFFF' },
      stats: {
        matchesPlayed: 0,
        wins: 0,
        draws: 0,
        losses: 0,
        goalsFor: 0,
        goalsAgainst: 0,
        goalDifference: 0,
        points: 0,
        form: [],
        homeRecord: { played: 0, wins: 0, draws: 0, losses: 0 },
        awayRecord: { played: 0, wins: 0, draws: 0, losses: 0 },
      },
    };
  }

  /**
   * Create a basic league object when full data is not available
   */
  private createBasicLeague(leagueData: { id: number; name: string; country: string; logo: string; season: number }): League {
    return {
      id: leagueData.id.toString(),
      name: leagueData.name,
      shortName: leagueData.name.split(' ').map(w => w[0]).join('').toUpperCase(),
      country: leagueData.country,
      logo: leagueData.logo,
      season: `${leagueData.season}/${(leagueData.season + 1).toString().slice(-2)}`,
      type: 'domestic',
      tier: 1,
    };
  }

  /**
   * Clear all caches
   */
  clearCache() {
    cache.leagues.clear();
    cache.teams.clear();
    cache.matches.clear();
  }
}

// Export singleton instance
export const footballDataService = new FootballDataService();
export default footballDataService;

