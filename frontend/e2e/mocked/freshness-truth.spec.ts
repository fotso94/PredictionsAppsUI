import { test, expect, Page, Route, Request } from '@playwright/test';
import {
  ApiMatch, ApiTeam, Json, SyncTaskPayload, ProviderStatusPayload,
  baseStatus, dayPayload, fixtureAt, stubBackend,
} from '../support/api-stub';
import { signIn, regularUser } from '../support/auth';

/**
 * Three states in which the interface told the reader something the data did not support.
 *
 * This file is the adversarial half of e2e/mocked/freshness.spec.ts, which pins the four scheduler
 * states that must never blur together. Those still hold and are not touched here. What is added
 * is the set of states that are TWO things at once, because every defect below came from a display
 * that assumed they could only be one:
 *
 *   A FOLLOW WHOSE READ FAILED IS NOT A FOLLOW WITH NOTHING ON. Each follow is its own request and
 *   one can come back 500 while the others answer. The row said "No fixture stored for the next 7
 *   days" — a positive claim about data that had never arrived.
 *
 *   A TASK CAN BE FAILING AND PAUSED AT THE SAME TIME. The summary picked one branch, the failure
 *   won it, and the resume time — the only half a reader can act on — went with the branch that
 *   lost. It was not behind the disclosure either, because the detail rows drop whatever the
 *   summary is supposed to have said.
 *
 *   A TASK THAT RAN AND FAILED HAS RUN. "Has never run" and "has not succeeded yet" are different
 *   claims about different states, and the row has to make the same distinction the summary above
 *   it makes or the same block contradicts itself.
 *
 *   AN ATTEMPT THAT HAS NOT HAPPENED YET IS NOT A MOMENT IN THE PAST. The next attempt was
 *   described with a relative-time helper that renders a passed instant in the past tense, so any
 *   overdue task read "The next attempt is 2 minutes ago" — which every task on a short cadence
 *   does for part of every cycle, and a paused one does for hours.
 *
 *   A SENTENCE WITH NO SUBJECT BELONGS TO NOBODY. With two tasks in trouble the resume sentences
 *   were pooled at the end of the note, so two next-attempt times and two backoff windows sat in a
 *   row with nothing saying which task either pair described.
 *
 *   A CONTROL THAT DOES NOT ANSWER LOOKS BROKEN. Three Retry controls drive the same reload and
 *   one of them said nothing while it ran, which is the exact complaint Retry exists to answer.
 *
 * Every payload is stubbed. No provider request is made and no allowance is spent.
 */

// --------------------------------------------------------------------------- payloads
/*
 * Built here rather than in e2e/support/api-stub.ts, which another agent owns this round. Only the
 * shapes it already exports are imported; every combination this file needs and that file does not
 * have is assembled below.
 */
const ago = (minutes: number): string => new Date(Date.now() - minutes * 60_000).toISOString();
const ahead = (minutes: number): string => new Date(Date.now() + minutes * 60_000).toISOString();
const secondsAgo = (seconds: number): string => new Date(Date.now() - seconds * 1_000).toISOString();

/** The backend's own wording for the refusal that stopped the forecast provider. */
const QUOTA_REFUSAL = 'gameforecast: rate limit or quota exceeded (HTTP 429): You have exceeded the '
  + 'DAILY quota for Requests on your current plan, BASIC';
/** The backend's own wording for a skip once our side stops trying. */
const SPENT_ALLOWANCE = 'daily request budget for gameforecast is spent (8/8 used; 0 held back for page loads)';

/**
 * A forecasts task that has RUN, FAILED, and is now skipping while it waits.
 *
 * Both `consecutive_failures` and `last_skip_reason` are set, which the backend does publish
 * together and which the display treated as mutually exclusive. `never_run` is false and
 * `last_success_at` is null, which is the second pair that used to be conflated.
 */
