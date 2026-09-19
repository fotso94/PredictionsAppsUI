import React from 'react'
import { CpuChipIcon, UserIcon } from '@heroicons/react/24/outline'
import type { BriefSourceKey } from '@/types'
import Card from '@/components/ui/Card'

/**
 * One source's contribution, sized to what it actually contributed.
 *
 * The layout problem this solves: an empty expert panel used to take an equal desktop column beside
 * a full model panel, and on a phone the empty one came FIRST — so the only real analysis on the
 * page started below the fold, under a box whose entire content was "nobody has published
 * anything". Absence deserves a sentence, not half the screen.
 *
 * So a source that published nothing gets NO panel here at all. It is not dropped — "the expert
 * said nothing" is worth knowing next to a model that did — it is stated once, by the coverage row
 * in the evidence panel at the top of the page. This file used to also export an `AbsentSourceStrip`
 * that repeated that sentence a third time further down the page; the sentence outlived the strip.
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
      {/* Tighter on a phone: the panel heading is a signpost, and a signpost does not need the
          same breathing room as the table under it when the table is what the reader scrolled for. */}
      <Card.Header className="py-3 sm:py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center space-x-2 text-base font-semibold text-white sm:text-lg">
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

export default SourcePanel
