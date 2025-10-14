/**
 * API-Football Service
 * 
 * This service handles all interactions with the API-Football API (via RapidAPI)
 * Documentation: https://www.api-football.com/documentation-v3
 */

import axios, { AxiosInstance, AxiosError } from 'axios';

// API Configuration
// Using Vite proxy to avoid CORS issues
// In development: requests go through Vite proxy at /api/football
// In production: you'll need to set up a backend proxy or use environment variables
const API_CONFIG = {
  baseURL: import.meta.env.DEV ? '/api/football' : 'https://v3.football.api-sports.io',
  apiKey: '38164887e0ce0b93419671e273fe64c0', // Pro API Key
  timeout: 10000,
};

// API-Football Response Types
export interface APIFootballResponse<T> {
  get: string;
  parameters: Record<string, any>;
  errors: any[];
  results: number;
  paging: {
    current: number;
    total: number;
  };
  response: T;
}

export interface APILeague {
  league: {
    id: number;
    name: string;
    type: string;
    logo: string;
  };
  country: {
    name: string;
    code: string | null;
    flag: string | null;
  };
  seasons: Array<{
    year: number;
    start: string;
    end: string;
    current: boolean;
    coverage: {
      fixtures: {
        events: boolean;
        lineups: boolean;
        statistics_fixtures: boolean;
        statistics_players: boolean;
      };
      standings: boolean;
      players: boolean;
      top_scorers: boolean;
      top_assists: boolean;
      top_cards: boolean;
      injuries: boolean;
      predictions: boolean;
      odds: boolean;
    };
  }>;
}

export interface APITeam {
  team: {
    id: number;
    name: string;
    code: string;
    country: string;
    founded: number;
    national: boolean;
    logo: string;
  };
  venue: {
    id: number;
    name: string;
    address: string;
    city: string;
    capacity: number;
    surface: string;
    image: string;
  };
}

export interface APIFixture {
  fixture: {
    id: number;
    referee: string | null;
    timezone: string;
    date: string;
    timestamp: number;
    periods: {
      first: number | null;
      second: number | null;
    };
    venue: {
      id: number | null;
      name: string | null;
      city: string | null;
    };
    status: {
      long: string;
      short: string;
      elapsed: number | null;
    };
  };
  league: {
    id: number;
    name: string;
    country: string;
    logo: string;
    flag: string | null;
    season: number;
    round: string;
  };
  teams: {
    home: {
      id: number;
      name: string;
      logo: string;
      winner: boolean | null;
    };
    away: {
      id: number;
      name: string;
      logo: string;
      winner: boolean | null;
    };
  };
  goals: {
    home: number | null;
    away: number | null;
  };
  score: {
    halftime: {
      home: number | null;
      away: number | null;
    };
    fulltime: {
      home: number | null;
      away: number | null;
    };
    extratime: {
      home: number | null;
      away: number | null;
    };
    penalty: {
      home: number | null;
      away: number | null;
    };
  };
}

export interface APITeamStatistics {
  league: {
    id: number;
    name: string;
    country: string;
    logo: string;
    flag: string;
    season: number;
  };
  team: {
    id: number;
    name: string;
    logo: string;
  };
  form: string;
  fixtures: {
    played: {
      home: number;
      away: number;
      total: number;
    };
    wins: {
      home: number;
      away: number;
      total: number;
    };
    draws: {
      home: number;
      away: number;
      total: number;
    };
    loses: {
      home: number;
      away: number;
      total: number;
    };
  };
  goals: {
    for: {
      total: {
        home: number;
        away: number;
        total: number;
      };
      average: {
        home: string;
        away: string;
        total: string;
      };
    };
    against: {
      total: {
        home: number;
        away: number;
        total: number;
      };
      average: {
        home: string;
        away: string;
        total: string;
      };
    };
  };
}

export interface APIPrediction {
  predictions: {
    winner: {
      id: number;
      name: string;
      comment: string;
    };
    win_or_draw: boolean;
    under_over: string | null;
    goals: {
      home: string;
      away: string;
    };
    advice: string;
    percent: {
      home: string;
      draw: string;
      away: string;
    };
  };
  league: {
    id: number;
    name: string;
    country: string;
    logo: string;
    flag: string;
    season: number;
  };
  teams: {
    home: {
      id: number;
      name: string;
      logo: string;
      last_5: {
        form: string;
        att: string;
        def: string;
        goals: {
          for: {
            total: number;
            average: string;
          };
          against: {
            total: number;
            average: string;
          };
        };
      };
    };
    away: {
      id: number;
      name: string;
      logo: string;
      last_5: {
        form: string;
        att: string;
        def: string;
        goals: {
          for: {
            total: number;
            average: string;
          };
          against: {
            total: number;
            average: string;
          };
        };
      };
    };
  };
  comparison: {
    form: {
      home: string;
      away: string;
    };
    att: {
      home: string;
      away: string;
    };
    def: {
      home: string;
      away: string;
    };
    poisson_distribution: {
      home: string;
      away: string;
    };
    h2h: {
      home: string;
      away: string;
    };
    goals: {
      home: string;
      away: string;
    };
    total: {
      home: string;
      away: string;
    };
  };
}

