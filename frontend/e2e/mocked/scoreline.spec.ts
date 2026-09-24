import { test, expect, Page } from '@playwright/test';
import { stubBackend, dayPayload, fixtureAt, localDay } from '../support/api-stub';
import type { ApiMatch, Json } from '../support/api-stub';

/**
 * A knockout tie, shown as the result it actually had.
 *
 * The backend publishes `GET /api/v1/performance/rules`, and its PERIODS_RULE tells readers that
 * the score after extra time and the penalty shoot-out "are published with the match and shown
 * beside its score", and that neither is ever folded into the score a market settles on. That is
 * a promise the product makes to the people using it, so it is held to here rather than left to
 * the serialiser's unit tests.
 *
 * The two things that go wrong are opposite mistakes and both are tested:
 *
 *  - SHOWING TOO LITTLE. "0-0" for a tie won 4-3 on penalties is the draw every market settles on
 *    and is half the result: the reader is not told who went through.
 *  - SHOWING TOO MUCH. "4-3" as the scoreline is the other half thrown away, and it would make
 *    every forecast of a draw look wrong when settlement scores it as one.
 *
 * Every /api/v1 route is stubbed, so nothing here reaches a provider or spends an allowance. The
 * periods are supplied exactly as `serialize_match` serves them — absent periods as null, never as
 * zero — so a payload the backend cannot produce cannot make these tests pass.
 */

const LANGUAGE_KEY = 'sp.language.v1';

/** Put the reader's stored language in place before the application's own scripts run. */
async function seedLanguage(page: Page, language: 'en' | 'fr'): Promise<void> {
  await page.addInitScript(
    ([key, value]) => { window.localStorage.setItem(key, value); },
    [LANGUAGE_KEY, language] as const,
  );
}

const bodyText = (page: Page): Promise<string> =>
  page.evaluate(() => document.body.innerText.replace(/\s+/g, ' '));

/** A tie that finished 0-0 after 90 minutes and was won 4-3 on penalties. */
function penaltiesTie(isoDate: string): ApiMatch {
  const match = fixtureAt(`${isoDate}T12:00:00Z`, 'Switzerland', 'Colombia', 'tie-on-penalties');
  match.status = 'finished';
  match.score = {
    home: 0, away: 0, ht_home: 0, ht_away: 0, ft_home: 0, ft_away: 0,
    et_home: null, et_away: null, ps_home: 4, ps_away: 3,
  } as Json;
  return match;
}

/** A tie that was 1-1 after 90 minutes and 2-1 after extra time, with no shoot-out. */
function extraTimeTie(isoDate: string): ApiMatch {
  const match = fixtureAt(`${isoDate}T14:00:00Z`, 'Portugal', 'Uruguay', 'tie-in-extra-time');
  match.status = 'finished';
  match.score = {
    home: 2, away: 1, ht_home: 0, ht_away: 1, ft_home: 1, ft_away: 1,
    et_home: 2, et_away: 1, ps_home: null, ps_away: null,
  } as Json;
  return match;
}

/** An ordinary league match: one scoreline, and no period line to explain it. */
function ordinaryMatch(isoDate: string): ApiMatch {
  const match = fixtureAt(`${isoDate}T16:00:00Z`, 'Arsenal', 'Everton', 'ordinary-ninety-minutes');
  match.status = 'finished';
  match.score = {
    home: 2, away: 0, ht_home: 1, ht_away: 0, ft_home: 2, ft_away: 0,
    et_home: null, et_away: null, ps_home: null, ps_away: null,
  } as Json;
  return match;
}

const ties = (isoDate: string): ApiMatch[] =>
  [penaltiesTie(isoDate), extraTimeTie(isoDate), ordinaryMatch(isoDate)];

async function openDetail(page: Page, match: ApiMatch): Promise<void> {
  const day = localDay();
  await stubBackend(page, {
    day: d => dayPayload(d, ties(d)),
    matchById: id => ties(day).find(m => m.id === id) ?? null,
  });
  await page.goto(`/match/${match.id}`);
  await page.waitForLoadState('networkidle');
}

