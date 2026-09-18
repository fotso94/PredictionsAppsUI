import { test, expect, Page, Request } from '@playwright/test';
import { ApiMatch, dayPayload, fixtureAt, selectLocalDay, stubBackend } from '../support/api-stub';

/**
 * Today and tomorrow must mean the VIEWER's today and tomorrow.
 *
 * A kickoff at 21:00 in New York is 01:00 the next day in UTC. Bucketing it by the UTC calendar
 * day would hide tonight's match from Today and show it under Tomorrow, which is wrong for
 * everyone west of Greenwich. Daylight-saving days are the same problem with a different offset.
 *
 * Two different things are checked here, and the second is the one that matters to a reader:
 *
 *  - which day the client ASKS the backend for (`date`), and with which boundary offsets; and
 *  - whether a fixture at the edge of the local day is actually SHOWN.
 *
 * Only the second can catch the failure this whole feature exists to prevent, so the edge-of-day
 * tests answer /api/v1/matches through selectLocalDay(), which applies the backend's documented
 * rule — the half-open UTC window [local midnight, next local midnight) derived from the client's
 * own `tz_offset` and `tz_offset_end` — to a fixed pool of fixtures. If the client sends offsets
 * that do not bound its calendar day, the edge fixture falls outside the window, never reaches the
 * page, and the test fails.
 *
 * The clock is pinned with page.clock.setFixedTime so a daylight-saving day can be tested on any
 * date instead of only twice a year. The timezone still comes from the browser context, so
 * getTimezoneOffset() returns the real transition rules for the pinned date.
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

/** Load Today with a fixed pool of fixtures, selected by the backend's own local-day rule. */
async function todayWith(page: Page, now: string, pool: ApiMatch[]): Promise<void> {
  await page.clock.setFixedTime(new Date(now));
  await stubBackend(page, { day: (isoDate, params) => selectLocalDay(pool, isoDate, params) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');
}

const shown = (page: Page, club: string) => page.getByText(club, { exact: true });

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

  // Monday 15 June 2026, 11:00 PDT (UTC-7). The local day runs 07:00Z on the 15th to 07:00Z on the 16th.
  const NOW = '2026-06-15T18:00:00Z';

  //  04:30Z on the 16th  =  21:30 on the 15th in Los Angeles  -> tonight's match
  const tonight = () => fixtureAt('2026-06-16T04:30:00Z', 'Late Kickoff United', 'Late Kickoff City', 'la-tonight');
  //  07:30Z on the 16th  =  00:30 on the 16th in Los Angeles  -> tomorrow, not today
  const tomorrow = () => fixtureAt('2026-06-16T07:30:00Z', 'Next Day Rovers', 'Next Day Athletic', 'la-tomorrow');
  //  06:30Z on the 15th  =  23:30 on the 14th in Los Angeles  -> yesterday, not today
  const yesterday = () => fixtureAt('2026-06-15T06:30:00Z', 'Last Night Wanderers', 'Last Night Albion', 'la-yesterday');

  test('a late-evening kickoff still belongs to today', async ({ page }) => {
    await todayWith(page, NOW, [tonight(), tomorrow(), yesterday()]);

    // It kicks off on the NEXT UTC day, so a UTC-bucketed backend would have hidden it.
    await expect(shown(page, 'Late Kickoff United')).toBeVisible();
    await expect(shown(page, 'Late Kickoff City')).toBeVisible();
  });

  test('a kickoff just outside the local day is not shown as today', async ({ page }) => {
    await todayWith(page, NOW, [tonight(), tomorrow(), yesterday()]);

    // Half past midnight tomorrow, and half past eleven last night: neither is today.
    await expect(shown(page, 'Next Day Rovers')).toHaveCount(0);
    await expect(shown(page, 'Last Night Wanderers')).toHaveCount(0);
  });
});

