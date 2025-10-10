import apiClient from './api-client';

const PREDICTION_BASE_URL = '/api/v1/predictions';

/**
 * Prediction Types
 */
export interface PredictionListItem {
  id: string;
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  match_date: string;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  confidence_level: number | null;
  source: string;
  status: string;
  created_at: string;
}

export interface PredictionDetail {
  id: string;
  match_id: string;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  confidence_level: number | null;
  source: string;
  reasoning: string | null;
  key_factors: string[] | null;
  status: string;
  created_at: string;
}

export interface PaginationInfo {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface TierInfo {
  tier: string;
  daily_limit: number | null;
  daily_used: number;
  daily_remaining: number | null;
}

export interface PredictionListResponse {
  predictions: PredictionListItem[];
  pagination: PaginationInfo;
  tier_info: TierInfo;
}

export interface FeedbackRequest {
  rating: number;
  comment?: string;
  is_upvote?: boolean;
  is_downvote?: boolean;
}

export interface FeedbackItem {
  id: string;
  user_id: string;
  username: string;
  rating: number;
  comment: string | null;
  is_upvote: boolean;
  is_downvote: boolean;
  created_at: string;
}

export interface FeedbackSummary {
  average_rating: number;
  total_count: number;
  rating_distribution: Record<string, number>;
  upvote_count: number;
  downvote_count: number;
}

export interface FeedbackListResponse {
  prediction_id: string;
  summary: FeedbackSummary;
  feedback: FeedbackItem[];
  pagination: PaginationInfo;
}

/**
 * Prediction Service
 * Handles all prediction-related API calls
 */
export const predictionService = {
  /**
   * Get list of predictions with pagination
   */
  getPredictions: async (params?: {
    page?: number;
    page_size?: number;
    date_from?: string;
    date_to?: string;
  }): Promise<PredictionListResponse> => {
    const response = await apiClient.get<PredictionListResponse>(
      PREDICTION_BASE_URL,
      { params }
    );
    return response.data;
  },

  /**
   * Get today's predictions
   */
  getTodayPredictions: async (params?: {
    sort_by?: 'confidence' | 'created_at';
  }): Promise<PredictionListResponse> => {
    const response = await apiClient.get<PredictionListResponse>(
      `${PREDICTION_BASE_URL}/today`,
      { params }
    );
    return response.data;
  },

  /**
   * Get prediction detail by ID
   */
  getPredictionDetail: async (predictionId: string): Promise<PredictionDetail> => {
    const response = await apiClient.get<PredictionDetail>(
      `${PREDICTION_BASE_URL}/${predictionId}`
    );
    return response.data;
  },

  /**
   * Submit feedback for a prediction
   */
  submitFeedback: async (
    predictionId: string,
    data: FeedbackRequest
  ): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>(
      `${PREDICTION_BASE_URL}/${predictionId}/feedback`,
      data
    );
    return response.data;
  },

  /**
   * Get feedback for a prediction
   */
  getFeedback: async (
    predictionId: string,
    params?: {
      page?: number;
      page_size?: number;
    }
  ): Promise<FeedbackListResponse> => {
    const response = await apiClient.get<FeedbackListResponse>(
      `${PREDICTION_BASE_URL}/${predictionId}/feedback`,
      { params }
    );
    return response.data;
  },
};

