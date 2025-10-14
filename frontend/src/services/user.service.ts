import apiClient from './api-client';

const USER_BASE_URL = '/api/v1/users';

/**
 * User Profile Request/Response Types
 */
export interface UserProfile {
  id: string;
  email: string;
  username: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  user_type: string;
  account_status: string;
  email_verified: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export interface UpdateProfileRequest {
  first_name?: string;
  last_name?: string;
  username?: string;
  avatar_url?: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export interface UpdatePreferencesRequest {
  theme?: 'light' | 'dark' | 'auto';
  email_notifications?: boolean;
  push_notifications?: boolean;
  favorite_teams?: string[];
  favorite_leagues?: string[];
  odds_format?: 'decimal' | 'fractional' | 'american';
  timezone?: string;
  language?: string;
}

export interface MessageResponse {
  message: string;
}

/**
 * User Service
 * Handles all user profile-related API calls
 */
export const userService = {
  /**
   * Get current user's profile
   */
  getProfile: async (): Promise<UserProfile> => {
    const response = await apiClient.get<UserProfile>(`${USER_BASE_URL}/me`);
    return response.data;
  },

  /**
   * Update current user's profile
   */
  updateProfile: async (data: UpdateProfileRequest): Promise<UserProfile> => {
    const response = await apiClient.put<UserProfile>(`${USER_BASE_URL}/me`, data);
    return response.data;
  },

  /**
   * Change user password
   */
  changePassword: async (data: ChangePasswordRequest): Promise<MessageResponse> => {
    const response = await apiClient.put<MessageResponse>(
      `${USER_BASE_URL}/me/password`,
      data
    );
    return response.data;
  },

  /**
   * Update user preferences
   */
  updatePreferences: async (data: UpdatePreferencesRequest): Promise<MessageResponse> => {
    const response = await apiClient.put<MessageResponse>(
      `${USER_BASE_URL}/me/preferences`,
      data
    );
    return response.data;
  },
};

