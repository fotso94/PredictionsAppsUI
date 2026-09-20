import { expect, test, Page, Request, Route } from '@playwright/test';
import en from '../../src/i18n/messages/en';
import fr from '../../src/i18n/messages/fr';
import expertEn from '../../src/i18n/messages/expert.en';
import expertFr from '../../src/i18n/messages/expert.fr';
import { compileMessage, renderMessage } from '../../src/i18n/format';
import { ApiMatch, Json, baseMatches, emptyDayPayload, fixtureAt, selectLocalDay, stubBackend } from '../support/api-stub';
import { regularUser, signIn } from '../support/auth';
import { OFFERED_ZONES } from '../../src/i18n/zones';

/**
 * THE EXPERT SCREENS, IN THE READER'S LANGUAGE AND THE READER'S ZONE.
 *
 * An expert is the one person on this site who writes a probability down rather than reading
 * one. That makes these five screens the place where a mistranslation costs the most: a
 * withheld figure that reads as a zero, or a prematch deadline that reads as advice, is not a
 * cosmetic defect on the page where somebody is deciding what to publish under their own name.
 *
 * WHAT THIS FILE ESTABLISHES, and what it deliberately does not.
 *
 * It does NOT establish that the French reads well. No automated test can, and ../../src/i18n/
 * messages/expert.fr.ts says in its own header that no native speaker has reviewed it. What it
 * establishes is the set of things a test CAN settle and a reader cannot easily check:
 *
 *   - that all five screens are actually in the reader's language, in both directions, with a
 *     POSITIVE anchor on each so that an empty page cannot pass the negative check;
 *   - that the stand-ins for a figure nobody published — an unscored accuracy, an unclaimed
 *     conviction, an unset market — are sentences in both languages and never a zero;
 *   - that every count on these screens is right at 0, 1, 2 and 11 in both languages, with a
 *     guard that fails if a new counting message is added and not listed here;
 *   - that a kick-off and a record timestamp are rendered in the zone the reader CHOSE, proved
 *     against a chosen zone that puts them on a DIFFERENT CALENDAR DAY from the browser's own;
 *   - that the composer still turns a typed 55 into a stored 0.55, in French as in English,
 *     which is the behaviour e2e/live/expert-composer.spec.ts pins against the real API;
 *   - and that the English which remains on these screens — all of it from components another
 *     package owns — is counted rather than overlooked, so the gap cannot quietly grow.
 *
 * COST. Every /api/v1 route is intercepted. Nothing here can reach a provider, and the last test
 * asserts that directly: no request may carry `refresh=true`.
 *
 * ZONES. playwright.config.ts gives every project `timezoneId: 'America/New_York'`. A test that
 * had the reader choose New York would pass whether the choice was honoured or thrown away, so
 * no test here chooses it; it is only ever the wrong answer each zone test proves it did not
 * give.
 */

type Language = 'en' | 'fr';

const LANGUAGE_KEY = 'sp.language.v1';
const ZONE_KEY = 'sp.timeZone.v1';

const DOUALA = 'Africa/Douala';
/** The browser context's own zone. Chosen by no test. */
const NEW_YORK = 'America/New_York';

const LOCALE: Record<Language, string> = { en: 'en-GB', fr: 'fr-FR' };

/**
 * A kick-off late enough in UTC that Douala (+01:00) and New York (-04:00) disagree about the
 * DAY, not merely the clock. 23:30Z is 00:30 on the 21st in Douala and 19:30 on the 20th in New
 * York — so a page that ignored the reader's choice would print a different date, not a
 * different time, and no assertion here could miss it.
 */
const KICKOFF_UTC = '2026-09-20T23:30:00Z';
const CREATED_UTC = '2026-09-20T23:45:00Z';
const PUBLISHED_UTC = '2026-09-20T23:50:00Z';

const MATCH_ID = 'expert-fixture-1';

// --------------------------------------------------------------------------- preferences

/**
 * Put the reader's stored choices in place BEFORE the app boots.
 *
 * src/i18n reads both keys while its module is evaluated, so a value written after navigation
 * would be testing the settings panel rather than the stored preference.
 */
async function seedPreferences(
  page: Page,
  preferences: { language?: Language; zone?: string },
): Promise<void> {
  await page.addInitScript(
    ([languageKey, zoneKey, language, zone]) => {
      if (language) window.localStorage.setItem(languageKey, language);
      if (zone) window.localStorage.setItem(zoneKey, zone);
    },
    [LANGUAGE_KEY, ZONE_KEY, preferences.language ?? '', preferences.zone ?? ''] as const,
  );
}

const bodyText = (page: Page): Promise<string> =>
  page.evaluate(() => document.body.innerText.replace(/\s+/g, ' '));

// --------------------------------------------------------------------------- expert payloads

/**
 * One published prediction.
 *
 * `confidence_score` is a real claim; every optional market is absent, which is how the API
 * reports "this expert offered no view here". Nothing below ever turns an absence into a 0.
 *
 * The default 0.8 is deliberate and so is overriding it. `confidence_score` is now nullable the
 * whole way down — column, service, response model — so `prediction({ confidence_score: null })`
 * is a payload the real API produces for an author who supplied no conviction, and
 * `prediction({ confidence_score: 0 })` is one who supplied zero. Those two are different
 * records and the tests below keep them different.
 */
function prediction(over: Partial<Json> = {}): Json {
  return {
    id: 'pred-1',
    match_id: MATCH_ID,
    source: 'EXPERT_MANUAL',
    priority_level: 1,
    home_win_prob: 0.55,
    draw_prob: 0.25,
    away_win_prob: 0.2,
    confidence_score: 0.8,
    btts_yes_prob: null,
    btts_no_prob: null,
    btts_confidence: null,
    total_goals_over_25_prob: null,
    total_goals_under_25_prob: null,
    total_goals_over_35_prob: null,
    total_goals_under_35_prob: null,
    total_goals_confidence: null,
    reasoning: 'The home side keeps more of the ball in this fixture.',
    key_factors: null,
    status: 'PUBLISHED',
    created_by: 'qa-expert',
    created_at: CREATED_UTC,
    published_at: PUBLISHED_UTC,
    superseded_by: null,
    match_details: {
      home_team_name: 'Coton Sport',
      away_team_name: 'Union Douala',
      home_team_logo: null,
      away_team_logo: null,
      league_name: 'Elite One',
      match_date: KICKOFF_UTC,
      external_match_id: null,
    },
    user_details: { username: 'qa-expert', first_name: null, last_name: null },
    ...over,
  };
}

/**
 * The honest empty record: nothing has ever been settled, and no conviction has ever been
 * claimed. `accuracy_rate: null` and `average_confidence: 0` are exactly the two values whose
 * stand-in wording this file exists to check.
 */
function metrics(over: Partial<Json> = {}): Json {
  return {
    expert_id: 'qa-expert',
    expert_name: 'QA Expert',
    total_predictions: 0,
    published_predictions: 0,
    pending_predictions: 0,
    accuracy_rate: null,
    average_confidence: 0,
    predictions_by_league: {},
    recent_predictions: [],
    performance_trend: [],
    ...over,
  };
}

interface ExpertStub {
  mine?: Json[];
  queue?: Json[];
  performance?: Json;
  /** Bodies of every POST to the manual-create endpoint, in order. */
  created?: Json[];
}

/**
 * Answer the expert endpoints.
 *
 * Registered AFTER stubBackend, because Playwright matches the most recently registered route
 * first: stubBackend's catch-all would otherwise hand these paths an empty object and every list
 * on every screen would render as "nothing found" for reasons nothing to do with the language.
 */
async function stubExpert(page: Page, options: ExpertStub = {}): Promise<void> {
  await page.route('**/api/v1/expert/**', async (route: Route, request: Request) => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/expert/, '');

    if (path === '/analytics/performance') return json(options.performance ?? metrics());
    if (path === '/predictions/my-predictions') return json(options.mine ?? []);
    if (path === '/predictions/review-queue') return json(options.queue ?? []);
    if (path === '/predictions/manual' && request.method() === 'POST') {
      const body = JSON.parse(request.postData() || '{}') as Json;
      options.created?.push(body);
      return json({ ...prediction(), ...body, id: 'pred-new' });
    }
    return json({});
  });
}

/** Sign in as an expert and answer everything. The five routes are behind an EXPERT role gate. */
async function openAsExpert(
  page: Page,
  preferences: { language: Language; zone: string },
  options: ExpertStub & { fixtures?: ApiMatch[] } = {},
): Promise<void> {
  await seedPreferences(page, preferences);
  await stubBackend(page, {
    matchById: (id: string) => (options.fixtures ?? []).find(match => match.id === id) ?? null,
  });
  await signIn(page, { user: regularUser({ role: 'expert', full_name: 'QA Expert' }) });
  await stubExpert(page, options);
}

