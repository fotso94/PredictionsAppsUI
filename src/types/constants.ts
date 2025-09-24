// API endpoints
export const API_ENDPOINTS = {
  // Authentication
  AUTH: {
    LOGIN: '/auth/login',
    REGISTER: '/auth/register',
    LOGOUT: '/auth/logout',
    REFRESH: '/auth/refresh',
    FORGOT_PASSWORD: '/auth/forgot-password',
    RESET_PASSWORD: '/auth/reset-password',
    VERIFY_EMAIL: '/auth/verify-email',
    RESEND_VERIFICATION: '/auth/resend-verification',
  },
  
  // Matches
  MATCHES: {
    BASE: '/matches',
    BY_ID: (id: string) => `/matches/${id}`,
    BY_DATE: (date: string) => `/matches/date/${date}`,
    BY_LEAGUE: (leagueId: string) => `/matches/league/${leagueId}`,
    BY_TEAM: (teamId: string) => `/matches/team/${teamId}`,
    LIVE: '/matches/live',
    UPCOMING: '/matches/upcoming',
    SEARCH: '/matches/search',
  },
  
  // Predictions
  PREDICTIONS: {
    BASE: '/predictions',
    BY_ID: (id: string) => `/predictions/${id}`,
    BY_MATCH: (matchId: string) => `/predictions/match/${matchId}`,
    BY_TYPE: (type: string) => `/predictions/type/${type}`,
    TODAY: '/predictions/today',
    TOMORROW: '/predictions/tomorrow',
    FEATURED: '/predictions/featured',
    PREDICTION_OF_DAY: '/predictions/prediction-of-day',
  },
  
  // Teams
  TEAMS: {
    BASE: '/teams',
    BY_ID: (id: string) => `/teams/${id}`,
    BY_LEAGUE: (leagueId: string) => `/teams/league/${leagueId}`,
    BY_COUNTRY: (country: string) => `/teams/country/${country}`,
    SEARCH: '/teams/search',
    STATS: (id: string) => `/teams/${id}/stats`,
    FIXTURES: (id: string) => `/teams/${id}/fixtures`,
    RESULTS: (id: string) => `/teams/${id}/results`,
  },
  
  // Leagues
  LEAGUES: {
    BASE: '/leagues',
    BY_ID: (id: string) => `/leagues/${id}`,
    BY_COUNTRY: (country: string) => `/leagues/country/${country}`,
    TABLE: (id: string) => `/leagues/${id}/table`,
    FIXTURES: (id: string) => `/leagues/${id}/fixtures`,
    RESULTS: (id: string) => `/leagues/${id}/results`,
    TOP_SCORERS: (id: string) => `/leagues/${id}/top-scorers`,
    SEARCH: '/leagues/search',
  },
  
  // Users
  USERS: {
    PROFILE: '/users/profile',
    STATS: '/users/stats',
    PREDICTIONS: '/users/predictions',
    FAVORITES: '/users/favorites',
    FAVORITE_TEAMS: '/users/favorites/teams',
    FAVORITE_LEAGUES: '/users/favorites/leagues',
  },
  
  // Statistics
  STATISTICS: {
    OVERALL: '/statistics/overall',
    LEAGUE: (id: string) => `/statistics/league/${id}`,
    TEAM: (id: string) => `/statistics/team/${id}`,
    PREDICTIONS: '/statistics/predictions',
    ACCURACY: '/statistics/accuracy',
    PROFIT: '/statistics/profit',
    TRENDING: '/statistics/trending',
    POPULAR_LEAGUES: '/statistics/popular/leagues',
    POPULAR_TEAMS: '/statistics/popular/teams',
  },
  
  // Notifications
  NOTIFICATIONS: {
    BASE: '/notifications',
    MARK_READ: (id: string) => `/notifications/${id}/read`,
    MARK_ALL_READ: '/notifications/mark-all-read',
    DELETE: (id: string) => `/notifications/${id}`,
    UNREAD_COUNT: '/notifications/unread-count',
    SETTINGS: '/notifications/settings',
  },
} as const;

// Prediction types
export const PREDICTION_TYPES = {
  '1X2': '1x2',
  'OVER_UNDER': 'over_under',
  'BTTS': 'btts',
  'CORRECT_SCORE': 'correct_score',
  'DOUBLE_CHANCE': 'double_chance',
  'HANDICAP': 'handicap',
  'CORNERS': 'corners',
  'CARDS': 'cards',
} as const;

