import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import type { SignInHandoff } from '@/components/favourites/useMatchSaving';
import type { UserType } from '@/types/auth';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserType[];
  requireAuth?: boolean;
}

/**
 * ProtectedRoute Component
 * Protects routes based on authentication status and user roles
 *
 * An anonymous visitor is sent to /login carrying where they were, in the one handoff shape the
 * sign-in forms know how to read (SignInHandoff, defined with its validation in
 * components/favourites/useMatchSaving.ts). `location` carries the pathname, the query string and
 * the fragment, so a filtered list comes back filtered. There is no `save` here: nothing was being
 * saved — this visitor asked for a page, and the page is all they get back.
 */
const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  allowedRoles,
  requireAuth = true,
}) => {
  const { isAuthenticated, user, isLoading } = useAuth();
  const location = useLocation();

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <div className="min-h-screen bg-dark-950 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
          <p className="mt-4 text-secondary-400">Loading...</p>
        </div>
      </div>
    );
  }

  // Redirect to login if authentication is required but user is not authenticated
  if (requireAuth && !isAuthenticated) {
    // No `at`: the timestamp exists to expire an interrupted SAVE, and there is none here. A
    // return destination does not go stale — the page is still the page they asked for.
    const handoff: SignInHandoff = { from: location };
    return <Navigate to="/login" state={handoff} replace />;
  }

  // Check role-based access
  if (allowedRoles && user) {
    const hasRequiredRole = allowedRoles.includes(user.user_type);
    
    if (!hasRequiredRole) {
      // User doesn't have required role, redirect to unauthorized page or home
      return (
        <div className="min-h-screen bg-dark-950 flex items-center justify-center">
          <div className="text-center max-w-md">
            <h1 className="text-4xl font-bold text-white mb-4">Access Denied</h1>
            <p className="text-secondary-400 mb-6">
              You don't have permission to access this page.
            </p>
            <a
              href="/"
              className="inline-block px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              Go to Home
            </a>
          </div>
        </div>
      );
    }
  }

  // User is authenticated and has required role (if specified)
  return <>{children}</>;
};

export default ProtectedRoute;