// --------------------------------------------------------------------------- stray detection

/**
 * The English a French page must not carry, and the French an English page must not carry —
 * generated from the catalogues rather than written by hand, so the check grows with them.
 *
 * The exclusions are the same three ../mocked/localisation.spec.ts uses and are safe for the
 * same reasons: an entry whose two languages are identical proves nothing, an entry holding ICU
 * syntax is a template and not a literal, and anything under 16 characters or without a space
 * collides by accident.
 */
function otherLanguageStrings(from: 'en' | 'fr'): string[] {
  const source = from === 'en' ? en : fr;
  return (Object.keys(en) as Array<keyof typeof en>)
    .filter(key => en[key] !== fr[key])
    .map(key => source[key] as string)
    .filter(value => !/[{}#]/.test(value))
    .filter(value => value.trim().length >= 16 && value.trim().includes(' '))
    .map(value => value.trim());
}

const ENGLISH_ONLY = otherLanguageStrings('en');
const FRENCH_ONLY = otherLanguageStrings('fr');

function strays(text: string, forbidden: string[]): string[] {
  const normalised = text.replace(/\s+/g, ' ');
  return forbidden.filter(value => normalised.includes(value.replace(/\s+/g, ' ')));
}

/**
 * The five routes and the heading each must actually show.
 *
 * THE POSITIVE ANCHOR IS THE POINT. A stray check on its own passes on a blank page, a redirect
 * to the sign-in form, and a role gate that sent the visitor somewhere else — three failures
 * that look exactly like success. Each route below names a key whose text has to be on the
 * screen before the absence of the other language means anything.
 */
const ROUTES: Array<{ path: string; anchor: keyof typeof en }> = [
  { path: '/expert/dashboard', anchor: 'expert.dashboard.title' },
  { path: '/expert/match-selection', anchor: 'expert.selection.howHeading' },
  { path: '/expert/predictions/create', anchor: 'expert.compose.chooseIntro' },
  { path: '/expert/predictions/my-predictions', anchor: 'expert.mine.intro' },
  { path: '/expert/predictions/review-queue', anchor: 'expert.queue.noticeBody' },
];

/**
 * ENGLISH THAT IS REALLY ON THE FRENCH PAGE AND IS NOT THIS PACKAGE'S TO REMOVE.
 *
 * The stray check below is exact rather than "at most" on purpose: a new English string on one of
 * these pages fails the test, and so does removing one of these without deleting its line, which
 * means the gap can only shrink deliberately.
 *
 * WHY THIS LIST MOVED, AND WHY THE COMPOSER'S HALF OF IT GREW.
 *
 * It used to name one string on two routes. `components/expert/FixturePicker.tsx` hard-coded
 * twenty-two English literals, and exactly ONE of them — "No forecast held" — happened to be the
 * same sentence as `brief.noForecastHeld` in the core catalogue, which is the only reason a
 * catalogue-derived check could see it. The other twenty-one were in no catalogue and therefore
 * invisible to every check in this file.
 *
 * `/expert/match-selection` no longer renders that component. `pages/ExpertMatchSelectionPage.tsx`
 * renders the list itself, from `expert.picker.*`, so its entry is now EMPTY — and being empty
 * rather than absent is the point: the route is still in ROUTES, still checked, and the day it
 * grows English again this line turns red.
 *
 * `/expert/predictions/create` still renders `FixturePicker`, unchanged, and the entry below grew
 * from one string to four. NOTHING ON THAT PAGE GOT WORSE. Putting the picker's wording into the
 * catalogue is what made three more of its literals VISIBLE to a generated check that could
 * previously see one, and this is where they are counted until the owner of that component
 * translates it.
 *
 * WHY ONLY FOUR OF THE TWENTY-TWO, which is a property of the generator and not a claim that the
 * other eighteen are gone. `otherLanguageStrings` above drops anything holding ICU syntax, and
 * anything under sixteen characters or without a space; `strays` then searches `innerText`. So
 * the picker's English divides up like this, and each line is a reason, not an excuse:
 *
 *   found here (4)     brief.noForecastHeld, expert.picker.searchLabel,
 *                      expert.picker.onlyWithoutExpert, expert.picker.modelForecastHeld
 *   not in innerText   expert.picker.searchPlaceholder (a placeholder attribute) and
 *                      expert.picker.competitionGroup (an aria-label)
 *   too short          expert.picker.dayLabel, dayAfterTomorrow, clearFilters,
 *                      matchday.relative.today, matchday.relative.tomorrow, fixture.live,
 *                      expert.retry
 *   holds ICU syntax   expert.picker.showing, expert.picker.rowAction
 *   not in this state  expert.picker.loading (transient), expertPublished (no fixture in
 *                      e2e/fixtures/matches-day.json has an expert prediction), loadFailed,
 *                      emptyFilteredTitle, emptyFilteredBody, emptyDayTitle, emptyDayBody
 *
 * The package report names all twenty-two and says which of them a French expert meets on the
 * composer today.
 */
const CATALOGUE_ENGLISH_STILL_ON_THE_FRENCH_PAGE: Record<string, string[]> = {
  // Renders its own list now, in the reader's language. Empty on purpose, not absent.
  '/expert/match-selection': [],
  /*
   * FixturePicker.tsx, still English on the composer. In ENGLISH_ONLY order, which is the order
   * `Object.keys(en)` gives and therefore the order the filtered result comes back in:
   *   core.en.ts      brief.noForecastHeld          the badge on a fixture with no forecast
   *   expert.en.ts    expert.picker.searchLabel     the search field's visually-hidden label
   *                   expert.picker.onlyWithoutExpert   the checkbox
   *                   expert.picker.modelForecastHeld   the badge on a fixture with a forecast
   *
   * `expert.picker.expertPublished` clears every filter the generator applies and is STILL not
   * listed, for a reason about the data rather than the check: no fixture in
   * e2e/fixtures/matches-day.json carries an expert prediction, so that badge is never in this
   * page's DOM to be found. It is English on the composer all the same — `the French match picker
   * carries no English the catalogue cannot account for` below builds a fixture that has one, so
   * the badge is rendered and checked somewhere — and listing it here would fail this test for
   * the honest reason that the string is absent.
   */
  '/expert/predictions/create': [
    'No forecast held',
    'Filter by team or competition',
    'Only fixtures with no expert prediction yet',
    'Model forecast held',
  ],
};

for (const language of ['en', 'fr'] as const) {
  test(`every expert screen is in ${language} and carries nothing from the other CATALOGUE`, async ({ page }) => {
    await openAsExpert(page, { language, zone: DOUALA }, {
      mine: [prediction()],
      queue: [prediction({ id: 'pred-2', status: 'UNDER_REVIEW' })],
      performance: metrics({ total_predictions: 1, published_predictions: 1, recent_predictions: [prediction()] }),
    });

    for (const route of ROUTES) {
      await page.goto(route.path);
      await page.waitForLoadState('networkidle');

      // A screen reader picks its voice from this. Getting it wrong is a real defect that no
      // sighted reviewer ever sees.
      await expect(page.locator('html')).toHaveAttribute('lang', language);

      const text = await bodyText(page);
      const wanted = (language === 'en' ? en : fr)[route.anchor];
      expect(text.replace(/\s+/g, ' '), `${route.path} did not render in ${language} at all`)
        .toContain(wanted.replace(/\s+/g, ' '));

      const found = strays(text, language === 'fr' ? ENGLISH_ONLY : FRENCH_ONLY);
      const allowed = language === 'fr' ? CATALOGUE_ENGLISH_STILL_ON_THE_FRENCH_PAGE[route.path] ?? [] : [];
      expect(found, `${route.path} in ${language} carried text from the other catalogue`).toEqual(allowed);
    }
  });
}

/* ================================================== a figure nobody published is not a zero */

/**
 * The three stand-ins, in both languages, on a brand-new expert's dashboard.
 *
 * This is the assertion this whole package is for. `accuracy_rate` is null because nothing has
 * been settled; `average_confidence` is 0 because nobody ever claimed a conviction. Both slots
 * hold a number everywhere else on the page, and in both languages they must hold a SENTENCE.
 * The French adds a trap the English does not have: « Pas encore évaluée » and « Aucune
 * publiée » are feminine, agreeing with « l'exactitude » and « la conviction », and a masculine
 * form here would be the visible sign that the agreement was done by eye.
 */
for (const language of ['en', 'fr'] as const) {
  test(`an unscored accuracy and an unclaimed conviction are sentences, not zeros, in ${language}`, async ({ page }) => {
    await openAsExpert(page, { language, zone: DOUALA }, { performance: metrics() });
    await page.goto('/expert/dashboard');
    await page.waitForLoadState('networkidle');

    const catalogue = language === 'en' ? en : fr;
    const record = page.locator('section[aria-labelledby="record-heading"]');
    await expect(record).toContainText(catalogue['expert.dashboard.notScoredYet']);
    await expect(record).toContainText(catalogue['expert.dashboard.nonePublished']);
    await expect(record).toContainText(catalogue['expert.dashboard.accuracyNote']);

    // And neither slot holds anything a reader could scan as a measurement.
    const figures = await record.locator('p.num').allInnerTexts();
    for (const figure of figures) {
      expect(figure, 'a withheld figure was rendered as a percentage').not.toMatch(/%/);
    }
    expect(figures, 'the three tiles and the accuracy tile all rendered').toContain(
      catalogue['expert.dashboard.notScoredYet'],
    );
    expect(figures).toContain(catalogue['expert.dashboard.nonePublished']);
  });

  test(`a market the expert never published reads as unset, not 0%, in ${language}`, async ({ page }) => {
    await openAsExpert(page, { language, zone: DOUALA }, { mine: [prediction()] });
    await page.goto('/expert/predictions/my-predictions');
    await page.waitForLoadState('networkidle');

    // Open the full record, where every optional market is spelled out.
    await page.getByRole('button', { name: (language === 'en' ? en : fr)['expert.action.viewDetails'] }).first().click();
    const details = page.getByTestId('prediction-details').first();
    await expect(details).toBeVisible();

    const catalogue = language === 'en' ? en : fr;
    // Both goal-line convictions and the BTTS conviction are null in the payload.
    await expect(details).toContainText(catalogue['probability.notSet']);
    // The whole panel must not contain a zero percentage anywhere.
    const text = (await details.innerText()).replace(/\s+/g, ' ');
    expect(text, 'an unpublished market was rendered as zero').not.toMatch(/\b0([.,]0)?\s?%/);
  });

  /**
   * THE HEADLINE CONVICTION, WHICH THE TEST ABOVE NEVER TOUCHED.
   *
   * `prediction()` sets `confidence_score: 0.8`, a real claim, so the panel's conviction row
   * rendered "80%" and the market assertion passed without ever reaching the fallback beside it.
   * Worse, `confidence_score: null` was not a payload the backend could produce: the column was
   * NOT NULL and `ExpertPredictionService` coerced a missing conviction to Decimal("0.0") on
   * three paths, so the page's own comment — "a conviction nobody claimed is not a conviction of
   * zero" — described a guarantee nothing upstream could keep, and this fallback was dead code.
   * The column, the service, the response model and this page now carry null end to end; the
   * payload below is what the API really returns for a prediction whose author gave no
   * conviction, and this is the test that would have gone red before that change.
   */
  test(`a conviction the expert never claimed reads as unset, not 0%, in ${language}`, async ({ page }) => {
    await openAsExpert(page, { language, zone: DOUALA },
      { mine: [prediction({ confidence_score: null })] });
    await page.goto('/expert/predictions/my-predictions');
    await page.waitForLoadState('networkidle');

    const catalogue = language === 'en' ? en : fr;

    // The summary row first. `ConfidenceBadge` takes a bare number and bands it, so an absent
    // conviction reaching it comes out as the lowest band at "(0%)" — the loudest possible way
    // of stating a figure nobody gave. The badge must not be rendered at all.
    const summary = (await bodyText(page));
    expect(summary, 'the conviction badge banded a conviction nobody claimed')
      .not.toMatch(/\(\s*0\s?%\s*\)/);
    expect(summary, 'the summary row did not say the conviction was unset')
      .toContain(catalogue['probability.notSet']);

    // Then the full record, where the conviction has its own labelled row.
    await page.getByRole('button', { name: catalogue['expert.action.viewDetails'] }).first().click();
    const details = page.getByTestId('prediction-details').first();
    await expect(details).toBeVisible();
    await expect(details).toContainText(catalogue['expert.details.confidence']);
    await expect(details).toContainText(catalogue['probability.notSet']);
    const text = (await details.innerText()).replace(/\s+/g, ' ');
    expect(text, 'an unclaimed conviction was rendered as zero').not.toMatch(/\b0([.,]0)?\s?%/);
  });

  /**
   * The other half of the same distinction, and the reason none of this may be done with
   * truthiness. An expert who deliberately rates a prediction at zero has claimed something, and
   * the page must print it. If this test and the one above ever agree, the fix has been undone.
   */
  test(`a conviction the expert deliberately set to zero still reads as 0%, in ${language}`, async ({ page }) => {
    await openAsExpert(page, { language, zone: DOUALA },
      { mine: [prediction({ confidence_score: 0 })] });
    await page.goto('/expert/predictions/my-predictions');
    await page.waitForLoadState('networkidle');

    const catalogue = language === 'en' ? en : fr;
    await page.getByRole('button', { name: catalogue['expert.action.viewDetails'] }).first().click();
    const details = page.getByTestId('prediction-details').first();
    await expect(details).toBeVisible();

    const rows = await details.locator('div.flex.justify-between').allInnerTexts();
    const conviction = rows.find(row => row.includes(catalogue['expert.details.confidence']));
    expect(conviction, 'the conviction row was not rendered at all').toBeTruthy();
    expect((conviction as string).replace(/\s+/g, ' '),
      'a conviction of zero was hidden behind the "not set" wording')
      .toMatch(/\b0\s?%/);
    expect(conviction as string, 'a claimed zero was reported as nothing having been claimed')
      .not.toContain(catalogue['probability.notSet']);
  });
}

/* ========================================================================== counts, 0/1/2/11 */

const COUNTS = [0, 1, 2, 11] as const;

/**
 * Every count-bearing string in the expert area, at 0, 1, 2 and 11, in BOTH languages.
 *
 * None of these needs a plural branch and that is a claim, not an excuse — the nouns are fixed
 * list labels in both languages, exactly as the screens already shipped them, and « Page » does
 * not agree with its numeral. So the claim is checked here at the four counts rather than
 * asserted in a comment. `no expert message counts something without being in the table above`
 * below is what stops the next person adding a counting sentence that nothing renders.
 *
 * The values arrive already formatted, exactly as the components hand them over: the pages call
 * `formatNumber`, so a four-figure count would be "1,024" in English and « 1 024 » in French
 * and the catalogue never sees a raw number.
 */
interface CountCase {
  key: keyof typeof expertEn;
  en: [string, string, string, string];
  fr: [string, string, string, string];
}

const NBSP = '\u00a0';

const COUNT_CASES: CountCase[] = [
  {
    key: 'expert.mine.listHeading',
    en: ['Your Predictions (0)', 'Your Predictions (1)', 'Your Predictions (2)', 'Your Predictions (11)'],
    fr: ['Vos pronostics (0)', 'Vos pronostics (1)', 'Vos pronostics (2)', 'Vos pronostics (11)'],
  },
  {
    key: 'expert.queue.listHeading',
    en: [
      'Flagged for moderation (0)',
      'Flagged for moderation (1)',
      'Flagged for moderation (2)',
      'Flagged for moderation (11)',
    ],
    fr: [
      'Signalés pour modération (0)',
      'Signalés pour modération (1)',
      'Signalés pour modération (2)',
      'Signalés pour modération (11)',
    ],
  },
  {
    key: 'expert.page.number',
    en: ['Page 0', 'Page 1', 'Page 2', 'Page 11'],
    // The insécable between the word and the numeral is part of the expected string, so it
    // cannot be dropped without this failing.
    fr: [`Page${NBSP}0`, `Page${NBSP}1`, `Page${NBSP}2`, `Page${NBSP}11`],
  },
  {
    /*
     * The match picker's count line, and the one entry here whose two languages are built
     * DIFFERENTLY rather than word-for-word.
     *
     * The English is the sentence that screen already showed and is not reworded on the way into
     * the catalogue, so it says "1 of 1 fixtures" at one. It is wrong English and it is recorded
     * as wrong rather than quietly fixed, because fixing it is a copy change and this is a
     * translation change; the note on the key in ../../src/i18n/messages/expert.en.ts says so
     * where the next person will read it.
     *
     * The French is not a translation of that shape. French is singular at 0 AND 1, no ICU
     * plural is available to this area (see the guard below), and « 1 rencontres » would be a
     * mistake on the empty-ish state a reader meets most often — so the noun is attached to
     * NEITHER figure and the sentence is invariable. That is the claim, and these four rows are
     * what check it instead of a comment asserting it.
     *
     * Both holes are fed the same count here. The page passes `shown` and `total` separately and
     * they differ in normal use; what varies the GRAMMAR is the magnitude, and 0/1/2/11 in both
     * holes at once exercises it at the four magnitudes that matter.
     */
    key: 'expert.picker.showing',
    en: [
      'Showing 0 of 0 fixtures on this day.',
      'Showing 1 of 1 fixtures on this day.',
      'Showing 2 of 2 fixtures on this day.',
      'Showing 11 of 11 fixtures on this day.',
    ],
    fr: [
      `Rencontres affichées ce jour-là${NBSP}: 0 sur 0.`,
      `Rencontres affichées ce jour-là${NBSP}: 1 sur 1.`,
      `Rencontres affichées ce jour-là${NBSP}: 2 sur 2.`,
      `Rencontres affichées ce jour-là${NBSP}: 11 sur 11.`,
    ],
  },
];

/**
 * The parameters each count-bearing key takes, named once so the guard below can reuse them.
 *
 * A list rather than a single name: `expert.picker.showing` has two holes, and a table that could
 * only fill one would have had to leave the other rendering as the literal `{total}` — which the
 * formatter prints loudly on purpose, so the row would have "passed" against a string no reader
 * ever sees.
 */
const COUNT_PARAM: Record<string, string[]> = {
  'expert.mine.listHeading': ['count'],
  'expert.queue.listHeading': ['count'],
  'expert.page.number': ['number'],
  'expert.picker.showing': ['shown', 'total'],
};

function render(
  catalogue: Record<string, string>,
  locale: Language,
  key: string,
  params: Record<string, string | number>,
): string {
  return renderMessage(compileMessage(catalogue[key]), LOCALE[locale], params);
}

test('every count on the expert screens is right at 0, 1, 2 and 11, in both languages', () => {
  const wrong: Array<{ at: string; expected: string; actual: string }> = [];
  for (const testCase of COUNT_CASES) {
    const params = COUNT_PARAM[testCase.key];
    COUNTS.forEach((count, index) => {
      for (const language of ['en', 'fr'] as const) {
        // Formatted by the language's own convention, which is what the pages pass in.
        const value = new Intl.NumberFormat(LOCALE[language]).format(count);
        const actual = render(
          (language === 'en' ? expertEn : expertFr) as Record<string, string>,
          language,
          testCase.key,
          Object.fromEntries(params.map(name => [name, value])),
        );
        const expected = testCase[language][index];
        if (actual !== expected) wrong.push({ at: `${testCase.key} in ${language} at ${count}`, expected, actual });
      }
    });
  }
  expect(wrong, 'these expert messages render the wrong form at these counts').toEqual([]);
});

/**
 * THE TABLE ABOVE CANNOT GO STALE, and the area may not grow a plural behind the catalogue's back.
 *
 * Two guards, because two different mistakes are possible. The first: a new expert message that
 * interpolates a count and is not rendered at 0, 1, 2 and 11 by anything. The second, and the
 * one with a consequence outside this file: an expert message that uses ICU `plural`.
 * `every message with a plural is in the table above` in ./localisation.spec.ts scans the WHOLE
 * composed French catalogue and fails on any plural not listed in ITS `COUNT_CASES` — a
 * constant in a file this package does not own. So an expert plural added here would turn that
 * test red, and this says so where the person adding it will read it.
 */
test('no expert message counts something without being in the table above', () => {
  const covered = new Set<string>(COUNT_CASES.map(testCase => testCase.key));
  const holes = (value: string): string[] =>
    [...value.matchAll(/\{\s*([A-Za-z0-9_]+)/g)].map(match => match[1]);

  const counting = (Object.keys(expertEn) as Array<keyof typeof expertEn>)
    .filter(key => holes(expertEn[key]).some(name => /count|number|total|sample/i.test(name)))
    .filter(key => !covered.has(key));
  expect(counting, 'these expert messages interpolate a count and nothing renders them at 0, 1, 2 and 11')
    .toEqual([]);

  const plurals = (Object.keys(expertFr) as Array<keyof typeof expertFr>)
    .filter(key => /,\s*plural\s*,/.test(expertFr[key]));
  expect(
    plurals,
    'an expert message uses an ICU plural: add it to COUNT_CASES in localisation.spec.ts as well, '
    + 'whose guard scans the whole French catalogue, or that file turns red',
  ).toEqual([]);
});

/* ===================================================== a kick-off in the zone the reader chose */

/**
 * The zone test, and why it is written against a DAY rather than a clock.
 *
 * 23:30Z is 00:30 on the 21st in Douala and 19:30 on the 20th in New York, which is the browser
 * context's own zone. So an implementation that read the device zone and threw the reader's
 * choice away prints a different DATE, not a shifted time, and both halves of each assertion
 * below catch it: the chosen answer must be present and the device's answer must be absent.
 *
 * Both expectations are computed with `Intl` rather than typed out, so this test states the
 * RULE — the reader's zone and the reader's locale — instead of a string that would have to be
 * edited every time a format changed.
 *
 * AND THEY ARE COMPUTED BY THE BROWSER UNDER TEST, NOT BY NODE. `Intl` belongs to the engine and
 * the engines disagree: for the same locale, zone and options, Chromium writes
 * "21 Sept 2026, 00:45" and WebKit writes "21 Sep 2026 at 00:45". The mocked suite runs on both
 * — mocked-desktop is Chromium, mocked-mobile is an iPhone 13 and therefore WebKit — so an
 * expectation computed in the test process passes on one project and fails on the other while
 * the page behaves identically on both. Evaluating it in the page keeps this test about the zone
 * and the locale instead of about one engine's spelling of a month.
 */
const inZone = (
  page: Page,
  zone: string,
  locale: string,
  options: Intl.DateTimeFormatOptions,
  iso: string,
): Promise<string> => page.evaluate(
  ([z, l, o, at]) => new Intl.DateTimeFormat(l as string, {
    timeZone: z as string,
    ...(o as Intl.DateTimeFormatOptions),
  }).format(new Date(at as string)),
  [zone, locale, options, iso] as const,
);

/** The invisible spaces `Intl` puts inside a time, flattened so a substring test is meaningful. */
const plainSpaces = (value: string): string => value.replace(/[\u202f\u00a0]/g, ' ');

const DATE_OPTIONS: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long', year: 'numeric' };
const STAMP_OPTIONS: Intl.DateTimeFormatOptions = {
  day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
};

for (const language of ['en', 'fr'] as const) {
  test(`a kick-off and a timestamp are shown in the CHOSEN zone, not the device's, in ${language}`, async ({ page }) => {
    await openAsExpert(page, { language, zone: DOUALA }, { mine: [prediction()] });
    await page.goto('/expert/predictions/my-predictions');
    await page.waitForLoadState('networkidle');

    const text = plainSpaces(await bodyText(page));
    const locale = LOCALE[language];

    const chosenKickoff = await inZone(page, DOUALA, locale, DATE_OPTIONS, KICKOFF_UTC);
    const deviceKickoff = await inZone(page, NEW_YORK, locale, DATE_OPTIONS, KICKOFF_UTC);
    expect(chosenKickoff, 'the two zones must disagree, or this test proves nothing')
      .not.toBe(deviceKickoff);
    expect(text, 'the kick-off was not shown in the zone the reader chose').toContain(chosenKickoff);
    expect(text, "the kick-off was shown in the device's zone").not.toContain(deviceKickoff);

    const chosenStamp = plainSpaces(await inZone(page, DOUALA, locale, STAMP_OPTIONS, CREATED_UTC));
    const deviceStamp = plainSpaces(await inZone(page, NEW_YORK, locale, STAMP_OPTIONS, CREATED_UTC));
    expect(chosenStamp).not.toBe(deviceStamp);
    expect(text, 'the creation timestamp was not shown in the chosen zone').toContain(chosenStamp);
    expect(text, "the creation timestamp was shown in the device's zone").not.toContain(deviceStamp);
  });
}

test('the moderation list reads its timestamps in the chosen zone too', async ({ page }) => {
  await openAsExpert(page, { language: 'fr', zone: DOUALA }, {
    queue: [prediction({ id: 'pred-2', status: 'UNDER_REVIEW' })],
  });
  await page.goto('/expert/predictions/review-queue');
  await page.waitForLoadState('networkidle');

  const text = plainSpaces(await bodyText(page));
  const chosen = await inZone(page, DOUALA, LOCALE.fr, DATE_OPTIONS, KICKOFF_UTC);
  const device = await inZone(page, NEW_YORK, LOCALE.fr, DATE_OPTIONS, KICKOFF_UTC);
  expect(chosen).not.toBe(device);
  expect(text).toContain(chosen);
  expect(text).not.toContain(device);
});

/* ================================================= the unpublished draft, which is private */

/**
 * THE DRAFT NOTICES, WHICH ARE THE ONLY PRIVATE SURFACE ON THESE SCREENS.
 *
 * A draft is half-written words an expert has not published and may never publish. It lives in
 * `localStorage`, keyed by the signed-in user's id, and the two sentences that describe it both
 * have to say three things at once: that it exists, when it was last saved, and — the part that
 * matters — that it is in this browser only and will not publish itself. Nothing else in this
 * file reaches those sentences, because they need a draft in storage before the page loads.
 *
 * They are also the sharpest test of the whole-sentence rule. English puts the fixture in the
 * middle and the "saved" phrase after it; the catalogue owns the entire sentence, so French is
 * free to put them elsewhere, and `relativeTime` supplies the duration already framed — "3
 * minutes ago" against « il y a 3 minutes », which is the frame moving from the end of the
 * phrase to the front of it. A three-fragment implementation cannot do that and would show
 * « 3 minutes il y a ».
 */
const DRAFT_KEY_PREFIX = 'expert.composer.draft.v1';
/** `regularUser()` in e2e/support/auth.ts. The draft is stored per signed-in user id. */
const QA_USER_ID = '00000000-0000-4000-8000-000000000001';

async function seedDraft(page: Page, fixtureId: string, minutesAgo: number): Promise<void> {
  await page.addInitScript(
    ([key, id, minutes]) => {
      window.localStorage.setItem(key as string, JSON.stringify({
        fixture: {
          id,
          homeTeam: 'Coton Sport',
          awayTeam: 'Union Douala',
          competition: 'Elite One',
          kickoff: null,
        },
        values: {
          homeWin: '55', draw: '25', awayWin: '20', conviction: '',
          bttsEnabled: false, bttsYes: '', bttsNo: '', bttsConviction: '',
          over25Enabled: false, over25: '', under25: '',
          over35Enabled: false, over35: '', under35: '',
          totalsConviction: '', reasoning: 'a private note nobody has published',
        },
        savedAt: new Date(Date.now() - (minutes as number) * 60_000).toISOString(),
      }));
    },
    [`${DRAFT_KEY_PREFIX}.${QA_USER_ID}`, fixtureId, minutesAgo] as const,
  );
}

for (const language of ['en', 'fr'] as const) {
  test(`an unfinished draft for another fixture is offered in ${language}, whole sentence and all`, async ({ page }) => {
    const fixture = fixtureAt(KICKOFF_UTC, 'Coton Sport', 'Union Douala', MATCH_ID);
    await openAsExpert(page, { language, zone: DOUALA }, { fixtures: [fixture] });
    await seedDraft(page, 'a-different-fixture', 3);

    /*
     * The journey that reaches this panel, rather than a URL that only looks like it would.
     *
     * Opening the composer on a fixture the draft is NOT for sets the draft aside instead of
     * restoring it — the expert asked for this match, so their half-written words about another
     * one must not appear in these fields. The offer is made on the fixture-choosing screen,
     * which is where the expert lands when they press "change fixture"; that is the only route
     * to it, and going straight to a URL would have tested a branch nobody can reach.
     */
    await page.goto(`/expert/predictions/create?matchId=${MATCH_ID}`);
    await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: (language === 'en' ? en : fr)['expert.compose.changeFixture'] }).click();

    const catalogue = language === 'en' ? en : fr;
    const duration = renderMessage(
      compileMessage(catalogue['duration.minutes']),
      LOCALE[language],
      { count: 3 },
    );
    const ago = renderMessage(compileMessage(catalogue['time.ago']), LOCALE[language], { duration });
    const fixtureLabel = renderMessage(
      compileMessage(catalogue['expert.fixtureShort']),
      LOCALE[language],
      { home: 'Coton Sport', away: 'Union Douala' },
    );
    const sentence = renderMessage(
      compileMessage(catalogue['expert.draft.unfinishedForSaved']),
      LOCALE[language],
      { fixture: fixtureLabel, ago },
    );

    const text = plainSpaces(await bodyText(page));
    expect(text, 'the draft notice was not the catalogue sentence').toContain(plainSpaces(sentence));
    // And the promise the notice makes about where the words live.
    expect(text).toContain(catalogue['expert.draft.notPublishedNote']);
    // The fixture inside the sentence is emphasised, wherever the language put it.
    await expect(page.locator('.card strong, .card .font-semibold').filter({ hasText: 'Coton Sport' }).first())
      .toBeVisible();
  });

  test(`a restored draft says so in ${language}, and says it publishes nothing by itself`, async ({ page }) => {
    const fixture = fixtureAt(KICKOFF_UTC, 'Coton Sport', 'Union Douala', MATCH_ID);
    await openAsExpert(page, { language, zone: DOUALA }, { fixtures: [fixture] });
    await seedDraft(page, MATCH_ID, 3);

    await page.goto(`/expert/predictions/create?matchId=${MATCH_ID}`);
    await page.waitForLoadState('networkidle');

    const catalogue = language === 'en' ? en : fr;
    const duration = renderMessage(
      compileMessage(catalogue['duration.minutes']),
      LOCALE[language],
      { count: 3 },
    );
    const ago = renderMessage(compileMessage(catalogue['time.ago']), LOCALE[language], { duration });
    const sentence = renderMessage(
      compileMessage(catalogue['expert.draft.restoredSaved']),
      LOCALE[language],
      { ago },
    );

    const text = plainSpaces(await bodyText(page));
    expect(text, 'the restore notice was not the catalogue sentence').toContain(plainSpaces(sentence));
    await expect(page.getByRole('button', { name: catalogue['expert.draft.startAgain'] })).toBeVisible();
    // The words the expert typed are their own: restored intact, and shown back untranslated.
    await expect(page.locator('textarea').first()).toHaveValue('a private note nobody has published');
  });
}

/* ============================================ the composer still stores 0.55 for a typed 55 */

/**
 * THE ARITHMETIC IS NOT A LANGUAGE FEATURE, and this proves the translation did not touch it.
 *
 * `e2e/live/expert-composer.spec.ts` pins "55 typed becomes 0.55 stored" against the real API in
 * English. The risk this package introduced is that the French reader is TAUGHT something
 * different — the sentence "type 55 for 55%" now interpolates formatted examples, and French
 * writes them « 55 » and « 55 % ». So two things are checked at once here: that the French
 * sentence still names a whole number and a percentage rather than a decimal, and that a 55
 * typed into the French form still reaches the API as 0.55.
 */
test('a percentage typed as 55 in the French composer is still sent as 0.55', async ({ page }) => {
  const created: Json[] = [];
  const fixture = fixtureAt(KICKOFF_UTC, 'Coton Sport', 'Union Douala', MATCH_ID);
  await openAsExpert(page, { language: 'fr', zone: DOUALA }, { created, fixtures: [fixture] });

  await page.goto(`/expert/predictions/create?matchId=${MATCH_ID}`);
  await page.waitForLoadState('networkidle');

  // The teaching sentence is in French and still teaches the whole number, not the decimal.
  const note = plainSpaces(await bodyText(page));
  expect(note).toContain('Saisissez des pourcentages, pas des décimales');
  expect(note).toContain('tapez 55 pour 55 %');

  const numbers = page.locator('input[inputmode="decimal"]');
  await expect(numbers.first()).toBeVisible();
  await numbers.nth(0).fill('55');
  await numbers.nth(1).fill('25');
  await numbers.nth(2).fill('20');

  await page.getByRole('button', { name: fr['expert.action.publish'], exact: true }).first().click();
  await expect.poll(() => created.length, { timeout: 10_000 }).toBe(1);

  const body = created[0] as Record<string, number>;
  expect(body.home_win_prob).toBeCloseTo(0.55, 4);
  expect(body.draw_prob).toBeCloseTo(0.25, 4);
  expect(body.away_win_prob).toBeCloseTo(0.2, 4);
  // A market the expert did not tick is absent, never zero.
  expect(body.btts_yes_prob ?? null).toBeNull();

  // And the confirmation is in French, in the indicative: it says the thing IS public.
  await expect(page.getByRole('heading', { name: fr['expert.published.title'] })).toBeVisible();
  await expect(page.locator('body')).toContainText(fr['expert.published.body']);
});

/* =================================== the English that is left is counted, not overlooked */

/**
 * WHAT THIS FILE CANNOT FIX, MEASURED RATHER THAN LEFT AS A BLIND SPOT.
 *
 * The stray check above is generated from the CATALOGUES, so it can only ever see a string that
 * entered one of them. The composer's own editor never did: `components/expert/
 * PredictionMarketsEditor.tsx`, `PercentField.tsx`, `PublishPreview.tsx`, `FixtureEvidence.tsx`,
 * `FixturePicker.tsx` and the validation messages in `components/expert/composer.ts` are English
 * literals in the component source, and all six files belong to another package's ownership
 * block. So a French expert reads this page's frame in French and the field labels, hints and
 * errors in English, while every test above passes — which is precisely the shape of false green
 * this project has been burned by before.
 *
 * This does not translate them; it counts them. Each string below is named with the file it
 * comes from, and the owner of those files can delete a line here as they fix each one.
 *
 * WHAT THIS ASSERTION ACTUALLY GUARANTEES, WHICH IS ONE DIRECTION AND NOT TWO. The check filters
 * the ledger by what is on the page, so it fails when a listed string is GONE — translated,
 * reworded or removed — and the number therefore comes down deliberately rather than by accident.
 * It does NOT fail when new English appears, because a string that is in no catalogue and in no
 * list here is in nothing this test iterates over. An earlier version of this comment claimed
 * both directions; it was wrong, and the ledger was eleven strings short for exactly as long as
 * the claim stood. Catching new English needs a different mechanism — an allow-list of the
 * French the page may contain, rather than a deny-list of the English it may not — and that is
 * not built here. Until it is, adding to this ledger is a manual act and the package report, not
 * this test, is what says the list is complete.
 */
const ENGLISH_LEFT_ON_THE_FRENCH_COMPOSER = [
  // components/expert/PredictionMarketsEditor.tsx — the 1X2 block
  'Match result',
  'Your own percentages for the three outcomes. Every prediction publishes this market.',
  'The three outcomes must total 100%.',
  'Your conviction in this call',
  'How strongly you hold this view. Left blank, no conviction is published',
  // components/expert/PredictionMarketsEditor.tsx — the optional-markets block
  'Other markets',
  'Tick only the markets you want to publish a view on. The rest stay unavailable.',
  'Left unticked, this market is not published and readers see it as unavailable.',
  // components/expert/composer.ts — OPTIONAL_MARKET_LABEL, rendered for each market's checkbox
  'Both teams to score',
  'Over / under 2.5 goals',
  'Over / under 3.5 goals',
  // components/expert/PredictionMarketsEditor.tsx — the reasoning field
  'Your reasoning',
  'of 2000 characters.',
  // components/expert/FixtureEvidence.tsx
  'What is already known',
  'The same evidence the public match page shows',
];

/*
 * WHY THIS LIST GREW, AND WHAT IS STILL OUTSIDE IT.
 *
 * It previously held four entries, on the stated grounds that the optional markets' labels "are
 * not in the DOM until the market is ticked". That was checked against the running page and it is
 * not true: `PredictionMarketsEditor` renders every market's label, its checkbox and its
 * "Left unticked…" hint on arrival, unticked. Every entry added above was verified present in
 * this very test's DOM before being listed, and each is named with the file it comes from, so the
 * count a reader takes from this ledger is the count a French expert actually meets.
 *
 * "The three outcomes must total 100%." is the 1X2 pair hint in its UNBALANCED state, which is the
 * state this test's composer is in — it opens with three empty fields and touches nothing. When
 * the three add up the same component says "100% total." instead. Both are English; this ledger
 * names the one that is on the screen here.
 *
 * STILL OUTSIDE IT, deliberately: the single words — "Kick-off", "Venue", "Round", "HOME", "AWAY",
 * "Draw" in FixtureEvidence and the "Draw*" field label — and the validation messages, which need
 * a wrong number typed into a field before they exist. A one-word `includes` against a whole page
 * is an accident waiting to happen ("Venue" is also a French word), and provoking validation
 * inside a check whose job is to count what a reader meets on ARRIVAL would be measuring
 * something else. They are English, they are real, and they are in the package report with the
 * rest; the owner of those files has the full list.
 */

test('the English left on the French composer is counted, and has not grown', async ({ page }) => {
  const fixture = fixtureAt(KICKOFF_UTC, 'Coton Sport', 'Union Douala', MATCH_ID);
  await openAsExpert(page, { language: 'fr', zone: DOUALA }, { fixtures: [fixture] });
  await page.goto(`/expert/predictions/create?matchId=${MATCH_ID}`);
  await page.waitForLoadState('networkidle');

  const text = (await bodyText(page)).replace(/\s+/g, ' ');
  const stillEnglish = ENGLISH_LEFT_ON_THE_FRENCH_COMPOSER.filter(value => text.includes(value));
  expect(
    stillEnglish,
    'this is the ledger of English a French expert still meets in the composer; if one of these '
    + 'was translated, delete its line here, and if a new one appeared, add it and say so',
  ).toEqual(ENGLISH_LEFT_ON_THE_FRENCH_COMPOSER);
});

/* ======================================================================= no provider spend */

/**
 * Nothing in this file may reach a provider.
 *
 * Every /api/v1 route is intercepted, so it cannot; this asserts it anyway, because a
 * localisation change that quietly re-enabled refreshing would spend an allowance that is
 * already spent, and the failure would look like a data problem rather than a test problem.
 */
test('no expert screen asks a provider to refresh', async ({ page }) => {
  const refreshing: string[] = [];
  page.on('request', request => {
    const url = request.url();
    if (url.includes('/api/v1') && /refresh=true/i.test(url)) refreshing.push(url);
  });

  await openAsExpert(page, { language: 'fr', zone: DOUALA }, {
    mine: [prediction()],
    queue: [prediction({ id: 'pred-2' })],
    performance: metrics({ recent_predictions: [prediction()] }),
  });
  for (const route of ROUTES) {
    await page.goto(route.path);
    await page.waitForLoadState('networkidle');
  }

  expect(refreshing, 'an expert screen asked a provider for fresh data').toEqual([]);
});

/* ============================================ the match picker, checked by walking the PAGE */

/**
 * THE CHECK THIS FILE DID NOT HAVE, AND WHY THE ONE IT HAD COULD NOT HAVE FOUND ANY OF THIS.
 *
 * Two mechanisms above look for English on a French page and both are DENY-LISTS. `strays()` is
 * generated from the catalogues, so it can only see a string that entered one of them — of the
 * twenty-two English literals `FixturePicker` held, it could see exactly one, by the coincidence
 * that "No forecast held" is also `brief.noForecastHeld`. `ENGLISH_LEFT_ON_THE_FRENCH_COMPOSER`
 * is a hand-written list, and its own header now says what it took a re-count to learn: a check
 * that iterates a list of known strings finds only what is already on the list, so it cannot fail
 * on a string nobody has thought of. That list was eleven entries short for as long as it claimed
 * otherwise.
 *
 * So this one is the other way round. It iterates the PAGE — every text node, every accessible
 * name, every placeholder, every title inside the match-selection page's own container — reduces
 * what it finds to words, and requires each word to be ACCOUNTED FOR by one of four sources that
 * are themselves derived rather than typed here:
 *
 *   1. the French catalogue, all four areas of it, with the ICU holes stripped out first — a
 *      parameter is named `{home}` and `{total}` in both languages and would otherwise smuggle
 *      "home" and "total" into the vocabulary of allowed French;
 *   2. the fixtures this test itself injected — club names, competitions and countries are data
 *      and are shown as the provider published them, in every language;
 *   3. the zone cities in ../../src/i18n/zones.ts, for the zone named beside the day;
 *   4. what `Intl` itself calls the months and weekdays in French, for the spelled-out date.
 *
 * A word from none of those is a failure, and it is reported with the string it came from.
 *
 * WHAT IT CANNOT DO, said plainly so nobody reads more into a green run than is there. It cannot
 * see a BAD translation — « Jour des rencontres » and « Jour des pommes » are both French. It
 * cannot catch an untranslated English string whose every word also happens to appear somewhere
 * in the French catalogue, and single words are its weakest case for exactly that reason. And it
 * checks this page's own container, not the shared header and footer, which belong to other
 * packages: "Text-only" and "Off" in the header are English on this page in French, they are in
 * the package report, and they are deliberately outside this assertion because failing here would
 * make this package's test go red for another package's string.
 */

/** Words from one message, ICU holes removed, lowercased. Anything under two letters is noise. */
function wordsOf(value: string, into: Set<string>): void {
  value
    .replace(/\{[^}]*\}/g, ' ')
    .toLowerCase()
    .split(/[^\p{L}]+/u)
    .forEach(word => { if (word.length >= 2) into.add(word); });
}

