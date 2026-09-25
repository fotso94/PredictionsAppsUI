import { expect, test, Page, Request, Route } from '@playwright/test';
import en from '../../src/i18n/messages/en';
import fr from '../../src/i18n/messages/fr';
import coreEn from '../../src/i18n/messages/core.en';
import authEn from '../../src/i18n/messages/auth.en';
import expertEn from '../../src/i18n/messages/expert.en';
import readerEn from '../../src/i18n/messages/reader.en';
import { compileMessage, renderMessage } from '../../src/i18n/format';
import {
  ApiMatch, dayPayload, fixtureAt, selectLocalDay, stubBackend, withoutForecast,
} from '../support/api-stub';
import { signIn } from '../support/auth';

/**
 * English and French, and a time zone the reader chose.
 *
 * WHAT THIS FILE IS FOR, and what it deliberately is not. It does not check that the French reads
 * well — no automated test can, and the package report says in as many words that no native
 * speaker has reviewed it. It checks the things a test CAN establish and a reader cannot easily
 * verify for themselves:
 *
 *   - that the core journey is actually in the reader's language, on both sides, with no English
 *     left behind (the check is generated from the catalogues themselves, so it cannot go stale);
 *   - that a sentence built from measured data is a whole sentence in each language rather than
 *     translated fragments in English word order, including where French counts 0 and 1 as one;
 *   - that EVERY count-bearing French string has the right form at 0, 1, 2 and 11, written out
 *     case by case, with a guard that fails if a new counting message is added and not listed —
 *     one sample and a hope is how five agreement errors reached the home page with this file
 *     green;
 *   - that "today" is a day in the zone the READER CHOSE, not the one the device is set to, on a
 *     zone with no daylight saving and on one with it — and never a zone the device is already
 *     on, which proves nothing and is asserted against directly;
 *   - that a midnight kick-off and a rescheduled one land on the right day and show the right
 *     clock reading in that zone;
 *   - that the choice survives a reload;
 *   - that nothing is clipped at 200% text zoom, in either language, at 360, 390 and 1440.
 *
 * COST. Every /api/v1 route is intercepted, so nothing here can reach a provider. The last test
 * in the file asserts that directly — no request may carry `refresh=true`, and every day read
 * must carry `refresh=false` — because a localisation change that quietly re-enabled refreshing
 * would spend an allowance that is already spent.
 *
 * WIDTHS. The suite's projects give 1440 (mocked-desktop) and 390 (mocked-mobile); 360 is a
 * project of its own restricted to another file. So the zoom test sets its own viewport and runs
 * at all three inside whichever project it is given, exactly as journey-proof.spec.ts does, and
 * the report says which emulation that actually was.
 */

type Language = 'en' | 'fr';

const LANGUAGE_KEY = 'sp.language.v1';
const ZONE_KEY = 'sp.timeZone.v1';

/**
 * Zones the tests pin, and the one they may never pin.
 *
 * NEW_YORK IS THE BROWSER CONTEXT'S OWN ZONE — playwright.config.ts sets `timezoneId:
 * 'America/New_York'` for every project. So a test that has the READER choose New York and then
 * checks a New York answer is green whether the chosen zone is honoured or ignored: an
 * implementation that read `Intl.DateTimeFormat().resolvedOptions().timeZone` and threw the
 * reader's choice away would pass it. Three tests in this file did exactly that, including both
 * of the daylight-saving ones, which are the tests most worth having.
 *
 * Every zone a test CHOOSES is therefore one the device is not set to, and `NEW_YORK` is used
 * only as the device's zone — the wrong answer each test proves it did not give.
 *
 * PARIS replaces New York for daylight saving. Its clocks go back on 25 October 2026 (the last
 * Sunday of October, at 01:00 UTC), which makes that local day 25 hours long; New York's clocks
 * do not move until 1 November, so on 25 October the device and the choice disagree about the
 * offset AND, at the hours these tests pick, about the date.
 */
const DOUALA = 'Africa/Douala';
const PARIS = 'Europe/Paris';
const DUBAI = 'Asia/Dubai';
/** The browser context's zone. Chosen by no test; the answer every zone test must NOT give. */
const NEW_YORK = 'America/New_York';

const WIDTHS = [
  { label: '360', width: 360, height: 740 },
  { label: '390', width: 390, height: 844 },
  { label: '1440', width: 1440, height: 900 },
];

/**
 * Put the reader's stored choices in place BEFORE the app boots.
 *
 * `addInitScript` runs ahead of the page's own scripts, which is the only moment that proves
 * anything: src/i18n reads both keys while its module is evaluated, so a value written later
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

/**
 * The English strings a French page must not contain — generated from the catalogues.
 *
 * WHY IT IS GENERATED AND NOT A HAND-WRITTEN LIST. A hand-written list of "watch out for these
 * English words" is complete on the day it is written and rots from then on: the next person adds
 * a key, translates it or does not, and the list says nothing either way. Deriving it from `en`
 * and `fr` means the check grows with the catalogue automatically, and a key whose French is
 * accidentally left as its English is caught here rather than by a reader.
 *
 * WHAT IS EXCLUDED, and why each exclusion is safe:
 *   - keys whose English and French are identical. A product name ("Soccer Predictions"), a word
 *     French shares ("Expert", "Matches" → no, that one differs) or a purely punctuation string
 *     is not evidence of anything.
 *   - anything holding ICU syntax. Those are templates, not literals: the rendered text is
 *     nothing like the source, so a substring test on them is meaningless.
 *   - anything under 16 characters, or without a space. Short strings collide by accident —
 *     "Source" appears inside "Source :" — and a false failure here would teach the next person
 *     to weaken the test.
 */
