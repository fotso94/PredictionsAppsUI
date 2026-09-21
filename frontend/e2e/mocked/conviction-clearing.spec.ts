import { expect, test, Page, Request, Route } from '@playwright/test';
import { Json, stubBackend } from '../support/api-stub';
import { regularUser, signIn } from '../support/auth';

/**
 * WITHDRAWING A FIGURE, PINNED AT THE REQUEST BODY.
 *
 * An expert who deletes a number from the composer is saying "I no longer stand behind this".
 * Whether that reaches the database depends on one thing only: what the browser puts in the PUT
 * body. `PUT /api/v1/expert/predictions/{id}` reads an ABSENT key as "leave the stored value
 * alone" and a key carrying `null` as "withdraw it" (app/services/expert_prediction.py, via
 * `model_fields_set`), so a composer that omits the field it could not read is indistinguishable
 * from one that never mentioned it — and that is exactly the bug these tests exist for. An API
 * that honours an explicit null is only half of the answer: while the body omits the key, the
 * expert clears the box, saves, and watches the old percentage come back.
 *
 * So the assertions here are on the REQUEST BODY, not on the screen. A rendering test would pass
 * against a page that displays a cleared field perfectly and sends nothing, which is the failure
 * mode. Every test below reads the JSON the page actually put on the wire, and the parsed body is
 * checked with `in` rather than by value, because `undefined` and `null` both print as "no value"
 * in a diff while meaning opposite things to the API.
 *
 * WHAT MUST NOT DRIFT. src/components/expert/composer.ts states the contract these pin:
 *   - an edit body is a COMPLETE statement of the prediction, so every optional key is present;
 *   - a cleared box is `null`, never an omitted key and never 0;
 *   - a complementary pair moves together — both sides numbers, or both sides null — which is
 *     the rule COMPLEMENTARY_PAIRS in app/schemas/predictions.py enforces with a 422 naming the
 *     missing half;
 *   - `key_factors` is the one key deliberately left out, because this form cannot edit it and
 *     an absent key is the only way to say "I have nothing to say about that";
 *   - a body whose totals the API will refuse is not sent at all, and the totals are measured on
 *     the values the API will store rather than on the digits as typed.
 *
 * COST. Every /api/v1 route is intercepted; no provider and no backend is reached.
 */

const PREDICTION_ID = 'pred-clearing-1';
const MATCH_ID = 'match-clearing-1';
const KICKOFF_UTC = '2026-10-04T14:00:00Z';

/** Every optional key an edit body has to carry, and none of the required ones. */
const OPTIONAL_KEYS = [
  'confidence_score',
  'btts_yes_prob', 'btts_no_prob', 'btts_confidence',
  'total_goals_over_25_prob', 'total_goals_under_25_prob',
  'total_goals_over_35_prob', 'total_goals_under_35_prob', 'total_goals_confidence',
  'reasoning',
] as const;

/** The complementary markets, as the backend groups them. Neither side travels alone. */
const PAIRS: Array<[string, string]> = [
  ['btts_yes_prob', 'btts_no_prob'],
  ['total_goals_over_25_prob', 'total_goals_under_25_prob'],
  ['total_goals_over_35_prob', 'total_goals_under_35_prob'],
];

/**
 * Each market conviction with the probabilities it is a conviction ABOUT, as MARKET_CONVICTIONS
 * in app/schemas/predictions.py groups them — the two goal lines share one conviction column.
 * A conviction cannot outlive its market, so a body that withdraws every outcome of a market and
 * leaves the conviction in it standing is refused with a 422.
 */
const CONVICTIONS: Array<[string, string[]]> = [
  ['btts_confidence', ['btts_yes_prob', 'btts_no_prob']],
  ['total_goals_confidence', ['total_goals_over_25_prob', 'total_goals_under_25_prob',
                              'total_goals_over_35_prob', 'total_goals_under_35_prob']],
];

/**
 * One published prediction, owned by the signed-in expert.
 *
 * It publishes the match result and a conviction and nothing else, which is what makes the
 * optional markets testable: src/components/expert/PredictionMarketsEditor.tsx LOCKS a market
 * that is already published (it can be re-valued but not unticked), so a market that has to be
 * switched off during the test must start off null here.
 */
