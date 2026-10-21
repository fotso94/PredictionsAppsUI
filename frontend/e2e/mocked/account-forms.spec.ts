import { test, expect, Page, Request, Route } from '@playwright/test';
import { Json, registerAuthHandler, stubBackend } from '../support/api-stub';
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '../support/auth';
import authEn from '../../src/i18n/messages/auth.en';
import authFr from '../../src/i18n/messages/auth.fr';

/**
 * THE PROFILE FORM AND THE PASSWORD FORM, BY WHAT THEY SEND.
 *
 * The defects (QA findings 1 and 8):
 *
 *  - Edit SAVED. The action row swapped an unkeyed type="button" Edit for an unkeyed
 *    type="submit" Save at the same position, so React reused the one DOM node and turned it into
 *    a submit button inside the click. The browser's default action then submitted the form: the
 *    unchanged values went out in a PUT and the fields went back to disabled. Editing by hand was
 *    impossible, by mouse or keyboard.
 *  - A name never supplied was sent as '' on every save, which the backend refused with 422 until
 *    181b8932, blocking unrelated username and avatar edits with it.
 *  - After a save the header kept the old name until a reload: nothing told the signed-in state.
 *  - No label was tied to its input, so none of these fields had an accessible name.
 *  - A changed password left this browser signed in (tokens kept, state kept), sent the reader to
 *    /login two seconds later only to be bounced home, and claimed a logout "from all devices"
 *    that never happened anywhere.
 *
 * WHAT IS ASSERTED IS WHAT WAS SENT AND STORED: the PUT bodies the stub received, how many, the
 * tokens left in localStorage, the logout call. Text on screen is checked as well, never instead.
 *
 * ABSENCE IS A BOUNDED WINDOW. "No PUT" is `waitForRequest` with a deadline of ABSENCE_WINDOW_MS,
 * armed BEFORE the action. On the old code the Edit PUT left within milliseconds of the click, so
 * the window exposes it with a wide margin without making the test slow or flaky.
 *
 * FIELDS ARE FOUND BY PLACEHOLDER in the behavioural tests, which both the old and the new form
 * carry, so a failure on the old code is the defect itself and not a missing label. The labels
 * have tests of their own.
 *
 * THE SESSION IS SEEDED ONCE PER TAB, not on every document load as support/auth.ts does, so a
 * reload after a password change shows what the browser really holds then: no tokens.
 *
 * COST. Every /api/v1 route is stubbed; nothing reaches a backend. A guard aborts, and the test
 * fails on, any request to the live stack (:8000 or :3100).
 */

/** How long an absence ("no PUT", "no bounce") is watched for. See the note above. */
const ABSENCE_WINDOW_MS = 1500;
/** How long after a save the test keeps watching for a second, unwanted PUT. */
const EXTRA_PUT_WINDOW_MS = 1000;
/** The old page navigated to /login after 2000 ms and was bounced home; watch past that. */
const BOUNCE_WINDOW_MS = 2500;

/** Opaque strings that never leave this browser context. They are not credentials. */
const ACCESS_TOKEN = 'e2e-account-forms-access-token';
const REFRESH_TOKEN = 'e2e-account-forms-refresh-token';
/** sessionStorage survives a reload in the same tab, which is what makes the seed one-shot. */
const SEEDED_FLAG = 'e2e-account-forms-seeded';
/** Mirrors LANGUAGE_KEY in src/i18n/index.ts. */
const LANGUAGE_KEY = 'sp.language.v1';

/** The live stack. Nothing in this file may reach it. */
const LIVE_STACK = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):(8000|3100)(\/|$)/;

