import React, { useCallback, useEffect, useId, useRef } from 'react'
import clsx from 'clsx'
import { AdjustmentsHorizontalIcon, XMarkIcon } from '@heroicons/react/24/outline'

/**
 * Filters on a small screen: a sheet from the bottom edge, plus a summary bar that stays visible.
 *
 * The summary bar is the point. A filter the reader cannot see is a filter they will not think to
 * remove, and "no matches today" after a forgotten competition filter is a false statement about
 * the day. So every active filter is listed on the page itself, each one removable on its own, with
 * the total on the button that opens the sheet.
 *
 * Both parts are presentational: they render the filters they are given and report what the user
 * pressed. Nothing here knows what a filter means or fetches anything.
 *
 * Sheet behaviour:
 *  - `role="dialog"` with `aria-modal`, labelled by its own heading.
 *  - Focus moves into the sheet on open, is trapped while it is open (Tab and Shift+Tab cycle), and
 *    returns to whatever opened it on close.
 *  - Escape closes. The backdrop closes. Both, because either alone leaves somebody stuck.
 *  - Page scrolling is locked while it is open, so the page behind does not drift under the sheet.
 *  - The slide-up is CSS, which `prefers-reduced-motion` in index.css already neutralises; there is
 *    nothing to switch off in JavaScript.
 */

/** One filter the user has switched on, and how to switch it off again. */
export interface ActiveFilter {
  /** Stable key. */
  id: string
  /** What it says on the chip, e.g. "Premier League", "Has expert prediction". */
  label: string
  /** Optional category shown to a screen reader, e.g. "Competition". */
  group?: string
  /** Omit to render the chip without a remove control (a filter that cannot be lifted on its own). */
  onRemove?: () => void
}

/** "match" -> "matches", "team" -> "teams". Only used for the result counter's own noun. */
function plural(noun: string, override?: string): string {
  if (override) return override
  return /(s|x|z|ch|sh)$/i.test(noun) ? `${noun}es` : `${noun}s`
}

export interface FilterSummaryBarProps {
  activeFilters: ActiveFilter[]
  /**
   * Opens the sheet. Omit it and no open button is rendered — used when the bar is shown INSIDE the
   * sheet, where a button that reopens what is already open would be a control that does nothing.
   */
  onOpen?: () => void
  /** Clears everything at once. Hidden when absent or when nothing is active. */
  onClearAll?: () => void
  /**
   * How many results the current filters produce. Shown so the reader can connect the two.
   * Pass null while it is still loading — passing 0 would announce an empty result before we know.
   */
  resultCount?: number | null
  /** Noun for `resultCount`, singular. Default "match". */
  resultNoun?: string
  /** Override the plural when the default rule gets it wrong. */
  resultNounPlural?: string
  openLabel?: string
  className?: string
}

/**
 * The always-visible strip: what is filtering the list right now, and the way into the sheet.
 * Measured in the browser: chip text secondary-200 #e2e8f0 on dark-800 #1e293b 11.87:1; the count
 * badge white on primary-700 #0369a1 5.93:1 (primary-600, the app's usual button blue, measures
 * 4.10:1 against white and would not clear the 4.5:1 AA threshold at this size).
 */
export const FilterSummaryBar: React.FC<FilterSummaryBarProps> = ({
  activeFilters,
  onOpen,
  onClearAll,
  resultCount = null,
  resultNoun = 'match',
  resultNounPlural,
  openLabel = 'Filters',
  className,
}) => {
  const count = activeFilters.length

  return (
    <div className={clsx('flex flex-wrap items-center gap-2', className)} data-testid="filter-summary-bar">
      {onOpen && (
        <button
          type="button"
          onClick={onOpen}
          className="tap-target-row focus-ring inline-flex items-center gap-2 rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm font-medium text-secondary-200 transition-colors hover:bg-dark-700 hover:text-white"
          data-testid="filter-sheet-open"
        >
          <AdjustmentsHorizontalIcon className="h-4 w-4" aria-hidden="true" />
          <span>{openLabel}</span>
          {count > 0 && (
            <span className="num rounded-full bg-primary-700 px-1.5 text-xs font-semibold text-white">{count}</span>
          )}
          {/* The count in words too, so it is not carried by a coloured badge alone. */}
          <span className="sr-only">{count === 0 ? ', no filters applied' : `, ${count} filter${count === 1 ? '' : 's'} applied`}</span>
        </button>
      )}

      {/* Live, because the list changes under the reader when a filter is removed from here. */}
      <div className="flex flex-wrap items-center gap-1.5" aria-live="polite">
        {activeFilters.map(filter => (
          <span
            key={filter.id}
            className="inline-flex items-center gap-1 rounded-full border border-dark-600 bg-dark-800 py-1 pl-2.5 pr-1 text-xs text-secondary-200"
            data-testid="active-filter-chip"
          >
            {filter.group && <span className="sr-only">{filter.group}: </span>}
            <span className="max-w-[10rem] truncate">{filter.label}</span>
            {filter.onRemove && (
              <button
                type="button"
                onClick={filter.onRemove}
                aria-label={`Remove filter ${filter.group ? `${filter.group} ` : ''}${filter.label}`}
                className="focus-ring inline-flex h-6 w-6 items-center justify-center rounded-full text-secondary-300 hover:bg-dark-600 hover:text-white"
              >
                <XMarkIcon className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            )}
          </span>
        ))}
        {count > 0 && onClearAll && (
          <button
            type="button"
            onClick={onClearAll}
            className="focus-ring rounded px-2 py-1 text-xs font-medium text-primary-300 underline-offset-2 hover:text-primary-200 hover:underline"
            data-testid="filter-clear-all"
          >
            Clear all
          </button>
        )}
      </div>

      {typeof resultCount === 'number' && (
        <span className="num ml-auto text-xs text-secondary-300" data-testid="filter-result-count">
          {resultCount} {resultCount === 1 ? resultNoun : plural(resultNoun, resultNounPlural)}
        </span>
      )}
    </div>
  )
}