const ENGLISH_ONLY = (Object.keys(en) as Array<keyof typeof en>)
  .filter(key => en[key] !== fr[key])
  .map(key => en[key] as string)
  .filter(value => !/[{}#]/.test(value))
  .filter(value => value.trim().length >= 16 && value.trim().includes(' '))
  .map(value => value.trim());

/** The reverse: French a page in English must not contain, by the same rule. */
const FRENCH_ONLY = (Object.keys(en) as Array<keyof typeof en>)
  .filter(key => en[key] !== fr[key])
  .map(key => fr[key])
  .filter(value => !/[{}#]/.test(value))
  .filter(value => value.trim().length >= 16 && value.trim().includes(' '))
  .map(value => value.trim());

/** Every catalogue string found on the page that belongs to the other language. */
function strays(text: string, forbidden: string[]): string[] {
  const normalised = text.replace(/\s+/g, ' ');
  return forbidden.filter(value => normalised.includes(value.replace(/\s+/g, ' ')));
}

/* ========================================================== the journey, in both languages */

/**
 * The routes this package claims. Named here rather than in prose so the report and the test
 * cannot disagree about what was covered.
 */
const COVERED_ROUTES = ['/', '/predictions/today', '/predictions/tomorrow', '/matches', '/nowhere-at-all'];

for (const language of ['en', 'fr'] as const) {
  test(`the core journey is in ${language} and carries nothing from the other CATALOGUE`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);

    for (const route of COVERED_ROUTES) {
      await page.goto(route);
      await page.waitForLoadState('networkidle');

      // The document says which language it is in. A screen reader picks its voice from this,
      // and getting it wrong is a defect a sighted reviewer never sees.
      await expect(page.locator('html')).toHaveAttribute('lang', language);

      const text = await bodyText(page);
      const found = strays(text, language === 'fr' ? ENGLISH_ONLY : FRENCH_ONLY);
      expect(found, `${route} in ${language} carried text from the other catalogue`).toEqual([]);
    }
  });

  /*
   * WHAT THE TEST ABOVE CANNOT SEE, measured rather than left as a blind spot.
   *
   * ENGLISH_ONLY is derived from the two catalogues, so it can only ever catch a string that
   * entered one of them. The settlement rules, the market definitions and the minimum-sample
   * rationale never do: they are backend constants (MINIMUM_SAMPLE_RATIONALE and
   * HIT_RATE_DEFINITION in app/services/settlement.py) served as prose in English, and the
   * interface renders what the server sent. So the French home page carries whole English
   * paragraphs while the test above passes, which is exactly the shape of false green this
   * project has been burned by before.
   *
   * This does not translate them. Those sentences are load-bearing — "a void is never a loss",
   * what a hit test compares, why a rate is withheld below thirty — and a French paraphrase that
   * drifted from the English rule would be worse than English, so localising them is a backend
   * change that needs a native reviewer and is recorded as outstanding work.
   *
   * What this does is stop the gap being invisible and stop it growing. It counts the
   * server-supplied English actually rendered on the French page and pins the count. A new
   * untranslated string makes this fail; translating one makes it fail too, and the number comes
   * down deliberately rather than by accident.
   */
  if (language === 'fr') {
    test('the English the backend supplies on a French page is counted, not overlooked', async ({ page }) => {
      await seedPreferences(page, { language, zone: DOUALA });
      await stubBackend(page);
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const serverEnglish = await page.evaluate(() => {
        // A sentence of five or more words carrying English function words and no French marker.
        const english = /\b(the|of those|and the|with|from|have been|has been|were|which|nothing|scored|published|forecast|before|after)\b/i;
        const french = /[àâçéèêëîïôûùüÿœ]|\b(le|la|les|des|une?|qui|pour|pas|sur|est|sont)\b/i;
        const found: string[] = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node: Node | null;
        while ((node = walker.nextNode())) {
          const text = (node.textContent || '').replace(/\s+/g, ' ').trim();
          if (text.length < 25 || text.split(' ').length < 5) continue;
          if (english.test(text) && !french.test(text)) found.push(text);
        }
        return [...new Set(found)];
      });

      // The count is a characterisation, not an endorsement. Seven is what the STUBBED payload
      // renders; the real backend renders twelve, because it serves more rule and definition
      // prose than the fixture carries. Both numbers are the same defect, and this pins the one
      // this test can actually observe.
      expect(serverEnglish.length,
        `server-supplied English on the French home page changed. Found:\n${serverEnglish.map(s => `  - ${s.slice(0, 90)}`).join('\n')}`)
        .toBe(7);
    });
  }
}

/* ====================================================== the auth and account screens */

/**
 * THE ACCOUNT ENDPOINTS, which stubBackend does not model.
 *
 * `/users/me`, `/subscriptions/me` and `/subscriptions/tiers` fall through its catch-all and
 * answer `{}`, which renders a profile with no fields and a subscription page with no tiers —
 * a page with nothing on it passes a "no English here" check trivially. These answers give
 * those screens something to render, so the assertions below are about the screens.
 *
 * Registered AFTER stubBackend on purpose: Playwright tries the most recently added route
 * first, so these win for the two prefixes they claim and stubBackend keeps everything else.
 *
 * WHAT IS DELIBERATELY ENGLISH IN THESE PAYLOADS. `tier_name`, `name`, `description`,
 * `status`, `user_type` and `account_status` are the BACKEND's words, and the interface renders
 * them as sent in both languages — translating a server's own message would be putting words in
 * its mouth. `the backend's own words are not translated, in either language` below asserts
 * that, and the package report records it as a gap a backend change has to close.
 */
interface AccountStubOptions {
  /** Overrides merged into the profile `/users/me` returns. */
  profile?: Record<string, unknown>;
  /** Whether `/auth/verify-reset-token/:token` accepts the token. Default: it does. */
  resetTokenValid?: boolean;
}

/** The backend's own description of a tier: English prose we do not rewrite. */
const TIER_DESCRIPTION = 'Everything in the free tier, plus every market';

/**
 * A timestamp with no offset on it, which is what this backend actually sends.
 *
 * `created_at` is a `DateTime` column written with `datetime.utcnow()`
 * (backend/app/models/base.py:34), and Pydantic serialises a naive datetime WITHOUT a zone. At
 * 21:00 UTC on 5 January the calendar date is the 5th in New York (the device) and the 6th in
 * Dubai (the choice), so this value separates the two bugs of FORMATTING: in the device's zone,
 * and in the device's locale.
 *
 * IT DOES NOT SEPARATE THE THIRD — reading the offset-less string in the device's zone instead
 * of as the UTC the server wrote. Against this pair the two readings are 06 Jan 01:00 and 06 Jan
 * 06:00 in Dubai: five hours apart, same calendar day, and the assertions here are on the date.
 * That bug is pinned separately, in a zone where the two readings fall on different days — see
 * "an offset-less timestamp is read as the UTC the server wrote" below.
 */
const JOINED_NAIVE = '2026-01-05T21:00:00';
/** The same instant, said properly. Used to prove the anchored path is not the same code path. */
const JOINED_ANCHORED = '2026-01-05T21:00:00Z';

async function stubAccount(page: Page, options: AccountStubOptions = {}): Promise<void> {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  const profile = {
    id: '00000000-0000-4000-8000-000000000001',
    email: 'qa.regular@predictions-local.dev',
    username: 'qa-regular',
    first_name: 'QA',
    last_name: 'Regular',
    avatar_url: null,
    user_type: 'regular',
    account_status: 'active',
    email_verified: true,
    created_at: JOINED_NAIVE,
    updated_at: JOINED_NAIVE,
    last_login_at: null,
    ...options.profile,
  };

  const features = {
    daily_predictions: 10,
    markets: ['1X2', 'BTTS'],
    history_days: 30,
    confidence_visible: true,
    expert_predictions: true,
    advanced_analytics: false,
    api_access: false,
    priority_support: false,
  };

  const subscription = {
    subscription_id: '00000000-0000-4000-8000-0000000000a1',
    user_id: profile.id,
    tier: 'basic',
    tier_name: 'Basic',
    status: 'active',
    price: 9.99,
    currency: 'USD',
    billing_period: 'month',
    features,
    starts_at: JOINED_NAIVE,
    ends_at: null,
    usage: { predictions_today: 3, predictions_limit: 10, predictions_remaining: 7 },
  };

  const tiers = [
    {
      tier: 'free',
      name: 'Free',
      description: TIER_DESCRIPTION,
      price: 0,
      currency: 'USD',
      billing_period: 'month',
      features: { ...features, daily_predictions: 1, history_days: 1 },
      is_current: false,
      is_popular: false,
      savings_percentage: 0,
    },
    {
      tier: 'basic',
      name: 'Basic',
      description: TIER_DESCRIPTION,
      price: 9.99,
      currency: 'USD',
      billing_period: 'month',
      features,
      is_current: true,
      is_popular: true,
      savings_percentage: 0,
    },
    {
      tier: 'pro',
      name: 'Pro',
      description: TIER_DESCRIPTION,
      price: 29.99,
      currency: 'USD',
      billing_period: 'month',
      features: { ...features, daily_predictions: null, history_days: null, api_access: true },
      is_current: false,
      is_popular: false,
      savings_percentage: 0,
    },
  ];

  await page.route('**/api/v1/users/**', (route: Route) => json(route, profile));
  await page.route('**/api/v1/subscriptions/**', (route: Route, request: Request) => {
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/tiers')) return json(route, tiers);
    return json(route, subscription);
  });
  await page.route('**/api/v1/auth/verify-reset-token/**', (route: Route) => (
    options.resetTokenValid === false
      ? json(route, { detail: 'Invalid or expired reset token' }, 400)
      : json(route, { valid: true, message: 'Token is valid' })
  ));
}

/**
 * The account screens, the URL each is reached at, and one string that proves it arrived.
 *
 * THE ANCHOR IS NOT DECORATION. "No text from the other catalogue" is derived from the
 * catalogues, so it can only ever see a string that is IN one — and before this package the
 * English on these forms was hard-coded in the JSX, where no generated check could reach it.
 * That check alone would therefore have passed on the broken page, which is precisely the shape
 * of false green this project has been bitten by twice. So each route also has to SHOW its own
 * language's heading and NOT show the other's, which fails the moment a `t()` call is replaced
 * by a literal again.
 */
const SIGNED_OUT_AUTH_ROUTES: Array<[string, keyof typeof en]> = [
  ['/login', 'auth.login.heading'],
  ['/register', 'auth.register.heading'],
  ['/forgot-password', 'auth.forgot.heading'],
  ['/reset-password?token=qa-token', 'auth.reset.heading'],
];
const SIGNED_IN_AUTH_ROUTES: Array<[string, keyof typeof en]> = [
  ['/profile', 'auth.profile.heading'],
  ['/password-change', 'auth.change.heading'],
  ['/subscription', 'auth.subscription.heading'],
];

/**
 * The heading this language must show, and the one it must not.
 *
 * Both sides are whitespace-normalised, because `bodyText` is: French puts a NO-BREAK space
 * before « ? » and the catalogue holds it as one, so a raw comparison of "Mot de passe oublié ?"
 * against the rendered text fails on an invisible character rather than on anything real.
 */
const flat = (value: string): string => value.replace(/\s+/g, ' ');

function assertHeading(text: string, key: keyof typeof en, language: 'en' | 'fr', route: string): void {
  const mine = flat(language === 'fr' ? fr[key] : (en[key] as string));
  const theirs = flat(language === 'fr' ? (en[key] as string) : fr[key]);
  expect(text, `${route} did not show its ${language} heading (${key})`).toContain(mine);
  if (mine !== theirs) {
    expect(text, `${route} in ${language} still shows the other language's heading`)
      .not.toContain(theirs);
  }
}

for (const language of ['en', 'fr'] as const) {
  /**
   * SIGN-IN WAS THE ONE FORM A FRENCH READER WAS GUARANTEED TO MEET AND THE ONE STILL ENTIRELY
   * IN ENGLISH. A save control sends a signed-out reader here, so the page most likely to be
   * their first was the page with none of their language on it. The reviewer reproduced the
   * French-to-English jump in the browser; this is the assertion that was missing.
   *
   * It is the same generated check the core journey uses — every catalogue string from the
   * other language, derived from the catalogues rather than listed by hand — applied to each of
   * the seven auth and account screens in turn.
   */
  test(`the auth and account screens are in ${language} and carry nothing from the other CATALOGUE`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);
    await stubAccount(page);

    for (const [route, heading] of SIGNED_OUT_AUTH_ROUTES) {
      await page.goto(route);
      await page.waitForLoadState('networkidle');
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      const text = await bodyText(page);
      expect(strays(text, language === 'fr' ? ENGLISH_ONLY : FRENCH_ONLY),
        `${route} in ${language} carried text from the other catalogue`).toEqual([]);
      assertHeading(text, heading, language, route);
      // And it is the screen this test thinks it is, not a redirect to somewhere emptier.
      expect(new URL(page.url()).pathname, `${route} did not stay put`)
        .toBe(new URL(route, 'http://localhost').pathname);
    }

    await signIn(page);
    for (const [route, heading] of SIGNED_IN_AUTH_ROUTES) {
      await page.goto(route);
      await page.waitForLoadState('networkidle');
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      const text = await bodyText(page);
      expect(strays(text, language === 'fr' ? ENGLISH_ONLY : FRENCH_ONLY),
        `${route} in ${language} carried text from the other catalogue`).toEqual([]);
      assertHeading(text, heading, language, route);
      expect(new URL(page.url()).pathname, `${route} redirected: is the session stub still good?`)
        .toBe(route);
    }
  });

  /**
   * The reset link that has expired, and the one that has not.
   *
   * Both states of this page exist and only one of them is reachable from the route above, so
   * both are visited. The expired one carries the sentence with the link's lifetime counted in
   * it — a number the page holds as a named constant and the catalogue counts, rather than a
   * digit written into two catalogues.
   */
  test(`both states of the reset screen are in ${language}`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);
    await stubAccount(page, { resetTokenValid: false });
    await page.goto('/reset-password?token=stale');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText(
      language === 'fr' ? fr['auth.reset.invalidHeading'] : en['auth.reset.invalidHeading'],
    )).toBeVisible();
    const text = await bodyText(page);
    expect(strays(text, language === 'fr' ? ENGLISH_ONLY : FRENCH_ONLY),
      `the expired-link screen in ${language} carried the other catalogue`).toEqual([]);
    // One hour, counted by the language's own rule rather than spelled out in the catalogue.
    expect(text).toContain(language === 'fr' ? '1 heure' : '1 hour');
    expect(text, 'a plural at one is the bug this package exists to remove')
      .not.toContain(language === 'fr' ? '1 heures' : '1 hours');
  });

  /**
   * THE SAVE-INTENT NOTICE, which is the reason a reader is on the sign-in form at all.
   *
   * Reached the way a reader reaches it — by pressing save on a fixture while signed out — so
   * this also proves the handoff still carries the label after the notice became one catalogue
   * sentence instead of three fragments in English word order.
   *
   * The fixture's own name inside it is the PROVIDER's and is not translated. What is
   * translated is the word joining the two clubs (`fixture.versus`), so the French notice reads
   * "… contre …" and the English "… versus …" — and the emphasis follows the name wherever the
   * sentence puts it.
   */
  test(`the save-intent notice on sign-in is in ${language}, with the fixture named as published`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);

    await page.goto('/predictions/today');
    await page.waitForLoadState('networkidle');
    await page.getByTestId('save-match-button').first().click();
    await page.waitForURL('**/login**');

    const notice = page.getByTestId('login-save-intent');
    await expect(notice).toBeVisible();
    const noticeText = (await notice.innerText()).replace(/\s+/g, ' ');

    // The whole sentence, in this language, with a real fixture in the hole.
    const joiner = language === 'fr' ? ' contre ' : ' versus ';
    expect(noticeText, 'the two clubs are joined by the word this language uses')
      .toContain(joiner);
    expect(strays(noticeText, language === 'fr' ? ENGLISH_ONLY : FRENCH_ONLY),
      'the notice carried text from the other catalogue').toEqual([]);

    // The club names are emphasised INSIDE the sentence, not bolted to the end of it: the run in
    // the span has to be a strict substring with catalogue text on at least one side of it.
    const emphasised = (await notice.locator('span').first().innerText()).trim();
    expect(emphasised, 'the fixture is what is picked out').toContain(joiner.trim());
    expect(noticeText.indexOf(emphasised), 'the sentence does not begin with the fixture')
      .toBeGreaterThan(0);
    expect(noticeText.endsWith(emphasised), 'nor end with it').toBe(false);

    /*
     * AND THE SENTENCE AROUND IT IS THIS LANGUAGE'S, character for character.
     *
     * The stray check above cannot see this one: the message carries a hole, and ENGLISH_ONLY
     * skips anything with ICU syntax in it because a template is not a literal. Without this
     * line the French notice could still be the English sentence with a French fixture name in
     * it — which is exactly what it was — and every assertion above would pass.
     */
    expect(noticeText, 'the notice is the catalogue sentence for this language').toBe(
      renderMessage(
        compileMessage((language === 'fr' ? FR : EN)['auth.saveIntent.signIn']),
        language,
        { match: emphasised },
      ).replace(/\s+/g, ' '),
    );
  });
}

