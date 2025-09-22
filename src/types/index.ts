// Core entity types
export interface Team {
  id: string;
  name: string;
  shortName: string;
  logo: string;
  country: string;
  league: string;
  founded?: number;
  stadium?: string;
  website?: string;
  colors: {
    primary: string;
    secondary: string;
  };
  stats?: TeamStats;
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

export interface League {
  id: string;
  name: string;
  shortName: string;
  country: string;
  logo: string;
  season: string;
  type: 'domestic' | 'international' | 'cup';
  tier: number;
  website?: string;
}

export interface Match {
  id: string;
  homeTeam: Team;
  awayTeam: Team;
  league: League;
  date: string;
  time: string;
  status: MatchStatus;
  venue?: string;
  referee?: string;
  weather?: WeatherCondition;
  odds?: MatchOdds;
  result?: MatchResult;
  stats?: MatchStats;
  h2h?: HeadToHead;
}

export type MatchStatus = 
  | 'scheduled' 
  | 'live' 
  | 'halftime' 
  | 'finished' 
  | 'postponed' 
  | 'cancelled';

export interface MatchResult {
  homeScore: number;
  awayScore: number;
  halftimeScore: {
    home: number;
    away: number;
  };
  extraTime?: {
    home: number;
    away: number;
  };
  penalties?: {
    home: number;
    away: number;
  };
}

export interface MatchOdds {
  homeWin: number;
  draw: number;
  awayWin: number;
  over25: number;
  under25: number;
  btts: number;
  noGoals: number;
  correctScore?: { [key: string]: number };
}

export interface MatchStats {
  possession: {
    home: number;
    away: number;
  };
  shots: {
    home: number;
    away: number;
  };
  shotsOnTarget: {
    home: number;
    away: number;
  };
  corners: {
    home: number;
    away: number;
  };
  fouls: {
    home: number;
    away: number;
  };
  yellowCards: {
    home: number;
    away: number;
  };
  redCards: {
    home: number;
    away: number;
  };
}

export interface HeadToHead {
  totalMatches: number;
  homeWins: number;
  awayWins: number;
  draws: number;
  lastMatches: Match[];
  averageGoals: number;
  bttsPercentage: number;
}

export interface WeatherCondition {
  temperature: number;
  condition: string;
  humidity: number;
  windSpeed: number;
}

// Prediction types
export interface Prediction {
  id: string;
  match: Match;
  predictionType: PredictionType;
  prediction: string;
  confidence: number;
  odds: number;
  reasoning: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
  status: PredictionStatus;
  result?: PredictionResult;
}

export type PredictionType = 
  | '1x2' 
  | 'over_under' 
  | 'btts' 
  | 'correct_score' 
  | 'double_chance' 
  | 'handicap' 
  | 'corners' 
  | 'cards';

export type PredictionStatus = 'pending' | 'won' | 'lost' | 'void' | 'half_won' | 'half_lost';

export interface PredictionResult {
  status: PredictionStatus;
  profit: number;
  stake: number;
  payout: number;
}

// User types
export interface User {
  id: string;
  username: string;
  email: string;
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

export type UserRole = 'user' | 'premium' | 'vip' | 'admin';
export type SubscriptionType = 'free' | 'basic' | 'premium' | 'vip';

export interface UserPreferences {
  favoriteTeams: string[];
  favoriteLeagues: string[];
  notifications: {
    email: boolean;
    push: boolean;
    predictions: boolean;
    results: boolean;
  };
  timezone: string;
  language: string;
  currency: string;
}

export interface UserStats {
  totalPredictions: number;
  correctPredictions: number;
  accuracy: number;
  profit: number;
  roi: number;
  streak: {
    current: number;
    best: number;
    type: 'win' | 'loss';
  };
  monthlyStats: MonthlyStats[];
}

export interface MonthlyStats {
  month: string;
  predictions: number;
  correct: number;
  accuracy: number;
  profit: number;
}

// API Response types
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  error?: string;
  pagination?: PaginationInfo;
}

export interface PaginationInfo {
  page: number;
  limit: number;
  total: number;
  totalPages: number;
  hasNext: boolean;
  hasPrev: boolean;
}

export interface ErrorResponse {
  success: false;
  error: string;
  message: string;
  statusCode: number;
}

// Filter and search types
export interface MatchFilters {
  league?: string[];
  date?: {
    from: string;
    to: string;
  };
  status?: MatchStatus[];
  teams?: string[];
  predictionType?: PredictionType[];
  minOdds?: number;
  maxOdds?: number;
  minConfidence?: number;
}

export interface SearchParams {
  query?: string;
  filters?: MatchFilters;
  sort?: {
    field: string;
    direction: 'asc' | 'desc';
  };
  page?: number;
  limit?: number;
}

// Chart and statistics types
export interface ChartData {
  labels: string[];
  datasets: ChartDataset[];
}

export interface ChartDataset {
  label: string;
  data: number[];
  backgroundColor?: string | string[];
  borderColor?: string | string[];
  borderWidth?: number;
  fill?: boolean;
}

export interface StatCard {
  title: string;
  value: string | number;
  change?: {
    value: number;
    type: 'increase' | 'decrease';
    period: string;
  };
  icon?: string;
  color?: 'primary' | 'success' | 'danger' | 'warning';
}

// Navigation and UI types
export interface NavItem {
  name: string;
  href: string;
  icon?: string;
  children?: NavItem[];
  badge?: string | number;
  external?: boolean;
}

export interface BreadcrumbItem {
  name: string;
  href?: string;
  current: boolean;
}

// Form types
export interface LoginForm {
  email: string;
  password: string;
  rememberMe: boolean;
}

export interface RegisterForm {
  firstName: string;
  lastName: string;
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
  agreeToTerms: boolean;
}

export interface ContactForm {
  name: string;
  email: string;
  subject: string;
  message: string;
}

// Notification types
export interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  action?: {
    label: string;
    href: string;
  };
}

// Settings types
export interface AppSettings {
  theme: 'light' | 'dark' | 'system';
  language: string;
  timezone: string;
  currency: string;
  notifications: {
    email: boolean;
    push: boolean;
    desktop: boolean;
  };
  privacy: {
    profileVisibility: 'public' | 'private';
    showStats: boolean;
    allowMessages: boolean;
  };
}