/** GET/PUT /api/v1/users/me, as backend UserResponse. */
interface Profile extends Json {
  id: string;
  email: string;
  username: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  user_type: string;
  account_status: string;
  email_verified: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

const baseProfile = (over: Partial<Profile> = {}): Profile => ({
  id: '00000000-0000-4000-8000-0000000000f1',
  email: 'qa.forms@predictions-local.dev',
  username: 'qa-regular',
  first_name: 'QA',
  last_name: 'Regular',
  avatar_url: null,
  user_type: 'regular',
  account_status: 'active',
  email_verified: true,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-05T09:00:00Z',
  last_login_at: null,
  ...over,
});

/** What the stub backend holds and what it was sent. */
interface World {
  profile: Profile;
  /** Every PUT /users/me body, in order. */
  puts: Json[];
  /** Statuses for the next PUTs /users/me to fail with, consumed in order. */
  putFailures: number[];
  /** Delay before answering a PUT /users/me, to hold a save in flight. */
  putDelayMs: number;
  /** Every PUT /users/me/password body, in order. */
  passwordPuts: Json[];
  passwordAnswer: { status: number; body: Json };
  /** Every POST /auth/logout body, in order. */
  logouts: Json[];
  /** GET /auth/me calls, the path the header's user comes from. */
  meCalls: number;
  signedOut: boolean;
  /** Requests that tried to reach the live stack. Must stay empty. */
  liveStackHits: string[];
}

let world: World | null = null;

/** backend /auth/me builds full_name exactly like this (backend/app/api/v1/endpoints/auth.py). */
const backendUser = (profile: Profile): Json => ({
  user_id: profile.id,
  email: profile.email,
  full_name: `${profile.first_name ?? ''} ${profile.last_name ?? ''}`.trim(),
  role: profile.user_type,
  is_active: true,
  is_verified: profile.email_verified,
  created_at: profile.created_at,
  updated_at: profile.updated_at,
});

async function setUp(
  page: Page,
  options: { profile?: Partial<Profile>; language?: 'en' | 'fr' } = {},
): Promise<World> {
  const state: World = {
    profile: baseProfile(options.profile),
    puts: [],
    putFailures: [],
    putDelayMs: 0,
    passwordPuts: [],
    passwordAnswer: {
      status: 200,
      body: { message: 'Password changed successfully. Sign in again with your new password.' },
    },
    logouts: [],
    meCalls: 0,
    signedOut: false,
    liveStackHits: [],
  };
  world = state;
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  if (options.language) {
    await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [LANGUAGE_KEY, options.language]);
  }
  await page.addInitScript(
    ([flag, accessKey, refreshKey, access, refresh]) => {
      if (window.sessionStorage.getItem(flag)) return;
      window.sessionStorage.setItem(flag, '1');
      window.localStorage.setItem(accessKey, access);
      window.localStorage.setItem(refreshKey, refresh);
    },
    [SEEDED_FLAG, ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, ACCESS_TOKEN, REFRESH_TOKEN],
  );

  await stubBackend(page);

  const auth = (route: Route, request: Request): Promise<void> => {
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/auth/, '');
    if (path === '/me') {
      state.meCalls += 1;
      return state.signedOut
        ? json(route, { detail: 'Not authenticated' }, 401)
        : json(route, backendUser(state.profile));
    }
    if (path === '/logout') {
      state.logouts.push((request.postDataJSON() ?? {}) as Json);
      state.signedOut = true;
      return json(route, { message: 'Successfully logged out' });
    }
    if (path === '/refresh') {
      return state.signedOut
        ? json(route, { detail: 'Invalid refresh token' }, 401)
        : json(route, { access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN, token_type: 'bearer' });
    }
    return json(route, { detail: 'Not found' }, 404);
  };
  registerAuthHandler(page, auth);
  await page.route('**/api/v1/auth/**', auth);

  // Registered after stubBackend, so Playwright reaches these first. The glob is the exact path:
  // it does not match /users/me/password, which has a route of its own below.
  await page.route('**/api/v1/users/me', async (route: Route, request: Request) => {
    if (request.method() === 'GET') return json(route, state.profile);
    if (request.method() !== 'PUT') return json(route, { detail: 'Method Not Allowed' }, 405);
    const body = (request.postDataJSON() ?? {}) as Json;
    state.puts.push(body);
    if (state.putDelayMs) await new Promise(resolve => setTimeout(resolve, state.putDelayMs));
    const failure = state.putFailures.shift();
    if (failure) return json(route, { detail: 'Simulated server error' }, failure);
    // Stricter than today's backend on purpose: before 181b8932 a blank name was refused with
    // 422, and the form must send null for a blank, so a form that still sends '' fails here.
    for (const field of ['first_name', 'last_name'] as const) {
      if (body[field] === '') {
        return json(route, { detail: [{ loc: ['body', field], msg: 'String should have at least 1 character' }] }, 422);
      }
    }
    state.profile = { ...state.profile, ...(body as Partial<Profile>), updated_at: new Date().toISOString() };
    return json(route, state.profile);
  });
  await page.route('**/api/v1/users/me/password', (route: Route, request: Request) => {
    if (request.method() !== 'PUT') return json(route, { detail: 'Method Not Allowed' }, 405);
    state.passwordPuts.push((request.postDataJSON() ?? {}) as Json);
    return json(route, state.passwordAnswer.body, state.passwordAnswer.status);
  });

  // Last, so it wins over every route above for the two origins it claims.
  await page.route(LIVE_STACK, (route: Route) => {
    state.liveStackHits.push(`${route.request().method()} ${route.request().url()}`);
    return route.abort('blockedbyclient');
  });
  return state;
}

