import { expect, test, Locator, Page, Request, Route } from '@playwright/test';
import { Json, stubBackend } from '../support/api-stub';
import { regularUser, signIn } from '../support/auth';
import { LIVE_API_MESSAGE, fenceLiveApi } from '../support/live-stack';
import expertEn from '../../src/i18n/messages/expert.en';
import expertFr from '../../src/i18n/messages/expert.fr';

/**
 * THE EXPERT'S DASHBOARD RECORD, MY PREDICTIONS' PAGES, AND PUBLISH / UNPUBLISH (QA findings 4, 5).
 *
 * The defects this file was written against:
 *   - the dashboard's "Not published" tile showed PENDING alone. Experts publish directly, so their
 *     unpublished predictions are ARCHIVED, which nothing counted: unpublish the only prediction and
 *     the record read Written 1 / Published 0 / Not published 0. The list under "Recently published"
 *     held every status, and a row with no publication time showed its creation time as one;
 *   - My Predictions guessed "there is a next page" from "this page came back full", so exactly 20
 *     predictions offered Next into an empty page; on an empty page the pagination bar vanished
 *     with Previous in it, and the empty state said "You haven't created any predictions yet";
 *     deleting the only row of page 2 landed there too; the heading counted the rows on the page;
 *   - Unpublish and Publish existed only on the dashboard's ten-row list.
 *
 * THE STUB IS STATEFUL. One list of rows, newest first, behind every expert endpoint the two pages
 * read: my-predictions honours limit, offset and status the way the backend does and sets
 * X-Total-Count for the same filter (exposed to the page as the backend's CORS configuration
 * exposes it); DELETE removes a row; toggle-publish flips PUBLISHED and ARCHIVED and nothing else;
 * analytics/performance is derived from the rows on every call, so a count is right only if the
 * page reads the right field. Every request is logged, and the assertions are on that log and on
 * the rows as well as on the screen: how many toggles were sent, which offset was asked for, what
 * the row's status is now.
 *
 * ABSENCE CHECKS ARE BOUNDED. "Nothing was sent" is checked over a stated window (1500 ms after a
 * dismissed confirmation or after a page settles), which is far longer than the page takes to send
 * a request it is going to send.
 *
 * COPY. The strings this change adds are written out below in both languages rather than looked up,
 * so on the old code (which has none of the new keys) a lookup cannot come back undefined and match
 * anything; the last test checks that these literals are still the catalogue's.
 *
 * COST. Every /api/v1 route is stubbed; nothing reaches a backend. A guard (support/live-stack.ts)
 * aborts, and fails the test on, any request to the live API (:8000) that no stub answered. It does
 * not fence the frontend origin, which is the page under test on the default configuration.
 */

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;
const isoIn = (ms: number): string => new Date(Date.now() + ms).toISOString().replace(/\.\d{3}Z$/, 'Z');

/** How long "nothing more was sent" is watched for. */
const QUIET_MS = 1500;

type Language = 'en' | 'fr';

const COPY = {
  en: {
    myPredictionsTitle: 'My Predictions',
    viewDetails: 'View details',
    next: 'Next',
    previous: 'Previous',
    edit: 'Edit',
    delete: 'Delete',
    unpublish: 'Unpublish',
    publish: 'Publish',
    working: 'Working…',
    heading: (count: number) => `Your Predictions (${count})`,
    headingUncounted: 'Your Predictions',
    emptyNone: "You haven't created any predictions yet.",
    createFirst: 'Create Your First Prediction',
    emptyPageTitle: 'This page is empty',
    emptyPageBody: 'Nothing is listed on this page any more: the list has become shorter since it was opened. Go back to the previous page.',
    confirmUnpublish: 'Unpublish this prediction? Readers will no longer see it on the match page. You can publish it again later.',
    confirmPublish: 'Publish this prediction? Readers will see it on the match page straight away.',
    // True whichever way the record stands (finding #19): a counted prediction stays counted, and
    // one never counted is not counted now. The old pair said "does not remove it" / "does not add
    // it", each of which implied the state it did not name.
    kickedOffUnpublish: 'This match has kicked off. Unpublishing now hides this prediction from readers but does not change your measured record, which is decided by what stood at kick-off.',
    kickedOffPublish: 'This match has kicked off. Publishing now shows this prediction to readers but does not change your measured record, which is decided by what stood at kick-off.',
    confirmDeleteMine: 'Are you sure you want to delete this prediction? This action cannot be undone.',
    confirmDeleteDashboard: 'Delete this prediction? It disappears from the public match page and cannot be undone.',
    kickedOffDelete: 'This match has kicked off. Deleting this prediction now removes it from readers and from your lists, but does not change your measured record, which is decided by what stood at kick-off.',
    lateNotScored: 'Published after kick-off · not in your measured record',
    withdrawnNotScored: 'Withdrawn before kick-off · not in your measured record',
    recentHeading: 'Recent predictions',
    statWritten: 'Predictions written',
    statPublished: 'Published',
    statNotPublished: 'Not published',
    // The ARCHIVED part of "Not published", named as the status filter and the badge name it
    // (finding #22): "Unpublished" beside "Not published" was two near-synonyms counting two sets.
    statUnpublished: 'Archived',
    statAverage: 'Average conviction',
  },
  fr: {
    myPredictionsTitle: 'Mes pronostics',
    viewDetails: 'Voir le détail',
    next: 'Suivant',
    previous: 'Précédent',
    edit: 'Modifier',
    delete: 'Supprimer',
    unpublish: 'Dépublier',
    publish: 'Publier',
    working: 'En cours…',
    heading: (count: number) => `Vos pronostics (${count})`,
    headingUncounted: 'Vos pronostics',
    emptyNone: 'Vous n’avez encore créé aucun pronostic.',
    createFirst: 'Rédiger votre premier pronostic',
    emptyPageTitle: 'Cette page est vide',
    emptyPageBody: 'Plus rien n’est listé sur cette page : la liste a raccourci depuis son ouverture. Revenez à la page précédente.',
    confirmUnpublish: 'Dépublier ce pronostic ? Les lecteurs ne le verront plus sur la page du match. Vous pourrez le publier à nouveau plus tard.',
    confirmPublish: 'Publier ce pronostic ? Les lecteurs le verront immédiatement sur la page du match.',
    kickedOffUnpublish: 'Le coup d’envoi a été donné. Dépublier ce pronostic maintenant le cache aux lecteurs, mais ne change rien à votre bilan mesuré, qui dépend de ce qui était publié au coup d’envoi.',
    kickedOffPublish: 'Le coup d’envoi a été donné. Publier ce pronostic maintenant le montre aux lecteurs, mais ne change rien à votre bilan mesuré, qui dépend de ce qui était publié au coup d’envoi.',
    confirmDeleteMine: 'Voulez-vous vraiment supprimer ce pronostic ? Cette action est irréversible.',
    confirmDeleteDashboard: 'Supprimer ce pronostic ? Il disparaît de la page publique du match et l’opération est irréversible.',
    kickedOffDelete: 'Le coup d’envoi a été donné. Supprimer ce pronostic maintenant le retire de vos listes et le cache aux lecteurs, mais ne change rien à votre bilan mesuré, qui dépend de ce qui était publié au coup d’envoi.',
    lateNotScored: 'Publié après le coup d’envoi · hors de votre bilan mesuré',
    withdrawnNotScored: 'Retiré avant le coup d’envoi · hors de votre bilan mesuré',
    recentHeading: 'Pronostics récents',
    statWritten: 'Pronostics rédigés',
    statPublished: 'Publiés',
    statNotPublished: 'Non publiés',
    statUnpublished: 'Dépubliés',
    statAverage: 'Conviction moyenne',
  },
} as const;

