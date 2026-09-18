import React from 'react'
import { CpuChipIcon, UserIcon } from '@heroicons/react/24/outline'
import type { BriefSourceKey } from '@/types'
import Card from '@/components/ui/Card'
import SourceMarker from '@/components/ui/SourceMarker'

/**
 * One source's contribution, sized to what it actually contributed.
 *
 * The layout problem this solves: an empty expert panel used to take an equal desktop column beside
 * a full model panel, and on a phone the empty one came FIRST — so the only real analysis on the
 * page started below the fold, under a box whose entire content was "nobody has published
 * anything". Absence deserves a sentence, not half the screen.
 *
 * So a source that published nothing is rendered by `AbsentSourceStrip` instead: one line, after
 * the analysis, saying what is missing in the brief's own words. A source that published something
 * gets the room. The absent source is never dropped altogether — "the expert said nothing" is
 * itself worth knowing next to a model that did.
 */

const SourcePanel: React.FC<{
  source: BriefSourceKey
  title: string
  /** Right-hand badge: provider name, number of experts, and so on. */
  badge?: React.ReactNode
  /**
   * Whether this source published a confidence value at all — a different fact from the
   * probability beside it, and from any accuracy (nothing here has been scored against a result).
   */
  confidenceNote: string
  /** True when the badges below are bands derived from the probability, not published confidences. */
  derivedBands: boolean
  children: React.ReactNode
  /**
   * Rendered after the confidence note. A section of its own (the revision history) belongs here
   * rather than among the children, so the note stays close to the badges it explains.
   */
  footer?: React.ReactNode
  testId?: string
  className?: string
}> = ({ source, title, badge = null, confidenceNote, derivedBands, children, footer = null, testId, className }) => {
  const Icon = source === 'expert' ? UserIcon : CpuChipIcon
  return (
    <Card className={className} data-testid={testId}>
      <Card.Header>
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center space-x-2 text-lg font-semibold text-white">
            <Icon className={`h-5 w-5 ${source === 'expert' ? 'text-blue-400' : 'text-yellow-400'}`} aria-hidden="true" />
            <span>{title}</span>
          </h3>
          {badge}
        </div>
      </Card.Header>
      <Card.Body className="space-y-4">
        {children}
        {/*
          Kept at the foot of the panel, with the badges it qualifies still on screen: a probability
          is what the source expects, a confidence is what the source claims about its own view, and
          neither is a record of being right.
        */}
        <p className="border-t border-dark-700 pt-3 text-xs text-secondary-400" data-testid={`confidence-basis-${source}`}>
          <span className="text-secondary-300">Confidence: </span>
          {confidenceNote}
          {derivedBands && (
            <>
              {' '}
              The band shown beside each probability is derived from the strength of that probability
              alone. It is not a confidence this source stated, and it is not a measure of how often
              this source has been right.
            </>
          )}
        </p>
        {footer}
      </Card.Body>
    </Card>
  )
}

/** A source with nothing on this fixture: one line, in the brief's own words where it gave one. */
export const AbsentSourceStrip: React.FC<{
  source: BriefSourceKey
  /** The backend's sentence for why there is nothing. */
  detail: string
  /** A quieter second line: what would change this. Never a promise about when. */
  note?: string | null
  testId?: string
  className?: string
}> = ({ source, detail, note = null, testId, className }) => (
  <div
    className={`rounded-xl border border-dark-700 bg-dark-900/60 px-4 py-3 ${className ?? ''}`}
    data-testid={testId}
  >
    <div className="flex flex-wrap items-center gap-2">
      <SourceMarker source={source} state="unavailable" title={detail} />
      <p className="min-w-0 flex-1 text-sm text-secondary-300">{detail}</p>
    </div>
    {note && <p className="mt-1 text-xs text-secondary-500">{note}</p>}
  </div>
)

export default SourcePanel