class APIFootballService {
  private api: AxiosInstance;

  constructor() {
    // In development, use proxy (no API key header needed - proxy adds it)
    // In production, add API key header directly
    const headers: Record<string, string> = {};
    if (!import.meta.env.DEV) {
      headers['x-apisports-key'] = API_CONFIG.apiKey;
    }

    this.api = axios.create({
      baseURL: API_CONFIG.baseURL,
      timeout: API_CONFIG.timeout,
      headers,
    });

    // Add request interceptor to clean headers (only in production)
    this.api.interceptors.request.use(
      (config) => {
        if (!import.meta.env.DEV && config.headers) {
          // In production, API-Sports only allows specific headers
          const allowedHeaders = ['x-apisports-key'];
          const cleanHeaders: Record<string, string> = {};

          allowedHeaders.forEach(header => {
            const value = config.headers[header];
            if (value) {
              cleanHeaders[header] = value as string;
            }
          });

          config.headers = cleanHeaders as any;
        }

        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );

    // Add response interceptor for error handling
    this.api.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        console.error('API-Football Error:', error.response?.data || error.message);
        throw this.handleError(error);
      }
    );
  }

  private handleError(error: AxiosError): Error {
    if (error.response) {
      // Server responded with error status
      const status = error.response.status;
      const data = error.response.data as any;
      
      if (status === 429) {
        return new Error('API rate limit exceeded. Please try again later.');
      } else if (status === 401 || status === 403) {
        return new Error('API authentication failed. Please check your API key.');
      } else if (data?.errors && Object.keys(data.errors).length > 0) {
        return new Error(`API Error: ${JSON.stringify(data.errors)}`);
      }
      
      return new Error(`API Error: ${status} - ${error.message}`);
    } else if (error.request) {
      // Request made but no response
      return new Error('No response from API. Please check your internet connection.');
    } else {
      // Error in request setup
      return new Error(`Request Error: ${error.message}`);
    }
  }

  /**
   * Get API status and account information
   */
  async getStatus() {
    const response = await this.api.get('/status');
    return response.data;
  }

  /**
   * Get all leagues or filter by specific criteria
   */
  async getLeagues(params?: {
    id?: number;
    name?: string;
    country?: string;
    code?: string;
    season?: number;
    team?: number;
    type?: string;
    current?: boolean;
    search?: string;
  }) {
    const response = await this.api.get<APIFootballResponse<APILeague[]>>('/leagues', { params });
    return response.data;
  }

  /**
   * Get teams by league and season
   */
  async getTeams(params: {
    league: number;
    season: number;
    id?: number;
    name?: string;
    country?: string;
    code?: string;
    venue?: number;
    search?: string;
  }) {
    const response = await this.api.get<APIFootballResponse<APITeam[]>>('/teams', { params });
    return response.data;
  }

  /**
   * Get fixtures by various filters
   */
  async getFixtures(params?: {
    id?: number;
    live?: string;
    date?: string;
    league?: number;
    season?: number;
    team?: number;
    last?: number;
    next?: number;
    from?: string;
    to?: string;
    round?: string;
    status?: string;
    venue?: number;
    timezone?: string;
  }) {
    const response = await this.api.get<APIFootballResponse<APIFixture[]>>('/fixtures', { params });
    return response.data;
  }

  /**
   * Get team statistics for a specific league and season
   */
  async getTeamStatistics(params: {
    league: number;
    season: number;
    team: number;
    date?: string;
  }) {
    const response = await this.api.get<APIFootballResponse<APITeamStatistics>>('/teams/statistics', { params });
    return response.data;
  }

  /**
   * Get predictions for a specific fixture
   */
  async getPredictions(fixtureId: number) {
    const response = await this.api.get<APIFootballResponse<APIPrediction[]>>('/predictions', {
      params: { fixture: fixtureId },
    });
    return response.data;
  }

  /**
   * Get head to head matches between two teams
   */
  async getHeadToHead(params: {
    h2h: string; // Format: "teamId-teamId" e.g., "33-34"
    date?: string;
    league?: number;
    season?: number;
    last?: number;
    next?: number;
    from?: string;
    to?: string;
    status?: string;
    venue?: number;
    timezone?: string;
  }) {
    const response = await this.api.get<APIFootballResponse<APIFixture[]>>('/fixtures/headtohead', { params });
    return response.data;
  }

  /**
   * Get league standings
   */
  async getStandings(params: {
    league: number;
    season: number;
    team?: number;
  }) {
    const response = await this.api.get('/standings', { params });
    return response.data;
  }
}

// Export singleton instance
export const apiFootballService = new APIFootballService();
export default apiFootballService;

