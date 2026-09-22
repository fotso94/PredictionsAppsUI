import { test, expect, Page, Route } from '@playwright/test';
import { stubBackend, emptyDayPayload, dayPayload } from '../support/api-stub';
import { signIn } from '../support/auth';

/**
 * What an empty matchday says about when football comes back.
 *
 * From 2026-09-21 the six covered competitions were in the international break and the first
 * fixture in any of them was eighteen days out. Every list in between was correctly empty, and
 * "no matches stored for this date" was a true sentence that told the reader nothing they could
 * use. The empty state now names the next fixtures, read from the providers' competition
 * calendars through `/matches/upcoming`.
 *
 * The thing that must not break is the honesty of it. `/matches/upcoming` answers four different
 * ways and they are four different sentences:
 *
 *   known, with fixtures       we read every calendar and this is what is next;
 *   known, with fixtures,
 *     some competitions
 *     unanswered               we read some calendars, these come next among them, and a
 *                              competition we could not reach may play sooner;
 *   known, with none           we read every calendar and none lists anything more;
 *   not known                  nobody could tell us.
 *
 * Two of them look identical from outside — an empty list either way — and collapsing them is
 * how a network failure ends up printed as "no football is scheduled". So each is asserted
 * separately, and each is asserted to be absent from the others.
 *
 * The last one is also asserted not to stick. It is remembered for a couple of minutes, so that a
 * reader who keeps coming back does not re-ask into the same bad minute, and it is forgotten
 * again after that: a day that could not find out never becomes a session that cannot, and no
 * reader has to reload anything to get out of one — every one of those failures arrives as a
 * perfectly successful HTTP 200 and would otherwise be indistinguishable from an answer.
 *
 * And a failure may never take anything away. A refresh that cannot answer leaves the notice the
 * reader is already reading exactly where it is; the section at the bottom of this file is about
 * that alone.
 *
 * `/matches/upcoming` is stubbed here rather than left to the shared stub: the shared handler
 * routes anything under `/matches/` to the match-by-id branch, which answers 404. That is the
 * right thing for a page that never asks, and it is also one more state tested below - a request
 * that fails outright must render nothing at all.
 */

const UPCOMING = '**/api/v1/matches/upcoming*';
const LANGUAGE_KEY = 'sp.language.v1';
const ZONE_KEY = 'sp.timeZone.v1';

/** The shape `/matches/upcoming` returns. Kickoffs are UTC, as the backend sends them. */
interface UpcomingBody {
  known: boolean;
  next_kickoff: string | null;
  fixtures: Array<{
    competition: { key: string; name: string };
    home: string;
    away: string;
    kickoff_utc: string;
  }>;
  /** Covered competitions nobody could be asked about; the fixtures do not speak for these. */
  unanswered: string[];
}

/** The real 9 October answer, as the provider's calendar gave it on 2026-09-21. */
const RESUMES_9_OCTOBER: UpcomingBody = {
  known: true,
  unanswered: [],
  next_kickoff: '2026-10-09T18:30:00+00:00',
  fixtures: [
    {
      competition: { key: 'bundesliga', name: 'Bundesliga' },
      home: 'Borussia Dortmund', away: 'Werder Bremen',
      kickoff_utc: '2026-10-09T18:30:00+00:00',
    },
    {
      competition: { key: 'ligue_1', name: 'Ligue 1' },
      home: 'Lens', away: 'Lyon',
      kickoff_utc: '2026-10-09T18:45:00+00:00',
    },
  ],
};

/**
 * Register the `/matches/upcoming` answer.
 *
 * Playwright checks route handlers in reverse registration order, so this must be registered
 * AFTER `stubBackend` for its `**\/api/v1/**` catch-all not to win.
 */
async function stubUpcoming(page: Page, body: UpcomingBody | 'fails'): Promise<void> {
  await page.route(UPCOMING, (route: Route) => (
    body === 'fails'
      ? route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"no"}' })
      : route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  ));
}

/** The reader's stored choices, in place before the app boots and reads them. */
async function seedPreferences(page: Page, language: 'en' | 'fr', zone: string): Promise<void> {
  await page.addInitScript(
    ([languageKey, zoneKey, lang, tz]) => {
      window.localStorage.setItem(languageKey, lang);
      window.localStorage.setItem(zoneKey, tz);
    },
    [LANGUAGE_KEY, ZONE_KEY, language, zone] as const,
  );
}

async function openEmptyDay(page: Page): Promise<void> {
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('matchday-empty')).toBeVisible();
}

