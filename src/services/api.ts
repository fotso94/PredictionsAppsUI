import {
  ApiResponse,
  PaginatedResponse,
  ErrorResponse,
  Prediction,
  Match,
  League,
  Team,
  Article,
  User,
  SearchParams,
  AccuracyStats,
  DashboardStats
} from '../types';

// API Configuration
const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.predictionsapp.com/v1';

class ApiService {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;

    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    // Add authentication token if available
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers = {
        ...config.headers,
        Authorization: `Bearer ${token}`,
      };
    }

    try {
      const response = await fetch(url, config);

      if (!response.ok) {
        const errorData: ErrorResponse = await response.json();
        throw new Error(errorData.error.message || 'API request failed');
      }

      const data: ApiResponse<T> = await response.json();

      if (!data.success) {
        throw new Error(data.message || 'API request failed');
      }

      return data.data;
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }

  // Predictions API
  async getPredictions(params?: SearchParams): Promise<PaginatedResponse<Prediction>> {
    const queryParams = new URLSearchParams();

    if (params?.query) queryParams.append('query', params.query);
    if (params?.page) queryParams.append('page', params.page.toString());
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.sortBy) queryParams.append('sortBy', params.sortBy);
    if (params?.sortOrder) queryParams.append('sortOrder', params.sortOrder);

    // Add filters
    if (params?.filters) {
      if (params.filters.leagues?.length) {
        queryParams.append('leagues', params.filters.leagues.join(','));
      }
      if (params.filters.markets?.length) {
        queryParams.append('markets', params.filters.markets.join(','));
      }
      if (params.filters.confidence?.length) {
        queryParams.append('confidence', params.filters.confidence.join(','));
      }
      if (params.filters.dateRange) {
        queryParams.append('dateStart', params.filters.dateRange.start);
        queryParams.append('dateEnd', params.filters.dateRange.end);
      }
    }

    const queryString = queryParams.toString();
    const endpoint = `/predictions${queryString ? `?${queryString}` : ''}`;

    return this.request<PaginatedResponse<Prediction>>(endpoint);
  }

  async getTodaysPredictions(): Promise<Prediction[]> {
    return this.request<Prediction[]>('/predictions/today');
  }

  async getTomorrowsPredictions(): Promise<Prediction[]> {
    return this.request<Prediction[]>('/predictions/tomorrow');
  }

  async getPredictionById(id: string): Promise<Prediction> {
    return this.request<Prediction>(`/predictions/${id}`);
  }

  // Matches API
  async getMatches(params?: SearchParams): Promise<PaginatedResponse<Match>> {
    const queryParams = new URLSearchParams();

    if (params?.page) queryParams.append('page', params.page.toString());
    if (params?.limit) queryParams.append('limit', params.limit.toString());

    const queryString = queryParams.toString();
    const endpoint = `/matches${queryString ? `?${queryString}` : ''}`;

    return this.request<PaginatedResponse<Match>>(endpoint);
  }

  async getMatchById(id: string): Promise<Match> {
    return this.request<Match>(`/matches/${id}`);
  }

  async getUpcomingMatches(): Promise<Match[]> {
    return this.request<Match[]>('/matches/upcoming');
  }

  // Leagues API
  async getLeagues(): Promise<League[]> {
    return this.request<League[]>('/leagues');
  }

  async getLeagueById(id: string): Promise<League> {
    return this.request<League>(`/leagues/${id}`);
  }

  async getLeagueBySlug(slug: string): Promise<League> {
    return this.request<League>(`/leagues/slug/${slug}`);
  }

  async getLeagueMatches(leagueId: string, params?: SearchParams): Promise<PaginatedResponse<Match>> {
    const queryParams = new URLSearchParams();

    if (params?.page) queryParams.append('page', params.page.toString());
    if (params?.limit) queryParams.append('limit', params.limit.toString());

    const queryString = queryParams.toString();
    const endpoint = `/leagues/${leagueId}/matches${queryString ? `?${queryString}` : ''}`;

    return this.request<PaginatedResponse<Match>>(endpoint);
  }

  // Teams API
  async getTeams(): Promise<Team[]> {
    return this.request<Team[]>('/teams');
  }

  async getTeamById(id: string): Promise<Team> {
    return this.request<Team>(`/teams/${id}`);
  }

  async getTeamMatches(teamId: string): Promise<Match[]> {
    return this.request<Match[]>(`/teams/${teamId}/matches`);
  }

  // Articles API
  async getArticles(params?: SearchParams): Promise<PaginatedResponse<Article>> {
    const queryParams = new URLSearchParams();

    if (params?.query) queryParams.append('query', params.query);
    if (params?.page) queryParams.append('page', params.page.toString());
    if (params?.limit) queryParams.append('limit', params.limit.toString());

    const queryString = queryParams.toString();
    const endpoint = `/articles${queryString ? `?${queryString}` : ''}`;

    return this.request<PaginatedResponse<Article>>(endpoint);
  }

  async getArticleBySlug(slug: string): Promise<Article> {
    return this.request<Article>(`/articles/slug/${slug}`);
  }

  async getFeaturedArticles(): Promise<Article[]> {
    return this.request<Article[]>('/articles/featured');
  }

  // Statistics API
  async getAccuracyStats(): Promise<AccuracyStats> {
    return this.request<AccuracyStats>('/statistics/accuracy');
  }

  async getDashboardStats(): Promise<DashboardStats> {
    return this.request<DashboardStats>('/statistics/dashboard');
  }

  // Authentication API
  async login(email: string, password: string): Promise<{ user: User; token: string }> {
    const response = await this.request<{ user: User; token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });

    // Store token in localStorage
    localStorage.setItem('auth_token', response.token);
    localStorage.setItem('user', JSON.stringify(response.user));

    return response;
  }

  async register(userData: {
    email: string;
    password: string;
    firstName: string;
    lastName: string;
  }): Promise<{ user: User; token: string }> {
    const response = await this.request<{ user: User; token: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(userData),
    });

    // Store token in localStorage
    localStorage.setItem('auth_token', response.token);
    localStorage.setItem('user', JSON.stringify(response.user));

    return response;
  }

  async logout(): Promise<void> {
    await this.request<void>('/auth/logout', {
      method: 'POST',
    });

    // Clear stored data
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  async refreshToken(): Promise<{ token: string }> {
    const response = await this.request<{ token: string }>('/auth/refresh', {
      method: 'POST',
    });

    localStorage.setItem('auth_token', response.token);
    return response;
  }

  // User API
  async updateProfile(userData: Partial<User>): Promise<User> {
    return this.request<User>('/user/profile', {
      method: 'PUT',
      body: JSON.stringify(userData),
    });
  }

  async getUserPredictions(userId?: string): Promise<PaginatedResponse<Prediction>> {
    const endpoint = userId ? `/users/${userId}/predictions` : '/user/predictions';
    return this.request<PaginatedResponse<Prediction>>(endpoint);
  }

  // Search API
  async search(query: string, type?: 'predictions' | 'matches' | 'teams' | 'leagues'): Promise<{
    predictions: Prediction[];
    matches: Match[];
    teams: Team[];
    leagues: League[];
  }> {
    const queryParams = new URLSearchParams({ query });
    if (type) queryParams.append('type', type);

    return this.request(`/search?${queryParams.toString()}`);
  }

  // Subscription API
  async subscribe(email: string): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>('/newsletter/subscribe', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  // Odds API
  async getMatchOdds(matchId: string): Promise<any> {
    return this.request(`/matches/${matchId}/odds`);
  }

  async getOddsComparison(matchId: string): Promise<any> {
    return this.request(`/odds/compare/${matchId}`);
  }
}

// Create and export a singleton instance
export const apiService = new ApiService();
export default apiService;