function failingAndPausedForecasts(): SyncTaskPayload {
  return {
    enabled: true,
    interval_seconds: 21_600,
    never_run: false,
    last_run_at: ago(180),
    last_success_at: null,
    last_error_at: ago(180),
    last_error: `${QUOTA_REFUSAL}; 5 competition(s) deferred to the next reset`,
    last_duration_ms: 6312,
    last_result: null,
    last_skipped_at: ago(20),
    last_skip_reason: SPENT_ALLOWANCE,
    runs: 1,
    failures: 1,
    consecutive_failures: 1,
    backoff_seconds: 21_600,
    next_due_at: ahead(95),
    due_now: false,
    reason_not_due: `next due at ${ahead(95)}`,
  };
}

/** The same task FAILING ONLY: our own counter still has room, the provider is what refused. */
function failingForecasts(): SyncTaskPayload {
  return { ...failingAndPausedForecasts(), last_skipped_at: null, last_skip_reason: null };
}

/** Fixtures current; the forecast side in whatever state the caller wants to look at. */
function forecastStatusWith(task: SyncTaskPayload, coolingDown: string | null): ProviderStatusPayload {
  const status = baseStatus();
  status.scheduler!.tasks.forecasts = task;
  status.forecasts.cooling_down = coolingDown;
  return status;
}

/**
 * A task refreshing normally, as the base the states below bend out of shape.
 *
 * Written here rather than reusing the stub's `healthyTask` so that the fields these tests turn
 * on — `next_due_at`, `consecutive_failures`, `backoff_seconds` — are set explicitly at each call
 * site and a test cannot start asserting on a default it never chose.
 */
function healthyTaskPayload(
  intervalSeconds: number, minutesSinceSuccess: number, nextDueAt: string,
  overrides: Partial<SyncTaskPayload> = {},
): SyncTaskPayload {
  return {
    enabled: true,
    interval_seconds: intervalSeconds,
    never_run: false,
    last_run_at: ago(minutesSinceSuccess),
    last_success_at: ago(minutesSinceSuccess),
    last_error_at: null,
    last_error: null,
    last_duration_ms: 812,
    last_result: null,
    last_skipped_at: null,
    last_skip_reason: null,
    runs: 4,
    failures: 0,
    consecutive_failures: 0,
    backoff_seconds: null,
    next_due_at: nextDueAt,
    due_now: Date.parse(nextDueAt) <= Date.now(),
    reason_not_due: null,
    ...overrides,
  };
}

/** The healthy baseline with some of its tasks replaced. Forecasts are left alone and current. */
function schedulerWith(tasks: Record<string, SyncTaskPayload>): ProviderStatusPayload {
  const status = baseStatus();
  Object.assign(status.scheduler!.tasks, tasks);
  return status;
}

const team = (id: string, name: string): ApiTeam => ({
  id, name, short_name: name.slice(0, 3).toUpperCase(), logo: `/teams/${id}.svg`, country: 'England',
});

/** `GET /api/v1/me/favourites` for a reader following exactly these teams and nothing else. */
function favouritesFollowing(teams: ApiTeam[]): Json {
  return {
    teams,
    leagues: [],
    team_ids: teams.map(entry => entry.id),
    league_ids: [],
    unresolved: { teams: [], leagues: [] },
    saved_matches: {
      upcoming: [], live: [], finished: [],
      counts: { upcoming: 0, live: 0, finished: 0, total: 0 },
    },
    limits: { teams: 10, leagues: 5 },
  };
}

/**
 * Answer the reader's own endpoints.
 *
 * Registered AFTER stubBackend so it wins: Playwright matches the most recently added route first,
 * and stubBackend's catch-all would otherwise hand back an empty favourites object.
 */
