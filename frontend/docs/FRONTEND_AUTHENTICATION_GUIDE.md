# Frontend Authentication Implementation Guide

## Overview

This document describes the complete frontend authentication system integrated with the backend JWT authentication API.

## Architecture

### Components

1. **API Client** (`src/services/api-client.ts`)
   - Axios instance with base configuration
   - Request/response interceptors
   - Automatic token refresh
   - Error handling

2. **Authentication Service** (`src/services/auth.service.ts`)
   - Login, register, logout functions
   - Token management
   - User data fetching

3. **Auth Context** (`src/contexts/AuthContext.tsx`)
   - Global authentication state
   - React hooks for auth operations
   - Auto-initialization on app load

4. **Protected Routes** (`src/components/ProtectedRoute.tsx`)
   - Route protection based on authentication
   - Role-based access control
   - Loading states and redirects

## Authentication Flow

### 1. User Registration

```typescript
// User fills registration form
const handleRegister = async () => {
  await register({
    email: 'user@example.com',
    password: 'password123',
    first_name: 'John',
    last_name: 'Doe'
  });
  // Automatically logged in and redirected to dashboard
};
```

**Flow:**
1. User submits registration form
2. `authService.register()` calls `POST /api/v1/auth/register`
3. Backend creates user and returns tokens
4. Tokens stored in localStorage
5. User state updated in AuthContext
6. Redirect to dashboard
7. Success toast notification

### 2. User Login

```typescript
// User fills login form
const handleLogin = async () => {
  await login('user@example.com', 'password123');
  // Redirected based on user role
};
```

**Flow:**
1. User submits login form
2. `authService.login()` calls `POST /api/v1/auth/login`
3. Backend validates credentials and returns tokens
4. Tokens stored in localStorage
5. User state updated in AuthContext
6. Redirect based on role:
   - ADMIN → `/dashboard`
   - EXPERT → `/dashboard`
   - REGULAR → `/` (home)
7. Success toast notification

### 3. Authenticated Requests

```typescript
// All API requests automatically include JWT token
const response = await apiClient.get('/api/v1/some-endpoint');
```

**Flow:**
1. Request interceptor adds `Authorization: Bearer <access_token>` header
2. Request sent to backend
3. If 401 error (token expired):
   - Automatically call refresh token endpoint
   - Update tokens in localStorage
   - Retry original request with new token
4. If refresh fails:
   - Clear tokens
   - Redirect to login

### 4. Token Refresh

**Automatic refresh on 401 errors:**
```typescript
// Happens automatically in response interceptor
// User doesn't need to do anything
```

**Manual refresh:**
```typescript
const { refreshToken } = useAuth();
await refreshToken();
```

**Flow:**
1. Access token expires (7 days)
2. API request returns 401
3. Response interceptor catches error
4. Calls `POST /api/v1/auth/refresh` with refresh token
5. Backend validates refresh token
6. Returns new access and refresh tokens
7. Tokens updated in localStorage
8. Original request retried with new token
9. If refresh token expired (30 days):
   - Clear all tokens
   - Redirect to login

### 5. User Logout

```typescript
const { logout } = useAuth();
await logout();
```

**Flow:**
1. User clicks logout
2. `authService.logout()` calls `POST /api/v1/auth/logout`
3. Backend blacklists refresh token
4. Tokens cleared from localStorage
5. User state cleared in AuthContext
6. Redirect to login page
7. Success toast notification

## Usage Examples

### Using Auth in Components

```typescript
import { useAuth } from '@/contexts/AuthContext';

function MyComponent() {
  const { user, isAuthenticated, isLoading, login, logout } = useAuth();

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (!isAuthenticated) {
    return <div>Please login</div>;
  }

  return (
    <div>
      <p>Welcome, {user.first_name}!</p>
      <p>Role: {user.user_type}</p>
      <button onClick={logout}>Logout</button>
    </div>
  );
}
```

### Protecting Routes

```typescript
// In App.tsx
<Route 
  path="/dashboard" 
  element={
    <ProtectedRoute>
      <DashboardPage />
    </ProtectedRoute>
  } 
/>

// Role-based protection
<Route 
  path="/admin" 
  element={
    <ProtectedRoute allowedRoles={['ADMIN']}>
      <AdminPage />
    </ProtectedRoute>
  } 
/>
```

### Making Authenticated API Calls

```typescript
import apiClient from '@/services/api-client';

// GET request
const fetchData = async () => {
  const response = await apiClient.get('/api/v1/data');
  return response.data;
};

// POST request
const createData = async (data) => {
  const response = await apiClient.post('/api/v1/data', data);
  return response.data;
};
```

