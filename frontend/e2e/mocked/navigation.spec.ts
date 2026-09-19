import { test, expect, Page, Locator } from '@playwright/test';
import { stubBackend, dayPayload, Json } from '../support/api-stub';

/**
 * Navigation, layout and honesty of the marketing surface.
 *
 * These run in both the desktop and the mobile project, so a layout that only works at one width
 * fails here.
 */

const PUBLIC_PAGES = ['/', '/predictions/today', '/predictions/tomorrow', '/leagues'];

for (const path of PUBLIC_PAGES) {
  test(`${path} renders and does not scroll sideways`, async ({ page }) => {
    await stubBackend(page, { day: d => dayPayload(d) });
    await page.goto(path);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('body')).toBeVisible();
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

test('every internal link points at a route that renders', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const hrefs = await page.locator('a[href^="/"]').evaluateAll(links =>
    [...new Set(links.map(a => (a as HTMLAnchorElement).getAttribute('href') || ''))]
      .filter(href => href && !href.startsWith('//') && !href.startsWith('/#')));

  const broken: string[] = [];
  for (const href of hrefs) {
    await page.goto(href);
    await page.waitForLoadState('domcontentloaded');
    const text = await page.locator('body').innerText();
    if (/404|page not found/i.test(text)) broken.push(href);
  }
  expect(broken, `dead links: ${broken.join(', ')}`).toEqual([]);
});

test('no image falls back to a third-party placeholder host', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const sources = await page.locator('img').evaluateAll(images =>
    images.map(img => (img as HTMLImageElement).getAttribute('src') || ''));
  const external = sources.filter(src => /via\.placeholder\.com|placehold\.it|placekitten/.test(src));
  expect(external, `placeholder hosts in use: ${external.join(', ')}`).toEqual([]);
});

test('every image either loads or falls back to a local asset', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);

  const broken = await page.locator('img').evaluateAll(images =>
    images
      .filter(img => {
        const image = img as HTMLImageElement;
        return image.complete && image.naturalWidth === 0;
      })
      .map(img => (img as HTMLImageElement).src));
  expect(broken, `images that failed to load: ${broken.join(', ')}`).toEqual([]);
});

test('the home page publishes no unmeasured performance claim', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const text = (await page.locator('body').innerText()).toLowerCase();
  // Scoring a forecast needs settled results; none have been scored, so no such figure can be true.
  expect(text).not.toMatch(/accuracy rate/);
  expect(text).not.toMatch(/success rate/);
  expect(text).not.toMatch(/active users/);
  expect(text).not.toMatch(/\d+% accurate/);
  expect(text).not.toMatch(/from last month/);
  // the footer appears on every page and used to promise accuracy too
  expect(text).not.toMatch(/accurate match predictions/);
  expect(text).not.toMatch(/thousands of successful/);
});

test('the footer makes no promise the site does not keep', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // a link that goes nowhere is a promise the site does not keep
  const deadLinks = await page.locator('a[href="#"]').count();
  expect(deadLinks).toBe(0);

  // nobody's credentials have been reviewed, so nothing may claim they were
  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).not.toContain('verified expert');
});

test('the footer copyright year is current, not frozen', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const text = await page.locator('body').innerText();
  expect(text).toContain(`© ${new Date().getFullYear()}`);
});

/**
 * Header search.
 *
 * These used to type a query and then only check the page contained no "undefined" and no "NaN",
 * which a search box that silently does nothing also passes. What matters is what the reader is
 * told: the matching club when there is one, an explicit "no results" when there is not, and
 * something other than a false "no results" when the request failed.
 *
 * SearchDropdown (src/components/layout/SearchDropdown.tsx) waits for three characters and debounces
 * for 400 ms before calling the backend, so each test types a real query and waits for the request.
 */
const ARSENAL_RESULTS = {
  teams: [
    { id: 'team-arsenal', name: 'Arsenal', short_name: 'ARS', logo: '/teams/default.svg', country: 'England' },
    { id: 'team-arsenal-w', name: 'Arsenal Women', short_name: 'ARSW', logo: '/teams/default.svg', country: 'England' },
  ] as Json[],
  competitions: [
    {
      id: 'comp-premier-league', key: 'premier_league', name: 'Premier League', country: 'England',
      country_code: 'ENG', logo: '/leagues/default.svg', is_cup: false, providers: {},
    },
  ] as Json[],
};

