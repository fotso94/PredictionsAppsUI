import { expect, test, Page, Request, Route } from '@playwright/test';
import en from '../../src/i18n/messages/en';
import fr from '../../src/i18n/messages/fr';
import { compileMessage, renderMessage } from '../../src/i18n/format';
import { ApiMatch, Json, baseMatches, emptyDayPayload, fixtureAt, matchDetail, stubBackend } from '../support/api-stub';
import { regularUser, signIn } from '../support/auth';
import { LIVE_API_MESSAGE, fenceLiveApi } from '../support/live-stack';

/**
 * AN EXPERT'S EARLIER VERSIONS, THEIR AUTHOR, AND A PREDICTION PUBLISHED TOO LATE TO BE SCORED.
 *
 * Three defects on the public match page and the expert screens (QA finding 6 and its map):
 *
 *  1. "Earlier published versions" rendered four numbers of each earlier version — home, draw,
 *     away and the 1X2 conviction — so the both-teams-to-score and total-goals figures an expert
 *     had published, and later changed, were nowhere on the page. The "what changed" line printed
 *     the backend's audit string verbatim: `btts_yes_prob 0.6 -> 0.4`, column names and Python
 *     reprs, in English on a French page.
 *  2. The expert card's footer read `Expert · expert_manual`: the raw source enum, and no name.
 *     The backend now serves `author {id, username}`; the card names the expert by that username
 *     and never by anything else.
 *  3. Settlement never scores a prediction published at or after kick-off, and nothing on any
 *     screen said so. The backend now serves `published_after_kickoff`; readers get a chip, and an
 *     expert choosing, writing or editing on a fixture that has kicked off is told before
 *     publishing. The posting policy is NOT changed: such fixtures are still offered, and a
 *     publish on one still goes through.
 *
 * WHAT IS ASSERTED. The numbers on screen against the numbers in the stub payload (formatted in
 * the page by the browser's own `Intl`, never by Node's, whose CLDR differs), the sentences against
 * the catalogue rendered by src/i18n's own formatter, the absence of every raw field name, and the
 * requests the composer sends. Every payload is on the backend's 0-1 scale.
 *
 * ABSENCE WINDOWS. A "this is not on the page" check runs after the element it would sit beside is
 * visible and the network is idle; there is no timer to wait out, because nothing here renders late.
 *
 * COST. Every /api/v1 route is stubbed; nothing reaches a backend. A guard (support/live-stack.ts)
 * aborts, and fails the test on, any request to the live API (:8000) that no stub answered. It does
 * not fence the frontend origin, which is the page under test on the default configuration.
 */

type Language = 'en' | 'fr';

const LANGUAGE_KEY = 'sp.language.v1';
const ZONE_KEY = 'sp.timeZone.v1';
/** A zone the device (America/New_York, playwright.config.ts) is not on. */
const DOUALA = 'Africa/Douala';
const LOCALE: Record<Language, string> = { en: 'en-GB', fr: 'fr-FR' };

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;
const isoIn = (ms: number): string => new Date(Date.now() + ms).toISOString().replace(/\.\d{3}Z$/, 'Z');

let liveStackHits: string[] = [];

/** Seed the reader's choices before the app boots, and fence off the live API. */
async function prepare(page: Page, language: Language): Promise<void> {
  liveStackHits = [];
  await page.addInitScript(
    ([languageKey, zoneKey, chosen, zone]) => {
      window.localStorage.setItem(languageKey, chosen);
      window.localStorage.setItem(zoneKey, zone);
    },
    [LANGUAGE_KEY, ZONE_KEY, language, DOUALA] as const,
  );
  await fenceLiveApi(page, liveStackHits);
}

test.afterEach(() => {
  expect(liveStackHits, LIVE_API_MESSAGE).toEqual([]);
});

/**
 * One catalogue sentence, rendered the way src/i18n renders it. Throws a readable error for a key
 * the catalogue does not have, so a run against a build without the key fails on that, plainly.
 */
function say(language: Language, key: string, params: Record<string, string | number> = {}): string {
  const catalogue = (language === 'en' ? en : fr) as unknown as Record<string, string>;
  const source = catalogue[key];
  if (typeof source !== 'string') throw new Error(`the ${language} catalogue has no key "${key}"`);
  return renderMessage(compileMessage(source), LOCALE[language], params);
}

const normalise = (value: string): string => value.replace(/\s+/g, ' ').trim();

