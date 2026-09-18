// Core Entity Types
export interface Team {
  id: string;
  name: string;
  shortName: string;
  logo: string;
  country: string;
  league: string;
  founded: number;
  venue: string;
  colors: {
    primary: string;
    secondary: string;
  };
  stats: TeamStats;
}

export interface TeamStats {
  matchesPlayed: number;
  wins: number;
  draws: number;
  losses: number;
  goalsFor: number;
  goalsAgainst: number;
  goalDifference: number;
  points: number;
  form: string[]; // Last 5 matches: 'W', 'D', 'L'
  homeRecord: {
    played: number;
    wins: number;
    draws: number;
    losses: number;
  };
  awayRecord: {
    played: number;
    wins: number;
    draws: number;
    losses: number;
  };
}

export interface Match {
  id: string;
  homeTeam: Team;
  awayTeam: Team;
  league: League;
  /** UTC calendar date (YYYY-MM-DD) */
  date: string;
  /** Local kickoff time (HH:mm) */
  time: string;
  /** ISO 8601 UTC kickoff, when known */
  kickoffUtc?: string;
  status: MatchStatus;
  venue: string;
  round: string;
  season: string;
  /** Bookmaker odds. Null when no odds feed is configured (Phase 1 has none). */
  odds: MatchOdds | null;
  /** Primary prediction shown to users: the expert prediction when one exists, otherwise the provider forecast. */
  predictions: MatchPredictions | null;
  /** Published expert prediction (highest priority), separate from any model forecast. */
  expertPrediction?: MatchPredictions | null;
  /** Every published expert prediction (detail pages). */
  expertPredictions?: MatchPredictions[];
  /** Forecast from the configured prediction provider (e.g. GameForecastAPI), never mixed with expert data. */
  providerForecast?: MatchPredictions | null;
  headToHead: HeadToHead;
  result?: MatchResult;
  /** Provenance of the fixture record */
  provider?: string | null;
  externalId?: string | null;
  minute?: string | null;
  lastSyncedAt?: string | null;
}

/** Availability of a provider forecast; anything but "available" must be shown as such. */
export type ForecastState = 'available' | 'stale' | 'kickoff_passed' | 'unavailable';

export type PredictionSourceKind = 'expert' | 'provider' | 'api-football' | 'default';

export interface PredictionMarkets {
  matchResult: boolean;
  btts: boolean;
  overUnder25: boolean;
  overUnder35: boolean;
}

export interface MatchResult {
  homeScore: number;
  awayScore: number;
  halfTimeScore: {
    home: number;
    away: number;
  };
  fullTimeScore: {
    home: number;
    away: number;
  };
  extraTimeScore?: {
    home: number;
    away: number;
  };
  penaltyScore?: {
    home: number;
    away: number;
  };
}

export interface League {
  id: string;
  name: string;
  shortName: string;
  country: string;
  logo: string;
  season: string;
  type: 'domestic' | 'international' | 'cup';
  tier: number;
  standings?: LeagueStanding[];
}

export interface LeagueStanding {
  position: number;
  team: Team;
  matchesPlayed: number;
  wins: number;
  draws: number;
  losses: number;
  goalsFor: number;
  goalsAgainst: number;
  goalDifference: number;
  points: number;
  form: string[];
}

export interface MatchOdds {
  homeWin: number;
  draw: number;
  awayWin: number;
  bothTeamsToScore: {
    yes: number;
    no: number;
  };
  overUnder: {
    over25: number;
    under25: number;
    over35: number;
    under35: number;
  };
  correctScore: {
    [key: string]: number; // "1-0", "2-1", etc.
  };
}

export interface MatchPredictions {
  /** 1X2 probabilities in percent (0-100) */
  outcome: {
    homeWin: number;
    draw: number;
    awayWin: number;
    confidence: ConfidenceLevel;
  };
  /** Null when the source did not supply this market */
  bothTeamsToScore: {
    yes: number;
    no: number;
    confidence: ConfidenceLevel;
  } | null;
  /** Null when the source did not supply this market; over35/under35 null when only the 2.5 line exists */
  totalGoals: {
    over25: number;
    under25: number;
    over35: number | null;
    under35: number | null;
    confidence: ConfidenceLevel;
  } | null;
  /** Null when the source did not supply an exact-score market */
  correctScore: {
    mostLikely: string;
    probability: number;
    confidence: ConfidenceLevel;
  } | null;
  analysis: string;
  keyFactors: string[];
  // Metadata for prediction source
  source?: PredictionSourceKind;
  source_type?: string;
  confidence_score?: number | null;
  priority_level?: number;
  /** Provider name for provider forecasts (e.g. "gameforecast") */
  providerName?: string;
  /** Freshness of a provider forecast */
  state?: ForecastState;
  stateReason?: string | null;
  /** Which markets the source actually supplied */
  markets?: PredictionMarkets;
  /** When the model run / expert publication happened */
  generatedAt?: string | null;
  publishedAt?: string | null;
  /** Provider-reported recommended bets, verbatim */
  recommendedBets?: Record<string, unknown> | null;
  /** How confidently the forecast was linked to this fixture (exact | high) */
  matchConfidence?: string | null;
}

