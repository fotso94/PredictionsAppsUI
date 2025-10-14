import apiClient from './api-client';

const SUBSCRIPTION_BASE_URL = '/api/v1/subscriptions';

/**
 * Subscription Types
 */
export interface SubscriptionFeatures {
  daily_predictions: number | null;
  markets: string[];
  history_days: number | null;
  confidence_visible: boolean;
  expert_predictions: boolean;
  advanced_analytics: boolean;
  api_access: boolean;
  priority_support: boolean;
}

export interface SubscriptionResponse {
  subscription_id: string;
  user_id: string;
  tier: string;
  tier_name: string;
  status: string;
  price: number;
  currency: string;
  billing_period: string;
  features: SubscriptionFeatures;
  starts_at: string;
  ends_at: string | null;
  usage?: {
    predictions_today: number;
    predictions_limit: number | null;
    predictions_remaining: number | null;
  };
}

export interface SubscriptionTier {
  tier: string;
  name: string;
  description: string;
  price: number;
  currency: string;
  billing_period: string;
  features: SubscriptionFeatures;
  is_current: boolean;
  is_popular: boolean;
  savings_percentage: number;
}

export interface UpdateSubscriptionRequest {
  new_tier: 'free' | 'basic' | 'premium' | 'pro';
}

export interface UpdateSubscriptionResponse {
  subscription: SubscriptionResponse;
  message: string;
}

/**
 * Subscription Service
 * Handles all subscription-related API calls
 */
export const subscriptionService = {
  /**
   * Get current user's subscription
   */
  getCurrentSubscription: async (): Promise<SubscriptionResponse> => {
    const response = await apiClient.get<SubscriptionResponse>(
      `${SUBSCRIPTION_BASE_URL}/me`
    );
    return response.data;
  },

  /**
   * Update subscription tier (upgrade/downgrade)
   */
  updateSubscription: async (
    data: UpdateSubscriptionRequest
  ): Promise<UpdateSubscriptionResponse> => {
    const response = await apiClient.put<UpdateSubscriptionResponse>(
      `${SUBSCRIPTION_BASE_URL}/me`,
      data
    );
    return response.data;
  },

  /**
   * Get all available subscription tiers
   */
  getSubscriptionTiers: async (): Promise<SubscriptionTier[]> => {
    const response = await apiClient.get<SubscriptionTier[]>(
      `${SUBSCRIPTION_BASE_URL}/tiers`
    );
    return response.data;
  },
};