/** The header search box, reached through the menu button on the narrow layout. */
async function openSearch(page: Page): Promise<Locator> {
  const menu = page.getByRole('button', { name: /menu|open main menu/i }).first();
  if (await menu.count() > 0 && await menu.isVisible()) await menu.click();
  return page.locator('input[type="search"], input[placeholder*="Search" i]')
    .filter({ visible: true }).first();
}

/** Type `query` and wait for the search request the component makes after its debounce. */
async function searchFor(page: Page, query: string): Promise<Locator> {
  const box = await openSearch(page);
  await expect(box, 'the header must offer a search box on this layout').toHaveCount(1);
  const answered = page.waitForResponse(r => r.url().includes('/api/v1/teams/search'));
  await box.fill(query);
  await answered;
  return box;
}

test('search lists the clubs and competitions that match', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    teamSearch: () => ARSENAL_RESULTS,
  });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await searchFor(page, 'Arsenal');

  // the matching club is actually listed, by name, with its country
  await expect(page.getByRole('button', { name: /Arsenal\s+England/ }).first()).toBeVisible();
  await expect(page.getByText('Arsenal Women', { exact: true })).toBeVisible();
  await expect(page.getByText('Premier League', { exact: true }).first()).toBeVisible();
  // and the counts the dropdown prints match what the backend returned
  await expect(page.getByText('Teams (2)', { exact: true })).toBeVisible();
  await expect(page.getByText('Leagues (1)', { exact: true })).toBeVisible();

  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).not.toContain('undefined');
  expect(text).not.toContain('nan');
});

test('a search with no matches says so instead of showing a blank panel', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    teamSearch: () => ({ teams: [], competitions: [] }),
  });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await searchFor(page, 'Nowhere Athletic');

  await expect(page.getByText(/no results found for "Nowhere Athletic"/i)).toBeVisible();
  await expect(page.getByText(/try a different search term/i)).toBeVisible();
});

/**
 * A search that failed must not be reported as a search that found nothing.
 *
 * search.service.ts used to catch every error and return an empty result, so a 500 from the API
 * produced "No results found for Arsenal" — a statement about the world, manufactured from a
 * network error. The service now lets the failure reach the component's own error branch.
 */
test('a failed search reports the failure, not an empty result', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    fail: url => (url.includes('/teams/search') ? 500 : null),
  });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await searchFor(page, 'Arsenal');

  await expect(page.getByText(/failed to search/i)).toBeVisible();
  // and it must NOT claim there is no such club
  await expect(page.getByText(/no results found for "Arsenal"/i)).toHaveCount(0);
});

/**
 * The competition filter while the day is still arriving.
 *
 * An independent reviewer opened the desktop filters during a load, waited ten seconds for a
 * competition option that never appeared, and recorded it as an unexplained failure. It was not a
 * hang. The options are derived from the fixtures, so before those arrive there are none, and the
 * whole strip was guarded on having more than one competition — which meant it was absent from
 * the document rather than empty. An absent control and a control with nothing in it read exactly
 * the same to a reader and to a test, and neither was the truth.
 */
test('the competition filter says it is loading rather than not existing', async ({ page }) => {
  let releaseDay: (() => void) | null = null;
  const held = new Promise<void>(resolve => { releaseDay = resolve; });

  await stubBackend(page, { day: d => dayPayload(d) });
  // Hold the day's fixtures open so the loading window is long enough to look at.
  await page.route('**/api/v1/matches**', async route => {
    await held;
    await route.fallback();
  });

  const navigation = page.goto('/matches');

  const loading = page.getByTestId('competition-chip-row-loading');
  await expect(loading, 'the strip exists and explains itself while the day is arriving')
    .toBeVisible();
  await expect(loading).toHaveAttribute('role', 'status');
  // And it is not pretending to offer a filter it cannot yet populate.
  await expect(page.getByTestId('competition-chip-row')).toHaveCount(0);

  releaseDay!();
  await navigation;
  await page.waitForLoadState('networkidle');

  // Once the fixtures land the real strip replaces it, and the placeholder goes.
  await expect(page.getByTestId('competition-chip-row')).toBeVisible();
  await expect(page.getByTestId('competition-chip-row-loading')).toHaveCount(0);
});
