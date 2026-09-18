import { test, expect } from '@playwright/test';
import { stubBackend, dayPayload } from '../support/api-stub';

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

test('the footer copyright year is current, not frozen', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const text = await page.locator('body').innerText();
  expect(text).toContain(`© ${new Date().getFullYear()}`);
});

test('search accepts a query and reports its result honestly', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // On the narrow layout the search box lives behind the menu button; open it first.
  const menu = page.getByRole('button', { name: /menu|open main menu/i }).first();
  if (await menu.count() > 0 && await menu.isVisible()) await menu.click();

  const search = page.locator('input[type="search"], input[placeholder*="Search" i]')
    .filter({ visible: true }).first();
  if (await search.count() === 0) {
    test.skip(true, 'no visible search input on this layout');
    return;
  }
  await search.fill('Arsenal');
  await page.waitForTimeout(800);
  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).not.toContain('undefined');
  expect(text).not.toContain('nan');
});
