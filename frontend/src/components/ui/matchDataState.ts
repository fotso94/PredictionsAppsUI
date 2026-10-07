/**
 * Whether fixture and result updates can reach us at all, in the words every surface shares.
 *
 * THE DISTINCTION THIS EXISTS FOR. Forecasts and match data come from different providers. On
 * 2026-10-07 the forecast provider answered every request while every match-data source refused
 * — Live Score's access was disabled, API-Football's plan excluded the season, TheSportsDB rejected
 * its key — so the pages could keep showing forecasts for the fixtures already stored, and nothing
 * else could change: no new fixture, no kick-off correction, no live score, no result, no slip
 * settled. A reader was told none of that. The banner named one provider by its internal key and
 * quoted its English; the freshness line said the fixtures had been refreshed "4 minutes ago".
 *
 * The backend now states it as one block (`MatchDataState`, `match_data` on the status payload)
 * and this turns it into sentences, once, for every surface: the banner, the freshness block, the
 * match page, the empty day, the slip, the selection history and the suggestions. Each of them asks
 * `matchDataNotice` and gets null unless the state is BLOCKED — so a degraded chain, a healthy one,
 * one we cannot judge, and an older backend that sends no block at all all leave every page
 * exactly as it was.
 *
 * WHAT THE VISIBLE LINES MAY SAY. That updates are unavailable at the moment, since when nothing
 * new has reached us, and what still works. Never a vendor's name, a plan tier, an HTTP code or a
 * link, and never a time it will come back: nobody here knows that, and "at the moment" is the
 * honest tense. The per-source reasons — with each provider's own words, verbatim and marked as
 * English — belong one disclosure away, where the banner keeps them.
 *
 * Plain helpers, deliberately in a .ts file: a .tsx may export only components.
 */

import type {
  MatchDataSourceState, MatchDataState, ProviderChainEntry,
} from '@/services/match-data-source'
import type { MessageKey } from '@/i18n'
import { formatDateTime, t } from '@/i18n'
import { fixtureProviderLabel, nextAttemptSentence } from './freshness'

const STATES: ReadonlyArray<MatchDataState['state']> = ['ok', 'degraded', 'blocked', 'unknown']

const asNumber = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null
const asText = (value: unknown): string | null => (typeof value === 'string' && value ? value : null)

/**
 * The block as the backend sent it, or null when there is none to read.
 *
 * An older backend has no `/data-providers/match-data` route and no `match_data` key; a stub that
 * answers every unknown path with `{}` sends an object with no state. All of those are "no block",
 * which every caller treats exactly as it treated the page before the block existed.
 */
export function asMatchDataState(value: unknown): MatchDataState | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Record<string, unknown>
  const state = raw.state as MatchDataState['state']
  if (!STATES.includes(state)) return null
  return {
    state,
    since: asText(raw.since),
    since_basis: asText(raw.since_basis),
    sources: Array.isArray(raw.sources)
      ? (raw.sources as MatchDataSourceState[]).filter(source => source && typeof source.name === 'string')
      : [],
    affects: Array.isArray(raw.affects) ? (raw.affects as string[]) : [],
    still_available: Array.isArray(raw.still_available) ? (raw.still_available as string[]) : [],
    upcoming_stored: asNumber(raw.upcoming_stored),
    overdue_results: asNumber(raw.overdue_results),
    forecasts_waiting_for_fixtures: asNumber(raw.forecasts_waiting_for_fixtures),
    next_check_at: asText(raw.next_check_at),
    checked_at: asText(raw.checked_at) ?? '',
  }
}

/** True only for BLOCKED. Degraded, ok, unknown and "no block" all leave the page as it was. */
export function isMatchDataBlocked(state: MatchDataState | null | undefined): boolean {
  return asMatchDataState(state)?.state === 'blocked'
}

/** One source, for the disclosure: who, why in our words, and the provider's own words. */
export interface MatchDataSourceLine {
  name: string
  /** The product name as the rest of the page names it ("Live Score API", "API-Football (fallback)"). */
  label: string
  answer: MatchDataSourceState['answer']
  kind: MatchDataSourceState['kind']
  /** Our summary of why it is not delivering data, in the reader's language. */
  reason: string
  /**
   * The provider's own message, exactly as recorded, or null when none is held — a later success
   * clears it. Always English, whatever the page's language, and rendered as such.
   */
  verbatim: string | null
}

