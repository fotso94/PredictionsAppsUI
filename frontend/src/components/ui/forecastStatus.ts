/**
 * Telling a PAUSED forecast refresh apart from an UNAVAILABLE forecast.
 *
 * "The daily allowance is spent" and "this provider has no forecast for this fixture" are different
 * facts and must never share a message: the first means the numbers already on screen are simply
 * not being refreshed, the second means there is nothing to show at all.
 *
 * AND A PAUSE IS ONLY HALF AN ANSWER. "Paused" tells a reader nothing they can act on. What they
 * want is when it comes back, and now that the backend runs a scheduler that is a real fact rather
 * than a guess: the forecasts task publishes its next attempt, and our own request allowance is
 * counted per UTC day, so it resets at 00:00 UTC. Both are stated.
 */

import { ProviderStatus } from '@/services/match-data-source'
import { allowanceResetNote, relativeTime } from './freshness'

export interface ForecastAvailability {
  /** True when refreshes are stopped but existing forecasts are still valid to display. */
  paused: boolean
  /** The state itself, in the backend's own terms where it gave any. One short sentence. */
  message: string
  /**
   * When refreshing resumes — deliberately NOT folded into `message`.
   *
   * The site-wide banner and the page's own freshness panel both describe this pause, and if the
   * resume time rode along inside `message` the reader would meet the same paragraph twice on one
   * screen. Keeping it separate lets the banner stay one line while the page states it properly.
   *
   * Null when nothing in the payload says when it resumes; nothing is invented to fill it.
   */
  resume: string | null
}

/**
 * When the forecast refresh comes back.
 *
 * `allowanceReset` is only passed as true for a pause the payload attributes to a spent request
 * allowance: `app/services/providers/budget.py` counts requests per UTC day, so that pause and
 * only that pause is known to lift at 00:00 UTC.
 */
function resumeNote(
  status: ProviderStatus | null | undefined,
  allowanceReset: boolean,
  now: number,
): string | null {
  const parts: string[] = []
  if (allowanceReset) parts.push(allowanceResetNote(now))

  const task = status?.scheduler?.tasks?.forecasts
  if (task?.enabled !== false && task?.next_due_at) {
    const when = relativeTime(task.next_due_at, now)
    if (when) parts.push(`The next scheduled attempt is ${when}.`)
  }
  return parts.length > 0 ? parts.join(' ') : null
}

/**
 * What the backend's provider-status report says about model forecasts.
 * Returns null when forecasts are configured and refreshing normally.
 */
export function forecastAvailability(
  status: ProviderStatus | null | undefined,
  now: number = Date.now(),
): ForecastAvailability | null {
  const forecasts = status?.forecasts
  if (!forecasts) return null

  if (!forecasts.configured && forecasts.active_provider !== 'none') {
    return {
      paused: false,
      message: `Prediction provider "${forecasts.active_provider}" is not configured; model forecasts are unavailable.`,
      resume: null,
    }
  }
  if (forecasts.budget && forecasts.budget.enforced && forecasts.budget.remaining_today === 0) {
    return {
      paused: true,
      message: 'Model forecast updates are paused until the daily request allowance resets; '
        + 'forecasts already loaded stay visible.',
      resume: resumeNote(status, true, now),
    }
  }
  if (forecasts.cooling_down) {
    // A cooldown after a provider error is not an allowance problem, so the allowance sentence is
    // withheld unless the backend's own wording says the allowance is what stopped it.
    const allowance = /\ballowance\b|\bbudget\b|\bquota\b/i.test(forecasts.cooling_down)
    return {
      paused: true,
      message: `Model forecast updates are paused after a provider error: ${forecasts.cooling_down}. `
        + 'Forecasts already loaded stay visible.',
      resume: resumeNote(status, allowance, now),
    }
  }
  return null
}
