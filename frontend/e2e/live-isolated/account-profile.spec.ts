import { APIRequestContext, BrowserContext, Page, Request } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { ISOLATED_BASE, isolatedApiContext } from '../support/isolated';
import { guardExternalAssets } from '../support/external-assets';
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '../support/auth';
import authEn from '../../src/i18n/messages/auth.en';

/**
 * The profile and password forms against the real isolated backend (:8001, soccer_predictions_e2e).
 *
 * WHY LIVE AS WELL AS MOCKED. The mocked suite (e2e/mocked/account-forms.spec.ts) proves what the
 * forms SEND. Only the real backend can say what was STORED, that a reload reads it back, that the
 * old password really stops working, and what happens to a browser that was already signed in when
 * the password changed — which is the one claim on that page a stub cannot substantiate.
 *
 * A DEDICATED ACCOUNT, NOT QA_EXPERT. These tests rename an account and change its password; the
 * other isolated suites sign in as QA_EXPERT and would break if a run stopped halfway. This account
 * exists only on the isolated database, is registered here if missing, and is put back to its
 * canonical names and password before and after every test, including after a run that died
 * between changing the password and restoring it (restoreAccount tries both passwords).
 *
 * NOTHING HERE MAY REACH THE LIVE STACK. Every API call goes through isolatedApiContext, which
 * refuses :8000 and any backend serving the live database, and every browser context gets a route
 * that aborts, and fails the test on, any request to :8000 or :3100.
 *
 * ABSENCE IS A BOUNDED WINDOW, as in the mocked suite: ABSENCE_WINDOW_MS, armed before the action.
 */

const ACCOUNT = {
  email: 'qa.account-forms@predictions-local.dev',
  username: 'qa_account_forms',
  first_name: 'QA',
  last_name: 'Account',
  role: 'regular',
};
/**
 * LOCAL TEST FIXTURES, like QA_EXPERT's password in support/qa-account.ts: not secrets (this
 * repository is public), and the account they open exists only on the isolated database.
 */
const ORIGINAL_PASSWORD = 'local-only-account-forms-fixture';
const CHANGED_PASSWORD = 'local-only-account-forms-fixture-2';

const ABSENCE_WINDOW_MS = 1500;
const EXTRA_PUT_WINDOW_MS = 1000;
const BOUNCE_WINDOW_MS = 2500;

/** The live stack. Nothing in this file may reach it. */
const LIVE_STACK = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):(8000|3100)(\/|$)/;
let liveStackHits: string[] = [];

async function guardLiveStack(context: BrowserContext): Promise<void> {
  await context.route(LIVE_STACK, route => {
    liveStackHits.push(`${route.request().method()} ${route.request().url()}`);
    return route.abort('blockedbyclient');
  });
}

interface Session { access_token: string; refresh_token: string }
type Json = Record<string, unknown>;

const bearer = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

async function signInApi(api: APIRequestContext, password: string): Promise<{ status: number; session: Session | null }> {
  const response = await api.post('/api/v1/auth/login', { data: { email: ACCOUNT.email, password } });
  return { status: response.status(), session: response.ok() ? ((await response.json()) as Session) : null };
}

/**
 * Leave the account as every test expects to find it: registered, on ORIGINAL_PASSWORD, with its
 * canonical username and names and no avatar. Safe to call at any point, any number of times.
 */
async function restoreAccount(api: APIRequestContext): Promise<Session> {
  let { session } = await signInApi(api, ORIGINAL_PASSWORD);
  if (!session) {
    const changed = (await signInApi(api, CHANGED_PASSWORD)).session;
    if (changed) {
      // A run changed the password and did not get to put it back.
      const back = await api.put('/api/v1/users/me/password', {
        ...bearer(changed.access_token),
        data: { current_password: CHANGED_PASSWORD, new_password: ORIGINAL_PASSWORD, confirm_password: ORIGINAL_PASSWORD },
      });
      if (!back.ok()) throw new Error(`could not restore the QA password: ${back.status()} ${await back.text()}`);
    } else {
      const registered = await api.post('/api/v1/auth/register', { data: { ...ACCOUNT, password: ORIGINAL_PASSWORD } });
      if (!registered.ok()) throw new Error(`could not register the QA account: ${registered.status()} ${await registered.text()}`);
    }
    session = (await signInApi(api, ORIGINAL_PASSWORD)).session;
    if (!session) throw new Error('the QA account still cannot sign in with its original password');
  }
  const reset = await api.put('/api/v1/users/me', {
    ...bearer(session.access_token),
    data: { username: ACCOUNT.username, first_name: ACCOUNT.first_name, last_name: ACCOUNT.last_name, avatar_url: null },
  });
  if (!reset.ok()) throw new Error(`could not restore the QA profile: ${reset.status()} ${await reset.text()}`);
  return session;
}