/**
 * The backend's own words are the backend's own words.
 *
 * A tier's description is English prose the server sends, and it is rendered as sent on the
 * French page too. That is deliberate — a French paraphrase of a server's message would be
 * putting words in its mouth — and it is a real gap for a French reader, so it is asserted
 * rather than left for someone to discover. Closing it is a backend change.
 */
for (const language of ['en', 'fr'] as const) {
  test(`the backend's own words are not translated in ${language}`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);
    await stubAccount(page);
    await signIn(page);
    await page.goto('/subscription');
    await page.waitForLoadState('networkidle');
    const text = await bodyText(page);
    expect(text, `the server's description must survive into ${language} unchanged`)
      .toContain(TIER_DESCRIPTION);
  });
}

/**
 * Keys that are deliberately identical in both catalogues, each with its reason.
 *
 * The list is short and it is checked in both directions: an entry here that has since been
 * translated fails the test just as loudly as an entry missing from it that has not.
 */
const SAME_IN_BOTH_ON_PURPOSE: Record<string, string> = {
  // Product names are names, in any language.
  'app.name': 'the product name',
  'fixtureProvider.livescore': 'the provider\'s product name',
  // "minute"/"minutes" happen to be spelled the same in both languages. The PLURAL RULE behind
  // them is not the same, and that is what the message carries: French selects `one` at 0 as
  // well as at 1, so the same source text renders "0 minute" in French and "0 minutes" in
  // English. Identical strings, different output.
  'duration.minutes': 'the words coincide; the plural rules behind them do not',
  // Words French spells exactly as English does. Leaving them alone is the translation.
  'nav.expert': 'the same word in French',
  'source.expert': 'the same word in French',
  'provider.expert': 'the same word in French',
  'measured.sourceKind.expert': 'the same word in French',
  'filters.sources': 'the same word in French',
  // The French betting term is the English one, letter for letter.
  'selections.market.doubleChance': 'the same term in French',
  'filters.group.source': 'the same word in French',
  // "Clubs" is the French word too, plural included. The two alternatives beside it are not —
  // "National teams" is « Sélections » and "All" is « Tous » — so this is the only one of the
  // three that coincides, which is what makes leaving it alone a translation rather than a gap.
  'filters.kind.club': 'the same word in French',
};

/**
 * THE AREAS CLAIM NO KEY TWICE.
 *
 * ./messages/en.ts composes four area modules with a spread, and a spread resolves a duplicate
 * silently by taking the last one. Three packages are writing into this catalogue at the same
 * time; the way that goes wrong is two of them choosing the same key and one of them quietly
 * losing, on a page nobody in that package is looking at. This is the only place that can see
 * it, because by the time the catalogue is composed the collision is gone.
 */
test('the four catalogue areas claim no key twice', () => {
  const areas: Array<[string, Record<string, string>]> = [
    ['core', coreEn as Record<string, string>],
    ['auth', authEn as Record<string, string>],
    ['expert', expertEn as Record<string, string>],
    ['reader', readerEn as Record<string, string>],
  ];
  const owner = new Map<string, string>();
  const clashes: string[] = [];
  for (const [name, area] of areas) {
    for (const key of Object.keys(area)) {
      const already = owner.get(key);
      if (already) clashes.push(`${key}: claimed by ${already} and by ${name}`);
      else owner.set(key, name);
    }
  }
  expect(clashes, 'two areas define the same key; the spread in en.ts silently picks one')
    .toEqual([]);

  // And the composition holds exactly what the areas hold — no key added directly to en.ts,
  // where the per-area French typing could never see it.
  expect(Object.keys(en).sort()).toEqual([...owner.keys()].sort());
});

test('the two catalogues hold the same keys, and no French entry is still its English', () => {
  // `Catalog` in src/i18n/messages/types.ts makes the first half a compile error rather than a
  // test failure; asserting it here as well costs nothing and states the guarantee out loud.
  expect(Object.keys(fr).sort()).toEqual(Object.keys(en).sort());

  const untranslated = (Object.keys(en) as Array<keyof typeof en>)
    .filter(key => en[key] === fr[key])
    .filter(key => !(key in SAME_IN_BOTH_ON_PURPOSE))
    // Pure interpolation — "{relative}, {date}", "{description} — {suffix}" — has no words in it
    // to translate, so sameness says nothing. Anything with real text in it is still checked.
    .filter(key => (en[key] as string).replace(/\{[^}]*\}/g, '').replace(/[^\p{L}]/gu, '').length >= 3);
  expect(untranslated, 'these keys are still their English in the French catalogue').toEqual([]);

  // And the other direction: an allowance that is no longer needed is a comment that has gone
  // stale, which is how a list like this stops meaning anything.
  const needlessly = Object.keys(SAME_IN_BOTH_ON_PURPOSE)
    .filter(key => en[key as keyof typeof en] !== fr[key as keyof typeof en]);
  expect(needlessly, 'these are now translated and no longer need an exemption').toEqual([]);
});

test('the language a reader chose survives a reload, and the other one does not come back', async ({ page }) => {
  await stubBackend(page);
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  // Through the control a reader actually has, not by writing storage: the point of the test is
  // that pressing the button is what persists.
  await page.getByTestId('footer-region-settings').first().click();
  await page.getByTestId('language-choice-fr').first().click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr');
  expect(await page.evaluate(k => window.localStorage.getItem(k), LANGUAGE_KEY)).toBe('fr');

  // And the page is French from the first frame, not English that turns into French: the
  // catalogue is awaited before anything is drawn.
  const text = await bodyText(page);
  expect(strays(text, ENGLISH_ONLY)).toEqual([]);
});

test('language, time zone and country are three separate choices', async ({ page }) => {
  // Dubai, not New York: New York is the device's own zone, so it would be on the page whether
  // the choice was honoured or discarded. Dubai is neither the device's zone nor a French one.
  await seedPreferences(page, { language: 'fr', zone: DUBAI });
  await stubBackend(page);
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  // French did not move the reader to a French zone, a Gulf zone did not put the page into
  // English or Arabic, and the device's New York did not override the choice. Nothing stores a
  // country.
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr');
  await expect(page.getByTestId('matchday-zone')).toContainText('Dubai');
  await expect(page.getByTestId('matchday-zone')).not.toContainText('New York');
  const keys = await page.evaluate(() => Object.keys(window.localStorage));
  expect(keys.filter(key => /country|region|nation/i.test(key))).toEqual([]);

  // And the page says so, rather than leaving the reader to work it out from the behaviour.
  await page.getByTestId('footer-region-settings').first().click();
  await expect(page.getByTestId('settings-independent').first()).toBeVisible();
});

/* ============================================ measured sentences, which fragments cannot build */

