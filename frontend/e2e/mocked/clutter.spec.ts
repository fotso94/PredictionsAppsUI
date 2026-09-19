import { test, expect, Page } from '@playwright/test';
import {
  baseCoverage, baseMatches, baseStatus, dayPayload, expiredTrialStatus, healthyTask, matchDetail,
  quotaExhaustedStatus, stubBackend, StubOptions, VENDOR_UPGRADE_URL, vendorRefusalStatus,
} from '../support/api-stub';

/**
 * Getting the football above the plumbing.
 *
 * A reviewer opened a match on a 390px phone and met a provider quota banner, then a freshness
 * block saying the same thing in more words, then a per-fixture notice saying it a third time —
 * and reached the forecast table 1,911px down the document. Everything they read was true. The
 * page was still wrong: three notices about one fact is not three times the honesty, and an
 * explanation of an absent odds feed does not earn a headed panel above the numbers.
 *
 * WHAT THESE TESTS PIN, and deliberately do not pin:
 *  - a BOUND on how far down the forecast table starts, not a snapshot of it. A snapshot would
 *    fail on a longer club name; the point is that the distance cannot creep back.
 *  - that the quota explanation is in exactly ONE region of the page, and which region. Counting
 *    words alone would pass a page that had simply reworded the duplicate.
 *  - that everything moved is still reachable. Every assertion that something is gone from the
 *    top of the page is paired with one that finds it behind a disclosure.
 *
 * Every payload is stubbed from e2e/support/api-stub.ts. No provider request is made and no
 * allowance is spent.
 */

const PHONE = { width: 390, height: 844 };
const NARROW = { width: 360, height: 740 };
const DESKTOP = { width: 1440, height: 900 };

/**
 * Measured on the running application before this work, at 390px, with the provider paused.
 *
 * The model forecast PANEL BODY began 1,426px down a stubbed page carrying no evidence brief, and
 * 1,911px down the live one, whose brief carries missing-data rows. The table sits a fixed 72px
 * inside that body — padding and the anomalies slot, neither of which this work touched — so the
 * table itself began 1,498px down the briefless page and 1,983px down the live one.
 *
 * The home page ran to 5,117px stubbed and 5,755px live.
 *
 * WHICH OF THOSE THE BOUND IS AGAINST, because the guard used to answer the wrong one.
 *
 * `GET /matches/{id}` always carries the full brief, so every match page a reader opens has one.
 * This guard was asserting against the LIST-shaped stub, which has none, and its 1,280px bound was
 * measuring a page nobody is ever served. Measured today at 390, identically on Chromium and
 * WebKit to within a pixel: the table sits 1,191px down without a brief and 1,462px down with the
 * captured one. So the guard passed with 89px to spare while the real page sat 182px the wrong
 * side of it. (At 360 the same two pages measure 1,279 and 1,602; at 1440, 1,015 and 1,254.)
 *
 * The bound below is therefore the real page's number with room for a line or two of honest
 * wording — a longer club name wrapping the brief headline, one more coverage row — and no more.
 * It is 463px below where that page started and 58px above where it stands: headroom a rewritten
 * sentence fits inside and a reinstated banner or headed panel does not. It is NOT the 1,280 this
 * file used to claim: closing that last 182px needs the brief panel itself to get shorter, which
 * is a change to components this round did not open.
 */
const FORECAST_TABLE_TOP_BEFORE = 1983;
const FORECAST_TABLE_TOP_BOUND = 1520;
const HOME_HEIGHT_BEFORE = 5117;
const HOME_HEIGHT_BOUND = 4300;

const FIXTURE = baseMatches()[0];

/** Distance from the top of the DOCUMENT — not the viewport — to the top of an element. */
async function documentTop(page: Page, testId: string): Promise<number> {
  return page.evaluate(id => {
    const el = document.querySelector(`[data-testid="${id}"]`);
    if (!el) throw new Error(`no element with data-testid="${id}"`);
    return Math.round(el.getBoundingClientRect().top + window.scrollY);
  }, testId);
}