/**
 * Every word a French page may legitimately show, derived from four sources and typed in none.
 *
 * `fixtures` is what the calling test put on the wire; nothing else about the data is assumed.
 */
function frenchVocabulary(fixtures: ApiMatch[]): Set<string> {
  const allowed = new Set<string>();

  for (const value of Object.values(fr)) wordsOf(value, allowed);

  for (const match of fixtures) {
    const competition = match.competition as { name?: string; country?: string } | undefined;
    [match.home?.name, match.home?.short_name, match.home?.country,
      match.away?.name, match.away?.short_name, match.away?.country,
      competition?.name, competition?.country]
      .forEach(name => { if (name) wordsOf(name, allowed); });
  }

  for (const zone of OFFERED_ZONES) wordsOf(zone.city, allowed);
  // `zoneLabel` writes the offset as "UTC+01:00"; the city list already carries "UTC" itself.

  for (let month = 0; month < 12; month += 1) {
    wordsOf(new Intl.DateTimeFormat('fr-FR', { month: 'long' }).format(new Date(Date.UTC(2026, month, 15))), allowed);
  }
  for (let day = 4; day <= 10; day += 1) {
    wordsOf(new Intl.DateTimeFormat('fr-FR', { weekday: 'long' }).format(new Date(Date.UTC(2026, 0, day))), allowed);
  }

  return allowed;
}