const EN = COPY.en;

// --------------------------------------------------------------------------- rows

/** Created a minute apart, newest first, so row 01 is the first card and row 21 opens page 2. */
const CREATED_BASE = Date.now() - DAY_MS;
const createdAt = (n: number): string => new Date(CREATED_BASE - n * 60_000).toISOString().replace(/\.\d{3}Z$/, 'Z');

const tag = (n: number): string => String(n).padStart(2, '0');

/**
 * One of the expert's predictions as the API returns it. Statuses are lowercase, as the real API
 * sends them. The fixture kicks off three days from now unless `kickoff` says otherwise, so no
 * kickoff rule interferes with a test that is not about one.
 */
function row(n: number, over: Partial<Json> = {}, kickoff: string = isoIn(3 * DAY_MS)): Json {
  const created = createdAt(n);
  return {
    id: `pred-${tag(n)}`,
    match_id: `fx-${tag(n)}`,
    source: 'expert_manual',
    priority_level: 1,
    home_win_prob: 0.5,
    draw_prob: 0.3,
    away_win_prob: 0.2,
    confidence_score: 0.7,
    btts_yes_prob: null,
    btts_no_prob: null,
    btts_confidence: null,
    total_goals_over_25_prob: null,
    total_goals_under_25_prob: null,
    total_goals_over_35_prob: null,
    total_goals_under_35_prob: null,
    total_goals_confidence: null,
    reasoning: `Reasoning for fixture ${tag(n)}.`,
    key_factors: null,
    status: 'published',
    created_by: 'qa-expert',
    created_at: created,
    published_at: created,
    unpublished_at: null,
    superseded_by: null,
    match_details: {
      home_team_name: `Alpha ${tag(n)}`,
      away_team_name: `Omega ${tag(n)}`,
      home_team_logo: null,
      away_team_logo: null,
      league_name: 'Elite One',
      match_date: kickoff,
      external_match_id: null,
    },
    user_details: { username: 'qa_expert', first_name: 'QA', last_name: 'Expert' },
    ...over,
  };
}

const rows = (from: number, to: number, over: (n: number) => Partial<Json> = () => ({})): Json[] =>
  Array.from({ length: to - from + 1 }, (_, i) => row(from + i, over(from + i)));

// --------------------------------------------------------------------------- the stateful stub

interface Logged { method: string; path: string; params: URLSearchParams }

interface Store {
  /** Newest first, exactly as the backend orders an expert's predictions. */
  rows: Json[];
  /** False answers my-predictions without X-Total-Count, as an older backend would. */
  sendTotal: boolean;
  /** True answers analytics/performance without the two counts this change reads. */
  legacyPerformance: boolean;
  /** While set, toggle-publish waits for it before answering. */
  toggleGate: Promise<void> | null;
  log: Logged[];
  dialogs: string[];
  dialogAnswer: 'accept' | 'dismiss';
  liveStackHits: string[];
}

let current: Store | null = null;

