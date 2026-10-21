import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { APIRequestContext, BrowserContext, Locator, Page, Request } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { ISOLATED_BASE, isolatedApiContext } from '../support/isolated';
import { guardExternalAssets } from '../support/external-assets';
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '../support/auth';
import {
  cleanupQaPredictions, classifyQaPrediction, ensureQaExpertToken, QA_EXPERT, QA_REASONING_MARKER,
} from '../support/qa-account';
import authEn from '../../src/i18n/messages/auth.en';
import coreEn from '../../src/i18n/messages/core.en';
import expertEn from '../../src/i18n/messages/expert.en';
import readerEn from '../../src/i18n/messages/reader.en';

/**
 * THE OWNER'S JOURNEY, in one browser, through the real pages, on the isolated pair (:3101 against
 * :8001, soccer_predictions_e2e, scheduler off, no provider credentials).
 *
 * Every step is a UI action a person takes: the sign-in form (a wrong password first), the profile
 * form, match selection, the composer (an invalid figure, a draft, a reload, the preview, publish),
 * a SEPARATE ANONYMOUS browser on the public match page, My Predictions (edit, unpublish, publish,
 * delete, an empty filter) and the profile form again to put the name back. Nothing in the journey
 * itself is done through the API. The API on :8001 (isolatedApiContext only) is used for three
 * things and no more: to read back what the UI's actions stored, as a second witness beside the
 * page; to classify the one prediction the journey publishes as test data (the composer's own
 * request does not and must not carry that flag); and to send the second DELETE, which no UI
 * control can send, to prove the deletion time does not move.
 *
 * WHAT IT WRITES. One prediction by the QA expert on one upcoming fixture, published, edited once,
 * unpublished, published again and soft-deleted, all through the UI; its audit rows and its
 * deleted_at stay in soccer_predictions_e2e, as every delete's do. The QA expert's first name is
 * changed and put back through the UI. cleanupQaPredictions runs before and after (it finds nothing
 * after a passing run, the journey having deleted its own record); a profile safety net in
 * afterAll puts the first name back through the API only if a failed run left it changed, and says
 * so.
 *
 * NOTHING HERE MAY REACH THE LIVE STACK. Both browser contexts abort, and the test fails on, any
 * request to :8000 or :3100, and every API call goes through isolatedApiContext, which refuses
 * :8000 and any backend serving the live database. No provider is called: match selection and
 * the match page read stored rows, and the isolated backend has no provider keys.
 *
 * EVIDENCE. With E2E_EVIDENCE_DIR set, a full-page JPEG is kept at each major step. A screenshot
 * is refused if the QA account's email is in the page's text, and every email input is masked;
 * the header's account menu (the one place that prints the email) is never open in a picture.
 */

const LIVE_STACK = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):(8000|3100)(\/|$)/;
const EVIDENCE = process.env.E2E_EVIDENCE_DIR;
/** How long "nothing more was sent" is watched for. */
const ABSENCE_WINDOW_MS = 1500;

/** A LOCAL TEST FIXTURE, like QA_EXPERT.password: deliberately not the QA expert's password. */
const WRONG_PASSWORD = 'local-only-e2e-wrong-password';
const JOURNEY_FIRST_NAME = 'QA-Journey';
/** Both start with the same label, so My Predictions finds the card before and after the edit. */
const CARD_LABEL = `${QA_REASONING_MARKER} journey:`;
const REASONING_FIRST = `${CARD_LABEL} the home side presses higher and wins more second balls`;
const REASONING_EDITED = `${CARD_LABEL} revised after the team news, the away keeper is back`;

/** What is typed into the composer, as the expert types it: whole percentages. */
const TYPED = {
  home: '52', draw: '27', away: '21', conviction: '70',
  bttsYes: '58', bttsNo: '42', bttsConviction: '65',
  over25: '54', under25: '46', totalsConviction: '60',
};
/** The edit made on My Predictions: BTTS only, plus the reasoning. */
const EDITED = { bttsYes: '45', bttsNo: '55' };

/* --------------------------------------------------------------------------- shared state */

let api: APIRequestContext;
let token: string;
let liveStackHits: string[] = [];
/** `METHOD /path` of every non-GET API request the expert's browser sent, in order. */
const expertWrites: string[] = [];
/** The same for the anonymous browser, which must send none. */
const anonymousWrites: string[] = [];
/** Paths of anonymous-browser API requests that carried an Authorization header (must be none). */
const anonymousAuthorised: string[] = [];
const dialogs: string[] = [];
/** The QA expert's first name before the journey, read from the profile form. */
let originalFirstName: string | null = null;

const auth = () => ({ headers: { Authorization: `Bearer ${token}` } });
const say = (template: string, params: Record<string, string> = {}): string =>
  template.replace(/\{(\w+)\}/g, (whole, key: string) => (key in params ? params[key] : whole));
const escapeRe = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const normalise = (text: string): string => text.replace(/\s+/g, ' ').trim();
const log = (line: string): void => console.log(`[expert-journey] ${line}`);
const observe = (line: string): void => {
  test.info().annotations.push({ type: 'observed', description: line });
  log(`observed: ${line}`);
};

async function guardLiveStack(context: BrowserContext): Promise<void> {
  await context.route(LIVE_STACK, route => {
    liveStackHits.push(`${route.request().method()} ${route.request().url()}`);
    return route.abort('blockedbyclient');
  });
}

const apiPath = (request: Request): string | null => {
  const url = new URL(request.url());
  return url.pathname.startsWith('/api/v1/') ? url.pathname : null;
};
const isWrite = (request: Request): boolean => !['GET', 'HEAD', 'OPTIONS'].includes(request.method());
const is = (method: string, path: string | RegExp) => (request: Request): boolean => {
  if (request.method() !== method) return false;
  const pathname = apiPath(request);
  return pathname !== null && (typeof path === 'string' ? pathname === path : path.test(pathname));
};
const isLogin = is('POST', '/api/v1/auth/login');
const isProfilePut = is('PUT', '/api/v1/users/me');
const isCreate = is('POST', '/api/v1/expert/predictions/manual');