test.afterEach(() => {
  if (world) expect(world.liveStackHits, 'nothing may reach the live stack (:8000 or :3100)').toEqual([]);
  world = null;
});

const isProfilePut = (request: Request): boolean =>
  request.method() === 'PUT' && new URL(request.url()).pathname === '/api/v1/users/me';
const isPasswordPut = (request: Request): boolean =>
  request.method() === 'PUT' && new URL(request.url()).pathname === '/api/v1/users/me/password';
const isLogout = (request: Request): boolean =>
  request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/auth/logout';

/** Armed before the action: true if a matching request leaves inside the window. */
const sent = (page: Page, predicate: (request: Request) => boolean, windowMs = ABSENCE_WINDOW_MS): Promise<boolean> =>
  page.waitForRequest(predicate, { timeout: windowMs }).then(() => true, () => false);

const fields = (page: Page) => ({
  username: page.getByPlaceholder(authEn['auth.profile.usernamePlaceholder'], { exact: true }),
  firstName: page.getByPlaceholder(authEn['auth.profile.firstNamePlaceholder'], { exact: true }),
  lastName: page.getByPlaceholder(authEn['auth.profile.lastNamePlaceholder'], { exact: true }),
  avatar: page.getByPlaceholder('https://example.com/avatar.jpg', { exact: true }),
});

const editButton = (page: Page) => page.getByRole('button', { name: authEn['auth.profile.edit'], exact: true });
const saveButton = (page: Page) => page.getByRole('button', { name: authEn['auth.profile.save'], exact: true });
const cancelButton = (page: Page) => page.getByRole('button', { name: authEn['auth.cancel'], exact: true });

async function openProfile(page: Page): Promise<void> {
  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: authEn['auth.profile.heading'] })).toBeVisible();
  await expect(fields(page).username).toHaveValue(/.+/);
}

/** Open the header's account menu and return its panel; found by role, so it works at every width. */
async function accountMenu(page: Page) {
  await page.locator('header button[aria-haspopup]').last().click();
  const menu = page.getByRole('menu');
  await expect(menu).toBeVisible();
  return menu;
}

const storedTokens = (page: Page) =>
  page.evaluate(([a, r]) => [window.localStorage.getItem(a), window.localStorage.getItem(r)], [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY]);

/* ====================================================================== the profile form */

for (const how of ['mouse', 'Enter', 'Space'] as const) {
  test(`Edit by ${how} opens the form and saves nothing`, async ({ page }) => {
    const state = await setUp(page);
    await openProfile(page);
    const { username, firstName, lastName, avatar } = fields(page);
    await expect(username).toBeDisabled();

    const putSent = sent(page, isProfilePut);
    if (how === 'mouse') {
      await editButton(page).click();
    } else {
      await editButton(page).focus();
      await page.keyboard.press(how);
    }
    expect(await putSent, `Edit by ${how} must not save (watched ${ABSENCE_WINDOW_MS} ms)`).toBe(false);
    expect(state.puts, 'no PUT body may have reached the backend').toEqual([]);

    for (const field of [username, firstName, lastName, avatar]) await expect(field).toBeEnabled();
    await expect(saveButton(page)).toBeVisible();
    await expect(cancelButton(page)).toBeVisible();
    await expect(editButton(page)).toHaveCount(0);
  });
}

test('Cancel sends nothing and puts every original value back', async ({ page }) => {
  const state = await setUp(page, { profile: { avatar_url: 'https://example.com/qa.png' } });
  await openProfile(page);
  const { username, firstName, lastName, avatar } = fields(page);

  const editPut = sent(page, isProfilePut);
  await editButton(page).click();
  expect(await editPut, 'Edit must not save').toBe(false);

  await username.fill('qa-cancelled');
  await firstName.fill('Changed');
  await lastName.fill('');
  await avatar.fill('https://example.com/other.png');

  const cancelPut = sent(page, isProfilePut);
  await cancelButton(page).click();
  expect(await cancelPut, 'Cancel must not save').toBe(false);
  expect(state.puts).toEqual([]);

  await expect(username).toHaveValue('qa-regular');
  await expect(firstName).toHaveValue('QA');
  await expect(lastName).toHaveValue('Regular');
  await expect(avatar).toHaveValue('https://example.com/qa.png');
  for (const field of [username, firstName, lastName, avatar]) await expect(field).toBeDisabled();
  await expect(editButton(page)).toBeVisible();
});