async function stubMe(page: Page, favourites: Json): Promise<void> {
  await page.route('**/api/v1/me/**', (route: Route, request: Request) => {
    const path = new URL(request.url()).pathname;
    const body = path.endsWith('/favourites') ? favourites : {};
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

const freshness = (page: Page) => page.getByTestId('data-freshness');

async function openDetail(page: Page): Promise<void> {
  await freshness(page).getByTestId('freshness-detail').locator('summary').click();
}

// ------------------------------------------------- a failed follow is not an empty follow
/**
 * The measured defect: follow two teams, fail one team's request with a 500, and its row read
 * "No fixture stored for the next 7 days." One request answered and one never did, and the panel
 * reported both as the same thing.
 */
test('a follow whose fixtures could not be read says so and offers a retry, while an empty one stays empty', async ({ page }) => {
  const broken = team('team-broken', 'Unreadable Rovers');
  const quiet = team('team-quiet', 'Nothing Scheduled United');

  await stubBackend(page, {
    day: d => dayPayload(d),
    // Only this one team's read fails. Everything else, the other team included, answers normally.
    fail: url => (url.includes('/teams/team-broken') ? 500 : null),
  });
  await signIn(page, { user: regularUser() });
  await stubMe(page, favouritesFollowing([broken, quiet]));

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  const brokenRow = page.getByTestId('followed-team').filter({ hasText: broken.name });
  const quietRow = page.getByTestId('followed-team').filter({ hasText: quiet.name });
  await expect(brokenRow).toHaveCount(1);
  await expect(quietRow).toHaveCount(1);

  // THE FAILED FOLLOW. It says the read failed, it claims nothing about the fixtures, and it
  // offers the same way out the rest of the application offers.
  const failed = brokenRow.getByTestId('follow-fixture-failed');
  await expect(failed).toContainText(/could not be loaded, so nothing is claimed about them/i);
  await expect(brokenRow.getByTestId('follow-fixture-retry')).toBeVisible();
  // The sentence that was the whole defect must not be on this row.
  await expect(brokenRow).not.toContainText(/no fixture stored/i);

  // THE EMPTY FOLLOW, on the same page, from a read that genuinely succeeded with nothing in it.
  // It keeps its own wording — a statement about our stored window, not about the calendar.
  await expect(quietRow.getByTestId('follow-fixture-line')).toContainText(/no fixture stored for the next/i);
  await expect(quietRow.getByTestId('follow-fixture-failed')).toHaveCount(0);
  await expect(quietRow.getByTestId('follow-fixture-retry')).toHaveCount(0);

  /*
   * And the feed above makes the same distinction. With nothing to list it used to reach
   * "nothing you follow has a fixture stored in it", which is the identical defect one level up:
   * a claim about every follow, made while one of them had never been read.
   */
  const feed = page.getByTestId('feed-partly-unreadable');
  await expect(feed).toContainText(broken.name);
  await expect(feed).toContainText(/nothing we could read for your follows/i);
  await expect(feed).not.toContainText(/nothing you follow has a fixture stored/i);
  await expect(page.getByTestId('feed-window-empty')).toHaveCount(0);
});

test('retrying a failed follow recovers it, so an error is not left reading as a result', async ({ page }) => {
  const broken = team('team-broken', 'Unreadable Rovers');
  const quiet = team('team-quiet', 'Nothing Scheduled United');
  let refuse = true;

  /*
   * Two follows, one of which fails — the PARTIAL case. With a single follow every read fails,
   * the store reports the whole feed as an error, and the panel's existing whole-feed failure
   * state covers it; the row-level state this exercises is only reachable when some of the reads
   * came back and some did not.
   */
  await stubBackend(page, {
    day: d => dayPayload(d),
    fail: url => (refuse && url.includes('/teams/team-broken') ? 500 : null),
  });
  await signIn(page, { user: regularUser() });
  await stubMe(page, favouritesFollowing([broken, quiet]));

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  const row = page.getByTestId('followed-team').filter({ hasText: broken.name });
  await expect(row.getByTestId('follow-fixture-failed')).toBeVisible();

  // The backend recovers, and Retry is what lets the reader find that out without a reload.
  refuse = false;
  await row.getByTestId('follow-fixture-retry').click();

  // The read now succeeds and returns nothing, so the row lands on the honest empty sentence —
  // which is a different statement from the one it was making before, and only now earned.
  await expect(row.getByTestId('follow-fixture-line')).toContainText(/no fixture stored for the next/i);
  await expect(row.getByTestId('follow-fixture-failed')).toHaveCount(0);
  // The feed above drops its own qualification at the same moment, for the same reason.
  await expect(page.getByTestId('feed-partly-unreadable')).toHaveCount(0);
  await expect(page.getByTestId('feed-window-empty')).toBeVisible();
});

// ------------------------------------------------- failing and paused are not exclusive
test('a task that is failing AND paused shows both, with the time it comes back', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    status: forecastStatusWith(failingAndPausedForecasts(), null),
  });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  const note = block.getByTestId('freshness-note');

  // The failure, readable — and attributed to the failure, not to the skip.
  await expect(note).toContainText(/model forecasts: last attempt failed/i);
  await expect(note).toContainText(/the provider refused the request/i);
  // The pause, with ITS own reason. The two fields hold two different sentences and neither may
  // be printed under the other's heading, and the two summaries must differ: an upstream refusal
  // and our own spent allowance are different facts even when they arrive together.
  await expect(note).toContainText(/model forecasts: paused/i);
  await expect(note).toContainText(/our own daily request allowance for this provider is spent/i);
  // And the half a reader can act on, which the failure branch used to swallow.
  await expect(note).toContainText(/the next attempt is in/i);

  /*
   * BOTH UPSTREAM MESSAGES SURVIVE, one disclosure away. This test used to require them in the
   * note itself, which is how the vendor's name, our plan tier and an upgrade link ended up above
   * the football on a phone. Asserting them here keeps the guarantee that nothing was discarded.
   */
  const detail = block.getByTestId('freshness-detail');
  await detail.locator('summary').click();
  await expect(detail).toContainText(/exceeded the daily quota for requests/i);
  await expect(detail).toContainText(/daily request budget for gameforecast is spent/i);
  await expect(block.getByTestId('freshness-mechanics')).toContainText(/resets at 00:00 utc/i);
});

