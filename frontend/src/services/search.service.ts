/**
 * Search Service
 * 
 * Handles search functionality for teams and leagues using API-Football
 */

import apiFootballService, { APITeam, APILeague } from './api-football.service';

export interface SearchTeamResult {
  id: number;
  name: string;
  logo: string;
  country: string;
  founded?: number;
}

export interface SearchLeagueResult {
  id: number;
  name: string;
  logo: string;
  country: string;
  type: string;
}

export interface SearchResults {
  teams: SearchTeamResult[];
  leagues: SearchLeagueResult[];
}

class SearchService {
  /**
   * Search for teams using API-Football search endpoint
   * Note: API-Football search parameter cannot be combined with league/season parameters
   */
  async searchTeams(query: string): Promise<SearchTeamResult[]> {
    if (!query || query.length < 3) {
      return [];
    }

    try {
      // Use search parameter alone (cannot combine with league/season)
      const response = await apiFootballService.getTeams({
        search: query,
      });

      if (!response.response) {
        return [];
      }

      // Map and limit results
      const teams = response.response.map((apiTeam: APITeam) => ({
        id: apiTeam.team.id,
        name: apiTeam.team.name,
        logo: apiTeam.team.logo,
        country: apiTeam.team.country,
        founded: apiTeam.team.founded,
      }));

      return teams.slice(0, 10);
    } catch (error) {
      console.error('Error searching teams:', error);
      return [];
    }
  }

  /**
   * Search for leagues using API-Football search endpoint
   * Note: API-Football search parameter cannot be combined with current parameter
   */
  async searchLeagues(query: string): Promise<SearchLeagueResult[]> {
    if (!query || query.length < 3) {
      return [];
    }

    try {
      // Use search parameter alone (cannot combine with current)
      const response = await apiFootballService.getLeagues({
        search: query,
      });

      if (!response.response) {
        return [];
      }

      // Map and limit results
      const leagues = response.response.map((apiLeague: APILeague) => ({
        id: apiLeague.league.id,
        name: apiLeague.league.name,
        logo: apiLeague.league.logo,
        country: apiLeague.country.name,
        type: apiLeague.league.type,
      }));

      return leagues.slice(0, 10);
    } catch (error) {
      console.error('Error searching leagues:', error);
      return [];
    }
  }

  /**
   * Search for both teams and leagues simultaneously
   */
  async search(query: string): Promise<SearchResults> {
    if (!query || query.length < 3) {
      return { teams: [], leagues: [] };
    }

    try {
      // Execute both searches in parallel
      const [teams, leagues] = await Promise.all([
        this.searchTeams(query),
        this.searchLeagues(query),
      ]);

      return { teams, leagues };
    } catch (error) {
      console.error('Error performing search:', error);
      return { teams: [], leagues: [] };
    }
  }
}

// Export singleton instance
const searchService = new SearchService();
export default searchService;