test('Save sends exactly one normalised PUT, the header follows without a reload, and it survives one', async ({ page, isMobile }) => {
  const state = await setUp(page);
  await openProfile(page);
  const { username, firstName, lastName, avatar } = fields(page);

  const editPut = sent(page, isProfilePut);
  await editButton(page).click();
  expect(await editPut, 'Edit must not save').toBe(false);

  await firstName.fill('  Audited  ');
  const meCallsBeforeSave = state.meCalls;
  const putRequest = page.waitForRequest(isProfilePut);
  await saveButton(page).click();
  const response = await (await putRequest).response();
  expect(response?.status()).toBe(200);
  await expect(page.getByText(authEn['auth.profile.saved'], { exact: true })).toBeVisible();

  const extraPut = sent(page, isProfilePut, EXTRA_PUT_WINDOW_MS);
  expect(await extraPut, 'one Save, one PUT').toBe(false);
  // The whole form, explicitly: trimmed, and the avatar that was never set sent as null, not ''.
  expect(state.puts).toEqual([{ username: 'qa-regular', first_name: 'Audited', last_name: 'Regular', avatar_url: null }]);

  // What the server stored, back in the form, read-only again.
  await expect(firstName).toHaveValue('Audited');
  for (const field of [username, firstName, lastName, avatar]) await expect(field).toBeDisabled();

  // The header, WITHOUT a reload: the signed-in user was refetched through /auth/me.
  await expect.poll(() => state.meCalls, { message: 'the save must refresh the signed-in user' })
    .toBeGreaterThan(meCallsBeforeSave);
  if (!isMobile) await expect(page.locator('header button[aria-haspopup]').last()).toContainText('Audited');
  const menu = await accountMenu(page);
  await expect(menu).toContainText('Audited Regular');
  await page.keyboard.press('Escape');

  await page.reload();
  await expect(fields(page).firstName).toHaveValue('Audited');
  await expect(await accountMenu(page)).toContainText('Audited Regular');
  expect(state.puts, 'a reload sends nothing').toHaveLength(1);
});

test('pressing Enter in a field saves once', async ({ page }) => {
  const state = await setUp(page);
  await openProfile(page);

  const editPut = sent(page, isProfilePut);
  await editButton(page).click();
  expect(await editPut, 'Edit must not save').toBe(false);

  await fields(page).lastName.fill('Entered');
  const putRequest = page.waitForRequest(isProfilePut);
  await fields(page).lastName.press('Enter');
  expect((await (await putRequest).response())?.status()).toBe(200);
  expect(await sent(page, isProfilePut, EXTRA_PUT_WINDOW_MS), 'one Enter, one PUT').toBe(false);
  expect(state.puts).toEqual([{ username: 'qa-regular', first_name: 'QA', last_name: 'Entered', avatar_url: null }]);
});

test('a double activation of Save while it is in flight sends one PUT', async ({ page }) => {
  const state = await setUp(page);
  state.putDelayMs = 600;
  await openProfile(page);

  const editPut = sent(page, isProfilePut);
  await editButton(page).click();
  expect(await editPut, 'Edit must not save').toBe(false);

  await fields(page).firstName.fill('Twice');
  await saveButton(page).dblclick();
  await expect(page.getByText(authEn['auth.profile.saved'], { exact: true })).toBeVisible();
  expect(await sent(page, isProfilePut, EXTRA_PUT_WINDOW_MS)).toBe(false);
  expect(state.puts, 'a save in flight is not sent again').toHaveLength(1);
});

