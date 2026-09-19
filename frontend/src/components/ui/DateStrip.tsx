import React, { useCallback, useEffect, useMemo, useRef } from 'react'
import clsx from 'clsx'
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline'
import { localDateString } from '@/services/match-data-source'
import { formatDayOfMonth, formatFullDate, formatWeekdayShort, zonedNoon } from '@/i18n'
import { useT } from '@/i18n/react'

/**
 * The compact date navigator the matches-first workspace scrolls along.
 *
 * Dates are the viewer's LOCAL calendar days, produced by `localDateString`, the same function the
 * match services use to ask the backend for a day. A 21:00 kickoff in New York is 01:00 the next
 * day in UTC; bucketing it by the UTC day would hide tonight's match from "Today", so the local day
 * is what the strip and the request agree on.
 *
 * Presentational and prop-driven: it holds no selection of its own and fetches nothing. The page
 * owns the selected date and whatever counts it chooses to pass in.
 *
 * Keyboard: the strip is a single tab stop (roving `tabindex`). Left/Right move between days,
 * Home/End jump to the ends, and Enter/Space select — which is what a listbox-like row of choices
 * should do, rather than making a user tab through fourteen buttons to reach next week.
 *
 * Measured in the browser: selected day white on primary-700 #0369a1 → 5.93:1, and its count line
 * primary-100 #e0f2fe on the same → 5.17:1; unselected secondary-200 #e2e8f0 on dark-800 #1e293b →
 * 11.87:1. The current day also carries the WORD "Today", so it is never signalled by colour alone.
 */

export interface DateStripDay {
  /** YYYY-MM-DD in the viewer's local calendar. */
  date: string
  /** Short weekday, e.g. "Fri". Defaults to the locale's own short weekday. */
  weekday?: string
  /** Day of month, e.g. "18". Defaults to the day number. */
  dayOfMonth?: string
  /** "Today" / "Tomorrow" / "Yesterday", when it applies. */
  relativeLabel?: string | null
  /**
   * How many fixtures this day has, when the caller knows. Leave undefined for "not known" —
   * passing 0 would claim the day is empty when nobody has looked.
   */
  count?: number
}

export interface DateStripProps {
  /** The selected day, YYYY-MM-DD. */
  value: string
  onChange: (date: string) => void
  /** Explicit days. When omitted the strip builds `count` days starting `daysBefore` back from today. */
  days?: DateStripDay[]
  /** Days to show when `days` is not given. Default 9. */
  count?: number
  /** How many of those fall before today. Default 2. */
  daysBefore?: number
  /** Fixture counts keyed by YYYY-MM-DD, for the generated days. */
  counts?: Record<string, number>
  /** Show the native date input, so any date is reachable and not only the visible window. Default true. */
  showDatePicker?: boolean
  /** Accessible name for the whole control. */
  label?: string
  className?: string
}

/*
 * The formatters used to be two module-level `Intl.DateTimeFormat`s built with `undefined` as the
 * locale — which means the DEVICE's language and the DEVICE's zone, decided once at import. Both
 * halves of that are wrong here: the language is the reader's choice, and so is the zone. They
 * are now built per call in src/i18n, cached there by locale and zone, and rebuilt when either
 * changes.
 */

/**
 * Midday in the READER'S CHOSEN ZONE, so a date string never lands on the wrong side of a
 * daylight-saving boundary — nor on the wrong side of midnight, which is what
 * `new Date(`${date}T12:00:00`)` did as soon as the chosen zone was not the device's: that parses
 * in the device's zone, so noon on the 25th in Douala became 04:00 on the 25th in Los Angeles.
 */
function localNoon(date: string): Date {
  return zonedNoon(date)
}

function buildDays(count: number, daysBefore: number, counts?: Record<string, number>): DateStripDay[] {
  return Array.from({ length: count }, (_, index) => {
    const date = localDateString(index - daysBefore)
    return { date, count: counts?.[date] }
  })
}

function describe(
  day: DateStripDay,
  relativeLabel: (date: string) => string | null,
): { weekday: string; dayOfMonth: string; relative: string | null; full: string } {
  const at = localNoon(day.date)
  const valid = !Number.isNaN(at.getTime())
  return {
    weekday: day.weekday ?? (valid ? formatWeekdayShort(at) : day.date),
    dayOfMonth: day.dayOfMonth ?? (valid ? formatDayOfMonth(at) : ''),
    relative: day.relativeLabel !== undefined ? day.relativeLabel : relativeLabel(day.date),
    full: (valid ? formatFullDate(at) : null) ?? day.date,
  }
}