const pageOverflow = (page: Page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth);

/** A match page with the provider paused — the state the reviewer actually met. */
async function openPausedMatch(page: Page, viewport = PHONE, options: StubOptions = {}): Promise<void> {
  await page.setViewportSize(viewport);
  await stubBackend(page, { day: d => dayPayload(d), status: quotaExhaustedStatus(), ...options });
  await page.goto(`/match/${FIXTURE.id}`);
  await page.waitForLoadState('networkidle');
}

// ------------------------------------------------------------------ how far down the football is
test('the forecast table is far closer to the top of a phone than it was', async ({ page }) => {
  // The detail payload, deliberately: this is the page `GET /matches/{id}` serves and the only
  // match page a reader ever opens. Measuring the briefless list-shaped stub instead is how this
  // guard came to pass while the page it is named after sat 182px past its bound.
  await openPausedMatch(page, PHONE, { matchById: matchDetail });

  // The brief really did reach the page. Everything below is about the distance the brief adds,
  // so a payload that quietly lost it would turn this back into the guard that measured nothing.
  await expect(page.getByTestId('brief-headline')).toBeVisible();

  const top = await documentTop(page, 'market-table');
  expect(top,
    `the model forecast table started ${FORECAST_TABLE_TOP_BEFORE}px down the live match page before this work`,
  ).toBeLessThan(FORECAST_TABLE_TOP_BOUND);

  // And it is the MODEL table that has to be reachable, not merely some table.
  await expect(page.getByTestId('provider-forecast').getByTestId('market-table')).toBeVisible();
});

test('the home page is materially shorter on a phone, with nothing dropped', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await stubBackend(page, { day: d => dayPayload(d), status: quotaExhaustedStatus() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  expect(height, `the home page was ${HOME_HEIGHT_BEFORE}px tall before this work`)
    .toBeLessThan(HOME_HEIGHT_BOUND);

  /*
   * Shorter because two blocks were folded, not because anything was deleted. A closed <details>
   * keeps its content in the DOM, so these assert on what is RENDERED — toBeHidden and innerText —
   * rather than on presence, which would pass either way.
   */
  const counts = page.getByTestId('coverage-detail');
  await expect(counts.getByTestId('coverage-stat').first()).toBeHidden();
  await counts.locator('summary').click();
  await expect(counts.getByTestId('coverage-stat')).toHaveCount(4);
  await expect(counts.getByTestId('coverage-stat').first()).toBeVisible();

  const method = page.getByTestId('home-method');
  await expect(method).not.toContainText(/instead of showing a zero/i, { useInnerText: true });
  await method.locator('summary').click();
  await expect(method).toContainText(/instead of showing a zero/i, { useInnerText: true });
});

test('the headings on the home page are written for a reader who wants football', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // "What this installation holds" is how an operator describes a database.
  await expect(page.getByRole('heading', { name: /installation holds/i })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /how much football is loaded/i })).toBeVisible();

  /*
   * The summary that replaced the four stacked cards carries the same measured numbers, read
   * from the same payload, and carries the denominator with them: "30 of 48" is the fact, "30"
   * on its own is not. Built from the fixture rather than typed out, so it asserts the
   * relationship and not a number somebody could quietly change in one place.
   */
  const coverage = baseCoverage() as Record<string, number>;
  const without = coverage.upcoming_matches - coverage.upcoming_matches_with_forecast;
  const summary = page.getByTestId('coverage-summary');
  await expect(summary).toContainText(
    new RegExp(`${coverage.upcoming_matches} upcoming fixtures stored across ${coverage.competitions_covered} competitions`, 'i'));
  await expect(summary).toContainText(
    new RegExp(`${coverage.upcoming_matches_with_forecast} of them carry a model forecast; the other ${without} have none`, 'i'));
});

