import { test, expect } from '@playwright/test';
import { apiContext } from '../support/qa-account';
import { ApiMatch } from '../support/api-stub';

/**
 * What the running local stack actually serves.
 *
 * Read-only, and every request uses the database and cache the backend already holds, so no
 * provider request is issued and no trial allowance is spent.
 */

test('the coverage figures the home page shows are measured, not invented', async ({ page }) => {
  const api = await apiContext();
  const response = await api.get('/api/v1/data-providers/coverage');
  expect(response.ok()).toBeTruthy();
  const coverage = await response.json();

  // The backend must refuse to publish an accuracy figure while nothing has been scored
  expect(coverage.accuracy_available).toBe(false);

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const text = await page.locator('body').innerText();
  expect(text).toContain(String(coverage.competitions_covered));
  expect(text.toLowerCase()).not.toContain('accuracy rate');
  await api.dispose();
});

test('a stored forecast renders with the same numbers the API serves', async ({ page }) => {
  const api = await apiContext();
  const today = new Date().toISOString().slice(0, 10);
  const response = await api.get(`/api/v1/matches?date=${today}&refresh=false`);
  const body = await response.json();
  const withForecast = (body.matches || []).find((m: ApiMatch) => m.forecast?.markets_available?.match_result);
  test.skip(!withForecast, 'no match with a 1X2 forecast in the local database today');

  await page.goto(`/match/${withForecast.id}`);
  await page.waitForLoadState('networkidle');
  const text = await page.locator('body').innerText();

  const expected = Math.round(withForecast.forecast.home_win_prob * 100);
  expect(text).toContain(`${expected}%`);
  await api.dispose();
});

test('three distinct forecast timestamps reach the API', async () => {
  const api = await apiContext();
  const today = new Date().toISOString().slice(0, 10);
  const response = await api.get(`/api/v1/matches?date=${today}&refresh=false`);
  const body = await response.json();
  const withForecast = (body.matches || []).find((m: ApiMatch) => m.forecast);
  test.skip(!withForecast, 'no forecast in the local database today');

  const forecast = withForecast.forecast;
  expect(forecast).toHaveProperty('model_run_at');
  expect(forecast).toHaveProperty('provider_updated_at');
  expect(forecast).toHaveProperty('fetched_at');
  expect(forecast).toHaveProperty('generated_at_known');
  // fetched_at is when WE retrieved it and must always be known
  expect(forecast.fetched_at).toBeTruthy();
  await api.dispose();
});

test('no provider request is spent by browsing', async () => {
  const api = await apiContext();
  const before = await (await api.get('/api/v1/data-providers/status')).json();
  const today = new Date().toISOString().slice(0, 10);
  await api.get(`/api/v1/matches?date=${today}&refresh=false`);
  await api.get('/api/v1/leagues');
  const after = await (await api.get('/api/v1/data-providers/status')).json();

  expect(after.forecasts.budget?.used_today ?? 0).toBe(before.forecasts.budget?.used_today ?? 0);
  await api.dispose();
});
