import React from 'react'
import clsx from 'clsx'
import { ClockIcon, NoSymbolIcon, QuestionMarkCircleIcon } from '@heroicons/react/24/outline'
import { BriefFreshness, MatchBriefCompact } from '@/types'
import { freshnessLine, refreshBlockedNote } from '@/utils/brief'
import { providerLabel } from '@/utils/predictionLabels'

/**
 * One compact line: where a number came from, how current it is, and — when that is the honest
 * answer — that we do not know.
 *
 * Three facts are kept apart on purpose, because merging any two of them would state something
 * nobody has established:
 *
 *  - WHO published it. A provider name, or the expert.
 *  - HOW OLD it is. Measured from the provider's own model-run time. When the provider published
 *    no model-run time, the age is genuinely UNKNOWN and this says so; it does not quietly show the
 *    time we fetched the record, which is a fact about us, not about when the forecast was made.
 *  - WHETHER A REFRESH IS RUNNING. "Nobody has asked the provider recently" says nothing about
 *    whether the numbers on screen are wrong, so it is its own clause and never replaces the age.
 *
 * Every wording comes from the brief where the brief supplied one.
 */

export interface ProvenanceLineProps {
  /** Provider key ('gameforecast') or 'expert'; rendered through `providerLabel`. */
  source?: string | null
  /** Display name, when you already have one. Wins over `source`. */
  sourceLabel?: string | null
  /** The brief's freshness block. Everything below is derived from it when it is supplied. */
  freshness?: BriefFreshness | null
  /** A compact brief, for a list row that has no full freshness block. */
  compact?: MatchBriefCompact | null
  /** Hide the source name and show only the freshness clause. */
  hideSource?: boolean
  /** `full` adds the refresh-blocked sentence on its own line; `inline` keeps everything on one. */
  layout?: 'inline' | 'full'
  className?: string
}

/** Colour is confirmation only — each tone always ships with its own words. */
const TONE_CLASS = {
  // secondary-300 on dark-900 12.02:1, on dark-800 9.85:1
  ok: 'text-secondary-300',
  // warning-200 on dark-900 14.33:1
  ageing: 'text-warning-200',
  // secondary-300: "unknown" is not a fault, so it is not coloured like one
  unknown: 'text-secondary-300',
  // orange-200 on dark-900 13.19:1 — distinct from the warning amber without shouting red
  problem: 'text-orange-200',
} as const

const ProvenanceLine: React.FC<ProvenanceLineProps> = ({
  source = null,
  sourceLabel = null,
  freshness = null,
  compact = null,
  hideSource = false,
  layout = 'inline',
  className,
}) => {
  const name = sourceLabel ?? (source ? providerLabel(source) : null)
  const line = freshnessLine(freshness)
  const blocked = refreshBlockedNote(freshness ?? compact)

  // A compact brief carries no timestamps, so the only honest freshness statement from one is
  // whether what we hold is out of date. It is not turned into an age it cannot support.
  const compactState = !line && compact
    ? compact.forecast_state === 'unavailable'
      ? { text: 'No forecast held', tone: 'problem' as const }
      : compact.stale
        ? { text: 'Out of date', tone: 'problem' as const }
        : null
    : null

  const text = line?.text ?? compactState?.text ?? null
  const tone = line?.tone ?? compactState?.tone ?? 'ok'
  if (!name && !text && !blocked) return null

  const Icon = tone === 'unknown' ? QuestionMarkCircleIcon : tone === 'problem' ? NoSymbolIcon : ClockIcon

  return (
    <div
      className={clsx('text-xs', layout === 'full' ? 'space-y-1' : 'flex flex-wrap items-center gap-x-2 gap-y-1', className)}
      data-testid="provenance-line"
    >
      <span className={clsx('flex flex-wrap items-center gap-x-1.5 gap-y-1', TONE_CLASS[tone])}>
        {!hideSource && name && (
          <span className="text-secondary-300">
            <span className="sr-only">Source: </span>{name}
          </span>
        )}
        {!hideSource && name && text && <span aria-hidden="true" className="text-secondary-400">·</span>}
        {text && (
          <span className="inline-flex items-center gap-1" title={line?.detail ?? undefined}>
            <Icon className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
            {text}
          </span>
        )}
      </span>
      {blocked && (
        <span className={clsx('text-secondary-300', layout === 'full' ? 'block' : 'inline')} data-testid="provenance-refresh-blocked">
          {/* Deliberately its own sentence: a paused refresh is not a reason to doubt the numbers. */}
          Refresh paused — {blocked}
        </span>
      )}
      {line?.detail && layout === 'full' && (
        <span className="block text-secondary-400">{line.detail}</span>
      )}
    </div>
  )
}

export default ProvenanceLine