const DateStrip: React.FC<DateStripProps> = ({
  value,
  onChange,
  days,
  count = 9,
  daysBefore = 2,
  counts,
  showDatePicker = true,
  label,
  className,
}) => {
  const t = useT()
  // "Today" / "Tomorrow" / "Yesterday" against the reader's chosen zone, because that is what
  // `localDateString` now answers in — the same zone the list and the backend request use.
  const relativeLabel = useCallback((date: string): string | null => {
    if (date === localDateString(0)) return t('matchday.relative.today')
    if (date === localDateString(1)) return t('matchday.relative.tomorrow')
    if (date === localDateString(-1)) return t('matchday.relative.yesterday')
    return null
  }, [t])
  const resolved = useMemo(() => days ?? buildDays(count, daysBefore, counts), [days, count, daysBefore, counts])
  const selectedIndex = Math.max(0, resolved.findIndex(day => day.date === value))
  const listRef = useRef<HTMLDivElement>(null)

  /*
   * Keep the selected day in view when the page changes it (a "jump to today" button, a deep link).
   *
   * The strip's own `scrollLeft` is set rather than `scrollIntoView`, which would also scroll the
   * PAGE to bring the strip into view — on a phone that yanks the reader away from whatever they
   * were looking at just because a date changed.
   */
  useEffect(() => {
    const list = listRef.current
    const node = list?.querySelector<HTMLElement>(`[data-date="${CSS.escape(value)}"]`)
    if (!list || !node) return
    const target = node.offsetLeft - (list.clientWidth - node.clientWidth) / 2
    list.scrollLeft = Math.max(0, target)
  }, [value])

  const focusDay = useCallback((index: number) => {
    const clamped = Math.min(Math.max(index, 0), resolved.length - 1)
    const target = resolved[clamped]
    if (!target) return
    const node = listRef.current?.querySelector<HTMLElement>(`[data-date="${CSS.escape(target.date)}"]`)
    node?.focus()
  }, [resolved])

  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>, index: number) => {
    switch (event.key) {
      case 'ArrowLeft': event.preventDefault(); focusDay(index - 1); break
      case 'ArrowRight': event.preventDefault(); focusDay(index + 1); break
      case 'Home': event.preventDefault(); focusDay(0); break
      case 'End': event.preventDefault(); focusDay(resolved.length - 1); break
      default: break
    }
  }

  const step = (delta: number) => {
    const at = localNoon(value)
    if (Number.isNaN(at.getTime())) return
    onChange(localDateString(delta, at))
  }

  return (
    // Wrapping, so the native date input drops to a second line on a phone instead of stealing
    // half the width from the strip itself.
    <div className={clsx('flex flex-wrap items-center gap-2', className)} data-testid="date-strip">
      <div className="flex w-full min-w-0 items-center gap-1 sm:w-auto sm:flex-1">
      <button
        type="button"
        onClick={() => step(-1)}
        className="tap-target focus-ring flex-shrink-0 rounded-lg text-secondary-300 hover:bg-dark-700 hover:text-white"
        aria-label={t('dateStrip.previousDay')}
      >
        <ChevronLeftIcon className="h-5 w-5" aria-hidden="true" />
      </button>

      <div
        ref={listRef}
        role="group"
        aria-label={label ?? t('dateStrip.chooseDate')}
        className="no-scrollbar flex flex-1 items-stretch gap-1 overflow-x-auto scroll-smooth"
      >
        {resolved.map((day, index) => {
          const info = describe(day, relativeLabel)
          const selected = day.date === value
          return (
            <button
              key={day.date}
              type="button"
              data-date={day.date}
              // Roving tabindex: one tab stop for the whole strip, arrow keys inside it.
              tabIndex={index === selectedIndex ? 0 : -1}
              aria-pressed={selected}
              onKeyDown={event => onKeyDown(event, index)}
              onClick={() => onChange(day.date)}
              className={clsx(
                'tap-target focus-ring flex min-w-[3rem] flex-col items-center justify-center gap-0 rounded-lg px-1.5 py-1.5 transition-colors',
                selected
                  // primary-700 rather than primary-600: white on primary-600 measures 4.10:1,
                  // which is under the 4.5:1 AA threshold for text this size. On primary-700
                  // #0369a1 it is 5.93:1.
                  ? 'bg-primary-700 text-white'
                  : 'bg-dark-800 text-secondary-200 hover:bg-dark-700 hover:text-white',
              )}
              data-selected={selected}
              data-testid="date-strip-day"
            >
              <span className="whitespace-nowrap text-[10px] leading-4">
                {info.relative ?? info.weekday}
              </span>
              <span className="num text-sm font-semibold leading-5">{info.dayOfMonth}</span>
              {typeof day.count === 'number' && (
                <span className={clsx('num text-[10px] leading-3', selected ? 'text-primary-100' : 'text-secondary-400')}>
                  {day.count}
                </span>
              )}
              {/* The full date, and the count as a sentence, for anyone not reading the column. */}
              <span className="sr-only">
                {info.full}
                {typeof day.count === 'number' ? t('dateStrip.dayMatches', { count: day.count }) : ''}
              </span>
            </button>
          )
        })}
      </div>

      <button
        type="button"
        onClick={() => step(1)}
        className="tap-target focus-ring flex-shrink-0 rounded-lg text-secondary-300 hover:bg-dark-700 hover:text-white"
        aria-label={t('dateStrip.nextDay')}
      >
        <ChevronRightIcon className="h-5 w-5" aria-hidden="true" />
      </button>
      </div>

      {showDatePicker && (
        // Any date, not only the days in the window. A native input so the platform's own picker,
        // keyboard handling and locale formatting apply.
        <label className="flex-shrink-0">
          <span className="sr-only">{t('dateStrip.jumpToDate')}</span>
          <input
            type="date"
            value={value}
            onChange={event => { if (event.target.value) onChange(event.target.value) }}
            className="tap-target-row focus-ring rounded-lg border border-dark-600 bg-dark-800 px-2 py-1.5 text-xs text-secondary-200"
            data-testid="date-strip-picker"
          />
        </label>
      )}
    </div>
  )
}

export default DateStrip
