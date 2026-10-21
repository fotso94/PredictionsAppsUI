import React from 'react'
import clsx from 'clsx'
import type { ExpertPredictionResponse } from '@/types/expert'
import { NOT_SCORED_LABEL, notScoredReason } from '@/utils/publication'
import { useT } from '@/i18n/react'

/**
 * On the expert's own card or row: this prediction is already known to be outside their measured
 * record, and why (review finding #1). Nothing at all when it counts, when nothing is decided yet,
 * or when it was never public — `notScoredReason` in utils/publication.ts holds the rule, which is
 * settlement's own (`stood_at_kickoff`), with the backend's boundary: AT kick-off is after it.
 *
 * The same orange as the reader's "not scored" chip on the match page, which says the same two
 * facts to readers. It wraps rather than truncates: a French label at 360px is a whole sentence.
 */
const NotScoredLabel: React.FC<{ prediction: ExpertPredictionResponse; className?: string }> = ({ prediction, className }) => {
  const t = useT()
  const reason = notScoredReason(prediction)
  if (!reason) return null
  return (
    <span
      className={clsx(
        'inline-block max-w-full break-words rounded-md border border-orange-700 px-1.5 py-0.5 text-[11px] leading-4 text-orange-200',
        className,
      )}
      data-testid="record-not-scored"
      data-reason={reason}
    >
      {t(NOT_SCORED_LABEL[reason])}
    </span>
  )
}

export default NotScoredLabel