test('a measured sentence is one sentence in French, not English fragments', async ({ page }) => {
  await seedPreferences(page, { language: 'fr', zone: DOUALA });
  // Every fixture in the captured day is scheduled and none has been played, so the workspace's
  // footnote takes the "none of these has been played" branch with a plural count.
  await stubBackend(page, { day: iso => dayPayload(iso) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const footnote = page.getByTestId('matchday-footnote');
  await expect(footnote).toBeVisible();
  const text = (await footnote.innerText()).replace(/\s+/g, ' ');

  // The agreement that a fragment-based translation gets wrong: the determiner and the pronoun
  // agree with a noun that has not appeared yet, and the negation wraps the verb.
  expect(text).toMatch(/Aucun des \d+ matchs listés ici n’a encore été joué/);
  // And not a word of the English assembly survives.
  expect(text).not.toMatch(/fixture|listed here|has been played/i);
});

test('a French page counts one as singular where the English rule would not', async ({ page }) => {
  await seedPreferences(page, { language: 'fr', zone: DOUALA });

  // ONE fixture in the day, and it carries no model forecast; the filter insists on one. The
  // empty state's sentence counts what the day holds, so the count it is given is exactly 1 —
  // the value English and French disagree about least obviously and get wrong most often.
  //
  // This is the RENDERED page, which is all a browser test can add: that the count reaching the
  // message is the real one and the sentence on screen is the one the catalogue produces. The
  // rule itself — every count-bearing string at 0, 1, 2 and 11, in both languages — is pinned
  // by the table below, because no captured day can produce all of those counts.
  const single = (iso: string) => dayPayload(iso, [
    withoutForecast(fixtureAt(`${iso}T14:00:00Z`, 'Coton Sport', 'Union Douala', 'single-fixture')),
  ]);
  await stubBackend(page, { day: iso => single(iso) });

  await page.goto('/matches?source=model');
  await page.waitForLoadState('networkidle');

  const empty = page.getByTestId('matchday-filtered-empty');
  await expect(empty).toBeVisible();
  const text = (await empty.innerText()).replace(/\s+/g, ' ');
  // "1 match est enregistré", never "1 matchs sont enregistrés" — and never the English rule
  // applied to a French noun.
  expect(text).toMatch(/1 match est enregistré/);
  expect(text).not.toMatch(/1 matchs/);
});

/* ===================================================== every count, in the language's own rule */

/**
 * THE PLURAL CASES, WRITTEN OUT.
 *
 * WHY A TABLE AND NOT A PAGE. The browser tests below reach a handful of these sentences with
 * whatever count the captured day happens to hold — one fixture here, twelve there. That is how
 * five agreement errors shipped on the home page while every localisation test was green:
 * "0 réglés", "1 réglés", "1 pronostics réglés", "calculable pour 0 pronostics" and "{count}
 * compétition(s)" all live on counts no test happened to produce. Asserting one sample and
 * hoping is not a test of a plural rule; the rule has to be exercised at the values it turns on.
 *
 * SO EVERY COUNT-BEARING FRENCH STRING IS RENDERED HERE AT 0, 1, 2 AND 11, and its exact output
 * is written down. 0 and 1 are where French and English part company (French puts both with the
 * singular); 2 is the first plural; 11 is a plural far enough from 1 that a message built by
 * appending "s" to a stem still passes and a message with the wrong stem does not.
 *
 * THE LIST CANNOT GO STALE. `every message with a plural is in the table above` below fails if a
 * catalogue entry grows a plural and no case is added for it, so the next person cannot add a
 * counting sentence that nothing checks.
 *
 * WHAT IT DOES NOT CLAIM. Not that the French reads well — no test can say that, and the
 * catalogue says in as many words that no native speaker has reviewed it. Only that the FORM is
 * the one the language's own rule produces at each count.
 */

/** Values the catalogue receives already formatted, exactly as the components hand them over. */
const grouped = (n: number): string => new Intl.NumberFormat('fr').format(n);

const COUNTS = [0, 1, 2, 11] as const;

interface CountCase {
  key: keyof typeof en;
  params: (n: number) => Record<string, string | number>;
  /** The expected French at 0, 1, 2 and 11, in that order. */
  fr: [string, string, string, string];
}

const COUNT_CASES: CountCase[] = [
  // ── the selections area (reader) ──────────────────────────────────────────────────────────
  {
    key: 'selections.dock.count',
    params: (n: number) => ({ count: n }),
    fr: ['0 sélection', '1 sélection', '2 sélections', '11 sélections'],
  },
  {
    key: 'selections.copy.count',
    params: (n: number) => ({ count: n }),
    fr: ['0 sélection', '1 sélection', '2 sélections', '11 sélections'],
  },
  {
    key: 'selections.suggest.ageHours',
    params: (n: number) => ({ count: n }),
    fr: ['0 heure', '1 heure', '2 heures', '11 heures'],
  },
  {
    key: 'selections.suggest.days',
    params: (n: number) => ({ count: n }),
    fr: ['0 prochain jour', '1 prochain jour', '2 prochains jours', '11 prochains jours'],
  },
  {
    key: 'selections.dock.combinedPriceMissing',
    params: (n: number) => ({ count: n }),
    fr: [
      'Pas de cote combinée\u00a0: une sélection n’a pas de cote. Saisissez les cotes de votre bookmaker.',
      'Pas de cote combinée\u00a0: une sélection n’a pas de cote. Saisissez les cotes de votre bookmaker.',
      'Pas de cote combinée\u00a0: 2 sélections n’ont pas de cote. Saisissez les cotes de votre bookmaker.',
      'Pas de cote combinée\u00a0: 11 sélections n’ont pas de cote. Saisissez les cotes de votre bookmaker.',
    ],
  },
  {
    // Rendered only above zero; the form at 0 is the `one` form French selects there.
    key: 'selections.dock.handoffRefused',
    params: (n: number) => ({ count: n, reasons: 'coup d’envoi donné' }),
    fr: [
      'Une sélection de ce navigateur n’a pas pu être ajoutée à votre compte\u00a0: coup d’envoi donné',
      'Une sélection de ce navigateur n’a pas pu être ajoutée à votre compte\u00a0: coup d’envoi donné',
      '2 sélections de ce navigateur n’ont pas pu être ajoutées à votre compte\u00a0: coup d’envoi donné',
      '11 sélections de ce navigateur n’ont pas pu être ajoutées à votre compte\u00a0: coup d’envoi donné',
    ],
  },
  {
    key: 'duration.minutes',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 minute',
      '1 minute',
      '2 minutes',
      '11 minutes',
    ],
  },
  {
    key: 'duration.hours',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 heure',
      '1 heure',
      '2 heures',
      '11 heures',
    ],
  },
  {
    key: 'duration.days',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 jour',
      '1 jour',
      '2 jours',
      '11 jours',
    ],
  },
  {
    key: 'matchday.filteredEmptyDescription',
    params: (n: number) => ({ count: n, date: '15 juin 2026' }),
    fr: [
      '0 match est enregistré pour le 15 juin 2026\u00a0; aucun ne correspond à tous les filtres que vous avez posés.',
      '1 match est enregistré pour le 15 juin 2026\u00a0; aucun ne correspond à tous les filtres que vous avez posés.',
      '2 matchs sont enregistrés pour le 15 juin 2026\u00a0; aucun ne correspond à tous les filtres que vous avez posés.',
      '11 matchs sont enregistrés pour le 15 juin 2026\u00a0; aucun ne correspond à tous les filtres que vous avez posés.',
    ],
  },
  {
    /*
      The international-break note. Its `=0` branch is written out here and is unreachable on
      screen — the note renders only where at least one national-team fixture was listed — but a
      branch nothing renders is exactly the branch a plural rule is got wrong in, and the table
      is the only place that can see it.
    */
    key: 'matchday.nationalTeamDay',
    params: (n: number) => ({ count: n }),
    fr: [
      'Aucun match n’est enregistré à cette date. Aucun match de club n’est enregistré à cette date.',
      'Le seul match enregistré à cette date est un match de sélections nationales. Aucun match de club n’est enregistré à cette date.',
      'Les 2 matchs enregistrés à cette date sont tous des matchs de sélections nationales. Aucun match de club n’est enregistré à cette date.',
      'Les 11 matchs enregistrés à cette date sont tous des matchs de sélections nationales. Aucun match de club n’est enregistré à cette date.',
    ],
  },
  {
    key: 'matchday.scoring.nonePlayed',
    params: (n: number) => ({ count: n }),
    fr: [
      'Aucun match n’est listé ici, donc rien sur cette page n’a été comparé à un résultat et aucune exactitude n’y est revendiquée.',
      'Le match listé ici n’a pas encore été joué, donc rien sur cette page n’a été comparé à un résultat et aucune exactitude n’y est revendiquée.',
      'Aucun des 2 matchs listés ici n’a encore été joué, donc rien sur cette page n’a été comparé à un résultat et aucune exactitude n’y est revendiquée.',
      'Aucun des 11 matchs listés ici n’a encore été joué, donc rien sur cette page n’a été comparé à un résultat et aucune exactitude n’y est revendiquée.',
    ],
  },
  {
    key: 'matchday.scoring.allPlayed',
    params: (n: number) => ({ count: n, verb: 'finished' }),
    fr: [
      'Aucun match n’est listé ici. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',
      'Le match listé ici est terminé. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',
      'Les 2 matchs listés ici sont terminés. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',
      'Les 11 matchs listés ici sont terminés. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',
    ],
  },
  {
    key: 'matchday.scoring.somePlayed',
    params: (n: number) => ({ started: n, total: 12, verb: 'kickedOff' }),
    fr: [
      '0 des 12 matchs listés ici a commencé. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',
      '1 des 12 matchs listés ici a commencé. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',
      '2 des 12 matchs listés ici ont commencé. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',
      '11 des 12 matchs listés ici ont commencé. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',
    ],
  },
  {
    key: 'matchday.seeAll',
    params: (n: number) => ({ count: n }),
    fr: [
      'Voir le match',
      'Voir le match',
      'Voir les 2 matchs',
      'Voir les 11 matchs',
    ],
  },
  {
    key: 'dateStrip.dayMatches',
    params: (n: number) => ({ count: n }),
    fr: [
      ', 0 match',
      ', 1 match',
      ', 2 matchs',
      ', 11 matchs',
    ],
  },
  {
    key: 'filters.countApplied',
    params: (n: number) => ({ count: n }),
    fr: [
      ', 0 filtre appliqué',
      ', 1 filtre appliqué',
      ', 2 filtres appliqués',
      ', 11 filtres appliqués',
    ],
  },
  {
    key: 'filters.resultCount',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 match',
      '1 match',
      '2 matchs',
      '11 matchs',
    ],
  },
  {
    key: 'fixture.groupCount',
    params: (n: number) => ({ count: n }),
    fr: [
      ' match',
      ' match',
      ' matchs',
      ' matchs',
    ],
  },
  {
    key: 'brief.staleDetailWithLimit',
    params: (n: number) => ({ hours: n }),
    fr: [
      'Cette prévision est plus ancienne que la limite de fraîcheur (limite\u00a0: 0 heure).',
      'Cette prévision est plus ancienne que la limite de fraîcheur (limite\u00a0: 1 heure).',
      'Cette prévision est plus ancienne que la limite de fraîcheur (limite\u00a0: 2 heures).',
      'Cette prévision est plus ancienne que la limite de fraîcheur (limite\u00a0: 11 heures).',
    ],
  },
  {
    key: 'freshness.nextAttempt.overdueMinutes',
    params: (n: number) => ({ count: n }),
    fr: [
      'La prochaine tentative a 0 minute de retard.',
      'La prochaine tentative a 1 minute de retard.',
      'La prochaine tentative a 2 minutes de retard.',
      'La prochaine tentative a 11 minutes de retard.',
    ],
  },
  {
    key: 'freshness.nextAttempt.overdueHours',
    params: (n: number) => ({ count: n }),
    fr: [
      'La prochaine tentative a 0 heure de retard.',
      'La prochaine tentative a 1 heure de retard.',
      'La prochaine tentative a 2 heures de retard.',
      'La prochaine tentative a 11 heures de retard.',
    ],
  },
  {
    key: 'freshness.nextAttempt.overdueDays',
    params: (n: number) => ({ count: n }),
    fr: [
      'La prochaine tentative a 0 jour de retard.',
      'La prochaine tentative a 1 jour de retard.',
      'La prochaine tentative a 2 jours de retard.',
      'La prochaine tentative a 11 jours de retard.',
    ],
  },
  {
    key: 'freshness.backoff.afterMany',
    params: (n: number) => ({ count: n, window: '30 minutes' }),
    fr: [
      'Après 0 échec consécutif, attente de 30 minutes avant une nouvelle tentative.',
      'Après 1 échec consécutif, attente de 30 minutes avant une nouvelle tentative.',
      'Après 2 échecs consécutifs, attente de 30 minutes avant une nouvelle tentative.',
      'Après 11 échecs consécutifs, attente de 30 minutes avant une nouvelle tentative.',
    ],
  },
  {
    key: 'forecastSync.pausedDeferred',
    params: (n: number) => ({ provider: 'GameForecast', count: n }),
    fr: [
      'L’actualisation de GameForecast est en pause\u00a0; 0 compétition attend la prochaine réinitialisation du quota',
      'L’actualisation de GameForecast est en pause\u00a0; 1 compétition attend la prochaine réinitialisation du quota',
      'L’actualisation de GameForecast est en pause\u00a0; 2 compétitions attendent la prochaine réinitialisation du quota',
      'L’actualisation de GameForecast est en pause\u00a0; 11 compétitions attendent la prochaine réinitialisation du quota',
    ],
  },
  {
    key: 'banner.moreDetails',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 détail de fournisseur supplémentaire',
      '1 détail de fournisseur supplémentaire',
      '2 détails de fournisseur supplémentaires',
      '11 détails de fournisseur supplémentaires',
    ],
  },
  {
    key: 'measured.excluded.pushes',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 égalité',
      '1 égalité',
      '2 égalités',
      '11 égalités',
    ],
  },
  {
    key: 'measured.excluded.voids',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 annulé',
      '1 annulé',
      '2 annulés',
      '11 annulés',
    ],
  },
  {
    key: 'measured.excluded.notScored',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 non calculable',
      '1 non calculable',
      '2 non calculables',
      '11 non calculables',
    ],
  },
  {
    key: 'measured.counts',
    params: (n: number) => ({ eligible: n, parts: '…' }),
    fr: [
      '0 éligible · …',
      '1 éligible · …',
      '2 éligibles · …',
      '11 éligibles · …',
    ],
  },
  {
    key: 'measured.counts.scored',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 réglé',
      '1 réglé',
      '2 réglés',
      '11 réglés',
    ],
  },
  {
    key: 'measured.counts.pending',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 en attente de règlement',
      '1 en attente de règlement',
      '2 en attente de règlement',
      '11 en attente de règlement',
    ],
  },
  {
    key: 'measured.counts.void',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 annulé',
      '1 annulé',
      '2 annulés',
      '11 annulés',
    ],
  },
  {
    key: 'measured.counts.notScored',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 non calculable',
      '1 non calculable',
      '2 non calculables',
      '11 non calculables',
    ],
  },
  {
    key: 'measured.state.measured',
    params: (n: number) => ({ measured: n, total: 4 }),
    fr: [
      '0 source sur 4 a un bilan mesuré.',
      '1 source sur 4 a un bilan mesuré.',
      '2 sources sur 4 ont un bilan mesuré.',
      '11 sources sur 4 ont un bilan mesuré.',
    ],
  },
  {
    key: 'measured.hitRate',
    params: (n: number) => ({ sample: grouped(n) }),
    fr: [
      'de taux de réussite sur 0 réglé',
      'de taux de réussite sur 1 réglé',
      'de taux de réussite sur 2 réglés',
      'de taux de réussite sur 11 réglés',
    ],
  },
  {
    key: 'measured.needMore',
    params: (n: number) => ({ sample: grouped(n), minimum: '30' }),
    fr: [
      '0 pronostic réglé sur 30 nécessaires avant la publication d’un taux.',
      '1 pronostic réglé sur 30 nécessaires avant la publication d’un taux.',
      '2 pronostics réglés sur 30 nécessaires avant la publication d’un taux.',
      '11 pronostics réglés sur 30 nécessaires avant la publication d’un taux.',
    ],
  },
  {
    key: 'measured.sampleSizeValue',
    params: (n: number) => ({ count: n }),
    fr: [
      'pronostic réglé',
      'pronostic réglé',
      'pronostics réglés',
      'pronostics réglés',
    ],
  },
  {
    key: 'measured.brierWithheld',
    params: (n: number) => ({ sample: grouped(n), minimum: '30' }),
    fr: [
      'calculable pour 0 pronostic à ce jour\u00a0; 30 sont nécessaires avant la publication d’un score de Brier',
      'calculable pour 1 pronostic à ce jour\u00a0; 30 sont nécessaires avant la publication d’un score de Brier',
      'calculable pour 2 pronostics à ce jour\u00a0; 30 sont nécessaires avant la publication d’un score de Brier',
      'calculable pour 11 pronostics à ce jour\u00a0; 30 sont nécessaires avant la publication d’un score de Brier',
    ],
  },
  {
    key: 'measured.notScoredReason',
    // `_n` unused on purpose: this one is invariable, and the four identical rows below are the
    // statement that it is. See "the strings their component gives no count to do not inflect".
    params: (_n: number) => ({ reason: 'le résultat final manque' }),
    fr: [
      'sans règlement — le résultat final manque',
      'sans règlement — le résultat final manque',
      'sans règlement — le résultat final manque',
      'sans règlement — le résultat final manque',
    ],
  },
  {
    key: 'home.coverageStored',
    params: (n: number) => ({ fixtures: grouped(n), competitions: grouped(n) }),
    fr: [
      '0 match à venir enregistré dans 0 compétition.',
      '1 match à venir enregistré dans 1 compétition.',
      '2 matchs à venir enregistrés dans 2 compétitions.',
      '11 matchs à venir enregistrés dans 11 compétitions.',
    ],
  },
  {
    key: 'home.coverageForecasts',
    params: (n: number) => ({ withForecast: grouped(n), without: grouped(n) }),
    fr: [
      '0 d’entre eux porte une prévision du modèle\u00a0; aucun n’en est dépourvu.',
      '1 d’entre eux porte une prévision du modèle\u00a0; l’autre n’en a aucune.',
      '2 d’entre eux portent une prévision du modèle\u00a0; les 2 autres n’en ont aucune.',
      '11 d’entre eux portent une prévision du modèle\u00a0; les 11 autres n’en ont aucune.',
    ],
  },
  {
    key: 'home.coverageExperts',
    params: (n: number) => ({ count: grouped(n) }),
    fr: [
      '0 pronostic d’expert a été publié.',
      '1 pronostic d’expert a été publié.',
      '2 pronostics d’experts ont été publiés.',
      '11 pronostics d’experts ont été publiés.',
    ],
  },
  {
    key: 'home.stat.forecastsDetailOf',
    params: (n: number) => ({ total: grouped(n) }),
    fr: [
      'Sur 0 match à venir enregistré\u00a0; les autres n’ont aucune prévision du modèle rattachée',
      'Sur 1 match à venir enregistré\u00a0; les autres n’ont aucune prévision du modèle rattachée',
      'Sur 2 matchs à venir enregistrés\u00a0; les autres n’ont aucune prévision du modèle rattachée',
      'Sur 11 matchs à venir enregistrés\u00a0; les autres n’ont aucune prévision du modèle rattachée',
    ],
  },
  {
    key: 'search.teams',
    params: (n: number) => ({ count: n }),
    fr: [
      'Équipes (0)',
      'Équipes (1)',
      'Équipes (2)',
      'Équipes (11)',
    ],
  },
  {
    key: 'search.leagues',
    params: (n: number) => ({ count: n }),
    fr: [
      'Compétitions (0)',
      'Compétitions (1)',
      'Compétitions (2)',
      'Compétitions (11)',
    ],
  },
  {
    key: 'matchday.moreCompetitions',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 de plus',
      '1 de plus',
      '2 de plus',
      '11 de plus',
    ],
  },
  {
    // "sur", not "sur ces". The demonstrative has to agree with the count that follows it, so
    // "sur ces" renders "1 sur ces 1" on any market holding exactly one scored prediction — the
    // commonest state on a young installation. "X sur Y" is the ordinary French ratio and is
    // correct at every count. The scored side is exercised at 1 below for exactly that reason.
    key: 'measured.hitCount',
    params: (n: number) => ({ hits: n, scored: 12 }),
    fr: [
      '0 sur 12',
      '1 sur 12',
      '2 sur 12',
      '11 sur 12',
    ],
  },
  {
    // The half that was wrong: one scored prediction. This is the case the demonstrative broke.
    key: 'measured.hitCount',
    params: (n: number) => ({ hits: n, scored: 1 }),
    fr: [
      '0 sur 1',
      '1 sur 1',
      '2 sur 1',
      '11 sur 1',
    ],
  },

  /* ---------------------------------------------- the auth and account screens */

  /*
   * Four of these count something that used to be a digit written into a sentence: the minimum
   * password length, how long a reset link lasts, a tier's daily allowance and its history
   * window. Each is now a value the page passes in from the payload or from a named constant,
   * which is what lets the sentence agree — and "1 predictions/day" and "1 days history" were
   * wrong in English too, not only untranslatable.
   */
  {
    key: 'auth.validation.tooShortLong',
    params: (n: number) => ({ count: n }),
    fr: [
      'Le mot de passe doit comporter au moins 0 caractère',
      'Le mot de passe doit comporter au moins 1 caractère',
      'Le mot de passe doit comporter au moins 2 caractères',
      'Le mot de passe doit comporter au moins 11 caractères',
    ],
  },
  {
    key: 'auth.validation.tooShort',
    params: (n: number) => ({ count: n }),
    fr: [
      'Le mot de passe doit comporter au moins 0 caractère',
      'Le mot de passe doit comporter au moins 1 caractère',
      'Le mot de passe doit comporter au moins 2 caractères',
      'Le mot de passe doit comporter au moins 11 caractères',
    ],
  },
  {
    key: 'auth.reset.invalidBody',
    params: (n: number) => ({ hours: n }),
    fr: [
      'Ce lien de réinitialisation est invalide ou a expiré. Les liens de réinitialisation ne sont valables que 0 heure.',
      'Ce lien de réinitialisation est invalide ou a expiré. Les liens de réinitialisation ne sont valables que 1 heure.',
      'Ce lien de réinitialisation est invalide ou a expiré. Les liens de réinitialisation ne sont valables que 2 heures.',
      'Ce lien de réinitialisation est invalide ou a expiré. Les liens de réinitialisation ne sont valables que 11 heures.',
    ],
  },
  {
    key: 'auth.reset.newPasswordPlaceholder',
    params: (n: number) => ({ count: n }),
    fr: [
      'Saisissez un nouveau mot de passe (0 caractère minimum)',
      'Saisissez un nouveau mot de passe (1 caractère minimum)',
      'Saisissez un nouveau mot de passe (2 caractères minimum)',
      'Saisissez un nouveau mot de passe (11 caractères minimum)',
    ],
  },
  {
    key: 'auth.change.rules',
    params: (n: number) => ({ count: n }),
    fr: [
      'Doit comporter au moins 0 caractère, dont une majuscule, une minuscule et un chiffre',
      'Doit comporter au moins 1 caractère, dont une majuscule, une minuscule et un chiffre',
      'Doit comporter au moins 2 caractères, dont une majuscule, une minuscule et un chiffre',
      'Doit comporter au moins 11 caractères, dont une majuscule, une minuscule et un chiffre',
    ],
  },
  {
    key: 'auth.subscription.predictionsPerDay',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 pronostic/jour',
      '1 pronostic/jour',
      '2 pronostics/jour',
      '11 pronostics/jour',
    ],
  },
  {
    key: 'auth.subscription.historyDays',
    params: (n: number) => ({ count: n }),
    fr: [
      '0 jour d’historique',
      '1 jour d’historique',
      '2 jours d’historique',
      '11 jours d’historique',
    ],
  },
  {
    /*
     * How often the provider answered without a result, on a fixture the backend has stopped
     * asking about.
     *
     * Zero never reaches the page — the notice is only rendered when `attempts` is above it, and
     * a fixture retired with nothing answered would be a claim about a chase that never
     * happened — but it is rendered here anyway, because the only way to know a French plural is
     * right at one is to see what it does at zero, where French and English disagree.
     */
    key: 'fixture.result.attempts',
    params: (n: number) => ({ count: n }),
    fr: [
      'Le fournisseur a répondu une fois sans résultat pour ce match.',
      'Le fournisseur a répondu une fois sans résultat pour ce match.',
      'Le fournisseur a répondu 2 fois sans résultat pour ce match.',
      'Le fournisseur a répondu 11 fois sans résultat pour ce match.',
    ],
  },
];

