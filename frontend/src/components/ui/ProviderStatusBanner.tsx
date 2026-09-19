import React, { useEffect, useState } from 'react'
import { ChevronRightIcon, ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { footballDataService } from '@/services/football-data.service'
import { ProviderStatus } from '@/services/match-data-source'
import { forecastAvailability } from './forecastStatus'

/**
 * The site-wide banner: FAULTS ONLY, one line, with the operator detail one tap away.
 *
 * WHAT IT NO LONGER SAYS, AND WHY. It used to lead every page — above the fixtures, above the
 * scoreline, above everything — with the model provider's own quota prose, URL and all. On a phone
 * that was two hundred pixels of vendor billing text before any football, and the same fact was
 * then repeated by the freshness block and a third time by the match page's data-state notice. A
 * spent daily allowance is not a fault: nothing on screen is wrong, nothing is unreachable, and
 * new forecasts simply are not arriving for a while. It belongs beside the forecasts it affects,
 * which is where DataFreshness now states it — once, with the time it comes back.
 *
 * So this renders only when something is genuinely BROKEN and a page cannot be refreshed at all:
 * no match-data provider configured, the primary one missing and a fallback standing in, the
 * fixture provider cooling down or failing its last request, its own request budget spent, or the
 * forecast provider not configured (which means no model forecasts exist at all, rather than none
 * arriving today).
 *
 * WHAT IS STILL HERE, JUST NOT IN YOUR FACE. The first fault is the visible line. Everything
 * else — the remaining faults, and any paused refresh — is inside the disclosure, so nothing that
 * was reported before has stopped being reported. A native <details>: keyboard-operable, announced
 * as expandable, and working without JavaScript.
 *
 * Renders nothing when everything is healthy, when the status endpoint is unavailable, or when the
 * only thing to report is a paused refresh.
 */
const ProviderStatusBanner: React.FC = () => {
  const [status, setStatus] = useState<ProviderStatus | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let cancelled = false
    footballDataService.getProviderStatus().then(result => {
      if (!cancelled) setStatus(result)
    })
    return () => { cancelled = true }
  }, [])

  if (!status || dismissed) return null

  /** Something is broken: data cannot be refreshed until somebody changes a configuration or a key. */
  const faults: string[] = []
  const active = status.chain[0]
  if (!active) {
    faults.push(`No match-data provider is configured (DATA_PROVIDER=${status.active_provider}); fixtures cannot be refreshed.`)
  } else {
    if (active.name !== status.active_provider) {
      faults.push(`Primary provider "${status.active_provider}" is not configured; using ${active.name} as fallback.`)
    }
    if (active.budget && active.budget.enforced && active.budget.remaining_today === 0) {
      faults.push(`Daily request budget for ${active.name} is exhausted; showing cached data until tomorrow.`)
    }
    if (active.cooling_down) {
      faults.push(`Fixture provider ${active.name} is paused after a failure: ${active.cooling_down}`)
    } else if (active.last_error && (!active.last_success_at || (active.last_error_at || '') > active.last_success_at)) {
      faults.push(`Last ${active.name} request failed: ${active.last_error}`)
    }
  }

  /*
   * Paused refresh vs unavailable forecasts: one shared helper so the two never blur together here
   * and on the match pages. A provider that is not configured at all is a fault and leads; a pause
   * is not, and travels in the disclosure so the banner does not appear for it alone.
   */
  const forecasts = forecastAvailability(status)
  if (forecasts && !forecasts.paused) faults.push(forecasts.message)
  const pause = forecasts?.paused
    ? [forecasts.message, forecasts.resume].filter(Boolean).join(' ')
    : null

  if (faults.length === 0) return null

  const [lead, ...rest] = faults
  const detail = pause ? [...rest, pause] : rest

  return (
    <div className="bg-yellow-900/30 border-b border-yellow-800 text-yellow-100" role="status" data-testid="provider-status-banner">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-2 text-sm">
        <div className="flex items-start gap-3">
          <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 mt-0.5" aria-hidden="true" />
          {/*
            `min-w-0` is load-bearing. `flex-1` is `flex: 1 1 0%` with the default `min-width:auto`,
            so without it this refuses to shrink below its min-content width — and a provider
            message containing an unbreakable vendor URL made that wider than a 360px phone, which
            scrolled the whole document sideways and clipped the dismiss button off the screen.
            `break-words` makes the URL itself wrap rather than set that minimum.
          */}
          <p className="min-w-0 flex-1 break-words">{lead}</p>
          <button
            onClick={() => setDismissed(true)}
            className="focus-ring flex-shrink-0 rounded text-yellow-200 hover:text-white"
            aria-label="Dismiss"
          >
            <XMarkIcon className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {detail.length > 0 && (
          <details className="group ml-8 mt-1">
            <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs text-yellow-200/90 hover:text-white">
              <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
              {detail.length === 1 ? 'One more provider detail' : `${detail.length} more provider details`}
            </summary>
            <ul className="mt-1 space-y-0.5 text-xs text-yellow-200/90">
              {detail.map(line => <li key={line} className="break-words">{line}</li>)}
            </ul>
          </details>
        )}
      </div>
    </div>
  )
}

export default ProviderStatusBanner
