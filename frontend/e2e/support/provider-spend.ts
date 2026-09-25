import { APIRequestContext, expect } from '@playwright/test';

/**
 * What the providers have spent, with the backend scheduler's share kept apart from everyone else's.
 *
 * `budget.used_today` is the WHOLE day's spend, and the scheduler moves it on its own: its `live`
 * task polls every 120 seconds while a match is in play. Comparing that counter before and after a
 * journey therefore measures the scheduler as well as the browser. On 2026-09-25 at 17:42:01 UTC a
 * journey that spent nothing failed with livescore 730 -> 731, because the scheduler's live pass
 * landed one second inside the window.
 *
 * So every budget also carries `scheduler_sent.total`: each request the scheduler has sent that
 * provider since its ledger began. It is written by the same Redis script that moves `used_today`,
 * at the moment the request is granted, and the status endpoint reads the two in one transaction
 * (backend/app/services/providers/budget.py). Between two readings, then, the change in
 * `used_today` minus the change in `scheduler_sent.total` is exactly what everything other than the
 * scheduler spent. There is no tolerance and no retry: a scheduler pass in flight at either reading
 * has its request on both sides of the subtraction or on neither.
 */
export interface ProviderSpend {
  /** `budget.used_today`: everything spent at this provider today, by anyone. */
  usedToday: number;
  /** `budget.scheduler_sent.total`: what the scheduler has sent it. A running total, not a day's. */
  schedulerSent: number;
}

/** One reading of every budgeted provider, keyed by provider name. */
export type SpendReading = Record<string, ProviderSpend>;

interface BudgetBlock {
  provider?: string;
  used_today?: number;
  scheduler_sent?: { total?: number } | null;
}

/** The parts of `GET /api/v1/data-providers/status` a spend reading is taken from. */
export interface ProviderStatus {
  chain?: Array<{ name: string; budget?: BudgetBlock | null }>;
  forecasts?: { budget?: BudgetBlock | null } | null;
}

function spendOf(name: string, budget: BudgetBlock): ProviderSpend {
  const sent = budget.scheduler_sent?.total;
  if (typeof budget.used_today !== 'number' || typeof sent !== 'number') {
    // Never read as zero: a missing ledger would quietly put back the comparison that flaked.
    throw new Error(`the ${name} budget carries no readable scheduler ledger `
      + `(scheduler_sent: ${JSON.stringify(budget.scheduler_sent)}), so the scheduler's own requests `
      + 'cannot be told apart from this test\'s. Is the backend on port 8000 running the current code?');
  }
  return { usedToday: budget.used_today, schedulerSent: sent };
}

/** Every budgeted provider's spend in one status payload: the match-data chain and the forecasts. */
export function spendFromStatus(status: ProviderStatus): SpendReading {
  const blocks: Array<[string, BudgetBlock | null | undefined]> = [];
  for (const provider of status.chain ?? []) blocks.push([provider.name, provider.budget]);
  const forecast = status.forecasts?.budget;
  blocks.push([forecast?.provider ?? 'forecasts', forecast]);
  const reading: SpendReading = {};
  // A provider with no budget keeps no counter, so there is nothing of it to compare.
  for (const [name, budget] of blocks) if (budget) reading[name] = spendOf(name, budget);
  return reading;
}

/** Every budgeted provider's spend right now. */
export async function providerSpend(api: APIRequestContext): Promise<SpendReading> {
  const response = await api.get('/api/v1/data-providers/status');
  expect(response.ok(), 'the provider status endpoint did not answer').toBeTruthy();
  return spendFromStatus(await response.json());
}

/** Per provider, what moved `used_today` between two readings that the scheduler did not send. */
export function spentBesidesTheScheduler(before: SpendReading, after: SpendReading): Record<string, number> {
  const spent: Record<string, number> = {};
  for (const name of new Set([...Object.keys(before), ...Object.keys(after)])) {
    const was = before[name];
    const now = after[name];
    if (!was || !now) {
      throw new Error(`${name} has a budget in only one of the two readings: the provider chain `
        + 'changed inside the window, so the window measures nothing');
    }
    if (now.usedToday < was.usedToday) {
      throw new Error(`${name} used_today went from ${was.usedToday} to ${now.usedToday}: the UTC day `
        + 'turned over inside the window, so the window measures nothing');
    }
    spent[name] = (now.usedToday - was.usedToday) - (now.schedulerSent - was.schedulerSent);
  }
  return spent;
}

/** Assert that nothing but the scheduler spent a provider request between the two readings. */
export function expectNothingSpentBesidesTheScheduler(before: SpendReading, after: SpendReading,
                                                      message: string): void {
  const spent = spentBesidesTheScheduler(before, after);
  const nothing = Object.fromEntries(Object.keys(spent).map(name => [name, 0]));
  const scheduler = Object.keys(spent)
    .map(name => `${name} +${after[name].schedulerSent - before[name].schedulerSent}`)
    .join(', ');
  expect(spent, `${message} (the scheduler's own requests in the window, already subtracted: ${scheduler})`)
    .toEqual(nothing);
}