/** A 0-1 probability as the page prints it (whole percent), formatted by the page's own Intl. */
const percentIn = (page: Page, language: Language, unit: number): Promise<string> =>
  page.evaluate(([locale, value]) => new Intl.NumberFormat(locale as string, {
    style: 'percent', minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format((value as number * 100) / 100), [LOCALE[language], unit] as const);

/** A goal line as the page prints it: 2.5 in English, 2,5 in French. */
const numberIn = (page: Page, language: Language, value: number): Promise<string> =>
  page.evaluate(([locale, v]) => new Intl.NumberFormat(locale as string).format(v as number), [LOCALE[language], value] as const);

const noSidewaysScroll = (page: Page): Promise<boolean> =>
  page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);

/* ======================================================================== the payloads */

const FIXTURE_ID = baseMatches()[0].id;
const PUBLISHED_AT = '2026-09-17T08:00:00Z';
const REPLACED_AT = '2026-09-17T09:30:00Z';

const AUTHOR_A = { id: '00000000-0000-4000-8000-0000000000a1', username: 'qa_expert' };
const AUTHOR_B = { id: '00000000-0000-4000-8000-0000000000b2', username: 'qa_second_expert' };

/** The twelve numeric fields every revision snapshot carries (REVISION_VALUE_FIELDS). */
type Field =
  | 'home_win_prob' | 'draw_prob' | 'away_win_prob' | 'confidence_score'
  | 'btts_yes_prob' | 'btts_no_prob' | 'btts_confidence'
  | 'total_goals_over_25_prob' | 'total_goals_under_25_prob'
  | 'total_goals_over_35_prob' | 'total_goals_under_35_prob' | 'total_goals_confidence';

/**
 * The version an expert first published: BTTS 60/40, over/under 2.5 at 55/45, 3.5 left out
 * entirely, a 1X2 conviction of ZERO (a claim, not an absence) and no BTTS conviction (an absence,
 * not a zero).
 */
const EARLIER: Record<Field, number | null> = {
  home_win_prob: 0.5, draw_prob: 0.3, away_win_prob: 0.2, confidence_score: 0,
  btts_yes_prob: 0.6, btts_no_prob: 0.4, btts_confidence: null,
  total_goals_over_25_prob: 0.55, total_goals_under_25_prob: 0.45,
  total_goals_over_35_prob: null, total_goals_under_35_prob: null,
  total_goals_confidence: 0.65,
};

/** The same view after the one edit, which changed BTTS and nothing else. */
const CURRENT: Record<Field, number | null> = { ...EARLIER, btts_yes_prob: 0.4, btts_no_prob: 0.6 };

/** The audit text the backend still serves beside `changes`. It must never reach the page. */
const RAW_SUMMARY = 'btts_yes_prob 0.6 -> 0.4; btts_no_prob 0.4 -> 0.6';

function expertPrediction(over: Json = {}): Json {
  return {
    id: 'qa-pred-a',
    source: 'expert_manual',
    priority_level: 2,
    status: 'published',
    ...CURRENT,
    reasoning: 'QA current reasoning for the revision history test.',
    published_at: PUBLISHED_AT,
    created_by: AUTHOR_A.id,
    published_after_kickoff: false,
    author: AUTHOR_A,
    ...over,
  };
}

function revision(over: Json = {}, values: Json = {}): Json {
  const snapshot = {
    ...EARLIER,
    reasoning: 'QA original reasoning for the revision history test.',
    key_factors: null,
    status: 'PUBLISHED',
    published_at: PUBLISHED_AT,
    created_at: PUBLISHED_AT,
    updated_at: PUBLISHED_AT,
    ...values,
  };
  return {
    id: 'qa-rev-a1',
    prediction_id: 'qa-pred-a',
    revision: 1,
    replaced_at: REPLACED_AT,
    edited_by: AUTHOR_A.id,
    changes_summary: RAW_SUMMARY,
    changes: [
      { field: 'btts_yes_prob', from: 0.6, to: 0.4 },
      { field: 'btts_no_prob', from: 0.4, to: 0.6 },
    ],
    edited_after_kickoff: false,
    published_at: PUBLISHED_AT,
    values: snapshot,
    ...over,
  };
}

/**
 * The detail payload of the first captured fixture with these experts and revisions on it.
 *
 * The brief's expert entry is switched to present, as reader-localisation.spec.ts does: the
 * evidence panel reads presence from the BRIEF, and a brief saying "no expert" beside an expert
 * card would be a page that contradicts itself.
 */
function detailWith(experts: Json[], revisions: Json[]): ApiMatch {
  const found = matchDetail(FIXTURE_ID);
  if (!found) throw new Error('the captured fixture is missing');
  const brief = JSON.parse(JSON.stringify(found.brief)) as { known: { sources: Array<Record<string, unknown>> } };
  const source = brief.known.sources.find(entry => entry.source === 'expert');
  if (source) {
    source.present = true;
    source.published_at = PUBLISHED_AT;
  }
  return {
    ...found,
    brief,
    expert_prediction: experts[0] ?? null,
    expert_predictions: experts,
    expert_prediction_revisions: revisions,
  } as unknown as ApiMatch;
}

async function openMatch(page: Page, language: Language, payload: () => ApiMatch): Promise<void> {
  await prepare(page, language);
  await stubBackend(page, { matchById: id => (id === FIXTURE_ID ? payload() : null) });
  await page.goto(`/match/${FIXTURE_ID}`);
  await expect(page.getByTestId('expert-predictions')).toBeVisible();
  await page.waitForLoadState('networkidle');
}

const revisionItem = (page: Page) => page.getByTestId('expert-revision').first();
const cell = (page: Page, field: Field) => revisionItem(page).locator(`[data-testid="revision-value"][data-field="${field}"]`);
const market = (page: Page, id: string) => revisionItem(page).locator(`[data-testid="revision-market"][data-market="${id}"]`);

/* ================================================ every market an earlier version carried */

for (const language of ['en', 'fr'] as const) {
  test(`an earlier version shows every market it carried, with zero and "not set" kept apart, in ${language}`, async ({ page }) => {
    await openMatch(page, language, () => detailWith([expertPrediction()], [revision()]));

    // The figures first, by value, so the old four-cell rendering fails on what a reader misses.
    const shown = normalise(await revisionItem(page).innerText());
    for (const field of ['btts_yes_prob', 'btts_no_prob', 'total_goals_over_25_prob', 'total_goals_under_25_prob'] as const) {
      const expected = await percentIn(page, language, EARLIER[field] as number);
      expect(shown, `the earlier ${field} (${EARLIER[field]}) is not on the earlier version`).toContain(normalise(expected));
    }

    // Each published number in its own labelled cell, read back against the payload it came from.
    for (const field of Object.keys(EARLIER) as Field[]) {
      const value = EARLIER[field];
      if (value === null) continue;
      if (field.startsWith('total_goals_') && field.includes('_35_')) continue;
      await expect(cell(page, field), `${field} has no cell of its own`).toHaveCount(1);
      await expect(cell(page, field)).toContainText(await percentIn(page, language, value));
    }

    // The labels are the reader's words for each market and side, not column names.
    const line25 = await numberIn(page, language, 2.5);
    await expect(market(page, 'btts')).toContainText(say(language, 'market.btts'));
    await expect(cell(page, 'btts_yes_prob')).toContainText(say(language, 'selections.outcome.yes'));
    await expect(cell(page, 'btts_no_prob')).toContainText(say(language, 'selections.outcome.no'));
    await expect(market(page, 'ou25')).toContainText(say(language, 'market.overUnder25'));
    await expect(cell(page, 'total_goals_over_25_prob')).toContainText(say(language, 'selections.outcome.over', { line: line25 }));
    await expect(cell(page, 'total_goals_under_25_prob')).toContainText(say(language, 'selections.outcome.under', { line: line25 }));

    // A conviction of zero is a claim and reads as 0 %; no BTTS conviction is "not set".
    const zero = await percentIn(page, language, 0);
    const notSet = say(language, 'probability.notSet');
    expect(normalise(await cell(page, 'confidence_score').innerText())).toContain(normalise(zero));
    expect(normalise(await cell(page, 'confidence_score').innerText()), 'a stated zero read as "not set"').not.toContain(notSet);
    await expect(cell(page, 'btts_confidence')).toContainText(notSet);
    await expect(cell(page, 'btts_confidence')).toContainText(say(language, 'reader.revisions.conviction'));

    // Both halves of 3.5 null: the market was left out, said once, and never as two zeros.
    await expect(market(page, 'ou35')).toContainText(say(language, 'market.overUnder35'));
    await expect(market(page, 'ou35')).toContainText(say(language, 'missing.marketNotSupplied'));
    await expect(cell(page, 'total_goals_over_35_prob')).toHaveCount(0);
    await expect(cell(page, 'total_goals_under_35_prob')).toHaveCount(0);

    // The total-goals conviction the version carried.
    await expect(cell(page, 'total_goals_confidence')).toContainText(await percentIn(page, language, 0.65));

    // The earlier reasoning is still there, as published.
    await expect(revisionItem(page)).toContainText('QA original reasoning for the revision history test.');

    expect(await noSidewaysScroll(page), 'the history pushed the page sideways').toBe(true);
  });

  test(`what changed is a sentence in ${language}, never the backend's field names`, async ({ page }) => {
    await openMatch(page, language, () => detailWith([expertPrediction()], [revision()]));

    const panel = normalise(await page.getByTestId('expert-revisions').innerText());
    expect(panel, 'the raw audit string reached the page').not.toContain(RAW_SUMMARY);
    expect(panel, 'a column name or a Python repr reached the page').not.toMatch(/btts_yes_prob|_prob\b|->|\bNone\b/);

    const p60 = await percentIn(page, language, 0.6);
    const p40 = await percentIn(page, language, 0.4);
    const field = (side: string) => say(language, 'reader.revisions.fieldLabel', {
      market: say(language, 'market.btts'),
      side: say(language, side),
    });
    const changes = page.getByTestId('revision-change');
    // Exactly the two BTTS halves: the edit changed nothing else, so nothing else is reported.
    await expect(changes).toHaveCount(2);
    await expect(changes.nth(0)).toHaveText(say(language, 'reader.revisions.change.value', {
      field: field('selections.outcome.yes'), from: p60, to: p40,
    }));
    await expect(changes.nth(1)).toHaveText(say(language, 'reader.revisions.change.value', {
      field: field('selections.outcome.no'), from: p40, to: p60,
    }));
  });

  test(`the card names the expert by username, never by email or the source enum, in ${language}`, async ({ page }) => {
    await openMatch(page, language, () => detailWith([expertPrediction()], [revision()]));

    const body = normalise(await page.locator('body').innerText());
    expect(body, 'the raw source enum is on the page').not.toContain('expert_manual');

    const byline = page.getByTestId('expert-byline');
    await expect(byline).toHaveCount(1);
    await expect(byline).toContainText(say(language, 'reader.expert.byline', { name: AUTHOR_A.username }));
    expect(await byline.innerText(), 'the byline carries something shaped like an email').not.toContain('@');

    // The history is headed with the same author.
    await expect(page.getByTestId('expert-revision-group')).toHaveCount(1);
    await expect(page.getByTestId('expert-revision-group').first())
      .toContainText(say(language, 'reader.revisions.byAuthor', { name: AUTHOR_A.username }));
  });

  test(`the late-publication chip appears only when the backend says so, in ${language}`, async ({ page }) => {
    let late: boolean | null = true;
    await openMatch(page, language, () => detailWith([expertPrediction({ published_after_kickoff: late })], [revision()]));

    const chip = page.getByTestId('expert-late-publication');
    await expect(chip).toHaveCount(1);
    await expect(chip).toContainText(say(language, 'reader.expert.publishedAfterKickoff'));
    await expect(chip).toContainText(say(language, 'reader.expert.publishedAfterKickoffDetail'));

    for (const value of [false, null] as const) {
      late = value;
      await page.reload();
      await expect(page.getByTestId('expert-byline')).toBeVisible();
      await page.waitForLoadState('networkidle');
      await expect(chip, `published_after_kickoff=${value} still showed the chip`).toHaveCount(0);
      expect(normalise(await page.locator('body').innerText()))
        .not.toContain(normalise(say(language, 'reader.expert.publishedAfterKickoff')));
    }
  });

  /*
   * Review finding #0/#6/#18. Published before kick-off, unpublished before it, published again
   * after it: the prematch withdrawal is frozen, so settlement does not score it, yet it is served
   * with its ORIGINAL pre-kick-off `published_at` and `published_after_kickoff: false`. The backend
   * now says so in `withdrawn_before_kickoff`; the card must say "not scored", in words of its own
   * — the late chip's "published at or after kick-off" would be false of a row the byline dates
   * before kick-off.
   */
  test(`a prediction withdrawn before kick-off and published again after it says it is not scored, in ${language}`, async ({ page }) => {
    let flags: Json = { published_after_kickoff: false, withdrawn_before_kickoff: true };
    await openMatch(page, language, () => detailWith([expertPrediction(flags)], [revision()]));

    const chip = page.getByTestId('expert-withdrawn-before-kickoff');
    await expect(chip, 'a prediction settlement leaves out is shown as an ordinary prematch one').toHaveCount(1);
    await expect(chip).toContainText(say(language, 'reader.expert.withdrawnBeforeKickoff'));
    await expect(chip).toContainText(say(language, 'reader.expert.withdrawnBeforeKickoffDetail'));
    // Not the late chip: its sentence ("published at or after kick-off") is false of this row.
    await expect(page.getByTestId('expert-late-publication')).toHaveCount(0);
    // The byline still carries the first publication time, which the detail sentence accounts for.
    await expect(page.getByTestId('expert-byline')).toContainText(say(language, 'reader.expert.byline', { name: AUTHOR_A.username }));

    // False (it stood), null (kick-off unknown) and absent (a backend older than the field): no chip.
    for (const next of [
      { published_after_kickoff: false, withdrawn_before_kickoff: false },
      { published_after_kickoff: false, withdrawn_before_kickoff: null },
      { published_after_kickoff: false },
    ] as Json[]) {
      flags = next;
      await page.reload();
      await expect(page.getByTestId('expert-byline')).toBeVisible();
      await page.waitForLoadState('networkidle');
      await expect(chip, `${JSON.stringify(next)} still showed the chip`).toHaveCount(0);
      expect(normalise(await page.locator('body').innerText()))
        .not.toContain(normalise(say(language, 'reader.expert.withdrawnBeforeKickoff')));
    }

    // Late AND withdrawn cannot both be true of one row; if a payload ever says so, one chip, the late one.
    flags = { published_after_kickoff: true, withdrawn_before_kickoff: true };
    await page.reload();
    await expect(page.getByTestId('expert-byline')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('expert-late-publication')).toHaveCount(1);
    await expect(chip).toHaveCount(0);
  });
}

/* ============================================================= grouping, and the edge states */

test('revisions are grouped per prediction, each under its own author', async ({ page }) => {
  const second = expertPrediction({ id: 'qa-pred-b', priority_level: 1, created_by: AUTHOR_B.id, author: AUTHOR_B });
  const revisions = [
    revision({ id: 'qa-rev-b1', prediction_id: 'qa-pred-b', edited_by: AUTHOR_B.id }),
    revision(),
    revision({ id: 'qa-rev-b2', prediction_id: 'qa-pred-b', revision: 2, edited_by: AUTHOR_B.id }),
  ];
  await openMatch(page, 'en', () => detailWith([expertPrediction(), second], revisions));

  const groups = page.getByTestId('expert-revision-group');
  await expect(groups).toHaveCount(2);
  const first = groups.nth(0);
  const other = groups.nth(1);
  await expect(first).toHaveAttribute('data-prediction-id', 'qa-pred-a');
  await expect(first).toContainText(say('en', 'reader.revisions.byAuthor', { name: AUTHOR_A.username }));
  await expect(first.getByTestId('expert-revision')).toHaveCount(1);
  await expect(other).toHaveAttribute('data-prediction-id', 'qa-pred-b');
  await expect(other).toContainText(say('en', 'reader.revisions.byAuthor', { name: AUTHOR_B.username }));
  await expect(other.getByTestId('expert-revision')).toHaveCount(2);
  // Numbered within their own prediction, oldest first: no "Version 1" belongs to two experts.
  await expect(other.getByTestId('expert-revision').nth(0)).toHaveAttribute('data-revision', '1');
  await expect(other.getByTestId('expert-revision').nth(1)).toHaveAttribute('data-revision', '2');
  // And each group counts its own corrections.
  expect(normalise(await first.innerText())).toContain('This view was updated once');
  expect(normalise(await other.innerText())).toContain('This view was updated 2 times');
  // Two bylines, one per expert.
  await expect(page.getByTestId('expert-byline')).toHaveCount(2);
  await expect(page.getByTestId('expert-byline').nth(1)).toContainText(say('en', 'reader.expert.byline', { name: AUTHOR_B.username }));
});

test('an author with no public name, or a name shaped like an email, is shown as the generic Expert label', async ({ page }) => {
  let author: Json | null = null;
  await openMatch(page, 'en', () => detailWith([expertPrediction({ author })], [revision()]));

  expect(normalise(await page.getByTestId('expert-predictions').innerText()), 'the raw source enum stands in for a name')
    .not.toContain('expert_manual');
  const byline = page.getByTestId('expert-byline');
  await expect(byline).toHaveCount(1);
  expect(normalise(await byline.innerText())).toMatch(new RegExp(`^${say('en', 'source.expert')}\\b`));
  await expect(byline).not.toContainText('expert_manual');
  await expect(page.getByTestId('expert-revision-group').first()).toContainText(say('en', 'reader.revisions.byUnnamed'));

  author = { id: AUTHOR_A.id, username: 'someone@example.test' };
  await page.reload();
  await expect(byline).toBeVisible();
  expect(normalise(await byline.innerText())).toMatch(new RegExp(`^${say('en', 'source.expert')}\\b`));
  expect(normalise(await page.locator('body').innerText()), 'an email-shaped name reached the page').not.toContain('someone@example.test');
});

test('a version recorded before a market existed says so, and no structured changes means no change line', async ({ page }) => {
  // An older snapshot: no BTTS keys and no total-goals keys at all, and a row without `changes`.
  const older = revision({ changes: null }, {});
  const values = older.values as Record<string, unknown>;
  for (const key of ['btts_yes_prob', 'btts_no_prob', 'btts_confidence', 'total_goals_over_25_prob', 'total_goals_under_25_prob',
    'total_goals_over_35_prob', 'total_goals_under_35_prob', 'total_goals_confidence']) delete values[key];
  await openMatch(page, 'fr', () => detailWith([expertPrediction()], [older]));

  // Observable first: the audit text is not shown, and the markets the snapshot lacks are still
  // named, as markets this version did not record.
  expect(normalise(await page.getByTestId('expert-revisions').innerText()), 'the raw audit string reached the page')
    .not.toContain(RAW_SUMMARY);
  await expect(market(page, 'btts'), 'a market the snapshot lacks is not named at all').toHaveCount(1);
  await expect(market(page, 'btts')).toHaveAttribute('data-state', 'not-recorded');
  await expect(market(page, 'btts')).toContainText(say('fr', 'reader.revisions.notRecorded'));
  await expect(market(page, 'ou25')).toContainText(say('fr', 'reader.revisions.notRecorded'));
  await expect(market(page, 'btts'), 'an absent key was reported as a market left out')
    .not.toContainText(say('fr', 'missing.marketNotSupplied'));
  // 1X2 was recorded, so it is still shown.
  await expect(cell(page, 'home_win_prob')).toContainText(await percentIn(page, 'fr', 0.5));

  await expect(page.getByTestId('revision-change')).toHaveCount(0);
});

test('a withdrawn figure, a new one, a change inside one whole percent, and rewritten text each say what happened', async ({ page }) => {
  const changes = [
    { field: 'confidence_score', from: 0, to: null },
    { field: 'total_goals_over_35_prob', from: null, to: 0.3 },
    { field: 'total_goals_over_25_prob', from: 0.551, to: 0.554 },
    { field: 'reasoning' },
    { field: 'a_field_this_build_does_not_know', from: 0.1, to: 0.2 },
  ];
  await openMatch(page, 'en', () => detailWith([expertPrediction()], [revision({ changes })]));

  const lines = page.getByTestId('revision-change');
  const label = (market: string, side: string, params: Record<string, string> = {}) =>
    say('en', 'reader.revisions.fieldLabel', { market: say('en', market), side: say('en', side, params) });
  await expect(lines).toHaveCount(4);
  await expect(lines.nth(0)).toHaveText(say('en', 'reader.revisions.change.withdrawn', {
    field: label('market.matchResult', 'reader.revisions.conviction'), from: await percentIn(page, 'en', 0),
  }));
  await expect(lines.nth(1)).toHaveText(say('en', 'reader.revisions.change.set', {
    field: label('market.overUnder35', 'selections.outcome.over', { line: await numberIn(page, 'en', 3.5) }),
    to: await percentIn(page, 'en', 0.3),
  }));
  // 55.1% and 55.4% are both "55%" at whole percent; the line keeps the decimal that moved.
  await expect(lines.nth(2)).toHaveText(say('en', 'reader.revisions.change.value', {
    field: label('market.overUnder25', 'selections.outcome.over', { line: await numberIn(page, 'en', 2.5) }),
    from: '55.1%', to: '55.4%',
  }));
  await expect(lines.nth(3)).toHaveText(say('en', 'reader.revisions.change.reasoning'));
  // A field this build cannot name is left out, never shown by its column name.
  await expect(page.getByTestId('expert-revisions')).not.toContainText('a_field_this_build_does_not_know');
});

/* ============================================ an expert, on a fixture that has kicked off */

/** Status still "scheduled", kickoff three hours ago: the case the old status-only filter admits. */
const KICKED = fixtureAt(isoIn(-3 * HOUR_MS), 'Fovu Baham', 'Bamboutos', 'fx-kicked');
const UPCOMING = fixtureAt(isoIn(3 * DAY_MS), 'Coton Sport', 'Union Douala', 'fx-upcoming');
const FIXTURES = [KICKED, UPCOMING];

interface ExpertWorld { created: Json[]; mine: Json[] }

async function openAsExpert(page: Page, language: Language, mine: Json[] = []): Promise<ExpertWorld> {
  const world: ExpertWorld = { created: [], mine };
  await prepare(page, language);
  await stubBackend(page, {
    // Both fixtures on whatever day the picker asks for: this is about the row, not the day window.
    day: iso => ({ ...emptyDayPayload(iso), matches: FIXTURES.map(match => ({ ...match })) }),
    matchById: id => FIXTURES.find(match => match.id === id) ?? null,
  });
  await page.route('**/api/v1/expert/**', async (route: Route, request: Request) => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/expert/, '');
    if (path === '/analytics/performance') {
      return json({
        expert_id: 'qa-expert', expert_name: 'QA Expert', total_predictions: 0, published_predictions: 0,
        pending_predictions: 0, archived_predictions: 0, not_published_predictions: 0, accuracy_rate: null,
        average_confidence: null, predictions_by_league: {}, recent_predictions: [], performance_trend: [],
      });
    }
    if (path === '/predictions/my-predictions') return json(world.mine);
    if (path === '/predictions/review-queue') return json([]);
    if (path === '/predictions/manual' && request.method() === 'POST') {
      const body = JSON.parse(request.postData() || '{}') as Json;
      world.created.push(body);
      return json({
        id: 'pred-new', source: 'EXPERT_MANUAL', priority_level: 1, status: 'PUBLISHED',
        created_by: 'qa-expert', created_at: new Date().toISOString(), published_at: new Date().toISOString(),
        superseded_by: null, match_details: null, user_details: null, key_factors: null, ...body,
      });
    }
    return json({});
  });
  await signIn(page, { user: regularUser({ role: 'expert', full_name: 'QA Expert' }) });
  return world;
}