// ------------------------------------------------------- known, and there are fixtures to name
test('an empty day names when the competitions play again, and who plays', async ({ page }) => {
  await seedPreferences(page, 'en', 'Europe/Paris');
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  await stubUpcoming(page, RESUMES_9_OCTOBER);

  await openEmptyDay(page);

  const upcoming = page.getByTestId('matchday-upcoming');
  await expect(upcoming).toBeVisible();
  await expect(upcoming).toContainText('These competitions play again on Friday, 9 October 2026.');
  // 18:30 UTC is 20:30 in Paris: the kickoff is shown in the reader's chosen zone, not in UTC.
  await expect(upcoming).toContainText('Borussia Dortmund v Werder Bremen — Bundesliga, 20:30');
  await expect(upcoming).toContainText('Lens v Lyon — Ligue 1, 20:45');

  // The sentence the empty state already made is not replaced by the new one.
  await expect(page.getByTestId('matchday-empty')).toContainText(/no matches stored for this date/i);
});

test('the same answer reads as French for a French reader', async ({ page }) => {
  await seedPreferences(page, 'fr', 'Europe/Paris');
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  await stubUpcoming(page, RESUMES_9_OCTOBER);

  await openEmptyDay(page);

  const upcoming = page.getByTestId('matchday-upcoming');
  await expect(upcoming).toContainText('Ces compétitions rejouent le vendredi 9 octobre 2026.');
  await expect(upcoming).toContainText('Premiers matchs');
  // French does not oppose two clubs with "v": the separator belongs to the catalogue, not to the
  // component, and this is the assertion that keeps it there.
  await expect(upcoming).toContainText('Borussia Dortmund - Werder Bremen — Bundesliga, 20:30');
  await expect(upcoming).not.toContainText('Dortmund v Werder');
});

// ------------------------------------------------------- the two silences, told apart
test('a calendar that was read and lists nothing says so', async ({ page }) => {
  await seedPreferences(page, 'en', 'Europe/Paris');
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  await stubUpcoming(page, { known: true, next_kickoff: null, fixtures: [], unanswered: [] });

  await openEmptyDay(page);

  await expect(page.getByTestId('matchday-upcoming-none'))
    .toContainText('The competition calendars list no fixture still to come.');
  await expect(page.getByTestId('matchday-upcoming')).toHaveCount(0);
  await expect(page.getByTestId('matchday-upcoming-unknown')).toHaveCount(0);
});

test('a calendar nobody could read is reported as not known, never as no football', async ({ page }) => {
  await seedPreferences(page, 'en', 'Europe/Paris');
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  await stubUpcoming(page, { known: false, next_kickoff: null, fixtures: [], unanswered: [] });

  await openEmptyDay(page);

  await expect(page.getByTestId('matchday-upcoming-unknown'))
    .toContainText('We could not find out when these competitions play next.');
  await expect(page.getByTestId('matchday-upcoming-none')).toHaveCount(0);
  const body = (await page.locator('body').innerText()).toLowerCase();
  expect(body, 'an unread calendar must not be reported as an empty one')
    .not.toContain('list no fixture still to come');
});

test('a request that fails adds nothing at all to the empty state', async ({ page }) => {
  await seedPreferences(page, 'en', 'Europe/Paris');
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  await stubUpcoming(page, 'fails');

  await openEmptyDay(page);

  await expect(page.getByTestId('matchday-upcoming')).toHaveCount(0);
  await expect(page.getByTestId('matchday-upcoming-none')).toHaveCount(0);
  await expect(page.getByTestId('matchday-upcoming-unknown')).toHaveCount(0);
  // And the state it sits in is untouched: the day still says what it holds.
  await expect(page.getByTestId('matchday-empty')).toContainText(/holds no fixtures/i);
});

// ------------------------------------------------------- a partial answer speaks for its part
test('an answer that missed some calendars does not speak for the ones it missed', async ({ page }) => {
  await seedPreferences(page, 'en', 'Europe/Paris');
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  await stubUpcoming(page, { ...RESUMES_9_OCTOBER, unanswered: ['serie_a', 'la_liga'] });

  await openEmptyDay(page);

  const upcoming = page.getByTestId('matchday-upcoming');
  // The fixtures that were read are still named, and still dated: what changes is the size of
  // the claim made above them, because Serie A or La Liga may play before 9 October.
  await expect(upcoming).toContainText(
    'Of the calendars we could read, the next fixtures are on Friday, 9 October 2026.');
  await expect(upcoming).toContainText('Borussia Dortmund v Werder Bremen — Bundesliga, 20:30');
  await expect(upcoming).not.toContainText('These competitions play again on');
});

test('a partial answer with nothing in it is not reported as a calendar with nothing in it',
  async ({ page }) => {
    await seedPreferences(page, 'en', 'Europe/Paris');
    await stubBackend(page, { day: d => emptyDayPayload(d) });
    await stubUpcoming(page, {
      known: true, next_kickoff: null, fixtures: [], unanswered: ['serie_a'],
    });

    await openEmptyDay(page);

    // Serie A was never asked, so "the calendars list no fixture still to come" is not available.
    await expect(page.getByTestId('matchday-upcoming-unknown')).toBeVisible();
    await expect(page.getByTestId('matchday-upcoming-none')).toHaveCount(0);
  });

