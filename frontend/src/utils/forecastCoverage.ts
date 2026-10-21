/**
 * What a fixture's model forecast is, in one of four words, from the list payload alone.
 *
 * QA FINDING 9. Both fixture pickers asked one question — "is `providerForecast.state` exactly
 * 'available'?" — and labelled every other answer "No forecast held". That is true of a fixture
 * with no forecast and FALSE of two others the backend reports just as plainly: a forecast that
 * is stored but older than the freshness limit (`stale`), and one kept after kick-off for reference
 * (`kickoff_passed`). An expert choosing what to write about was told the model had nothing to say
 * about fixtures where it had said something and the something had aged.
 *
 * THE STATES ARE THE BACKEND'S, NOT RE-DERIVED HERE. app/services/forecast_service.py::freshness
 * decides them (unavailable / kickoff_passed / stale / available, in that order of precedence), and
 * app/services/match_brief.py puts the same verdict on every list fixture twice: the compact
 * brief's `forecast_state` with `stale`, and the forecast's own `state`. This reads the compact
 * brief first — it is the list's own verdict, the one `ProvenanceLine` already shows on the public
 * lists — then the forecast's `state`, and only then says "absent". No clock, no age arithmetic,
 * and no request: everything needed arrived with the day's fixtures (STORED_ONLY).
 *
 * A FORECAST THAT IS ON THE PAGE IS NEVER CALLED ABSENT. If a forecast is held but its reported
 * state says `unavailable` (a payload the backend should not produce, but one the mapper can be
 * handed), the honest label is the plain "held" one — the same rule as `HELD_WITHOUT_STATE` in
 * components/match-detail/evidence.ts, which refuses to say "no forecast" over a forecast it is
 * showing. "Held" makes no claim about freshness, which is exactly what is unknown then.
 */

import type { Match } from '@/types'
import type { MessageKey } from '@/i18n'

export type ForecastCoverage = 'current' | 'stale' | 'reference' | 'absent'

export function forecastCoverage(match: Pick<Match, 'briefCompact' | 'providerForecast'>): ForecastCoverage {
  const held = Boolean(match.providerForecast)
  const compact = match.briefCompact ?? null
  const state = compact?.forecast_state ?? match.providerForecast?.state ?? null

  if (state === 'kickoff_passed') return 'reference'
  if (state === 'stale' || compact?.stale === true) return 'stale'
  if (state === 'available') return 'current'
  // `unavailable`, or nothing said at all.
  return held ? 'current' : 'absent'
}

/**
 * The badge's words. "Current" is "Model forecast held" rather than a freshness claim, so the
 * held-without-a-state case above can share it truthfully; "absent" is the core catalogue's own
 * `brief.noForecastHeld`, the sentence the public lists use.
 */
export const FORECAST_COVERAGE_LABEL: Record<ForecastCoverage, MessageKey> = {
  current: 'expert.picker.modelForecastHeld',
  stale: 'expert.picker.modelForecastStale',
  reference: 'expert.picker.modelForecastReference',
  absent: 'brief.noForecastHeld',
}

/** The badge colour for each state: out of date reads as a caution, absent as quieter text. */
export const FORECAST_COVERAGE_CLASS: Record<ForecastCoverage, string> = {
  current: 'bg-dark-700 text-secondary-200',
  stale: 'bg-warning-900/40 text-warning-200',
  reference: 'bg-dark-700 text-secondary-300',
  absent: 'bg-dark-700 text-secondary-300',
}
