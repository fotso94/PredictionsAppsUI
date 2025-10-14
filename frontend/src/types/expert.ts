/**
 * Expert Prediction Types
 * TypeScript interfaces for Expert API endpoints (KAN-154)
 */

/**
 * Prediction source enumeration
 */
export enum PredictionSource {
  ML_BASELINE = 'ml_baseline',
  EXPERT_OVERRIDE = 'expert_override',
  EXPERT_MANUAL = 'expert_manual',
  ADMIN_MANUAL = 'admin_manual',
  LLM_GENERATED = 'llm_generated',
  API_FOOTBALL_BASELINE = 'api_football_baseline',
  DEFAULT_RANDOMIZED = 'default_randomized',
}

/**
 * Prediction status enumeration
 */
export enum PredictionStatus {
  PENDING = 'pending',
  UNDER_REVIEW = 'under_review',
  APPROVED = 'approved',
  PUBLISHED = 'published',
  ARCHIVED = 'archived',
  REJECTED = 'rejected',
}

/**
 * Request: Create manual expert prediction
 */
export interface ExpertPredictionCreateRequest {
  match_id: string;
  home_win_prob: number; // 0-1
  draw_prob: number; // 0-1
  away_win_prob: number; // 0-1
  confidence_score?: number; // 0-1
  reasoning?: string;
  key_factors?: Record<string, any>;
}

/**
 * Request: Override existing prediction
 */
export interface ExpertPredictionOverrideRequest {
  prediction_id: string;
  home_win_prob: number; // 0-1
  draw_prob: number; // 0-1
  away_win_prob: number; // 0-1
  confidence_score?: number; // 0-1
  reasoning: string; // Required, min 10 chars
  key_factors?: Record<string, any>;
}

/**
 * Request: Update existing prediction
 */
export interface ExpertPredictionUpdateRequest {
  home_win_prob: number; // 0-1
  draw_prob: number; // 0-1
  away_win_prob: number; // 0-1
  confidence_score?: number; // 0-1
  reasoning?: string;
  key_factors?: Record<string, any>;
}

/**
 * Match details for prediction responses
 */
export interface MatchDetails {
  home_team_name: string;
  away_team_name: string;
  home_team_logo: string | null;
  away_team_logo: string | null;
  league_name: string | null;
  match_date: string | null;
  external_match_id: string | null;
}

/**
 * User details for prediction responses
 */
export interface UserDetails {
  username: string;
  first_name: string | null;
  last_name: string | null;
}

/**
 * Response: Expert prediction
 */
export interface ExpertPredictionResponse {
  id: string;
  match_id: string;
  source: PredictionSource;
  priority_level: number;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  confidence_score: number;
  reasoning: string | null;
  key_factors: Record<string, any> | null;
  status: PredictionStatus;
  created_by: string;
  created_at: string;
  published_at: string | null;
  superseded_by: string | null;

  // Enhanced fields
  match_details?: MatchDetails;
  user_details?: UserDetails;
}

/**
 * Review queue item
 */
export interface ReviewQueueItem {
  prediction_id: string;
  match_id: string;
  match_details: {
    home_team: string;
    away_team: string;
    league: string;
    match_date: string;
  };
  source: PredictionSource;
  created_by: string;
  expert_name: string | null;
  created_at: string;
  status: PredictionStatus;
  requires_approval: boolean;
}

/**
 * Expert performance metrics
 */
export interface ExpertPerformanceMetrics {
  expert_id: string;
  expert_name: string;
  total_predictions: number;
  published_predictions: number;
  pending_predictions: number;
  accuracy_rate: number | null;
  average_confidence: number;
  predictions_by_league: Record<string, number>;
  recent_predictions: ExpertPredictionResponse[];
  performance_trend: Array<{
    date: string;
    predictions: number;
    accuracy: number;
  }>;
}

/**
 * Prediction source display info
 */
export interface PredictionSourceInfo {
  source: PredictionSource;
  label: string;
  icon: string; // Emoji or icon name
  color: string; // Tailwind color class
  priority: number;
  description: string;
}

/**
 * Prediction source display mapping
 */
