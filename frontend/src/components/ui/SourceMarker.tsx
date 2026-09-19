import React from 'react'
import clsx from 'clsx'
import { CpuChipIcon, UserIcon } from '@heroicons/react/24/outline'
import { BriefSourceKey, BriefSourceState } from '@/types'
import { sourceDescription, sourceLabel } from '@/utils/brief'
import { useT } from '@/i18n/react'
import type { MessageKey } from '@/i18n'

/**
 * Who said it: the model provider, or one of our experts.
 *
 * THE LABEL IS ALWAYS RENDERED AS TEXT. MatchCard hides its source label below the `sm` breakpoint
 * and leaves only an icon with a `title`, which a touch user can never open — so on a phone, the
 * screen where most of this is read, the single most important fact about a number (who produced
 * it) is unavailable. This component does not repeat that: the icon is decoration
 * (`aria-hidden`), the word carries the meaning at every width, and the colour is confirmation
 * rather than the message.
 *
 * Measured on the dark-800 #1e293b chip this sits on:
 *   model    warning-200 #fde68a   11.75:1
 *   expert   primary-200 #bae6fd   11.02:1
 *   muted    secondary-300 #cbd5e1  9.85:1
 * all far above the 4.5:1 AA threshold for text this size.
 */

export interface SourceMarkerProps {
  source: BriefSourceKey
  /**
   * What this source has for the fixture. `unavailable` renders muted with a strike-free "none"
   * suffix — never a 0%, and never simply omitted, because "the expert said nothing" is itself
   * worth showing next to a model that did.
   */
  state?: BriefSourceState
  /** Short text after the label, e.g. the leading probability. Kept to a few characters. */
  detail?: string | null
  /** Overrides the default explanation used for the tooltip and the accessible description. */
  title?: string
  size?: 'xs' | 'sm'
  className?: string
}

/** Extra wording for a state that is not plainly "available". Text, so colour is never the only cue. */
const STATE_SUFFIX_KEY: Partial<Record<BriefSourceState, MessageKey>> = {
  stale: 'source.state.stale',
  reference_only: 'source.state.referenceOnly',
  unavailable: 'source.state.unavailable',
}

const SourceMarker: React.FC<SourceMarkerProps> = ({
  source,
  state = 'available',
  detail = null,
  title,
  size = 'xs',
  className,
}) => {
  const t = useT()
  const Icon = source === 'expert' ? UserIcon : CpuChipIcon
  const muted = state === 'unavailable'
  const suffixKey = STATE_SUFFIX_KEY[state]
  // The source travels with the wording: in French the state agrees with the noun each source
  // implies, and that cannot be applied after the fact. See the note in the catalogue.
  const suffix = suffixKey ? t(suffixKey, { source }) : null
  const description = title ?? (suffix
    ? t('source.markerDescription', { description: sourceDescription(source), suffix })
    : sourceDescription(source))

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-md border bg-dark-800 font-medium whitespace-nowrap',
        size === 'xs' ? 'px-1.5 py-0.5 text-[11px] leading-4' : 'px-2 py-1 text-xs',
        muted
          ? 'border-dark-600 text-secondary-300'
          : source === 'expert'
            ? 'border-primary-700 text-primary-200'
            : 'border-warning-700 text-warning-200',
        className,
      )}
      title={description}
      data-source={source}
      data-state={state}
      data-testid={`source-marker-${source}`}
    >
      <Icon className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
      <span>{sourceLabel(source)}</span>
      {detail && <span className="num font-semibold">{detail}</span>}
      {suffix && <span className="font-normal text-secondary-300">{suffix}</span>}
      <span className="sr-only">. {description}</span>
    </span>
  )
}

export default SourceMarker