async function storedProfile(api: APIRequestContext, token: string): Promise<Json> {
  const response = await api.get('/api/v1/users/me', bearer(token));
  expect(response.ok(), 'GET /users/me on the isolated backend').toBe(true);
  return (await response.json()) as Json;
}

test.beforeAll(async () => {
  const api = await isolatedApiContext();
  try { await restoreAccount(api); } finally { await api.dispose(); }
});

test.afterAll(async () => {
  const api = await isolatedApiContext();
  try { await restoreAccount(api); } finally { await api.dispose(); }
});

test.beforeEach(async ({ context }) => {
  liveStackHits = [];
  await guardLiveStack(context);
});

test.afterEach(() => {
  expect(liveStackHits, 'nothing may reach the live stack (:8000 or :3100)').toEqual([]);
});

const isProfilePut = (request: Request): boolean =>
  request.method() === 'PUT' && new URL(request.url()).pathname === '/api/v1/users/me';
const isPasswordPut = (request: Request): boolean =>
  request.method() === 'PUT' && new URL(request.url()).pathname === '/api/v1/users/me/password';
const isLogout = (request: Request): boolean =>
  request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/auth/logout';

const sent = (page: Page, predicate: (request: Request) => boolean, windowMs = ABSENCE_WINDOW_MS): Promise<boolean> =>
  page.waitForRequest(predicate, { timeout: windowMs }).then(() => true, () => false);

const fields = (page: Page) => ({
  username: page.getByPlaceholder(authEn['auth.profile.usernamePlaceholder'], { exact: true }),
  firstName: page.getByPlaceholder(authEn['auth.profile.firstNamePlaceholder'], { exact: true }),
  lastName: page.getByPlaceholder(authEn['auth.profile.lastNamePlaceholder'], { exact: true }),
});
const editButton = (page: Page) => page.getByRole('button', { name: authEn['auth.profile.edit'], exact: true });
const saveButton = (page: Page) => page.getByRole('button', { name: authEn['auth.profile.save'], exact: true });
const cancelButton = (page: Page) => page.getByRole('button', { name: authEn['auth.cancel'], exact: true });
const signInButton = (page: Page) => page.getByRole('button', { name: authEn['auth.login.submit'], exact: true });

/**
 * The two tokens this browser holds. NEVER ASSERTED ON DIRECTLY: a failing assertion prints its
 * operands, and these are real tokens from the isolated backend. Assertions go through holdsTokens
 * and holdsExactly below, which compare in the test and hand the assertion booleans only.
 */
const storedTokens = (page: Page): Promise<Array<string | null>> =>
  page.evaluate(([a, r]) => [window.localStorage.getItem(a), window.localStorage.getItem(r)], [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY]);
/** Whether this browser holds each token, as [access, refresh]. */
const holdsTokens = async (page: Page): Promise<boolean[]> => (await storedTokens(page)).map(token => token !== null);
/** Whether this browser still holds exactly these tokens. */
const holdsExactly = async (page: Page, tokens: Array<string | null>): Promise<boolean> => {
  const now = await storedTokens(page);
  return now.length === tokens.length && now.every((token, index) => token !== null && token === tokens[index]);
};

/** Sign in through the real form, as a visitor would. Resolves once the route has changed. */
async function signInThroughTheForm(page: Page, password: string): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"]').first().fill(ACCOUNT.email);
  await page.locator('input[type="password"]').first().fill(password);
  await signInButton(page).click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 20_000 });
}