// ------------------------------------------------------- what is remembered between empty days
/**
 * Answer each call with the next entry in `answers`, repeating the last one, and count the calls.
 *
 * `'fails'` is a request that does not come back with an answer at all — a 503 from a gateway, a
 * backend that is down — as opposed to the `known: false` body, which is this endpoint answering
 * that nobody could tell it. The note has to survive both, and they are not the same event.
 */
async function stubUpcomingInTurn(
  page: Page, answers: Array<UpcomingBody | 'fails'>,
): Promise<{ calls: number }> {
  const counter = { calls: 0 };
  await page.route(UPCOMING, (route: Route) => {
    const body = answers[Math.min(counter.calls, answers.length - 1)];
    counter.calls += 1;
    return body === 'fails'
      ? route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"no"}' })
      : route.fulfill({
        status: 200, contentType: 'application/json', body: JSON.stringify(body),
      });
  });
  return counter;
}

/**
 * What the endpoint sends when it could not find out — an outage behind it, or its own backoff or
 * daily ceiling refusing to spend on another calendar sweep. A perfectly successful HTTP 200 with
 * no answer in it, which is why the two silences are told apart above.
 */
const COULD_NOT_FIND_OUT: UpcomingBody = {
  known: false, next_kickoff: null, fixtures: [], unanswered: [],
};

test('a day that could not find out does not stop the next empty day from asking', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  // Every calendar failure reaches the browser as a successful response saying `known: false`,
  // so this is what a blip looks like from here: 200, and no answer in it.
  const upcoming = await stubUpcomingInTurn(page, [COULD_NOT_FIND_OUT, RESUMES_9_OCTOBER]);

  await openEmptyDay(page);
  await expect(page.getByTestId('matchday-upcoming-unknown')).toBeVisible();

  // The day next door, opened straight away. The blip is a few seconds old and the backend that
  // could not answer it cannot have a different answer yet, so this day is told what the last one
  // was told rather than asking again into the same minute — see FAILURE_TTL_MS.
  await page.getByTestId('matchday-empty-jump').click();
  await expect(page.getByTestId('matchday-upcoming-unknown')).toBeVisible();
  expect(upcoming.calls, 'a blip is not re-asked into the minute it happened in').toBe(1);

  // Past that window it is asked again: what is remembered is a bad minute, not a bad session,
  // and no reader has to reload anything to get out of it.
  await page.clock.fastForward(FAILURE_TTL_MS + 60 * 1000);
  await page.getByTestId('matchday-empty-jump').click();

  await expect(page.getByTestId('matchday-upcoming'))
    .toContainText('These competitions play again on Friday, 9 October 2026.');
  expect(upcoming.calls, 'the blip belongs to the minutes it happened in, not to the session')
    .toBe(2);
});

/*
 * THE CLOCK IS PINNED HERE TOO, not only in the expiry block further down, and the reason is the
 * assertion at the end rather than anything about ageing.
 *
 * `stillCurrent` in src/components/matches/nextFixtures.ts keeps an answer only until the kickoff
 * it names has passed. RESUMES_9_OCTOBER names 2026-10-09T18:30Z, so on the real clock this test
 * asks one question before that instant and a different one after it: from 18:30 UTC that day the
 * answer expires BETWEEN the two empty days, the note is fetched a second time, and the count
 * below reads 2 for a reason that has nothing to do with the behaviour under test. Measured by
 * pinning the clock to 2026-10-20 — the count came back 2 and the test failed.
 *
 * START is before the kickoff the answer names, so the question is the same one on every date.
 */
test('an answer already given is not paid for again on the next empty day', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  const upcoming = await stubUpcomingInTurn(page, [RESUMES_9_OCTOBER]);

  await openEmptyDay(page);
  await expect(page.getByTestId('matchday-upcoming')).toBeVisible();

  await page.getByTestId('matchday-empty-jump').click();

  await expect(page.getByTestId('matchday-upcoming'))
    .toContainText('These competitions play again on Friday, 9 October 2026.');
  expect(upcoming.calls, 'one answer serves every empty day the reader walks through')
    .toBe(1);
});

// ------------------------------------------------------- only an empty day pays for the answer
test('a day with fixtures on it never asks when football resumes', async ({ page }) => {
  await seedPreferences(page, 'en', 'Europe/Paris');
  await stubBackend(page, { day: d => dayPayload(d) });
  const asked: string[] = [];
  await page.route(UPCOMING, (route: Route) => {
    asked.push(route.request().url());
    return route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify(RESUMES_9_OCTOBER),
    });
  });

  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  await expect(page.getByTestId('matchday-empty')).toHaveCount(0);
  expect(asked, 'the calendar costs a provider request per competition; a full day must not ask')
    .toEqual([]);
});

