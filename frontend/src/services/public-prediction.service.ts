/**
 * Public Prediction Service
 * Fetches published expert predictions from the backend (no authentication required)
 */

import apiClient from './api-client';

const PREDICTIONS_BASE_URL = '/api/v1/predictions';

export interface PublicPrediction {
  id: string;
  match_id: string;
  external_match_id: string | null;
  source: string;
  priority_level: number;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  confidence_score: number | null;
  reasoning: string | null;
  published_at: string | null;
  match_details: {
    home_team_name: string;
    away_team_name: string;
    home_team_logo: string | null;
    away_team_logo: string | null;
    league_name: string | null;
    match_date: string | null;
  };
}

/**
 * Public Prediction Service
 * Provides methods to fetch published expert predictions
 */
export const publicPredictionService = {
  /**
   * Get published predictions with optional filters
   * 
   * @param params - Query parameters
   * @returns List of published predictions
   */
  getPublishedPredictions: async (params?: {
    match_id?: string;
    external_match_id?: string;
    date?: string;
    limit?: number;
  }): Promise<PublicPrediction[]> => {
    try {
      const response = await apiClient.get<PublicPrediction[]>(
        `${PREDICTIONS_BASE_URL}/published`,
        { params }
      );
      return response.data;
    } catch (error) {
      console.error('Error fetching published predictions:', error);
      return [];
    }
  },

  /**
   * Get the highest priority published prediction for a specific match
   * 
   * @param externalMatchId - External API match ID (e.g., API-Football fixture ID)
   * @returns Single highest priority published prediction, or null if none found
   */
  getPublishedPredictionByMatch: async (
    externalMatchId: string
  ): Promise<PublicPrediction | null> => {
    try {
      const response = await apiClient.get<PublicPrediction>(
        `${PREDICTIONS_BASE_URL}/published/by-match/${externalMatchId}`
      );
      return response.data;
    } catch (error) {
      // Return null if no prediction found (404) or other errors
      return null;
    }
  },

  /**
   * Get published predictions for multiple matches (batch)
   * 
   * @param externalMatchIds - Array of external match IDs
   * @returns Map of external match ID to prediction
   */
  getPublishedPredictionsBatch: async (
    externalMatchIds: string[]
  ): Promise<Map<string, PublicPrediction>> => {
    const predictions = new Map<string, PublicPrediction>();

    // Fetch predictions in parallel
    const promises = externalMatchIds.map(async (matchId) => {
      const prediction = await publicPredictionService.getPublishedPredictionByMatch(matchId);
      if (prediction) {
        predictions.set(matchId, prediction);
      }
    });

    await Promise.all(promises);
    return predictions;
  },

  /**
   * Get published predictions for today's matches
   * 
   * @returns List of published predictions for today
   */
  getTodayPublishedPredictions: async (): Promise<PublicPrediction[]> => {
    const today = new Date().toISOString().split('T')[0];
    return publicPredictionService.getPublishedPredictions({ date: today });
  },

  /**
   * Get published predictions for tomorrow's matches
   * 
   * @returns List of published predictions for tomorrow
   */
  getTomorrowPublishedPredictions: async (): Promise<PublicPrediction[]> => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];
    return publicPredictionService.getPublishedPredictions({ date: tomorrowStr });
  },
};

export default publicPredictionService;