/**
 * The same seven, in English — because four of them changed the English too.
 *
 * "1 predictions/day", "1 days history", "min. 1 characters" and "valid for 1 hours" were what
 * this interface printed before this package; they were frozen at the plural because the count
 * was interpolated into a fixed string. Fixing the French would not have fixed those, and a
 * table that only checks French would not have noticed either way.
 */
const ENGLISH_COUNT_CASES: Array<{ key: keyof typeof en; params: (n: number) => Record<string, string | number>; en: [string, string, string, string] }> = [
  {
    // The international-break note. Its `=0` branch is unreachable on screen — the note renders
    // only where at least one national-team fixture was listed — and is written out here because
    // a branch nothing renders is the branch a plural rule is got wrong in.
    key: 'matchday.nationalTeamDay',
    params: (n: number) => ({ count: n }),
    en: [
      'No fixture is stored for this date. No club fixture is stored for this date.',
      'The one fixture stored for this date is a national-team fixture. No club fixture is stored for this date.',
      'All 2 fixtures stored for this date are national-team fixtures. No club fixture is stored for this date.',
      'All 11 fixtures stored for this date are national-team fixtures. No club fixture is stored for this date.',
    ],
  },
  {
    key: 'auth.validation.tooShortLong',
    params: (n: number) => ({ count: n }),
    en: [
      'Password must be at least 0 characters long',
      'Password must be at least 1 character long',
      'Password must be at least 2 characters long',
      'Password must be at least 11 characters long',
    ],
  },
  {
    key: 'auth.reset.invalidBody',
    params: (n: number) => ({ hours: n }),
    en: [
      'This password reset link is invalid or has expired. Reset links are only valid for 0 hours.',
      'This password reset link is invalid or has expired. Reset links are only valid for 1 hour.',
      'This password reset link is invalid or has expired. Reset links are only valid for 2 hours.',
      'This password reset link is invalid or has expired. Reset links are only valid for 11 hours.',
    ],
  },
  {
    key: 'auth.subscription.predictionsPerDay',
    params: (n: number) => ({ count: n }),
    en: [
      '0 predictions/day',
      '1 prediction/day',
      '2 predictions/day',
      '11 predictions/day',
    ],
  },
  {
    key: 'auth.subscription.historyDays',
    params: (n: number) => ({ count: n }),
    en: [
      '0 days history',
      '1 day history',
      '2 days history',
      '11 days history',
    ],
  },
];

