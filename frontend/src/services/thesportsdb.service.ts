/**
 * TheSportsDB V1 API Service
 * 
 * This service handles all interactions with TheSportsDB V1 API
 * Documentation: https://www.thesportsdb.com/api/v1/json/773015/
 * 
 * V1 API uses API key in URL path (browser-friendly, no CORS issues)
 * Premium Account: 100 requests/minute
 */

import axios, { AxiosInstance, AxiosError } from 'axios';

// API Configuration
const API_CONFIG = {
  apiKey: '773015',
  baseURL: 'https://www.thesportsdb.com/api/v1/json/773015',
  timeout: 10000,
};

// TheSportsDB Response Types
export interface TheSportsDBResponse<T> {
  [key: string]: T;
}

export interface DBLeague {
  idLeague: string;
  strLeague: string;
  strSport: string;
  strLeagueAlternate: string;
  strCountry: string;
  strBadge: string;
  strLogo: string;
  strDescriptionEN: string;
  intFormedYear: string;
  strGender: string;
  strWebsite: string;
}

export interface DBTeam {
  idTeam: string;
  strTeam: string;
  strTeamShort: string;
  strAlternate: string;
  intFormedYear: string;
  strSport: string;
  strLeague: string;
  strStadium: string;
  strStadiumLocation: string;
  intStadiumCapacity: string;
  strDescriptionEN: string;
  strCountry: string;
  strBadge: string;  // Team badge/logo URL
  strLogo: string;   // Alternative logo URL
  strTeamBadge?: string;  // Legacy field (not always present)
  strTeamLogo?: string;   // Legacy field (not always present)
  strTeamJersey: string;
  strWebsite: string;
}

export interface DBEvent {
  idEvent: string;
  strEvent: string;
  strEventAlternate: string;
  strFilename: string;
  strSport: string;
  idLeague: string;
  strLeague: string;
  strSeason: string;
  strDescriptionEN: string;
  strHomeTeam: string;
  strAwayTeam: string;
  intHomeScore: string | null;
  intAwayScore: string | null;
  intRound: string;
  strTimestamp: string;
  dateEvent: string;
  strDate: string;
  strTime: string;
  strTimeLocal: string;
  idHomeTeam: string;
  idAwayTeam: string;
  strResult: string | null;
  strVenue: string;
  strCountry: string;
  strCity: string;
  strPoster: string;
  strSquare: string;
  strThumb: string;
  strBanner: string;
  strStatus: string;
  strPostponed: string;
}

export interface DBStanding {
  idStanding: string;
  intRank: string;
  idTeam: string;
  strTeam: string;
  strBadge: string;  // Team badge URL (correct field name from API)
  strTeamBadge?: string;  // Legacy field (not used in standings)
  idLeague: string;
  strLeague: string;
  strSeason: string;
  strForm: string;
  strDescription: string;
  intPlayed: string;
  intWin: string;
  intDraw: string;
  intLoss: string;
  intGoalsFor: string;
  intGoalsAgainst: string;
  intGoalDifference: string;
  intPoints: string;
  dateUpdated: string;
}

export interface DBPlayer {
  idPlayer: string;
  idTeam: string;
  strPlayer: string;
  strTeam: string;
  strNationality: string;
  strPosition: string;
  strThumb: string;
  strCutout: string;
  strBanner: string;
  dateBorn: string;
  strNumber: string;
  strHeight: string;
  strWeight: string;
  strDescriptionEN: string;
}

class TheSportsDBService {
  private api: AxiosInstance;