// Match statuses
export const MATCH_STATUSES = {
  SCHEDULED: 'scheduled',
  LIVE: 'live',
  HALFTIME: 'halftime',
  FINISHED: 'finished',
  POSTPONED: 'postponed',
  CANCELLED: 'cancelled',
} as const;

// User roles
export const USER_ROLES = {
  USER: 'user',
  PREMIUM: 'premium',
  VIP: 'vip',
  ADMIN: 'admin',
} as const;

// Subscription types
export const SUBSCRIPTION_TYPES = {
  FREE: 'free',
  BASIC: 'basic',
  PREMIUM: 'premium',
  VIP: 'vip',
} as const;

// Prediction statuses
export const PREDICTION_STATUSES = {
  PENDING: 'pending',
  WON: 'won',
  LOST: 'lost',
  VOID: 'void',
  HALF_WON: 'half_won',
  HALF_LOST: 'half_lost',
} as const;

// Notification types
export const NOTIFICATION_TYPES = {
  INFO: 'info',
  SUCCESS: 'success',
  WARNING: 'warning',
  ERROR: 'error',
} as const;

// Theme options
export const THEMES = {
  LIGHT: 'light',
  DARK: 'dark',
  SYSTEM: 'system',
} as const;

// Supported languages
export const LANGUAGES = {
  EN: 'en',
  ES: 'es',
  FR: 'fr',
  DE: 'de',
  IT: 'it',
  PT: 'pt',
} as const;

// Supported currencies
export const CURRENCIES = {
  USD: 'USD',
  EUR: 'EUR',
  GBP: 'GBP',
  NGN: 'NGN',
  CAD: 'CAD',
  AUD: 'AUD',
} as const;

// Time zones
export const TIMEZONES = {
  UTC: 'UTC',
  EST: 'America/New_York',
  PST: 'America/Los_Angeles',
  GMT: 'Europe/London',
  CET: 'Europe/Paris',
  WAT: 'Africa/Lagos',
} as const;

// Chart colors
export const CHART_COLORS = {
  PRIMARY: '#0ea5e9',
  SUCCESS: '#22c55e',
  DANGER: '#ef4444',
  WARNING: '#f59e0b',
  INFO: '#3b82f6',
  SECONDARY: '#6b7280',
} as const;

// Default pagination
export const DEFAULT_PAGINATION = {
  PAGE: 1,
  LIMIT: 20,
  MAX_LIMIT: 100,
} as const;

// Cache keys
export const CACHE_KEYS = {
  USER: 'user',
  TOKEN: 'token',
  PREFERENCES: 'preferences',
  FAVORITES: 'favorites',
  RECENT_SEARCHES: 'recent_searches',
  THEME: 'theme',
  LANGUAGE: 'language',
} as const;

// Local storage keys
export const STORAGE_KEYS = {
  AUTH_TOKEN: 'auth_token',
  REFRESH_TOKEN: 'refresh_token',
  USER_DATA: 'user_data',
  PREFERENCES: 'user_preferences',
  THEME: 'app_theme',
  LANGUAGE: 'app_language',
  FAVORITES: 'user_favorites',
} as const;

// Error codes
export const ERROR_CODES = {
  UNAUTHORIZED: 'UNAUTHORIZED',
  FORBIDDEN: 'FORBIDDEN',
  NOT_FOUND: 'NOT_FOUND',
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  SERVER_ERROR: 'SERVER_ERROR',
  NETWORK_ERROR: 'NETWORK_ERROR',
  TIMEOUT: 'TIMEOUT',
} as const;

// HTTP status codes
export const HTTP_STATUS = {
  OK: 200,
  CREATED: 201,
  NO_CONTENT: 204,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  UNPROCESSABLE_ENTITY: 422,
  INTERNAL_SERVER_ERROR: 500,
  BAD_GATEWAY: 502,
  SERVICE_UNAVAILABLE: 503,
} as const;

// WebSocket events
export const WS_EVENTS = {
  CONNECT: 'connect',
  DISCONNECT: 'disconnect',
  MATCH_UPDATE: 'match_update',
  PREDICTION_UPDATE: 'prediction_update',
  LIVE_SCORE: 'live_score',
  USER_NOTIFICATION: 'user_notification',
} as const;

// Feature flags
export const FEATURES = {
  LIVE_UPDATES: 'live_updates',
  PUSH_NOTIFICATIONS: 'push_notifications',
  DARK_MODE: 'dark_mode',
  ANALYTICS: 'analytics',
  SOCIAL_SHARING: 'social_sharing',
  EXPORT_DATA: 'export_data',
} as const;
