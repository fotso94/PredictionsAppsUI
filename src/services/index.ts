// Export all mock data
export { mockTeams } from '../data/mockTeams';
export { mockLeagues } from '../data/mockLeagues';
export { mockMatches } from '../data/mockMatches';
export { mockPredictions } from '../data/mockPredictions';
export { mockUser, mockUsers } from '../data/mockUsers';

// Service configuration
export const serviceConfig = {
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:3001/api',
  timeout: 10000,
  retries: 3,
  retryDelay: 1000,
};

// API endpoints (re-export from constants)
export { API_ENDPOINTS } from '../types/constants';
