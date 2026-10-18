import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { APIRequestContext, Page } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { QA_EXPERT, ensureQaExpertToken } from '../support/qa-account';
import { ISOLATED_API as API, isolatedApiContext as apiContext } from '../support/isolated';

/**
 * The browser-level journey on the isolated pair, in two halves, each through the real pages
 * against the clone of the live database behind the isolated backend (:8001, scheduler off,
 * no provider credentials).
 *
 *  1. A suggested combination becomes a recorded slip THROUGH THE PAGE: the suggestions page,
 *     its first combination, the slip dock, save, record, and the slip history showing the new
 *     slip as recorded and pending. The combination's identity - every leg's fixture id,
 *     selection id and forecast snapshot id - is read from the response the page itself received
 *     and followed to the dock and to the recorded slip; three wrong selections cannot pass on
 *     their count.
 *  2. A slip that has results SHOWS THEM on the slip history, and viewing it again - a reload,
 *     then leaving and coming back - changes nothing: the card reads the same, and the API's
 *     answer for every slip is byte-identical before and after the views.
 *
 * This demonstrates creating one PENDING slip and displaying ANOTHER, already-settled slip. Two
 * slips, not one, by design: the clone receives no results (its providers are blank), so a slip
 * recorded here can only ever be pending here, and the one whose results are displayed is the
 * suggestion-born slip settled on the live database on 2026-10-17, which the clone carries.
 * Every screenshot and page text goes to E2E_EVIDENCE_DIR when it is set, so a run can be kept.
 */

const EVIDENCE = process.env.E2E_EVIDENCE_DIR;
/** Unique per run, to the millisecond plus a random tail: two runs in the same minute never collide. */
const RUN_ID = `${new Date().toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 19)}-${Math.random().toString(36).slice(2, 8)}`;

function keep(name: string, text: string): void {
  if (!EVIDENCE) return;
  mkdirSync(EVIDENCE, { recursive: true });
  writeFileSync(join(EVIDENCE, name), text);
}

async function shot(page: Page, name: string): Promise<void> {
  if (!EVIDENCE) return;
  mkdirSync(EVIDENCE, { recursive: true });
  await page.screenshot({ path: join(EVIDENCE, name), fullPage: true, type: 'jpeg', quality: 70 });
}

function auth(bearer: string) {
  return { headers: { Authorization: `Bearer ${bearer}` } };
}

