import { APIRequestContext, request } from '@playwright/test';
import { ApiMatch } from './api-stub';

/**
 * An isolated QA expert account for the live browser tests.
 *
 * It is created through the public API on the local backend, is clearly marked, and only ever
 * publishes predictions this suite created. Nothing here touches a data provider, so running the
 * live tests costs no trial allowance.
 */

export const API = process.env.E2E_API_URL || 'http://127.0.0.1:8000';

export const QA_EXPERT = {
  email: 'qa.expert@predictions-local.dev',
  username: 'qa_expert_local',
  password: 'QaExpertLocal!2026',
  first_name: 'QA',
  last_name: 'Expert',
  role: 'expert',
};

export const QA_REASONING_MARKER = '[e2e-qa]';

export async function apiContext(): Promise<APIRequestContext> {
  return request.newContext({ baseURL: API });
}

/** Create the QA expert if it does not exist yet, then return a bearer token. */
export async function ensureQaExpertToken(api: APIRequestContext): Promise<string> {
  const login = async () => {
    const response = await api.post('/api/v1/auth/login', {
      data: { email: QA_EXPERT.email, password: QA_EXPERT.password },
    });
    return response.ok() ? (await response.json()) : null;
  };

  let session = await login();
  if (!session) {
    await api.post('/api/v1/auth/register', { data: QA_EXPERT });
    session = await login();
  }
  if (!session) throw new Error('could not sign the QA expert in against the local backend');
  return session.access_token || session.accessToken || session.token;
}

/** Remove every prediction this suite created, so a rerun starts from the same place. */
interface QaPredictionRow {
  id: string;
  reasoning?: string | null;
}

export async function cleanupQaPredictions(api: APIRequestContext, token: string): Promise<number> {
  const response = await api.get('/api/v1/expert/predictions/my-predictions?limit=100', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) return 0;
  const body = await response.json();
  // the endpoint returns a bare list; the object forms are tolerated in case that changes
  const rows: QaPredictionRow[] = Array.isArray(body) ? body : (body.predictions || body.items || []);
  let removed = 0;
  for (const row of rows) {
    if (typeof row.reasoning === 'string' && row.reasoning.includes(QA_REASONING_MARKER)) {
      const deleted = await api.delete(`/api/v1/expert/predictions/${row.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (deleted.ok()) removed += 1;
    }
  }
  return removed;
}

/** A match from the local database that the QA expert can attach a prediction to. */
export async function anyUpcomingMatch(api: APIRequestContext): Promise<ApiMatch | null> {
  for (let offset = 0; offset < 8; offset += 1) {
    const day = new Date();
    day.setUTCDate(day.getUTCDate() + offset);
    const iso = day.toISOString().slice(0, 10);
    // refresh=false keeps this a database read: no provider request is made
    const response = await api.get(`/api/v1/matches?date=${iso}&refresh=false`);
    if (!response.ok()) continue;
    const body = await response.json();
    const upcoming = (body.matches || []).find((m: ApiMatch) => m.status === 'scheduled');
    if (upcoming) return upcoming;
  }
  return null;
}
