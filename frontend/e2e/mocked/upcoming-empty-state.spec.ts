import { test, expect, Page, Route } from '@playwright/test';
import { stubBackend, emptyDayPayload, dayPayload } from '../support/api-stub';

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
 * The last one is also asserted not to stick: a day that could not find out does not stop the
 * next empty day from asking, because every one of those failures arrives as a perfectly
 * successful HTTP 200.
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
/** Answer each call with the next body in `bodies`, repeating the last one, and count the calls. */
async function stubUpcomingInTurn(page: Page, bodies: UpcomingBody[]): Promise<{ calls: number }> {
  const counter = { calls: 0 };
  await page.route(UPCOMING, (route: Route) => {
    const body = bodies[Math.min(counter.calls, bodies.length - 1)];
    counter.calls += 1;
    return route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify(body),
    });
  });
  return counter;
}

test('a day that could not find out does not stop the next empty day from asking', async ({ page }) => {
  await seedPreferences(page, 'en', 'Europe/Paris');
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  // Every calendar failure reaches the browser as a successful response saying `known: false`,
  // so this is what a blip looks like from here: 200, and no answer in it.
  const upcoming = await stubUpcomingInTurn(page, [
    { known: false, next_kickoff: null, fixtures: [], unanswered: [] },
    RESUMES_9_OCTOBER,
  ]);

  await openEmptyDay(page);
  await expect(page.getByTestId('matchday-upcoming-unknown')).toBeVisible();

  await page.getByTestId('matchday-empty-jump').click();

  await expect(page.getByTestId('matchday-upcoming'))
    .toContainText('These competitions play again on Friday, 9 October 2026.');
  expect(upcoming.calls, 'the blip belongs to the day it happened on, not to the session')
    .toBe(2);
});

test('an answer already given is not paid for again on the next empty day', async ({ page }) => {
  await seedPreferences(page, 'en', 'Europe/Paris');
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