test.describe('a daylight-saving transition day in Lisbon', () => {
  // Europe/Lisbon leaves summer time on the last Sunday of October: 25 October 2026, when the day
  // starts at UTC+1 (WEST) and ends at UTC+0 (WET) and is therefore 25 hours long, running from
  // 23:00Z on the 24th to 00:00Z on the 26th.
  test.use({ timezoneId: 'Europe/Lisbon' });

  const NOW = '2026-10-25T12:00:00Z';

  //  23:30Z on the 25th  =  23:30 local, after the clocks went back  -> today's last kickoff.
  //  A client that reused the start offset for both ends would close the day at 23:00Z and lose it.
  const lastKickoff = () => fixtureAt('2026-10-25T23:30:00Z', 'Clocks Back Sporting', 'Clocks Back Lusitano', 'lx-late');
  //  23:30Z on the 24th  =  00:30 local on the 25th, still on summer time  -> today's first kickoff,
  //  on the PREVIOUS UTC day.
  const firstKickoff = () => fixtureAt('2026-10-24T23:30:00Z', 'Early Hours Belenenses', 'Early Hours Estoril', 'lx-early');
  //  00:30Z on the 26th  =  00:30 local on the 26th  -> the next day.
  const nextDay = () => fixtureAt('2026-10-26T00:30:00Z', 'Monday Morning Braga', 'Monday Morning Chaves', 'lx-next');
  //  22:30Z on the 24th  =  23:30 local on the 24th  -> the day before.
  const dayBefore = () => fixtureAt('2026-10-24T22:30:00Z', 'Saturday Night Guimaraes', 'Saturday Night Famalicao', 'lx-prev');

  const pool = () => [lastKickoff(), firstKickoff(), nextDay(), dayBefore()];

  test('the requested day matches the viewer\'s calendar', async ({ page }) => {
    await page.clock.setFixedTime(new Date(NOW));
    await stubBackend(page, { day: d => dayPayload(d) });
    const requested = await dayRequestedBy(page, '/predictions/today');
    expect(requested).toBe('2026-10-25');
  });

  test('both ends of a 25-hour local day are shown', async ({ page }) => {
    await todayWith(page, NOW, pool());

    await expect(shown(page, 'Early Hours Belenenses')).toBeVisible();
    await expect(shown(page, 'Clocks Back Sporting')).toBeVisible();
  });

  test('the hours either side of a 25-hour local day are not', async ({ page }) => {
    await todayWith(page, NOW, pool());

    await expect(shown(page, 'Saturday Night Guimaraes')).toHaveCount(0);
    await expect(shown(page, 'Monday Morning Braga')).toHaveCount(0);
  });
});

test.describe('a daylight-saving transition day in New York', () => {
  // America/New_York leaves summer time on the first Sunday of November: 1 November 2026, starting
  // at UTC-4 (EDT) and ending at UTC-5 (EST). The local day runs 04:00Z on the 1st to 05:00Z on the 2nd.
  test.use({ timezoneId: 'America/New_York' });

  const NOW = '2026-11-01T16:00:00Z';

  //  04:30Z on the 2nd  =  23:30 EST on the 1st  -> today's last kickoff, on the next UTC day.
  const lastKickoff = () => fixtureAt('2026-11-02T04:30:00Z', 'Fall Back Rangers', 'Fall Back Union', 'ny-late');
  //  04:30Z on the 1st  =  00:30 EDT on the 1st  -> today's first kickoff.
  const firstKickoff = () => fixtureAt('2026-11-01T04:30:00Z', 'Extra Hour Dynamo', 'Extra Hour Revolution', 'ny-early');
  //  05:30Z on the 2nd  =  00:30 EST on the 2nd  -> the next day.
  const nextDay = () => fixtureAt('2026-11-02T05:30:00Z', 'Monday Nightwatch', 'Monday Sounders', 'ny-next');

  const pool = () => [lastKickoff(), firstKickoff(), nextDay()];

  test('the requested day matches the viewer\'s calendar', async ({ page }) => {
    await page.clock.setFixedTime(new Date(NOW));
    await stubBackend(page, { day: d => dayPayload(d) });
    const requested = await dayRequestedBy(page, '/predictions/today');
    expect(requested).toBe('2026-11-01');
  });

  test('the client bounds the day with the offset at each end, not one offset twice', async ({ page }) => {
    await page.clock.setFixedTime(new Date(NOW));
    let params: URLSearchParams | null = null;
    await stubBackend(page, {
      day: (isoDate, search) => { params ??= search; return dayPayload(isoDate); },
    });
    await page.goto('/predictions/today');
    await page.waitForLoadState('networkidle');

    // -240 is EDT, -300 is EST: an hour apart, because this local day is 25 hours long.
    expect(params!.get('tz_offset')).toBe('-240');
    expect(params!.get('tz_offset_end')).toBe('-300');
  });

  test('both ends of a 25-hour local day are shown', async ({ page }) => {
    await todayWith(page, NOW, pool());

    await expect(shown(page, 'Extra Hour Dynamo')).toBeVisible();
    await expect(shown(page, 'Fall Back Rangers')).toBeVisible();
  });

  test('the first hour of the next local day is not', async ({ page }) => {
    await todayWith(page, NOW, pool());

    await expect(shown(page, 'Monday Nightwatch')).toHaveCount(0);
  });
});
