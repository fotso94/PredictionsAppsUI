import React, { useEffect, useState } from 'react'
import { ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { footballDataService } from '@/services/football-data.service'
import { ProviderStatus } from '@/services/match-data-source'

/**
 * Site-wide warning when the backend reports a data/prediction provider problem
 * (missing credentials, expired trial, exhausted daily budget, recent upstream error).
 * Renders nothing when everything is healthy or the status endpoint is unavailable.
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

  const problems: string[] = []
  const active = status.chain[0]
  if (!active) {
    problems.push(`No match-data provider is configured (DATA_PROVIDER=${status.active_provider}); fixtures cannot be refreshed.`)
  } else {
    if (active.name !== status.active_provider) {
      problems.push(`Primary provider "${status.active_provider}" is not configured; using ${active.name} as fallback.`)
    }
    if (active.budget && active.budget.enforced && active.budget.remaining_today === 0) {
      problems.push(`Daily request budget for ${active.name} is exhausted; showing cached data until tomorrow.`)
    }
    if (active.cooling_down) {
      problems.push(`Fixture provider ${active.name} is paused after a failure: ${active.cooling_down}`)
    } else if (active.last_error && (!active.last_success_at || (active.last_error_at || '') > active.last_success_at)) {
      problems.push(`Last ${active.name} request failed: ${active.last_error}`)
    }
  }
  if (status.forecasts?.cooling_down) {
    problems.push(`Model forecasts are unavailable: ${status.forecasts.cooling_down}`)
  }
  if (status.forecasts && !status.forecasts.configured && status.forecasts.active_provider !== 'none') {
    problems.push(`Prediction provider "${status.forecasts.active_provider}" is not configured; model forecasts are unavailable.`)
  }
  if (status.forecasts?.budget && status.forecasts.budget.enforced && status.forecasts.budget.remaining_today === 0) {
    problems.push('Daily forecast request budget is exhausted; forecasts refresh tomorrow.')
  }

  if (problems.length === 0) return null

  return (
    <div className="bg-yellow-900/30 border-b border-yellow-800 text-yellow-100" role="status" data-testid="provider-status-banner">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-2 flex items-start space-x-3 text-sm">
        <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 mt-0.5" />
        <ul className="flex-1 space-y-0.5">
          {problems.map(p => <li key={p}>{p}</li>)}
        </ul>
        <button onClick={() => setDismissed(true)} className="text-yellow-200 hover:text-white" aria-label="Dismiss">
          <XMarkIcon className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}

export default ProviderStatusBanner