test('a forecast refresh the provider refused still says when it comes back', async ({ page }) => {
  /*
   * The state measured on the running installation: our own counter has room, so nothing is
   * SKIPPING, but the provider refused and the task's last attempt failed. The scheduler's note
   * won and the availability note — the only one carrying the allowance reset — was suppressed
   * wholesale, so the reader was told the forecasts are stuck and never told when they resume.
   */
  await stubBackend(page, {
    day: d => dayPayload(d),
    status: forecastStatusWith(failingForecasts(), QUOTA_REFUSAL),
  });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  const note = block.getByTestId('freshness-note');
  await expect(note).toContainText(/model forecasts: last attempt failed/i);
  // The note answers "when does it come back". HOW that answer was worked out — which calendar
  // our allowance resets on — is mechanics and lives in the disclosure.
  await expect(note).toContainText(/the next attempt is in/i);
  await expect(note).not.toContainText(/resets at 00:00 utc/i);
  await block.getByTestId('freshness-detail').locator('summary').click();
  await expect(block.getByTestId('freshness-mechanics')).toContainText(/resets at 00:00 utc/i);

  // Stated once. Two paths can answer "when does it come back" and the reader meeting the same
  // sentence twice reads it as two separate problems.
  const resets = ((await block.innerText()).match(/resets at 00:00 UTC/gi) ?? []).length;
  expect(resets, 'the reset time is stated once, not once per source that knows it').toBe(1);

  // The fixture side is current and is not dragged down by the forecast side's trouble.
  await expect(block.getByTestId('freshness-summary')).toContainText(/fixtures and scores last refreshed/i);
});

