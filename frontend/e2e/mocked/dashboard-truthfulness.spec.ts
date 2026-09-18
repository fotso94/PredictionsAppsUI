import { test, expect } from '@playwright/test';
import { stubBackend, dayPayload } from '../support/api-stub';

/**
 * Pages that used to show invented user statistics.
 *
 * Results settlement is not implemented, so there is no accuracy, streak, profit or win-rate
 * figure that could be true. The correct output is an honest empty state.
 */

test('the dashboard shows no fabricated performance figures', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).not.toMatch(/win rate|winning streak|total profit|roi/);
  expect(text).not.toMatch(/\$\s?\d/);
  expect(text).not.toContain('nan');
});
