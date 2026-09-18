import { test, expect, Page } from '@playwright/test';
import {
  MINIMUM_SAMPLE, baseMatches, belowMinimumPerformance, dayPayload, measuredPerformance,
  neverRunSchedulerStatus, noSchedulerStatus, nothingMeasuredPerformance, pausedSchedulerStatus,
  stubBackend,
} from '../support/api-stub';

/**
 * Two questions the reader could not previously answer, and the states in which the honest answer
 * is "we do not know" or "nothing yet".
 *
 * HOW OLD IS THIS? Every page reads stored data. Until the backend gained a scheduler, nothing
 * refreshed unless somebody happened to load a page with refresh on, so there was no answer at
 * all. There is one now, and the states below are the ones that must not blur into each other:
 * a scheduler that has never run has NO timestamp and must not borrow one; a scheduler that is
 * paused on a spent allowance has neither succeeded nor failed and must say when it returns; and
 * a backend that reports no scheduler at all must say that rather than imply a schedule exists.
 *
 * HOW OFTEN HAS THIS SOURCE BEEN RIGHT? Only ever from settled results, only ever with the sample
 * it was counted from, and — below the backend's minimum sample — not at all. A refused figure is
 * a sentence, never a zero, a dash or an empty chart.
 *
 * Every payload is stubbed from e2e/support/api-stub.ts. No provider request is made and no
 * allowance is spent.
 */

/** The freshness block, wherever it is rendered. */
const freshness = (page: Page) => page.getByTestId('data-freshness');

/** Open the disclosure so the per-task rows are in the accessibility tree and the DOM text. */
async function openDetail(page: Page): Promise<void> {
  await freshness(page).getByTestId('freshness-detail').locator('summary').click();
}

// --------------------------------------------------------------------------- how old is this
test('a scheduler that has never run says so, and borrows no timestamp', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), status: neverRunSchedulerStatus() });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  await expect(block).toBeVisible();
  await expect(block.getByTestId('freshness-summary')).toContainText(/no scheduled refresh has run yet/i);
  // "unknown" and not "ok": nothing is claimed to be current.
  await expect(block).toHaveAttribute('data-tone', 'unknown');
  // And above all, no invented age. "12 minutes ago" would have to have come from somewhere else.
  await expect(block).not.toContainText(/last refreshed/i);
  await expect(block).not.toContainText(/ago/i);

  await openDetail(page);
  await expect(block.getByTestId('freshness-task')).toHaveCount(4);
  for (const name of ['fixtures', 'live', 'results', 'forecasts']) {
    await expect(block.locator(`[data-task="${name}"]`)).toContainText(/has never run/i);
  }
  // Nor does the provider row invent an answer it never received.
  await expect(block.getByTestId('freshness-retrieval')).toContainText(/has not answered successfully yet/i);
});

test('a scheduler that ran recently reports when, and stays quiet about it', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  await expect(block).toHaveAttribute('data-tone', 'ok');
  await expect(block.getByTestId('freshness-summary')).toContainText(/last refreshed .* ago/i);
  // Nothing on any page is live, and the line says so before it says anything reassuring.
  await expect(block.getByTestId('freshness-summary')).toContainText(/stored data/i);
  // A healthy schedule needs no second sentence.
  await expect(block.getByTestId('freshness-note')).toHaveCount(0);

  await openDetail(page);
  await expect(block.locator('[data-task="fixtures"]')).toContainText(/updated .* ago/i);
  // The provider retrieval is a different fact from our own refresh, and is labelled as one.
  await expect(block.getByTestId('freshness-retrieval')).toContainText(/last answer from live score api/i);
  await expect(block).toContainText(/when a provider.s model actually\s+ran is a different fact/i);
});

test('a paused refresh says when it resumes, not merely that it is paused', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), status: pausedSchedulerStatus() });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  // Paused is not broken: attention, not alarm, and the fixtures that are current stay current.
  await expect(block).toHaveAttribute('data-tone', 'ageing');
  await expect(block.getByTestId('freshness-summary')).toContainText(/last refreshed .* ago/i);

  const note = block.getByTestId('freshness-note');
  await expect(note).toContainText(/model forecasts: paused/i);
  // The backend's own reason, verbatim.
  await expect(note).toContainText(/daily request budget for gameforecast is spent/i);
  // And the half that makes it useful: when it comes back.
  await expect(note).toContainText(/resets at 00:00 utc/i);
  await expect(note).toContainText(/the next attempt is in/i);
});

test('a backend with no scheduler does not imply that one exists', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), status: noSchedulerStatus() });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  await expect(block.getByTestId('freshness-summary')).toContainText(/no scheduled refresh is reported/i);
  await expect(block).toHaveAttribute('data-tone', 'unknown');
  await expect(block.getByTestId('freshness-note'))
    .toContainText(/stored data changes only when a page asks the provider for new data/i);
});