/** Everything the page shows or announces, inside this page's own container. */
async function pageStrings(page: Page, testId: string): Promise<string[]> {
  return page.evaluate(id => {
    const root = document.querySelector(`[data-testid="${id}"]`);
    if (!root) return [];
    const found: string[] = [];
    const keep = (value: string | null) => {
      const trimmed = (value ?? '').replace(/\s+/g, ' ').trim();
      if (trimmed) found.push(trimmed);
    };

    // Text nodes, including the visually hidden ones a screen reader is the only reader of.
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) keep(node.textContent);

    // And everything announced rather than drawn.
    root.querySelectorAll('[aria-label]').forEach(el => keep(el.getAttribute('aria-label')));
    root.querySelectorAll('[placeholder]').forEach(el => keep(el.getAttribute('placeholder')));
    root.querySelectorAll('[title]').forEach(el => keep(el.getAttribute('title')));
    root.querySelectorAll('img[alt]').forEach(el => keep(el.getAttribute('alt')));
    return found;
  }, testId);
}

/** Each unaccounted-for word, with one string it appeared in, so a failure names the sentence. */
function unaccountedWords(strings: string[], allowed: Set<string>): string[] {
  const offences = new Map<string, string>();
  for (const value of strings) {
    const seen = new Set<string>();
    wordsOf(value, seen);
    for (const word of seen) if (!allowed.has(word) && !offences.has(word)) offences.set(word, value);
  }
  return [...offences].map(([word, inside]) => `${word} — in: ${inside}`).sort();
}