export interface FilterSheetProps {
  open: boolean
  onClose: () => void
  /** The filter controls. Whatever the page needs; this component does not interpret them. */
  children: React.ReactNode
  title?: string
  /** Repeated inside the sheet so the reader can see what is on without closing it first. */
  activeFilters?: ActiveFilter[]
  onClearAll?: () => void
  /** Confirm button. Defaults to closing the sheet, because filters here apply as they are changed. */
  onApply?: () => void
  applyLabel?: string
  /** Shown on the apply button so the reader knows what they are about to see. */
  resultCount?: number | null
  resultNoun?: string
  resultNounPlural?: string
  className?: string
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

const FilterSheet: React.FC<FilterSheetProps> = ({
  open,
  onClose,
  children,
  title = 'Filters',
  activeFilters = [],
  onClearAll,
  onApply,
  applyLabel = 'Show results',
  resultCount = null,
  resultNoun = 'match',
  resultNounPlural,
  className,
}) => {
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreFocusTo = useRef<HTMLElement | null>(null)
  const titleId = useId()

  const focusables = useCallback(
    () => Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(el => el.offsetParent !== null),
    [],
  )

  useEffect(() => {
    if (!open) return

    restoreFocusTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    // The panel itself takes focus first: reading starts at the heading, not at whichever control
    // happens to be first in the markup.
    panelRef.current?.focus()

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const items = focusables()
      if (items.length === 0) {
        event.preventDefault()
        panelRef.current?.focus()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || active === panelRef.current)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('keydown', onKeyDown, true)
      document.body.style.overflow = previousOverflow
      // Back where they were. Losing focus to <body> after closing a sheet strands a keyboard user
      // at the top of the document.
      restoreFocusTo.current?.focus()
    }
  }, [open, onClose, focusables])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center" data-testid="filter-sheet">
      <div
        className="sheet-backdrop absolute inset-0 bg-dark-950/70"
        // The backdrop duplicates the close button and Escape; it is not the only way out, so it is
        // hidden from assistive technology rather than presented as a mystery control.
        aria-hidden="true"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={clsx(
          'sheet-panel relative flex max-h-[85vh] w-full flex-col rounded-t-2xl border border-dark-700 bg-dark-900 shadow-xl focus:outline-none',
          'sm:max-w-lg sm:rounded-2xl',
          className,
        )}
      >
        <div className="flex items-center justify-between gap-3 border-b border-dark-700 px-4 py-3">
          <h2 id={titleId} className="text-base font-semibold text-white">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="tap-target focus-ring -mr-2 rounded-lg text-secondary-300 hover:bg-dark-700 hover:text-white"
            aria-label="Close filters"
          >
            <XMarkIcon className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {activeFilters.length > 0 && (
          <div className="border-b border-dark-700 px-4 py-2">
            {/* No `onOpen`: the sheet is already open, so there is nothing for that button to do. */}
            <FilterSummaryBar activeFilters={activeFilters} onClearAll={onClearAll} />
          </div>
        )}

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">{children}</div>

        <div className="border-t border-dark-700 px-4 py-3">
          <button
            type="button"
            onClick={onApply ?? onClose}
            // Not `.btn-primary`: that shared class is primary-600 on white, which measures
            // 4.10:1 and falls short of 4.5:1. primary-700 here is 5.93:1. The shared class is
            // left alone deliberately — changing it would restyle every button in the app.
            className="tap-target-row focus-ring w-full rounded-lg bg-primary-700 px-4 py-2 font-medium text-white transition-colors hover:bg-primary-800"
            data-testid="filter-sheet-apply"
          >
            {applyLabel}
            {typeof resultCount === 'number' && (
              <span className="num ml-1">({resultCount} {resultCount === 1 ? resultNoun : plural(resultNoun, resultNounPlural)})</span>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export default FilterSheet
