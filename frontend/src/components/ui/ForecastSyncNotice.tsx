import React from 'react'
import { ChevronRightIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { ForecastSyncStatus } from '@/services/match-data-source'
import { forecastSyncMessage } from '@/utils/predictionLabels'
import { formatDateTime } from '@/i18n'
import { useT } from '@/i18n/react'

interface ForecastSyncNoticeProps {
  sync: ForecastSyncStatus | null | undefined
  /**
   * When refreshing resumes, from the backend's scheduler (see forecastStatus.ts).
   *
   * Optional: a caller with no scheduler state simply omits it and the notice reads exactly as it
   * did before. Nothing here derives a resume time — an absent one stays absent.
   */
  resume?: string | null
  className?: string
}

/**
 * Says that forecast REFRESHES are paused — not that forecasts are unavailable.
 *
 * A spent daily allowance or a provider cooldown stops new numbers arriving; everything already
 * fetched is still exactly what the provider published and stays on screen. Renders nothing when
 * the last refresh ran normally.
 *
 * WHAT MOVED BEHIND THE DISCLOSURE, AND WHY. This sits directly under the freshness block, which
 * now carries a line of its own for the forecast clock and, when a refresh is paused, when it
 * comes back. Two blocks restating one pause in more words each is exactly what made a working
 * forecast look broken, so what is left visible here is the one clause only THIS notice knows —
 * that the day's own refresh pass was skipped, in the backend's own words. The reassurance, the
 * deferred competitions and the timestamp of the last attempt are all still published, one tap
 * away, because they are operator detail rather than a reason to doubt the numbers below.
 */
const ForecastSyncNotice: React.FC<ForecastSyncNoticeProps> = ({ sync, resume = null, className = '' }) => {
  const t = useT()
  const message = forecastSyncMessage(sync)
  if (!message) return null

  const detail: string[] = [t('forecastSync.stayVisible')]
  if (resume) detail.push(resume)
  if (sync && sync.deferred.length > 0) {
    // Competition names as the provider publishes them: a list of names, not of words.
    detail.push(t('forecastSync.waitingFor', { competitions: sync.deferred.join(', ') }))
  }
  const attemptedAt = formatDateTime(sync?.syncedAt)
  if (attemptedAt) detail.push(t('forecastSync.lastAttempt', { when: attemptedAt }))

  return (
    <div
      className={`rounded-lg border border-yellow-700/60 bg-yellow-900/20 px-4 py-3 text-sm text-yellow-200 ${className}`}
      role="status"
      data-testid="forecast-sync-notice"
    >
      <div className="flex items-start gap-2">
        <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
        {/* min-w-0 and break-words: a provider reason can carry an unbreakable URL, and without
            both of these it sets a min-content width that scrolls a narrow phone sideways. */}
        <p className="min-w-0 flex-1 break-words font-medium">{message}</p>
      </div>

      <details className="group ml-7 mt-1">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs text-yellow-300/80 hover:text-yellow-100">
          <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
          {t('forecastSync.disclosure')}
        </summary>
        <ul className="mt-1 space-y-0.5 text-xs text-yellow-300/80">
          {detail.map(line => <li key={line} className="break-words">{line}</li>)}
        </ul>
      </details>
    </div>
  )
}

export default ForecastSyncNotice
