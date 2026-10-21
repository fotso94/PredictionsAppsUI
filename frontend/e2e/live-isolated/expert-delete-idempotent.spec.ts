import { APIRequestContext, APIResponse } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { isolatedApiContext } from '../support/isolated';
import {
  anyUpcomingMatch, cleanupQaPredictions, ensureQaExpertToken, publishQaPrediction, QA_REASONING_MARKER,
} from '../support/qa-account';
import { ApiMatch } from '../support/api-stub';

/**
 * Deleting a prediction twice, through the REAL isolated backend (:8001, soccer_predictions_e2e).
 *
 * WHY. QA reproduced the deletion-history defect (P1-3) on the isolated backend: a repeated DELETE
 * moved the stored deletion time, and with it settlement's answer to "was this withdrawn before
 * kickoff?". The fix is proved by backend tests against soccer_predictions_test and a race test on
 * its own database, but nothing had sent the repeat through the running backend where the defect
 * was seen. This does: the real endpoint, the real database, the real public match payload.
 *
 * WHAT IT CHECKS. Both calls answer 200 with the same `deleted_at`; the first says
 * `already_deleted: false` and the repeat `already_deleted: true`; the row is gone from the public
 * match payload and from the expert's own list. The same for two DELETEs sent at once.
 *
 * WHAT IT WRITES. Only predictions it publishes itself, through publishQaPrediction (classified as
 * test data, labelled with the QA marker), on one upcoming fixture; every QA prediction is removed
 * again before and after (cleanupQaPredictions). Deletion is a soft delete, so each deleted row
 * stays in soccer_predictions_e2e with its deleted_at and one DELETE audit entry - which is the
 * evidence this test is about.
 *
 * NOTHING HERE MAY REACH THE LIVE STACK. Every request goes through isolatedApiContext, which
 * refuses :8000 and any backend serving the live database. No browser page is opened, and no
 * provider is called: anyUpcomingMatch reads with refresh=false and the isolated backend has no
 * provider keys.
 */

let api: APIRequestContext;
let token: string;
let match: ApiMatch | null = null;

const auth = () => ({ Authorization: `Bearer ${token}` });

interface DeleteBody {
  message: string;
  prediction_id: string;
  deleted_at: string | null;
  already_deleted: boolean;
}

test.beforeAll(async () => {
  api = await isolatedApiContext();
  token = await ensureQaExpertToken(api);
  await cleanupQaPredictions(api, token);
  match = await anyUpcomingMatch(api);
});

test.beforeEach(async () => {
  test.skip(!match, 'no upcoming fixture in the isolated database to attach a prediction to');
  await cleanupQaPredictions(api, token);
});

test.afterAll(async () => {
  if (api && token) await cleanupQaPredictions(api, token);
  await api?.dispose();
});

const publish = (label: string) => publishQaPrediction(api, token, {
  match_id: match?.id,
  home_win_prob: 0.45,
  draw_prob: 0.3,
  away_win_prob: 0.25,
  confidence_score: 0.6,
  reasoning: `${QA_REASONING_MARKER} delete-idempotent ${label}`,
});

const remove = (id: string) => api.delete(`/api/v1/expert/predictions/${id}`, { headers: auth() });

async function body(response: APIResponse, what: string): Promise<DeleteBody> {
  expect(response.status(), `${what}: ${await response.text()}`).toBe(200);
  return response.json();
}

/** The public match payload's expert prediction ids: the list, and the headline one. */
async function publicIds(): Promise<string[]> {
  const response = await api.get(`/api/v1/matches/${match?.id}`);
  expect(response.ok(), 'GET the public match on the isolated backend').toBe(true);
  const payload = await response.json();
  const listed = (payload.expert_predictions ?? []).map((row: { id: string }) => row.id);
  return payload.expert_prediction?.id ? [...listed, payload.expert_prediction.id] : listed;
}

async function mine(): Promise<string[]> {
  const response = await api.get('/api/v1/expert/predictions/my-predictions?limit=100', { headers: auth() });
  expect(response.ok(), 'GET my-predictions on the isolated backend').toBe(true);
  const rows = await response.json();
  return (Array.isArray(rows) ? rows : (rows.predictions ?? rows.items ?? [])).map((row: { id: string }) => row.id);
}

function expectSameDeletion(first: DeleteBody, second: DeleteBody, id: string): void {
  expect(first.prediction_id).toBe(id);
  expect(second.prediction_id).toBe(id);
  expect(first.deleted_at, 'the first delete reports when it deleted').toMatch(/^\d{4}-\d{2}-\d{2}T.*Z$/);
  expect(second.deleted_at, 'the repeat reports the FIRST deletion time, unmoved').toBe(first.deleted_at);
}

test('a DELETE sent twice answers 200 both times with one deletion time, and the row leaves the public match', async () => {
  const created = await publish('twice');
  const served = await api.get(`/api/v1/matches/${match?.id}`);
  const row = ((await served.json()).expert_predictions ?? []).find((r: { id: string }) => r.id === created.id);
  expect(row, 'the new prediction is public before it is deleted').toBeTruthy();
  // Published now, on an upcoming fixture, never withdrawn: it stands, and the payload says so.
  expect(row.published_after_kickoff).toBe(false);
  expect(row.withdrawn_before_kickoff).toBe(false);

  const first = await body(await remove(created.id), 'first DELETE');
  const second = await body(await remove(created.id), 'repeated DELETE');

  expect(first.already_deleted, 'the first call is the one that deleted').toBe(false);
  expect(second.already_deleted, 'the repeat says it was already deleted').toBe(true);
  expectSameDeletion(first, second, created.id);
  expect(await publicIds(), 'a deleted prediction is not served publicly').not.toContain(created.id);
  expect(await mine(), 'nor listed among the expert\'s own').not.toContain(created.id);

  // A third call, later still, changes nothing either.
  const third = await body(await remove(created.id), 'third DELETE');
  expect(third.already_deleted).toBe(true);
  expect(third.deleted_at).toBe(first.deleted_at);
});

test('two DELETEs sent at once: both 200, exactly one deletes, both report the same time', async () => {
  const created = await publish('at once');
  expect(await publicIds()).toContain(created.id);

  const answers = await Promise.all([remove(created.id), remove(created.id)]);
  const [a, b] = await Promise.all(answers.map((response, n) => body(response, `simultaneous DELETE ${n + 1}`)));

  expect([a.already_deleted, b.already_deleted].sort(), 'exactly one call deleted').toEqual([false, true]);
  const [first, second] = a.already_deleted ? [b, a] : [a, b];
  expectSameDeletion(first, second, created.id);
  expect(await publicIds()).not.toContain(created.id);
  expect(await mine()).not.toContain(created.id);
});
