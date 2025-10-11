import apiClient, { tokenManager } from './api-client';
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
  RefreshTokenRequest,
  RefreshTokenResponse,
  LogoutRequest,
  LogoutResponse,
  UserInfoResponse,
  ChangePasswordRequest,
  ChangePasswordResponse,
  ForgotPasswordRequest,
  ForgotPasswordResponse,
  ResetPasswordRequest,
  ResetPasswordResponse,
  VerifyResetTokenResponse,
} from '@/types/auth';

const AUTH_BASE_URL = '/api/v1/auth';

/**
 * Authentication Service
 * Handles all authentication-related API calls
 */
export const authService = {
  /**
   * Login user with email and password
   */
  login: async (credentials: LoginRequest): Promise<LoginResponse> => {
    const response = await apiClient.post<LoginResponse>(
      `${AUTH_BASE_URL}/login`,
      credentials
    );
    
    // Store tokens
    const { access_token, refresh_token } = response.data;
    tokenManager.setTokens(access_token, refresh_token);
    
    return response.data;
  },

  /**
   * Register new user
   */
  register: async (userData: RegisterRequest): Promise<RegisterResponse> => {
    const response = await apiClient.post<RegisterResponse>(
      `${AUTH_BASE_URL}/register`,
      userData
    );
    
    // Store tokens
    const { access_token, refresh_token } = response.data;
    tokenManager.setTokens(access_token, refresh_token);
    
    return response.data;
  },

  /**
   * Logout user
   */
  logout: async (): Promise<LogoutResponse> => {
    const refreshToken = tokenManager.getRefreshToken();
    
    if (!refreshToken) {
      // No refresh token, just clear local storage
      tokenManager.clearTokens();
      return { message: 'Logged out successfully' };
    }

    try {
      const response = await apiClient.post<LogoutResponse>(
        `${AUTH_BASE_URL}/logout`,
        { refresh_token: refreshToken } as LogoutRequest
      );
      
      return response.data;
    } finally {
      // Always clear tokens, even if API call fails
      tokenManager.clearTokens();
    }
  },

  /**
   * Refresh access token using refresh token
   */
  refreshToken: async (): Promise<RefreshTokenResponse> => {
    const refreshToken = tokenManager.getRefreshToken();
    
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    const response = await apiClient.post<RefreshTokenResponse>(
      `${AUTH_BASE_URL}/refresh`,
      { refresh_token: refreshToken } as RefreshTokenRequest
    );
    
    // Update tokens
    const { access_token, refresh_token: new_refresh_token } = response.data;
    tokenManager.setTokens(access_token, new_refresh_token);
    
    return response.data;
  },

  /**
   * Get current user information
   */
  getCurrentUser: async (): Promise<UserInfoResponse> => {
    const response = await apiClient.get<UserInfoResponse>(
      `${AUTH_BASE_URL}/me`
    );
    
    return response.data;
  },

  /**
   * Change user password
   */
  changePassword: async (
    passwordData: ChangePasswordRequest
  ): Promise<ChangePasswordResponse> => {
    const response = await apiClient.post<ChangePasswordResponse>(
      `${AUTH_BASE_URL}/change-password`,
      passwordData
    );

    return response.data;
  },

  /**
   * Request password reset
   */
  forgotPassword: async (
    email: string
  ): Promise<ForgotPasswordResponse> => {
    const response = await apiClient.post<ForgotPasswordResponse>(
      `${AUTH_BASE_URL}/forgot-password`,
      { email } as ForgotPasswordRequest
    );

    return response.data;
  },

  /**
   * Verify password reset token
   */
  verifyResetToken: async (
    token: string
  ): Promise<VerifyResetTokenResponse> => {
    const response = await apiClient.get<VerifyResetTokenResponse>(
      `${AUTH_BASE_URL}/verify-reset-token/${token}`
    );

    return response.data;
  },

  /**
   * Reset password with token
   */
  resetPassword: async (
    token: string,
    newPassword: string
  ): Promise<ResetPasswordResponse> => {
    const response = await apiClient.post<ResetPasswordResponse>(
      `${AUTH_BASE_URL}/reset-password`,
      { token, new_password: newPassword } as ResetPasswordRequest
    );

    return response.data;
  },

  /**
   * Check if user is authenticated (has valid tokens)
   */
  isAuthenticated: (): boolean => {
    return tokenManager.hasTokens();
  },

  /**
   * Clear authentication data
   */
  clearAuth: (): void => {
    tokenManager.clearTokens();
  },
};

export default authService;