// ------------------------------------------------- ran and failed is not never ran
test('a task that ran and failed is not described as never having run', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    status: forecastStatusWith(failingAndPausedForecasts(), null),
  });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  // The summary already drew this distinction; the row underneath has to draw the same one.
  await expect(block.getByTestId('freshness-forecasts')).toContainText(/no refresh has succeeded yet/i);

  await openDetail(page);
  const row = block.locator('[data-task="forecasts"]');
  await expect(row).toContainText(/has not succeeded yet/i);
  await expect(row).not.toContainText(/has never run/i);

  // And a task that really never has run still says so, so this is a distinction and not a rename.
  const neverRun = { ...failingAndPausedForecasts(), never_run: true, runs: 0, last_run_at: null };
  await stubBackend(page, { day: d => dayPayload(d), status: forecastStatusWith(neverRun, null) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');
  await openDetail(page);
  await expect(freshness(page).locator('[data-task="forecasts"]')).toContainText(/has never run/i);
});

// ------------------------------------------------- an attempt still to come is not a past moment
/**
 * The measured defect: "THE NEXT ATTEMPT IS 2 MINUTES AGO", live on the settle row.
 *
 * The sentence was built from a relative-time helper whose past branch describes a MOMENT that has
 * passed, and an attempt that has not happened is not one. Being late is a real state and worth
 * saying — a reader looking at a stuck refresh wants to know it is late, not to watch the line
 * vanish — so both ends of the range are checked here: seconds past due, which is the ordinary
 * condition of anything on a short cadence, and hours past due, which is what a paused or failing
 * task leaves behind.
 */
test('an attempt that is already late is reported as late, never as a moment in the past', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    status: schedulerWith({
      // Seconds past due on a half-hourly cadence: late, but not yet a full interval behind, so
      // this is the state every healthy task passes through between ticks.
      results: healthyTaskPayload(1800, 10, secondsAgo(15)),
      // Hours past due, and still inside its own six-hour interval, so nothing is called a fault:
      // the only thing said about it is when it should have run.
      fixtures: healthyTaskPayload(21_600, 660, ago(300)),
      // Hours past due on a two-minute cadence. This one IS a fault, and the summary says so.
      live: healthyTaskPayload(120, 300, ago(180)),
    }),
  });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);

  // THE SENTENCE THAT WAS WRONG, in neither of its two shapes. "just now" is what the old helper
  // returned seconds past due and "5 hours ago" is what it returned hours past due; both of them
  // put an attempt still to come in the past tense.
  await expect(block).not.toContainText(/the next attempt is (just now|\d+ (second|minute|hour|day)s? ago)/i);

  // Being late is still SAID, and said about the task it is true of.
  const note = block.getByTestId('freshness-note');
  await expect(note).toContainText(/live scores.*more than a full interval past due/i);
  await expect(note).toContainText(/the next attempt is overdue by 3 hours\./i);

  await openDetail(page);
  // Seconds past due reads as being due, not as a length of time too small to name.
  await expect(block.locator('[data-task="results"]')).toContainText(/the next attempt is due now\./i);
  // And hours past due reads as hours late, on the row where a reader goes looking for it.
  await expect(block.locator('[data-task="fixtures"]')).toContainText(/the next attempt is overdue by 5 hours\./i);
});

// ------------------------------------------------- a statement with no subject belongs to nobody
/**
 * The measured defect: with two tasks in trouble the block read "The next attempt is in 10
 * minutes. After 3 failures in a row it is waiting 10 minutes before trying again. The next
 * attempt is in 30 minutes. After 2 failures in a row it is waiting 30 minutes before trying
 * again." Four sentences, two tasks, and nothing saying which pair described which.
 */