/** Whether a request matching `predicate` leaves the page within the window. */
const sentWithin = (page: Page, predicate: (request: Request) => boolean, windowMs = ABSENCE_WINDOW_MS): Promise<boolean> =>
  page.waitForRequest(predicate, { timeout: windowMs }).then(() => true, () => false);

/** Whether this browser holds each token, as [access, refresh]. The tokens themselves never leave the page. */
const holdsTokens = (page: Page): Promise<boolean[]> =>
  page.evaluate(([a, r]) => [window.localStorage.getItem(a) !== null, window.localStorage.getItem(r) !== null],
    [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY]);

/** A full-page picture for the evidence folder, refused if the QA email is in the page's text. */
async function shot(page: Page, name: string): Promise<void> {
  const text = await page.locator('body').innerText();
  expect(text.includes(QA_EXPERT.email), `${name}: the QA account's email is on the page`).toBe(false);
  if (!EVIDENCE) return;
  mkdirSync(EVIDENCE, { recursive: true });
  // From the top: a full-page capture taken while scrolled draws the sticky header over the page
  // at the scroll offset, on top of whatever the step is about.
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(150);
  await page.screenshot({
    path: join(EVIDENCE, `${name}.jpg`),
    fullPage: true,
    type: 'jpeg',
    quality: 70,
    animations: 'disabled',
    mask: [page.locator('input[type="email"]')],
  });
}

/** A legible close-up of one region beside the full page, for a step whose subject is small on it. */
async function closeUp(region: Locator, name: string): Promise<void> {
  if (!EVIDENCE) return;
  mkdirSync(EVIDENCE, { recursive: true });
  // Cut from a full-page capture taken at the top, for the same reason as shot(): an element
  // screenshot scrolls to the element and the sticky header is drawn across it.
  const page = region.page();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(150);
  const box = await region.boundingBox();
  expect(box, `${name}: the region is on the page`).not.toBeNull();
  await page.screenshot({
    path: join(EVIDENCE, `${name}.jpg`), fullPage: true, clip: box as NonNullable<typeof box>,
    type: 'jpeg', quality: 80, animations: 'disabled', mask: [page.locator('input[type="email"]')],
  });
}

/* --------------------------------------------------------------------------- UI pieces */

const signInButton = (page: Page) => page.getByRole('button', { name: authEn['auth.login.submit'], exact: true });
const accountMenuButton = (page: Page) => page.locator('header button[aria-haspopup]').last();
const profileFields = (page: Page) => ({
  username: page.getByPlaceholder(authEn['auth.profile.usernamePlaceholder'], { exact: true }),
  firstName: page.getByPlaceholder(authEn['auth.profile.firstNamePlaceholder'], { exact: true }),
  lastName: page.getByPlaceholder(authEn['auth.profile.lastNamePlaceholder'], { exact: true }),
});
const composer = (page: Page, id: string) => page.locator(`#composer-${id}`);
const myCards = (page: Page) => page.locator('div.space-y-4 > div');
const ourCard = (page: Page) => myCards(page).filter({ hasText: CARD_LABEL });