async function stubExpert(page: Page, store: Store): Promise<void> {
  await page.route('**/api/v1/expert/**', async (route: Route, request: Request) => {
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1\/expert/, '');
    const method = request.method();
    store.log.push({ method, path, params: url.searchParams });
    const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
      route.fulfill({ status, contentType: 'application/json', headers, body: JSON.stringify(body) });
    const statusOf = (r: Json): string => String(r.status).toLowerCase();

    if (path === '/predictions/my-predictions' && method === 'GET') {
      const limit = Number(url.searchParams.get('limit') ?? 50);
      const offset = Number(url.searchParams.get('offset') ?? 0);
      const wanted = url.searchParams.get('status');
      const matching = store.rows.filter(r => !wanted || statusOf(r) === wanted.toLowerCase());
      // The backend's CORS configuration exposes X-Total-Count (backend/app/main.py); without the
      // expose header a cross-origin page could not read it, so the stub says the same.
      const headers: Record<string, string> = store.sendTotal
        ? { 'X-Total-Count': String(matching.length), 'Access-Control-Expose-Headers': 'X-Total-Count' }
        : {};
      return json(matching.slice(offset, offset + limit), 200, headers);
    }

    const toggle = path.match(/^\/predictions\/([^/]+)\/toggle-publish$/);
    if (toggle && method === 'POST') {
      if (store.toggleGate) await store.toggleGate;
      const target = store.rows.find(r => r.id === toggle[1]);
      if (!target) return json({ detail: `Prediction ${toggle[1]} not found` }, 404);
      const was = statusOf(target);
      if (was !== 'published' && was !== 'archived') {
        return json({ detail: `Cannot toggle publish status for prediction with status ${was}.` }, 400);
      }
      target.status = was === 'published' ? 'archived' : 'published';
      if (target.status === 'published' && !target.published_at) target.published_at = isoIn(0);
      return json(target);
    }

    const single = path.match(/^\/predictions\/([^/]+)$/);
    if (single && method === 'DELETE') {
      const index = store.rows.findIndex(r => r.id === single[1]);
      if (index < 0) return json({ detail: `Prediction ${single[1]} not found` }, 404);
      store.rows.splice(index, 1);
      return json({
        message: 'Prediction deleted successfully', prediction_id: single[1], deleted_at: isoIn(0), already_deleted: false,
      });
    }

    if (path === '/analytics/performance') {
      const count = (status: string) => store.rows.filter(r => statusOf(r) === status).length;
      const total = store.rows.length;
      const published = count('published');
      const stated = store.rows.map(r => r.confidence_score).filter((v): v is number => typeof v === 'number');
      const body: Json = {
        expert_id: 'qa-expert',
        expert_name: 'QA Expert',
        total_predictions: total,
        published_predictions: published,
        pending_predictions: count('pending'),
        archived_predictions: count('archived'),
        not_published_predictions: total - published,
        accuracy_rate: null,
        average_confidence: stated.length ? stated.reduce((a, b) => a + b, 0) / stated.length : null,
        predictions_by_league: {},
        recent_predictions: store.rows.slice(0, 10),
        performance_trend: [],
      };
      if (store.legacyPerformance) {
        delete body.archived_predictions;
        delete body.not_published_predictions;
      }
      return json(body);
    }
    if (path === '/predictions/review-queue') return json([]);
    return json({});
  });
}

async function open(
  page: Page,
  seed: Json[],
  options: { language?: Language; sendTotal?: boolean; legacyPerformance?: boolean } = {},
): Promise<Store> {
  const store: Store = {
    rows: seed,
    sendTotal: options.sendTotal ?? true,
    legacyPerformance: options.legacyPerformance ?? false,
    toggleGate: null,
    log: [],
    dialogs: [],
    dialogAnswer: 'dismiss',
    liveStackHits: [],
  };
  current = store;
  if (options.language) {
    await page.addInitScript(language => window.localStorage.setItem('sp.language.v1', language), options.language);
  }
  // One answer for every confirm() this page raises, set by the test before the click.
  page.on('dialog', dialog => {
    store.dialogs.push(dialog.message());
    void (store.dialogAnswer === 'accept' ? dialog.accept() : dialog.dismiss());
  });
  await stubBackend(page);
  await stubExpert(page, store);
  await signIn(page, { user: regularUser({ role: 'expert', full_name: 'QA Expert' }) });
  await fenceLiveApi(page, store.liveStackHits);
  return store;
}

test.afterEach(() => {
  if (current) expect(current.liveStackHits, LIVE_API_MESSAGE).toEqual([]);
  current = null;
});

// --------------------------------------------------------------------------- reading the log

const listGets = (store: Store): Logged[] =>
  store.log.filter(entry => entry.method === 'GET' && entry.path === '/predictions/my-predictions');
const lastListGet = (store: Store): Logged | undefined => listGets(store).at(-1);
const toggles = (store: Store): string[] =>
  store.log.filter(entry => entry.method === 'POST' && entry.path.endsWith('/toggle-publish')).map(entry => entry.path);
const deletes = (store: Store): string[] =>
  store.log.filter(entry => entry.method === 'DELETE').map(entry => entry.path);
const statusOfRow = (store: Store, id: string): string | undefined =>
  store.rows.find(r => r.id === id)?.status as string | undefined;

// --------------------------------------------------------------------------- reading the page

/** The cards on My Predictions: the children of the list, one per prediction, on the old page and the new. */
const cards = (page: Page) => page.locator('div.space-y-4 > div');
const card = (page: Page, n: number) => cards(page).filter({ hasText: `Alpha ${tag(n)}` });
const listHeading = (page: Page) => page.locator('h2').filter({ hasText: /^(Your Predictions|Vos pronostics)/ });
const button = (scope: Page | Locator, name: string) =>
  scope.getByRole('button', { name, exact: true });
const pageLabel = (page: Page, n: number) => page.getByText(`Page ${n}`, { exact: true });

async function openMine(page: Page, language: Language = 'en'): Promise<void> {
  await page.goto('/expert/predictions/my-predictions');
  await expect(page.getByRole('heading', { level: 1, name: COPY[language].myPredictionsTitle })).toBeVisible();
  await page.waitForLoadState('networkidle');
}

/** Next is either not offered or cannot be pressed. */
async function expectNoNext(page: Page, why: string): Promise<void> {
  const next = button(page, EN.next);
  if (await next.count() > 0) await expect(next, why).toBeDisabled();
}

/** Previous is either not offered or cannot be pressed. */
async function expectNoPrevious(page: Page, why: string): Promise<void> {
  const previous = button(page, EN.previous);
  if (await previous.count() > 0) await expect(previous, why).toBeDisabled();
}

/** The record tiles as label -> figure. A tile that is not there is simply absent. */
async function recordTiles(page: Page): Promise<Record<string, string>> {
  const tiles = page.locator('section[aria-labelledby="record-heading"] div.grid > div.card');
  const out: Record<string, string> = {};
  for (let i = 0; i < await tiles.count(); i += 1) {
    const label = (await tiles.nth(i).locator('p').first().innerText()).trim();
    out[label] = (await tiles.nth(i).locator('p.num').innerText()).replace(/\s+/g, ' ').trim();
  }
  return out;
}

interface Counts { written: number; published: number; notPublished: number; unpublished: number | undefined }