test('clearing an optional name and the avatar sends null for each, and succeeds', async ({ page }) => {
  const state = await setUp(page, { profile: { avatar_url: 'https://example.com/qa.png' } });
  await openProfile(page);
  const { firstName, lastName, avatar } = fields(page);

  const editPut = sent(page, isProfilePut);
  await editButton(page).click();
  expect(await editPut, 'Edit must not save').toBe(false);

  // A name of spaces is blank once trimmed. (Spaces in the URL field would be stopped by the
  // browser's own type="url" check before any submit, which is the browser's business.)
  await lastName.fill('   ');
  await avatar.fill('');
  const putRequest = page.waitForRequest(isProfilePut);
  await saveButton(page).click();
  expect((await (await putRequest).response())?.status()).toBe(200);
  await expect(page.getByText(authEn['auth.profile.saved'], { exact: true })).toBeVisible();

  expect(state.puts).toEqual([{ username: 'qa-regular', first_name: 'QA', last_name: null, avatar_url: null }]);
  expect(state.profile.last_name).toBeNull();
  await expect(lastName).toHaveValue('');
  await expect(avatar).toHaveValue('');
  await expect(firstName).toHaveValue('QA');
  // The menu's first line is the name, "{first} {last}".
  await expect((await accountMenu(page)).locator('p').first()).toHaveText('QA');
});

test('an account whose names were never supplied can change its username', async ({ page }) => {
  const state = await setUp(page, { profile: { first_name: null, last_name: null } });
  await openProfile(page);
  const { username, firstName, lastName } = fields(page);
  await expect(firstName).toHaveValue('');
  await expect(lastName).toHaveValue('');

  // The body itself is kept, so a PUT that does go out (as Edit's did) shows what it carried.
  const editBody = page.waitForRequest(isProfilePut, { timeout: ABSENCE_WINDOW_MS })
    .then(request => (request.postDataJSON() ?? {}) as Json, () => null);
  await editButton(page).click();
  const leaked = await editBody;
  expect.soft(leaked === null ? [] : ['first_name', 'last_name'].filter(field => leaked[field] === ''),
    'a name that was never supplied must not be sent as an empty string').toEqual([]);
  expect(leaked, 'Edit must not save').toBeNull();

  await username.fill('qa-renamed');
  const putRequest = page.waitForRequest(isProfilePut);
  await saveButton(page).click();
  expect((await (await putRequest).response())?.status(), 'blank names are sent as null and accepted').toBe(200);
  await expect(page.getByText(authEn['auth.profile.saved'], { exact: true })).toBeVisible();
  expect(state.puts).toEqual([{ username: 'qa-renamed', first_name: null, last_name: null, avatar_url: null }]);

  await page.reload();
  await expect(fields(page).username).toHaveValue('qa-renamed');
});

test('a failed save keeps the edits and says so, sends one request, and a retry sends exactly one more', async ({ page }) => {
  const state = await setUp(page);
  state.putFailures = [500];
  await openProfile(page);
  const { username, firstName } = fields(page);

  const editPut = sent(page, isProfilePut);
  await editButton(page).click();
  expect(await editPut, 'Edit must not save').toBe(false);

  await firstName.fill('Retried');
  await username.fill('qa-retried');
  const failedRequest = page.waitForRequest(isProfilePut);
  await saveButton(page).click();
  expect((await (await failedRequest).response())?.status()).toBe(500);
  await expect(page.getByText('Simulated server error', { exact: true })).toBeVisible();
  expect(await sent(page, isProfilePut, EXTRA_PUT_WINDOW_MS), 'a failure is not retried behind the reader\'s back').toBe(false);
  expect(state.puts).toHaveLength(1);

  // Still editing, nothing lost, both ways out available.
  await expect(firstName).toHaveValue('Retried');
  await expect(username).toHaveValue('qa-retried');
  await expect(firstName).toBeEnabled();
  await expect(saveButton(page)).toBeEnabled();
  await expect(cancelButton(page)).toBeEnabled();
  expect(state.profile.first_name, 'nothing was stored').toBe('QA');

  const retry = page.waitForRequest(isProfilePut);
  await saveButton(page).click();
  expect((await (await retry).response())?.status()).toBe(200);
  await expect(page.getByText(authEn['auth.profile.saved'], { exact: true })).toBeVisible();
  expect(await sent(page, isProfilePut, EXTRA_PUT_WINDOW_MS)).toBe(false);
  expect(state.puts).toHaveLength(2);
  expect(state.puts[1]).toEqual({ username: 'qa-retried', first_name: 'Retried', last_name: 'Regular', avatar_url: null });
  await expect(firstName).toBeDisabled();
  await expect(await accountMenu(page)).toContainText('Retried Regular');
});

