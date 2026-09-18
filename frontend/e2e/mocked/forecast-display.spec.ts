import { test, expect } from '@playwright/test';
import {
  stubBackend, dayPayload, baseMatches, withoutMarkets, withOnePercentFavourite,
  withoutForecast, watchForProblems,
} from '../support/api-stub';

/**
 * How a model forecast is allowed to appear on screen.
 *
 * The rule under test throughout: a market the provider did not publish is UNAVAILABLE. It is never
 * 0%, never a guessed complement, and never a renormalised scoreline list.
 */

test.describe('forecast probabilities', () => {
  test('a 1% probability reads as 1%, not 100%', async ({ page }) => {
    // The parser used to infer the 0-100 scale from whether values exceeded 1, so a genuine 1%
    // became certainty. This is the regression guard for that.
    const [first, ...rest] = baseMatches();
    const match = withOnePercentFavourite(first);
    await stubBackend(page, {
      day: d => dayPayload(d, [match, ...rest]),
      matchById: () => match,
    });

    await page.goto(`/match/${match.id}`);
    const body = page.locator('body');
    await expect(body).toContainText('1%');
    await expect(body).not.toContainText('100%');
  });

  test('probabilities are shown as whole percentages that never exceed 100', async ({ page }) => {
    await stubBackend(page, { day: d => dayPayload(d) });
    await page.goto('/predictions/today');
    await page.waitForLoadState('networkidle');

    const percentages = await page.locator('body').innerText();
    const values = [...percentages.matchAll(/(\d+(?:\.\d+)?)\s?%/g)].map(m => Number(m[1]));
    expect(values.length).toBeGreaterThan(0);
    for (const value of values) {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThanOrEqual(100);
    }
  });
});

test.describe('missing markets', () => {
  test('a forecast with no 1X2 market never shows a 0% outcome', async ({ page }) => {
    const [first, ...rest] = baseMatches();
    const match = withoutMarkets(first, ['match_result']);
    await stubBackend(page, {
      day: d => dayPayload(d, [match, ...rest]),
      matchById: () => match,
    });

    await page.goto(`/match/${match.id}`);
    await page.waitForLoadState('networkidle');
    const text = await page.locator('body').innerText();

    expect(text).not.toMatch(/Home Win\s*\(?\s*0\s?%/i);
    expect(text).not.toMatch(/Away Win\s*\(?\s*0\s?%/i);
    expect(text).not.toMatch(/Draw\s*\(?\s*0\s?%/i);
    expect(text.toLowerCase()).toContain('unavailable');
  });

  test('a forecast with only both-teams-to-score still renders that market', async ({ page }) => {
    const [first, ...rest] = baseMatches();
    const match = withoutMarkets(first, ['match_result', 'over_under_25', 'over_under_35', 'exact_score']);
    await stubBackend(page, {
      day: d => dayPayload(d, [match, ...rest]),
      matchById: () => match,
    });

    await page.goto(`/match/${match.id}`);
    await page.waitForLoadState('networkidle');
    const text = (await page.locator('body').innerText()).toLowerCase();

    expect(text).toContain('both teams');
    expect(text).toContain('unavailable');
  });

  test('a forecast with only an exact score does not invent the other markets', async ({ page }) => {
    const [first, ...rest] = baseMatches();
    const match = withoutMarkets(first, ['match_result', 'btts', 'over_under_25', 'over_under_35']);
    await stubBackend(page, {
      day: d => dayPayload(d, [match, ...rest]),
      matchById: () => match,
    });

    await page.goto(`/match/${match.id}`);
    await page.waitForLoadState('networkidle');
    const text = (await page.locator('body').innerText()).toLowerCase();
    expect(text).toContain('unavailable');
    expect(text).not.toMatch(/\b0\.0\s?%/);
    expect(text).not.toContain('nan');
  });

  test('a match with no forecast at all says so plainly', async ({ page }) => {
    const [first, ...rest] = baseMatches();
    const match = withoutForecast(first);
    await stubBackend(page, {
      day: d => dayPayload(d, [match, ...rest]),
      matchById: () => match,
    });

    await page.goto(`/match/${match.id}`);
    await page.waitForLoadState('networkidle');
    const text = (await page.locator('body').innerText()).toLowerCase();
    expect(text).toMatch(/no (model )?forecast|unavailable|not available/);
    expect(text).not.toContain('nan');
  });
});

test.describe('bookmaker odds', () => {
  test('absent odds are reported as unavailable, never invented', async ({ page }) => {
    const matches = baseMatches();
    await stubBackend(page, { day: d => dayPayload(d, matches), matchById: () => matches[0] });
    await page.goto(`/match/${matches[0].id}`);
    await page.waitForLoadState('networkidle');
    const text = (await page.locator('body').innerText()).toLowerCase();
    expect(text).toMatch(/odds (are )?(not available|unavailable)/);
  });
});

test.describe('page health', () => {
  test('today renders without console errors or failed requests', async ({ page }) => {
    const problems = watchForProblems(page);
    await stubBackend(page, { day: d => dayPayload(d) });
    await page.goto('/predictions/today');
    await page.waitForLoadState('networkidle');

    expect(problems.failedRequests).toEqual([]);
    expect(problems.consoleErrors.filter(e => !e.includes('favicon'))).toEqual([]);
  });

  test('a match detail page renders without console errors', async ({ page }) => {
    const problems = watchForProblems(page);
    const matches = baseMatches();
    await stubBackend(page, { day: d => dayPayload(d, matches), matchById: () => matches[0] });
    await page.goto(`/match/${matches[0].id}`);
    await page.waitForLoadState('networkidle');

    expect(problems.failedRequests).toEqual([]);
    expect(problems.consoleErrors.filter(e => !e.includes('favicon'))).toEqual([]);
  });
});
