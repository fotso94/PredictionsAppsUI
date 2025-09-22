// Core Types
export interface User {
  id: string;
  email: string;
  username: string;
  firstName: string;
  lastName: string;
  avatar?: string;
  isPremium: boolean;
  createdAt: string;
  preferences: UserPreferences;
}

export interface UserPreferences {
  favoriteLeagues: string[];
  defaultMarkets: PredictionMarket[];
  notifications: NotificationSettings;
  timezone: string;
}

export interface NotificationSettings {
  email: boolean;
  push: boolean;
  sms: boolean;
  predictionResults: boolean;
  dailyTips: boolean;
}

// League and Team Types
export interface League {
  id: string;
  name: string;
  country: string;
  countryCode: string;
  logo: string;
  season: string;
  isActive: boolean;
  tier: 1 | 2 | 3; // 1 = Top tier, 2 = Second tier, 3 = Lower tiers
}

export interface Team {
  id: string;
  name: string;
  logo: string;
  country: string;
  leagueId: string;
  form: string; // Recent form like "WWLDW"
  position?: number; // League position
  points?: number;
  goalsFor?: number;
  goalsAgainst?: number;
}

// Match and Prediction Types
export interface Match {
  id: string;
  homeTeam: Team;
  awayTeam: Team;
  league: League;
  dateTime: string;
  status: MatchStatus;
  venue?: string;
  referee?: string;
  weather?: WeatherCondition;
  odds?: MatchOdds;
  statistics?: MatchStatistics;
}

export enum MatchStatus {
  SCHEDULED = 'scheduled',
  LIVE = 'live',
  FINISHED = 'finished',
  POSTPONED = 'postponed',
  CANCELLED = 'cancelled'
}

export interface WeatherCondition {
  temperature: number;
  condition: string;
  humidity: number;
  windSpeed: number;
}

export interface MatchOdds {
  home: number;
  draw: number;
  away: number;
  overUnder25: {
    over: number;
    under: number;
  };
  bothTeamsToScore: {
    yes: number;
    no: number;
  };
}

export interface MatchStatistics {
  homeStats: TeamMatchStats;
  awayStats: TeamMatchStats;
}

export interface TeamMatchStats {
  possession: number;
  shots: number;
  shotsOnTarget: number;
  corners: number;
  fouls: number;
  yellowCards: number;
  redCards: number;
}

// Prediction Types
export interface Prediction {
  id: string;
  match: Match;
  market: PredictionMarket;
  prediction: string;
  confidence: ConfidenceLevel;
  accuracy: number;
  analysis: PredictionAnalysis;
  status: PredictionStatus;
  createdAt: string;
  updatedAt: string;
  result?: PredictionResult;
}

export enum PredictionMarket {
  MATCH_RESULT = '1X2', // Home/Draw/Away
  OVER_UNDER_25 = 'Over/Under 2.5',
  BOTH_TEAMS_TO_SCORE = 'BTTS',
  CORRECT_SCORE = 'Correct Score',
  DOUBLE_CHANCE = 'Double Chance',
  FIRST_HALF_RESULT = '1st Half Result',
  TOTAL_GOALS = 'Total Goals',
  ASIAN_HANDICAP = 'Asian Handicap'
}

export enum ConfidenceLevel {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  VERY_HIGH = 'very_high'
}

export enum PredictionStatus {
  PENDING = 'pending',
  WON = 'won',
  LOST = 'lost',
  VOID = 'void'
}

export interface PredictionAnalysis {
  keyFactors: string[];
  headToHead: HeadToHeadRecord;
  teamForm: {
    home: TeamFormAnalysis;
    away: TeamFormAnalysis;
  };
  injuries: InjuryReport[];
  weatherImpact?: string;
  expertTip: string;
}

export interface HeadToHeadRecord {
  totalMeetings: number;
  homeWins: number;
  draws: number;
  awayWins: number;
  lastMeeting: {
    date: string;
    result: string;
    score: string;
  };
}

export interface TeamFormAnalysis {
  last5Games: string; // "WWLDL"
  goalsScored: number;
  goalsConceded: number;
  cleanSheets: number;
  winPercentage: number;
  homeAwayForm?: string; // For home/away specific form
}

export interface InjuryReport {
  player: string;
  position: string;
  injuryType: string;
  expectedReturn?: string;
  impact: 'low' | 'medium' | 'high';
}

export interface PredictionResult {
  actualResult: string;
  isCorrect: boolean;
  confidence: ConfidenceLevel;
  profit?: number; // If odds were tracked
}

// Statistics and Analytics
export interface AccuracyStats {
  overall: number;
  byMarket: Record<PredictionMarket, number>;
  byLeague: Record<string, number>;
  byConfidence: Record<ConfidenceLevel, number>;
  last30Days: number;
  last7Days: number;
  trend: 'up' | 'down' | 'stable';
}

export interface DashboardStats {
  totalPredictions: number;
  correctPredictions: number;
  accuracy: AccuracyStats;
  todaysPredictions: number;
  activeBets: number;
  profit: number;
  roi: number;
}

// API Response Types
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export interface ErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    details?: any;
  };
  timestamp: string;
}

// Filter and Search Types
export interface PredictionFilters {
  leagues?: string[];
  markets?: PredictionMarket[];
  confidence?: ConfidenceLevel[];
  dateRange?: {
    start: string;
    end: string;
  };
  status?: PredictionStatus[];
}

export interface SearchParams {
  query?: string;
  filters?: PredictionFilters;
  sortBy?: 'date' | 'confidence' | 'accuracy';
  sortOrder?: 'asc' | 'desc';
  page?: number;
  limit?: number;
}

// Component Props Types
export interface LoadingState {
  isLoading: boolean;
  error?: string;
}

export interface ComponentProps {
  className?: string;
  children?: React.ReactNode;
}

// Navigation Types
export interface NavigationItem {
  label: string;
  href: string;
  icon?: string;
  isExternal?: boolean;
  children?: NavigationItem[];
}

// Betting Academy Types
export interface Article {
  id: string;
  title: string;
  slug: string;
  excerpt: string;
  content: string;
  author: {
    name: string;
    avatar: string;
    bio: string;
  };
  category: ArticleCategory;
  tags: string[];
  publishedAt: string;
  readTime: number;
  featuredImage: string;
  isFeature: boolean;
}

export enum ArticleCategory {
  BEGINNER_GUIDE = 'Beginner Guide',
  ADVANCED_STRATEGY = 'Advanced Strategy',
  MARKET_ANALYSIS = 'Market Analysis',
  BANKROLL_MANAGEMENT = 'Bankroll Management',
  PSYCHOLOGY = 'Psychology',
  NEWS = 'News'
}