import React from 'react'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { ForecastSyncStatus } from '@/services/match-data-source'
import { forecastSyncMessage } from '@/utils/predictionLabels'

interface ForecastSyncNoticeProps {
  sync: ForecastSyncStatus | null | undefined
  className?: string
}

/**
 * Says that forecast REFRESHES are paused — not that forecasts are unavailable.
 *
 * A spent daily allowance or a provider cooldown stops new numbers arriving; everything already
 * fetched is still exactly what the provider published and stays on screen. Renders nothing when
 * the last refresh ran normally.
 */
const ForecastSyncNotice: React.FC<ForecastSyncNoticeProps> = ({ sync, className = '' }) => {
  const message = forecastSyncMessage(sync)
  if (!message) return null

  return (
    <div
      className={`flex items-start space-x-2 rounded-lg border border-yellow-700/60 bg-yellow-900/20 px-4 py-3 text-sm text-yellow-200 ${className}`}
      role="status"
      data-testid="forecast-sync-notice"
    >
      <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" />
      <div>
        <p className="font-medium">{message}</p>
        <p className="text-yellow-300/80">
          Forecasts already loaded stay visible and are unchanged — they are just not being updated right now.
        </p>
        {sync && sync.deferred.length > 0 && (
          <p className="mt-1 text-xs text-yellow-300/60">
            Waiting for the next allowance reset: {sync.deferred.join(', ')}
          </p>
        )}
        {sync?.syncedAt && (
          <p className="mt-1 text-xs text-yellow-300/60">
            Last refresh attempt {new Date(sync.syncedAt).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  )
}

export default ForecastSyncNotice