/* ==========================================================================================
 * HOW LONG AN ANSWER LASTS, AND WHAT MAKES THE NOTE ASK AGAIN
 *
 * Everything above proves what the note SAYS. Everything below proves how long it is entitled to
 * go on saying it, which is a different property and the one a tab left open all week breaks.
 *
 * Two expiries, and an answer lives only until the first of them (see `stillCurrent` in
 * src/components/matches/nextFixtures.ts):
 *
 *   the kickoff it names   once that instant is behind the reader the answer describes the past;
 *   its own age            because a kickoff eighteen days out is no expiry at all, and eighteen
 *                          days out is exactly what an international break looks like.
 *
 * And one trigger to notice either without a reader reloading by hand: coming back to the tab.
 *
 * THE CLOCK IS DRIVEN, NEVER WAITED ON. `page.clock` moves the BROWSER's clock; the stub decides
 * what the next answer is. Nothing here sleeps for six hours and nothing here depends on the hour
 * the suite is run.
 *
 * WHAT COSTS WHAT. `/matches/upcoming` is one provider request PER COVERED COMPETITION on a
 * miss, so every test below counts the requests as carefully as it reads the sentence, and the
 * ones that assert a refresh happens are matched by ones that assert it does not.
 * ========================================================================================== */

/**
 * Where the browser's clock starts. A fixed instant, chosen so that six hours and five minutes
 * later it is still the same calendar day in both the suite's timezone (America/New_York) and the
 * reader's chosen one (Europe/Paris): the day the matchday list is showing must not move
 * underneath a test that is about something else.
 */
const START = new Date('2026-09-22T09:00:00Z');

/**
 * Mirrors ANSWER_TTL_MS in src/components/matches/nextFixtures.ts, which is deliberately the same
 * six hours as CALENDAR_HEAD_TTL_SECONDS in backend/app/services/match_data_service.py. A change
 * to either that is not made here will show up as one of the two age tests below failing, which
 * is the point of having both sides of the boundary.
 */
const ANSWER_TTL_MS = 6 * 60 * 60 * 1000;

/**
 * Mirrors FAILURE_TTL_MS in src/components/matches/nextFixtures.ts: how briefly a request that
 * could not be answered is remembered, so that a reader coming back does not re-ask into the same
 * bad minute. Two minutes, the shortest interval in which the backend behind this endpoint can
 * possibly have tried again — see that file for why.
 */
const FAILURE_TTL_MS = 2 * 60 * 1000;

/**
 * An answer whose kickoff is two minutes out, so it can be walked past without touching the age
 * limit. The clubs are invented, as everywhere in the mocked suite: what is under test is the
 * instant in `next_kickoff`, not the fixture.
 */
const KICKOFF_TWO_MINUTES_OUT: UpcomingBody = {
  known: true,
  unanswered: [],
  next_kickoff: '2026-09-22T09:02:00+00:00',
  fixtures: [
    {
      competition: { key: 'bundesliga', name: 'Bundesliga' },
      home: 'Fenchurch Rangers', away: 'Deptford Albion',
      kickoff_utc: '2026-09-22T09:02:00+00:00',
    },
  ],
};

/**
 * The answer a re-ask is given, and the only thing that matters about it is that it is
 * DISTINGUISHABLE from the one already on screen: if the note still says 9 October, the re-ask
 * never reached the reader. A calendar that has moved is also the reason the age limit exists —
 * a postponement does not move the kickoff an answer already named.
 */
const POSTPONED_TO_10_OCTOBER: UpcomingBody = {
  known: true,
  unanswered: [],
  next_kickoff: '2026-10-10T14:00:00+00:00',
  fixtures: [
    {
      competition: { key: 'bundesliga', name: 'Bundesliga' },
      home: 'Borussia Dortmund', away: 'Werder Bremen',
      kickoff_utc: '2026-10-10T14:00:00+00:00',
    },
  ],
};

const SAYS_9_OCTOBER = 'These competitions play again on Friday, 9 October 2026.';
const SAYS_10_OCTOBER = 'These competitions play again on Saturday, 10 October 2026.';
const SAYS_TODAY = 'These competitions play again on Tuesday, 22 September 2026.';

/** Mirrors PREFERENCES_KEY_PREFIX in src/services/favourites.service.ts. */
const preferencesKeyFor = (userId: string) => `personal.preferences.v1.${userId}`;

/**
 * The tab switch is SYNTHESISED, for the reason recorded in e2e/mocked/detail-refresh.spec.ts:
 * headless Chromium never blurs or hides a page, so `bringToFront()` on another page leaves this
 * one reporting `visibilityState: "visible"` throughout and fires neither event.
 *
 * So the pair a browser really sends on the way back is dispatched, in the order it sends them.
 * Only the trigger is synthetic — the listener, the visibility test, the expiry check, the
 * request and the render are all the application's own, and breaking any of them fails these
 * tests. Dispatching BOTH is deliberate: one return must not cost two requests.
 */
