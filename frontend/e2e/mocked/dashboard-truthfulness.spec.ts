import { test, expect, Page } from '@playwright/test';
import { stubBackend, dayPayload } from '../support/api-stub';
import { signIn, regularUser } from '../support/auth';

/**
 * Pages that used to show invented user statistics.
 *
 * Results settlement is not implemented, so there is no accuracy, streak, profit or win-rate
 * figure that could be true. The correct output is an honest empty state.
 *
 * The dashboard is behind ProtectedRoute. An earlier version of this file navigated to /dashboard
 * signed out, was redirected to /login, and then checked that the page showed no win rate and no
 * profit — which a sign-in form never does. It proved nothing. Every test here signs in first and
 * proves it is looking at the dashboard before it asserts anything about the dashboard's honesty.
 */

/**
 * The "Your prediction record" card.
 *
 * DashboardPage marks it `data-testid="dashboard-no-record"`, but src/components/ui/Card.tsx takes
 * only children/className/hover, so that attribute never reaches the DOM and getByTestId finds
 * nothing. Reported for the owner of those files; until Card forwards the attribute, this anchors
 * on the heading, which is really rendered.
 */
const recordPanel = (page: Page) =>
  page.locator('.card').filter({ has: page.getByRole('heading', { name: 'Your prediction record' }) });

/** Fails unless the dashboard itself rendered — not the login form it redirects an anonymous visitor to. */
async function expectOnDashboard(page: Page, email: string): Promise<void> {
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Dashboard', level: 1 })).toBeVisible();
  await expect(recordPanel(page)).toBeVisible();
  // the signed-in identity the page shows is the one we signed in as, so the session is real
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  // and the sign-in form is definitively not what we are looking at
  await expect(page.getByRole('heading', { name: /sign in to your account/i })).toHaveCount(0);
}

test('the dashboard is not reachable without signing in', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  // The guard that makes the assertions below meaningful: prove it still works.
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Dashboard', level: 1 })).toHaveCount(0);
  await expect(recordPanel(page)).toHaveCount(0);
});

test('the dashboard shows no fabricated performance figures', async ({ page }) => {
  const user = regularUser();
  await stubBackend(page, { day: d => dayPayload(d) });
  await signIn(page, { user });

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expectOnDashboard(page, user.email);

  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).not.toMatch(/win rate|winning streak|total profit|roi/);
  expect(text).not.toMatch(/\$\s?\d/);
  expect(text).not.toContain('nan');
  expect(text).not.toContain('undefined');
});

test('the dashboard says plainly that no record has been scored', async ({ page }) => {
  const user = regularUser();
  await stubBackend(page, { day: d => dayPayload(d) });
  await signIn(page, { user });

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expectOnDashboard(page, user.email);

  // An empty state is only honest if it explains itself; a blank panel would not.
  const record = recordPanel(page);
  await expect(record).toContainText(/not settled against final results/i);
  await expect(record).toContainText(/no accuracy rate/i);
});

test('the coverage counts are labelled site-wide, not as the reader\'s own record', async ({ page }) => {
  const user = regularUser();
  await stubBackend(page, { day: d => dayPayload(d) });
  await signIn(page, { user });

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expectOnDashboard(page, user.email);

  // e2e/fixtures/coverage.json: 6 competitions, 48 upcoming, 30 forecast, 0 expert predictions,
  // accuracy_available false. The page must show those measured numbers and no invented one.
  const stats = page.getByTestId('dashboard-site-stat');
  await expect(stats).toHaveCount(4);
  await expect(stats.filter({ hasText: 'Competitions covered' })).toContainText('6');
  await expect(stats.filter({ hasText: 'Upcoming fixtures loaded' })).toContainText('48');
  await expect(stats.filter({ hasText: 'Model forecasts available' })).toContainText('30');
  await expect(page.getByText(/site-wide counts measured from stored data/i)).toBeVisible();
  await expect(page.getByText(/no accuracy figure is shown/i)).toBeVisible();
});

test('a dashboard whose coverage endpoint fails says so instead of showing a number', async ({ page }) => {
  const user = regularUser();
  await stubBackend(page, {
    day: d => dayPayload(d),
    fail: url => (url.includes('/data-providers/coverage') ? 503 : null),
  });
  await signIn(page, { user });

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expectOnDashboard(page, user.email);

  await expect(page.getByText(/coverage endpoint could not be reached/i)).toBeVisible();
  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).not.toContain('nan');
  expect(text).not.toContain('undefined');
  expect(text).toContain('unavailable');
});
