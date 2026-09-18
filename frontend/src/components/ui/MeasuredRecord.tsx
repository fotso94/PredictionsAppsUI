import React from 'react'
import clsx from 'clsx'
import { ChevronRightIcon } from '@heroicons/react/24/outline'
import type { MeasuredMarket, MeasuredSource } from '@/types'
import type { PerformanceResult } from '@/services/performance.service'
import {
  measuredMarketLabel, measuredView, ratioPercent, sourceCounts, sourceKindLabel, windowText,
} from './measurement'

/**
 * The measured record: what each source actually got right, counted from settled results.
 *
 * THE ONE RULE. A figure appears only with its sample size, the definition of what was counted and
 * the window it was counted over. The backend enforces the first half of that — it refuses to
 * publish a rate below its minimum sample and returns null with a reason instead — and this panel
 * renders that refusal as the plain sentence it is. It is never a 0%, never a dash, never an empty
 * bar. A dash invites the reader to assume the worst; a zero states something false.
 *
 * THE STATE YOU WILL ACTUALLY SEE. Nothing on this installation has been scored yet, so the
 * "not measured" path is what a real visitor meets today. It is written as a genuine answer —
 * what would have to happen for a figure to exist, and what is already counted in the meantime —
 * rather than as an apology or an empty chart.
 *
 * WHAT THIS IS NOT. Not a prediction, not a ranking, and not a recommendation. A source that did
 * well over ninety days has not thereby told anyone what will happen on Saturday, and nothing here
 * is phrased as though it had.
 */

/** One market's line for a measured source: the figure, its sample, and its definition. */
const MarketRow: React.FC<{ market: MeasuredMarket; minimumSample: number }> = ({ market, minimumSample }) => {
  const rate = ratioPercent(market.hit_rate)

  return (
    <div className="border-t border-dark-700 pt-2" data-testid="measured-market" data-market={market.market}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <span className="text-sm text-secondary-200">{measuredMarketLabel(market.market)}</span>
        {market.hit_rate_available && rate ? (
          <span className="text-sm text-white" data-testid="measured-hit-rate">
            {/* Never apart: the figure and the sample it came from are one statement. */}
            <span className="num font-semibold">{rate}</span>
            <span className="text-secondary-400"> hit rate from {market.hit_rate_sample} scored</span>
          </span>
        ) : (
          <span className="text-sm text-secondary-300" data-testid="measured-hit-rate-withheld">
            no hit rate published
          </span>
        )}
      </div>

      {/*
        Why there is no figure, in as few words as carry the meaning. The full rationale for the
        minimum sample is stated ONCE for the whole block, below the markets: repeating three
        sentences under every market made five honest rows read like five errors, which is the same
        way the quota notices once made a good forecast look broken.
      */}
      {!market.hit_rate_available && (
        <p className="mt-0.5 text-xs text-secondary-400">
          {market.hit_rate_sample} of {minimumSample} scored predictions needed before a rate is published.
        </p>
      )}

      <dl className="mt-1 space-y-0.5 text-xs text-secondary-500">
        {/* The definitions matter but they are identical on every row; they belong behind a
            disclosure, not repeated five times down the page. */}
        <details className="group">
          <summary className="cursor-pointer text-secondary-400 hover:text-secondary-300 focus-ring">
            How this market is counted and settled
          </summary>
          <div className="mt-1 space-y-0.5 pl-3">
            <p><span className="text-secondary-400">Counted as: </span>{market.hit_rate_definition}</p>
            <p><span className="text-secondary-400">Settled by: </span>{market.rule}</p>
          </div>
        </details>
        <div>
          <dt className="inline text-secondary-400">Sample: </dt>
          <dd className="inline">
            <span className="num">{market.hits}</span> of <span className="num">{market.scored}</span> scored
            {market.pushes > 0 && <> · <span className="num">{market.pushes}</span> push</>}
            {market.voids > 0 && <> · <span className="num">{market.voids}</span> void</>}
            {market.not_scored > 0 && <> · <span className="num">{market.not_scored}</span> not scorable</>}
          </dd>
        </div>
        <div>
          <dt className="inline text-secondary-400">Brier score: </dt>
          <dd className="inline">
            {market.brier_available && typeof market.brier_score === 'number' ? (
              <>
                <span className="num">{market.brier_score}</span> from{' '}
                <span className="num">{market.brier_sample}</span> predictions
                {typeof market.brier_baseline === 'number' && (
                  <> · an uninformative forecast scores <span className="num">{market.brier_baseline}</span></>
                )}
              </>
            ) : (
              <span className="text-secondary-500">
                {market.brier_sample} of {minimumSample} needed
              </span>
            )}
          </dd>
        </div>
      </dl>
    </div>
  )
}