async function recordCounts(page: Page): Promise<Counts> {
  const tiles = await recordTiles(page);
  const number = (label: string): number | undefined =>
    tiles[label] === undefined ? undefined : Number(tiles[label].replace(/\D/g, ''));
  return {
    written: number(EN.statWritten) ?? NaN,
    published: number(EN.statPublished) ?? NaN,
    notPublished: number(EN.statNotPublished) ?? NaN,
    unpublished: number(EN.statUnpublished),
  };
}

async function openDashboard(page: Page): Promise<void> {
  await page.goto('/expert/dashboard');
  await expect(page.locator('section[aria-labelledby="record-heading"]')).toBeVisible();
  await page.waitForLoadState('networkidle');
}

/**
 * Wait for the record to show `written` and `published`, then check that it adds up, and then the
 * rest. In that order, so a record that does not add up is reported as that. `unpublished` is
 * checked only when the expectation names it.
 */
async function expectRecord(
  page: Page,
  expected: Omit<Counts, 'unpublished'> & { unpublished?: number },
  when: string,
): Promise<void> {
  await expect.poll(async () => {
    const counts = await recordCounts(page);
    return [counts.written, counts.published];
  }, { message: `the record did not settle ${when}` }).toEqual([expected.written, expected.published]);
  const counts = await recordCounts(page);
  expect(counts.written, `${when}: Predictions written = Published + Not published`)
    .toBe(counts.published + counts.notPublished);
  expect(counts.notPublished, `${when}: Not published`).toBe(expected.notPublished);
  if ('unpublished' in expected) expect(counts.unpublished, `${when}: ${EN.statUnpublished} (the archived tile)`).toBe(expected.unpublished);
}

/* ======================================================================= My Predictions: pages */

test('exactly 20 predictions are one page: Next cannot be pressed and the heading says 20', async ({ page }) => {
  const store = await open(page, rows(1, 20));
  await openMine(page);

  await expect(cards(page)).toHaveCount(20);
  await expect(listHeading(page)).toHaveText(EN.heading(20));
  // A full page is not evidence of a second one: the total says there is none.
  await expectNoNext(page, 'Next is offered into a page that cannot hold anything');
  await expect(page.locator('body')).not.toContainText(EN.emptyNone);
  expect(listGets(store).map(entry => entry.params.get('offset') ?? '0'), 'only the first page was asked for')
    .toEqual(listGets(store).map(() => '0'));
});

test('a later page that has emptied since it was counted keeps Previous and says so', async ({ page }) => {
  const store = await open(page, rows(1, 21));
  await openMine(page);
  await expect(cards(page)).toHaveCount(20);

  // Another tab deletes one prediction after page 1 was counted: page 2 is now past the end.
  store.rows.splice(0, 1);
  await button(page, EN.next).click();
  await expect(pageLabel(page, 2)).toBeVisible();
  await expect(cards(page)).toHaveCount(0);
  await expect(page.getByText(EN.emptyPageTitle, { exact: true })).toBeVisible();
  await expect(page.locator('body')).toContainText(EN.emptyPageBody);
  // The account has predictions; the page must not say otherwise or offer to create the first one.
  await expect(page.locator('body')).not.toContainText(EN.emptyNone);
  await expect(page.locator('body')).not.toContainText(EN.createFirst);
  await expect(listHeading(page)).toHaveText(EN.heading(20));
  const previous = button(page, EN.previous);
  await expect(previous).toBeVisible();
  await expect(previous).toBeEnabled();

  // The empty page is shown, not chased: no request is sent on its own within the window.
  const settled = listGets(store).length;
  await page.waitForTimeout(QUIET_MS);
  expect(listGets(store).length, `a request was sent within ${QUIET_MS} ms of an empty page settling`).toBe(settled);

  await previous.click();
  await expect(cards(page)).toHaveCount(20);
  expect(lastListGet(store)?.params.get('offset')).toBe('0');
});

test('21 predictions: page 2 holds the 21st, and deleting it steps back to page 1 with 20', async ({ page }) => {
  const store = await open(page, rows(1, 21));
  await openMine(page);
  await expect(cards(page)).toHaveCount(20);
  await expect(listHeading(page), 'the heading counts every prediction, not this page').toHaveText(EN.heading(21));

  await button(page, EN.next).click();
  await expect(pageLabel(page, 2)).toBeVisible();
  await expect(cards(page)).toHaveCount(1);
  await expect(card(page, 21)).toHaveCount(1);
  await expect(listHeading(page)).toHaveText(EN.heading(21));
  await expectNoNext(page, 'Next is offered past the last prediction');

  store.dialogAnswer = 'accept';
  const before = listGets(store).length;
  await button(card(page, 21), EN.delete).click();
  await expect.poll(() => deletes(store)).toEqual(['/predictions/pred-21']);

  await expect(cards(page)).toHaveCount(20);
  await expect(pageLabel(page, 2)).toHaveCount(0);
  await expect(listHeading(page)).toHaveText(EN.heading(20));
  await expect(page.locator('body')).not.toContainText(EN.emptyNone);
  await expect(page.locator('body')).not.toContainText(EN.emptyPageTitle);
  await expectNoNext(page, 'Next is offered from the only page left');
  await expectNoPrevious(page, 'Previous is offered from the first page');

  // One step back and no further: the page it was on, then the page before it, then quiet.
  await page.waitForTimeout(QUIET_MS);
  const after = listGets(store).slice(before);
  expect(after.length, 'reloads after the delete').toBeLessThanOrEqual(2);
  expect(after.at(-1)?.params.get('offset')).toBe('0');
  expect(store.rows).toHaveLength(20);
});

test('the heading counts every prediction on every page, and Next stops at the last page', async ({ page }) => {
  const store = await open(page, rows(1, 45));
  await openMine(page);
  await expect(cards(page)).toHaveCount(20);
  await expect(listHeading(page)).toHaveText(EN.heading(45));

  await button(page, EN.next).click();
  await expect(pageLabel(page, 2)).toBeVisible();
  await expect(cards(page)).toHaveCount(20);
  await expect(listHeading(page)).toHaveText(EN.heading(45));

  await button(page, EN.next).click();
  await expect(pageLabel(page, 3)).toBeVisible();
  await expect(cards(page)).toHaveCount(5);
  await expect(card(page, 45)).toHaveCount(1);
  await expect(listHeading(page)).toHaveText(EN.heading(45));
  await expectNoNext(page, 'Next is offered past the 45th prediction');
  await expect(button(page, EN.previous)).toBeEnabled();
  expect(lastListGet(store)?.params.get('offset')).toBe('40');
});