// ------------------------------------------------------------------ one status message, not three
test('the quota explanation appears exactly once on a match detail page', async ({ page }) => {
  await openPausedMatch(page);

  /*
   * Which REGION carries it, not merely how many times the word appears. A page that reworded its
   * duplicate would pass a word count and still make a sound forecast look broken.
   */
  const speaking = await page.evaluate(() => {
    const regions = [
      'provider-status-banner', 'data-freshness', 'match-data-state', 'forecast-sync-notice',
    ];
    return regions.filter(id => {
      const el = document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
      return !!el && /allowance|quota|request budget/i.test(el.innerText);
    });
  });
  expect(speaking, 'the state of the refresh belongs beside the ages it explains, and nowhere else')
    .toEqual(['data-freshness']);

  /*
   * And the backend's own reason, verbatim, reaches the reader exactly once — from inside the
   * disclosure, not from the top of the page.
   *
   * It used to be printed in the note, which is how the vendor's name, our plan tier and an
   * upgrade link ended up above the football on a phone. The note now carries a readable summary
   * of it instead. Both halves are asserted: nothing quotes the upstream string at a reader who
   * did not ask for it, and exactly one copy is there for anyone who opens the detail.
   */
  const verbatim = /daily request budget for gameforecast is spent/gi;
  const visible = await page.locator('body').innerText();
  expect(visible.match(verbatim) ?? [], 'the upstream string is not shown unasked').toHaveLength(0);
  await expect(page.getByTestId('freshness-note')).toContainText(/allowance/i);

  await page.getByTestId('freshness-detail').locator('summary').click();
  const opened = await page.locator('body').innerText();
  expect(opened.match(verbatim) ?? [], 'and it is there once for anyone diagnosing it')
    .toHaveLength(1);
});

test('a paused refresh alone raises no site-wide banner, and a broken provider still does', async ({ page }) => {
  await openPausedMatch(page);
  // Nothing is unreachable and nothing on screen is wrong, so nothing leads the page about it.
  await expect(page.getByTestId('provider-status-banner')).toHaveCount(0);
  // The fact itself is still stated, with the time it comes back.
  await expect(page.getByTestId('data-freshness')).toContainText(/paused/i);

  // A provider that cannot answer at all is a different matter and keeps its banner.
  await stubBackend(page, { day: d => dayPayload(d), status: expiredTrialStatus() });
  await page.goto(`/match/${FIXTURE.id}`);
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('provider-status-banner')).toBeVisible();
});

test('fixture freshness and forecast freshness are separately identifiable', async ({ page }) => {
  /*
   * The bug this exists for: one "last refreshed" line took the most recent success across every
   * task, so a live-score pass from a minute ago made a forecast nobody had touched in two days
   * read as current. Here the two clocks are deliberately two days apart.
   */
  const status = baseStatus();
  status.scheduler!.tasks.forecasts = healthyTask(21_600, 2 * 24 * 60, 320);
  await page.setViewportSize(PHONE);
  await stubBackend(page, { day: d => dayPayload(d), status });
  await page.goto(`/match/${FIXTURE.id}`);
  await page.waitForLoadState('networkidle');

  const block = page.getByTestId('data-freshness');
  const fixtures = block.getByTestId('freshness-summary');
  const forecasts = block.getByTestId('freshness-forecasts');

  await expect(fixtures).toContainText(/fixtures and scores/i);
  await expect(forecasts).toContainText(/model forecasts/i);

  // Two different ages, each attached to the thing it is the age of.
  await expect(fixtures).toContainText(/minute(s)? ago/i);
  await expect(forecasts).toContainText(/(2 days|4[0-9] hours) ago/i);
  // The fixture line must never speak for the forecasts.
  await expect(fixtures).not.toContainText(/2 days ago/i);
});