/**
 * A day of fixtures with the three coverage states and a live kick-off all present at once.
 *
 * Without this the badges are not on the page to be checked: nothing in
 * e2e/fixtures/matches-day.json carries an expert prediction, and nothing in it is live, so a
 * test that took the captured day as it comes would have proved the two rarest labels on the
 * screen were translated when neither had been rendered.
 */
function pickerDay(isoDate: string): ApiMatch[] {
  const pool = baseMatches().slice(0, 6).map((match, index) => ({
    ...match,
    kickoff_utc: `${isoDate}T${String(12 + index).padStart(2, '0')}:00:00Z`,
  }));

  // One already written up by an expert → "Expert prediction published".
  pool[0] = {
    ...pool[0],
    expert_prediction: {
      home_win_prob: 0.5, draw_prob: 0.25, away_win_prob: 0.25, confidence_score: 0.8,
      btts_yes_prob: null, btts_no_prob: null, btts_confidence: null,
      total_goals_over_25_prob: null, total_goals_under_25_prob: null,
      total_goals_over_35_prob: null, total_goals_under_35_prob: null,
      total_goals_confidence: null, reasoning: null, source: 'EXPERT_MANUAL',
      priority_level: 1, published_at: PUBLISHED_UTC,
    },
  };
  // One in play → the live marker stands where the kick-off would be.
  pool[1] = { ...pool[1], status: 'live', minute: '58' };
  // One with no forecast at all → "No forecast held".
  pool[2] = { ...pool[2], forecast: null, forecast_state: 'unavailable' };

  return pool;
}