// ------------------------------------------------------------------ the shoot-out is shown
test('a tie won on penalties names the shoot-out beside the score, not as the score', async ({ page }) => {
  await openDetail(page, penaltiesTie(localDay()));

  const scoreline = page.getByTestId('match-scoreline');
  await expect(scoreline).toContainText('0 - 0');
  await expect(scoreline.getByTestId('match-score-period')).toContainText('4–3 on penalties');

  // The shoot-out is never the scoreline: a reader must not be able to read "4-3" as the result
  // of the football, and settlement scores this tie as the draw it was.
  const text = await bodyText(page);
  expect(text).not.toMatch(/\b4\s*-\s*3\b/);
});

test('a tie decided in extra time publishes the 90-minute score the markets settle on', async ({ page }) => {
  await openDetail(page, extraTimeTie(localDay()));

  const scoreline = page.getByTestId('match-scoreline');
  await expect(scoreline).toContainText('2 - 1');
  const periods = scoreline.getByTestId('match-score-period');
  await expect(periods.first()).toContainText('1–1 after 90 minutes');
  await expect(scoreline).toContainText('After extra time');
});

test('an ordinary match gets no period line at all', async ({ page }) => {
  await openDetail(page, ordinaryMatch(localDay()));

  await expect(page.getByTestId('match-scoreline')).toContainText('2 - 0');
  // Nothing to explain: the score of the football played and the 90-minute score are one number,
  // and a second line repeating it would be noise on every league fixture there is.
  await expect(page.getByTestId('match-score-period')).toHaveCount(0);
});

// ------------------------------------------------------------------ an absent period is not a zero
test('a period the source never supplied is shown as nothing, never as 0-0', async ({ page }) => {
  const day = localDay();
  const unknown = penaltiesTie(day);
  // The ordinary state of every result stored before the periods were carried: a score, and no
  // period breakdown at all.
  unknown.score = { home: 1, away: 1, ht_home: null, ht_away: null } as Json;

  await stubBackend(page, {
    day: d => dayPayload(d, [unknown]),
    matchById: () => unknown,
  });
  await page.goto(`/match/${unknown.id}`);
  await page.waitForLoadState('networkidle');

  await expect(page.getByTestId('match-scoreline')).toContainText('1 - 1');
  await expect(page.getByTestId('match-score-period')).toHaveCount(0);
  expect(await bodyText(page)).not.toMatch(/on penalties|after 90 minutes|After extra time/i);
});

// ------------------------------------------------------------------ both languages
test('the shoot-out is named in French for a reader who chose French', async ({ page }) => {
  await seedLanguage(page, 'fr');
  await openDetail(page, penaltiesTie(localDay()));

  const scoreline = page.getByTestId('match-scoreline');
  await expect(scoreline.getByTestId('match-score-period')).toContainText('4–3 aux tirs au but');
  // The English catalogue's wording for the same fact must not survive into a French page.
  expect(await bodyText(page)).not.toMatch(/on penalties/i);
});

test('the extra-time lines are in French too', async ({ page }) => {
  await seedLanguage(page, 'fr');
  await openDetail(page, extraTimeTie(localDay()));

  const scoreline = page.getByTestId('match-scoreline');
  await expect(scoreline).toContainText('1–1 après 90 minutes');
  await expect(scoreline).toContainText('Après prolongation');
  expect(await bodyText(page)).not.toMatch(/after 90 minutes|After extra time/i);
});

// ------------------------------------------------------------------ the day's list, not only the detail
test('the fixture list carries the shoot-out too, in the short form the row has space for', async ({ page }) => {
  const day = localDay();
  await stubBackend(page, { day: d => dayPayload(d, ties(d)) });
  await page.goto('/matches');
  await page.waitForLoadState('networkidle');

  const row = page.locator(`[data-match-id="${penaltiesTie(day).id}"]`);
  await expect(row).toBeVisible();
  await expect(row.getByTestId('fixture-row-periods')).toContainText('4–3 pens');

  // The ordinary match on the same day gets no line, so the note is a fact about the tie and not
  // something every finished row now carries.
  const ordinary = page.locator(`[data-match-id="${ordinaryMatch(day).id}"]`);
  await expect(ordinary.getByTestId('fixture-row-periods')).toHaveCount(0);
});
