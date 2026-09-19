import { test, expect, Locator, Page, Request } from '@playwright/test';
import { dayPayload, stubBackend } from '../support/api-stub';
import { regularUser, signIn } from '../support/auth';

/**
 * What a reader on an expensive megabyte actually downloads, and the two promises that come with
 * reducing it.
 *
 * WHY THIS FILE EXISTS. The matchday route was measured at 360x740 against a production build
 * served the way a production host serves it: on 2026-09-19, 2,440.5 kB transferred across 56
 * requests on a cold visit, of which 2,164.1 kB and 48 requests were club crests drawn at 16-24px.
 * Splitting the bundle took the JavaScript from 199.2 kB transferred to 146.2 kB. Text-only mode
 * took the whole cold visit to 223.5 kB and a second date to 14.3 kB — the second date including
 * its 13.3 kB of API payload, which is most of what is left once the images are gone. The numbers
 * live in the report; what lives here is the behaviour they depend on, so that a later change
 * cannot quietly undo them.
 *
 * THE FOUR THINGS ASSERTED, AND WHY EACH IS A PROMISE AND NOT A PREFERENCE:
 *
 *  1. Text-only mode really does not fetch. Not hidden, not deferred — not requested. `display:
 *     none` would have satisfied a screenshot and cost the reader every byte anyway, so the test
 *     counts requests, not pixels.
 *  2. Splitting the bundle did not break a route. Every lazy boundary has a loading state, and
 *     that state neither invents content nor flashes: on a chunk that arrives quickly, nothing is
 *     announced at all.
 *  3. Nothing cached is presented as live. Turning the reading mode on must not change one word of
 *     what the freshness block says about how old the stored data is — so the test compares the
 *     sentence in both modes and requires it to be identical.
 *  4. None of it spends the provider's allowance. Filtering, changing the date, reloading and
 *     toggling the mode are all reads of stored rows: every `/matches` call must carry
 *     `refresh=false`, because the backend's own default is `refresh=True` and an omission would
 *     send a request to a provider whose allowance is spent.
 *
 * Every backend payload is stubbed from e2e/support/api-stub.ts. Crest images are answered locally
 * too — see CREST_HOSTS — so this file, unlike a plain page load, reaches no third-party host at
 * all while still proving the requests were made.
 */

/** A one-pixel PNG. Enough to be a real image response; small enough to be free. */
const PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
);

/**
 * Where club crests and competition badges come from. The captured fixtures point at the live
 * score provider's CDN, and the two local SVGs are the fallbacks in src/components/ui/imageFallback.ts.
 */
const CREST_PATTERN = /cdn\.live-score-api\.com|media\.api-sports\.io|\/teams\/default\.svg|\/leagues\/default\.svg/;

interface Traffic {
  /** Every request the page made, in order. */
  all: string[];
  /** The subset that was a club crest or competition badge. */
  crests: string[];
}

/**
 * Stub the backend, answer crest images locally, and record everything.
 *
 * Returns the running tally, which the assertions read at the end of the test rather than at the
 * moment of each gesture: a provider request fired late — by a retry, a debounce, an effect on
 * unmount — would still be caught.
 */
async function harness(page: Page): Promise<Traffic> {
  const traffic: Traffic = { all: [], crests: [] };

  page.on('request', (request: Request) => {
    const url = request.url();
    traffic.all.push(url);
    if (CREST_PATTERN.test(url)) traffic.crests.push(url);
  });

  await page.route(CREST_PATTERN, route =>
    route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL_PNG }),
  );
  await stubBackend(page, { day: d => dayPayload(d) });

  // Record every moment the loading state actually says something, so "it does not flash" can be
  // asserted as an absence rather than hoped for.
  //
  // The observer watches `document`, not `document.documentElement`. An init script runs before
  // the document element exists, and in WebKit that made `observe()` throw — which silently
  // skipped every init script registered after this one, signed the expert out, and left the
  // announcement list empty for the wrong reason. Watching the Document node itself covers the
  // same tree and exists from the start.
  await page.addInitScript(() => {
    const announcements: string[] = [];
    (window as unknown as { __routeLoadingSaid: string[] }).__routeLoadingSaid = announcements;
    const look = () => {
      const said = document.querySelector('[data-testid="route-loading"] [role="status"]');
      if (said && said.textContent) announcements.push(said.textContent.trim());
    };
    new MutationObserver(look).observe(document, { childList: true, subtree: true });
  });

  return traffic;
}