export interface MatchDataNotice {
  /** When a provider last wrote a match row, in the reader's zone. Null when none is recorded. */
  since: string | null
  /** The same instant as the backend sent it, for a `title`. */
  sinceIso: string | null
  /** The banner's one visible line. */
  lead: string
  /**
   * The same line without its closing promise that forecasts are still shown, for when the forecast
   * source has a fault of its own: the banner then states that fault in its place.
   */
  leadWithoutForecasts: string
  /** Every configured source, in chain order. */
  sources: MatchDataSourceLine[]
  /** "The next attempt is in 24 minutes." Null when the backend reports no next check. */
  nextCheck: string | null
  /** Forecasts already retrieved and waiting for a fixture we do not hold; 0 when none or unknown. */
  forecastsWaiting: number
}

/**
 * Why a source is not delivering data, in our words — never its words, which travel beside.
 *
 * A refusal of access is worded by what it says: Live Score's "do not have access to our data
 * enabled" is access that was never switched on or has been switched off, which is a different
 * thing to tell an operator from a key that is wrong. A source whose latest record is a SUCCESS
 * while the state is blocked answered something that brought no data — API-Football answers a live
 * poll on its free plan with nothing in play — and is said to have done exactly that.
 */
function sourceReason(source: MatchDataSourceState, verbatim: string | null): string {
  const text = (verbatim ?? '').toLowerCase()
  if (source.answer === 'ok') return t('banner.matchData.answeredWithoutData')
  if (source.answer === 'never_answered') return t('freshness.panel.notAnswered')
  const byKind: Record<string, MessageKey> = {
    plan: 'freshness.reason.plan',
    unavailable: 'freshness.reason.unavailable',
  }
  if (source.kind === 'access') {
    return t(/not have access|not enabled/.test(text) ? 'freshness.reason.accessNotEnabled' : 'freshness.reason.credentials')
  }
  if (source.kind === 'quota') {
    // Ours or the provider's. Our own refusals name our budget ("Daily request budget for X
    // exhausted ...; refused by the daily ceiling we configured", "budget store unavailable");
    // the provider's own refusal is an HTTP 429 that names no budget of ours.
    if (text.includes('budget store unavailable')) return t('freshness.reason.unavailable')
    return t(text.includes('budget') || text.includes('ceiling we configured')
      ? 'freshness.reason.budget' : 'freshness.reason.quota')
  }
  return t(byKind[source.kind ?? 'unavailable'] ?? 'freshness.reason.unavailable')
}

/**
 * Everything a surface needs to say that fixture and result updates are blocked — or null.
 *
 * `chain` is optional and only lends the providers' verbatim messages to the disclosure: the lean
 * endpoint carries no messages, and the surfaces that read it say nothing about sources.
 */
export function matchDataNotice(
  state: MatchDataState | null | undefined,
  now: number = Date.now(),
  chain: ReadonlyArray<ProviderChainEntry> = [],
): MatchDataNotice | null {
  const block = asMatchDataState(state)
  if (!block || block.state !== 'blocked') return null
  const since = formatDateTime(block.since)
  const sources = block.sources
    .filter(source => source.configured !== false)
    .map(source => {
      const verbatim = chain.find(entry => entry.name === source.name)?.last_error?.trim() || null
      return {
        name: source.name,
        label: fixtureProviderLabel(source.name),
        answer: source.answer,
        kind: source.kind,
        reason: sourceReason(source, verbatim),
        verbatim: source.answer === 'ok' ? null : verbatim,
      }
    })
  return {
    since,
    sinceIso: block.since,
    lead: since
      ? t('banner.matchData.blocked', { since })
      : t('banner.matchData.blockedNoSince'),
    leadWithoutForecasts: since
      ? t('banner.matchData.blockedOnly', { since })
      : t('banner.matchData.blockedOnlyNoSince'),
    sources,
    nextCheck: nextAttemptSentence(block.next_check_at, now),
    forecastsWaiting: Math.max(block.forecasts_waiting_for_fixtures ?? 0, 0),
  }
}