test('without an X-Total-Count header the page still knows whether a next page exists', async ({ page }) => {
  const store = await open(page, rows(1, 20), { sendTotal: false });
  await openMine(page);
  await expect(cards(page)).toHaveCount(20);
  await expectNoNext(page, 'Next is offered on a full page that is also the last one');
  // The first page with nothing after it is the whole list, so its count is the total.
  await expect(listHeading(page)).toHaveText(EN.heading(20));

  store.rows.push(row(21));
  await page.reload();
  await expect(cards(page)).toHaveCount(20);
  // More exists and nothing says how much: the heading claims no number rather than a wrong one.
  await expect(listHeading(page)).toHaveText(EN.headingUncounted);
  await button(page, EN.next).click();
  await expect(pageLabel(page, 2)).toBeVisible();
  await expect(cards(page)).toHaveCount(1);
  await expectNoNext(page, 'Next is offered past the last prediction');
  // The last page, with full pages before it, gives the total.
  await expect(listHeading(page)).toHaveText(EN.heading(21));
  // The probe: one row more than a page is asked for, and that row is never shown.
  expect(listGets(store).every(entry => entry.params.get('limit') === '21'), 'each page asks for one extra row').toBe(true);
});

/**
 * A PIN, NOT A REGRESSION TEST: the old page already reset to the first page on a filter change, in
 * the select's own onChange. It is pinned because the step-back rule below must not undo it.
 */
test('changing the status filter on page 2 asks for the first page of that status', async ({ page }) => {
  const store = await open(page, rows(1, 25, n => (n % 5 === 0 ? { status: 'archived' } : {})));
  await openMine(page);
  await button(page, EN.next).click();
  await expect(pageLabel(page, 2)).toBeVisible();
  await expect(cards(page)).toHaveCount(5);

  await page.locator('#status-filter').selectOption('archived');
  await expect.poll(() => lastListGet(store)?.params.get('status')).toBe('archived');
  expect(lastListGet(store)?.params.get('offset')).toBe('0');
  await expect(cards(page)).toHaveCount(5);
  await expect(pageLabel(page, 2)).toHaveCount(0);
  await expect(listHeading(page)).toHaveText(EN.heading(5));
  for (const n of [5, 10, 15, 20, 25]) await expect(card(page, n)).toContainText('Archived');
});

/* ================================================================ My Predictions: publication */

test('Unpublish and Publish on My Predictions: a confirmation each, one request each', async ({ page }) => {
  const store = await open(page, [row(1)]);
  await openMine(page);
  const unpublish = button(card(page, 1), EN.unpublish);
  await expect(unpublish, 'My Predictions offers no Unpublish').toBeVisible();
  // The fixture is three days away: nothing about kickoff applies.
  await expect(card(page, 1)).not.toContainText(EN.kickedOffUnpublish);

  // Dismissed: nothing is sent.
  store.dialogAnswer = 'dismiss';
  await unpublish.click();
  await expect.poll(() => store.dialogs.length).toBe(1);
  expect(store.dialogs[0]).toBe(EN.confirmUnpublish);
  await page.waitForTimeout(QUIET_MS);
  expect(toggles(store), `a toggle was sent within ${QUIET_MS} ms of a dismissed confirmation`).toEqual([]);
  expect(statusOfRow(store, 'pred-01')).toBe('published');

  // Accepted: exactly one request, and the card says what it is now.
  store.dialogAnswer = 'accept';
  await unpublish.click();
  await expect.poll(() => toggles(store)).toEqual(['/predictions/pred-01/toggle-publish']);
  await expect(button(card(page, 1), EN.publish)).toBeVisible();
  await expect(card(page, 1)).toContainText('Archived');
  expect(statusOfRow(store, 'pred-01')).toBe('archived');
  await page.waitForTimeout(QUIET_MS);
  expect(toggles(store), 'one click sent more than one toggle').toHaveLength(1);

  // And back.
  await button(card(page, 1), EN.publish).click();
  await expect.poll(() => toggles(store)).toHaveLength(2);
  expect(store.dialogs[2]).toBe(EN.confirmPublish);
  await expect(button(card(page, 1), EN.unpublish)).toBeVisible();
  await expect(card(page, 1)).toContainText('Published');
  expect(statusOfRow(store, 'pred-01')).toBe('published');
});

test('the publication control is disabled while its request is in flight', async ({ page }) => {
  const store = await open(page, [row(1)]);
  await openMine(page);
  let release: () => void = () => undefined;
  store.toggleGate = new Promise<void>(resolve => { release = resolve; });
  store.dialogAnswer = 'accept';

  await button(card(page, 1), EN.unpublish).click();
  const busy = button(card(page, 1), EN.working);
  await expect(busy).toBeVisible();
  await expect(busy).toBeDisabled();
  await expect(button(card(page, 1), EN.delete)).toBeDisabled();
  // A second press on the busy control raises no confirmation and sends nothing.
  await busy.click({ force: true });
  await page.waitForTimeout(QUIET_MS);
  expect(store.dialogs, 'a busy control asked again').toHaveLength(1);
  expect(toggles(store)).toHaveLength(1);

  release();
  await expect(button(card(page, 1), EN.publish)).toBeVisible();
  expect(toggles(store)).toHaveLength(1);
  expect(statusOfRow(store, 'pred-01')).toBe('archived');
});

