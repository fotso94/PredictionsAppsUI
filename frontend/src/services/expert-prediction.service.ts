/**
 * Expert Prediction Service
 * Handles all expert prediction-related API calls (KAN-154)
 */

import apiClient from './api-client';
import {
  ExpertPredictionCreateRequest,
  ExpertPredictionOverrideRequest,
  ExpertPredictionUpdateRequest,
  ExpertPredictionResponse,
  ReviewQueueItem,
  ExpertPerformanceMetrics,
} from '../types/expert';

const EXPERT_BASE_URL = '/api/v1/expert';

/**
 * Expert Prediction Service
 * Provides methods for expert users to manage predictions
 */
export const expertPredictionService = {
  /**
   * Create manual expert prediction (KAN-149)
   * 
   * @param data - Prediction data
   * @returns Created prediction
   */
  createManualPrediction: async (
    data: ExpertPredictionCreateRequest
  ): Promise<ExpertPredictionResponse> => {
    const response = await apiClient.post<ExpertPredictionResponse>(
      `${EXPERT_BASE_URL}/predictions/manual`,
      data
    );
    return response.data;
  },

  /**
   * Override existing prediction (KAN-150)
   * 
   * @param data - Override data
   * @returns New expert override prediction
   */
  overridePrediction: async (
    data: ExpertPredictionOverrideRequest
  ): Promise<ExpertPredictionResponse> => {
    const response = await apiClient.post<ExpertPredictionResponse>(
      `${EXPERT_BASE_URL}/predictions/override`,
      data
    );
    return response.data;
  },

  /**
   * Get predictions pending review/approval (KAN-151)
   * 
   * @param params - Query parameters
   * @returns List of pending predictions
   */
  getReviewQueue: async (params?: {
    limit?: number;
    offset?: number;
  }): Promise<ExpertPredictionResponse[]> => {
    const response = await apiClient.get<ExpertPredictionResponse[]>(
      `${EXPERT_BASE_URL}/predictions/review-queue`,
      { params }
    );
    return response.data;
  },

  /**
   * Get expert's own predictions (KAN-152)
   * 
   * @param params - Query parameters
   * @returns List of expert's predictions
   */
  getMyPredictions: async (params?: {
    limit?: number;
    offset?: number;
    status?: string;
  }): Promise<ExpertPredictionResponse[]> => {
    const response = await apiClient.get<ExpertPredictionResponse[]>(
      `${EXPERT_BASE_URL}/predictions/my-predictions`,
      { params }
    );
    return response.data;
  },

  /**
   * Get expert performance analytics (KAN-153)
   * 
   * @returns Expert performance metrics
   */
  getPerformanceMetrics: async (): Promise<ExpertPerformanceMetrics> => {
    const response = await apiClient.get<ExpertPerformanceMetrics>(
      `${EXPERT_BASE_URL}/analytics/performance`
    );
    return response.data;
  },

  /**
   * Get expert dashboard data
   * 
   * @returns Dashboard overview
   */
  getDashboard: async (): Promise<{
    user_id: string;
    role: string;
    is_verified: boolean;
    dashboard_data: {
      total_predictions: number;
      accuracy_rate: number;
      recent_predictions: any[];
    };
  }> => {
    const response = await apiClient.get(
      `${EXPERT_BASE_URL}/dashboard`
    );
    return response.data;
  },

  /**
   * Get ML baseline predictions for a match
   * 
   * @param matchId - Match ID
   * @returns ML baseline prediction
   */
  getMLBaseline: async (matchId: string): Promise<{
    match_id: string;
    ml_baseline: {
      home_win_probability: number;
      draw_probability: number;
      away_win_probability: number;
      model_confidence: number;
      model_version: string;
    };
    expert_can_override: boolean;
  }> => {
    const response = await apiClient.get(
      `${EXPERT_BASE_URL}/ml-baseline`,
      { params: { match_id: matchId } }
    );
    return response.data;
  },

  /**
   * Get advanced analytics
   * 
   * @returns Advanced analytics data
   */
  getAdvancedAnalytics: async (): Promise<{
    user_id: string;
    analytics: {
      prediction_accuracy_by_league: Record<string, number>;
      confidence_calibration: Record<string, number>;
      feature_importance: Record<string, number>;
      model_performance_trends: any[];
    };
  }> => {
    const response = await apiClient.get(
      `${EXPERT_BASE_URL}/analytics/advanced`
    );
    return response.data;
  },

  /**
   * Get expert verification status
   *
   * @returns Verification status
   */
  getVerificationStatus: async (): Promise<{
    user_id: string;
    role: string;
    is_verified: boolean;
    verification_status: string;
    application_date?: string;
    verified_date?: string;
    verified_by?: string;
  }> => {
    const response = await apiClient.get(
      `${EXPERT_BASE_URL}/verification-status`
    );
    return response.data;
  },

  /**
   * Approve a prediction
   *
   * @param predictionId - Prediction ID
   * @returns Approved prediction
   */
  approvePrediction: async (predictionId: string): Promise<ExpertPredictionResponse> => {
    const response = await apiClient.post<ExpertPredictionResponse>(
      `${EXPERT_BASE_URL}/predictions/${predictionId}/approve`
    );
    return response.data;
  },

  /**
   * Reject a prediction
   *
   * @param predictionId - Prediction ID
   * @param reason - Optional reason for rejection
   * @returns Rejected prediction
   */
  rejectPrediction: async (predictionId: string, reason?: string): Promise<ExpertPredictionResponse> => {
    const response = await apiClient.post<ExpertPredictionResponse>(
      `${EXPERT_BASE_URL}/predictions/${predictionId}/reject`,
      { reason }
    );
    return response.data;
  },

  /**
   * Update a prediction
   *
   * @param predictionId - Prediction ID
   * @param data - Update data
   * @returns Updated prediction
   */
  updatePrediction: async (
    predictionId: string,
    data: ExpertPredictionUpdateRequest
  ): Promise<ExpertPredictionResponse> => {
    const response = await apiClient.put<ExpertPredictionResponse>(
      `${EXPERT_BASE_URL}/predictions/${predictionId}`,
      data
    );
    return response.data;
  },

  /**
   * Delete a prediction
   *
   * @param predictionId - Prediction ID
   * @returns Success message
   */
  deletePrediction: async (predictionId: string): Promise<{ message: string; prediction_id: string }> => {
    const response = await apiClient.delete(
      `${EXPERT_BASE_URL}/predictions/${predictionId}`
    );
    return response.data;
  },
};

export default expertPredictionService;

