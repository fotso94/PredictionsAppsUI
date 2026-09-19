import { test, expect, Page } from '@playwright/test';
import {
  stubBackend, dayPayload, emptyDayPayload, belowMinimumPerformance, measuredPerformance,
  nothingMeasuredPerformance, baseMatches, localDay, MINIMUM_SAMPLE,
} from '../support/api-stub';
import type { ApiMatch, Json } from '../support/api-stub';

/**
 * What the interface SAYS about results, as opposed to what it measures.
 *
 * Every failure these tests are written against was a sentence, not a number. The figures were
 * right throughout; the words around them claimed more, or less, than the data did:
 *
 *  - prose that asserted "nothing has been scored yet" as a standing fact, left behind when four
 *    forecasts had in fact been scored. An absence is a state to be read from the payload on every
 *    load, never a sentence written into a page;
 *  - "Sample: 1 of 4 scored", which puts a HIT COUNT where a reader expects a SAMPLE SIZE. A
 *    reviewer read it as "one prediction of four has been scored". It means one correct outcome
 *    out of a sample of four;
 *  - "No matches on this date", which claims the world is empty when all the application knows is
 *    that its own store is.
 *
 * Everything is driven from stubbed payloads, so each state is reached deliberately and no
 * provider request is made. The three states the measured record can be in — nothing scored,
 * scored but below the minimum sample, measured — all have to survive, and a test for one of them
 * must not be satisfiable by the wording of another.
 */

/** Every rendered word on the page, lower-cased, for the "no screen claims X" assertions. */
const pageText = async (page: Page): Promise<string> =>
  (await page.locator('body').innerText()).toLowerCase();

/** The claim C1 exists to kill: an absence stated as a fact regardless of the payload. */
const NOTHING_SCORED = /nothing has been scored/i;

// ------------------------------------------------------------------ C1: the absence is not fixed
test('with forecasts scored, no screen claims nothing has been scored', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), performance: measuredPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // Prove we are looking at the measured state before asserting on what it does not say: the
  // assertion would pass trivially against a page that failed to load the record at all.
  const record = page.getByTestId('measured-record');
  await expect(record).toHaveAttribute('data-state', 'measured');

  expect(await pageText(page)).not.toMatch(NOTHING_SCORED);
});