test('the technical detail is one tap away, not deleted', async ({ page }) => {
  await openPausedMatch(page);

  // The per-task breakdown and the provider's own retrieval time.
  const freshness = page.getByTestId('data-freshness');
  const detail = freshness.getByTestId('freshness-detail');
  await expect(detail.getByTestId('freshness-task').first()).toBeHidden();
  await detail.locator('summary').click();
  await expect(detail.locator('[data-task="forecasts"]')).toBeVisible();
  await expect(detail.getByTestId('freshness-retrieval')).toContainText(/last answer from/i);

  // The fixture's provider keys and ids, which used to have a headed card of their own.
  const provenance = page.getByTestId('match-provenance');
  await expect(provenance).not.toContainText(/provider fixture id/i, { useInnerText: true });
  await provenance.locator('summary').click();
  await expect(provenance).toContainText(/fixture source/i, { useInnerText: true });
  await expect(provenance).toContainText(/provider fixture id/i, { useInnerText: true });
});

test('the site-wide banner keeps its extra reports behind a disclosure', async ({ page }) => {
  // A fault AND a pause at once: the fault leads, the pause travels inside.
  const status = expiredTrialStatus();
  status.forecasts.budget = {
    provider: 'gameforecast', daily_limit: 8, used_today: 8, refused_today: 2,
    remaining_today: 0, enforced: true,
  };
  await page.setViewportSize(PHONE);
  await stubBackend(page, { day: d => dayPayload(d), status });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const banner = page.getByTestId('provider-status-banner');
  await expect(banner).toContainText(/do not have access to our data enabled/i, { useInnerText: true });
  await expect(banner).not.toContainText(/daily request allowance/i, { useInnerText: true });
  await banner.locator('summary').click();
  await expect(banner).toContainText(/daily request allowance/i, { useInnerText: true });
});

// ------------------------------------------------------------------ what is no longer in the way
test('no odds panel exists while no odds feed does', async ({ page }) => {
  await openPausedMatch(page);

  await expect(page.getByTestId('odds-panel')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /betting odds/i })).toHaveCount(0);
  // The fact is not deleted with the panel: a reader who wonders where the odds went is answered,
  // in one line, without opening anything.
  await expect(page.getByTestId('odds-absent')).toContainText(/odds are not available/i);
});

/** The backend's own sentence for a fixture nobody has published a prediction for. */
const NO_EXPERT = 'No expert has published a prediction for this fixture.';

test('the missing-expert explanation appears once', async ({ page }) => {
  /*
   * WHAT THIS RUNS AGAINST, because it is the whole test.
   *
   * The consolidation lives in how the brief's `missing` array is grouped, so a payload with no
   * brief does not reach it: the evidence panel falls back to a sentence hardcoded in
   * EvidenceBrief.tsx, nothing else on the page says anything about experts, and "it appears
   * once" passes without a line of the code it is named after ever running. So this test asks for
   * the captured DETAIL payload — `matchById: matchDetail`, the fixture as `GET /matches/{id}`
   * serves it, brief and all — and that brief states the absence FIVE times: once for the source
   * and once for each of the four markets an expert could have supplied.
   */
  const brief = matchDetail(FIXTURE.id)?.brief as { missing: Array<{ detail: string; scope: string }> };
  const stated = brief.missing.filter(entry => entry.detail === NO_EXPERT);
  expect(stated.length,
    'the captured brief must really repeat it, or this test is not testing a consolidation',
  ).toBeGreaterThan(1);
  expect(stated.filter(entry => entry.scope === 'source').length,
    'and one of them must be the source-scoped statement the coverage row is for').toBe(1);

  await openPausedMatch(page, PHONE, { matchById: matchDetail });

  // The brief reached the page: this is its own headline, which no fallback can produce.
  await expect(page.getByTestId('brief-headline')).toBeVisible();

  // This fixture carries a model forecast and no expert prediction.
  await expect(page.getByTestId('provider-forecast')).toBeVisible();
  await expect(page.getByTestId('expert-predictions')).toHaveCount(0);

  // The one place it belongs: the row about who published what, in the backend's own words.
  await expect(page.getByTestId('brief-coverage-expert')).toContainText(NO_EXPERT);
  // And not again in the markets list below it, which is where the other four entries would land.
  const missingList = page.getByTestId('brief-missing');
  await expect(missingList.locator('[data-reason="no_expert_prediction"]')).toHaveCount(0);
  // That list is rendering — the assertion above is about consolidation, not about an empty list.
  await expect(missingList.locator('[data-reason="not_offered_by_source"]')).toHaveCount(1);

  const body = await page.locator('body').innerText();
  const said = body.match(/no expert has published a prediction for this fixture/gi) ?? [];
  expect(said.length, 'absence is worth one sentence, not a strip, a row and a marker description')
    .toBe(1);
  // Including to a screen reader: the marker's description must not repeat the sentence beside it.
  const spoken = (await page.locator('body').textContent() ?? '')
    .match(/No expert has published a prediction for this fixture/gi) ?? [];
  expect(spoken.length).toBe(1);
});