test('after a failed save, Cancel puts the stored values back and sends nothing more', async ({ page }) => {
  const state = await setUp(page);
  state.putFailures = [500];
  await openProfile(page);
  const { firstName } = fields(page);

  const editPut = sent(page, isProfilePut);
  await editButton(page).click();
  expect(await editPut, 'Edit must not save').toBe(false);

  await firstName.fill('Abandoned');
  const failedRequest = page.waitForRequest(isProfilePut);
  await saveButton(page).click();
  expect((await (await failedRequest).response())?.status()).toBe(500);
  await expect(page.getByText('Simulated server error', { exact: true })).toBeVisible();

  const cancelPut = sent(page, isProfilePut);
  await cancelButton(page).click();
  expect(await cancelPut).toBe(false);
  expect(state.puts).toHaveLength(1);
  await expect(firstName).toHaveValue('QA');
  await expect(firstName).toBeDisabled();
});

test('every profile field has an accessible name, and says what it holds', async ({ page }) => {
  await setUp(page);
  await openProfile(page);
  const expected: Array<[string, string, string, string]> = [
    [authEn['auth.profile.email'], 'profile-email', 'email', 'email'],
    [authEn['auth.profile.username'], 'profile-username', 'username', 'username'],
    [authEn['auth.profile.firstName'], 'profile-first-name', 'first_name', 'given-name'],
    [authEn['auth.profile.lastName'], 'profile-last-name', 'last_name', 'family-name'],
    [authEn['auth.profile.avatarUrl'], 'profile-avatar-url', 'avatar_url', 'url'],
  ];
  for (const [label, id, name, autocomplete] of expected) {
    const field = page.getByLabel(label, { exact: true });
    await expect(field, `"${label}" must name exactly one field`).toHaveCount(1);
    await expect(field).toHaveAttribute('id', id);
    await expect(field).toHaveAttribute('name', name);
    await expect(field).toHaveAttribute('autocomplete', autocomplete);
  }
});

/* ===================================================================== the password form */

const passwordFields = (page: Page) => ({
  current: page.getByPlaceholder(authEn['auth.change.currentPlaceholder'], { exact: true }),
  next: page.getByPlaceholder(authEn['auth.change.newPlaceholder'], { exact: true }),
  confirm: page.getByPlaceholder(authEn['auth.change.confirmPlaceholder'], { exact: true }),
});
const changeButton = (page: Page) => page.getByRole('button', { name: authEn['auth.change.submit'], exact: true });

async function openPasswordChange(page: Page): Promise<void> {
  await page.goto('/password-change');
  await expect(page.getByRole('heading', { name: authEn['auth.change.heading'] })).toBeVisible();
}

test('every password field has an accessible name and the autocomplete a password manager needs', async ({ page }) => {
  await setUp(page);
  await openPasswordChange(page);
  const expected: Array<[string, string, string]> = [
    [authEn['auth.change.current'], 'password-current', 'current-password'],
    [authEn['auth.change.new'], 'password-new', 'new-password'],
    [authEn['auth.change.confirm'], 'password-confirm', 'new-password'],
  ];
  for (const [label, id, autocomplete] of expected) {
    // exact: "New Password" is also inside "Confirm New Password".
    const field = page.getByLabel(label, { exact: true });
    await expect(field, `"${label}" must name exactly one field`).toHaveCount(1);
    await expect(field).toHaveAttribute('id', id);
    await expect(field).toHaveAttribute('autocomplete', autocomplete);
  }
});

test('a wrong current password is refused with the server\'s reason, and the reader stays signed in', async ({ page }) => {
  const state = await setUp(page);
  state.passwordAnswer = { status: 400, body: { detail: 'Incorrect current password' } };
  await openPasswordChange(page);
  const { current, next, confirm } = passwordFields(page);

  await current.fill('not-the-password');
  await next.fill('NewPassword-123');
  await confirm.fill('NewPassword-123');
  const putRequest = page.waitForRequest(isPasswordPut);
  const logoutSent = sent(page, isLogout);
  await changeButton(page).click();
  expect((await (await putRequest).response())?.status()).toBe(400);
  await expect(page.getByText('Incorrect current password', { exact: true })).toBeVisible();

  expect(await logoutSent, 'a refused change signs nobody out').toBe(false);
  expect(state.passwordPuts).toEqual([{ current_password: 'not-the-password', new_password: 'NewPassword-123', confirm_password: 'NewPassword-123' }]);
  expect(await storedTokens(page)).toEqual([ACCESS_TOKEN, REFRESH_TOKEN]);
  await expect(page).toHaveURL(/\/password-change$/);
  await expect(changeButton(page)).toBeEnabled();
});