function prediction(over: Partial<Json> = {}): Json {
  return {
    id: PREDICTION_ID,
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
    created_at: '2026-10-01T09:00:00Z',
    published_at: '2026-10-01T09:05:00Z',
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
 * Open the list as an expert and record every PUT body.
 *
 * The expert routes are registered AFTER stubBackend on purpose: Playwright tries the most
 * recently registered route first, and stubBackend's catch-all would otherwise answer
 * /predictions/my-predictions with an empty object, leaving nothing on the page to edit.
 *
 * The PUT is answered with the stored prediction MERGED WITH THE BODY, so the reload that follows
 * a save shows what was actually sent. A stub that echoed the unchanged record instead would let
 * a save that sent nothing look successful.
 */
async function openMyPredictions(page: Page, stored: Json = prediction()): Promise<Json[]> {
  const bodies: Json[] = [];
  let current = stored;

  await stubBackend(page);
  await signIn(page, { user: regularUser({ role: 'expert', full_name: 'QA Expert' }) });

  await page.route('**/api/v1/expert/**', async (route: Route, request: Request) => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/expert/, '');

    if (path === `/predictions/${PREDICTION_ID}` && request.method() === 'PUT') {
      const body = JSON.parse(request.postData() || '{}') as Json;
      bodies.push(body);
      current = { ...current, ...body };
      return json(current);
    }
    if (path === '/predictions/my-predictions') return json([current]);
    if (path === '/predictions/review-queue') return json([]);
    return json({});
  });

  await page.goto('/expert/predictions/my-predictions');
  await expect(page.getByRole('button', { name: 'Edit' })).toBeVisible();
  return bodies;
}

const field = (page: Page, suffix: string) => page.locator(`#edit-${PREDICTION_ID}-${suffix}`);

/** Open the editor on the one prediction on screen. */
async function startEditing(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Edit' }).click();
  await expect(field(page, 'conviction')).toBeVisible();
}

/**
 * Tick or untick a market, and do not go on until the editor agrees it happened.
 *
 * `check()` clicks once and then asserts the box changed state, which is a race against React:
 * the composer re-renders as it revalidates, and a click that lands in that window is swallowed
 * with "Clicking the checkbox did not change its state". Retrying the click-and-confirm is the
 * only way to close that from outside the app, and it is honest about what is being waited for —
 * unlike a sleep, it fails if the toggle genuinely does not respond.
 */
async function setMarket(page: Page, market: string, enabled: boolean): Promise<void> {
  const toggle = field(page, `${market}-enabled`);
  await expect(toggle).toBeEnabled();
  await expect(async () => {
    if (await toggle.isChecked() !== enabled) await toggle.click();
    expect(await toggle.isChecked()).toBe(enabled);
  }).toPass({ timeout: 10_000 });
}

async function save(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Save Changes' }).click();
  await expect(page.getByRole('button', { name: 'Edit' })).toBeVisible();
}

/**
 * The invariants every edit body must satisfy, whatever the expert typed.
 *
 * Kept in one place and asserted on every body: a rule that only held for the field under test
 * would be the same per-field thinking that produced the half-withdrawn pair in the first place.
 */
function assertBodyShape(body: Json): void {
  for (const key of OPTIONAL_KEYS) {
    expect(key in body, `${key} must be stated, not omitted — an absent key means "leave it alone"`)
      .toBe(true);
  }
  for (const [first, second] of PAIRS) {
    expect((body[first] === null) === (body[second] === null),
      `${first} and ${second} are one market and must be withdrawn together`).toBe(true);
  }
  for (const [conviction, outcomes] of CONVICTIONS) {
    if (outcomes.every(key => body[key] === null)) {
      expect(body[conviction],
        `${conviction} is a conviction in a market this body publishes no outcome for; it has to `
        + 'be withdrawn with the market, and the API refuses the body otherwise').toBeNull();
    }
  }
  expect('key_factors' in body,
    'this form cannot edit key_factors, so the body must say nothing about it').toBe(false);
  // The 1X2 market is not optional and is always three numbers.
  for (const key of ['home_win_prob', 'draw_prob', 'away_win_prob']) {
    expect(typeof body[key]).toBe('number');
  }
}