/** Nothing anywhere may ask a provider to go and fetch. */
function expectNoProviderRequest(traffic: Traffic): void {
  const refreshing = traffic.all.filter(url => /[?&]refresh=true/i.test(url));
  expect(refreshing, 'no request may ask the backend to refresh from a provider').toEqual([]);

  // Stronger than the line above: `GET /matches` is declared `refresh: bool = Query(True)` on the
  // backend, so leaving the parameter off is the same as asking for a provider request.
  const dayReads = traffic.all.filter(url => /\/api\/v1\/matches(\?|$)/.test(url));
  expect(dayReads.length, 'the matchday route must read the day at least once').toBeGreaterThan(0);
  for (const url of dayReads) {
    expect(new URL(url).searchParams.get('refresh'), `${url} must read stored rows only`).toBe('false');
  }
}

/**
 * The switch, wherever this viewport keeps it: on the wide bar at `lg` and above, and inside the
 * menu panel below it. Opening the menu is part of the journey a phone reader actually takes.
 */
async function lowDataSwitch(page: Page): Promise<Locator> {
  const onTheBar = page.getByTestId('low-data-toggle-bar');
  if (await onTheBar.isVisible()) return onTheBar;

  // The panel stays open after a tap on the switch — the reader may well want to change something
  // else — so a second call finds it already there rather than trying to open it twice.
  const inTheMenu = page.getByTestId('low-data-toggle-menu');
  if (await inTheMenu.isVisible()) return inTheMenu;

  const menuButton = page.getByRole('button', { name: /open main menu/i });
  await expect(menuButton, 'below lg the switch lives in the menu, so the menu must be reachable').toBeVisible();
  await menuButton.click();
  await expect(inTheMenu).toBeVisible();
  return inTheMenu;
}

/** The widths at which the bar has to hold everything, `lg` first because it is the tightest. */
const WIDE_WIDTHS = [1024, 1100, 1280, 1440];

const sidewaysScroll = (page: Page): Promise<number> => page.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
);

async function openMatchday(page: Page): Promise<void> {
  await page.goto('/matches');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('matchday-workspace')).toBeVisible();
}

// ------------------------------------------------------------------ 1. the mode does not fetch

test('text-only mode is off until the reader asks, and the crests load while it is', async ({ page }) => {
  const traffic = await harness(page);
  await openMatchday(page);

  const toggle = await lowDataSwitch(page);
  await expect(toggle).toHaveAttribute('aria-checked', 'false');
  await expect(page.locator('html')).toHaveAttribute('data-low-data', 'off');

  // The default reader sees the football with its badges on, and pays for them.
  expect(traffic.crests.length, 'crests are requested when the mode is off').toBeGreaterThan(0);
  expect(await page.locator('img[src]').count()).toBeGreaterThan(0);

  expectNoProviderRequest(traffic);
});

test('with text-only mode on, not one crest is requested', async ({ page }) => {
  const traffic = await harness(page);
  await openMatchday(page);

  const toggle = await lowDataSwitch(page);
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('html')).toHaveAttribute('data-low-data', 'on');

  // Whatever the first, image-carrying load cost, the reader's choice applies from here on.
  const spentBeforeTheChoice = traffic.crests.length;
  traffic.crests.length = 0;

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('matchday-workspace')).toBeVisible();

  expect(spentBeforeTheChoice, 'the images-on load is the baseline this is measured against').toBeGreaterThan(0);
  expect(traffic.crests, 'a reload in text-only mode must request no crest at all').toEqual([]);

  // And the reason it costs nothing is that the elements are not asking for anything, rather than
  // asking and being hidden.
  const images = page.locator('img');
  expect(await images.count(), 'the fixture rows still render their image elements').toBeGreaterThan(0);
  expect(await page.locator('img[src]').count(), 'none of them carries a src').toBe(0);
  expect(await page.locator('img[srcset]').count(), 'and none of them carries a srcset either').toBe(0);

  // The football itself is untouched: this is a reading mode, not a reduced edition.
  await expect(page.getByTestId('fixture-list')).toBeVisible();
  expect(await page.getByTestId('fixture-row').count()).toBeGreaterThan(0);

  expectNoProviderRequest(traffic);
});

