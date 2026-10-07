/**
 * `GET /data-providers/match-data`: whether fixture and result updates are arriving, on its own.
 *
 * For the surfaces that need ONLY that answer — the slip, the selection history, the suggestions —
 * and have no reason to download the whole provider-status payload (about seventy kilobytes, every
 * budget and scheduler detail) to get it. The pages that already read that payload — the banner,
 * the day list, the match page — read `match_data` off it instead and never call this.
 *
 * MEMOISED FOR SIXTY SECONDS, ACROSS THE APP. The answer moves when a provider's access is
 * restored, which is never a matter of seconds, and the backend itself caches the aggregate behind
 * it for a minute. So one request serves every surface a reader passes through in that minute, and
 * a reader moving between their slip, their history and the suggestions costs one request, not
 * three. A failure is memoised too — an older backend without the route must not be asked again on
 * every render — and is null, which every caller reads as "say nothing new".
 *
 * Reads Redis and one cached database aggregate on the backend. It sends no provider request and
 * spends no allowance.
 */

import apiClient from './api-client'
import { configuredDataSource, type MatchDataState } from './match-data-source'
import { asMatchDataState } from '@/components/ui/matchDataState'

const MEMO_MS = 60_000

let memo: { at: number; value: Promise<MatchDataState | null> } | null = null

export function getMatchDataState(now: number = Date.now()): Promise<MatchDataState | null> {
  // The browser-side API-Football mode has no backend to ask, so there is nothing to report.
  if (configuredDataSource() !== 'backend') return Promise.resolve(null)
  if (memo && now - memo.at < MEMO_MS) return memo.value
  const value = apiClient.get<unknown>('/api/v1/data-providers/match-data')
    .then(({ data }) => asMatchDataState(data))
    .catch(() => null)
  memo = { at: now, value }
  return value
}

/** Forget the memoised answer (a test, or a caller that has just changed what it would say). */
export function forgetMatchDataState(): void {
  memo = null
}