test('after kickoff, the card and the confirmation say the measured record does not change', async ({ page }) => {
  const kickedOff = isoIn(-2 * HOUR_MS);
  const store = await open(page, [
    row(1, {}, kickedOff),
    row(2, { status: 'archived' }, kickedOff),
    row(3),
  ]);
  await openMine(page);

  await expect(card(page, 1)).toContainText(EN.kickedOffUnpublish);
  await expect(card(page, 2)).toContainText(EN.kickedOffPublish);
  await expect(card(page, 3)).not.toContainText(EN.kickedOffUnpublish);
  await expect(card(page, 3)).not.toContainText(EN.kickedOffPublish);

  store.dialogAnswer = 'accept';
  await button(card(page, 1), EN.unpublish).click();
  await expect.poll(() => toggles(store)).toEqual(['/predictions/pred-01/toggle-publish']);
  expect(store.dialogs[0]).toBe(`${EN.confirmUnpublish}\n\n${EN.kickedOffUnpublish}`);
  // Unpublishing after kickoff is still allowed; the note is about what it changes, not a refusal.
  expect(statusOfRow(store, 'pred-01')).toBe('archived');
  await expect(card(page, 1)).toContainText(EN.kickedOffPublish);

  await button(card(page, 2), EN.publish).click();
  await expect.poll(() => toggles(store)).toHaveLength(2);
  expect(store.dialogs[1]).toBe(`${EN.confirmPublish}\n\n${EN.kickedOffPublish}`);
});

/*
 * Review finding #20. Settlement treats a deletion like an unpublish: one made at or after kick-off
 * does not take the prediction out of the measured record. The card's note said so for Unpublish,
 * directly above a Delete that asked only "cannot be undone" — which read, by contrast, as the way
 * to remove a loss. The note is for rows that were public (published or archived); a pending or
 * rejected row was never in the record, and a fixture still to come has nothing decided yet.
 */
test('after kickoff, Delete asks with the note that the measured record does not change, on both pages', async ({ page }) => {
  const kickedOff = isoIn(-2 * HOUR_MS);
  const store = await open(page, [
    row(1, {}, kickedOff),
    row(2, { status: 'archived' }, kickedOff),
    row(3),
    row(4, { status: 'pending', published_at: null }, kickedOff),
  ]);
  await openMine(page);
  const asked = async (scope: Locator, n: number): Promise<string> => {
    await button(scope, EN.delete).click();
    await expect.poll(() => store.dialogs.length).toBe(n);
    return store.dialogs[n - 1];
  };

  store.dialogAnswer = 'dismiss';
  expect(await asked(card(page, 1), 1), 'published, kicked off').toBe(`${EN.confirmDeleteMine}\n\n${EN.kickedOffDelete}`);
  expect(await asked(card(page, 2), 2), 'archived, kicked off').toBe(`${EN.confirmDeleteMine}\n\n${EN.kickedOffDelete}`);
  expect(await asked(card(page, 3), 3), 'published, kick-off still to come').toBe(EN.confirmDeleteMine);
  expect(await asked(card(page, 4), 4), 'pending: never in the record').toBe(EN.confirmDeleteMine);
  await page.waitForTimeout(QUIET_MS);
  expect(deletes(store), `a delete was sent within ${QUIET_MS} ms of a dismissed confirmation`).toEqual([]);

  // Accepted, it still deletes: the note says what the deletion does not change, it refuses nothing.
  store.dialogAnswer = 'accept';
  expect(await asked(card(page, 1), 5)).toBe(`${EN.confirmDeleteMine}\n\n${EN.kickedOffDelete}`);
  await expect.poll(() => deletes(store)).toEqual(['/predictions/pred-01']);

  // The dashboard's own Delete says the same, under the same rule.
  store.dialogAnswer = 'dismiss';
  await openDashboard(page);
  const recent = (n: number) => page.locator('section[aria-labelledby="recent-heading"] li').filter({ hasText: `Alpha ${tag(n)}` });
  expect(await asked(recent(2), 6), 'dashboard, archived, kicked off').toBe(`${EN.confirmDeleteDashboard}\n\n${EN.kickedOffDelete}`);
  expect(await asked(recent(3), 7), 'dashboard, kick-off still to come').toBe(EN.confirmDeleteDashboard);
  await page.waitForTimeout(QUIET_MS);
  expect(deletes(store), 'the dashboard deleted on a dismissed confirmation').toEqual(['/predictions/pred-01']);
});

/*
 * Review finding #1. The expert's own views never said which predictions count. Settlement scores
 * what stood at kick-off (`stood_at_kickoff`): published strictly before it and not withdrawn
 * before it, with the backend's boundary — AT kick-off is after it. My Predictions and the
 * dashboard now name the two ways a prediction that was public falls outside the record, and say
 * nothing where the record is not affected or not decided yet.
 */
test('My Predictions and the dashboard say which predictions are not in the measured record, and no others', async ({ page }) => {
  const kickoff = isoIn(-3 * HOUR_MS);
  const from = (ms: number): string => new Date(Date.parse(kickoff) + ms).toISOString().replace(/\.\d{3}Z$/, 'Z');
  // The backend serves unpublished_at with no zone on it (only created_at and published_at have a
  // Z serialiser): the page must read it as the UTC it is, as it reads every backend instant.
  const naive = (iso: string): string => iso.replace(/Z$/, '');
  await open(page, [
    row(1, { published_at: from(HOUR_MS) }, kickoff),
    row(2, { published_at: kickoff }, kickoff),
    row(3, { status: 'archived', published_at: from(-5 * HOUR_MS), unpublished_at: from(-HOUR_MS) }, kickoff),
    row(4, { published_at: from(-5 * HOUR_MS), unpublished_at: naive(from(-HOUR_MS)) }, kickoff),
    row(5, { published_at: from(-5 * HOUR_MS) }, kickoff),
    row(6, { status: 'archived', published_at: from(-5 * HOUR_MS), unpublished_at: from(HOUR_MS) }, kickoff),
    row(7, { status: 'archived', published_at: isoIn(-2 * HOUR_MS), unpublished_at: isoIn(-HOUR_MS) }),
    row(8, { status: 'pending', published_at: null }, kickoff),
  ]);
  const cases: Array<[number, string | null, string]> = [
    [1, EN.lateNotScored, 'published an hour after kick-off'],
    [2, EN.lateNotScored, 'published AT kick-off, which is after it'],
    [3, EN.withdrawnNotScored, 'unpublished before kick-off and still down'],
    [4, EN.withdrawnNotScored, 'unpublished before kick-off, published again after it (the withdrawal is frozen)'],
    [5, null, 'published before kick-off and standing: it counts'],
    [6, null, 'unpublished AFTER kick-off: it still counts'],
    [7, null, 'unpublished, kick-off three days away: nothing is decided yet'],
    [8, null, 'pending: never public, so not a record question'],
  ];
  const check = async (scope: (n: number) => Locator, where: string) => {
    for (const [n, label, why] of cases) {
      await expect(scope(n)).toBeVisible();
      if (label) {
        await expect(scope(n), `${where}, row ${n} (${why})`).toContainText(label);
      } else {
        await expect(scope(n), `${where}, row ${n} (${why})`).not.toContainText(EN.lateNotScored);
        await expect(scope(n), `${where}, row ${n} (${why})`).not.toContainText(EN.withdrawnNotScored);
      }
    }
  };

  await openMine(page);
  await check(n => card(page, n), 'My Predictions');
  await openDashboard(page);
  await check(n => page.locator('section[aria-labelledby="recent-heading"] li').filter({ hasText: `Alpha ${tag(n)}` }), 'the dashboard');
});