/** Sign in as an expert, with this day's fixtures on the wire and nothing else changed. */
async function openPicker(
  page: Page,
  preferences: { language: Language; zone: string },
  day: (iso: string, params: URLSearchParams) => Json,
): Promise<void> {
  await seedPreferences(page, preferences);
  await stubBackend(page, { day });
  await signIn(page, { user: regularUser({ role: 'expert', full_name: 'QA Expert' }) });
  await stubExpert(page, {});
}

test('the French match picker carries no English the catalogue cannot account for', async ({ page }) => {
  const today = new Date().toISOString().slice(0, 10);
  const fixtures = pickerDay(today);
  await openPicker(page, { language: 'fr', zone: DOUALA }, iso => ({
    date: iso,
    matches: iso === today ? fixtures : [],
  }));
  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');

  const allowed = frenchVocabulary(fixtures);

  // ---------------------------------------------------------------- arrival, fixtures present
  // The positive anchors first. A vocabulary check passes on a page that rendered nothing, and
  // the three coverage badges plus the live marker are the labels most likely to be missed,
  // because each needs a fixture in a particular state before it exists at all.
  const body = page.getByTestId('expert-match-selection');
  await expect(body).toContainText(fr['expert.picker.expertPublished']);
  await expect(body).toContainText(fr['expert.picker.modelForecastHeld']);
  await expect(body).toContainText(fr['brief.noForecastHeld']);
  await expect(body).toContainText(fr['fixture.live']);
  await expect(body).toContainText(fr['expert.picker.dayLabel']);
  await expect(page.getByTestId('picker-count'))
    .toHaveText(`Rencontres affichées ce jour-là${NBSP}: 6 sur 6.`);

  expect(
    unaccountedWords(await pageStrings(page, 'expert-match-selection'), allowed),
    'a word on the French match picker is in no catalogue, no fixture and no locale',
  ).toEqual([]);

  // ---------------------------------------------------------------- filtered down to nothing
  await page.locator('#picker-search').fill('zzz-no-such-club');
  await expect(body).toContainText(fr['expert.picker.emptyFilteredTitle']);
  await expect(body).toContainText(fr['expert.picker.clearFilters']);
  expect(
    unaccountedWords(await pageStrings(page, 'expert-match-selection'), allowed),
    'the filtered-to-nothing state of the French match picker carries unaccounted-for English',
  ).toEqual([]);
  await page.locator('#picker-search').fill('');

  // ---------------------------------------------------------------- the checkbox on its own
  await page.getByLabel(fr['expert.picker.onlyWithoutExpert']).check();
  await expect(page.getByTestId('picker-count'))
    .toHaveText(`Rencontres affichées ce jour-là${NBSP}: 5 sur 6.`);
  expect(
    unaccountedWords(await pageStrings(page, 'expert-match-selection'), allowed),
    'the expert-filter state of the French match picker carries unaccounted-for English',
  ).toEqual([]);
  await page.getByLabel(fr['expert.picker.onlyWithoutExpert']).uncheck();

  /*
   * AND IT STILL FITS ON THE NARROWEST PHONE, IN THE LONGER LANGUAGE.
   *
   * This list is the page that used to scroll sideways: a 23-fixture day measured 11 CSS pixels
   * of overflow at 390px, so the layout that fixed it is load-bearing rather than decorative.
   * Two things this package did could put it back — French is reliably longer than English, and
   * the day is now spelled out in words above the list where only a date control used to be —
   * and neither mocked project would notice, because they are 1440px and 390px and the phone
   * that broke is 360. Galaxy S8, 360x740, which is what a budget Android reports.
   */
  await page.setViewportSize({ width: 360, height: 740 });
  await expect(body).toContainText(fr['expert.picker.dayLabel']);
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, 'the French match picker scrolls the document sideways at 360px').toBeLessThanOrEqual(0);
});