test('the choice persists, and turning it off brings the crests back', async ({ page }) => {
  const traffic = await harness(page);
  await openMatchday(page);

  await (await lowDataSwitch(page)).click();
  await expect(page.locator('html')).toHaveAttribute('data-low-data', 'on');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('html')).toHaveAttribute('data-low-data', 'on');
  await expect(await lowDataSwitch(page), 'a remembered choice is still shown as made')
    .toHaveAttribute('aria-checked', 'true');

  // Reversible, and without a reload: the withheld addresses are given back.
  traffic.crests.length = 0;
  await (await lowDataSwitch(page)).click();
  await expect(page.locator('html')).toHaveAttribute('data-low-data', 'off');
  await expect.poll(() => traffic.crests.length, {
    message: 'turning the mode off must let the images load again',
  }).toBeGreaterThan(0);
  expect(await page.locator('img[src]').count()).toBeGreaterThan(0);

  expectNoProviderRequest(traffic);
});

test('the switch says what the mode does, and does not promise offline reading', async ({ page }) => {
  await harness(page);
  await openMatchday(page);
  const toggle = await lowDataSwitch(page);

  const words = (await toggle.getAttribute('aria-label'))
    ?? (await page.getByTestId('low-data-toggle-menu').locator('xpath=..').innerText());

  expect(words.toLowerCase()).toContain('text-only');
  expect(words.toLowerCase()).toContain('images are not downloaded');
  // A data-saving mode that sounded like an offline mode would be a promise this makes no attempt
  // to keep: there is no service worker and nothing is stored.
  expect(words.toLowerCase()).not.toMatch(/works offline|available offline|offline mode|read offline/);
  // Nor may it advertise a saving it is in no position to calculate for this reader.
  expect(words).not.toMatch(/\d+\s*%|\d+\s*(kb|mb|gb)/i);
});

test('the switch does not push the wide header into a sideways scroll', async ({ page }) => {
  await harness(page);

  /**
   * The header is the one row in this application with a measured history of overflowing, and the
   * switch is 126px wide against 32px of slack at 1024. Putting it on the bar there cost 94px of
   * horizontal scroll — measured, then moved to `xl`. This is the test that keeps it moved: it
   * checks the overflow AND that the switch is still reachable at every width, because hiding a
   * control is an easy way to make an overflow test pass and a hard way to notice nobody can find
   * the setting any more.
   *
   * An expert carries a sixth entry on the bar, so both states are measured.
   */
  for (const width of WIDE_WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await openMatchday(page);
    expect(await sidewaysScroll(page), `signed out at ${width}px the document must not scroll sideways`)
      .toBeLessThanOrEqual(0);
    await expect(await lowDataSwitch(page), `the switch must be reachable at ${width}px`).toBeVisible();
  }
});

test('nor does it overflow for an expert, who carries a sixth entry on that bar', async ({ page }) => {
  await harness(page);
  await signIn(page, { user: regularUser({ role: 'expert', full_name: 'QA Expert' }) });

  for (const width of WIDE_WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await openMatchday(page);
    await expect(
      page.locator('header a[href="/expert/dashboard"]'),
      `the expert entry must actually be on the bar at ${width}px, or this measures nothing`,
    ).toBeVisible();
    expect(await sidewaysScroll(page), `as an expert at ${width}px the document must not scroll sideways`)
      .toBeLessThanOrEqual(0);
    await expect(await lowDataSwitch(page), `an expert must reach the switch at ${width}px`).toBeVisible();
  }
});

// ------------------------------------------------------- 2. splitting did not break the routes