/** Header menu -> Profile Settings. The menu is closed again by the navigation, before any picture. */
async function openProfileThroughTheMenu(page: Page): Promise<void> {
  await accountMenuButton(page).click();
  await page.getByRole('menuitem', { name: coreEn['nav.profileSettings'] }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await expect(page.getByRole('menu')).toHaveCount(0);
  await expect(profileFields(page).username).not.toHaveValue('');
}

/** Profile form: Edit, set the first name, Save. Asserts one PUT, its body, and the header. */
async function saveFirstName(page: Page, firstName: string, lastName: string): Promise<void> {
  const fields = profileFields(page);
  const putsBefore = expertWrites.filter(write => write === 'PUT /api/v1/users/me').length;
  await page.getByRole('button', { name: authEn['auth.profile.edit'], exact: true }).click();
  await expect(fields.firstName).toBeEnabled();
  await fields.firstName.fill(firstName);
  const put = page.waitForRequest(isProfilePut);
  await page.getByRole('button', { name: authEn['auth.profile.save'], exact: true }).click();
  const request = await put;
  expect((await request.response())?.status(), 'the profile PUT is accepted').toBe(200);
  expect(await sentWithin(page, isProfilePut), 'one Save, one PUT').toBe(false);
  expect(expertWrites.filter(write => write === 'PUT /api/v1/users/me').length - putsBefore, 'exactly one PUT').toBe(1);
  // Only the first name was edited: the username is not sent, the other fields go back as they were.
  expect(request.postDataJSON()).toEqual({ first_name: firstName, last_name: lastName, avatar_url: null });
  await expect(fields.firstName).toBeDisabled();
  await expect(fields.firstName).toHaveValue(firstName);
  await expect(page.getByText(authEn['auth.profile.saved'], { exact: true })).toBeVisible();
  // The header follows without a reload.
  await expect(accountMenuButton(page)).toContainText(firstName);
}

/** The public match page, loaded: the match payload answered and the page went quiet. */
async function openPublicMatch(page: Page, path: string, how: 'goto' | 'reload'): Promise<void> {
  const matchId = path.split('/').pop() as string;
  const loaded = page.waitForResponse(response =>
    response.request().method() === 'GET' && new URL(response.url()).pathname === `/api/v1/matches/${matchId}`);
  if (how === 'goto') await page.goto(path);
  else await page.reload();
  expect((await loaded).status(), 'GET the public match').toBe(200);
  await expect(page.getByTestId('match-scoreline')).toBeVisible();
  await page.waitForLoadState('networkidle');
}

/** Our expert block on the public card: the byline by username, and the block that holds it. */
const publicByline = (page: Page, username: string) =>
  page.getByTestId('expert-byline').filter({ hasText: say(readerEn['reader.expert.byline'], { name: username }) });
const publicBlock = (page: Page, username: string) => publicByline(page, username).locator('xpath=..');

/* --------------------------------------------------------------------------- setup */

test.beforeAll(async () => {
  api = await isolatedApiContext();
  token = await ensureQaExpertToken(api);
  const removed = await cleanupQaPredictions(api, token);
  log(`before: removed ${removed} QA prediction(s) left by earlier runs`);
  // A run that died between the two profile saves left the journey's name behind: put the
  // canonical one back first, so the name the journey reads as "original" really is.
  const me = await (await api.get('/api/v1/users/me', auth())).json();
  if (me.first_name === JOURNEY_FIRST_NAME) {
    const reset = await api.put('/api/v1/users/me', { ...auth(), data: { first_name: QA_EXPERT.first_name } });
    expect(reset.ok(), 'reset a first name a failed run left behind').toBe(true);
    log('before: a failed run had left the first name changed; reset through the API');
  }
});

test.afterAll(async () => {
  if (api && token) {
    const removed = await cleanupQaPredictions(api, token);
    log(`after: cleanup removed ${removed} QA prediction(s)`);
    if (originalFirstName !== null) {
      const me = await (await api.get('/api/v1/users/me', auth())).json();
      if (me.first_name !== originalFirstName) {
        // Only reached when the journey failed before its own restore through the UI.
        await api.put('/api/v1/users/me', { ...auth(), data: { first_name: originalFirstName } });
        log('after: SAFETY NET - the UI restore did not run, the first name was put back through the API');
      }
    }
  }
  await api?.dispose();
});

test.afterEach(() => {
  expect(liveStackHits, 'nothing may reach the live stack (:8000 or :3100)').toEqual([]);
});

/* --------------------------------------------------------------------------- the journey */

test('the owner journey: sign in, profile, compose, publish, read anonymously, edit, unpublish, publish, delete', async ({ page, context, browser }) => {
  test.setTimeout(300_000);
  liveStackHits = [];
  await guardLiveStack(context);
  context.on('request', request => {
    const path = apiPath(request);
    if (path && isWrite(request)) expertWrites.push(`${request.method()} ${path}`);
  });
  page.on('dialog', dialog => {
    dialogs.push(dialog.message());
    void dialog.accept();
  });

  // The anonymous reader: a separate context, never signed in, guarded the same way.
  const anonymous = await browser.newContext({
    baseURL: ISOLATED_BASE, viewport: { width: 1440, height: 900 }, timezoneId: 'America/New_York', locale: 'en-US',
  });
  await guardExternalAssets(anonymous, 'real');
  await guardLiveStack(anonymous);
  anonymous.on('request', request => {
    const path = apiPath(request);
    if (!path) return;
    if (isWrite(request)) anonymousWrites.push(`${request.method()} ${path}`);
    if (request.headers().authorization !== undefined) anonymousAuthorised.push(path);
  });
  const reader = await anonymous.newPage();

  let username = '';
  let matchId = '';
  let matchPath = '';
  let homeTeam = '';
  let awayTeam = '';
  let predictionId = '';
  let publishedAt = '';
  let firstByline = '';

  try {
    /* ------------------------------------------------------------------ 1. sign in */
    await test.step('1. sign in through the form, a wrong password first', async () => {
      await page.goto('/login');
      await page.locator('#email').fill(QA_EXPERT.email);
      await page.locator('#password').fill(WRONG_PASSWORD);
      const refused = page.waitForResponse(response => isLogin(response.request()));
      await signInButton(page).click();
      expect((await refused).status(), 'a wrong password is refused').toBe(401);
      await expect(page.getByText('Incorrect email or password', { exact: true })).toBeVisible();
      await expect(page).toHaveURL(/\/login$/);
      expect(await holdsTokens(page), 'a refused sign-in stores no session').toEqual([false, false]);
      await shot(page, '01-login-wrong-password-refused');

      await page.locator('#password').fill(QA_EXPERT.password);
      const accepted = page.waitForResponse(response => isLogin(response.request()));
      await signInButton(page).click();
      expect((await accepted).status(), 'the right password is accepted').toBe(200);
      await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 20_000 });
      await expect(page).toHaveURL(/\/expert\/dashboard$/);
      expect(await holdsTokens(page), 'signing in stores a session').toEqual([true, true]);
      await page.waitForLoadState('networkidle');
      await shot(page, '02-signed-in-expert-dashboard');
      log('1: a wrong password was refused (401) and the right one signed in (200), landing on /expert/dashboard');
    });

    /* ------------------------------------------------------------------ 2. profile */
    await test.step('2. edit the first name through the profile form', async () => {
      await openProfileThroughTheMenu(page);
      const fields = profileFields(page);
      username = await fields.username.inputValue();
      originalFirstName = await fields.firstName.inputValue();
      const lastName = await fields.lastName.inputValue();
      expect(username, 'the profile shows a username').not.toBe('');
      expect(originalFirstName, 'the QA expert has a first name to change').not.toBe('');
      expect(originalFirstName).not.toBe(JOURNEY_FIRST_NAME);
      await expect(accountMenuButton(page)).toContainText(originalFirstName);

      await saveFirstName(page, JOURNEY_FIRST_NAME, lastName);
      const stored = await (await api.get('/api/v1/users/me', auth())).json();
      expect(stored.first_name, 'the backend stored the new first name').toBe(JOURNEY_FIRST_NAME);
      await shot(page, '03-profile-first-name-saved');
      log(`2: first name "${originalFirstName}" -> "${JOURNEY_FIRST_NAME}" with one PUT; header updated; username ${username}`);
    });

    /* ------------------------------------------------------------------ 3. match selection */
    await test.step('3. choose a stored fixture through match selection', async () => {
      await page.locator('header').getByRole('link', { name: coreEn['nav.expert'], exact: true }).click();
      await expect(page).toHaveURL(/\/expert\/dashboard$/);
      await page.getByRole('link', { name: new RegExp(`^${escapeRe(expertEn['expert.dashboard.chooseMatch'])}`) }).first().click();
      await expect(page).toHaveURL(/\/expert\/match-selection$/);
      // The route is loaded lazily: wait for the picker itself before counting anything on it.
      await expect(page.getByRole('heading', { level: 1, name: expertEn['expert.dashboard.chooseMatch'] })).toBeVisible();
      await expect(page.getByTestId('picker-day-shown')).toBeVisible();
      await page.waitForLoadState('networkidle');

      const rows = page.getByRole('button', { name: new RegExp(`^${escapeRe(expertEn['expert.action.writePrediction'])}:`) });
      let chosen: Locator | null = null;
      for (const day of [/^today$/i, /^tomorrow$/i, /^in two days$/i]) {
        const chip = page.getByRole('button', { name: day }).first();
        if (await chip.count() === 0) continue;
        await chip.click();
        await page.waitForLoadState('networkidle');
        await expect(page.getByText(expertEn['expert.picker.loading'])).toHaveCount(0);
        // Not kicked off (a prediction published then is never scored), and preferably one that
        // no expert has published on yet, so the public card is about this journey alone.
        const open = rows.filter({ hasNot: page.getByTestId('picker-kicked-off') });
        const untouched = open.filter({ hasNotText: expertEn['expert.picker.expertPublished'] });
        if (await untouched.count() > 0) { chosen = untouched.first(); break; }
        if (await open.count() > 0) { chosen = open.first(); break; }
      }
      test.skip(!chosen, 'the isolated database has no fixture that has not kicked off in the three days match selection offers');
      const row = chosen as Locator;
      log(`3: chose "${await row.getAttribute('aria-label')}"`);
      await shot(page, '04-match-selection');

      await row.click();
      await expect(page).toHaveURL(/\/expert\/predictions\/create\?matchId=/);
      await expect(composer(page, 'home')).toBeVisible();
      await page.waitForLoadState('networkidle');
      matchId = new URL(page.url()).searchParams.get('matchId') ?? '';
      expect(matchId, 'match selection opened the composer on a fixture').not.toBe('');
      const fixtureLabel = normalise(await page.getByTestId('composer-fixture-line').locator('span').first().innerText());
      [homeTeam, awayTeam] = fixtureLabel.split(' v ');
      expect(say(expertEn['expert.fixtureShort'], { home: homeTeam, away: awayTeam }), 'the fixture line names both clubs')
        .toBe(fixtureLabel);
      await expect(page.getByTestId('composer-kickoff-warning')).toHaveCount(0);
    });

    /* ------------------------------------------------------------------ 14a. a figure that cannot be published */
    await test.step('14a. invalid percentages are blocked before any request', async () => {
      await composer(page, 'home').fill('60');
      await composer(page, 'draw').fill('30');
      await composer(page, 'away').fill('30');
      await composer(page, 'conviction').fill('seventy');
      const create = sentWithin(page, isCreate);
      await page.getByRole('button', { name: expertEn['expert.action.publish'], exact: true }).click();
      expect(await create, `an invalid form sends no create request (watched ${ABSENCE_WINDOW_MS} ms)`).toBe(false);
      await expect(page.getByText(expertEn['expert.compose.fixThenPreview'], { exact: true })).toBeVisible();
      await expect(page.getByText(/120(\.0+)?% total/)).toBeVisible();
      await expect(page.getByText(say(expertEn['expert.validation.notANumber'], { example: '55' }), { exact: true })).toBeVisible();
      await expect(composer(page, 'conviction')).toHaveAttribute('aria-invalid', 'true');
      await shot(page, '05-composer-invalid-percentages-blocked');
      log('14a: 60/30/30 and a conviction of "seventy" were refused on the form; no create request was sent');
    });

    /* ------------------------------------------------------------------ 4. draft, reload */
    await test.step('4. type a draft, reload, see it restored', async () => {
      await composer(page, 'home').fill(TYPED.home);
      await composer(page, 'draw').fill(TYPED.draw);
      await composer(page, 'away').fill(TYPED.away);
      await composer(page, 'conviction').fill(TYPED.conviction);
      await composer(page, 'btts-enabled').check();
      await composer(page, 'btts-yes').fill(TYPED.bttsYes);
      await composer(page, 'btts-no').fill(TYPED.bttsNo);
      await composer(page, 'btts-conviction').fill(TYPED.bttsConviction);
      await composer(page, 'over25-enabled').check();
      await composer(page, 'over25').fill(TYPED.over25);
      await composer(page, 'under25').fill(TYPED.under25);
      await composer(page, 'totals-conviction').fill(TYPED.totalsConviction);
      await composer(page, 'reasoning').fill(REASONING_FIRST);
      await expect(page.getByText(expertEn['expert.compose.fixThenPreview'], { exact: true })).toHaveCount(0);
      // The draft is in this browser's storage before the reload (it is never sent anywhere).
      await expect.poll(() => page.evaluate(text => Object.keys(window.localStorage)
        .filter(key => key.startsWith('expert.composer.draft'))
        .some(key => (window.localStorage.getItem(key) ?? '').includes(text)), REASONING_FIRST)).toBe(true);

      await page.reload();
      await expect(composer(page, 'home')).toBeVisible();
      await page.waitForLoadState('networkidle');
      await expect(page.getByText(/^Draft restored/)).toBeVisible();
      await expect(composer(page, 'home')).toHaveValue(TYPED.home);
      await expect(composer(page, 'draw')).toHaveValue(TYPED.draw);
      await expect(composer(page, 'away')).toHaveValue(TYPED.away);
      await expect(composer(page, 'conviction')).toHaveValue(TYPED.conviction);
      await expect(composer(page, 'btts-enabled')).toBeChecked();
      await expect(composer(page, 'btts-yes')).toHaveValue(TYPED.bttsYes);
      await expect(composer(page, 'btts-no')).toHaveValue(TYPED.bttsNo);
      await expect(composer(page, 'btts-conviction')).toHaveValue(TYPED.bttsConviction);
      await expect(composer(page, 'over25-enabled')).toBeChecked();
      await expect(composer(page, 'over25')).toHaveValue(TYPED.over25);
      await expect(composer(page, 'under25')).toHaveValue(TYPED.under25);
      await expect(composer(page, 'totals-conviction')).toHaveValue(TYPED.totalsConviction);
      await expect(composer(page, 'over35-enabled')).not.toBeChecked();
      await expect(composer(page, 'reasoning')).toHaveValue(REASONING_FIRST);
      expect(expertWrites.filter(write => write.includes('/expert/')), 'a draft sends nothing').toEqual([]);
      await shot(page, '06-draft-restored-after-reload');
      log('4: the typed draft (1X2, conviction, BTTS, over/under 2.5, reasoning) came back whole after a reload');
    });

    /* ------------------------------------------------------------------ 5. preview */
    await test.step('5. the preview shows what was typed', async () => {
      await page.getByRole('button', { name: expertEn['expert.action.preview'], exact: true }).click();
      const preview = page.getByRole('region', { name: expertEn['expert.preview.regionLabel'] });
      await expect(preview).toBeVisible();
      const text = normalise(await preview.innerText());
      const expected = [
        say(expertEn['expert.fixtureShort'], { home: homeTeam, away: awayTeam }),
        `${say(expertEn['expert.editor.teamWin'], { team: homeTeam })} ${TYPED.home}%`,
        `${coreEn['outcome.draw']} ${TYPED.draw}%`,
        `${say(expertEn['expert.editor.teamWin'], { team: awayTeam })} ${TYPED.away}%`,
        say(expertEn['expert.preview.convictionStated'], { value: `${TYPED.conviction}%` }),
        `${expertEn['expert.editor.bttsYes']} ${TYPED.bttsYes}%`,
        `${expertEn['expert.editor.bttsNo']} ${TYPED.bttsNo}%`,
        `${say(expertEn['expert.editor.overGoals'], { line: '2.5' })} ${TYPED.over25}%`,
        `${say(expertEn['expert.editor.underGoals'], { line: '2.5' })} ${TYPED.under25}%`,
        say(expertEn['expert.preview.notPublished'], {
          market: say(expertEn['expert.editor.overUnderGoals'], { line: '3.5' }), zero: '0%',
        }),
        REASONING_FIRST,
      ];
      for (const line of expected) expect(text, `the preview shows "${line}"`).toContain(line);
      expect(text).not.toContain(expertEn['expert.preview.needsAttention']);
      // Reported, not asserted: the two market convictions are typed and published, but the
      // preview has no line for either.
      for (const [what, value] of [['BTTS conviction', TYPED.bttsConviction], ['goal-line conviction', TYPED.totalsConviction]]) {
        if (!text.includes(`${value}%`)) observe(`the preview does not show the ${what} typed in the composer (${value}%)`);
      }
      await shot(page, '07-preview');
      await closeUp(preview, '07b-preview-close-up');
      log('5: the preview shows the fixture, 1X2, the conviction, BTTS, over/under 2.5, 3.5 as not published, and the reasoning');
    });

    /* ------------------------------------------------------------------ 6. publish */
    await test.step('6. publish: exactly one create request, then the confirmation', async () => {
      const created = page.waitForResponse(response => isCreate(response.request()));
      await page.getByRole('button', { name: expertEn['expert.action.publish'], exact: true }).click();
      const response = await created;
      expect(response.status(), 'the create request is accepted').toBeLessThan(300);
      const body = await response.json();
      predictionId = String(body.id);
      expect(predictionId).toMatch(/^[0-9a-f-]{36}$/);
      expect(String(body.status).toLowerCase(), 'published directly, no approval step').toBe('published');

      await expect(page.getByRole('heading', { level: 1, name: expertEn['expert.published.title'] })).toBeVisible();
      await expect(page.getByText(expertEn['expert.published.body'], { exact: true })).toBeVisible();
      expect(await sentWithin(page, isCreate), 'one Publish, one create request').toBe(false);
      expect(expertWrites.filter(write => write === 'POST /api/v1/expert/predictions/manual'), 'exactly one create request')
        .toHaveLength(1);

      // Classified as test data straight away, through the supported endpoint and the id the
      // composer's own response returned (the composer has no such control, and must not).
      const classified = await classifyQaPrediction(api, token, predictionId);
      log(`6: published ${predictionId}; classified as test data: ${classified}`);
      if (!classified) observe('the isolated backend refused the test-data classification (ALLOW_TEST_DATA_CLASSIFICATION off?)');

      // Second witness: what the API stored is what was typed, 55 -> 0.55 style.
      const rows = await (await api.get('/api/v1/expert/predictions/my-predictions?limit=100', auth())).json();
      const stored = (rows as Array<Record<string, unknown>>).find(row => row.id === predictionId);
      expect(stored, 'the published prediction is in the expert\'s list').toBeTruthy();
      const row = stored as Record<string, unknown>;
      expect(Number(row.home_win_prob)).toBeCloseTo(0.52, 4);
      expect(Number(row.draw_prob)).toBeCloseTo(0.27, 4);
      expect(Number(row.away_win_prob)).toBeCloseTo(0.21, 4);
      expect(Number(row.confidence_score)).toBeCloseTo(0.7, 4);
      expect(Number(row.btts_yes_prob)).toBeCloseTo(0.58, 4);
      expect(Number(row.btts_no_prob)).toBeCloseTo(0.42, 4);
      expect(Number(row.btts_confidence)).toBeCloseTo(0.65, 4);
      expect(Number(row.total_goals_over_25_prob)).toBeCloseTo(0.54, 4);
      expect(Number(row.total_goals_under_25_prob)).toBeCloseTo(0.46, 4);
      expect(Number(row.total_goals_confidence)).toBeCloseTo(0.6, 4);
      expect(row.total_goals_over_35_prob ?? null, 'a market left out is not stored as zero').toBeNull();
      expect(row.reasoning).toBe(REASONING_FIRST);
      if (classified) expect(row.is_test_data).toBe(true);
      publishedAt = String(row.published_at);
      expect(publishedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);

      matchPath = (await page.getByRole('link', { name: expertEn['expert.published.viewMatch'] }).getAttribute('href')) ?? '';
      expect(matchPath).toBe(`/match/${matchId}`);
      await shot(page, '08-published-confirmation');
    });

    /* ------------------------------------------------------------------ 7. anonymous reader */
    const expectPublicCard = async (reasoning: string, btts: { yes: string; no: string }) => {
      const block = publicBlock(reader, username);
      await expect(block).toHaveCount(1);
      const text = normalise(await block.innerText());
      for (const line of [
        `Home ${TYPED.home}%`, `Draw ${TYPED.draw}%`, `Away ${TYPED.away}%`,
        `(Yes ${btts.yes}% / No ${btts.no}%)`,
        `(Over 2.5 ${TYPED.over25}% / Under 2.5 ${TYPED.under25}%)`,
        reasoning,
      ]) expect(text, `the public card shows "${line}"`).toContain(line);
      const byline = normalise(await publicByline(reader, username).innerText());
      expect(byline).toMatch(new RegExp(`^${escapeRe(say(readerEn['reader.expert.byline'], { name: username }))} · published `));
      const body = await reader.locator('body').innerText();
      expect(body.includes(QA_EXPERT.email), 'the author\'s email is on the public page').toBe(false);
      expect(body, 'the raw source enum is on the public page').not.toContain('expert_manual');
      expect(await holdsTokens(reader), 'the reader is anonymous').toEqual([false, false]);
      return byline;
    };

    await test.step('7. a separate anonymous browser sees it on the public match page, with the byline', async () => {
      await openPublicMatch(reader, matchPath, 'goto');
      firstByline = await expectPublicCard(REASONING_FIRST, { yes: TYPED.bttsYes, no: TYPED.bttsNo });
      await expect(reader.getByRole('link', { name: coreEn['nav.signIn'] }).first()).toBeVisible();
      // Not edited yet: no earlier version is listed for it.
      await expect(reader.locator(`[data-testid="expert-revision-group"][data-prediction-id="${predictionId}"]`)).toHaveCount(0);
      await shot(reader, '09-public-match-anonymous');
      await closeUp(reader.getByTestId('expert-predictions'), '09b-public-expert-panel-close-up');
      log(`7: the anonymous reader sees the prediction, byline "${firstByline}"`);
    });

    await test.step('8. reloaded, it is still there', async () => {
      await openPublicMatch(reader, matchPath, 'reload');
      const byline = await expectPublicCard(REASONING_FIRST, { yes: TYPED.bttsYes, no: TYPED.bttsNo });
      expect(byline, 'a reload reads the same byline').toBe(firstByline);
      await shot(reader, '10-public-match-anonymous-reloaded');
      log('8: after a reload the anonymous reader still sees it, same byline');
    });

    /* ------------------------------------------------------------------ 9. edit on My Predictions */
    await test.step('9. edit BTTS and the reasoning through My Predictions', async () => {
      await page.getByTestId('expert-composer').getByRole('link', { name: expertEn['expert.dashboard.myPredictions'], exact: true }).click();
      await expect(page).toHaveURL(/\/expert\/predictions\/my-predictions$/);
      await expect(page.getByRole('heading', { level: 1, name: expertEn['expert.mine.title'] })).toBeVisible();
      await page.waitForLoadState('networkidle');
      const card = ourCard(page);
      await expect(card).toHaveCount(1);
      await card.getByRole('button', { name: expertEn['expert.action.edit'], exact: true }).click();
      const field = (id: string) => page.locator(`#edit-${predictionId}-${id}`);
      await expect(card.getByTestId('prediction-editor')).toBeVisible();
      // The stored figures reopen as the percentages that were typed.
      await expect(field('home')).toHaveValue(TYPED.home);
      await expect(field('btts-yes')).toHaveValue(TYPED.bttsYes);
      await expect(field('btts-no')).toHaveValue(TYPED.bttsNo);
      await expect(field('reasoning')).toHaveValue(REASONING_FIRST);

      await field('btts-yes').fill(EDITED.bttsYes);
      await field('btts-no').fill(EDITED.bttsNo);
      await field('reasoning').fill(REASONING_EDITED);
      await shot(page, '11-my-predictions-editing');

      const isUpdate = is('PUT', `/api/v1/expert/predictions/${predictionId}`);
      const put = page.waitForRequest(isUpdate);
      await card.getByRole('button', { name: expertEn['expert.action.saveChanges'], exact: true }).click();
      const request = await put;
      expect((await request.response())?.status(), 'the edit is accepted').toBe(200);
      expect(await sentWithin(page, isUpdate), 'one Save, one PUT').toBe(false);
      const sent = request.postDataJSON();
      expect(Number(sent.btts_yes_prob)).toBeCloseTo(0.45, 4);
      expect(Number(sent.btts_no_prob)).toBeCloseTo(0.55, 4);
      expect(Number(sent.home_win_prob)).toBeCloseTo(0.52, 4);
      expect(sent.reasoning).toBe(REASONING_EDITED);

      await expect(card.getByTestId('prediction-editor')).toHaveCount(0);
      const shown = normalise(await card.innerText());
      expect(shown).toContain(REASONING_EDITED);
      expect(shown).toContain(`${expertEn['expert.mine.yes']} ${EDITED.bttsYes}.0%`);
      expect(shown).toContain(`${expertEn['expert.mine.no']} ${EDITED.bttsNo}.0%`);
      await shot(page, '12-my-predictions-edited');

      const rows = await (await api.get('/api/v1/expert/predictions/my-predictions?limit=100', auth())).json();
      const stored = (rows as Array<Record<string, unknown>>).find(row => row.id === predictionId) as Record<string, unknown>;
      expect(Number(stored.btts_yes_prob)).toBeCloseTo(0.45, 4);
      expect(String(stored.status).toLowerCase(), 'an edit keeps it published').toBe('published');
      expect(stored.published_at, 'an edit does not move the publication time').toBe(publishedAt);
      log('9: BTTS 58/42 -> 45/55 and the reasoning rewritten through My Predictions, one PUT, still published');
    });

    /* ------------------------------------------------------------------ 10. revision history */
    await test.step('10. the public page shows the earlier version, every market of it, and what changed', async () => {
      await openPublicMatch(reader, matchPath, 'reload');
      await expectPublicCard(REASONING_EDITED, { yes: EDITED.bttsYes, no: EDITED.bttsNo });

      const group = reader.locator(`[data-testid="expert-revision-group"][data-prediction-id="${predictionId}"]`);
      await expect(group).toHaveCount(1);
      await expect(group).toContainText(say(readerEn['reader.revisions.byAuthor'], { name: username }));
      const item = group.getByTestId('expert-revision');
      await expect(item).toHaveCount(1);
      await expect(item).toContainText(`${say(readerEn['reader.revisions.version'], { number: '1' })}${readerEn['reader.revisions.asFirstPublished']}`);

      // Every market the first version had, figure by figure, as it was typed.
      const cells: Array<[string, string]> = [
        ['home_win_prob', TYPED.home], ['draw_prob', TYPED.draw], ['away_win_prob', TYPED.away],
        ['confidence_score', TYPED.conviction],
        ['btts_yes_prob', TYPED.bttsYes], ['btts_no_prob', TYPED.bttsNo], ['btts_confidence', TYPED.bttsConviction],
        ['total_goals_over_25_prob', TYPED.over25], ['total_goals_under_25_prob', TYPED.under25],
        ['total_goals_confidence', TYPED.totalsConviction],
      ];
      for (const [field, value] of cells) {
        const cell = item.locator(`[data-testid="revision-value"][data-field="${field}"]`);
        await expect(cell, `${field} has one cell in the earlier version`).toHaveCount(1);
        await expect(cell, `${field} shows ${value}%`).toContainText(`${value}%`);
      }
      // The market it left out is said to be left out, never shown as 0%.
      await expect(item.locator('[data-testid="revision-market"][data-market="ou35"]')).toContainText(coreEn['missing.marketNotSupplied']);
      await expect(item.locator('[data-testid="revision-value"][data-field="total_goals_over_35_prob"]')).toHaveCount(0);
      // The words it was first published with.
      await expect(item).toContainText(REASONING_FIRST);

      // What changed, as sentences, never as column names.
      const changes = (await item.getByTestId('revision-change').allInnerTexts()).map(normalise).sort();
      expect(changes).toEqual([
        `${coreEn['market.btts']} – ${readerEn['selections.outcome.no']}: ${TYPED.bttsNo}% → ${EDITED.bttsNo}%`,
        `${coreEn['market.btts']} – ${readerEn['selections.outcome.yes']}: ${TYPED.bttsYes}% → ${EDITED.bttsYes}%`,
        readerEn['reader.revisions.change.reasoning'],
      ].sort());
      const history = normalise(await reader.getByTestId('expert-revisions').innerText());
      expect(history, 'a column name reached the page').not.toMatch(/btts_yes_prob|_prob\b|->/);

      // Second witness: the served revision is the first version, exactly.
      const detail = await (await api.get(`/api/v1/matches/${matchId}`)).json();
      const served = (detail.expert_prediction_revisions as Array<Record<string, unknown>>)
        .filter(revision => revision.prediction_id === predictionId);
      expect(served, 'one edit, one earlier version').toHaveLength(1);
      const values = served[0].values as Record<string, unknown>;
      expect(Number(values.btts_yes_prob)).toBeCloseTo(0.58, 4);
      expect(values.reasoning).toBe(REASONING_FIRST);

      await shot(reader, '13-public-revision-history');
      await closeUp(reader.getByTestId('expert-predictions'), '13b-public-revision-history-close-up');
      log(`10: version 1 shows ${cells.length} figures, 3.5 as left out, the first reasoning; changes: ${changes.join(' | ')}`);
    });

    /* ------------------------------------------------------------------ 11. unpublish */
    await test.step('11. unpublish from My Predictions; the anonymous reader no longer sees it', async () => {
      const card = ourCard(page);
      const toggle = is('POST', `/api/v1/expert/predictions/${predictionId}/toggle-publish`);
      const sent = page.waitForResponse(response => toggle(response.request()));
      await card.getByRole('button', { name: expertEn['expert.action.unpublish'], exact: true }).click();
      expect((await sent).status()).toBe(200);
      expect(dialogs[dialogs.length - 1], 'the unpublish asked first').toBe(expertEn['expert.publication.confirmUnpublish']);
      await expect(card.getByRole('button', { name: expertEn['expert.action.publish'], exact: true })).toBeVisible();
      await page.waitForLoadState('networkidle');
      await shot(page, '14-my-predictions-unpublished');

      await openPublicMatch(reader, matchPath, 'reload');
      await expect(publicByline(reader, username)).toHaveCount(0);
      await expect(reader.locator('body')).not.toContainText(CARD_LABEL);
      await expect(reader.locator(`[data-testid="expert-revision-group"][data-prediction-id="${predictionId}"]`)).toHaveCount(0);
      await shot(reader, '15-public-after-unpublish');

      const detail = await (await api.get(`/api/v1/matches/${matchId}`)).json();
      expect((detail.expert_predictions as Array<{ id: string }>).map(row => row.id)).not.toContain(predictionId);
      expect(detail.expert_prediction?.id ?? null).not.toBe(predictionId);
      log('11: unpublished after a confirmation; the anonymous reader no longer sees it, nor its earlier version');
    });

    /* ------------------------------------------------------------------ 12. publish again */
    await test.step('12. publish again; the anonymous reader sees it with the original publication time', async () => {
      const card = ourCard(page);
      const toggle = is('POST', `/api/v1/expert/predictions/${predictionId}/toggle-publish`);
      const sent = page.waitForResponse(response => toggle(response.request()));
      await card.getByRole('button', { name: expertEn['expert.action.publish'], exact: true }).click();
      expect((await sent).status()).toBe(200);
      expect(dialogs[dialogs.length - 1], 'the publish asked first').toBe(expertEn['expert.publication.confirmPublish']);
      await expect(card.getByRole('button', { name: expertEn['expert.action.unpublish'], exact: true })).toBeVisible();

      await openPublicMatch(reader, matchPath, 'reload');
      const byline = await expectPublicCard(REASONING_EDITED, { yes: EDITED.bttsYes, no: EDITED.bttsNo });
      expect(byline, 'the byline carries the ORIGINAL publication time').toBe(firstByline);
      await expect(reader.locator(`[data-testid="expert-revision-group"][data-prediction-id="${predictionId}"]`)).toHaveCount(1);
      await shot(reader, '16-public-after-republish');
      await closeUp(reader.getByTestId('expert-predictions'), '16b-public-after-republish-close-up');

      const rows = await (await api.get('/api/v1/expert/predictions/my-predictions?limit=100', auth())).json();
      const stored = (rows as Array<Record<string, unknown>>).find(row => row.id === predictionId) as Record<string, unknown>;
      expect(String(stored.status).toLowerCase()).toBe('published');
      expect(stored.published_at, 'published_at is the first publication, not the republish').toBe(publishedAt);
      log(`12: published again; byline unchanged ("${byline}"), published_at unchanged (${publishedAt})`);
    });

    /* ------------------------------------------------------------------ 13. delete */
    await test.step('13. delete from My Predictions; gone for the reader and from the list; a repeated DELETE keeps deleted_at', async () => {
      const card = ourCard(page);
      const isDelete = is('DELETE', `/api/v1/expert/predictions/${predictionId}`);
      const sent = page.waitForResponse(response => isDelete(response.request()));
      await card.getByRole('button', { name: expertEn['expert.action.delete'], exact: true }).click();
      const response = await sent;
      expect(response.status()).toBe(200);
      const first = await response.json();
      expect(dialogs[dialogs.length - 1], 'the delete asked first').toBe(expertEn['expert.mine.confirmDelete']);
      expect(first.already_deleted, 'the UI\'s DELETE is the one that deleted').toBe(false);
      expect(first.deleted_at).toMatch(/^\d{4}-\d{2}-\d{2}T.*Z$/);
      expect(await sentWithin(page, isDelete), 'one Delete, one DELETE').toBe(false);

      await expect(ourCard(page)).toHaveCount(0);
      await page.waitForLoadState('networkidle');
      await expect(page.locator('body')).not.toContainText(CARD_LABEL);
      // The heading counts what the backend counts; with nothing left, the list says so.
      const left = Number((await api.get('/api/v1/expert/predictions/my-predictions?limit=1', auth())).headers()['x-total-count']);
      await expect(page.locator('h2').filter({ hasText: /^Your Predictions/ }))
        .toHaveText(say(expertEn['expert.mine.listHeading'], { count: String(left) }));
      if (left === 0) await expect(page.getByText(expertEn['expert.mine.emptyNone'], { exact: true })).toBeVisible();
      await shot(page, '17-my-predictions-after-delete');

      await openPublicMatch(reader, matchPath, 'reload');
      await expect(publicByline(reader, username)).toHaveCount(0);
      await expect(reader.locator('body')).not.toContainText(CARD_LABEL);
      await shot(reader, '18-public-after-delete');

      // The second DELETE no control can send: through :8001, it changes nothing.
      const repeat = await api.delete(`/api/v1/expert/predictions/${predictionId}`, auth());
      expect(repeat.status(), 'a repeated DELETE answers 200').toBe(200);
      const second = await repeat.json();
      expect(second.already_deleted, 'the repeat says it was already deleted').toBe(true);
      expect(second.deleted_at, 'the repeat reports the first deletion time, unmoved').toBe(first.deleted_at);
      const detail = await (await api.get(`/api/v1/matches/${matchId}`)).json();
      expect((detail.expert_predictions as Array<{ id: string }>).map(row => row.id)).not.toContain(predictionId);
      const rows = await (await api.get('/api/v1/expert/predictions/my-predictions?limit=100', auth())).json();
      expect((rows as Array<{ id: string }>).map(row => row.id)).not.toContain(predictionId);
      log(`13: deleted through the UI (deleted_at ${first.deleted_at}); a repeated DELETE said already_deleted with the same deleted_at`);
    });

    /* ------------------------------------------------------------------ 14b. an empty filter */
    await test.step('14b. a status filter with nothing in it says so', async () => {
      // Pick a status the QA expert has nothing in (read through the API), so the message is owed.
      let empty: string | null = null;
      for (const status of ['rejected', 'under_review', 'pending']) {
        const answer = await api.get(`/api/v1/expert/predictions/my-predictions?limit=1&status=${status}`, auth());
        if (Number(answer.headers()['x-total-count']) === 0) { empty = status; break; }
      }
      expect(empty, 'the QA expert holds predictions in every status this test can filter on').not.toBeNull();
      const label = { rejected: 'expert.status.rejected', under_review: 'expert.status.underReview', pending: 'expert.status.pending' }[
        empty as 'rejected' | 'under_review' | 'pending'] as keyof typeof expertEn;
      await page.locator('#status-filter').selectOption(empty as string);
      await page.waitForLoadState('networkidle');
      await expect(page.getByText(expertEn['expert.mine.emptyTitle'])).toBeVisible();
      await expect(page.getByText(say(expertEn['expert.mine.emptyFiltered'], { status: String(expertEn[label]) }), { exact: true })).toBeVisible();
      await expect(page.getByRole('link', { name: expertEn['expert.mine.createFirst'] })).toHaveCount(0);
      await shot(page, '19-my-predictions-empty-filter');
      log(`14b: the "${String(expertEn[label])}" filter shows "${expertEn['expert.mine.emptyTitle']}"`);
    });

    /* ------------------------------------------------------------------ 15. put the name back */
    await test.step('15. restore the first name through the profile form', async () => {
      await openProfileThroughTheMenu(page);
      const fields = profileFields(page);
      await expect(fields.firstName).toHaveValue(JOURNEY_FIRST_NAME);
      await saveFirstName(page, originalFirstName as string, await fields.lastName.inputValue());
      const stored = await (await api.get('/api/v1/users/me', auth())).json();
      expect(stored.first_name, 'the original first name is stored again').toBe(originalFirstName);
      await shot(page, '20-profile-first-name-restored');
      log(`15: first name restored to "${originalFirstName}" through the form, one PUT`);
    });

    /* ------------------------------------------------------------------ the whole journey */
    await test.step('every write the journey sent, in order, and none from the reader', async () => {
      expect(expertWrites).toEqual([
        'POST /api/v1/auth/login',
        'POST /api/v1/auth/login',
        'PUT /api/v1/users/me',
        'POST /api/v1/expert/predictions/manual',
        `PUT /api/v1/expert/predictions/${predictionId}`,
        `POST /api/v1/expert/predictions/${predictionId}/toggle-publish`,
        `POST /api/v1/expert/predictions/${predictionId}/toggle-publish`,
        `DELETE /api/v1/expert/predictions/${predictionId}`,
        'PUT /api/v1/users/me',
      ]);
      expect(dialogs).toEqual([
        expertEn['expert.publication.confirmUnpublish'],
        expertEn['expert.publication.confirmPublish'],
        expertEn['expert.mine.confirmDelete'],
      ]);
      expect(anonymousWrites, 'the anonymous reader wrote nothing').toEqual([]);
      expect(anonymousAuthorised, 'the anonymous reader sent no credentials').toEqual([]);
      expect(liveStackHits, 'nothing reached the live stack (:8000 or :3100)').toEqual([]);
      log(`writes: ${expertWrites.map(write => write.replace(predictionId, '{id}')).join(', ')}`);
    });
  } finally {
    await anonymous.close();
  }
});