async function comeBackToTheTab(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('focus'));
  });
}

/**
 * Put the tab behind another one, the only way available here: `document.visibilityState` is a
 * getter on `Document.prototype`, and an own property shadows it for the page's own code exactly
 * as the browser's own hidden state would read.
 */
async function setTabVisibility(page: Page, state: 'visible' | 'hidden'): Promise<void> {
  await page.evaluate(value => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => value });
  }, state);
}

/** Seed one reader's stored settings, before the application boots and binds them. */
async function seedStoredPreferences(
  page: Page, userId: string, liveUpdates: boolean,
): Promise<void> {
  await page.addInitScript(([key, value]) => {
    window.localStorage.setItem(key, value);
  }, [preferencesKeyFor(userId), JSON.stringify({
    forecasts: true, prompts: true, liveUpdates, paused: false,
  })] as const);
}

/** The clock and the reader's choices, in the order the application reads them. */
async function openAt(page: Page, at: Date): Promise<void> {
  await page.clock.install({ time: at });
  // The clock is JUMPED, never stopped: a paused clock would also freeze everything these tests
  // are not about, and would prove less about a page that is otherwise running normally.
  await page.clock.resume();
  await seedPreferences(page, 'en', 'Europe/Paris');
}

// ------------------------------------------------------------------- expiry: the age of an answer
/**
 * WHY AN ANSWER NEEDS AN AGE LIMIT WHEN IT ALREADY NAMES A KICKOFF TO EXPIRE AGAINST. Through an
 * international break that kickoff is eighteen days out, so on its own it is no limit at all: a
 * tab open across a week would hold a calendar a week old, and a reader whose fixture had been
 * postponed in the meantime would never be told.
 *
 * Both sides of the boundary are asserted in one test on purpose. "It asks again after six hours"
 * passes just as well if the answer were never kept at all, which is a worse fault than the one
 * the age limit prevents; the first half is what rules that out.
 */
test('an answer is kept up to the age limit and asked again past it, kickoff or no kickoff',
  async ({ page }) => {
    await openAt(page, START);
    await stubBackend(page, { day: d => emptyDayPayload(d) });
    const upcoming = await stubUpcomingInTurn(page, [RESUMES_9_OCTOBER, POSTPONED_TO_10_OCTOBER]);

    await openEmptyDay(page);
    await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_9_OCTOBER);
    expect(upcoming.calls).toBe(1);

    // Five minutes short of the limit, with the named kickoff seventeen days ahead: a walk
    // through the empty days is still served from the answer this session already has.
    await page.clock.fastForward(ANSWER_TTL_MS - 5 * 60 * 1000);
    await page.getByTestId('matchday-empty-jump').click();
    await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_9_OCTOBER);
    expect(upcoming.calls, 'an answer inside its age must not be paid for twice').toBe(1);

    // Ten minutes later it is past the limit. The kickoff it names has not moved and is still
    // seventeen days off, so age is the only thing that can expire it.
    await page.clock.fastForward(10 * 60 * 1000);
    await page.getByTestId('matchday-empty-jump').click();

    await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_10_OCTOBER);
    expect(upcoming.calls, 'an answer older than the age limit must be asked again').toBe(2);
  });

// --------------------------------------------------------------- expiry: the kickoff it names
test('an answer whose kickoff has passed is asked again, long before it is old', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  const upcoming = await stubUpcomingInTurn(page, [KICKOFF_TWO_MINUTES_OUT, POSTPONED_TO_10_OCTOBER]);

  await openEmptyDay(page);
  await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_TODAY);

  // Three minutes: the kickoff is behind the reader and the answer is three minutes old, which is
  // nowhere near the age limit. The kickoff has to expire it on its own.
  await page.clock.fastForward(3 * 60 * 1000);
  await page.getByTestId('matchday-empty-jump').click();

  await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_10_OCTOBER);
  expect(upcoming.calls, 'an answer about a kickoff that has happened must be asked again').toBe(2);
});

/**
 * The answer with nothing to expire against, and the strongest sentence on this screen: "the
 * competition calendars list no fixture still to come" is a claim about every covered
 * competition. A calendar read empty during a break fills in later, and age is the only thing
 * that can take this one back.
 */
test('an answer that names nothing to come expires on the clock like any other', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  const upcoming = await stubUpcomingInTurn(page, [
    { known: true, next_kickoff: null, fixtures: [], unanswered: [] },
    POSTPONED_TO_10_OCTOBER,
  ]);

  await openEmptyDay(page);
  await expect(page.getByTestId('matchday-upcoming-none')).toBeVisible();

  await page.clock.fastForward(ANSWER_TTL_MS - 5 * 60 * 1000);
  await page.getByTestId('matchday-empty-jump').click();
  await expect(page.getByTestId('matchday-upcoming-none')).toBeVisible();
  expect(upcoming.calls, 'inside its age even this answer is not bought twice').toBe(1);

  await page.clock.fastForward(10 * 60 * 1000);
  await page.getByTestId('matchday-empty-jump').click();

  await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_10_OCTOBER);
  await expect(page.getByTestId('matchday-upcoming-none')).toHaveCount(0);
  expect(upcoming.calls, 'a calendar read empty hours ago has to be read again').toBe(2);
});