async function signInThroughTheForm(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

interface SlipLeg {
  match: { id: string };
  selection: { selection_id: string };
  snapshot_id?: string | null;
  state: string;
  settlement?: { actual?: unknown } | null;
}
interface Slip { id: string; name: string | null; status: string; state: string; settled_at: string | null; legs: SlipLeg[] }

async function slips(api: APIRequestContext, bearer: string): Promise<Slip[]> {
  const body = await (await api.get('/api/v1/me/slips', auth(bearer))).json();
  return body.slips as Slip[];
}

// ----------------------------------------------------------------------------- selection identity
/** One leg's identity: which fixture, which selection, which forecast snapshot it was priced from. */
export interface LegIdentity { match_id: string; selection_id: string; snapshot_id: string | null }

/** The combination as the page's own suggestions response gave it. */
export function identityOfCombination(combination: {
  legs: Array<{ match: { id: string }; selection: { selection_id: string }; why?: { forecast?: { snapshot_id?: string | null } | null } | null }>;
}): LegIdentity[] {
  return combination.legs.map(leg => ({
    match_id: leg.match.id,
    selection_id: leg.selection.selection_id,
    snapshot_id: leg.why?.forecast?.snapshot_id ?? null,
  }));
}

function key(leg: LegIdentity): string {
  return `${leg.match_id} ${leg.selection_id} ${leg.snapshot_id ?? '-'}`;
}

/**
 * Every way `actual` fails to be exactly `expected`, as sentences; empty when they are the same
 * legs (order aside). A leg with the right fixture but a different selection or snapshot is a
 * difference, so three wrong selections on the right three fixtures cannot pass.
 */
export function selectionDifferences(expected: LegIdentity[], actual: LegIdentity[]): string[] {
  const want = new Map(expected.map(leg => [key(leg), leg]));
  const got = new Map(actual.map(leg => [key(leg), leg]));
  const out: string[] = [];
  if (expected.length !== actual.length) out.push(`${expected.length} leg(s) expected, ${actual.length} found`);
  for (const [k, leg] of want) if (!got.has(k)) out.push(`missing: ${leg.selection_id} on ${leg.match_id} from snapshot ${leg.snapshot_id ?? '-'}`);
  for (const [k, leg] of got) if (!want.has(k)) out.push(`unexpected: ${leg.selection_id} on ${leg.match_id} from snapshot ${leg.snapshot_id ?? '-'}`);
  return out;
}

test.describe.configure({ mode: 'serial' });

test('the identity check rejects a wrong selection, a wrong snapshot and a wrong fixture', async () => {
  const expected: LegIdentity[] = [
    { match_id: 'm1', selection_id: 'total_goals:over@0.5', snapshot_id: 's1' },
    { match_id: 'm2', selection_id: 'match_result:home', snapshot_id: 's2' },
    { match_id: 'm3', selection_id: 'double_chance:1x', snapshot_id: 's3' },
  ];
  expect(selectionDifferences(expected, [...expected].reverse())).toEqual([]);
  const wrongSelection = expected.map((leg, i) => (i === 0 ? { ...leg, selection_id: 'total_goals:under@0.5' } : leg));
  const wrongSnapshot = expected.map((leg, i) => (i === 1 ? { ...leg, snapshot_id: 'other' } : leg));
  const wrongFixture = expected.map((leg, i) => (i === 2 ? { ...leg, match_id: 'm4' } : leg));
  const oneShort = expected.slice(0, 2);
  for (const tampered of [wrongSelection, wrongSnapshot, wrongFixture, oneShort]) {
    expect(selectionDifferences(expected, tampered), 'same count, different identity').not.toEqual([]);
  }
  expect(selectionDifferences(expected, wrongSelection)).toContain('missing: total_goals:over@0.5 on m1 from snapshot s1');
});

test('a suggested combination becomes a recorded slip through the page, selection for selection', async ({ page }) => {
  const api = await apiContext();
  const bearer = await ensureQaExpertToken(api);
  await signInThroughTheForm(page);

  // The page's OWN request decides whether there is anything to record: its defaults (three legs
  // at 60% here) are not the API probe's, so the probe is not consulted. A failed request is a
  // failure; only a 200 with no combination is an empty day.
  const suggestions = page.waitForResponse(r => r.request().method() === 'GET' && r.url().includes('/api/v1/suggestions'));
  await page.goto('/selections/suggestions');
  const response = await suggestions;
  const query = new URL(response.url()).searchParams;
  keep('00-page-request.txt', `${response.request().method()} ${response.url()}\nstatus ${response.status()}\n`);
  expect(response.ok(), `the page's suggestions request failed: HTTP ${response.status()}`).toBe(true);
  const body = await response.json();
  expect(Array.isArray(body.combinations), 'the page received a well-formed answer').toBe(true);
  test.skip(body.combinations.length === 0, `the page's own request (legs=${query.get('legs')}, min_probability=${query.get('min_probability')}) returned no combination at ${API}: ${body.shortfall}`);
  const expected = identityOfCombination(body.combinations[0]);
  keep('00-expected-identity.json', JSON.stringify({ query: Object.fromEntries(query), legs: expected }, null, 2));

  await expect(page.getByTestId('suggest-results')).toBeVisible();
  const first = page.getByTestId('suggested-combination').first();
  await expect(first).toBeVisible();
  const shownFixtures = await first.getByTestId('suggested-leg').evaluateAll(nodes => nodes.map(n => n.getAttribute('data-match-id')));
  expect(shownFixtures, 'the page renders the response it received, fixture for fixture').toEqual(expected.map(leg => leg.match_id));
  keep('01-first-suggested-combination.txt', await first.innerText());
  await shot(page, '01-suggestions-page.jpg');

  await first.getByTestId('suggested-add-all').click();
  await expect(page.getByTestId('slip-dock-count')).toHaveText(String(expected.length));
  await page.getByTestId('slip-dock-toggle').click();
  const dock = page.getByTestId('slip-dock');
  await expect(dock.getByTestId('slip-leg')).toHaveCount(expected.length);
  const inDock = await dock.getByTestId('slip-leg').evaluateAll(nodes =>
    nodes.map(n => ({ match_id: n.getAttribute('data-match-id') ?? '', selection_id: n.getAttribute('data-selection-id') ?? '' })));
  // The dock does not show which snapshot a leg was priced from; it is checked on the recorded slip.
  expect(selectionDifferences(expected.map(l => ({ ...l, snapshot_id: null })), inDock.map(l => ({ ...l, snapshot_id: null }))),
    'what reached the dock is the combination the page showed').toEqual([]);

  const name = `Browser journey ${RUN_ID}`;
  await dock.getByTestId('slip-name').fill(name);
  await dock.getByTestId('slip-save').click();
  await expect(dock.getByTestId('slip-dock-notice')).toContainText(name);
  await shot(page, '02-slip-saved-in-the-dock.jpg');

  await dock.getByTestId('slip-record-open').click();
  await dock.getByTestId('slip-record-reference').fill(`browser journey ${RUN_ID} on the isolated pair`);
  await dock.getByTestId('slip-record-confirm').click();
  await expect(dock.getByTestId('slip-dock-notice')).toContainText(/recorded|Marqué/i);
  await shot(page, '03-slip-recorded-in-the-dock.jpg');

  await page.goto('/selections');
  const card = page.locator('[data-testid="history-slip"]').filter({ hasText: name });
  await expect(card, 'exactly one slip carries this run\'s name').toHaveCount(1);
  await expect(card).toHaveAttribute('data-status', 'recorded');
  await expect(card).toHaveAttribute('data-state', 'pending');
  await expect(card.getByTestId('history-leg')).toHaveCount(expected.length);
  keep('04-history-new-slip.txt', await card.innerText());
  await shot(page, '04-history-with-the-new-slip.jpg');

  const mine = (await slips(api, bearer)).filter(s => s.name === name);
  expect(mine, 'one recorded slip on the server with this run\'s name').toHaveLength(1);
  const recorded = mine[0];
  expect(recorded.status).toBe('recorded');
  expect(recorded.state).toBe('pending');
  const asRecorded = recorded.legs.map(leg => ({ match_id: leg.match.id, selection_id: leg.selection.selection_id, snapshot_id: leg.snapshot_id ?? null }));
  expect(selectionDifferences(expected, asRecorded), 'what was recorded is the combination the page showed, snapshot included').toEqual([]);
  for (const leg of recorded.legs) expect(leg.state).toBe('pending');
  keep('04-recorded-slip-from-the-api.json', JSON.stringify(recorded, null, 2));
});

test('a settled slip shows its results, and viewing it again changes nothing', async ({ page }) => {
  const api = await apiContext();
  const bearer = await ensureQaExpertToken(api);
  const before = await slips(api, bearer);
  const settled = before.filter(s => s.state === 'won' || s.state === 'lost');
  test.skip(settled.length === 0, `the clone at ${API} holds no settled slip to display`);
  // The suggestion-born slip settled on the live database on 2026-10-17 when the clone carries it;
  // otherwise the most recently settled one.
  const target = settled.find(s => s.id.startsWith('a0dce8dd')) ?? settled.sort((a, b) => String(b.settled_at).localeCompare(String(a.settled_at)))[0];
  keep('05-all-slips-before-viewing.json', JSON.stringify(before, null, 2));

  await signInThroughTheForm(page);
  await page.goto('/selections');
  const card = page.locator('[data-testid="history-slip"]').filter({ hasText: String(target.name) });
  await expect(card).toHaveCount(1);
  await expect(card).toHaveAttribute('data-status', 'recorded');
  await expect(card).toHaveAttribute('data-state', target.state);
  const legs = card.getByTestId('history-leg');
  await expect(legs).toHaveCount(target.legs.length);
  for (let i = 0; i < target.legs.length; i += 1) {
    const leg = target.legs[i];
    await expect(legs.nth(i)).toHaveAttribute('data-state', leg.state);
    const actual = leg.settlement?.actual;
    if (typeof actual === 'string') await expect(legs.nth(i)).toContainText(actual);
  }
  const firstView = await card.innerText();
  keep('05-history-settled-slip.txt', firstView);
  await shot(page, '05-history-settled-slip.jpg');

  await page.reload();
  const afterReload = await page.locator('[data-testid="history-slip"]').filter({ hasText: String(target.name) }).innerText();
  expect(afterReload, 'a reload shows the same card').toBe(firstView);
  await shot(page, '06-history-settled-slip-after-reload.jpg');

  await page.goto('/');
  await page.goto('/selections');
  const afterReturn = await page.locator('[data-testid="history-slip"]').filter({ hasText: String(target.name) }).innerText();
  expect(afterReturn, 'leaving and coming back shows the same card').toBe(firstView);

  const after = await slips(api, bearer);
  keep('06-all-slips-after-viewing.json', JSON.stringify(after, null, 2));
  expect(after, 'every slip the API serves is identical before and after the views').toEqual(before);
});