/** The first line of the header's account menu: "{first} {last}". Closes the menu again. */
async function headerName(page: Page): Promise<string> {
  await page.locator('header button[aria-haspopup]').last().click();
  const menu = page.getByRole('menu');
  await expect(menu).toBeVisible();
  const name = ((await menu.locator('p').first().textContent()) ?? '').replace(/\s+/g, ' ').trim();
  await page.keyboard.press('Escape');
  await expect(menu).toBeHidden();
  return name;
}

/* ====================================================================== the profile form */

test('the profile form edits, cancels, saves once and keeps what it saved, on the real backend', async ({ page }) => {
  test.setTimeout(90_000);
  const api = await isolatedApiContext();
  try {
    const session = await restoreAccount(api);

    const puts: Json[] = [];
    page.on('request', request => { if (isProfilePut(request)) puts.push((request.postDataJSON() ?? {}) as Json); });

    await signInThroughTheForm(page, ORIGINAL_PASSWORD);
    await page.goto('/profile');
    const { username, firstName, lastName } = fields(page);
    await expect(username).toHaveValue(ACCOUNT.username);
    await expect(firstName).toHaveValue(ACCOUNT.first_name);
    // Read only now: signing in writes last_login_at, which moves updated_at on the same row.
    const before = await storedProfile(api, session.access_token);

    // Edit opens the form and writes nothing.
    const editPut = sent(page, isProfilePut);
    await editButton(page).click();
    expect(await editPut, `Edit must not save (watched ${ABSENCE_WINDOW_MS} ms)`).toBe(false);
    expect(puts, 'no PUT may have left the browser').toEqual([]);
    await expect(firstName).toBeEnabled();

    // Cancel writes nothing and puts the stored values back.
    await firstName.fill('QA-Cancelled');
    await lastName.fill('');
    const cancelPut = sent(page, isProfilePut);
    await cancelButton(page).click();
    expect(await cancelPut, 'Cancel must not save').toBe(false);
    await expect(firstName).toHaveValue(ACCOUNT.first_name);
    await expect(lastName).toHaveValue(ACCOUNT.last_name);
    await expect(firstName).toBeDisabled();
    const afterCancel = await storedProfile(api, session.access_token);
    expect(afterCancel.first_name).toBe(ACCOUNT.first_name);
    expect(afterCancel.updated_at, 'nothing was written, so nothing moved').toBe(before.updated_at);

    // Save sends one PUT, the backend stores it, and the header follows without a reload.
    await editButton(page).click();
    await firstName.fill('Audited');
    const putRequest = page.waitForRequest(isProfilePut);
    await saveButton(page).click();
    expect((await (await putRequest).response())?.status()).toBe(200);
    expect(await sent(page, isProfilePut, EXTRA_PUT_WINDOW_MS), 'one Save, one PUT').toBe(false);
    // The username was not edited, so it is not sent (finding #11: an absent key is "leave it alone").
    expect(puts).toEqual([{ first_name: 'Audited', last_name: ACCOUNT.last_name, avatar_url: null }]);
    const saved = await storedProfile(api, session.access_token);
    expect(saved.first_name).toBe('Audited');
    expect(saved.last_name).toBe(ACCOUNT.last_name);
    await expect(firstName).toBeDisabled();
    await expect(page.locator('header button[aria-haspopup]').last()).toContainText('Audited');
    expect(await headerName(page)).toBe(`Audited ${ACCOUNT.last_name}`);

    // A reload reads back what was stored.
    await page.reload();
    await expect(fields(page).firstName).toHaveValue('Audited');
    expect(await headerName(page)).toBe(`Audited ${ACCOUNT.last_name}`);

    // Clearing an optional name sends null and the backend clears it.
    await editButton(page).click();
    await fields(page).lastName.fill('');
    const clearRequest = page.waitForRequest(isProfilePut);
    await saveButton(page).click();
    expect((await (await clearRequest).response())?.status(), 'a cleared name is accepted').toBe(200);
    expect(puts).toHaveLength(2);
    expect(puts[1]).toEqual({ first_name: 'Audited', last_name: null, avatar_url: null });
    expect((await storedProfile(api, session.access_token)).last_name).toBeNull();
    expect(await headerName(page)).toBe('Audited');
    await page.reload();
    await expect(fields(page).lastName).toHaveValue('');
    await expect(fields(page).firstName).toHaveValue('Audited');
  } finally {
    await restoreAccount(api);
    await api.dispose();
  }
});