test('the French match picker says nothing in English when the day is empty or the load fails', async ({ page }) => {
  // ---------------------------------------------------------------- a day with no fixtures
  await openPicker(page, { language: 'fr', zone: DOUALA }, iso => emptyDayPayload(iso) as unknown as Json);
  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');

  const body = page.getByTestId('expert-match-selection');
  await expect(body).toContainText(fr['expert.picker.emptyDayTitle']);
  await expect(body).toContainText(fr['expert.picker.emptyDayBody']);
  expect(
    unaccountedWords(await pageStrings(page, 'expert-match-selection'), frenchVocabulary([])),
    'the empty-day state of the French match picker carries unaccounted-for English',
  ).toEqual([]);

  // ---------------------------------------------------------------- and when the read fails
  //
  // The failure's DESCRIPTION is the server's own sentence and is shown verbatim in both
  // languages — paraphrasing somebody else's error produces a different error. So the stub's
  // words are added to the vocabulary rather than asserted against it; what this checks is that
  // everything AROUND them, the title and the retry, is the reader's language.
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await stubBackend(page, { fail: (url: string) => (url.includes('/matches') ? 503 : 0) });
  await stubExpert(page, {});
  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');

  await expect(body).toContainText(fr['expert.picker.loadFailed']);
  await expect(body).toContainText(fr['expert.retry']);
  const withServerWords = frenchVocabulary([]);
  wordsOf('Simulated backend failure', withServerWords);
  expect(
    unaccountedWords(await pageStrings(page, 'expert-match-selection'), withServerWords),
    'the failed-load state of the French match picker carries unaccounted-for English',
  ).toEqual([]);
});

