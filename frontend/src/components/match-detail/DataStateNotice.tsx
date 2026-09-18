import React from 'react'
import clsx from 'clsx'
import { CheckCircleIcon, ClockIcon, NoSymbolIcon, QuestionMarkCircleIcon } from '@heroicons/react/24/outline'
import type { BriefFreshness, MatchPredictions } from '@/types'
import ProvenanceLine from '@/components/ui/ProvenanceLine'
import type { ForecastAvailability } from '@/components/ui/forecastStatus'
import Disclosure from './Disclosure'
import { describeDataState } from './evidence'

/**
 * ONE statement about the state of the data behind this page.
 *
 * Before this, a reader could meet three separate notices on one screen — the site-wide provider
 * banner, a per-match "updates are paused" line, and the operational quota wording repeated beside
 * it — and conclude that a perfectly good forecast was broken. Three notices about one fact is not
 * three times the honesty; it is a false impression built out of true sentences.
 *
 * So the order here is deliberate:
 *   1. the state of the forecast on this page, in plain language;
 *   2. how old it is and whether a refresh is running, as separate clauses (ProvenanceLine);
 *   3. the operational detail — quota, cooling-down, freshness limit — behind a disclosure.
 *
 * What is NEVER moved behind the disclosure: that a forecast is out of date, that none was
 * retrieved, or that a market is missing. Those change how the numbers should be read.
 */
const TONE_CLASS = {
  ok: 'text-secondary-200',
  ageing: 'text-warning-200',
  unknown: 'text-secondary-200',
  problem: 'text-orange-200',
} as const

const TONE_ICON = {
  ok: CheckCircleIcon,
  ageing: ClockIcon,
  unknown: QuestionMarkCircleIcon,
  problem: NoSymbolIcon,
} as const

const DataStateNotice: React.FC<{
  freshness?: BriefFreshness | null
  forecast: MatchPredictions | null
  availability: ForecastAvailability | null
  className?: string
}> = ({ freshness = null, forecast, availability, className }) => {
  const state = describeDataState(freshness, forecast, availability)
  const Icon = TONE_ICON[state.tone]

  return (
    <div className={clsx('space-y-2', className)} data-testid="match-data-state" data-tone={state.tone}>
      <p className={clsx('flex items-start gap-2 text-sm', TONE_CLASS[state.tone])}>
        <Icon className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <span>{state.statement}</span>
      </p>

      {/*
        How old the forecast is, and whether a refresh is running — two facts, kept apart by
        ProvenanceLine. It is shown only when there IS a forecast to date: with none held, its
        "No forecast held" would be a third wording of the statement already made above.
      */}
      {forecast && freshness ? (
        <ProvenanceLine
          source={forecast.providerName ?? null}
          freshness={freshness}
          layout="full"
          className="pl-6"
        />
      ) : (
        state.pausedClause && (
          <p className="pl-6 text-xs text-secondary-300" data-testid="match-refresh-paused">{state.pausedClause}</p>
        )
      )}

      {state.detail.length > 0 && (
        <Disclosure summary="Provider and refresh detail" className="ml-6" testId="match-data-state-detail">
          <ul className="space-y-1">
            {state.detail.map(line => <li key={line}>{line}</li>)}
          </ul>
        </Disclosure>
      )}
    </div>
  )
}

export default DataStateNotice