/** Both catalogues under one type, so a message can be rendered from either by key. */
type Catalogue = Record<keyof typeof en, string>;
const EN: Catalogue = en;
const FR: Catalogue = fr;

/** One message, compiled and rendered exactly the way src/i18n/index.ts renders it. */
function render(
  catalogue: Catalogue,
  locale: 'en' | 'fr',
  key: keyof typeof en,
  params: Record<string, string | number> = {},
): string {
  return renderMessage(compileMessage(catalogue[key]), locale, params);
}

test('every count-bearing French string has the right form at 0, 1, 2 and 11', () => {
  // Collected rather than thrown on the first miss: when a plural rule is misapplied it is
  // usually misapplied in several places at once, and a reviewer should see all of them.
  const wrong: Array<{ at: string; expected: string; actual: string }> = [];
  for (const testCase of COUNT_CASES) {
    COUNTS.forEach((count, index) => {
      const actual = render(FR, 'fr', testCase.key, testCase.params(count));
      if (actual !== testCase.fr[index]) {
        wrong.push({ at: `${testCase.key} at ${count}`, expected: testCase.fr[index], actual });
      }
    });
  }
  expect(wrong, 'these French messages render the wrong form at these counts').toEqual([]);
});

test('the English counts this package changed are right at 0, 1, 2 and 11', () => {
  const wrong: Array<{ at: string; expected: string; actual: string }> = [];
  for (const testCase of ENGLISH_COUNT_CASES) {
    COUNTS.forEach((count, index) => {
      const actual = render(EN, 'en', testCase.key, testCase.params(count));
      if (actual !== testCase.en[index]) {
        wrong.push({ at: `${testCase.key} at ${count}`, expected: testCase.en[index], actual });
      }
    });
  }
  expect(wrong, 'these English messages render the wrong form at these counts').toEqual([]);
});

test('every message with a plural is in the table above', () => {
  const covered = new Set<string>(COUNT_CASES.map(testCase => testCase.key));
  const uncovered = (Object.keys(FR) as Array<keyof typeof en>)
    .filter(key => /,\s*plural\s*,/.test(FR[key]))
    .filter(key => !covered.has(key));
  expect(uncovered, 'these French messages count something and nothing renders them at 0, 1, 2 and 11')
    .toEqual([]);
});

/**
 * The rule itself, stated against English so the difference is on the record.
 *
 * `duration.minutes` is the sharpest case in the catalogue: both catalogues hold the SAME source
 * string, character for character, and render different words at zero. That is the whole
 * argument for `Intl.PluralRules` over a written-out suffix, in one line — and it was asserted
 * only in a comment in this file until now, which is to say not asserted at all.
 */
test('French puts zero with the singular and English puts it with the plural', () => {
  expect(FR['duration.minutes'], 'the two catalogues must still hold the same source here')
    .toBe(EN['duration.minutes']);
  expect(render(EN, 'en', 'duration.minutes', { count: 0 })).toBe('0 minutes');
  expect(render(FR, 'fr', 'duration.minutes', { count: 0 })).toBe('0 minute');

  // And at one, where English agrees with French and a naive pluraliser looks correct.
  expect(render(EN, 'en', 'duration.minutes', { count: 1 })).toBe('1 minute');
  expect(render(FR, 'fr', 'duration.minutes', { count: 1 })).toBe('1 minute');

  // The same divergence in a whole sentence, where a verb and a participle follow the noun.
  const stored = (catalogue: Catalogue, locale: 'en' | 'fr') =>
    render(catalogue, locale, 'matchday.filteredEmptyDescription', { count: 0, date: '15 juin 2026' });
  expect(stored(EN, 'en')).toContain('0 fixtures are stored');
  expect(stored(FR, 'fr')).toContain('0 match est enregistré');
  expect(stored(FR, 'fr')).not.toContain('0 matchs');
});

/**
 * A count that arrives already formatted still chooses the right branch.
 *
 * Several components format a figure before handing it over, so the catalogue receives "1 234"
 * rather than 1234 — and `Number("1 234")` is NaN. Before src/i18n/format.ts learned to read a
 * formatted number back with the locale's own separators, a plural keyed on one of those printed
 * `{sample}` on the page the moment a sample passed a thousand: right in every test written with
 * small numbers, broken on the installation that grew. `#` prints back the identical string the
 * caller passed in, group separator and all.
 */
test('a count handed over already formatted still selects its branch, and prints back unchanged', () => {
  const groupedMany = grouped(1234);
  expect(groupedMany, 'French groups thousands, so this is not simply "1234"').not.toBe('1234');

  expect(render(FR, 'fr', 'measured.needMore', { sample: grouped(1), minimum: '30' }))
    .toBe('1 pronostic réglé sur 30 nécessaires avant la publication d’un taux.');
  expect(render(FR, 'fr', 'measured.needMore', { sample: groupedMany, minimum: '30' }))
    .toBe(`${groupedMany} pronostics réglés sur 30 nécessaires avant la publication d’un taux.`);

  // A value that is not a number in any reading is still reported loudly rather than guessed at.
  expect(render(FR, 'fr', 'measured.counts.scored', { count: 'beaucoup' })).toBe('{count}');
});

/**
 * The strings that cannot agree, and why that is recorded rather than hidden.
 *
 * MeasuredRecord.tsx prints these counts in a `<span>` of their own and passes the message no
 * number, so the catalogue has nothing to agree with. Rather than "non réglé(s)" — a written-out
 * suffix, which is the shape this package exists to remove — the French is a phrase that does
 * not inflect. The real fix is to pass the count in, and that is a change to a component this
 * package does not own; it is in the package report. This pins the invariance meanwhile, so a
 * later edit cannot quietly put a participle back where no count can reach it.
 */
test('the strings their component gives no count to do not inflect', () => {
  const invariable: Array<[keyof typeof en, Record<string, string | number>]> = [
    ['measured.notScoredReason', { reason: 'le résultat final manque' }],
    ['measured.brierPredictions', {}],
  ];
  for (const [key, params] of invariable) {
    expect(FR[key], `${key} cannot carry a plural: it is never given a count`)
      .not.toMatch(/,\s*plural\s*,/);
    expect(FR[key], `${key} must not fake agreement with a written-out suffix`)
      .not.toMatch(/\(s\)|\(e\)/);
    expect(
      render(FR, 'fr', key, { ...params, count: 1 }),
      `${key} must read the same whatever count the component prints beside it`,
    ).toBe(render(FR, 'fr', key, { ...params, count: 11 }));
  }
});

/* ============================================================== time, in the chosen zone */

/**
 * The premise every zone test below rests on, asserted instead of assumed.
 *
 * All of them prove "the reader's choice decided this, not the device". That proof is only worth
 * anything while the device is on a DIFFERENT zone from the one the test chose, and the device's
 * zone lives in playwright.config.ts, a file these tests do not own and cannot see. If it is ever
 * changed to one of the zones the tests choose, this fails here — once, loudly — rather than
 * turning four zone tests into tautologies nobody notices.
 */
test('the device this suite runs on is on none of the zones a test chooses', async ({ page }) => {
  await stubBackend(page);
  await page.goto('/predictions/today');
  const device = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  expect(device, 'playwright.config.ts sets the browser context zone').toBe(NEW_YORK);
  expect([DOUALA, PARIS, DUBAI], 'a test may never choose the zone the device is already on')
    .not.toContain(device);
});

/**
 * A pool that puts a fixture at each edge of the Douala day and one outside it.
 *
 * Douala is UTC+1 all year, so 2026-06-15 in Douala runs from 23:00Z on the 14th to 23:00Z on
 * the 15th.
 */
