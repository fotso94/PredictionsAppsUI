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
    // Deliberately NOT caught here. Swallowing the failure and returning an empty result made the
    // dropdown tell the reader "No results found for Arsenal" when the search had never run — a
    // statement about the world, made from a network error. The caller has an error branch; let it
    // reach it, so a failure reads as a failure.
    return footballDataService.search(query.trim());
  }
}

const searchService = new SearchService();
export default searchService;