  constructor() {
    this.api = axios.create({
      baseURL: API_CONFIG.baseURL,
      timeout: API_CONFIG.timeout,
      headers: {
        'Accept': 'application/json',
      },
    });

    // Add response interceptor for error handling
    this.api.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        console.error('TheSportsDB Error:', error.response?.data || error.message);
        throw this.handleError(error);
      }
    );
  }

  private handleError(error: AxiosError): Error {
    if (error.response) {
      const status = error.response.status;
      const data = error.response.data as any;
      
      if (status === 429) {
        return new Error('API rate limit exceeded (100 req/min). Please try again later.');
      } else if (status === 401 || status === 403) {
        return new Error('API authentication failed. Please check your API key.');
      } else if (data?.Message) {
        return new Error(`API Error: ${data.Message}`);
      }
      
      return new Error(`API Error: ${status} - ${error.message}`);
    } else if (error.request) {
      return new Error('No response from API. Please check your internet connection.');
    } else {
      return new Error(`Request Error: ${error.message}`);
    }
  }

  /**
   * Get all leagues
   */
  async getAllLeagues() {
    const response = await this.api.get<TheSportsDBResponse<DBLeague[]>>('/all_leagues.php');
    return response.data;
  }

  /**
   * Get all teams in a league by league name
   */
  async getTeamsByLeagueName(leagueName: string) {
    const response = await this.api.get<TheSportsDBResponse<DBTeam[]>>('/search_all_teams.php', {
      params: { l: leagueName }
    });
    return response.data;
  }

  /**
   * Get league standings
   */
  async getStandings(leagueId: string, season: string) {
    const response = await this.api.get<TheSportsDBResponse<DBStanding[]>>('/lookuptable.php', {
      params: { l: leagueId, s: season }
    });
    return response.data;
  }

  /**
   * Get full season schedule for a league
   */
  async getSeasonSchedule(leagueId: string, season: string) {
    const response = await this.api.get<TheSportsDBResponse<DBEvent[]>>('/eventsseason.php', {
      params: { id: leagueId, s: season }
    });
    return response.data;
  }

  /**
   * Get events by date
   */
  async getEventsByDate(date: string, sport: string = 'Soccer') {
    const response = await this.api.get<TheSportsDBResponse<DBEvent[]>>('/eventsday.php', {
      params: { d: date, s: sport }
    });
    return response.data;
  }

  /**
   * Get next events for a league
   */
  async getNextLeagueEvents(leagueId: string) {
    const response = await this.api.get<TheSportsDBResponse<DBEvent[]>>('/eventsnextleague.php', {
      params: { id: leagueId }
    });
    return response.data;
  }

  /**
   * Get previous events for a league
   */
  async getPreviousLeagueEvents(leagueId: string) {
    const response = await this.api.get<TheSportsDBResponse<DBEvent[]>>('/eventspastleague.php', {
      params: { id: leagueId }
    });
    return response.data;
  }

  /**
   * Get next events for a team
   */
  async getNextTeamEvents(teamId: string) {
    const response = await this.api.get<TheSportsDBResponse<DBEvent[]>>('/eventsnext.php', {
      params: { id: teamId }
    });
    return response.data;
  }

  /**
   * Get previous events for a team
   */
  async getPreviousTeamEvents(teamId: string) {
    const response = await this.api.get<TheSportsDBResponse<DBEvent[]>>('/eventslast.php', {
      params: { id: teamId }
    });
    return response.data;
  }

  /**
   * Lookup league details
   */
  async lookupLeague(leagueId: string) {
    const response = await this.api.get<TheSportsDBResponse<DBLeague[]>>('/lookupleague.php', {
      params: { id: leagueId }
    });
    return response.data;
  }

  /**
   * Lookup team details
   */
  async lookupTeam(teamId: string) {
    const response = await this.api.get<TheSportsDBResponse<DBTeam[]>>('/lookupteam.php', {
      params: { id: teamId }
    });
    return response.data;
  }

  /**
   * Lookup event details
   */
  async lookupEvent(eventId: string) {
    const response = await this.api.get<TheSportsDBResponse<DBEvent[]>>('/lookupevent.php', {
      params: { id: eventId }
    });
    return response.data;
  }

  /**
   * Get all players for a team
   */
  async getTeamPlayers(teamId: string) {
    const response = await this.api.get<TheSportsDBResponse<DBPlayer[]>>('/lookup_all_players.php', {
      params: { id: teamId }
    });
    return response.data;
  }

  /**
   * Search for teams
   */
  async searchTeams(teamName: string) {
    const response = await this.api.get<TheSportsDBResponse<DBTeam[]>>('/searchteams.php', {
      params: { t: teamName }
    });
    return response.data;
  }

  /**
   * Search for players
   */
  async searchPlayers(playerName: string) {
    const response = await this.api.get<TheSportsDBResponse<DBPlayer[]>>('/searchplayers.php', {
      params: { p: playerName }
    });
    return response.data;
  }
}

// Export singleton instance
export const theSportsDBService = new TheSportsDBService();
export default theSportsDBService;

