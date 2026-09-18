import React from 'react'
import clsx from 'clsx'
import type { BriefMissingReason } from '@/types'
import SourceMarker from '@/components/ui/SourceMarker'
import type { MissingGroup } from './evidence'
import { groupMarketNames } from './evidence'

/**
 * What this page does NOT know, and why — one row per distinct reason.
 *
 * The four ways a model market can be absent must read as four different statements, because they
 * are:
 *
 *   never fetched      we have never retrieved a forecast for this fixture; the model's view is
 *                      genuinely unknown.
 *   not in the forecast we did retrieve one, and it simply does not carry this market.
 *   out of date        we hold one, but it is older than the freshness limit.
 *   refresh paused     nobody has asked the provider recently. This says nothing at all about
 *                      whether what is on screen is right.
 *
 * Rendering all four as a single "unavailable" is the failure this component exists to prevent: it
 * makes "we do not know" and "nobody asked recently" look identical, and the difference between
 * them is the whole reason a reader can or cannot rely on the gap.
 *
 * Every sentence is the backend's own (`BriefMissingEntry.detail`), shown verbatim.
 */

/** Colour is confirmation only: each row carries its reason in words as well. */
const REASON_TONE: Record<BriefMissingReason, string> = {
  // We genuinely do not know. Not a fault, and not a reason to doubt what IS shown.
  no_forecast_retrieved: 'border-dark-600 text-secondary-200',
  no_expert_prediction: 'border-dark-600 text-secondary-200',
  // The source published, and left this out. Ordinary, and worth naming.
  market_not_in_forecast: 'border-dark-600 text-secondary-300',
  market_not_supplied: 'border-dark-600 text-secondary-300',
  not_offered_by_source: 'border-dark-600 text-secondary-300',
  // What we hold should not be read as current.
  forecast_stale: 'border-orange-700 text-orange-200',
  // Operational: nobody has asked recently. Deliberately the quietest of the four.
  refresh_blocked: 'border-dark-600 text-secondary-300',
}

const MissingDataList: React.FC<{ groups: MissingGroup[]; className?: string }> = ({ groups, className }) => {
  if (groups.length === 0) {
    return (
      <p className={clsx('text-sm text-secondary-300', className)} data-testid="brief-missing-none">
        Both sources published every market they offer for this fixture.
      </p>
    )
  }

  return (
    <div className={className} data-testid="brief-missing">
      <h3 className="mb-2 text-sm font-semibold text-white">What is missing, and why</h3>
      <ul className="space-y-2">
        {groups.map(group => {
          const markets = groupMarketNames(group)
          return (
            <li
              key={group.key}
              className="rounded-lg border border-dark-700 bg-dark-800/50 px-3 py-2"
              data-testid="brief-missing-reason"
              data-reason={group.reason}
              data-source={group.source}
            >
              <div className="flex flex-wrap items-center gap-2">
                <SourceMarker
                  source={group.source}
                  state={group.wholeSource ? 'unavailable' : 'available'}
                  title={group.detail}
                />
                <span
                  className={clsx(
                    'inline-flex items-center rounded-md border bg-dark-900 px-1.5 py-0.5 text-[11px] leading-4 font-medium',
                    REASON_TONE[group.reason] ?? 'border-dark-600 text-secondary-300',
                  )}
                >
                  {group.label}
                </span>
              </div>
              {/* The backend's sentence, verbatim: it is the statement this site stands behind. */}
              <p className="mt-1 text-xs text-secondary-300">{group.detail}</p>
              {markets.length > 0 && (
                <p className="mt-1 text-xs text-secondary-400">
                  <span className="text-secondary-500">Markets affected: </span>
                  {markets.join(' · ')}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default MissingDataList