test('a confirmation that does not match sends nothing', async ({ page }) => {
  const state = await setUp(page);
  await openPasswordChange(page);
  const { current, next, confirm } = passwordFields(page);

  await current.fill('CurrentPassword-1');
  await next.fill('NewPassword-123');
  await confirm.fill('NewPassword-456');
  const putSent = sent(page, isPasswordPut);
  await changeButton(page).click();
  expect(await putSent, 'a mismatch is caught before the request').toBe(false);
  expect(state.passwordPuts).toEqual([]);
  await expect(page.getByText(authEn['auth.validation.newPasswordsDiffer'], { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/password-change$/);
});

for (const language of ['en', 'fr'] as const) {
  test(`a changed password signs this browser out onto a usable sign-in form, and says only that, in ${language}`, async ({ page }) => {
    const catalogue = language === 'fr' ? authFr : authEn;
    const state = await setUp(page, { language });
    await page.goto('/password-change');
    await expect(page.getByRole('heading', { name: catalogue['auth.change.heading'] })).toBeVisible();

    // Soft through to the reload, so a run on the old code reports every one of these at once.
    // Deadlines are short for the same reason: they hold on the new code within a few hundred ms.
    const softly = expect.configure({ soft: true, timeout: 5000 });

    // The promise made BEFORE the change, word for word from the catalogue, and no wider.
    await expect(page.getByText(catalogue['auth.change.note'])).toBeVisible();
    const pageText = page.locator('body');
    await softly(pageText).not.toContainText('all devices');
    await softly(pageText).not.toContainText('tous vos appareils');

    const placeholders = (key: 'auth.change.currentPlaceholder' | 'auth.change.newPlaceholder' | 'auth.change.confirmPlaceholder') =>
      page.getByPlaceholder(catalogue[key], { exact: true });
    await placeholders('auth.change.currentPlaceholder').fill('CurrentPassword-1');
    await placeholders('auth.change.newPlaceholder').fill('NewPassword-123');
    await placeholders('auth.change.confirmPlaceholder').fill('NewPassword-123');

    const putRequest = page.waitForRequest(isPasswordPut);
    const logoutRequest = page.waitForRequest(isLogout, { timeout: 5000 }).then(request => request, () => null);
    await page.getByRole('button', { name: catalogue['auth.change.submit'], exact: true }).click();
    expect((await (await putRequest).response())?.status()).toBe(200);

    // This browser's session ends: its refresh token is handed to /auth/logout, and both tokens go.
    const logout = await logoutRequest;
    softly(logout, 'the change must sign this browser out through /auth/logout').not.toBeNull();
    softly(logout?.postDataJSON(), 'the refresh token this browser held is the one revoked').toEqual({ refresh_token: REFRESH_TOKEN });
    await softly.poll(() => state.logouts.length, { message: 'exactly one sign-out reached the backend' }).toBe(1);
    await softly.poll(() => storedTokens(page), { message: 'no token may stay in this browser' }).toEqual([null, null]);

    // A sign-in form the reader can use...
    await softly(page).toHaveURL(/\/login$/);
    await softly(page.getByRole('button', { name: catalogue['auth.login.submit'], exact: true })).toBeVisible();

    // ...told the truthful sentence, and not a hard-coded English logout toast.
    await softly(page.getByText(catalogue['auth.change.success'], { exact: true })).toBeVisible();
    await softly(pageText).not.toContainText('all devices');
    await softly(pageText).not.toContainText('tous vos appareils');
    await softly(page.getByText('Logged out successfully')).toHaveCount(0);
    softly(state.passwordPuts).toHaveLength(1);

    // ...and not bounced back home afterwards, as the old two-second timer did.
    const bounced = await page
      .waitForURL(url => !url.pathname.startsWith('/login'), { timeout: BOUNCE_WINDOW_MS })
      .then(() => true, () => false);
    softly(bounced, `the sign-in form must stay put (watched ${BOUNCE_WINDOW_MS} ms)`).toBe(false);

    // And the session really is gone: a reload does not find one (the seed is one-shot).
    await page.goto('/password-change');
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('button', { name: catalogue['auth.login.submit'], exact: true })).toBeVisible();
  });
}