const doualaPool = (): ApiMatch[] => [
  // 23:30Z on the 14th = 00:30 on the 15th in Douala: today's FIRST kick-off, on the previous
  // UTC day. A UTC-bucketed client loses this one.
  fixtureAt('2026-06-14T23:30:00Z', 'Midnight Coton Sport', 'Midnight Canon', 'douala-midnight'),
  fixtureAt('2026-06-15T19:00:00Z', 'Evening Astres', 'Evening Dynamo', 'douala-evening'),
  // 23:30Z on the 15th = 00:30 on the 16th in Douala: tomorrow.
  fixtureAt('2026-06-15T23:30:00Z', 'Next Day Aigle', 'Next Day Panthere', 'douala-next'),
];

test('a midnight kick-off in Africa/Douala belongs to the Douala day, whatever the device thinks', async ({ page }) => {
  // The browser context is America/New_York (the suite's default), five hours the other side of
  // UTC. If the page followed the device, the 23:30Z fixture would be filed under the 14th.
  await seedPreferences(page, { zone: DOUALA });
  await page.clock.setFixedTime(new Date('2026-06-15T12:00:00Z'));
  await stubBackend(page, { day: (iso, params) => selectLocalDay(doualaPool(), iso, params) });

  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('Midnight Coton Sport', { exact: true })).toBeVisible();
  await expect(page.getByText('Evening Astres', { exact: true })).toBeVisible();
  await expect(page.getByText('Next Day Aigle', { exact: true })).toHaveCount(0);

  // And the clock reading is the Douala one: 23:30Z is 00:30, not 19:30 as New York would show.
  const row = page.getByTestId('fixture-row').filter({ hasText: 'Midnight Coton Sport' });
  await expect(row.locator('time')).toHaveText('00:30');
  await expect(page.getByTestId('matchday-zone')).toContainText('Douala');
});

test('the day asked for, and the window it is bounded by, follow the chosen zone', async ({ page }) => {
  await seedPreferences(page, { zone: DOUALA });
  await page.clock.setFixedTime(new Date('2026-06-15T23:30:00Z'));

  let params: URLSearchParams | null = null;
  await stubBackend(page, {
    day: (iso, search) => { params ??= search; return dayPayload(iso); },
  });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  // 23:30Z on the 15th is already 00:30 on the 16th in Douala, and 19:30 on the 15th in the
  // device's New York. The reader's chosen zone decides, so it is the 16th.
  expect(params!.get('date')).toBe('2026-06-16');
  // Douala never changes its clocks, so both ends of the day are +60.
  expect(params!.get('tz_offset')).toBe('60');
  expect(params!.get('tz_offset_end')).toBe('60');
});

test('a chosen zone that observes daylight saving bounds its 25-hour day with two offsets', async ({ page }) => {
  /*
   * PARIS, AND A MOMENT WHERE PARIS AND THE DEVICE DISAGREE ABOUT BOTH THINGS AT ONCE.
   *
   * The device is America/New_York (playwright.config.ts). The reader chooses Europe/Paris,
   * whose clocks go back at 01:00 UTC on 25 October 2026 — so the Paris day of the 25th runs
   * 2026-10-24T22:00Z to 2026-10-25T23:00Z and is 25 hours long. New York's clocks do not move
   * until 1 November, so on this date the device's day is a flat 24 hours at -240.
   *
   * The clock is set to 23:30Z on the 24th: 01:30 on the 25th in Paris, but still 19:30 on the
   * 24th in New York. A page that followed the device would ask for 2026-10-24 at -240/-240.
   * Every one of the three assertions below therefore fails if the choice is not honoured, which
   * is what this test previously could not say: it chose New York, the device's own zone.
   */
  await seedPreferences(page, { zone: PARIS, language: 'fr' });
  await page.clock.setFixedTime(new Date('2026-10-24T23:30:00Z'));

  let params: URLSearchParams | null = null;
  await stubBackend(page, {
    day: (iso, search) => { params ??= search; return dayPayload(iso); },
  });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  // The Paris date, not the device's: in New York this instant is still the 24th.
  expect(params!.get('date')).toBe('2026-10-25');
  // +120 is CEST and +60 is CET: an hour apart, because this local day is 25 hours long. One
  // offset used twice would lose an hour of football at one end of it.
  expect(params!.get('tz_offset')).toBe('120');
  expect(params!.get('tz_offset_end')).toBe('60');

  // The zone is named on the page, and it is the chosen one rather than the device's.
  await expect(page.getByTestId('matchday-zone')).toContainText('Paris');
  await expect(page.getByTestId('matchday-zone')).not.toContainText('New York');
});

test('both ends of a 25-hour chosen day are shown, and the hour after it is not', async ({ page }) => {
  // Paris again, for the same reason: the device is New York, so a New York answer here would
  // have proved nothing. 12:00Z on the 25th is 13:00 CET in Paris and 08:00 EDT in New York.
  await seedPreferences(page, { zone: PARIS });
  await page.clock.setFixedTime(new Date('2026-10-25T12:00:00Z'));

  const pool = (): ApiMatch[] => [
    // 22:30Z on the 24th = 00:30 CEST on the 25th: the day's first kick-off, on the PREVIOUS UTC
    // day — and 18:30 on the 24th in New York, so a device-following page never lists it here.
    fixtureAt('2026-10-24T22:30:00Z', 'Extra Hour Dynamo', 'Extra Hour Revolution', 'paris-early'),
    // 22:30Z on the 25th = 23:30 CET, after the clocks went back: the day's last.
    fixtureAt('2026-10-25T22:30:00Z', 'Fall Back Rangers', 'Fall Back Union', 'paris-late'),
    // 23:30Z on the 25th = 00:30 CET on the 26th: tomorrow.
    fixtureAt('2026-10-25T23:30:00Z', 'Monday Nightwatch', 'Monday Sounders', 'paris-next'),
  ];
  await stubBackend(page, { day: (iso, params) => selectLocalDay(pool(), iso, params) });

  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('Extra Hour Dynamo', { exact: true })).toBeVisible();
  await expect(page.getByText('Fall Back Rangers', { exact: true })).toBeVisible();
  await expect(page.getByText('Monday Nightwatch', { exact: true })).toHaveCount(0);

  // The two kick-offs are on opposite sides of the transition, and each is shown on the clock
  // that was actually running: 00:30 on CEST, 23:30 on CET. In the device's New York they would
  // read 18:30 and 18:30 — the same reading twice, which is the tell that the clocks moved.
  await expect(page.getByTestId('fixture-row').filter({ hasText: 'Extra Hour Dynamo' }).locator('time'))
    .toHaveText('00:30');
  await expect(page.getByTestId('fixture-row').filter({ hasText: 'Fall Back Rangers' }).locator('time'))
    .toHaveText('23:30');
});

test('a rescheduled fixture moves to its new day and new time, in the chosen zone', async ({ page }) => {
  await seedPreferences(page, { zone: DOUALA, language: 'fr' });
  await page.clock.setFixedTime(new Date('2026-06-15T12:00:00Z'));

  /*
   * The same fixture, by id, at two different kick-offs: 21:00Z on the 15th (22:00 in Douala,
   * that evening) and then 23:30Z on the 15th (00:30 in Douala, the NEXT day). A reschedule that
   * crosses the local midnight is the case that catches a client bucketing by the UTC day or
   * formatting in the device's zone, because in New York — where this browser thinks it is —
   * both kick-offs fall on the same local day.
   */
  let moved = false;
  const fixture = (): ApiMatch => fixtureAt(
    moved ? '2026-06-15T23:30:00Z' : '2026-06-15T21:00:00Z',
    'Rescheduled Coton Sport', 'Rescheduled Canon', 'douala-rescheduled',
  );
  await stubBackend(page, { day: (iso, params) => selectLocalDay([fixture()], iso, params) });

  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');
  const row = page.getByTestId('fixture-row').filter({ hasText: 'Rescheduled Coton Sport' });
  await expect(row.locator('time')).toHaveText('22:00');

  // The provider moves it. Today no longer holds it; tomorrow does, at the new time.
  moved = true;
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('Rescheduled Coton Sport', { exact: true })).toHaveCount(0);
  await expect(page.getByTestId('matchday-empty')).toBeVisible();

  await page.goto('/predictions/tomorrow');
  await page.waitForLoadState('networkidle');
  const movedRow = page.getByTestId('fixture-row').filter({ hasText: 'Rescheduled Coton Sport' });
  await expect(movedRow.locator('time')).toHaveText('00:30');
});

test('changing the zone re-asks for the day and re-times the fixtures already on screen', async ({ page }) => {
  await seedPreferences(page, { zone: DOUALA });
  await page.clock.setFixedTime(new Date('2026-06-15T12:00:00Z'));
  await stubBackend(page, { day: (iso, params) => selectLocalDay(doualaPool(), iso, params) });

  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('fixture-row').filter({ hasText: 'Evening Astres' }).locator('time'))
    .toHaveText('20:00');

  await page.getByTestId('footer-region-settings').first().click();
  // Paris, not New York. Changing TO the device's own zone would have left a page that ignored
  // the new choice and fell back to the device looking exactly like a page that honoured it.
  await page.getByTestId('time-zone-choice').first().selectOption(PARIS);

  // 19:00Z is 20:00 in Douala, 21:00 in Paris (CEST on 15 June) and 15:00 in the device's New
  // York. The row re-formats from the instant it already holds, so the change is immediate and
  // does not wait for a refetch.
  await expect(page.getByTestId('fixture-row').filter({ hasText: 'Evening Astres' }).locator('time'))
    .toHaveText('21:00');
  await expect(page.getByTestId('matchday-zone')).toContainText('Paris');
  await expect(page.getByTestId('matchday-zone')).not.toContainText('New York');
});

/* ============================================ a date on an account page, in the chosen zone */

/**
 * "MEMBER SINCE" WAS THREE BUGS IN ONE EXPRESSION.
 *
 * `new Date(profile.created_at).toLocaleDateString()` read the timestamp in the DEVICE's zone,
 * formatted it in the DEVICE's zone, and formatted it in the DEVICE's locale. Only the second of
 * those is the one everybody thinks of; the first is the nastiest, because this backend writes
 * `created_at` with `datetime.utcnow()` into a column with no zone, and ECMAScript reads an
 * offset-less date-time string as LOCAL time.
 *
 * WHY Asia/Dubai AND NOT America/New_York. New York is the browser context's own zone (see the
 * note at the top of this file), so a test that chose it would pass whether the reader's choice
 * was honoured or thrown away. At 21:00 UTC the calendar date is the 5th in New York and the 6th
 * in Dubai: the two answers are different days, so only one of them can be given.
 */