test('a lazily loaded route still arrives, and the shell never leaves the screen', async ({ page }) => {
  const traffic = await harness(page);
  await openMatchday(page);

  await page.goto('/leagues');
  await page.waitForLoadState('networkidle');

  await expect(page.getByTestId('route-error')).toHaveCount(0);
  await expect(page.getByRole('link', { name: /soccer predictions, home/i })).toBeVisible();
  await expect(page.locator('main')).not.toBeEmpty();

  expectNoProviderRequest(traffic);
});

test('a chunk that arrives quickly says nothing at all', async ({ page }) => {
  await harness(page);

  // Warm the route once. The first visit in a run also pays for the dev server transforming the
  // module, which is a cost of the harness and not of the reader; the second visit is the one
  // that resembles a cached chunk, and it is the one asserted. The recorder is rebuilt on every
  // navigation, so the second visit starts from an empty list.
  await page.goto('/leagues');
  await page.waitForLoadState('networkidle');
  await openMatchday(page);

  await page.goto('/leagues');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('route-loading')).toHaveCount(0);

  const said = await page.evaluate(
    () => (window as unknown as { __routeLoadingSaid: string[] }).__routeLoadingSaid,
  );
  expect(said, 'a wait shorter than the delay must never be announced').toEqual([]);
});

test('a chunk that is slow says so, honestly, and draws no fixtures it does not have', async ({ page }) => {
  await harness(page);

  // Hold the route's own module back. Everything else — the shell, the header, the stylesheet —
  // arrives as usual, which is exactly the situation the loading state exists for.
  await page.route(/LeagueDetailPage|LeaguesPage/, async route => {
    await new Promise(resolve => setTimeout(resolve, 1500));
    await route.continue();
  });

  // `commit`, not the default `load`: the two engines in this suite issue the route's dynamic
  // import at different points relative to the load event, and waiting for load in WebKit means
  // waiting out the delay itself and arriving after the state under test has gone.
  await page.goto('/leagues', { waitUntil: 'commit' });

  const waiting = page.getByTestId('route-loading');
  await expect(waiting).toBeVisible();
  await expect(waiting).toContainText(/loading this page/i);

  // The one thing a loading state in this application may never do is stand in for content.
  const placeholder = (await waiting.innerText()).trim();
  expect(placeholder).toBe('Loading this page…');
  expect(placeholder).not.toMatch(/\d/);
  await expect(waiting.getByTestId('fixture-row')).toHaveCount(0);

  // And the reader keeps the navigation while they wait.
  await expect(page.getByRole('link', { name: /soccer predictions, home/i })).toBeVisible();

  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('route-loading')).toHaveCount(0);
  await expect(page.getByTestId('route-error')).toHaveCount(0);

  // The other half of the pair: this proves the recorder used by the test above really does fire,
  // so that "nothing was announced" there means the delay worked and not that nothing was watching.
  const said = await page.evaluate(
    () => (window as unknown as { __routeLoadingSaid: string[] }).__routeLoadingSaid,
  );
  expect(said.length, 'a wait this long must be announced').toBeGreaterThan(0);
});

test('a chunk that never arrives says so, and blames the download rather than the page', async ({ page }) => {
  await harness(page);

  // The failure splitting the bundle introduced: a dropped connection, or a deploy that replaced
  // the file this tab was told to ask for. Before the boundary existed this was a blank screen.
  await page.route(/LeagueDetailPage|LeaguesPage/, route => route.abort());
  await page.goto('/leagues');

  const failure = page.getByTestId('route-error');
  await expect(failure).toBeVisible();
  await expect(failure).toHaveAttribute('data-failure', 'not-downloaded');
  await expect(failure).toContainText(/could not be downloaded/i);
  await expect(failure.getByRole('button', { name: /reload the page/i })).toBeVisible();

  // It does not diagnose the reader's page as broken when the download is what failed, and it
  // says nothing at all about the data, because none arrived.
  await expect(failure).not.toContainText(/could not be shown/i);
  await expect(failure).not.toContainText(/stored data|last refreshed|up to date/i);

  // The navigation is still there to leave by.
  await expect(page.getByRole('link', { name: /soccer predictions, home/i })).toBeVisible();
});

