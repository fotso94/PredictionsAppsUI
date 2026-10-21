import { APIRequestContext, request } from '@playwright/test';
import { assertPreflightPassed } from './preflight-token';
import { loadCommittedPolicy, origin } from './target-policy';

/**
 * The isolated pair, for the browser tests that WRITE.
 *
 * Most live tests read the running stack and remove what they add. The parlay journey cannot: it
 * records a slip, and a recorded slip is immutable by design, so every run left one more on the
 * QA account of whatever backend it was pointed at - by default the one on :8000, on the live
 * database - and it deleted that account's unrecorded slips first. Those tests now run only
 * against the isolated pair (docs/isolated-dev-environment.md): a frontend on :3101 and a backend
 * on :8001 serving a clone of the live database, with the scheduler off and no provider
 * credentials, started by scripts/local-servers.sh.
 *
 * Two guards, because a wrong URL is a configuration slip and must fail loudly rather than write
 * to the wrong database: the isolated API may not be the same origin as the main one, and the
 * backend it reaches must say (GET /health, `database`) that it serves an APPROVED isolated
 * database - an allowlist from backend/app/core/isolation_targets.json, not "anything but the live
 * one", so soccer_predictions_dev or a typo is refused as well. A backend too old to say is refused
 * too. These are the per-spec second line: the run's isolation preflight (e2e/global-preflight.ts)
 * has already judged the isolated pair - every Redis database included - before any spec loaded.
 */

export const ISOLATED_API = process.env.E2E_ISOLATED_API_URL || 'http://127.0.0.1:8001';
export const ISOLATED_BASE = process.env.E2E_ISOLATED_BASE_URL || 'http://localhost:3101';
const MAIN_API = process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const POLICY = loadCommittedPolicy();

/** An API context on the isolated backend, refused unless it really is isolated. */
export async function isolatedApiContext(): Promise<APIRequestContext> {
  assertPreflightPassed('isolated.ts isolatedApiContext');
  if (origin(ISOLATED_API) === origin(MAIN_API)) {
    throw new Error(`E2E_ISOLATED_API_URL (${ISOLATED_API}) is the main backend (${MAIN_API}); `
      + 'a write-producing test runs only against the isolated pair');
  }
  const api = await request.newContext({ baseURL: ISOLATED_API });
  const health = await api.get('/health').catch(() => null);
  if (!health || !health.ok()) {
    await api.dispose();
    throw new Error(`no backend answers at ${ISOLATED_API}: start the isolated pair first `
      + '(scripts/local-servers.sh start isolated)');
  }
  const body = (await health.json()) as { database?: unknown };
  if (body.database === null) {
    await api.dispose();
    throw new Error(`the backend at ${ISOLATED_API} cannot say which database it really connects to (its DATABASE_URL `
      + 'cannot be read or carries a parameter that redirects it); refusing to write through it');
  }
  if (typeof body.database !== 'string') {
    await api.dispose();
    throw new Error(`the backend at ${ISOLATED_API} does not say which database it serves; `
      + 'it predates that field - restart it on the current code');
  }
  if (POLICY.live.databases.includes(body.database)) {
    await api.dispose();
    throw new Error(`the backend at ${ISOLATED_API} serves the live database ${body.database}; refusing to write to it`);
  }
  if (!POLICY.isolated.databases.includes(body.database)) {
    await api.dispose();
    throw new Error(`the backend at ${ISOLATED_API} serves ${body.database}, which is not an approved isolated database `
      + `(${POLICY.isolated.databases.join(', ')}); refusing to write to it`);
  }
  return api;
}
