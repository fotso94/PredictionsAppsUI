import React, { useCallback, useRef } from 'react'
import clsx from 'clsx'
import { KIND_OPTIONS, optionLabel } from './workspaceState'
import type { KindFilter } from '@/utils/squads'
import { useT } from '@/i18n/react'

/**
 * All / Club / National teams, as a segmented control beside the competition chips.
 *
 * ── WHY IT IS HERE AND NOT IN A BAR OF ITS OWN ──────────────────────────────────────────────
 *
 * The workspace's whole shape is that about a hundred pixels of controls sit above the fixtures
 * and everything else is behind one Filters button. A second always-visible bar would take back a
 * third of what that rebuild recovered. So this rides in the row the competition chips already
 * occupy, which is the row that answers the same question one level down — the reader picking
 * between two kinds of football and the reader picking between two competitions are the same
 * reader, mid-sentence.
 *
 * It is a SIBLING of the chip group rather than a member of it: that group is labelled "Filter by
 * competition" and these are not competitions, so folding them in would leave a screen-reader
 * user hearing "Club, filter by competition". Two labelled groups in one scroller, one row tall.
 *
 * ── A RADIO GROUP, NOT THREE TOGGLES ────────────────────────────────────────────────────────
 *
 * The three are alternatives. `aria-checked` on `role="radio"` states which one holds, arrow keys
 * move between them the way a keyboard user expects of a radio group, and only the selected
 * button is in the tab order — so a reader tabbing to the fixtures passes the control once rather
 * than three times. The selection also carries a check mark, so it never rests on colour alone.
 */

export interface KindFilterChipsProps {
  value: KindFilter
  onChange: (next: KindFilter) => void
  /**
   * Fixtures of each kind on this day, for the figure on each chip. Omit a count to leave it off
   * rather than printing 0 for "we did not work it out" — the same rule CompetitionChip states.
   */
  counts?: Partial<Record<KindFilter, number>>
  className?: string
}

const KindFilterChips: React.FC<KindFilterChipsProps> = ({ value, onChange, counts, className }) => {
  const t = useT()
  const group = useRef<HTMLDivElement>(null)

  /** Arrow keys move the selection, which is the behaviour a radio group promises. */
  const onKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1
      : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1
        : 0
    if (step === 0) return
    event.preventDefault()
    const current = KIND_OPTIONS.findIndex(option => option.value === value)
    const next = KIND_OPTIONS[(current + step + KIND_OPTIONS.length) % KIND_OPTIONS.length]
    onChange(next.value)
    // The moved selection is the only tab stop, so focus has to follow it or the keyboard user is
    // left on a button that has just left the tab order.
    requestAnimationFrame(() => {
      group.current?.querySelector<HTMLButtonElement>(`[data-kind="${next.value}"]`)?.focus()
    })
  }, [onChange, value])

  return (
    <div
      ref={group}
      role="radiogroup"
      aria-label={t('filters.kind.groupLabel')}
      onKeyDown={onKeyDown}
      className={clsx('flex flex-shrink-0 items-center gap-1', className)}
      data-testid="kind-filter"
    >
      {KIND_OPTIONS.map(option => {
        const selected = value === option.value
        const count = counts?.[option.value]
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(option.value)}
            data-kind={option.value}
            data-testid="kind-filter-option"
            data-selected={selected}
            className={clsx(
              'tap-target-row focus-ring inline-flex max-w-full flex-shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
              selected
                ? 'border-primary-500 bg-dark-800 text-primary-200'
                : 'border-dark-600 bg-dark-800 text-secondary-200 hover:border-dark-500 hover:bg-dark-700',
            )}
          >
            <span className="truncate">{optionLabel(option)}</span>
            {typeof count === 'number' && (
              <span className="num rounded bg-dark-700 px-1.5 text-[11px] text-secondary-200">{count}</span>
            )}
            {selected && <span aria-hidden="true" className="text-primary-200">&#10003;</span>}
          </button>
        )
      })}
    </div>
  )
}

export default KindFilterChips