## Token Storage

### Storage Keys
- `access_token` - JWT access token (7 days expiration)
- `refresh_token` - JWT refresh token (30 days expiration)

### Storage Location
- **localStorage** - Persists across browser sessions
- Tokens are automatically included in all API requests
- Tokens are cleared on logout or authentication failure

## Error Handling

### Authentication Errors

```typescript
try {
  await login(email, password);
} catch (error) {
  // Error is automatically displayed via toast
  // Error message is user-friendly
}
```

### Common Error Messages
- **401 Unauthorized**: "Authentication failed. Please login again."
- **403 Forbidden**: "You do not have permission to perform this action."
- **422 Validation Error**: "Validation error. Please check your input."
- **Network Error**: "Network error. Please check your connection and try again."

## Security Features

1. **Automatic Token Refresh**
   - Prevents session expiration during active use
   - Seamless user experience

2. **Token Blacklisting**
   - Logout invalidates refresh token on backend
   - Prevents token reuse after logout

3. **Request Queue During Refresh**
   - Multiple simultaneous requests don't trigger multiple refresh calls
   - Requests are queued and retried after token refresh

4. **Secure Token Storage**
   - Tokens stored in localStorage
   - Cleared on logout or authentication failure

5. **Role-Based Access Control**
   - Routes protected by user role
   - Unauthorized access shows access denied page

## Configuration

### Environment Variables

```env
# .env file
VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT=30000
```

### API Client Configuration

```typescript
// src/services/api-client.ts
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: parseInt(import.meta.env.VITE_API_TIMEOUT),
  headers: {
    'Content-Type': 'application/json',
  },
});
```

## Testing

### Manual Testing Steps

1. **Registration Flow**
   - Navigate to `/register`
   - Fill in registration form
   - Submit and verify redirect to dashboard
   - Check localStorage for tokens
   - Verify user info in header

2. **Login Flow**
   - Navigate to `/login`
   - Enter credentials
   - Submit and verify redirect based on role
   - Check localStorage for tokens
   - Verify user info in header

3. **Protected Routes**
   - Try accessing `/dashboard` without login
   - Verify redirect to `/login`
   - Login and verify access granted

4. **Logout Flow**
   - Click logout in header menu
   - Verify redirect to login
   - Check localStorage tokens are cleared
   - Try accessing protected route (should redirect to login)

5. **Token Refresh**
   - Login and wait for access token to expire (or manually delete it)
   - Make an API request
   - Verify automatic token refresh
   - Verify request succeeds

## Troubleshooting

### Issue: "Network error" on login
- **Solution**: Ensure backend is running on http://localhost:8000
- Check VITE_API_BASE_URL in .env file

### Issue: Infinite redirect loop
- **Solution**: Clear localStorage and refresh page
- Check AuthContext initialization logic

### Issue: 401 errors after login
- **Solution**: Check token format in localStorage
- Verify backend JWT secret matches

### Issue: Protected routes not working
- **Solution**: Ensure AuthProvider wraps App component in main.tsx
- Check ProtectedRoute component is used correctly

## Files Reference

### Core Files
- `src/services/api-client.ts` - Axios configuration and interceptors
- `src/services/auth.service.ts` - Authentication API calls
- `src/contexts/AuthContext.tsx` - Global auth state management
- `src/components/ProtectedRoute.tsx` - Route protection component
- `src/types/auth.ts` - TypeScript type definitions

### Integration Files
- `src/main.tsx` - AuthProvider setup
- `src/App.tsx` - Protected routes configuration
- `src/pages/LoginPage.tsx` - Login form integration
- `src/pages/RegisterPage.tsx` - Registration form integration
- `src/components/layout/Header.tsx` - User menu and logout

### Configuration Files
- `.env` - Environment variables
- `.env.example` - Environment variables template

## Next Steps

1. **Email Verification**
   - Implement email verification flow
   - Add resend verification email endpoint

2. **Password Reset**
   - Implement forgot password flow
   - Add reset password endpoint

3. **Remember Me**
   - Implement persistent login option
   - Use different token expiration for "remember me"

4. **Multi-Factor Authentication**
   - Add 2FA support
   - Implement TOTP or SMS verification

5. **Session Management**
   - Add active sessions view
   - Allow users to revoke sessions

---

**Last Updated**: 2025-10-09  
**Version**: 1.0.0  
**Status**: Production Ready

