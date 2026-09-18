import { test, expect, APIRequestContext } from '@playwright/test';
import { ApiMatch } from '../support/api-stub';
import {
  apiContext, ensureQaExpertToken, cleanupQaPredictions, anyUpcomingMatch, publishQaPrediction,
  classifyQaPrediction, QA_EXPERT, QA_REASONING_MARKER,
} from '../support/qa-account';

/**
 * Expert publishing, end to end, against the local backend and the real local data.
 *
 * The owner's rule is that an expert publishes directly: no admin approval step, and the prediction
 * is public immediately. These tests only create and remove their own records, and they never
 * trigger a provider refresh, so they spend no trial allowance.
 *
 * Every record created here asks to be classified as test data, server-side, so measured
 * performance leaves it out. The "[e2e-qa]" string in the reasoning is a label for a human reading
 * the database and decides nothing - see support/qa-account.ts.
 */

let api: APIRequestContext;
let token: string;
let match: ApiMatch;

test.beforeAll(async () => {
  api = await apiContext();
  token = await ensureQaExpertToken(api);
  await cleanupQaPredictions(api, token);
  match = await anyUpcomingMatch(api);
  test.skip(!match, 'no upcoming fixture in the local database to attach a prediction to');
});

test.beforeEach(async () => {
  // every test starts with none of this suite's records present, so counts are deterministic
  await cleanupQaPredictions(api, token);
});

test.afterAll(async () => {
  if (api && token) await cleanupQaPredictions(api, token);
  await api?.dispose();
});

const publish = async (overrides: Record<string, unknown> = {}) =>
  publishQaPrediction(api, token, {
    match_id: match.id,
    home_win_prob: 0.55,
    draw_prob: 0.25,
    away_win_prob: 0.2,
    confidence_score: 0.7,
    reasoning: `${QA_REASONING_MARKER} home side has the stronger recent form`,
    ...overrides,
  });

test('a published prediction needs no approval and is public immediately', async ({ page }) => {
  const created = await publish();

  // The owner's rule: publishing is direct. Nothing may sit in a pending state waiting for an admin.
  expect(String(created.status).toLowerCase()).toBe('published');
  expect(created.published_at).toBeTruthy();

  // Visible on the public API straight away, with no refresh and no provider call
  const publicView = await api.get(`/api/v1/matches/${match.id}`);
  expect(publicView.ok()).toBeTruthy();
  const body = await publicView.json();
  expect(body.expert_prediction).not.toBeNull();
  expect(body.expert_prediction.reasoning).toContain(QA_REASONING_MARKER);

  // And on the public page a visitor would open
  await page.goto(`/match/${match.id}`);
  await page.waitForLoadState('networkidle');
  const text = await page.locator('body').innerText();
  expect(text.toLowerCase()).toContain('expert');
  expect(text).toContain('home side has the stronger recent form');
});

test('an expert prediction is shown apart from the model forecast', async ({ page }) => {
  await publish();
  await page.goto(`/match/${match.id}`);
  await page.waitForLoadState('networkidle');
  const text = (await page.locator('body').innerText()).toLowerCase();

  expect(text).toContain('expert');
  // the model forecast keeps its own attribution rather than being merged into the expert's
  if (match.forecast) {
    expect(text).toMatch(/gameforecast|model/);
  }
});

test('editing a published prediction updates the public view', async ({ page }) => {
  const created = await publish();
  // the update endpoint replaces the prediction, so the whole 1X2 block goes with it
  const edited = await api.put(`/api/v1/expert/predictions/${created.id}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      home_win_prob: 0.62, draw_prob: 0.22, away_win_prob: 0.16, confidence_score: 0.75,
      reasoning: `${QA_REASONING_MARKER} revised after the team news`,
    },
  });
  expect(edited.status(), await edited.text()).toBeLessThan(300);
  // publishing is direct, and an edit must not send it back to a pending state
  expect(String((await edited.json()).status).toLowerCase()).toBe('published');

  const publicView = await api.get(`/api/v1/matches/${match.id}`);
  const body = await publicView.json();
  expect(body.expert_prediction.reasoning).toContain('revised after the team news');
  expect(Number(body.expert_prediction.home_win_prob)).toBeCloseTo(0.62, 2);

  await page.goto(`/match/${match.id}`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('body')).toContainText('revised after the team news');
});

test('deleting a prediction removes it from the public view immediately', async ({ page }) => {
  const created = await publish();
  const deleted = await api.delete(`/api/v1/expert/predictions/${created.id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(deleted.status(), await deleted.text()).toBeLessThan(300);

  const publicView = await api.get(`/api/v1/matches/${match.id}`);
  const body = await publicView.json();
  const reasoning = body.expert_prediction?.reasoning ?? '';
  expect(reasoning).not.toContain('stronger recent form');

  await page.goto(`/match/${match.id}`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('body')).not.toContainText('stronger recent form');
});

test('a record the suite creates is classified as test data, by a flag and not by its text', async () => {
  const created = await publish();

  test.skip(
    created.is_test_data !== true,
    'this backend runs without ALLOW_TEST_DATA_CLASSIFICATION, so nothing can be classified as ' +
      'test data here. Set it (it is off by default and must stay off where real predictions are ' +
      'published) to exercise this.',
  );

  // the classification is a stored field, not a reading of the reasoning
  expect(created.is_test_data).toBe(true);

  // and it can be applied afterwards too, which is how a record created through the composer UI
  // gets classified: the application's own request does not ask for it
  const second = await publish({ reasoning: `${QA_REASONING_MARKER} a second record` });
  expect(await classifyQaPrediction(api, token, second.id)).toBe(true);
});

test('the QA label in the reasoning is a label, not a mechanism', async () => {
  // A record carrying the marker but NOT classified is an ordinary record as far as the backend is
  // concerned. Nothing may key off this text: an expert who typed it must still be measured.
  const created = await publish({ is_test_data: false });
  expect(created.reasoning).toContain(QA_REASONING_MARKER);
  expect(created.is_test_data).not.toBe(true);
});

test('an expert signs in through the UI and reaches the match picker', async ({ page }) => {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');

  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /sign in|log in/i }).first().click();
  // the redirect follows the auth response, so wait for the route to change rather than for the
  // network to fall idle - the login page itself goes idle before the token comes back
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15_000 });

  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');
  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).toContain('match');
  expect(text).not.toContain('unauthorized');
});
