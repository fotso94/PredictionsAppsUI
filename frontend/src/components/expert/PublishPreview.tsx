import React from 'react'
import clsx from 'clsx'
import { ComposerValues, OPTIONAL_MARKET_LABEL, OptionalMarketKey, publishableValues } from './composer'
import { formatPercentValue, parsePercent } from './percent'

/**
 * Exactly what a reader will see, before the expert commits to it.
 *
 * Built from the composer's own values rather than from anything returned by the API, so the
 * preview is the request that is about to be sent. A market the expert did not tick appears here
 * as UNAVAILABLE, in the same words the public pages use — the expert sees the consequence of
 * leaving it out rather than discovering later that readers were shown a blank.
 *
 * No number on this panel is rounded into something friendlier, completed, or renormalised. If the
 * three outcomes do not total 100 the composer refuses to publish; the preview never quietly fixes
 * them on the way past.
 */
export interface PublishPreviewProps {
  values: ComposerValues
  fixture: { homeTeam: string; awayTeam: string; competition: string | null; kickoff: string | null } | null
  className?: string
}

/** A percentage as it will be published, or null when the field holds nothing readable. */
function shown(text: string): string | null {
  const value = parsePercent(text)
  return value === null ? null : `${formatPercentValue(value)}%`
}

const Line: React.FC<{ label: string; value: string | null }> = ({ label, value }) => (
  <div className="flex items-baseline justify-between gap-3 text-sm">
    <span className="min-w-0 truncate text-secondary-200">{label}</span>
    <span className={clsx('flex-shrink-0 font-semibold', value ? 'num text-white' : 'text-secondary-400')}>
      {value ?? 'Unavailable'}
    </span>
  </div>
)

/** An optional market the expert left out. Named, so its absence is a stated fact, not a gap. */
const NotPublished: React.FC<{ market: OptionalMarketKey }> = ({ market }) => (
  <div className="rounded-lg border border-dashed border-dark-700 px-3 py-2">
    <p className="text-xs text-secondary-300">
      <span className="font-medium text-secondary-200">{OPTIONAL_MARKET_LABEL[market]}</span> — not published. Readers
      see this market as unavailable, never as 0%.
    </p>
  </div>
)

const PublishPreview: React.FC<PublishPreviewProps> = ({ values, fixture, className }) => {
  const payload = publishableValues(values)
  const conviction = shown(values.conviction)

  return (
    <section className={clsx('card p-4', className)} aria-label="Preview of what will be published">
      <h3 className="text-sm font-semibold text-white">Preview</h3>
      <p className="mt-1 text-xs text-secondary-400">
        This is what readers will see. Publishing puts it on the public match page straight away.
      </p>

      {fixture && (
        <div className="mt-3 rounded-lg border border-dark-700 bg-dark-900/60 p-3">
          <p className="truncate text-sm font-medium text-white">{fixture.homeTeam} v {fixture.awayTeam}</p>
          <p className="mt-0.5 truncate text-xs text-secondary-400">
            {[fixture.competition, fixture.kickoff].filter(Boolean).join(' · ') || 'Fixture details unavailable'}
          </p>
        </div>
      )}

      <div className="mt-4 space-y-4">
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-secondary-400">Match result</h4>
          <div className="space-y-1.5">
            <Line label={fixture ? `${fixture.homeTeam} win` : 'Home win'} value={shown(values.homeWin)} />
            <Line label="Draw" value={shown(values.draw)} />
            <Line label={fixture ? `${fixture.awayTeam} win` : 'Away win'} value={shown(values.awayWin)} />
          </div>
          <p className="mt-2 text-xs text-secondary-400">
            {conviction
              // Said as the expert's own claim. It is not an accuracy: nothing here has been scored
              // against a result.
              ? <>Your stated conviction: <span className="num font-semibold text-secondary-200">{conviction}</span>.</>
              : 'No conviction published — readers are told none was given, and none is inferred from your percentages.'}
          </p>
        </div>

        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-secondary-400">Other markets</h4>

          {values.bttsEnabled ? (
            <div className="rounded-lg border border-dark-700 px-3 py-2">
              <p className="mb-1.5 text-xs font-medium text-secondary-200">{OPTIONAL_MARKET_LABEL.btts}</p>
              <Line label="Both teams score" value={shown(values.bttsYes)} />
              <Line label="At least one does not" value={shown(values.bttsNo)} />
            </div>
          ) : <NotPublished market="btts" />}

          {values.over25Enabled ? (
            <div className="rounded-lg border border-dark-700 px-3 py-2">
              <p className="mb-1.5 text-xs font-medium text-secondary-200">{OPTIONAL_MARKET_LABEL.over25}</p>
              <Line label="Over 2.5 goals" value={shown(values.over25)} />
              <Line label="Under 2.5 goals" value={shown(values.under25)} />
            </div>
          ) : <NotPublished market="over25" />}

          {values.over35Enabled ? (
            <div className="rounded-lg border border-dark-700 px-3 py-2">
              <p className="mb-1.5 text-xs font-medium text-secondary-200">{OPTIONAL_MARKET_LABEL.over35}</p>
              <Line label="Over 3.5 goals" value={shown(values.over35)} />
              <Line label="Under 3.5 goals" value={shown(values.under35)} />
            </div>
          ) : <NotPublished market="over35" />}
        </div>

        {values.reasoning.trim() && (
          <div>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-secondary-400">Your reasoning</h4>
            <p className="whitespace-pre-wrap break-words text-sm text-secondary-200">{values.reasoning.trim()}</p>
          </div>
        )}

        {!payload && (
          <p className="text-xs text-warning-200">
            Some fields still need attention. The problems are marked on the form above.
          </p>
        )}
      </div>
    </section>
  )
}

export default PublishPreview
