// Authentication Types

export type UserType = 'REGULAR' | 'EXPERT' | 'ADMIN';
export type AccountStatus = 'ACTIVE' | 'SUSPENDED' | 'DELETED' | 'PENDING_VERIFICATION';

// Backend UserInfo schema (from API)
export interface BackendUserInfo {
  user_id: string;
  email: string;
  full_name: string;
  role: string; // 'regular' | 'expert' | 'admin'
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
}

// Frontend User type
export interface User {
  id: string;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  user_type: UserType;
  account_status: AccountStatus;
  email_verified: boolean;
  created_at: string;
  last_login_at: string | null;
}

// Helper function to map backend UserInfo to frontend User
export function mapBackendUserToFrontend(backendUser: BackendUserInfo): User {
  const [firstName, ...lastNameParts] = backendUser.full_name.split(' ');
  const lastName = lastNameParts.join(' ');

  return {
    id: backendUser.user_id,
    email: backendUser.email,
    username: backendUser.email.split('@')[0], // Generate from email
    first_name: firstName || '',
    last_name: lastName || '',
    user_type: backendUser.role.toUpperCase() as UserType,
    account_status: backendUser.is_active ? 'ACTIVE' : 'SUSPENDED',
    email_verified: backendUser.is_verified,
    created_at: backendUser.created_at,
    last_login_at: null, // Not provided by backend
  };
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: BackendUserInfo;
}

export interface RegisterRequest {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
}

export interface RegisterResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: BackendUserInfo;
  message: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface RefreshTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LogoutRequest {
  refresh_token: string;
}

export interface LogoutResponse {
  message: string;
}

export interface UserInfoResponse {
  user: BackendUserInfo;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface ChangePasswordResponse {
  message: string;
}

export interface AuthState {
  user: User | null;
  tokens: AuthTokens | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}

export interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
  clearError: () => void;
}

// API Error Response
export interface ApiError {
  detail: string;
  status_code?: number;
}

// Form validation errors
export interface ValidationError {
  field: string;
  message: string;
}