test('below the minimum sample, the page still does not claim nothing has been scored', async ({ page }) => {
  // Seven scored and no published rate is the state most likely to be described as "nothing yet".
  // It is not nothing: seven predictions were scored and four of them were right.
  await stubBackend(page, { day: d => dayPayload(d), performance: belowMinimumPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const record = page.getByTestId('measured-record');
  await expect(record).toHaveAttribute('data-state', 'measured');
  await expect(record.getByTestId('measured-source-counts')).toContainText('7 scored');

  expect(await pageText(page)).not.toMatch(NOTHING_SCORED);
});

test('with nothing scored the honest nothing-scored state still renders', async ({ page }) => {
  // The other half of C1: the state was kept, only the assertion was removed. If the wording had
  // been deleted along with it, this installation would go silent on its most common answer.
  await stubBackend(page, { day: d => dayPayload(d), performance: nothingMeasuredPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const record = page.getByTestId('measured-record');
  await expect(record).toHaveAttribute('data-state', 'none');
  await expect(record.getByTestId('measured-headline')).toContainText(NOTHING_SCORED);
  // Stated with its reason and its window, which is what makes it an answer rather than a shrug.
  await expect(record.getByTestId('measured-detail'))
    .toContainText(/no match in this window has reached a terminal status yet/i);
  await expect(record.getByTestId('measured-window')).toContainText(/kickoff date in utc/i);
  // And never dressed up as a figure.
  await expect(record.getByTestId('measured-hit-rate')).toHaveCount(0);
  await expect(record).not.toContainText(/\b0(\.0)?%/);
});

// -------------------------------------------- C2: correct outcomes and sample size, told apart
test('correct outcomes and sample size are separately labelled', async ({ page }) => {
  // measuredPerformance(): 106 scored, 50 of them correct. Two numbers, two meanings, and the old
  // single line made the smaller one look like the number scored so far.
  await stubBackend(page, { day: d => dayPayload(d), performance: measuredPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const market = page.getByTestId('measured-record').getByTestId('measured-market').first();
  await expect(market).toContainText(/sample size:\s*106 scored predictions/i);
  await expect(market).toContainText(/correct outcomes:\s*50 of those 106/i);

  // The wording that caused the misreading is gone: a bare "1 of 4 scored" under a label that
  // says "Sample" invites the reader to take the hit count for the sample size.
  await expect(market).not.toContainText(/sample:\s*50 of/i);

  // The sample size row carries the larger number and the hit row the smaller one — the specific
  // swap the reviewer made. Reading the two rows must not be able to produce it.
  const sampleSize = await market.getByTestId('measured-sample-size').innerText();
  const hitCount = await market.getByTestId('measured-hit-count').innerText();
  expect(sampleSize).toContain('106');
  expect(sampleSize).not.toContain('50');
  expect(hitCount).toContain('50');
});

test('a hit count on a small sample cannot be read as a sample size', async ({ page }) => {
  // The reviewer's actual screen: four scored, one right. Under the old line this read as
  // "sample: 1 of 4 scored" and was understood as one of four predictions having been scored.
  await stubBackend(page, { day: d => dayPayload(d), performance: belowMinimumPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const market = page.getByTestId('measured-record').getByTestId('measured-market').first();
  await expect(market.getByTestId('measured-sample-size')).toContainText(/7 scored predictions/i);
  await expect(market.getByTestId('measured-hit-count')).toContainText(/4 of those 7/i);
  await expect(market).not.toContainText(/sample:\s*4 of/i);
});

// ------------------------------------------ C2: the refusal below the minimum stays a sentence
test('below the minimum sample no percentage appears and the refusal is a sentence', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), performance: belowMinimumPerformance() });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const record = page.getByTestId('measured-record');
  await expect(record.getByTestId('measured-hit-rate')).toHaveCount(0);
  await expect(record.getByTestId('measured-hit-rate-withheld')).toContainText(/no hit rate published/i);
  // A sentence saying how far off it is — not a 0%, not a dash, not an empty bar.
  await expect(record).toContainText(new RegExp(`7 of ${MINIMUM_SAMPLE} scored predictions needed`, 'i'));
  // No percentage in the market row at all, including the 57.1% that 4 of 7 would round to. The
  // check is scoped to the row because the block's rationale legitimately says "95% interval".
  const market = record.getByTestId('measured-market').first();
  expect(await market.innerText(), 'no figure on a sample below the minimum').not.toMatch(/\d+(\.\d+)?%/);
  await expect(record).not.toContainText(/%\s*hit rate/i);
  // The withheld Brier score names ITS own sample rather than borrowing the scored count, and
  // states it as a count rather than as a share of the scored sample. Both directions are real:
  // the exact-score market has four scored predictions and a Brier sample of zero, while a market
  // with a push has a Brier sample LARGER than its scored count (settlement keeps a push out of
  // `scored` but still records its Brier value), which "N of these predictions" would have
  // rendered as an impossible 5 of 4.
  await expect(market).toContainText(/computable for 7 predictions so far/i);
  await expect(market, 'the Brier count is not phrased as a share of the scored sample')
    .not.toContainText(/computable for \d+ of/i);

  // The statistical rationale is stated once for the block, not once per market: five honest rows
  // each carrying three sentences of caveat read as five errors.
  const rationale = (await record.innerText()).match(/standard error is 0\.5\/sqrt/g) || [];
  expect(rationale.length, 'the rationale is stated once, not once per market').toBe(1);
  await expect(record.getByTestId('measured-minimum-sample')).toContainText(/95% interval wider/i);
});

// ---------------------------------------------- C3: an empty day is a fact about what is stored
test('the empty-date state says what is stored, not what exists, and offers an action', async ({ page }) => {
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const empty = page.getByTestId('matchday-empty');
  await expect(empty).toBeVisible();
  await expect(empty).toContainText(/no matches stored for this date/i);
  await expect(empty).toContainText(/holds no fixtures/i);
  // The distinction this rewrite exists for: the store is empty, the world is not reported on.
  await expect(empty).toContainText(/rather than a statement that nothing is being played/i);
  await expect(empty).not.toContainText(/no matches on this date/i);

  // And a way out that works, rather than "pick another day above".
  const action = empty.getByTestId('matchday-empty-jump');
  await expect(action).toBeVisible();
  // Keyboard-reachable and visibly focused, like every other control in this workspace.
  await action.focus();
  await expect(action).toBeFocused();
  await action.click();
  await expect(page).toHaveURL(/\/matches\?.*date=/);
});

test('the filtered-empty state stays distinct from the nothing-stored one', async ({ page }) => {
  // Two different facts that look identical on screen: nothing is stored, versus plenty is stored
  // and the reader's own filters excluded it. The second keeps its "Clear all filters" way out.
  await stubBackend(page, { day: d => dayPayload(d) });
  // The workspace's own query keys (workspaceState.ts PARAM): every captured fixture is scheduled,
  // so "Played" selects none of them while the day itself is full.
  await page.goto('/predictions/today?show=finished&source=expert');
  await page.waitForLoadState('networkidle');

  const filtered = page.getByTestId('matchday-filtered-empty');
  await expect(filtered).toBeVisible();
  await expect(filtered).toContainText(/no matches match your filters/i);
  await expect(filtered).toContainText(/stored for/i);
  await expect(page.getByTestId('matchday-empty')).toHaveCount(0);
  await expect(filtered.getByRole('button', { name: 'Clear all filters' })).toBeVisible();
});

/** The captured fixture, played out: the shape `serialize_match` gives a match with a result. */
const played = (match: ApiMatch, home: number, away: number): ApiMatch => ({
  ...match,
  status: 'finished',
  score: { home, away, ht_home: null, ht_away: null },
});

/**
 * The captured fixture, IN PLAY. `serialize_match` emits `score` as soon as the stored match has
 * one, which for the live-score task means from the first goal of the first half — so a fixture
 * that is still being played is indistinguishable from a finished one if all you look at is
 * whether a score is present. It is the case a list of today's fixtures hits every matchday
 * evening, and the page must not describe it as finished.
 */
const inPlay = (match: ApiMatch, home: number, away: number): ApiMatch => ({
  ...match,
  status: 'live',
  minute: "57'",
  score: { home, away, ht_home: home, ht_away: away },
});

// ------------------------------------------------------------------ the page itself still behaves
/**
 * Widths.
 *
 * Longer sentences are the cheapest way to reintroduce horizontal scroll, so every panel whose
 * copy changed is measured at the three widths the reviewer used.
 *
 * Both the panel and the whole document are held to it, at every one of the three widths. An
 * earlier version of this file exempted the document at 360 on the grounds that the header
 * overflowed there anyway. Measured in this stubbed configuration the document is 0px over at
 * 360, 390 and 1440, so the exemption excused nothing and would have hidden the next regression
 * that did overflow. If this goes red at 360 the page really is scrolling sideways — find the
 * element whose right edge exceeds documentElement.clientWidth rather than relaxing the bound.
 *
 * (Against the RUNNING app, where the provider is paused, the document is 6px over at 360: the
 * dismiss button in src/components/ui/ProviderStatusBanner.tsx ends at x=366. That banner is not
 * stubbed into these payloads, it is another package's file, and it is in needs_other_owner.)
 */
for (const width of [360, 390, 1440]) {
  test(`the rewritten copy stays inside its container at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 780 });
    await stubBackend(page, { day: d => dayPayload(d), performance: belowMinimumPerformance() });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const record = page.getByTestId('measured-record');
    expect(await record.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
    const panel = await record.boundingBox();
    expect(panel, 'the measured record rendered').not.toBeNull();
    expect((panel?.x ?? 0) + (panel?.width ?? 0)).toBeLessThanOrEqual(width + 1);

    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, 'the home page does not scroll sideways').toBeLessThanOrEqual(1);
  });

  test(`the computed footnote stays inside its container at ${width}px`, async ({ page }) => {
    // The clause this package replaced was one line; the computed one is longer and carries a
    // count, so it is the cheapest new way to put horizontal scroll back on the matches page.
    await page.setViewportSize({ width, height: 780 });
    const pool = baseMatches();
    await stubBackend(page, {
      day: (d: string) => dayPayload(d, pool.map((m, i) => (i < Math.min(4, pool.length - 1) ? played(m, 2, 1) : m))),
    });
    await page.goto('/predictions/today');
    await page.waitForLoadState('networkidle');

    const footnote = page.getByTestId('matchday-footnote');
    await expect(footnote).toBeVisible();
    expect(await footnote.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
    const box = await footnote.boundingBox();
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(width + 1);
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, 'the matches page does not scroll sideways').toBeLessThanOrEqual(1);
  });

  test(`the empty-date state stays inside its container at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 780 });
    await stubBackend(page, { day: d => emptyDayPayload(d) });
    await page.goto('/predictions/today');
    await page.waitForLoadState('networkidle');

    const empty = page.getByTestId('matchday-empty');
    await expect(empty).toBeVisible();
    expect(await empty.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
    const box = await empty.boundingBox();
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(width + 1);
    // The action is a real target, not a link squeezed to nothing by the narrow width.
    const action = await empty.getByTestId('matchday-empty-jump').boundingBox();
    expect(action?.height ?? 0, 'the way out is tappable').toBeGreaterThanOrEqual(36);
  });
}

// ------------------------------------ F1: what the matchday footnote claims about its own fixtures
/**
 * The footnote under the fixture list used to end "Nothing on this page has been scored against a
 * result, so no accuracy is claimed for any of it." It was a string constant in MatchesPage.tsx,
 * so it went on saying it whatever the page was showing.
 *
 * Deleting the clause would have been the wrong repair. The claim is about THIS PAGE, and on a
 * page of fixtures that have not kicked off it is not merely defensible, it is the most useful
 * thing the footnote says — a reader wants to know that none of the numbers above is a score.
 * What was wrong is that it was ASSERTED. So both halves are tested here: the page must work out
 * what is true of the fixtures it actually listed, keep the strong statement when it holds, and
 * drop it the moment a listed fixture has been played.
 */
const NOTHING_ON_THIS_PAGE = /nothing on this page has been scored/i;

test('a list of fixtures none of which has been played says so, counted from the list', async ({ page }) => {
  const matches = baseMatches();
  await stubBackend(page, { day: (d: string) => dayPayload(d, matches) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const footnote = page.getByTestId('matchday-footnote');
  // The count is the evidence that the sentence was computed: a constant cannot know how many
  // fixtures this particular date turned out to hold.
  await expect(footnote).toContainText(
    new RegExp(`none of the ${matches.length} fixture(s?) listed here has been played yet`, 'i'));
  await expect(footnote).toContainText(NOTHING_ON_THIS_PAGE);
});

test('once a listed fixture has been played the page stops claiming nothing has been scored', async ({ page }) => {
  const pool = baseMatches();
  // Counted off the shared fixture rather than written down: the capture is another package's
  // file this round, and a test that hardcodes how many fixtures it holds goes red on its next
  // recapture for a reason that has nothing to do with what this test is about.
  const playedCount = Math.min(4, pool.length - 1);
  expect(playedCount, 'the capture must hold enough fixtures to leave one unplayed').toBeGreaterThan(0);
  const matches = pool.map((match, index) => (index < playedCount ? played(match, 2, 1) : match));
  await stubBackend(page, { day: (d: string) => dayPayload(d, matches) });
  await page.goto(`/matches?date=${localDay(0)}`);
  await page.waitForLoadState('networkidle');

  const footnote = page.getByTestId('matchday-footnote');
  await expect(footnote).toContainText(
    new RegExp(`${playedCount} of the ${matches.length} fixtures listed here ha(s|ve) finished`, 'i'));
  // The page cannot see whether those four were scored, so it points at the surface that can
  // rather than answering for it — and it does not answer "no" on their behalf.
  await expect(footnote).not.toContainText(NOTHING_ON_THIS_PAGE);
  expect(await pageText(page)).not.toMatch(NOTHING_ON_THIS_PAGE);
});

test('a fixture still in play is not reported as finished', async ({ page }) => {
  // The same defect class as the constant, one step further in: a fact about the data ("this one
  // is over") inferred from something that is not that fact (it has a score). A live fixture has
  // kicked off, so the strong "none has been played" claim must go; it has NOT finished, so the
  // page may not say it has, and no prediction for it can have been scored yet either way.
  const pool = baseMatches();
  const matches = pool.map((match, index) => (index === 0 ? inPlay(match, 1, 0) : match));
  await stubBackend(page, { day: (d: string) => dayPayload(d, matches) });
  await page.goto(`/matches?date=${localDay(0)}`);
  await page.waitForLoadState('networkidle');

  const footnote = page.getByTestId('matchday-footnote');
  await expect(footnote).toContainText(
    new RegExp(`1 of the ${matches.length} fixtures listed here has kicked off`, 'i'));
  await expect(footnote).not.toContainText(/finished/i);
  await expect(footnote).not.toContainText(NOTHING_ON_THIS_PAGE);
});

test('the rest of the footnote — the part that is about the page, not the data — survives', async ({ page }) => {
  await stubBackend(page, { day: (d: string) => dayPayload(d) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const footnote = page.getByTestId('matchday-footnote');
  await expect(footnote).toContainText(/every fixture stored for this date/i);
  await expect(footnote).toContainText(/marked unavailable rather than shown as zero/i);
});

// --------------------------- F2: the match page reports the scoring position the payload measured
/**
 * A brief with nothing in it but the fields the detail page reads, so a test can put one exact
 * sentence on `reliability.detail` and prove the page prints THAT rather than a sentence of its
 * own. The backend computes the sentence from settlement counts; the only thing the browser can
 * be held to is that it repeats what it was given.
 */
const briefWith = (detail: string): Json => ({
  match_id: 'brief-match',
  assembled_at: new Date().toISOString(),
  headline: null,
  known: { kickoff_utc: null, kickoff_known: false, status: 'scheduled', competition: null,
    competition_known: false, model_markets: [], expert_markets: [], sources: [] },
  markets: [],
  missing: [],
  missing_reasons: [],
  freshness: { state: 'unavailable', state_reason: null, stale: false, kickoff_passed: false,
    model_run_at: null, provider_updated_at: null, retrieved_at: null,
    model_run_at_known: false, provider_updated_at_known: false, retrieved_at_known: false,
    unknown_timestamps: [], age_basis: null, age_hours: null, max_age_hours: 12,
    refresh_blocked: false, refresh_blocked_reason: null },
  reliability: {
    model: { confidence_published: false, confidence: null,
      detail: 'This provider publishes no confidence value with its forecasts.' },
    expert: { confidence_published: false, confidence: null,
      detail: 'The expert published no confidence value with this prediction.' },
    accuracy_state: 'below_minimum_sample',
    accuracy_measured: false,
    results_scored: true,
    detail,
  },
  anomalies: [],
});

const SCORED = '4 of 9 eligible prediction(s) on this installation with a kickoff in 2026-06-21 to '
  + '2026-09-19 have been scored, but no market has reached the minimum of 30 scored predictions '
  + 'an accuracy figure is published from. The counts are published; the rate is not.';

test('the match page prints the scoring position the payload measured, not one of its own', async ({ page }) => {
  const match = baseMatches()[0];
  await stubBackend(page, {
    day: (d: string) => dayPayload(d),
    matchById: () => ({ ...match, brief: briefWith(SCORED) }) as unknown as ApiMatch,
  });
  await page.goto(`/match/${match.id}`);
  await page.waitForLoadState('networkidle');

  await expect(page.getByTestId('brief-accuracy')).toContainText(SCORED);
  expect(await pageText(page)).not.toMatch(NOTHING_SCORED);
  expect(await pageText(page)).not.toMatch(/no accuracy has ever been measured/i);
});

test('with nothing scored the match page still carries the honest nothing-scored sentence', async ({ page }) => {
  const match = baseMatches()[0];
  const nothing = 'No prediction on this installation has been scored against a match result yet '
    + '(9 prediction(s) with a kickoff in 2026-06-21 to 2026-09-19 are eligible, 9 are still '
    + 'waiting to be scored), so no accuracy figure has been measured for it.';
  await stubBackend(page, {
    day: (d: string) => dayPayload(d),
    matchById: () => ({ ...match, brief: briefWith(nothing) }) as unknown as ApiMatch,
  });
  await page.goto(`/match/${match.id}`);
  await page.waitForLoadState('networkidle');

  await expect(page.getByTestId('brief-accuracy')).toContainText(nothing);
});