export const PREDICTION_SOURCE_INFO: Record<PredictionSource, PredictionSourceInfo> = {
  [PredictionSource.EXPERT_MANUAL]: {
    source: PredictionSource.EXPERT_MANUAL,
    label: 'Expert Manual',
    icon: '👤',
    color: 'text-purple-600',
    priority: 100,
    description: 'Manual prediction created by verified expert',
  },
  [PredictionSource.EXPERT_OVERRIDE]: {
    source: PredictionSource.EXPERT_OVERRIDE,
    label: 'Expert Override',
    icon: '👤',
    color: 'text-purple-600',
    priority: 100,
    description: 'Expert override of ML/API prediction',
  },
  [PredictionSource.ADMIN_MANUAL]: {
    source: PredictionSource.ADMIN_MANUAL,
    label: 'Admin Manual',
    icon: '⚙️',
    color: 'text-red-600',
    priority: 90,
    description: 'Manual prediction created by admin',
  },
  [PredictionSource.LLM_GENERATED]: {
    source: PredictionSource.LLM_GENERATED,
    label: 'AI Generated',
    icon: '🤖',
    color: 'text-blue-600',
    priority: 50,
    description: 'AI-generated prediction using LLM',
  },
  [PredictionSource.ML_BASELINE]: {
    source: PredictionSource.ML_BASELINE,
    label: 'ML Baseline',
    icon: '📊',
    color: 'text-green-600',
    priority: 40,
    description: 'Machine learning baseline prediction',
  },
  [PredictionSource.API_FOOTBALL_BASELINE]: {
    source: PredictionSource.API_FOOTBALL_BASELINE,
    label: 'API-Football',
    icon: '⭐',
    color: 'text-yellow-600',
    priority: 25,
    description: 'Prediction from API-Football service',
  },
  [PredictionSource.DEFAULT_RANDOMIZED]: {
    source: PredictionSource.DEFAULT_RANDOMIZED,
    label: 'Randomized',
    icon: '🎲',
    color: 'text-gray-600',
    priority: 0,
    description: 'Randomized fallback prediction',
  },
};

/**
 * Get prediction source display info
 */
export function getPredictionSourceInfo(source: string): PredictionSourceInfo {
  const sourceEnum = source.toUpperCase() as PredictionSource;
  return PREDICTION_SOURCE_INFO[sourceEnum] || PREDICTION_SOURCE_INFO[PredictionSource.DEFAULT_RANDOMIZED];
}

/**
 * Format confidence score as percentage
 */
export function formatConfidence(confidence: number): string {
  return `${(confidence * 100).toFixed(1)}%`;
}

/**
 * Format probability as percentage
 */
export function formatProbability(probability: number): string {
  return `${(probability * 100).toFixed(1)}%`;
}

/**
 * Get confidence level from score
 */
export function getConfidenceLevel(confidence: number): 'low' | 'medium' | 'high' | 'very-high' {
  if (confidence >= 0.85) return 'very-high';
  if (confidence >= 0.70) return 'high';
  if (confidence >= 0.50) return 'medium';
  return 'low';
}

/**
 * Get confidence color class
 */
export function getConfidenceColor(confidence: number): string {
  const level = getConfidenceLevel(confidence);
  switch (level) {
    case 'very-high':
      return 'text-green-600';
    case 'high':
      return 'text-blue-600';
    case 'medium':
      return 'text-yellow-600';
    case 'low':
      return 'text-red-600';
  }
}

/**
 * Validate probabilities sum to 1.0
 */
export function validateProbabilities(
  homeWin: number,
  draw: number,
  awayWin: number
): { valid: boolean; error?: string } {
  const sum = homeWin + draw + awayWin;
  if (sum < 0.99 || sum > 1.01) {
    return {
      valid: false,
      error: `Probabilities must sum to 1.0 (current sum: ${sum.toFixed(4)})`,
    };
  }
  return { valid: true };
}

/**
 * Validate probability range
 */
export function validateProbabilityRange(value: number): { valid: boolean; error?: string } {
  if (value < 0 || value > 1) {
    return {
      valid: false,
      error: 'Probability must be between 0 and 1',
    };
  }
  return { valid: true };
}

