import { test, expect } from '@playwright/test';
import { apiContext } from '../support/qa-account';
import { ApiMatch } from '../support/api-stub';

/**
 * What the running local stack actually serves.
 *
 * Read-only, and every request uses the database and cache the backend already holds, so no
 * provider request is issued and no trial allowance is spent.
 */

/**
 * ASSERT THE RULE, NOT TODAY'S ANSWER.
 *
 * An earlier version of this test read `expect(coverage.accuracy_available).toBe(false)` and
 * `not.toContain('accuracy rate')`. Both were true of the installation on the day they were
 * written, when nothing had been settled yet, and neither is a rule the application promises: the
 * settlement pass keeps scoring, and the moment a source crosses the minimum sample the backend is
 * SUPPOSED to start publishing a figure. A test that pins a transient state fails on the day the
 * thing it is watching finally works, and it reads as a regression when it is the opposite.
 *
 * So what is pinned here is the relationship. The sample rule decides availability, the payload
 * agrees with itself about which side of it we are on, and the page says the same thing the
 * backend does. All three hold whether or not enough has been scored today.
 */
test('the coverage figures the home page shows are measured, not invented', async ({ page }) => {
  const api = await apiContext();
  const response = await api.get('/api/v1/data-providers/coverage');
  expect(response.ok()).toBeTruthy();
  const coverage = await response.json();

  // The payload must not contradict itself: one flag, one state and one reason, all agreeing.
  expect(coverage.accuracy_available).toBe(coverage.accuracy_state === 'available');
  expect(coverage.accuracy_unavailable_reason === null).toBe(coverage.accuracy_available);

  // And availability is the minimum-sample rule, not a mood. Below the sample nothing may be
  // published; at or above it the figure is owed, because withholding a measured rate is as
  // misleading as publishing an unmeasured one.
  const { scored, minimum_sample: minimum, published_figures: published } = coverage.scoring;
  expect(coverage.accuracy_available, `scored ${scored} against a minimum sample of ${minimum}`)
    .toBe(scored >= minimum);
  expect(published > 0).toBe(coverage.accuracy_available);

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const text = await page.locator('body').innerText();
  expect(text).toContain(String(coverage.competitions_covered));

  // The page must not disagree with the backend in either direction. When a figure is withheld the
  // reader is told so, in the backend's own words; when one is published that sentence must be
  // gone, or the page would deny a measurement it is showing.
  const withheld = 'No accuracy figure is shown';
  if (coverage.accuracy_available) {
    expect(text, 'the page claimed no accuracy was available while the backend published one')
      .not.toContain(withheld);
  } else {
    expect(text).toContain(withheld);
    expect(text).toContain(coverage.accuracy_unavailable_reason);
  }
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