test.describe('clearing a value in the composer reaches the API as a withdrawal', () => {
  test('a cleared conviction is sent as an explicit null', async ({ page }) => {
    const bodies = await openMyPredictions(page);
    await startEditing(page);

    await expect(field(page, 'conviction')).toHaveValue('80');
    await field(page, 'conviction').fill('');
    await save(page);

    expect(bodies).toHaveLength(1);
    const body = bodies[0];
    assertBodyShape(body);
    expect(body.confidence_score,
      'an omitted or 0 conviction is how this bug looked; null is the withdrawal').toBeNull();
  });

  test('a conviction that was not touched is sent unchanged, not withdrawn', async ({ page }) => {
    const bodies = await openMyPredictions(page);
    await startEditing(page);

    // Change something else entirely, so the save is real and the conviction is incidental.
    await field(page, 'reasoning').fill('Reworded, with the same conviction behind it.');
    await save(page);

    const body = bodies[0];
    assertBodyShape(body);
    expect(body.confidence_score, 'a rule that withdrew everything would be no better').toBe(0.8);
    expect(body.reasoning).toBe('Reworded, with the same conviction behind it.');
  });

  test('a conviction of zero is sent as zero and not as a withdrawal', async ({ page }) => {
    const bodies = await openMyPredictions(page);
    await startEditing(page);

    await field(page, 'conviction').fill('0');
    await save(page);

    const body = bodies[0];
    assertBodyShape(body);
    expect(body.confidence_score,
      '0% is a claim the expert made; null would report it as no claim at all').toBe(0);
  });

  test('a cleared reasoning note is sent as an explicit null', async ({ page }) => {
    const bodies = await openMyPredictions(page);
    await startEditing(page);

    await field(page, 'reasoning').fill('');
    await save(page);

    const body = bodies[0];
    assertBodyShape(body);
    expect(body.reasoning).toBeNull();
  });

  test('switching a market off sends both sides of the pair as null, never one', async ({ page }) => {
    const bodies = await openMyPredictions(page);
    await startEditing(page);

    // Tick the market, fill it, then change your mind — the sequence that leaves a stale value
    // behind if switching off means "say nothing about it".
    await setMarket(page, 'btts', true);
    await field(page, 'btts-yes').fill('60');
    await field(page, 'btts-no').fill('40');
    await setMarket(page, 'btts', false);
    await expect(field(page, 'btts-yes')).toHaveCount(0);
    await save(page);

    const body = bodies[0];
    assertBodyShape(body);
    expect(body.btts_yes_prob).toBeNull();
    expect(body.btts_no_prob).toBeNull();
    expect(body.btts_confidence,
      'a conviction for a market this prediction does not publish is a figure about nothing')
      .toBeNull();
  });

  test('a market switched on is sent whole, with both sides as numbers', async ({ page }) => {
    const bodies = await openMyPredictions(page);
    await startEditing(page);

    await setMarket(page, 'btts', true);
    await field(page, 'btts-yes').fill('60');
    await field(page, 'btts-no').fill('40');
    await save(page);

    const body = bodies[0];
    assertBodyShape(body);
    expect(body.btts_yes_prob).toBeCloseTo(0.6, 10);
    expect(body.btts_no_prob).toBeCloseTo(0.4, 10);
    // The goal lines were never ticked, so they are withdrawn rather than left unstated.
    expect(body.total_goals_over_25_prob).toBeNull();
    expect(body.total_goals_under_25_prob).toBeNull();
  });

  test('a conviction can be withdrawn while its market stays published', async ({ page }) => {
    /**
     * The editor locks a PUBLISHED market's toggle so it cannot be untied — and locks nothing
     * else. The conviction box beside it takes the form-wide disabled flag only, so clearing the
     * figure while the market stands is an edit an expert can make, and a legitimate one: they
     * still publish 60/40, they no longer want to say how sure they are. The body must carry the
     * market as two numbers and the conviction as null, which is the one combination the
     * conviction rule deliberately permits.
     */
    const bodies = await openMyPredictions(page, prediction({
      btts_yes_prob: 0.6, btts_no_prob: 0.4, btts_confidence: 0.9,
    }));
    await startEditing(page);

    await expect(field(page, 'btts-enabled')).toBeDisabled();
    await expect(field(page, 'btts-conviction')).toBeEnabled();
    await expect(field(page, 'btts-conviction')).toHaveValue('90');
    await field(page, 'btts-conviction').fill('');
    await save(page);

    const body = bodies[0];
    assertBodyShape(body);
    expect(body.btts_yes_prob).toBeCloseTo(0.6, 10);
    expect(body.btts_no_prob).toBeCloseTo(0.4, 10);
    expect(body.btts_confidence,
      'the market stands, so this is a withdrawn conviction and not an orphaned one').toBeNull();
  });

  test('an unbalanced pair is never sent at all', async ({ page }) => {
    const bodies = await openMyPredictions(page);
    await startEditing(page);

    await setMarket(page, 'btts', true);
    await field(page, 'btts-yes').fill('60');
    // The other side left blank: the form has to hold this back rather than send half a market
    // and let the API answer with a 422.
    await page.getByRole('button', { name: 'Save Changes' }).click();

    await expect(page.getByRole('button', { name: 'Save Changes' })).toBeVisible();
    expect(bodies, 'the composer sent an incomplete pair instead of refusing it').toHaveLength(0);
  });
});

