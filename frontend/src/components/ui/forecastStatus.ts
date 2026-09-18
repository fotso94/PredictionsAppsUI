/**
 * Telling a PAUSED forecast refresh apart from an UNAVAILABLE forecast.
 *
 * "The daily allowance is spent" and "this provider has no forecast for this fixture" are different
 * facts and must never share a message: the first means the numbers already on screen are simply
 * not being refreshed, the second means there is nothing to show at all.
 */

import { ProviderStatus } from '@/services/match-data-source'

export interface ForecastAvailability {
  /** True when refreshes are stopped but existing forecasts are still valid to display. */
  paused: boolean
  /** Wording for the reader, in the backend's own terms where it gave any. */
  message: string
}

/**
 * What the backend's provider-status report says about model forecasts.
 * Returns null when forecasts are configured and refreshing normally.
 */
export function forecastAvailability(status: ProviderStatus | null | undefined): ForecastAvailability | null {
  const forecasts = status?.forecasts
  if (!forecasts) return null

  if (!forecasts.configured && forecasts.active_provider !== 'none') {
    return {
      paused: false,
      message: `Prediction provider "${forecasts.active_provider}" is not configured; model forecasts are unavailable.`,
    }
  }
  if (forecasts.budget && forecasts.budget.enforced && forecasts.budget.remaining_today === 0) {
    return {
      paused: true,
      message: 'Model forecast updates are paused until the daily request allowance resets; forecasts already loaded stay visible.',
    }
  }
  if (forecasts.cooling_down) {
    return {
      paused: true,
      message: `Model forecast updates are paused after a provider error: ${forecasts.cooling_down}. Forecasts already loaded stay visible.`,
    }
  }
  return null
}