/* ======================================================= the kick-off, in the zone that was chosen */

/**
 * A KICK-OFF IN THE WRONG ZONE IS A WRONG ANSWER ON THIS SCREEN, NOT A COSMETIC ONE.
 *
 * The reader of this list is deciding whether a fixture is still prematch. So this is checked the
 * only way that can settle it: with a kick-off close enough to midnight that the candidate zones
 * disagree about the CALENDAR DAY, not merely the clock.
 *
 * 23:30Z on the 20th is 00:30 on the 21st in Douala (+01:00), 02:30 on the 21st in Nairobi
 * (+03:00) and 19:30 on the 20th in New York (-04:00). NEITHER CHOSEN ZONE IS NEW YORK, which is
 * what playwright.config.ts gives the browser context: a test that chose the browser's own zone
 * would pass whether the reader's choice was honoured or thrown away, and would prove nothing.
 * Both chosen zones are asserted to show their own time AND to show the right calendar day in
 * words, and both are asserted NOT to show the browser's.
 *
 * It also covers the day WINDOW and not only the formatting. The list asks the backend for one
 * local day, and `selectLocalDay` applies the backend's own rule to the `tz_offset` pair the
 * client sends — so a client that stopped sending offsets, or sent the device's, would drop this
 * fixture out of the response entirely and the row would not be there to read.
 */
const ZONE_CASES = [
  { zone: DOUALA, clock: '00:30', day: { fr: 'Rencontres du 21 septembre 2026', en: 'Fixtures for 21 September 2026' } },
  { zone: 'Africa/Nairobi', clock: '02:30', day: { fr: 'Rencontres du 21 septembre 2026', en: 'Fixtures for 21 September 2026' } },
] as const;

for (const language of ['fr', 'en'] as const) {
  for (const zoneCase of ZONE_CASES) {
    test(`a near-midnight kick-off reads in ${zoneCase.zone}, not the browser's zone, in ${language}`, async ({ page }) => {
      const fixture = fixtureAt(KICKOFF_UTC, 'Coton Sport', 'Union Douala', MATCH_ID);
      await openPicker(page, { language, zone: zoneCase.zone },
        (iso, params) => selectLocalDay([fixture], iso, params) as unknown as Json);
      await page.goto('/expert/match-selection');
      await page.waitForLoadState('networkidle');

      // The chosen zone's own calendar day for this instant, reached through the date control so
      // the test does not depend on what "today" is when it runs.
      await page.locator('#picker-date').fill('2026-09-21');
      await page.waitForLoadState('networkidle');

      const catalogue = language === 'en' ? en : fr;
      const body = page.getByTestId('expert-match-selection');
      await expect(body, 'the fixture is not in the day the chosen zone files it under')
        .toContainText('Coton Sport');

      // The clock, in the row.
      await expect(body).toContainText(zoneCase.clock);
      expect(await body.innerText(), 'the kick-off was rendered in the browser\'s zone, not the reader\'s')
        .not.toContain('19:30');

      // The day, spelled out, which is the half a clock reading alone cannot settle: 00:30 and
      // 19:30 are different times, but 00:30 on the 21st and 00:30 on the 20th are not.
      await expect(page.getByTestId('picker-day-shown')).toContainText(zoneCase.day[language]);

      // And the accessible name, which is all a screen reader gets and is assembled separately.
      const rowAction = renderMessage(
        compileMessage(catalogue['expert.picker.rowAction']),
        LOCALE[language],
        {
          action: catalogue['expert.action.writePrediction'],
          home: 'Coton Sport',
          away: 'Union Douala',
          competition: 'Premier League',
          time: zoneCase.clock,
        },
      );
      await expect(page.getByRole('button', { name: rowAction })).toBeVisible();
    });
  }
}

/**
 * AND THE ZONE CHANGING WHILE THE LIST IS ALREADY ON SCREEN.
 *
 * The four tests above load a page in a chosen zone. This one changes the choice underneath a
 * list that is already rendered, which is the case that fails differently: the kick-off, the day
 * spelled out beside it and the UTC window the backend is asked for all have to move together,
 * and a fixture at 23:30Z is on a different CALENDAR DAY in the two zones, so a list that moved
 * only the clock would be filing it under the wrong day.
 *
 * Nairobi and Douala, never New York — see the header. The device's 19:30 is asserted absent
 * throughout, because falling back to the device is the failure this is looking for.
 *
 * WHAT THIS DOES NOT PROVE, and the note is here so a green run is not read as more than it is.
 * `PickerRow` re-derives the clock from `kickoffUtc` on every render rather than printing the
 * `match.time` the mapper wrote once. That is strictly safer — it is right for a data source
 * whose mapper formats in the DEVICE's zone, and it repaints without waiting for a refetch — but
 * it is not what this test isolates: `backend-match-data.service.ts` also drops its cache on a
 * zone change, so the refetch this triggers would have produced a correctly re-mapped
 * `match.time` as well. Removing the re-derivation leaves these assertions green. No stubbed
 * test here can separate the two, and claiming otherwise would be the false green this file is
 * built to avoid.
 */
test('changing the zone re-times and re-dates the match picker already on screen', async ({ page }) => {
  const fixture = fixtureAt(KICKOFF_UTC, 'Coton Sport', 'Union Douala', MATCH_ID);
  await openPicker(page, { language: 'fr', zone: DOUALA },
    (iso, params) => selectLocalDay([fixture], iso, params) as unknown as Json);
  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');
  await page.locator('#picker-date').fill('2026-09-21');
  await page.waitForLoadState('networkidle');

  const body = page.getByTestId('expert-match-selection');
  await expect(body.locator('time')).toHaveText('00:30');
  await expect(page.getByTestId('picker-day-shown')).toContainText('Douala');

  await page.getByTestId('footer-region-settings').first().click();
  await page.getByTestId('time-zone-choice').first().selectOption('Africa/Nairobi');

  // 23:30Z is 00:30 on the 21st in Douala, 02:30 on the 21st in Nairobi, 19:30 on the 20th in
  // the device's New York. The clock moves, the day does not, and the fixture stays in the list
  // — which is the part that needs the refetch to have asked for Nairobi's day and not Douala's.
  await expect(body.locator('time')).toHaveText('02:30');
  await expect(body).toContainText('Coton Sport');
  await expect(page.getByTestId('picker-day-shown')).toContainText('Rencontres du 21 septembre 2026');
  await expect(page.getByTestId('picker-day-shown')).toContainText('Nairobi');
  expect(await body.innerText(), 'the list fell back to the device\'s zone')
    .not.toContain('19:30');
});

/*
 * AND THE REFETCH ITSELF, PINNED ON ITS OWN.
 *
 * The test above passes with EITHER production change in place: drop `zone` from the fetch
 * effect's dependencies and the kick-off re-derivation still renders the right clock; drop the
 * re-derivation and the refetch still brings back the right day. Only removing both turns it
 * red, so neither is individually held — the green-both-ways shape this project has shipped
 * more than once.
 *
 * This one watches the request rather than the rendering. A change of zone changes which UTC
 * window the reader's local day covers, so it has to be a new question to the backend even when
 * the date in the control has not moved. If `zone` leaves that dependency array, no second
 * request is issued and this fails, whatever the screen happens to show.
 */
test('changing the zone asks the backend again, because the local day is a different window', async ({ page }) => {
  const fixture = fixtureAt(KICKOFF_UTC, 'Coton Sport', 'Union Douala', MATCH_ID);
  let dayRequests = 0;
  await openPicker(page, { language: 'fr', zone: DOUALA }, (iso, params) => {
    dayRequests += 1;
    return selectLocalDay([fixture], iso, params) as unknown as Json;
  });
  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');
  await page.locator('#picker-date').fill('2026-09-21');
  await page.waitForLoadState('networkidle');

  const beforeZoneChange = dayRequests;
  expect(beforeZoneChange, 'the picker asked for the day at least once').toBeGreaterThan(0);

  await page.getByTestId('footer-region-settings').first().click();
  await page.getByTestId('time-zone-choice').first().selectOption('Africa/Nairobi');
  await page.waitForLoadState('networkidle');

  expect(dayRequests, 'a change of zone is a change of window, so it must be asked again')
    .toBeGreaterThan(beforeZoneChange);
});
