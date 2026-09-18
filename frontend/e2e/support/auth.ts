import { Page, Route, Request } from '@playwright/test';
import { Json, registerAuthHandler } from './api-stub';

/**
 * A signed-in session for the deterministic browser tests.
 *
 * The protected pages are behind ProtectedRoute, which sends an anonymous visitor to /login. A test
 * that simply navigates to /dashboard therefore asserts against the sign-in form, and "no win rate,
 * no profit, no NaN" passes trivially because a login form has none of those. Signing in first is
 * what makes those assertions about the dashboard.
 *
 * Nothing here weakens production authentication: it stubs the backend's answers inside one browser
 * context, exactly as the rest of e2e/support stubs the match endpoints. The application code still
 * reads its token from localStorage, still calls /auth/me, and still refuses to render the page if
 * either step fails — which is the point: breaking the stub must make the test fail.
 *
 * How the app boots a session (src/contexts/AuthContext.tsx + src/services/api-client.ts):
 *   1. tokenManager.hasTokens() reads localStorage "access_token" and "refresh_token";
 *   2. with both present, authService.getCurrentUser() does GET /api/v1/auth/me;
 *   3. the bare UserInfo body is mapped by mapBackendUserToFrontend();
 *   4. isAuthenticated is `!!user && !!tokens`, so step 2 failing leaves the visitor signed out.
 */

/** Mirrors TOKEN_STORAGE_KEYS in src/services/api-client.ts. */
export const ACCESS_TOKEN_KEY = 'access_token';
export const REFRESH_TOKEN_KEY = 'refresh_token';

/** The body GET /api/v1/auth/me returns — backend UserInfo, unwrapped. */
export interface BackendUser extends Json {
  user_id: string;
  email: string;
  full_name: string;
  role: 'regular' | 'expert' | 'admin';
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * These tokens are opaque strings that never leave the browser context: the stub accepts anything,
 * and no real backend is contacted. They are not credentials and unlock nothing.
 */
const STUB_ACCESS_TOKEN = 'e2e-stub-access-token';
const STUB_REFRESH_TOKEN = 'e2e-stub-refresh-token';

export const regularUser = (over: Partial<BackendUser> = {}): BackendUser => ({
  user_id: '00000000-0000-4000-8000-000000000001',
  email: 'qa.regular@predictions-local.dev',
  full_name: 'QA Regular',
  role: 'regular',
  is_active: true,
  is_verified: true,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-05T09:00:00Z',
  ...over,
});

export interface SignInOptions {
  /** Who is signed in; defaults to a verified regular account. */
  user?: BackendUser;
  /**
   * Status for GET /auth/me. Set it to 401 to break the sign-in on purpose and check that a test
   * which claims to assert about a protected page really does fail when it is not signed in.
   */
  meStatus?: number;
}

/**
 * Seed the session the application reads on start, and answer the auth endpoints.
 *
 * Call it in either order with stubBackend(): the handler is registered centrally (see
 * registerAuthHandler in api-stub.ts) and a page.route of its own is added as well, so whichever
 * interceptor Playwright reaches first produces the same answers.
 *
 * `page.addInitScript` runs before the application's own scripts on every navigation in this
 * context, which is what the token has to be there for.
 */
export async function signIn(page: Page, options: SignInOptions = {}): Promise<BackendUser> {
  const user = options.user ?? regularUser();
  const meStatus = options.meStatus ?? 200;

  await page.addInitScript(
    ({ accessKey, refreshKey, access, refresh }) => {
      window.localStorage.setItem(accessKey, access);
      window.localStorage.setItem(refreshKey, refresh);
    },
    {
      accessKey: ACCESS_TOKEN_KEY,
      refreshKey: REFRESH_TOKEN_KEY,
      access: STUB_ACCESS_TOKEN,
      refresh: STUB_REFRESH_TOKEN,
    },
  );

  const handler = (route: Route, request: Request): Promise<void> => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/auth/, '');
    const session = {
      access_token: STUB_ACCESS_TOKEN,
      refresh_token: STUB_REFRESH_TOKEN,
      token_type: 'bearer',
      user,
    };

    if (path === '/me') {
      return meStatus === 200 ? json(user) : json({ detail: 'Not authenticated' }, meStatus);
    }
    if (path === '/login' || path === '/register') return json(session);
    if (path === '/refresh') {
      return meStatus === 200
        ? json({ access_token: STUB_ACCESS_TOKEN, refresh_token: STUB_REFRESH_TOKEN, token_type: 'bearer' })
        : json({ detail: 'Invalid refresh token' }, 401);
    }
    if (path === '/logout') return json({ message: 'Logged out successfully' });
    return json({ detail: 'Not found' }, 404);
  };

  registerAuthHandler(page, handler);
  await page.route('**/api/v1/auth/**', handler);
  return user;
}