/**
 * A TOTAL THE TABLE CANNOT HOLD DOES NOT LEAVE THE BROWSER.
 *
 * `predictions.predictions` stores every probability as NUMERIC(5, 4) and constrains what the
 * columns may add up to: `ck_predictions_prob_sum` is an equality on the three match-result
 * probabilities, and `ck_predictions_btts_prob_sum` a one-point window on the BTTS pair. The
 * request validators in app/schemas/predictions.py enforce both on the STORED values, so a form
 * that accepts a total they refuse produces a 422 after the expert has pressed save — with their
 * numbers still on screen and nothing saying which one to change.
 *
 * Both tests below therefore assert two things: that nothing went on the wire, and that the
 * screen says what has to change. A form that silently refuses to save is its own bug.
 */
test.describe('a total the API cannot store is refused in the form', () => {
  /** The running-total line for one market, wherever the editor puts it. */
  const total = (page: Page, rule: string) =>
    page.locator('p').filter({ hasText: rule }).first();

  test('three outcomes that add to 99 are held back, and the form says to add 1', async ({ page }) => {
    /**
     * 33 / 33 / 33 is the split for a match too close to call, and it is the one a tolerance of
     * a percentage point would wave through: it is 0.99 in unit terms, and the table's equality
     * refuses it. The expert needs the missing point named, not just the refusal.
     */
    const bodies = await openMyPredictions(page);
    await startEditing(page);

    await field(page, 'home').fill('33');
    await field(page, 'draw').fill('33');
    await field(page, 'away').fill('33');

    const outcome = total(page, 'The three outcomes must total 100%.');
    await expect(outcome).toContainText('99% total');
    await expect(outcome, 'a refusal without a size leaves the expert guessing').toContainText('Add 1.');

    await page.getByRole('button', { name: 'Save Changes' }).click();

    await expect(page.getByRole('button', { name: 'Save Changes' })).toBeVisible();
    expect(bodies, 'the composer sent a triple the table cannot store').toHaveLength(0);
  });

  test('a pair that only rounds past the window at the fourth decimal is held back', async ({ page }) => {
    /**
     * 98.995 and 2.005 add to exactly 1.01 as doubles, which is inside the API's window for a
     * two-way market. Stored they are 0.9900 and 0.0201, and 1.0101 is outside it. Measuring the
     * total on the typed doubles is what makes this one look balanced on screen and come back as
     * a 422, so the totals here are measured on the values that will be stored.
     */
    const bodies = await openMyPredictions(page);
    await startEditing(page);

    await setMarket(page, 'btts', true);
    await field(page, 'btts-yes').fill('98.995');
    await field(page, 'btts-no').fill('2.005');

    const pair = total(page, 'The two sides must total 100%.');
    await expect(pair).toContainText('101.01% total');
    await expect(pair).toContainText('Remove 1.01.');

    await page.getByRole('button', { name: 'Save Changes' }).click();

    await expect(page.getByRole('button', { name: 'Save Changes' })).toBeVisible();
    expect(bodies, 'the composer sent a pair the BTTS constraint refuses').toHaveLength(0);
  });
});