// ------------------------------------------------------------------ and nothing scrolls sideways
for (const [label, viewport] of [['360', NARROW], ['390', PHONE], ['1440', DESKTOP]] as const) {
  test(`neither page scrolls sideways at ${label}px, banner and all`, async ({ page }) => {
    await page.setViewportSize(viewport);
    /*
     * THE MESSAGE MATTERS AS MUCH AS THE WIDTH.
     *
     * This used to run on expiredTrialStatus(), whose refusal is twelve short words — every one of
     * them breakable. A checker replaced the banner's `min-w-0 flex-1 break-words` with a bare
     * `flex-1` and this test went on passing, because nothing in that message can set a
     * min-content width wider than 360px in the first place.
     *
     * vendorRefusalStatus() is the message the provider really sends: a 429 ending in a
     * 53-character URL with no spaces in it (api-stub.ts records where it was read from). A
     * `flex-1` child keeps `min-width: auto`, so it refuses to shrink below that token's width,
     * and that is exactly how the document came to scroll sideways and the dismiss button came to
     * be clipped off the edge of a 360px phone.
     *
     * WHAT THIS CATCHES, measured one guard at a time at 360 on both engines, so the next reader
     * knows what it does and does not stand for:
     *
     *   min-w-0 removed  (the checker's own `flex-1`)   FAILS, 6px of sideways scroll
     *   min-w-0 kept, flex-1 removed                    passes — a shrinkable item still fits
     *   min-w-0 kept, break-words removed               passes — Chromium and WebKit both break
     *                                                   this URL at a slash on their own
     *
     * So this pins `min-w-0`, which is the guard that was actually load-bearing. `break-words` is
     * belt and braces against a token with no slash in it, and no assertion here proves it is
     * needed; do not read a pass as evidence that it is not.
     */
    await stubBackend(page, { day: d => dayPayload(d), status: vendorRefusalStatus() });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // The banner really is showing the unbreakable text, so the widths below mean something.
    const banner = page.getByTestId('provider-status-banner');
    await expect(banner).toContainText(VENDOR_UPGRADE_URL);

    expect(await pageOverflow(page), 'home page').toBeLessThanOrEqual(1);

    await page.goto(`/match/${FIXTURE.id}`);
    await page.waitForLoadState('networkidle');
    await expect(banner).toContainText(VENDOR_UPGRADE_URL);
    expect(await pageOverflow(page), 'match detail page').toBeLessThanOrEqual(1);

    // And the dismiss button stays inside the viewport rather than being clipped by the edge.
    const dismiss = banner.getByRole('button', { name: /dismiss/i });
    const box = await dismiss.boundingBox();
    expect(box, 'the banner is on screen').not.toBeNull();
    expect(Math.round(box!.x + box!.width)).toBeLessThanOrEqual(viewport.width);
  });
}