test('an unreachable status endpoint reads as unknown, never as current', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    fail: url => (url.includes('/data-providers/status') ? 503 : null),
  });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  await expect(block).toHaveAttribute('data-tone', 'unknown');
  await expect(block.getByTestId('freshness-summary')).toContainText(/how current it is cannot be stated/i);
  // No age at all. The note is allowed to use the words "last refreshed" in saying it is unknown;
  // what must never appear is a refresh time, which could only have been made up.
  await expect(block).not.toContainText(/refreshed (just now|\d)/i);
  await expect(block).not.toContainText(/\bago\b/i);
});

test('the match page carries the same freshness statement as the list', async ({ page }) => {
  const match = baseMatches()[0];
  await stubBackend(page, { day: d => dayPayload(d), status: pausedSchedulerStatus() });
  await page.goto(`/match/${match.id}`);
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  await expect(block).toBeVisible();
  await expect(block.getByTestId('freshness-summary')).toContainText(/stored data/i);
  await expect(block.getByTestId('freshness-note')).toContainText(/resets at 00:00 utc/i);
});

// --------------------------------------------------------------------------- the measured record
test('with nothing scored the record says so, with the reason and the window', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), performance: nothingMeasuredPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const record = page.getByTestId('measured-record');
  await expect(record).toHaveAttribute('data-state', 'none');
  await expect(record.getByTestId('measured-headline'))
    .toContainText(/nothing has been scored yet, so no source has a measured record/i);
  // The backend's own reason, not a shrug.
  await expect(record.getByTestId('measured-detail'))
    .toContainText(/no match in this window has reached a terminal status yet/i);
  // The window is stated even when the answer is "nothing": "nothing" is a claim about a range.
  await expect(record.getByTestId('measured-window')).toContainText(/kickoff date in utc/i);
  // No zero, no dash, no empty chart standing in for the absent figure.
  await expect(record.getByTestId('measured-hit-rate')).toHaveCount(0);
  await expect(record).not.toContainText(/\b0(\.0)?%/);
});

test('a source with too few scored predictions gets a sentence, not a number', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), performance: belowMinimumPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const record = page.getByTestId('measured-record');
  const source = record.getByTestId('measured-source').first();

  // The source IS measured — it has scored predictions — but no market reaches the minimum.
  await expect(record.getByTestId('measured-hit-rate')).toHaveCount(0);
  await expect(record.getByTestId('measured-hit-rate-withheld')).toHaveCount(1);
  // Each market says how far off it is, in few enough words to read as one line.
  await expect(source).toContainText(new RegExp(`7 of ${MINIMUM_SAMPLE} scored predictions needed`, 'i'));
  // The counts behind the refusal are still published: they are real.
  await expect(source.getByTestId('measured-source-counts')).toContainText(/7 scored/);
  // The full statistical rationale is stated ONCE for the block. Repeating it under every market
  // turned five honest rows into what looked like five errors, which is how the quota notices used
  // to make a perfectly good forecast look broken.
  await expect(record.getByTestId('measured-minimum-sample')).toContainText(/95% interval wider/i);
  const rationaleCount = (await record.innerText()).match(/standard error is 0\.5\/sqrt/g) || [];
  expect(rationaleCount.length, 'the rationale is stated once, not once per market').toBe(1);
});

test('a source with enough scored predictions shows the figure with its sample', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), performance: measuredPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const record = page.getByTestId('measured-record');
  await expect(record).toHaveAttribute('data-state', 'measured');

  const rate = record.getByTestId('measured-hit-rate');
  // 50 of 106: the figure, and never without the sample it was counted from.
  await expect(rate).toContainText('47.2%');
  await expect(rate).toContainText('from 106 scored');

  const market = record.getByTestId('measured-market').first();
  // The definition of what was counted travels with it.
  await expect(market).toContainText(/share of scored predictions whose single most likely published outcome/i);
  await expect(market).toContainText(/1x2 on the regulation-time score/i);
  // And the window, so it cannot be read as an all-time claim.
  await expect(record.getByTestId('measured-window')).toContainText(/both ends included/i);

  // A measured record is about the past and never phrased as a tip.
  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).not.toMatch(/sure bet|guaranteed|can.t lose|best bet/);
});

test('a failed performance request is not reported as "nothing measured"', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    fail: url => (url.includes('/performance/sources') ? 503 : null),
  });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const record = page.getByTestId('measured-record');
  await expect(record).toHaveAttribute('data-state', 'failed');
  await expect(record.getByTestId('measured-headline')).toContainText(/could not be loaded/i);
  // The distinction the whole state machine exists for.
  await expect(record.getByTestId('measured-detail'))
    .toContainText(/says nothing about what has or has not been scored/i);
  await expect(record).not.toContainText(/nothing has been scored yet/i);
});

// --------------------------------------------------------------------------- nothing else moved
test('the freshness and record panels do not disturb what the pages already promise', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), performance: measuredPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const text = (await page.locator('body').innerText()).toLowerCase();
  // The home page's standing prohibitions, re-checked with a measured figure on the page.
  expect(text).not.toMatch(/accuracy rate/);
  expect(text).not.toMatch(/success rate/);
  expect(text).not.toMatch(/\d+% accurate/);
  expect(text).not.toContain('nan');
  expect(text).not.toContain('undefined');
  // And the page must not scroll sideways because a panel was added to it.
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