test('unpublishing the last row of a filtered later page steps back one page', async ({ page }) => {
  const store = await open(page, rows(1, 21));
  await openMine(page);
  await page.locator('#status-filter').selectOption('published');
  await expect.poll(() => lastListGet(store)?.params.get('status')).toBe('published');
  await button(page, EN.next).click();
  await expect(pageLabel(page, 2)).toBeVisible();
  await expect(cards(page)).toHaveCount(1);

  store.dialogAnswer = 'accept';
  const before = listGets(store).length;
  await button(card(page, 21), EN.unpublish).click();
  await expect.poll(() => toggles(store)).toEqual(['/predictions/pred-21/toggle-publish']);
  // It is no longer published, so it has left this filter, and page 2 with it.
  await expect(cards(page)).toHaveCount(20);
  await expect(pageLabel(page, 2)).toHaveCount(0);
  await expect(listHeading(page)).toHaveText(EN.heading(20));
  await expect(page.locator('body')).not.toContainText(EN.emptyPageTitle);
  await page.waitForTimeout(QUIET_MS);
  const after = listGets(store).slice(before);
  expect(after.length, 'reloads after the toggle').toBeLessThanOrEqual(2);
  expect(after.at(-1)?.params.get('offset')).toBe('0');
  expect(after.at(-1)?.params.get('status')).toBe('published');
});

/* ======================================================================== the dashboard record */

test('the record adds up after publish, unpublish and republish, and after every reload', async ({ page }) => {
  const store = await open(page, [row(1)]);
  store.dialogAnswer = 'accept';
  await openDashboard(page);
  // The Archived tile is checked from the next state on, so that on a page which cannot add up
  // the failure reported is that one.
  await expectRecord(page, { written: 1, published: 1, notPublished: 0 }, 'after publishing');

  // Unpublished from the dashboard's own row.
  const recent = page.locator('section[aria-labelledby="recent-heading"] li').filter({ hasText: 'Alpha 01' });
  await button(recent, EN.unpublish).click();
  await expect.poll(() => toggles(store)).toHaveLength(1);
  expect(statusOfRow(store, 'pred-01')).toBe('archived');
  await expectRecord(page, { written: 1, published: 0, notPublished: 1, unpublished: 1 }, 'after unpublishing');
  await page.reload();
  await expectRecord(page, { written: 1, published: 0, notPublished: 1, unpublished: 1 }, 'after unpublishing and a reload');

  // Republished from My Predictions.
  await openMine(page);
  await button(card(page, 1), EN.publish).click();
  await expect.poll(() => toggles(store)).toHaveLength(2);
  await expect(button(card(page, 1), EN.unpublish)).toBeVisible();
  await openDashboard(page);
  await expectRecord(page, { written: 1, published: 1, notPublished: 0, unpublished: 0 }, 'after republishing');
  await page.reload();
  await expectRecord(page, { written: 1, published: 1, notPublished: 0, unpublished: 0 }, 'after republishing and a reload');
});

test('"Not published" counts everything that is not published, pending and rejected included', async ({ page }) => {
  await open(page, [
    row(1),
    row(2, { status: 'archived' }),
    row(3, { status: 'pending', published_at: null }),
    row(4, { status: 'rejected', published_at: null }),
  ]);
  await openDashboard(page);
  await expectRecord(page, { written: 4, published: 1, notPublished: 3, unpublished: 1 }, 'with four statuses');
});

test('an older payload without the new counts still adds up, and claims no unpublished count', async ({ page }) => {
  await open(page, [row(1), row(2, { status: 'archived' }), row(3, { status: 'archived' })], { legacyPerformance: true });
  await openDashboard(page);
  await expect.poll(async () => (await recordCounts(page)).written).toBe(3);
  const counts = await recordCounts(page);
  expect(counts.notPublished, 'Not published falls back to written - published').toBe(2);
  expect(counts.written).toBe(counts.published + counts.notPublished);
  expect(counts.unpublished, 'a count the payload did not carry is not shown').toBeUndefined();
  expect(Object.values(await recordTiles(page)).join(' '), 'no tile reads NaN').not.toContain('NaN');
});

test('the recent list is called what it holds, and only a published row says when it was published', async ({ page }) => {
  await open(page, [
    row(1),
    row(2, { status: 'archived' }),
    row(3, { status: 'pending', published_at: null }),
  ]);
  await openDashboard(page);
  const section = page.locator('section[aria-labelledby="recent-heading"]');
  await expect(section.locator('h2')).toHaveText(EN.recentHeading);
  const item = (n: number) => section.locator('li').filter({ hasText: `Alpha ${tag(n)}` });
  await expect(section.locator('li')).toHaveCount(3);
  await expect(item(1)).toContainText(/Published \S/);
  // An archived row WAS published, and when is a fact; its control publishes it again.
  await expect(item(2)).toContainText(/Published \S/);
  await expect(button(item(2), EN.publish)).toBeVisible();
  // A pending row was never published: no date may stand in for one (its badge says Pending).
  await expect(item(3)).not.toContainText('Published');
});

