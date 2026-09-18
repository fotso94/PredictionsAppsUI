/**
 * Search Service
 *
 * Team/competition search for the header search box. Delegates to the active data source
 * (backend /api/v1/teams/search by default, legacy API-Football when VITE_DATA_SOURCE=api-football).
 */

import { footballDataService } from './football-data.service';
import type { SearchLeagueResult, SearchResults, SearchTeamResult } from './match-data-source';

export type { SearchLeagueResult, SearchResults, SearchTeamResult };

const MIN_QUERY_LENGTH = 2;

class SearchService {
  async searchTeams(query: string): Promise<SearchTeamResult[]> {
    return (await this.search(query)).teams;
  }

  async searchLeagues(query: string): Promise<SearchLeagueResult[]> {
    return (await this.search(query)).leagues;
  }

  async search(query: string): Promise<SearchResults> {
    if (!query || query.trim().length < MIN_QUERY_LENGTH) {
      return { teams: [], leagues: [] };
    }
    try {
      return await footballDataService.search(query.trim());
    } catch (error) {
      console.error('Error performing search:', error);
      return { teams: [], leagues: [] };
    }
  }
}

const searchService = new SearchService();
export default searchService;
