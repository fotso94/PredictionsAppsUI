import { test, expect, Page, Request } from '@playwright/test';
import { stubBackend, dayPayload, baseMatches } from '../support/api-stub';

/**
 * Today and tomorrow must mean the VIEWER's today and tomorrow.
 *
 * A kickoff at 21:00 in New York is 01:00 the next day in UTC. Bucketing it by the UTC calendar
 * day would hide tonight's match from Today and show it under Tomorrow, which is wrong for
 * everyone west of Greenwich. Daylight-saving days are the same problem with a different offset.
 */

const dayRequestedBy = async (page: Page, path: string): Promise<string | null> => {
  let requested: string | null = null;
  page.on('request', (request: Request) => {
    const url = new URL(request.url());
    if (url.pathname.endsWith('/api/v1/matches') && url.searchParams.get('date')) {
      if (requested === null) requested = url.searchParams.get('date');
    }
  });
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  return requested;
};

test.describe('a viewer in New York', () => {
  test.use({ timezoneId: 'America/New_York' });

  test('today asks the backend for the viewer\'s local calendar day', async ({ page }) => {
    await stubBackend(page, { day: d => dayPayload(d) });
    const requested = await dayRequestedBy(page, '/predictions/today');
    const localToday = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
    expect(requested).toBe(localToday);
  });

  test('tomorrow asks for the day after the viewer\'s local day', async ({ page }) => {
    await stubBackend(page, { day: d => dayPayload(d) });
    const requested = await dayRequestedBy(page, '/predictions/tomorrow');
    const local = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }));
    local.setDate(local.getDate() + 1);
    expect(requested).toBe(local.toLocaleDateString('en-CA'));
  });
});

test.describe('a viewer in Auckland, far ahead of UTC', () => {
  test.use({ timezoneId: 'Pacific/Auckland' });

  test('today is the Auckland day, not the UTC day', async ({ page }) => {
    await stubBackend(page, { day: d => dayPayload(d) });
    const requested = await dayRequestedBy(page, '/predictions/today');
    const localToday = new Date().toLocaleDateString('en-CA', { timeZone: 'Pacific/Auckland' });
    expect(requested).toBe(localToday);
  });
});

test.describe('a viewer in Los Angeles, far behind UTC', () => {
  test.use({ timezoneId: 'America/Los_Angeles' });

  test('a late-evening kickoff still belongs to today', async ({ page }) => {
    const localToday = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' });
    const [first, ...rest] = baseMatches();
    // 21:30 in Los Angeles is 04:30 the next day in UTC
    const lateKickoff = { ...first, kickoff_utc: `${localToday}T04:30:00Z` };

    await stubBackend(page, { day: d => dayPayload(d, [lateKickoff, ...rest]) });
    const requested = await dayRequestedBy(page, '/predictions/today');
    expect(requested).toBe(localToday);
  });
});

test.describe('a daylight-saving transition day', () => {
  // Europe/Lisbon changes offset on the last Sunday of October; the date arithmetic must not
  // slip a day when the local day is 23 or 25 hours long.
  test.use({ timezoneId: 'Europe/Lisbon' });

  test('the requested day matches the viewer\'s calendar', async ({ page }) => {
    await stubBackend(page, { day: d => dayPayload(d) });
    const requested = await dayRequestedBy(page, '/predictions/today');
    const localToday = new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Lisbon' });
    expect(requested).toBe(localToday);
  });
});