test('the dashboard asks before it unpublishes, as My Predictions does', async ({ page }) => {
  const store = await open(page, [row(1, {}, isoIn(-2 * HOUR_MS))]);
  await openDashboard(page);
  const recent = page.locator('section[aria-labelledby="recent-heading"] li').filter({ hasText: 'Alpha 01' });

  store.dialogAnswer = 'dismiss';
  await button(recent, EN.unpublish).click();
  await expect.poll(() => store.dialogs.length).toBe(1);
  expect(store.dialogs[0]).toBe(`${EN.confirmUnpublish}\n\n${EN.kickedOffUnpublish}`);
  await page.waitForTimeout(QUIET_MS);
  expect(toggles(store), `a toggle was sent within ${QUIET_MS} ms of a dismissed confirmation`).toEqual([]);

  store.dialogAnswer = 'accept';
  await button(recent, EN.unpublish).click();
  await expect.poll(() => toggles(store)).toHaveLength(1);
});

/* ============================================================================== width, in French */

/**
 * Run at every width the mocked projects have, and the binding one is 360 (mocked-mobile-360):
 * French is the longer language, the record grew a fifth tile and the cards a fourth action.
 * "Fits" is measured: the document does not scroll sideways, no tile label is cut short by its
 * ellipsis, and every action button lies inside its card.
 */
test('in French the record, the recent list and the card actions fit this width', async ({ page }) => {
  const fr = COPY.fr;
  await open(page, [
    // Published an hour after a kick-off two hours ago: the longest card, with the not-in-the-record label.
    row(1, { published_at: isoIn(-HOUR_MS) }, isoIn(-2 * HOUR_MS)),
    row(2, { status: 'archived' }),
    ...rows(3, 21),
  ], { language: 'fr' });

  await openDashboard(page);
  await expect(page.locator('section[aria-labelledby="recent-heading"] h2')).toHaveText(fr.recentHeading);
  const tiles = page.locator('section[aria-labelledby="record-heading"] div.grid > div.card');
  const labels = (await tiles.locator('p:first-child').allInnerTexts()).map(text => text.trim());
  expect(labels).toEqual([fr.statWritten, fr.statPublished, fr.statNotPublished, fr.statUnpublished, fr.statAverage]);
  const cut = await tiles.locator('p:first-child').evaluateAll(nodes =>
    nodes.filter(node => node.scrollWidth > node.clientWidth + 1).map(node => node.textContent));
  expect(cut, 'these record labels are cut short at this width').toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth),
    'the dashboard scrolls sideways').toBeLessThanOrEqual(0);

  await openMine(page, 'fr');
  await expect(listHeading(page)).toHaveText(fr.heading(21));
  await expect(card(page, 1)).toContainText(fr.kickedOffUnpublish);
  await expect(card(page, 1)).toContainText(fr.lateNotScored);
  await expect(button(card(page, 1), fr.unpublish)).toBeVisible();
  await expect(button(card(page, 2), fr.publish)).toBeVisible();
  const outside = await cards(page).evaluateAll(nodes => nodes.flatMap(node => {
    const box = node.getBoundingClientRect();
    return Array.from(node.querySelectorAll('button, [data-testid="record-not-scored"]'))
      .filter(b => {
        const r = b.getBoundingClientRect();
        const cut = b.tagName !== 'BUTTON' && b.scrollWidth > b.clientWidth + 1;
        return r.left < box.left - 0.5 || r.right > box.right + 0.5 || cut;
      })
      .map(b => b.textContent);
  }));
  expect(outside, 'these card actions or labels overflow their card, or are cut short, at this width').toEqual([]);
  await expect(button(page, fr.next)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth),
    'My Predictions scrolls sideways').toBeLessThanOrEqual(0);
});

/* ============================================================================== the copy itself */

test('the copy this file reads is the catalogue\'s, in both languages', () => {
  const keys: Array<[keyof typeof COPY.en, string]> = [
    ['emptyPageTitle', 'expert.mine.emptyPageTitle'],
    ['emptyPageBody', 'expert.mine.emptyPageBody'],
    ['headingUncounted', 'expert.mine.listHeadingUncounted'],
    ['confirmUnpublish', 'expert.publication.confirmUnpublish'],
    ['confirmPublish', 'expert.publication.confirmPublish'],
    ['kickedOffUnpublish', 'expert.publication.kickedOffUnpublish'],
    ['kickedOffPublish', 'expert.publication.kickedOffPublish'],
    ['kickedOffDelete', 'expert.publication.kickedOffDelete'],
    ['confirmDeleteMine', 'expert.mine.confirmDelete'],
    ['confirmDeleteDashboard', 'expert.dashboard.confirmDelete'],
    ['lateNotScored', 'expert.record.publishedAfterKickoff'],
    ['withdrawnNotScored', 'expert.record.withdrawnBeforeKickoff'],
    ['recentHeading', 'expert.dashboard.recentHeading'],
    ['statUnpublished', 'expert.dashboard.statUnpublished'],
    ['statNotPublished', 'expert.dashboard.statNotPublished'],
    ['unpublish', 'expert.action.unpublish'],
    ['publish', 'expert.action.publish'],
    ['working', 'expert.action.working'],
    ['emptyNone', 'expert.mine.emptyNone'],
  ];
  const catalogues = { en: expertEn as Record<string, string>, fr: expertFr as Record<string, string> };
  const drift: string[] = [];
  for (const language of ['en', 'fr'] as const) {
    for (const [name, key] of keys) {
      if (COPY[language][name] !== catalogues[language][key]) drift.push(`${language} ${key}`);
    }
  }
  expect(drift, 'these literals no longer match the catalogue').toEqual([]);
});