for (const language of ['en', 'fr'] as const) {
  test(`Member Since follows the chosen zone and language, not the device's, in ${language}`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DUBAI });
    await stubBackend(page);
    await stubAccount(page);
    await signIn(page);
    await page.goto('/profile');
    await page.waitForLoadState('networkidle');

    const since = page.getByTestId('profile-member-since');
    await expect(since).toBeVisible();
    const shown = (await since.innerText()).trim();

    // The day the reader's chosen zone is on, spelled out in the reader's language.
    expect(shown, 'the chosen zone decides the calendar date')
      .toBe(language === 'fr' ? '6 janvier 2026' : '6 January 2026');
    // The device's answer, which is a different DAY, must not be what is on screen.
    expect(shown, "the device's zone is one day behind here and must not decide this")
      .not.toContain('5 ');
    // Nor the device's locale, which writes this date as a slashed numeral.
    expect(shown, 'the device locale must not decide the format either').not.toContain('/');

    /*
     * And the page says that the date rests on reading an offset-less timestamp as UTC. That is
     * a claim about the backend rather than something the payload states, so it is made out
     * loud — with the zone it was then shown in named.
     */
    const note = page.getByTestId('profile-member-since-note');
    await expect(note, 'an unzoned timestamp must say so').toBeVisible();
    await expect(note).toContainText('Dubai');
  });
}

/**
 * The other half of the same rule: when the server DOES say which zone it meant, the page does
 * not caveat it.
 *
 * Without this, "always show the note" would pass the test above, and the caveat would become
 * noise a reader learns to skip — which is how a warning stops being read.
 */
test('a timestamp that carries its own offset is shown without the caveat', async ({ page }) => {
  await seedPreferences(page, { language: 'fr', zone: DUBAI });
  await stubBackend(page);
  await stubAccount(page, { profile: { created_at: JOINED_ANCHORED } });
  await signIn(page);
  await page.goto('/profile');
  await page.waitForLoadState('networkidle');

  await expect(page.getByTestId('profile-member-since')).toHaveText('6 janvier 2026');
  await expect(page.getByTestId('profile-member-since-note'),
    'nothing was assumed here, so nothing should be disclaimed').toHaveCount(0);
});

/**
 * THE READ, ON ITS OWN — which the Dubai tests above cannot see.
 *
 * "Member Since" was three bugs in one expression: the string was READ in the device's zone, then
 * FORMATTED in the device's zone, and formatted in the device's locale. The tests above pin the
 * second and third. They cannot pin the first, and the fixture comment overstates when it says
 * one value separates all three.
 *
 * Work it through with their pair. Device New York (-5 in January), choice Dubai (+4), value
 * 21:00 with no offset. Read as UTC it is 06 Jan 01:00 in Dubai; read in the device's zone it is
 * 06 Jan 06:00 in Dubai. Five hours apart and the SAME CALENDAR DAY — and the assertion is on the
 * date alone, so both readings satisfy it. Removing the `Z` that `backendInstant` appends leaves
 * every test in this file green, which was verified by doing it.
 *
 * So this test picks the zone where the two readings fall on different days, and it is the zone
 * this product is actually for. In Douala (+1) the correct read is 05 Jan 22:00 and the device
 * read is 06 Jan 03:00 — a different DAY, and only one of them can be shown. That is the whole
 * point of `backendInstant`: against an offset-less timestamp the error is up to a full day, not
 * a few hours, and a date-only assertion in a zone that does not straddle midnight cannot say so.
 */
test('an offset-less timestamp is read as the UTC the server wrote, not in the device\'s zone', async ({ page }) => {
  await seedPreferences(page, { language: 'fr', zone: DOUALA });
  await stubBackend(page);
  await stubAccount(page);
  await signIn(page);
  await page.goto('/profile');
  await page.waitForLoadState('networkidle');

  const shown = (await page.getByTestId('profile-member-since').innerText()).trim();

  // 21:00 UTC on the 5th is 22:00 on the 5th in Douala.
  expect(shown, 'the server wrote 21:00 UTC, so in Douala this is still the 5th')
    .toBe('5 janvier 2026');
  // Reading the same string in the device's New York would carry it over into the 6th.
  expect(shown, "reading it in the device's zone would move it to the next day")
    .not.toContain('6 janvier');

  // And the page still says the reading rests on an assumption, naming the zone it then used.
  await expect(page.getByTestId('profile-member-since-note')).toContainText('Douala');
});

/* ================================================= a price, in the reader's own convention */

/**
 * `` `$${price.toFixed(2)}` `` wrote an American price for a French reader.
 *
 * French writes "9,99 $": the symbol after the figure, a comma for the decimal, and a no-break
 * space between them. None of that can come out of a template literal, and the currency was
 * assumed rather than read from the `currency` the payload carries.
 *
 * The assertion is about the CONVENTION rather than about CLDR's exact bytes — a runtime is
 * free to change which flavour of space it puts before the symbol, and a test that pinned that
 * would fail on an ICU upgrade for no reason. What may not change is that the French page is
 * not showing the English string.
 */
test('the subscription price is written the way the reader\'s language writes money', async ({ page }) => {
  await seedPreferences(page, { language: 'en', zone: DOUALA });
  await stubBackend(page);
  await stubAccount(page);
  await signIn(page);
  await page.goto('/subscription');
  await page.waitForLoadState('networkidle');
  // English is unchanged by this package, to the character.
  await expect(page.getByTestId('subscription-price')).toHaveText('$9.99/month');
});

test('the same price in French is not the English one', async ({ page }) => {
  await seedPreferences(page, { language: 'fr', zone: DOUALA });
  await stubBackend(page);
  await stubAccount(page);
  await signIn(page);
  await page.goto('/subscription');
  await page.waitForLoadState('networkidle');

  const price = (await page.getByTestId('subscription-price').innerText()).trim();
  expect(price, 'French puts the decimal comma in').toContain('9,99');
  expect(price, 'and the period in French').toContain('/mois');
  expect(price, 'and it is not the English rendering').not.toContain('$9.99');
  expect(price, 'nor the English period').not.toContain('/month');
});

/* ================================================================ 200% text zoom, both languages */

/**
 * Double the root font size.
 *
 * This is TEXT zoom, not page zoom: every size in this interface is in `rem`, so doubling the
 * root doubles the type while the viewport stays the width of the phone. It is the harder of the
 * two — page zoom narrows the layout as well, which lets a responsive design fall back to its
 * narrow arrangement — and it is what a reader who has set a larger font in their browser gets.
 */
async function doubleTextSize(page: Page): Promise<void> {
  await page.addStyleTag({ content: 'html { font-size: 200% !important; }' });
  // One frame for the layout to settle before anything is measured.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => resolve(null))));
}

/**
 * Controls whose whole text has to fit, measured as overflow of their own box.
 *
 * Deliberately NOT every element on the page. Several elements truncate on purpose — a club name
 * in a dense row is `truncate` by design, and a competition strip scrolls sideways on purpose —
 * and asserting on those would either fail honestly-designed markup or teach the next person to
 * add exceptions until the test means nothing. These are the ones whose text is a LABEL: if one
 * of them is cut off, the reader cannot tell what the control does.
 */
const LABELS_THAT_MUST_FIT = [
  '[data-testid="language-choice-en"]',
  '[data-testid="language-choice-fr"]',
  '[data-testid="filter-sheet-open"]',
  '[data-testid="matchday-workspace"] h1',
  '[data-testid="matchday-zone"]',
  'footer h3',
];

for (const size of WIDTHS) {
  for (const language of ['en', 'fr'] as const) {
    test(`at 200% text zoom in ${language} nothing is clipped or scrolls sideways at ${size.label}px`, async ({ page }) => {
      await seedPreferences(page, { language, zone: DOUALA });
      await stubBackend(page);
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto('/predictions/today');
      await page.waitForLoadState('networkidle');

      // The settings are in the footer behind a disclosure; open it so its controls are measured
      // rather than skipped for being hidden.
      await page.getByTestId('footer-region-settings').first().click();
      await doubleTextSize(page);

      /*
       * NO SIDEWAYS SCROLL, at any width, in either language.
       *
       * This is an absolute assertion and it took a header change to make it one. Before it,
       * measured: 360 English 0px / French 76px, 390 English 0px / French 46px, 1440 English
       * 381px / French 601px. The narrow rows overflowed because "Connexion" is longer than
       * "Sign In" and the row could not wrap; the wide row overflowed in BOTH languages, French
       * merely more. See the note on the header's own row in components/layout/Header.tsx.
       */
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `the document scrolls sideways at ${size.label}px in ${language}`)
        .toBeLessThanOrEqual(1);

      // And the control that reaches every other page is still on the screen, which is what the
      // overflow was pushing off it.
      // `isVisible`, not `count`: from `xl` up the button is `display: none` and the wide bar
      // carries the destinations itself, so there is nothing to keep on screen.
      const menuButton = page.locator('[aria-controls="mobile-menu"]');
      if (await menuButton.isVisible()) await expect(menuButton).toBeInViewport();

      const clipped = await page.evaluate((selectors) => {
        const bad: string[] = [];
        for (const selector of selectors) {
          for (const node of Array.from(document.querySelectorAll<HTMLElement>(selector))) {
            if (node.offsetParent === null && node.tagName !== 'BODY') continue;
            // A label that wraps is fine; a label whose text is wider than its box is not.
            if (node.scrollWidth > node.clientWidth + 1) {
              bad.push(`${selector}: ${node.scrollWidth} > ${node.clientWidth} — ${node.innerText.slice(0, 40)}`);
            }
          }
        }
        return bad;
      }, LABELS_THAT_MUST_FIT);

      expect(clipped, `labels clipped at ${size.label}px in ${language}`).toEqual([]);
    });
  }
}

/* ============================================================ and it still spends nothing */

test('nothing this package added asks a provider for anything', async ({ page }) => {
  const dayReads: string[] = [];
  const refreshing: string[] = [];
  page.on('request', (request: Request) => {
    const url = new URL(request.url());
    if (url.searchParams.get('refresh') === 'true') refreshing.push(request.url());
    if (url.pathname.endsWith('/api/v1/matches')) dayReads.push(url.searchParams.get('refresh') ?? 'absent');
  });

  await seedPreferences(page, { language: 'fr', zone: DOUALA });
  await stubBackend(page);
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  // Change the language, change the zone, change the day: three things this package added, and
  // none of them may turn into a provider request.
  await page.getByTestId('footer-region-settings').first().click();
  await page.getByTestId('language-choice-en').first().click();
  await page.getByTestId('time-zone-choice').first().selectOption(NEW_YORK);
  await page.getByTestId('date-strip-day').nth(3).click();
  await page.waitForLoadState('networkidle');

  expect(refreshing, 'no request may carry refresh=true').toEqual([]);
  expect(dayReads.length, 'the day was read at least once').toBeGreaterThan(0);
  expect([...new Set(dayReads)], 'every day read must be answered from stored rows').toEqual(['false']);
});