// ------------------------------------------------------- the notice already on screen refreshes
/**
 * A kickoff arrives whether or not anybody is at the keyboard. A notice that reads only on mount
 * goes on naming a fixture that has been played as the next one there is, for as long as the
 * reader leaves the tab open — and coming back to a tab is exactly when a reader expects what is
 * on screen to be current. So that return is the trigger, and these tests hold it to both halves
 * of the bargain: it refreshes what has expired, and it costs nothing for what has not.
 */
test('a kickoff that passes while the reader is away is re-asked when they come back to the tab',
  async ({ page }) => {
    await openAt(page, START);
    await stubBackend(page, { day: d => emptyDayPayload(d) });
    const upcoming = await stubUpcomingInTurn(page, [KICKOFF_TWO_MINUTES_OUT, POSTPONED_TO_10_OCTOBER]);

    await openEmptyDay(page);
    const note = page.getByTestId('matchday-upcoming');
    await expect(note).toContainText(SAYS_TODAY);

    // The kickoff passes with nobody touching the page. Nothing polls, so the sentence is still
    // the old one and nothing has been spent finding that out.
    await page.clock.fastForward(3 * 60 * 1000);
    await expect(note).toContainText(SAYS_TODAY);
    expect(upcoming.calls, 'a page nobody is looking at must not ask anything').toBe(1);

    await comeBackToTheTab(page);

    await expect(note).toContainText(SAYS_10_OCTOBER);
    expect(upcoming.calls, 'one return is one request, not one per event in the pair').toBe(2);
  });

test('coming back to the tab asks nothing when the answer on screen is still good', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  const upcoming = await stubUpcomingInTurn(page, [RESUMES_9_OCTOBER, POSTPONED_TO_10_OCTOBER]);

  await openEmptyDay(page);
  await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_9_OCTOBER);

  // A minute away and back, five times over. The named kickoff is seventeen days out and the
  // answer is minutes old, so every one of those returns is served from what this tab already has.
  for (let i = 0; i < 5; i += 1) {
    await page.clock.fastForward(60 * 1000);
    await comeBackToTheTab(page);
  }

  await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_9_OCTOBER);
  expect(upcoming.calls, 'a reader who keeps coming back must not become a request generator')
    .toBe(1);

  // The listener was live throughout, which is what makes the count above evidence about the
  // answer still being good rather than about nothing listening: one more return, this time past
  // the age limit, and the same reader does get a new answer.
  await page.clock.fastForward(ANSWER_TTL_MS);
  await comeBackToTheTab(page);

  await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_10_OCTOBER);
  expect(upcoming.calls).toBe(2);
});

test('a tab that is not in front does no work when the events arrive', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  const upcoming = await stubUpcomingInTurn(page, [KICKOFF_TWO_MINUTES_OUT, POSTPONED_TO_10_OCTOBER]);

  await openEmptyDay(page);
  const note = page.getByTestId('matchday-upcoming');
  await expect(note).toContainText(SAYS_TODAY);

  // Expired: the kickoff has passed, so a VISIBLE tab would ask again here.
  await page.clock.fastForward(3 * 60 * 1000);

  await setTabVisibility(page, 'hidden');
  await comeBackToTheTab(page);
  await page.waitForTimeout(500);

  expect(upcoming.calls, 'a hidden tab must not spend a request').toBe(1);
  await expect(note).toContainText(SAYS_TODAY);

  // And the same events on a tab that IS in front do ask, which is what makes the count above
  // evidence about visibility rather than about a listener that was never attached.
  await setTabVisibility(page, 'visible');
  await comeBackToTheTab(page);

  await expect(note).toContainText(SAYS_10_OCTOBER);
  expect(upcoming.calls).toBe(2);
});

/* ==========================================================================================
 * A REFRESH THAT CANNOT ANSWER LEAVES THE READER WHERE THEY WERE
 *
 * The refresh above exists to improve what is on screen. The whole of it is only worth having if
 * it can never make what is on screen WORSE, and there is one way it can: by taking the sentence
 * the reader was in the middle of reading and putting nothing in its place.
 *
 * The scenario is ordinary. A reader is told football comes back on 9 October, leaves the tab for
 * the afternoon, and comes back to it. The answer has aged out, so the return asks — and that one
 * request meets a gateway having a bad second, or a backend whose calendar backoff is refusing to
 * spend. A note that never re-read itself would still be showing that date, because nothing would
 * have taken it away; a note that re-reads has to clear the same bar. Losing what we already knew
 * because we went looking for better is a worse outcome than a date a few hours old.
 *
 * This is the promise src/pages/MatchDetailPage.tsx already makes for the same trigger — "there
 * IS something on screen, and it stays. A failed re-read may not blank the fixture" — so this
 * note keeps it the same way, and only replaces the notice when there is a better one to show.
 *
 * EACH TEST PROVES BOTH HALVES. "The note did not change" passes just as well for a note that has
 * stopped refreshing altogether, which is the worse fault; so every test below ends by letting
 * the same reader come back once more to a working endpoint and asserting that the notice DOES
 * change then.
 * ========================================================================================== */
