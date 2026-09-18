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

/**
 * The password is a LOCAL TEST FIXTURE, not a secret, and this repository is public. Override it
 * with E2E_QA_PASSWORD when you want a different one.
 *
 * This account must never exist in a deployed database. It is created by the suite against the
 * local backend, it holds nothing, and every prediction it publishes is removed again. If local
 * seed data is ever promoted to a real environment, delete it first: it can publish as an expert.
 */
export const QA_EXPERT = {
  email: process.env.E2E_QA_EMAIL || 'qa.expert@predictions-local.dev',
  username: 'qa_expert_local',
  password: process.env.E2E_QA_PASSWORD || 'local-only-e2e-fixture',
  first_name: 'QA',
  last_name: 'Expert',
  role: 'expert',
};

/**
 * A human-readable label, and nothing more.
 *
 * It used to be the mechanism: the suite wrote it into the reasoning text and found its own rows
 * again by searching for it. That was wrong in two ways. The reasoning field is free-form text a
 * user controls, so anything that keys off it can be spoofed - once such a marker affected
 * scoring, an expert could keep their own losses off the leaderboard by typing nine characters.
 * And it silently missed anything unmarked: two hand-typed records on this very account survived
 * every cleanup run because of it, one of them with a NULL reasoning that the substring test could
 * not even evaluate.
 *
 * The mechanism is now the server-side `is_test_data` classification (see classifyQaPrediction).
 * The label stays only so a person reading the database by eye can see at a glance where a row
 * came from.
 */
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

/**
 * Classify one record as test data, so measured performance leaves it out.
 *
 * This is the supported mechanism, and it is the one the suite must use for anything it creates
 * outside the API - a prediction typed into the composer UI, for instance, where the request body
 * is the application's and not ours.
 *
 * It is refused with 404 unless the backend is running with ALLOW_TEST_DATA_CLASSIFICATION on,
 * which is off by default and must stay off wherever real predictions are published. Returns
 * whether the record ended up classified, so a caller can skip rather than pretend.
 */
export async function classifyQaPrediction(
  api: APIRequestContext,
  token: string,
  predictionId: string,
): Promise<boolean> {
  const response = await api.post(`/api/v1/expert/predictions/${predictionId}/test-classification`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { is_test_data: true },
  });
  if (!response.ok()) return false;
  return (await response.json()).is_test_data === true;
}

/** A prediction this suite created, as the API returns it. */
export interface QaPredictionRow {
  id: string;
  status?: string;
  published_at?: string | null;
  unpublished_at?: string | null;
  reasoning?: string | null;
  is_test_data?: boolean | null;
  [field: string]: unknown;
}

/**
 * Publish a prediction as the QA expert, classified as test data from the moment it exists.
 *
 * Asking for the classification in the create request is the whole point: the record is marked
 * server-side, by a column, before anything can ever measure it - not by a string in a field the
 * expert writes.
 */
export async function publishQaPrediction(
  api: APIRequestContext,
  token: string,
  data: Record<string, unknown>,
): Promise<QaPredictionRow> {
  const response = await api.post('/api/v1/expert/predictions/manual', {
    headers: { Authorization: `Bearer ${token}` },
    data: { is_test_data: true, ...data },
  });
  if (!response.ok()) {
    throw new Error(`could not publish a QA prediction: ${response.status()} ${await response.text()}`);
  }
  return response.json();
}

let warnedAboutUnclassifiedRows = false;

/**
 * Remove every prediction this suite created, so a rerun starts from the same place.
 *
 * Rows are selected by the `is_test_data` classification. The legacy marker is still honoured as a
 * fallback, for one reason only: a prediction created through the composer UI is built by the
 * application's own request, which does not ask for the classification, so the suite cannot attach
 * the flag at creation time. Those rows would otherwise accumulate forever. The fallback warns,
 * because it should eventually go: the composer path needs to classify its record explicitly (see
 * classifyQaPrediction) and then this can select on the flag alone.
 */
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
    const classified = row.is_test_data === true;
    const legacyLabelled =
      !classified && typeof row.reasoning === 'string' && row.reasoning.includes(QA_REASONING_MARKER);
    if (legacyLabelled && !warnedAboutUnclassifiedRows) {
      warnedAboutUnclassifiedRows = true;
      console.warn(
        '[qa-account] removing a record that carries the legacy reasoning label but no ' +
          'is_test_data classification. Either the backend is running without ' +
          'ALLOW_TEST_DATA_CLASSIFICATION, or the record was created through the composer UI, ' +
          'which does not yet ask for the classification.',
      );
    }
    if (!classified && !legacyLabelled) continue;
    const deleted = await api.delete(`/api/v1/expert/predictions/${row.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (deleted.ok()) removed += 1;
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