/* ===================================================================== the password form */

test('a password change signs this browser out, the new password works and the old one does not; a browser already signed in elsewhere stays signed in', async ({ page, browser }) => {
  test.setTimeout(120_000);
  const api = await isolatedApiContext();
  const elsewhere = await browser.newContext({ baseURL: ISOLATED_BASE, viewport: { width: 1440, height: 900 } });
  await guardExternalAssets(elsewhere, 'real');
  await guardLiveStack(elsewhere);
  try {
    await restoreAccount(api);

    // ANOTHER BROWSER, signed in before the change: one of the "other browsers and devices" the page talks about.
    const otherPage = await elsewhere.newPage();
    await signInThroughTheForm(otherPage, ORIGINAL_PASSWORD);
    await otherPage.goto('/profile');
    await expect(fields(otherPage).username).toHaveValue(ACCOUNT.username);
    const otherTokens = await storedTokens(otherPage);
    expect(await holdsTokens(otherPage), 'the other browser holds a session').toEqual([true, true]);

    // THIS BROWSER.
    await signInThroughTheForm(page, ORIGINAL_PASSWORD);
    await page.goto('/password-change');
    await expect(page.getByRole('heading', { name: authEn['auth.change.heading'] })).toBeVisible();
    await expect(page.getByText(authEn['auth.change.note'])).toBeVisible();
    const [thisAccess, thisRefresh] = await storedTokens(page);
    const passwordStatuses: number[] = [];
    page.on('response', response => { if (isPasswordPut(response.request())) passwordStatuses.push(response.status()); });

    const current = page.getByPlaceholder(authEn['auth.change.currentPlaceholder'], { exact: true });
    const next = page.getByPlaceholder(authEn['auth.change.newPlaceholder'], { exact: true });
    const confirm = page.getByPlaceholder(authEn['auth.change.confirmPlaceholder'], { exact: true });
    const submit = page.getByRole('button', { name: authEn['auth.change.submit'], exact: true });

    // 1. A wrong current password: refused by the server, nothing changes, nobody is signed out.
    await current.fill('not-the-password-1');
    await next.fill(CHANGED_PASSWORD);
    await confirm.fill(CHANGED_PASSWORD);
    const logoutSent = sent(page, isLogout);
    const refused = page.waitForResponse(response => isPasswordPut(response.request()));
    await submit.click();
    expect((await refused).status()).toBe(400);
    await expect(page.getByText('Incorrect current password', { exact: true })).toBeVisible();
    expect(await logoutSent, 'a refused change signs nobody out').toBe(false);
    await expect(page).toHaveURL(/\/password-change$/);
    expect(await holdsExactly(page, [thisAccess, thisRefresh]), 'a refused change leaves this session as it was').toBe(true);
    expect((await signInApi(api, ORIGINAL_PASSWORD)).status, 'the password did not change').toBe(200);

    // 2. A confirmation that does not match: caught before any request.
    await current.fill(ORIGINAL_PASSWORD);
    await confirm.fill(`${CHANGED_PASSWORD}-typo`);
    const mismatchPut = sent(page, isPasswordPut);
    await submit.click();
    expect(await mismatchPut, `a mismatch sends nothing (watched ${ABSENCE_WINDOW_MS} ms)`).toBe(false);
    await expect(page.getByText(authEn['auth.validation.newPasswordsDiffer'], { exact: true })).toBeVisible();
    expect(passwordStatuses).toEqual([400]);

    // 3. The change itself.
    await confirm.fill(CHANGED_PASSWORD);
    const logoutResponse = page.waitForResponse(response => isLogout(response.request()), { timeout: 10_000 }).then(r => r, () => null);
    const changed = page.waitForResponse(response => isPasswordPut(response.request()));
    await submit.click();
    expect((await changed).status()).toBe(200);

    const softly = expect.configure({ soft: true, timeout: 5000 });
    const logout = await logoutResponse;
    softly(logout?.status(), 'this browser is signed out through /auth/logout').toBe(200);
    softly(logout?.request().postDataJSON()?.refresh_token === thisRefresh, 'with the refresh token it held').toBe(true);
    await softly.poll(() => holdsTokens(page), { message: 'no token stays in this browser' }).toEqual([false, false]);
    await softly(page).toHaveURL(/\/login$/);
    await softly(signInButton(page)).toBeVisible();
    await softly(page.getByText(authEn['auth.change.success'], { exact: true })).toBeVisible();
    await softly(page.locator('body')).not.toContainText('all devices');
    const bounced = await page
      .waitForURL(url => !url.pathname.startsWith('/login'), { timeout: BOUNCE_WINDOW_MS })
      .then(() => true, () => false);
    softly(bounced, `the sign-in form stays put (watched ${BOUNCE_WINDOW_MS} ms)`).toBe(false);
    softly(passwordStatuses).toEqual([400, 200]);
    // Everything below assumes this browser really was signed out.
    expect(await holdsTokens(page), 'this browser must not still hold its session').toEqual([false, false]);

    // On the server: the refresh token this browser held is revoked by that sign-out.
    const reusedRefresh = await api.post('/api/v1/auth/refresh', { data: { refresh_token: thisRefresh } });
    expect(reusedRefresh.status(), "this browser's refresh token no longer refreshes").toBe(401);
    // Observed, not promised: the ACCESS token this browser held is a stateless JWT. The browser no
    // longer has it, but a copy of it would still be accepted until it expires.
    const reusedAccess = await api.get('/api/v1/users/me', bearer(thisAccess as string));

    // The old password is refused and the new one works, through the API and through the form.
    expect((await signInApi(api, ORIGINAL_PASSWORD)).status, 'the old password must be refused').toBe(401);
    expect((await signInApi(api, CHANGED_PASSWORD)).status, 'the new password must work').toBe(200);
    await signInThroughTheForm(page, CHANGED_PASSWORD);
    expect(await holdsTokens(page), 'signing in with the new password stores a session').toEqual([true, true]);

    // THE OTHER BROWSER, already signed in before the change: NOT signed out automatically. This is
    // exactly what the page now says ("Other browsers and devices that are already signed in are not
    // signed out automatically"); if token hardening ever lands, this assertion is the one to invert.
    const otherReload = otherPage.waitForResponse(response =>
      response.request().method() === 'GET' && new URL(response.url()).pathname === '/api/v1/users/me');
    await otherPage.reload();
    const otherStatus = (await otherReload).status();
    expect(otherStatus, 'the other browser still reads its profile after the change').toBe(200);
    await expect(otherPage).toHaveURL(/\/profile$/);
    await expect(fields(otherPage).username).toHaveValue(ACCOUNT.username);
    expect(await holdsExactly(otherPage, otherTokens), 'the other browser keeps the session it had').toBe(true);
    const otherRefresh = await api.post('/api/v1/auth/refresh', { data: { refresh_token: otherTokens[1] } });

    const observed = [
      `other browser, signed in before the change, reloads /profile: GET /users/me -> ${otherStatus}, still signed in`,
      `other browser's pre-change refresh token: POST /auth/refresh -> ${otherRefresh.status()}`,
      `this browser's pre-change refresh token after its sign-out: POST /auth/refresh -> ${reusedRefresh.status()}`,
      `this browser's pre-change access token (no longer stored by the browser): GET /users/me -> ${reusedAccess.status()}`,
    ];
    for (const line of observed) {
      test.info().annotations.push({ type: 'observed', description: line });
      console.log(`[account-profile] observed: ${line}`);
    }
  } finally {
    await elsewhere.close();
    await restoreAccount(api);
    await api.dispose();
  }
});