test('a refresh that fails leaves the notice the reader was reading on screen', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  const upcoming = await stubUpcomingInTurn(
    page, [RESUMES_9_OCTOBER, 'fails', POSTPONED_TO_10_OCTOBER]);

  await openEmptyDay(page);
  const note = page.getByTestId('matchday-upcoming');
  await expect(note).toContainText(SAYS_9_OCTOBER);

  // An afternoon away: the answer has aged out, so coming back asks — and the request fails.
  await page.clock.fastForward(ANSWER_TTL_MS + 60 * 1000);
  const failed = page.waitForResponse(r => r.url().includes('/matches/upcoming'));
  await comeBackToTheTab(page);
  await failed;
  // The failure is handled in a promise continuation; a blanked note would be on screen within a
  // commit or two of it, and this is long enough for that to have happened.
  await page.waitForTimeout(500);

  await expect(note, 'a refresh that could not answer must not erase the answer we had')
    .toContainText(SAYS_9_OCTOBER);
  expect(upcoming.calls).toBe(2);

  // And once it is worth asking again, the same reader coming back does get the new calendar.
  await page.clock.fastForward(FAILURE_TTL_MS + 60 * 1000);
  await comeBackToTheTab(page);

  await expect(note).toContainText(SAYS_10_OCTOBER);
  expect(upcoming.calls).toBe(3);
});

test('a refresh the backend refuses to spend on leaves the notice alone', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  // The backoff and the daily ceiling refuse in exactly this shape: HTTP 200, `known: false`.
  const upcoming = await stubUpcomingInTurn(
    page, [RESUMES_9_OCTOBER, COULD_NOT_FIND_OUT, POSTPONED_TO_10_OCTOBER]);

  await openEmptyDay(page);
  const note = page.getByTestId('matchday-upcoming');
  await expect(note).toContainText(SAYS_9_OCTOBER);

  await page.clock.fastForward(ANSWER_TTL_MS + 60 * 1000);
  const refused = page.waitForResponse(r => r.url().includes('/matches/upcoming'));
  await comeBackToTheTab(page);
  await refused;
  await page.waitForTimeout(500);

  await expect(note, 'being told nobody knows is not a reason to forget what we were told')
    .toContainText(SAYS_9_OCTOBER);
  // Specifically not this: "we could not find out" is the right sentence for a reader who has
  // nothing on screen, and a downgrade for one who is reading named fixtures.
  await expect(page.getByTestId('matchday-upcoming-unknown')).toHaveCount(0);
  expect(upcoming.calls).toBe(2);

  await page.clock.fastForward(FAILURE_TTL_MS + 60 * 1000);
  await comeBackToTheTab(page);

  await expect(note).toContainText(SAYS_10_OCTOBER);
  expect(upcoming.calls).toBe(3);
});

/**
 * The cost of a failure, which is the half a reader never sees.
 *
 * A session that remembers only ANSWERS remembers nothing at all for as long as it cannot get
 * one, and then every return goes to the network: a reader alt-tabbing between this tab and their
 * work all afternoon is one request per return, indefinitely, at exactly the moment the thing
 * being asked is already failing or already refusing to spend. So a failure is remembered for as
 * long as the calendar path behind it could not have answered differently, and no longer.
 */
test('a return that could not find out is not re-asked by the return after it', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  const upcoming = await stubUpcomingInTurn(
    page, [RESUMES_9_OCTOBER, 'fails', POSTPONED_TO_10_OCTOBER]);

  await openEmptyDay(page);
  const note = page.getByTestId('matchday-upcoming');
  await expect(note).toContainText(SAYS_9_OCTOBER);

  await page.clock.fastForward(ANSWER_TTL_MS + 60 * 1000);
  const failed = page.waitForResponse(r => r.url().includes('/matches/upcoming'));
  await comeBackToTheTab(page);
  await failed;
  expect(upcoming.calls).toBe(2);

  // Back to the work, back to the tab, four times in the next forty seconds. None of them can be
  // answered any differently from the one that just was not.
  for (let i = 0; i < 4; i += 1) {
    await page.clock.fastForward(10 * 1000);
    await comeBackToTheTab(page);
  }
  await page.waitForTimeout(500);

  expect(upcoming.calls, 'a failure must not turn every return into a request').toBe(2);
  await expect(note).toContainText(SAYS_9_OCTOBER);

  // The memory is of a bad minute and nothing longer: past it, the next return asks.
  await page.clock.fastForward(FAILURE_TTL_MS);
  await comeBackToTheTab(page);

  await expect(note).toContainText(SAYS_10_OCTOBER);
  expect(upcoming.calls).toBe(3);
});