test('with two tasks in trouble every sentence stays with the task it is about', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    status: schedulerWith({
      live: healthyTaskPayload(120, 30, ahead(10), {
        last_error_at: ago(3), last_error: 'livescore: network error',
        failures: 3, consecutive_failures: 3, backoff_seconds: 600,
      }),
      results: healthyTaskPayload(1800, 45, ahead(30), {
        last_error_at: ago(5), last_error: 'settlement store: database timeout',
        failures: 2, consecutive_failures: 2, backoff_seconds: 1800,
      }),
    }),
  });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const text = (await freshness(page).getByTestId('freshness-note').innerText()).replace(/\s+/g, ' ');
  /** Where a sentence sits in the note, asserting on the way through that it is there at all. */
  const at = (needle: RegExp): number => {
    const index = text.search(needle);
    expect(index, `${needle} is missing from: ${text}`).toBeGreaterThanOrEqual(0);
    return index;
  };

  // Each failure carries its OWN reason. Neither task is described with the other's error.
  expect(text).toContain('Live scores: last attempt failed — livescore: network error.');
  // Summarised, and crucially NOT reattributed: a timeout in our own settlement store is ours.
  // An earlier summary rendered this as "the provider did not answer in time", which blames an
  // upstream service for a database of ours that the message never mentioned.
  expect(text).toContain('Final results: last attempt failed — it timed out before answering.');
  expect(text).not.toContain('Final results: last attempt failed — the provider');

  // And each task's two follow-up sentences sit inside that task's own statement rather than in a
  // pool at the end, which is the whole of what makes them attributable.
  const live = at(/Live scores: last attempt failed/);
  const results = at(/Final results: last attempt failed/);
  expect(results).toBeGreaterThan(live);
  expect(at(/The next attempt is in 10 minutes\./)).toBeGreaterThan(live);
  expect(at(/The next attempt is in 10 minutes\./)).toBeLessThan(results);
  expect(at(/The next attempt is in 30 minutes\./)).toBeGreaterThan(results);

  /*
   * The backoff windows are no longer here to be ordered: they are mechanics and moved into the
   * disclosure, which is the point of this round. They are still attributable there, because
   * each line is written with its own task's name in front of it, and that is what is asserted.
   */
  await freshness(page).getByTestId('freshness-detail').locator('summary').click();
  const mechanics = (await freshness(page).getByTestId('freshness-mechanics').innerText())
    .replace(/\s+/g, ' ');
  expect(mechanics).toContain('Live scores: after 3 failures in a row it is waiting 10 minutes');
  expect(mechanics).toContain('Final results: after 2 failures in a row it is waiting 30 minutes');
});

// ------------------------------------------------- one failure is not a run of failures
/**
 * The measured defect, read off the running installation rather than constructed: the forecasts
 * task is exactly one failure deep with a six-hour backoff, and the note said "After 1 failure in
 * a row it is waiting 360 minutes before trying again."
 *
 * A run of one is not a run. And 360 minutes is the same span the cadence line two lines below
 * calls "6 hours", so one duration was given two different numbers inside one block — the defect
 * `overduePhrase` was added to stop, in the sentence next to the one it fixed.
 */
test('a single failure is not described as a run, and its backoff is in the units the block uses', async ({ page }) => {
  await stubBackend(page, {
    day: d => dayPayload(d),
    // consecutive_failures: 1 and backoff_seconds: 21600 — the live forecasts task exactly.
    status: forecastStatusWith(failingForecasts(), null),
  });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const block = freshness(page);
  // The note stays short: which refresh is stuck, and when it next tries. The backoff window is
  // how that time was arrived at, so it reads one disclosure away.
  await expect(block.getByTestId('freshness-note')).toContainText(/the next attempt is in/i);
  await expect(block.getByTestId('freshness-note')).not.toContainText(/before trying again/i);

  await block.getByTestId('freshness-detail').locator('summary').click();
  const mechanics = block.getByTestId('freshness-mechanics');
  await expect(mechanics).toContainText('after 1 failure it is waiting 6 hours before trying again.');
  await expect(mechanics).not.toContainText(/failure in a row/i);
  await expect(mechanics).not.toContainText(/360 minutes/i);
});

// ------------------------------------------------- the three Retry controls answer the same way
/**
 * Hold the follow fan-out open, so a Retry can be looked at while it is still running.
 *
 * `upcomingFor` returns the fixtures a team's read should answer with, null to make that one read
 * fail, or undefined for an id this test knows nothing about — which is handed back to the main
 * stub rather than answered with a team-shaped body, so `/teams/search` keeps its own shape.
 */
