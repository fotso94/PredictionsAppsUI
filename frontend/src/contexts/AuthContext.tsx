import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { authService } from '@/services/auth.service';
import { tokenManager, handleApiError } from '@/services/api-client';
import type {
  User,
  AuthTokens,
  AuthContextType,
  RegisterRequest,
} from '@/types/auth';
import { mapBackendUserToFrontend } from '@/types/auth';
import toast from 'react-hot-toast';

// Create context
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Provider props
interface AuthProviderProps {
  children: React.ReactNode;
}

/**
 * AuthProvider Component
 * Manages authentication state and provides auth methods to the app
 */
export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [tokens, setTokens] = useState<AuthTokens | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Check if user is authenticated
  const isAuthenticated = !!user && !!tokens;

  /**
   * Initialize auth state on mount
   * Check if user has valid tokens and fetch user data
   */
  useEffect(() => {
    const initializeAuth = async () => {
      console.log('[AuthContext] Initializing authentication...');
      try {
        // Check if tokens exist in localStorage
        if (tokenManager.hasTokens()) {
          console.log('[AuthContext] Found tokens in localStorage');
          const accessToken = tokenManager.getAccessToken();
          const refreshToken = tokenManager.getRefreshToken();

          if (accessToken && refreshToken) {
            setTokens({
              access_token: accessToken,
              refresh_token: refreshToken,
              token_type: 'bearer',
            });

            // Fetch current user data
            // If access token is expired, the interceptor will automatically refresh it
            try {
              console.log('[AuthContext] Fetching current user data...');
              const response = await authService.getCurrentUser();
              const frontendUser = mapBackendUserToFrontend(response.user);
              setUser(frontendUser);
              console.log('[AuthContext] User authenticated:', frontendUser.email);
            } catch (userError) {
              // If fetching user fails even after token refresh, clear auth
              console.error('[AuthContext] Failed to fetch user data:', userError);
              tokenManager.clearTokens();
              setTokens(null);
              setUser(null);
            }
          }
        } else {
          console.log('[AuthContext] No tokens found in localStorage');
        }
      } catch (err) {
        console.error('[AuthContext] Failed to initialize auth:', err);
        // Clear invalid tokens
        tokenManager.clearTokens();
        setTokens(null);
        setUser(null);
      } finally {
        setIsLoading(false);
        console.log('[AuthContext] Initialization complete');
      }
    };

    initializeAuth();
  }, []);

  /**
   * Subscribe to token updates from api-client
   * This keeps the context in sync when tokens are refreshed automatically
   */
  useEffect(() => {
    // Set up callback to update tokens in context when they're refreshed
    tokenManager.onTokensUpdated = (accessToken: string, refreshToken: string) => {
      console.log('[AuthContext] Tokens updated from api-client');
      setTokens({
        access_token: accessToken,
        refresh_token: refreshToken,
        token_type: 'bearer',
      });
    };

    // Cleanup
    return () => {
      tokenManager.onTokensUpdated = null;
    };
  }, []);

  /**
   * Login user
   */
  const login = useCallback(
    async (email: string, password: string): Promise<void> => {
      try {
        setIsLoading(true);
        setError(null);

        const response = await authService.login({ email, password });

        // Map backend user to frontend user
        const frontendUser = mapBackendUserToFrontend(response.user);

        // Update state
        setUser(frontendUser);
        setTokens({
          access_token: response.access_token,
          refresh_token: response.refresh_token,
          token_type: response.token_type,
        });

        toast.success('Login successful!');

        // Redirect based on user role
        const redirectPath = getRedirectPath(frontendUser.user_type);
        navigate(redirectPath);
      } catch (err) {
        const errorMessage = handleApiError(err);
        setError(errorMessage);
        toast.error(errorMessage);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [navigate]
  );

  /**
   * Register new user
   */
  const register = useCallback(
    async (data: RegisterRequest): Promise<void> => {
      try {
        setIsLoading(true);
        setError(null);

        const response = await authService.register(data);

        // Map backend user to frontend user
        const frontendUser = mapBackendUserToFrontend(response.user);

        // Update state
        setUser(frontendUser);
        setTokens({
          access_token: response.access_token,
          refresh_token: response.refresh_token,
          token_type: response.token_type,
        });

        toast.success(response.message || 'Registration successful!');

        // Redirect based on user role
        const redirectPath = getRedirectPath(frontendUser.user_type);
        navigate(redirectPath);
      } catch (err) {
        const errorMessage = handleApiError(err);
        setError(errorMessage);
        toast.error(errorMessage);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [navigate]
  );

  /**
   * Logout user
   */
  const logout = useCallback(async (): Promise<void> => {
    try {
      setIsLoading(true);
      await authService.logout();

      // Clear state
      setUser(null);
      setTokens(null);
      setError(null);

      toast.success('Logged out successfully');
      navigate('/login');
    } catch (err) {
      console.error('Logout error:', err);
      // Clear state even if API call fails
      setUser(null);
      setTokens(null);
      tokenManager.clearTokens();
      navigate('/login');
    } finally {
      setIsLoading(false);
    }
  }, [navigate]);

  /**
   * Refresh access token
   */
  const refreshToken = useCallback(async (): Promise<void> => {
    try {
      const response = await authService.refreshToken();

      setTokens({
        access_token: response.access_token,
        refresh_token: response.refresh_token,
        token_type: response.token_type,
      });
    } catch (err) {
      console.error('Token refresh failed:', err);
      // Clear auth state and redirect to login
      setUser(null);
      setTokens(null);
      tokenManager.clearTokens();
      navigate('/login');
      throw err;
    }
  }, [navigate]);

  /**
   * Clear error state
   */
  const clearError = useCallback((): void => {
    setError(null);
  }, []);

  // Context value
  const value: AuthContextType = {
    user,
    tokens,
    isAuthenticated,
    isLoading,
    error,
    login,
    register,
    logout,
    refreshToken,
    clearError,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * useAuth Hook
 * Access auth context in components
 */
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  
  return context;
};

/**
 * Get redirect path based on user role
 */
const getRedirectPath = (userType: string): string => {
  switch (userType) {
    case 'ADMIN':
      return '/dashboard'; // Admin dashboard
    case 'EXPERT':
      return '/expert/dashboard'; // Expert dashboard
    case 'REGULAR':
    default:
      return '/'; // Home page for regular users
  }
};

export default AuthContext;

