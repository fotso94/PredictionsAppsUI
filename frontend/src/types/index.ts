// Modules added alongside this file, re-exported here so `@/types` stays the single entry point.
// Type-only re-exports: nothing at runtime, and `isolatedModules` stays satisfied.
// Added, never renamed — every existing export below keeps its name and shape.
import type { MatchBrief, MatchBriefCompact } from './brief';
import type { ExpertPredictionRevision } from './revisions';

/** The evidence brief for one match (src/types/brief.ts). */
export type * from './brief';
/** Preserved earlier versions of an edited expert prediction (src/types/revisions.ts). */
export type * from './revisions';
/** Followed teams/leagues and saved matches (src/types/favourites.ts). */
export type * from './favourites';
/** The measured record counted from settled results (src/types/performance.ts). */
export type * from './performance';

/**
 * Which squad a team row is: club or country, and senior men, senior women or youth.
 *
 * Served verbatim by the backend as `team.team_scope`. It exists because a name alone cannot tell
 * three of these apart — Spain's men, Spain's women and a Spanish club are three rows with one
 * word in them — and because `country` cannot stand in for it: a national team's country is not
 * stored at all, since the only country a national-team competition has is its confederation's
 * territory, and "World" is not a fact about Spain.
 */
export type TeamScope =
  | 'club_senior_men'
  | 'club_senior_women'
  | 'club_youth'
  | 'national_senior_men'
  | 'national_senior_women'
  | 'national_youth';

/** Which squad plays a competition, as the backend's canonical table records it. */
export type SquadCategory = 'senior_men' | 'senior_women' | 'youth';

/** Football's six continental confederations, plus FIFA for worldwide competitions. */
export type Confederation = 'FIFA' | 'CAF' | 'UEFA' | 'AFC' | 'CONCACAF' | 'CONMEBOL' | 'OFC';

// Core Entity Types
export interface Team {
  id: string;
  name: string;
  shortName: string;
  logo: string;
  country: string;
  /**
   * The squad this row is, when the payload said. Undefined means the payload carries no scope at
   * all — an older backend — which is not the same as "a club", so a caller that has to choose
   * must fall back rather than assert. See src/utils/squads.ts.
   */
  scope?: TeamScope;
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
  /**
   * The compact evidence brief carried on every fixture in a list payload.
   *
   * Undefined means the payload predates the brief (or came from the legacy API-Football source),
   * NOT that the brief is empty — treat it as "not supplied here" and fall back to `predictions`.
   * See src/types/brief.ts.
   */
  briefCompact?: MatchBriefCompact | null;
  /** The full brief. Only the match-detail endpoint supplies it; undefined in every list. */
  brief?: MatchBrief | null;
  /**
   * Preserved earlier versions of the published expert predictions on this fixture, oldest first.
   * Only the match-detail endpoint supplies them. An empty array means "never edited"; undefined
   * means "this payload does not carry the history".
   */
  expertPredictionRevisions?: ExpertPredictionRevision[];
}

/** Availability of a provider forecast; anything but "available" must be shown as such. */
export type ForecastState = 'available' | 'stale' | 'kickoff_passed' | 'unavailable';

export type PredictionSourceKind = 'expert' | 'provider' | 'api-football' | 'default';

export interface PredictionMarkets {
  matchResult: boolean;
  btts: boolean;
  overUnder25: boolean;
  overUnder35: boolean;
  /** The source published an exact-score distribution */
  exactScore: boolean;
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
  /**
   * Countries play this competition, rather than clubs.
   *
   * Written down per competition by the backend and served as `competition.is_national_team`;
   * nothing here derives it from a name, because "National Teams Friendlies", "UEFA Nations
   * League" and "Premier League" share no shape a rule could read.
   *
   * Undefined means the payload does not carry the classification at all, which is a different
   * statement from `false`: see `fixtureKind` in src/utils/squads.ts, which keeps them apart so a
   * fixture whose kind is unknown is never counted as a club fixture by a filter.
   */
  isNationalTeam?: boolean;
  /** The confederation the competition belongs to. Null when the backend does not recognise it. */
  confederation?: Confederation | null;
  /** Which squad plays it. Null when the backend does not recognise the competition. */
  squadCategory?: SquadCategory | null;
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

export interface ForecastAnomaly {
  severity: 'warning' | 'note';
  code: string;
  message: string;
}

export interface MatchPredictions {
  /**
   * 1X2 probabilities in percent (0-100).
   * null means the source published no 1X2 market for this fixture. It must be rendered as
   * unavailable — never as 0% / 0% / 0%, and never filled in from odds, history or any other market.
   */
  outcome: {
    homeWin: number;
    draw: number;
    awayWin: number;
    confidence: ConfidenceLevel;
  } | null;
  /**
   * Null when the source did not supply this market. A half the source omitted stays null: it is
   * never derived as 100 - the other half, because the two need not be complementary.
   */
  bothTeamsToScore: {
    yes: number | null;
    no: number | null;
    confidence: ConfidenceLevel;
  } | null;
  /**
   * Null when the source did not supply this market. Each line the source omitted stays null
   * (only the 2.5 line is common; 3.5 is often absent, and neither half is ever inferred).
   */
  totalGoals: {
    over25: number | null;
    under25: number | null;
    over35: number | null;
    under35: number | null;
    confidence: ConfidenceLevel;
  } | null;
  /** Null when the source did not supply a usable exact-score market */
  correctScore: {
    mostLikely: string;
    probability: number;
    confidence: ConfidenceLevel;
  } | null;
  /**
   * Probability (percent) the provider assigned to every scoreline it did not list — its "other"
   * remainder bucket. Never a scoreline, and never used to renormalise the listed ones.
   */
  exactScoreOther?: number | null;
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
  /**
   * Three distinct provider timestamps, deliberately NOT collapsed into one "generated at":
   *  - modelRunAt: when the provider says its model ran. Null when the provider never said.
   *  - providerUpdatedAt: when the provider last touched the event record.
   *  - fetchedAt: when this installation retrieved it.
   * Presenting any of the last two as the generation time would be a claim the provider never made.
   */
  modelRunAt?: string | null;
  providerUpdatedAt?: string | null;
  fetchedAt?: string | null;
  /** False when the provider published no model-run time: the UI must say the generation time is unknown. */
  generationTimeKnown?: boolean;
  publishedAt?: string | null;
  /** Observations the backend made about the provider payload, reported verbatim and never corrected.
   *  `warning` is a reason to doubt the numbers; `note` is bookkeeping that does not undermine them. */
  anomalies?: ForecastAnomaly[];
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