async function heldTeamFixtures(
  page: Page, upcomingFor: (id: string) => ApiMatch[] | null | undefined,
): Promise<{ hold: () => void; release: () => void }> {
  let release: (() => void) | null = null;
  let held: Promise<void> | null = null;

  await page.route('**/api/v1/teams/**', async (route: Route, request: Request) => {
    const id = new URL(request.url()).pathname.split('/').filter(Boolean).pop() ?? '';
    const upcoming = upcomingFor(id);
    if (upcoming === undefined) return route.fallback();
    if (held) await held;
    return upcoming === null
      ? route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Simulated backend failure' }) })
      : route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ team: null, upcoming, recent: [] }),
      });
  });

  return {
    hold: () => { held = new Promise<void>(resolve => { release = resolve; }); },
    release: () => { held = null; release?.(); release = null; },
  };
}

/**
 * The measured defect: three controls reload the same follow fan-out, two of them say "Trying
 * again…" while it runs, and the one in the feed-partly-unreadable empty state only went grey. A
 * reader who presses a control and is told nothing cannot tell a slow reload from a dead button.
 */
test('the Retry in the unreadable-follow empty state reports itself, like the row Retry beside it', async ({ page }) => {
  const broken = team('team-broken', 'Unreadable Rovers');
  const quiet = team('team-quiet', 'Nothing Scheduled United');

  await stubBackend(page, { day: d => dayPayload(d) });
  await signIn(page, { user: regularUser() });
  await stubMe(page, favouritesFollowing([broken, quiet]));
  const gate = await heldTeamFixtures(page, id => (id === broken.id ? null : id === quiet.id ? [] : undefined));

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  // Nothing readable fell in the window, and one follow never answered: the empty state that
  // carries its own Retry.
  const emptyRetry = page.getByTestId('feed-partly-unreadable-retry');
  const rowRetry = page.getByTestId('follow-fixture-retry').first();
  await expect(emptyRetry).toHaveText('Try again');
  await expect(rowRetry).toHaveText('Try again');

  gate.hold();
  await emptyRetry.click();

  await expect(emptyRetry).toHaveText('Trying again…');
  await expect(emptyRetry).toBeDisabled();
  // The row control is driven by the same reload and has always said so; both now agree.
  await expect(rowRetry).toHaveText('Trying again…');

  // And when the reload lands the label goes back, so "Trying again…" means what it says.
  gate.release();
  await expect(emptyRetry).toHaveText('Try again');
  await expect(rowRetry).toHaveText('Try again');
});

test('the Retry on a feed shortened by an unreadable follow reports itself too', async ({ page }) => {
  const broken = team('team-broken', 'Unreadable Rovers');
  const playing = team('team-playing', 'Fixture Held City');
  const fixture = fixtureAt(ahead(2 * 24 * 60), playing.name, 'Someone Else', 'feed-held-fixture');

  await stubBackend(page, { day: d => dayPayload(d) });
  await signIn(page, { user: regularUser() });
  await stubMe(page, favouritesFollowing([broken, playing]));
  const gate = await heldTeamFixtures(page, id => (id === broken.id ? null : id === playing.id ? [fixture] : undefined));

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  // One follow answered with a fixture, so the feed has content and carries the short-feed
  // qualification rather than an empty state.
  await expect(page.getByTestId('feed-incomplete')).toContainText(broken.name);
  const incompleteRetry = page.getByTestId('feed-incomplete-retry');
  const rowRetry = page.getByTestId('follow-fixture-retry').first();
  await expect(incompleteRetry).toHaveText('Try again');

  gate.hold();
  await incompleteRetry.click();

  await expect(incompleteRetry).toHaveText('Trying again…');
  await expect(rowRetry).toHaveText('Trying again…');

  gate.release();
  await expect(incompleteRetry).toHaveText('Try again');
});