export interface HeadToHead {
  totalMatches: number;
  homeTeamWins: number;
  draws: number;
  awayTeamWins: number;
  lastMatches: Match[];
  averageGoals: {
    home: number;
    away: number;
    total: number;
  };
}

// User and Authentication Types
export interface User {
  id: string;
  email: string;
  username: string;
  firstName: string;
  lastName: string;
  avatar?: string;
  role: UserRole;
  subscription: SubscriptionType;
  preferences: UserPreferences;
  stats: UserStats;
  createdAt: string;
  lastLogin: string;
}

export interface UserPreferences {
  favoriteTeams: string[];
  favoriteLeagues: string[];
  notifications: {
    email: boolean;
    push: boolean;
    predictions: boolean;
    results: boolean;
  };
  theme: 'light' | 'dark' | 'auto';
  language: string;
  timezone: string;
}

export interface UserStats {
  totalPredictions: number;
  correctPredictions: number;
  accuracy: number;
  streak: {
    current: number;
    best: number;
  };
  favoriteMarkets: BettingMarket[];
  monthlyStats: {
    month: string;
    predictions: number;
    correct: number;
    accuracy: number;
  }[];
}

// Prediction and Betting Types
export interface Prediction {
  id: string;
  matchId: string;
  userId?: string;
  market: BettingMarket;
  selection: string;
  odds: number;
  confidence: ConfidenceLevel;
  analysis: string;
  status: PredictionStatus;
  createdAt: string;
  result?: PredictionResult;
}

export interface PredictionResult {
  outcome: 'won' | 'lost' | 'void';
  profit: number;
  settledAt: string;
}

// Enums and Union Types
export type MatchStatus = 
  | 'scheduled' 
  | 'live' 
  | 'halftime' 
  | 'finished' 
  | 'postponed' 
  | 'cancelled';

export type UserRole = 'user' | 'premium' | 'admin';

export type SubscriptionType = 'free' | 'basic' | 'premium' | 'pro';

export type ConfidenceLevel = 'low' | 'medium' | 'high' | 'very-high';

export type BettingMarket = 
  | '1x2' 
  | 'btts' 
  | 'over-under' 
  | 'correct-score' 
  | 'double-chance' 
  | 'handicap';

export type PredictionStatus = 
  | 'pending' 
  | 'won' 
  | 'lost' 
  | 'void' 
  | 'cancelled';

// API Response Types
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  error?: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
    hasNext: boolean;
    hasPrev: boolean;
  };
}

// Component Props Types
export interface LoadingState {
  isLoading: boolean;
  error?: string;
}

export interface FilterOptions {
  leagues?: string[];
  teams?: string[];
  markets?: BettingMarket[];
  confidence?: ConfidenceLevel[];
  dateRange?: {
    start: string;
    end: string;
  };
}

// Chart and Statistics Types
export interface ChartDataPoint {
  label: string;
  value: number;
  color?: string;
}

export interface StatCard {
  title: string;
  value: string | number;
  change?: {
    value: number;
    type: 'increase' | 'decrease';
  };
  icon?: string;
  color?: string;
}

// Navigation and Route Types
export interface NavItem {
  name: string;
  href: string;
  icon?: string;
  badge?: string | number;
  children?: NavItem[];
}

// Form Types
export interface LoginForm {
  email: string;
  password: string;
  rememberMe: boolean;
}

export interface RegisterForm {
  firstName: string;
  lastName: string;
  email: string;
  username: string;
  password: string;
  confirmPassword: string;
  agreeToTerms: boolean;
}

// Notification Types
export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  action?: {
    label: string;
    href: string;
  };
}

// Search and Filter Types
export interface SearchResult {
  type: 'team' | 'league' | 'match';
  id: string;
  title: string;
  subtitle: string;
  image?: string;
  href: string;
}

// Theme and UI Types
export interface ThemeConfig {
  mode: 'light' | 'dark';
  primaryColor: string;
  accentColor: string;
}

// Error Types
export interface AppError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

// Analytics Types
export interface AnalyticsEvent {
  event: string;
  properties?: Record<string, unknown>;
  timestamp: string;
}