/** One source: measured or not, its counts are always real and always shown. */
const SourceBlock: React.FC<{ source: MeasuredSource; minimumSample: number }> = ({ source, minimumSample }) => (
  <div
    className="rounded-lg border border-dark-700 bg-dark-800/40 px-3 py-2"
    data-testid="measured-source"
    data-measured={source.measured ? 'true' : 'false'}
  >
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
      <h3 className="text-sm font-semibold text-white">{source.source_label}</h3>
      <span className="text-xs text-secondary-400">{sourceKindLabel(source.source_type)}</span>
    </div>
    <p className="mt-0.5 text-xs text-secondary-400" data-testid="measured-source-counts">{sourceCounts(source)}</p>

    {source.measured ? (
      <div className="mt-2 space-y-2">
        {source.markets.map(market => (
          <MarketRow key={market.market} market={market} minimumSample={minimumSample} />
        ))}
      </div>
    ) : (
      /* The whole source is unmeasured: one sentence, the backend's, rather than a row of dashes. */
      <p className="mt-1 text-xs text-secondary-300" data-testid="measured-source-unmeasured">
        {source.not_measured_reason ?? 'Nothing from this source has been scored in this window yet.'}
      </p>
    )}

    {source.not_scored_reasons.length > 0 && (
      <ul className="mt-1 space-y-0.5 text-xs text-secondary-500">
        {source.not_scored_reasons.map(entry => (
          <li key={entry.reason}>
            <span className="num">{entry.count}</span> not scored — {entry.reason}
          </li>
        ))}
      </ul>
    )}
  </div>
)

export interface MeasuredRecordProps {
  /** The service result. Null while it is still loading. */
  result: PerformanceResult | null
  /** True while the request is in flight, so "nothing measured" is never shown prematurely. */
  loading?: boolean
  className?: string
  /** 2 on a page whose own h1 is above this; 3 inside a section that already has an h2. */
  headingLevel?: 2 | 3
}

const MeasuredRecord: React.FC<MeasuredRecordProps> = ({
  result, loading = false, className, headingLevel = 2,
}) => {
  const Heading = (headingLevel === 2 ? 'h2' : 'h3') as 'h2' | 'h3'
  const view = measuredView(result)
  const performance = view.performance

  return (
    <section className={clsx('space-y-3', className)} data-testid="measured-record" data-state={loading ? 'loading' : view.state}>
      <div>
        <Heading className="text-xl font-bold text-white sm:text-2xl">How the sources have actually done</Heading>
        <p className="mt-1 max-w-3xl text-sm text-secondary-400">
          Counted from settled results by comparing what a source published before kick-off with
          what happened. Scoring a forecast is arithmetic against a real result — it is not a new
          prediction, and none of it says what will happen next.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-secondary-400" role="status">Loading the measured record&hellip;</p>
      ) : (
        <>
          <p
            className={clsx('text-sm', view.state === 'measured' ? 'text-secondary-200' : 'text-secondary-300')}
            data-testid="measured-headline"
          >
            {view.headline}
          </p>
          {view.detail && <p className="max-w-3xl text-sm text-secondary-400" data-testid="measured-detail">{view.detail}</p>}

          {performance && (
            <>
              <p className="text-xs text-secondary-500" data-testid="measured-window">
                {/* The window travels with every figure: "62%" over ninety days is not an all-time claim. */}
                Window: {windowText(performance)} — {performance.window.basis}. Measured{' '}
                {new Date(performance.measured_at).toLocaleString()}.
              </p>

              {(view.measured.length > 0 || view.unmeasured.length > 0) && (
                <div className="space-y-2">
                  {view.measured.map(source => (
                    <SourceBlock key={`${source.source_type}:${source.source_id}`} source={source}
                      minimumSample={performance.minimum_sample} />
                  ))}
                  {view.unmeasured.map(source => (
                    <SourceBlock key={`${source.source_type}:${source.source_id}`} source={source}
                      minimumSample={performance.minimum_sample} />
                  ))}
                </div>
              )}

              <p className="max-w-3xl text-xs text-secondary-500" data-testid="measured-minimum-sample">
                {performance.minimum_sample_rationale}
              </p>

              <details className="group rounded-lg border border-dark-700 bg-dark-800/40" data-testid="measured-rules">
                <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-xs text-secondary-300 hover:text-white">
                  <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
                  The rules every figure here was settled by
                </summary>
                <dl className="space-y-1.5 border-t border-dark-700 px-3 py-2 text-xs text-secondary-400">
                  <div><dt className="inline text-secondary-300">Ruleset: </dt><dd className="inline">{performance.rules.version}</dd></div>
                  <div><dt className="inline text-secondary-300">Basis: </dt><dd className="inline">{performance.rules.basis}</dd></div>
                  <div><dt className="inline text-secondary-300">Only pre-kickoff evidence: </dt><dd className="inline">{performance.rules.prematch_only}</dd></div>
                  <div><dt className="inline text-secondary-300">Void fixtures: </dt><dd className="inline">{performance.rules.void}</dd></div>
                  {/* The rule this whole application is built on, restated where it is enforced. */}
                  <div><dt className="inline text-secondary-300">A market a source did not publish: </dt><dd className="inline">{performance.rules.unsupplied_market}</dd></div>
                  <div><dt className="inline text-secondary-300">Hit rate: </dt><dd className="inline">{performance.rules.hit_rate}</dd></div>
                  <div><dt className="inline text-secondary-300">Brier score: </dt><dd className="inline">{performance.rules.brier}</dd></div>
                </dl>
              </details>
            </>
          )}
        </>
      )}
    </section>
  )
}

export default MeasuredRecord