const pickerRow = (page: Page, home: string) => page.locator('li').filter({ hasText: home });

for (const language of ['en', 'fr'] as const) {
  test(`both pickers mark a fixture that has kicked off, and still offer it, in ${language}`, async ({ page }) => {
    await openAsExpert(page, language);

    for (const path of ['/expert/match-selection', '/expert/predictions/create']) {
      await page.goto(path);
      await expect(pickerRow(page, 'Coton Sport')).toBeVisible();
      await page.waitForLoadState('networkidle');

      // Still offered: the policy is unchanged, the fixture is labelled rather than removed.
      await expect(pickerRow(page, 'Fovu Baham'), `${path} no longer offers the kicked-off fixture`).toHaveCount(1);
      await expect(pickerRow(page, 'Fovu Baham').getByTestId('picker-kicked-off'), `${path} does not mark the kicked-off fixture`)
        .toHaveCount(1);
      await expect(pickerRow(page, 'Coton Sport').getByTestId('picker-kicked-off'), `${path} marked an upcoming fixture`)
        .toHaveCount(0);
      const kickedOff = say(language, 'expert.picker.kickedOff');
      await expect(pickerRow(page, 'Fovu Baham'), `${path} does not say the fixture has kicked off`).toContainText(kickedOff);
      await expect(pickerRow(page, 'Coton Sport'), `${path} marked an upcoming fixture as kicked off`).not.toContainText(kickedOff);
      // A screen reader gets the row's accessible name only, so the badges are its description:
      // the forecast badge first, as drawn, then the warning. (The stub's forecast is current.)
      await expect(pickerRow(page, 'Fovu Baham').getByRole('button'))
        .toHaveAccessibleDescription(`${say(language, 'expert.picker.modelForecastHeld')} ${kickedOff}`);
      expect(await noSidewaysScroll(page), `${path} scrolls sideways`).toBe(true);
    }
  });

  test(`the composer and its preview warn on a fixture that has kicked off, in ${language}`, async ({ page }) => {
    await openAsExpert(page, language);

    await page.goto(`/expert/predictions/create?matchId=${KICKED.id}`);
    await expect(page.locator('#composer-home')).toBeVisible();
    await page.waitForLoadState('networkidle');

    const warning = page.getByTestId('composer-kickoff-warning');
    await expect(warning).toHaveCount(1);
    await expect(warning).toHaveAttribute('role', 'status');
    // The sentence names the kickoff time; the words either side of it are the catalogue's.
    const [before, after] = say(language, 'expert.compose.kickoffPassed', { time: '\u0000' }).split('\u0000');
    expect(normalise(await warning.innerText())).toContain(normalise(before));
    expect(normalise(await warning.innerText())).toContain(normalise(after));

    await page.getByRole('button', { name: say(language, 'expert.action.preview'), exact: true }).click();
    const previewWarning = page.getByTestId('preview-kickoff-warning');
    await expect(previewWarning).toHaveCount(1);
    await expect(previewWarning).toHaveAttribute('role', 'status');
    await expect(previewWarning).toContainText(say(language, 'expert.preview.kickedOff'));

    // An upcoming fixture gets neither.
    await page.goto(`/expert/predictions/create?matchId=${UPCOMING.id}`);
    await expect(page.locator('#composer-home')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('composer-kickoff-warning')).toHaveCount(0);
    await page.getByRole('button', { name: say(language, 'expert.action.preview'), exact: true }).click();
    await expect(page.getByLabel(say(language, 'expert.preview.regionLabel'))).toBeVisible();
    await expect(page.getByTestId('preview-kickoff-warning')).toHaveCount(0);
    expect(await noSidewaysScroll(page), 'the composer scrolls sideways').toBe(true);
  });

  test(`editing after kickoff says the version that stood at kickoff is what counts, in ${language}`, async ({ page }) => {
    const mine = (id: string, kickoff: string): Json => ({
      id, match_id: `match-${id}`, source: 'EXPERT_MANUAL', priority_level: 1,
      home_win_prob: 0.55, draw_prob: 0.25, away_win_prob: 0.2, confidence_score: 0.8,
      btts_yes_prob: null, btts_no_prob: null, btts_confidence: null,
      total_goals_over_25_prob: null, total_goals_under_25_prob: null,
      total_goals_over_35_prob: null, total_goals_under_35_prob: null, total_goals_confidence: null,
      reasoning: 'QA reasoning.', key_factors: null, status: 'PUBLISHED', created_by: 'qa-expert',
      created_at: isoIn(-2 * DAY_MS), published_at: isoIn(-2 * DAY_MS), superseded_by: null,
      match_details: {
        home_team_name: `Home ${id}`, away_team_name: `Away ${id}`, home_team_logo: null, away_team_logo: null,
        league_name: 'Elite One', match_date: kickoff, external_match_id: null,
      },
      user_details: { username: 'qa-expert', first_name: null, last_name: null },
    });
    const world = await openAsExpert(page, language, [mine('kicked', isoIn(-3 * HOUR_MS))]);

    await page.goto('/expert/predictions/my-predictions');
    await page.getByRole('button', { name: say(language, 'expert.action.edit'), exact: true }).click();
    await expect(page.locator('#edit-kicked-conviction')).toBeVisible();
    const shown = page.getByTestId('edit-after-kickoff');
    await expect(shown, 'editing a prediction on a kicked-off fixture says nothing about scoring').toHaveCount(1);
    await expect(shown).toHaveAttribute('role', 'status');
    await expect(shown).toHaveText(say(language, 'expert.edit.afterKickoff'));

    world.mine = [mine('upcoming', isoIn(3 * DAY_MS))];
    await page.reload();
    await page.getByRole('button', { name: say(language, 'expert.action.edit'), exact: true }).click();
    await expect(page.locator('#edit-upcoming-conviction')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('edit-after-kickoff'), 'an upcoming fixture carried the after-kickoff note').toHaveCount(0);
  });
}

test('a prediction on a kicked-off fixture is still published when the expert presses publish', async ({ page }) => {
  const world = await openAsExpert(page, 'en');
  await page.goto(`/expert/predictions/create?matchId=${KICKED.id}`);
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.locator('#composer-home').fill('55');
  await page.locator('#composer-draw').fill('25');
  await page.locator('#composer-away').fill('20');
  await page.getByRole('button', { name: 'Publish', exact: true }).first().click();
  await expect.poll(() => world.created.length, { message: 'the publish was not sent' }).toBe(1);
  expect(world.created[0].match_id).toBe(KICKED.id);
  await expect(page.getByRole('heading', { name: say('en', 'expert.published.title') })).toBeVisible();
});
