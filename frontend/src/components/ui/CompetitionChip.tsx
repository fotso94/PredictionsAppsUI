import React from 'react'
import clsx from 'clsx'
import { onLeagueLogoError } from './imageFallback'

/**
 * One competition, as a chip.
 *
 * Two shapes from one component: give it `onToggle` and it is a filter button carrying
 * `aria-pressed`; leave it off and it is a static label. A filter that looks like a button but does
 * nothing is worse than a label, so the element type follows the behaviour rather than the styling.
 *
 * Purely presentational: no fetching, no filter state of its own. The page owns which chips exist
 * and which are selected.
 *
 * Measured on the surfaces used here: unselected text secondary-200 #e2e8f0 on dark-800 #1e293b
 * 11.87:1; selected text primary-200 #bae6fd on dark-800 11.02:1 (the selected chip also gains a
 * primary border AND a check mark, so selection never rests on colour alone).
 */

export interface CompetitionChipProps {
  name: string
  /** Competition badge. Falls back to the shipped placeholder if the URL fails. */
  logo?: string | null
  /** Shown after the name when there is room; useful when two competitions share a name. */
  country?: string | null
  /** How many fixtures this competition contributes. Omit when you do not know — never pass 0 for unknown. */
  count?: number | null
  selected?: boolean
  /** Makes the chip a toggle button. Receives the state it is moving TO. */
  onToggle?: (next: boolean) => void
  disabled?: boolean
  size?: 'sm' | 'md'
  className?: string
}

const CompetitionChip: React.FC<CompetitionChipProps> = ({
  name,
  logo = null,
  country = null,
  count = null,
  selected = false,
  onToggle,
  disabled = false,
  size = 'md',
  className,
}) => {
  const body = (
    <>
      {logo && (
        <img
          src={logo}
          alt=""
          aria-hidden="true"
          className="h-4 w-4 flex-shrink-0 rounded-sm object-contain"
          onError={onLeagueLogoError}
        />
      )}
      <span className="truncate">{name}</span>
      {country && <span className="hidden text-secondary-400 sm:inline">{country}</span>}
      {typeof count === 'number' && (
        <span className="num rounded bg-dark-700 px-1.5 text-[11px] text-secondary-200">{count}</span>
      )}
      {selected && onToggle && (
        // A second, non-colour signal that this chip is on.
        <span aria-hidden="true" className="text-primary-200">&#10003;</span>
      )}
    </>
  )

  const shared = clsx(
    'inline-flex items-center gap-1.5 rounded-full border max-w-full',
    size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-sm',
    selected
      ? 'border-primary-500 bg-dark-800 text-primary-200'
      : 'border-dark-600 bg-dark-800 text-secondary-200',
    className,
  )

  if (!onToggle) {
    return (
      <span className={shared} data-testid="competition-chip" data-selected={selected}>
        {body}
      </span>
    )
  }

  return (
    <button
      type="button"
      // `aria-pressed` rather than a checkbox role: this is a toggle that filters what is already
      // on screen, not a value submitted with a form.
      aria-pressed={selected}
      disabled={disabled}
      onClick={() => onToggle(!selected)}
      className={clsx(
        shared,
        'tap-target-row focus-ring transition-colors',
        disabled ? 'cursor-not-allowed opacity-50' : 'hover:border-dark-500 hover:bg-dark-700',
      )}
      data-testid="competition-chip"
      data-selected={selected}
    >
      {body}
    </button>
  )
}

export default CompetitionChip