test('and leaving by that navigation actually works, rather than carrying the failure along', async ({ page }) => {
  await harness(page);

  /**
   * The test above checks the link is on screen. This one checks it does something, because the
   * two came apart: React Router renders every route in this layout at the same position, so React
   * reconciles one error boundary across a navigation instead of mounting a new one. Measured on a
   * production build before the fix, aborting the `/leagues` chunk and then clicking Home left the
   * error sitting at `/`, and at every other lazily loaded route after it — the reader trapped
   * until a full reload, on exactly the connection this split was made for.
   *
   * Only the chunk asked for here is held back; the destination's own chunk is untouched, so
   * anything still showing the failure afterwards is the boundary and not the network.
   */
  await page.route(/LeaguesPage/, route => route.abort());
  await page.goto('/leagues');
  await expect(page.getByTestId('route-error')).toBeVisible();

  await page.unroute(/LeaguesPage/);
  await page.getByRole('link', { name: /soccer predictions, home/i }).click();

  await expect(page.getByTestId('route-error'), 'a new route must not inherit the last one\'s failure')
    .toHaveCount(0);
  await expect(page.locator('main')).not.toBeEmpty();
});

// --------------------------------------------------------------- 3. staleness says the same thing

test('the reading mode changes not one word about how old the data is', async ({ page }) => {
  await harness(page);
  await openMatchday(page);

  const freshness = page.getByTestId('data-freshness');
  await expect(freshness).toBeVisible();
  const summaryWithImages = (await freshness.getByTestId('freshness-summary').innerText()).trim();
  const toneWithImages = await freshness.getAttribute('data-tone');
  expect(summaryWithImages.toLowerCase()).toContain('stored data');

  await (await lowDataSwitch(page)).click();
  await expect(page.locator('html')).toHaveAttribute('data-low-data', 'on');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('matchday-workspace')).toBeVisible();

  const freshnessNow = page.getByTestId('data-freshness');
  await expect(freshnessNow).toBeVisible();
  expect(
    (await freshnessNow.getByTestId('freshness-summary').innerText()).trim(),
    'text-only mode must not soften, shorten or drop the staleness statement',
  ).toBe(summaryWithImages);
  expect(await freshnessNow.getAttribute('data-tone')).toBe(toneWithImages);
});

// ----------------------------------------------------------------- 4. the allowance is untouched

test('filtering, changing the day, reloading and switching the mode spend nothing', async ({ page }) => {
  const traffic = await harness(page);
  await openMatchday(page);

  // A different day.
  const days = page.getByTestId('date-strip-day');
  await days.nth(await days.count() - 1).click();
  await expect(page.getByTestId('matchday-workspace')).toBeVisible();

  // A competition filter on, then off.
  const chip = page.getByTestId('competition-chip').first();
  if (await chip.isVisible()) {
    await chip.click();
    await expect(page.getByTestId('matchday-workspace')).toBeVisible();
    await chip.click();
  }

  // The filter sheet.
  const filters = page.getByTestId('filter-sheet-open');
  if (await filters.isVisible()) {
    await filters.click();
    await expect(page.getByTestId('filter-sheet')).toBeVisible();
    await page.keyboard.press('Escape');
  }

  // The reading mode, both ways.
  await (await lowDataSwitch(page)).click();
  await (await lowDataSwitch(page)).click();

  // And the closest thing to a refresh a reader has on this page.
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('matchday-workspace')).toBeVisible();

  expectNoProviderRequest(traffic);

  // Nothing reached a provider directly either: the only hosts touched are this application, the
  // stubbed backend, the crest CDN answered locally above, and the web font the page has always
  // loaded.
  const allowedHost = /^(localhost|127\.0\.0\.1|cdn\.live-score-api\.com|fonts\.googleapis\.com|fonts\.gstatic\.com)$/;
  const strangers = traffic.all
    .filter(url => /^https?:/.test(url))
    .map(url => new URL(url).hostname)
    .filter(host => !allowedHost.test(host));
  expect([...new Set(strangers)], 'no request may go straight to a data provider').toEqual([]);
});