// ------------------------------------------------------------- the reader's own switch is obeyed
/**
 * `liveUpdates` is the setting the saved-matches store and the followed-fixtures feed already
 * gate their polling on, and this note reads the same one rather than inventing a second switch
 * the reader would have to find and turn off twice.
 *
 * SIGNED IN BECAUSE THE SETTING IS PER ACCOUNT: `personalPreferencesStore` keys it by user id.
 * The pair of tests is what makes each half evidence — if the stubbed session failed to boot,
 * both would fall back to the default (on) and the "off" half would fail loudly rather than pass
 * for the wrong reason.
 */
async function openSignedInEmptyDay(page: Page, liveUpdates: boolean): Promise<void> {
  const user = await signIn(page);
  await seedStoredPreferences(page, user.user_id, liveUpdates);
  // Armed before the navigation, because the session boots during the load: the settings are
  // bound to the account only once `/auth/me` has answered, and a signed-in run that silently
  // failed to sign in would otherwise read the defaults and prove nothing.
  const session = page.waitForResponse(
    r => r.url().includes('/api/v1/auth/me') && r.status() === 200);
  await page.goto('/predictions/today');
  await session;
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('matchday-empty')).toBeVisible();
  // The binding happens in an effect, one commit after the account arrives.
  await page.waitForTimeout(500);
}

test('automatic updates switched off stops the note re-asking when the reader comes back',
  async ({ page }) => {
    await openAt(page, START);
    await stubBackend(page, { day: d => emptyDayPayload(d) });
    const upcoming = await stubUpcomingInTurn(page, [KICKOFF_TWO_MINUTES_OUT, POSTPONED_TO_10_OCTOBER]);

    await openSignedInEmptyDay(page, false);
    const note = page.getByTestId('matchday-upcoming');
    await expect(note).toContainText(SAYS_TODAY);

    await page.clock.fastForward(3 * 60 * 1000);
    await comeBackToTheTab(page);
    await page.waitForTimeout(500);

    expect(upcoming.calls, 'a reader who switched automatic updates off gets no automatic update')
      .toBe(1);
    await expect(note).toContainText(SAYS_TODAY);
  });

test('the same reader with automatic updates on does get the refresh', async ({ page }) => {
  await openAt(page, START);
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  const upcoming = await stubUpcomingInTurn(page, [KICKOFF_TWO_MINUTES_OUT, POSTPONED_TO_10_OCTOBER]);

  await openSignedInEmptyDay(page, true);
  const note = page.getByTestId('matchday-upcoming');
  await expect(note).toContainText(SAYS_TODAY);

  await page.clock.fastForward(3 * 60 * 1000);
  await comeBackToTheTab(page);

  await expect(note).toContainText(SAYS_10_OCTOBER);
  expect(upcoming.calls).toBe(2);
});

// --------------------------------------------------------- one gate, however many days are open
/**
 * The shared answer and the request in flight are what keep a walk through a break's worth of
 * empty days down to one request, and a refresh has to go through the same gate rather than
 * around it.
 *
 * WHAT "AT ONCE" CAN MEAN HERE. One route renders one matchday, so the way several empty days are
 * live at the same moment is a reader moving between them faster than the network answers — which
 * is what this drives, by holding the answer back while three days are opened. The other way one
 * return can cost several requests is the focus/visibilitychange pair, asserted above.
 */
test('empty days opened faster than the answer arrives share the one request', async ({ page }) => {
  await seedPreferences(page, 'en', 'Europe/Paris');
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  const counter = { calls: 0 };
  await page.route(UPCOMING, async (route: Route) => {
    counter.calls += 1;
    // Held open in the stub, in real time: the browser's clock is not installed here, because
    // what is being measured is what the application does while a request is genuinely pending.
    await new Promise(resolve => { setTimeout(resolve, 3_000); });
    return route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify(RESUMES_9_OCTOBER),
    });
  });

  await page.goto('/predictions/today');
  await expect(page.getByTestId('matchday-empty')).toBeVisible();
  await page.getByTestId('matchday-empty-jump').click();
  await expect(page.getByTestId('matchday-empty')).toBeVisible();
  await page.getByTestId('matchday-empty-jump').click();
  await expect(page.getByTestId('matchday-empty')).toBeVisible();

  await expect(page.getByTestId('matchday-upcoming')).toContainText(SAYS_9_OCTOBER);
  expect(counter.calls, 'three empty days opened before the answer landed cost one request')
    .toBe(1);
});
