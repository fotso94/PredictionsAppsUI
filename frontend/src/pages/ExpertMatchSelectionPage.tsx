/**
 * Choose the fixture to write about.
 *
 * This page used to render two long lists — "Today's Matches" and "Tomorrow's Matches" — of tall
 * three-column cards. Each card repeated the venue, the round, the internal UUID and the provider's
 * fixture id, and the three-column team grid did not collapse: a 23-fixture day pushed the page 11
 * CSS pixels wider than a 390px phone, so the whole thing scrolled sideways.
 *
 * It is now one list with filters, and the football context an expert actually chooses on — when it
 * kicks off, which competition, who is playing, and whether anybody has published on it yet. The
 * identifiers are gone from the card body; the composer keeps them behind an advanced disclosure
 * for the rare case where somebody has one to paste.
 *
 * Reads are stored-data-only, so filtering and paging between days spends no provider allowance.
 *
 * ── WHY THE LIST IS RENDERED HERE AND NOT BY components/expert/FixturePicker.tsx ─────────────
 *
 * It used to be, and the picker was measured before anything was changed: `FixturePicker` holds
 * TWENTY-TWO English literals that this screen renders — the label on the date control, three day
 * chips, the search field's hidden label and its placeholder, the competition strip's accessible
 * name, the checkbox, "Clear filters", the loading line, the count sentence, three coverage
 * badges, the row's whole accessible name, both empty states with their explanations, the failure
 * title and the retry. Not one of them was reachable from here: the component takes `actionLabel`
 * and `heading` and nothing else, so translating the other twenty would have meant editing the
 * component, and that file is in another package's ownership block.
 *
 * Changing it would not have been enough on its own either. The kick-off it printed was
 * `match.time`, which the mapper formats ONCE when the payload arrives — correct in the reader's
 * chosen zone only until the reader changes it, and formatted in the DEVICE's zone outright on
 * the legacy api-football data source.
 *
 * So the list lives here, where this package can translate it and can re-derive the kick-off from
 * the UTC instant on every render. THIS IS A FORK AND IS MEANT TO BE TEMPORARY. The composer
 * (`ExpertCreatePredictionPage`) still renders `FixturePicker`, still in English, and it is no
 * better off than before — but four of its English strings are now VISIBLE to the generated stray
 * check in `frontend/e2e/mocked/expert-localisation.spec.ts` where only one was, because putting
 * the picker's wording into the catalogue is what lets a catalogue-derived check see it. When the
 * picker's owner takes the labels below as props or reads them from the catalogue itself, this
 * page should go back to importing it and everything from `DAY_OFFSETS` to `FixtureList` here
 * should be deleted.
 *
 * ── THE KICK-OFF IS A CORRECTNESS PROBLEM ON THIS SCREEN, NOT A COSMETIC ONE ─────────────────
 *
 * The person reading this list is deciding whether a fixture is still prematch. A kick-off shown
 * in the wrong zone does not make the page look wrong — it makes the decision wrong. `PickerRow`
 * formats `kickoffUtc` through `formatTime` on every render, so the reader's CHOSEN zone decides
 * what it says and a zone change repaints it; `match.time` is the fallback for a payload that
 * carried no instant at all, and the day is spelled out above the list with the zone named beside
 * it so nobody has to infer which calendar day these times belong to.
 *
 * ── THE TWO EXAMPLE FIGURES IN THE "HOW" LIST ARE NOT LITERALS ──────────────────────────────
 *
 * "type 55 for 55%, not 0.55" reads like three characters-on-the-page and is nothing of the sort:
 * French writes the percentage as « 55 % », with a no-break space before the sign, and the decimal
 * as « 0,55 ». Writing them into the catalogue would have shipped English number formatting to a
 * French reader in the one sentence on the page that is teaching them how to type a number. So
 * they are formatted values passed into the sentence, exactly like every other figure here — as is
 * the "0%" further down, which is the thing a market left out must NEVER be shown as.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import { ArrowLeftIcon, ArrowRightIcon, MagnifyingGlassIcon } from '@heroicons/react/24/outline'
import { Match } from '@/types'
import { footballDataService } from '@/services/football-data.service'
import { localDateString, STORED_ONLY } from '@/services/match-data-source'
import { filterLiveAndScheduledMatches } from '@/utils/matchFilters'
import { getErrorMessage } from '@/utils/errors'
import CompetitionChip from '@/components/ui/CompetitionChip'
import EmptyState from '@/components/ui/EmptyState'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import {
  formatIsoDate, formatNumber, formatPercentValue, formatTime, zoneLabel,
} from '@/i18n'
import type { TranslateFn } from '@/i18n'
import { useLocale, useT } from '@/i18n/react'

/** Today, tomorrow, the day after. Relative to the reader's chosen zone, never the device's. */
const DAY_OFFSETS = [0, 1, 2] as const

/** The competitions present in a day's fixtures, with how many each has. */
interface CompetitionOption {
  id: string
  name: string
  logo: string | null
  count: number
}

/**
 * A published expert prediction, or a model forecast, or neither — said in words, not a colour.
 *
 * "No forecast held" is `brief.noForecastHeld` from the core catalogue rather than a key of this
 * area's own: it is the same sentence, already translated, and two copies of it could drift.
 */
function coverageNote(match: Match, t: TranslateFn): { label: string; className: string } {
  if (match.expertPrediction) {
    return { label: t('expert.picker.expertPublished'), className: 'bg-primary-900/60 text-primary-200' }
  }
  if (match.providerForecast?.state === 'available') {
    return { label: t('expert.picker.modelForecastHeld'), className: 'bg-dark-700 text-secondary-200' }
  }
  return { label: t('brief.noForecastHeld'), className: 'bg-dark-700 text-secondary-300' }
}

/**
 * One fixture as a single control.
 *
 * Every text node that can be long sits in a `min-w-0` box and truncates, the kick-off column has a
 * fixed narrow width, and the badges wrap onto their own line. That combination is what keeps the
 * row inside 390px however long a club is called — and the accessible name carries the same four
 * facts in one sentence, since a screen reader gets no benefit from the layout.
 */
const PickerRow: React.FC<{ match: Match; actionLabel: string; onChoose: (match: Match) => void }> = ({
  match, actionLabel, onChoose,
}) => {
  const t = useT()
  const coverage = coverageNote(match, t)
  const live = match.status === 'live' || match.status === 'halftime'
  // Re-derived from the instant on every render, in the chosen zone. `match.time` is the mapper's
  // one-off formatting and stands in only when the payload carried no instant to format.
  const kickoff = formatTime(match.kickoffUtc) ?? match.time

  return (
    <li className="border-b border-dark-800 last:border-b-0">
      <button
        type="button"
        onClick={() => onChoose(match)}
        className="focus-ring-inset tap-target-row flex w-full flex-col gap-1 px-2 py-2.5 text-left transition-colors hover:bg-dark-800/60 sm:px-3"
        aria-label={t('expert.picker.rowAction', {
          action: actionLabel,
          home: match.homeTeam.name,
          away: match.awayTeam.name,
          competition: match.league.name,
          time: kickoff,
        })}
      >
        <div className="flex w-full items-center gap-2">
          <span className="flex w-12 flex-shrink-0 flex-col items-center text-center">
            {live
              ? <span className="text-[11px] font-semibold uppercase tracking-wide text-success-300">{t('fixture.live')}</span>
              : <time className="num text-sm font-semibold text-white" dateTime={match.kickoffUtc ?? undefined}>{kickoff}</time>}
          </span>

          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm text-white">{match.homeTeam.name}</span>
            <span className="block truncate text-sm text-secondary-100">{match.awayTeam.name}</span>
            <span className="block truncate text-[11px] text-secondary-400">{match.league.name}</span>
          </span>

          <span className="flex flex-shrink-0 items-center gap-1 text-primary-300">
            <span className="hidden text-xs font-medium sm:inline">{actionLabel}</span>
            <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
          </span>
        </div>

        <span className="flex flex-wrap gap-1 pl-14">
          <span className={clsx('rounded-full px-2 py-0.5 text-[11px]', coverage.className)}>{coverage.label}</span>
        </span>
      </button>
    </li>
  )
}

/**
 * The filtered fixture list: one day at a time, narrowed by competition and by team name.
 *
 * NO PROVIDER CALL IS MADE. Every read passes `STORED_ONLY`, so the backend answers from rows it
 * already holds: paging through a week of dates spends nothing from the forecast allowance.
 */
const FixtureList: React.FC<{ onChoose: (match: Match) => void; actionLabel: string }> = ({
  onChoose, actionLabel,
}) => {
  const t = useT()
  // The zone is read rather than assumed: it decides which calendar day "today" is, which UTC
  // window the backend is asked for, and what every kick-off below says. A change to it has to
  // reach all three, so it is a dependency of the fetch and not only of the formatting.
  const { zone } = useLocale()
  const [date, setDate] = useState(() => localDateString(0))
  const [matches, setMatches] = useState<Match[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [competitionIds, setCompetitionIds] = useState<string[]>([])
  const [onlyWithoutExpert, setOnlyWithoutExpert] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)

  const retry = useCallback(() => setReloadToken(token => token + 1), [])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        // STORED_ONLY: the backend answers from what it already holds and makes no provider
        // request, so moving between days costs nothing from the daily allowance.
        const result = await footballDataService.getFixturesByDate(date, STORED_ONLY)
        if (!cancelled) setMatches(result)
      } catch (err) {
        console.error('Failed to load fixtures for the picker:', err)
        // A failed request is not an empty day. The list is cleared and the failure is stated.
        // `getErrorMessage` prefers the SERVER'S own words, then its two translated sentences
        // (503, timed out); the empty fallback means that when nothing was said this page states
        // only that the load failed rather than inventing a reason nobody gave.
        //
        // ONE GAP, AND IT IS NOT THIS PACKAGE'S TO CLOSE. Before reaching the fallback,
        // `getErrorMessage` returns axios's own `err.message` — "Network Error" and
        // "Request failed with status code 500" are English strings from the HTTP client, not
        // from the server and not from any catalogue, so a transport failure with no response
        // body puts English under this French title. It is an improvement on the `describeError`
        // this replaced, which synthesised two English sentences of its own, but it is not a
        // guarantee of "the server's words or nothing". src/utils/errors.ts owns that decision;
        // the failed-load test below covers the server-said-something case only.
        if (!cancelled) {
          setError(getErrorMessage(err, ''))
          setMatches([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
    // `zone` appears in nothing above and is a dependency on purpose — do not "clean it up".
    // The day this asks the backend for is a window bounded by the reader's own UTC offsets, so a
    // change of zone is a change of request even when the calendar date in the control has not
    // moved. Without it, a reader who switches zone keeps the previous zone's day of fixtures.
  }, [date, reloadToken, zone])

  /** Finished, postponed and cancelled fixtures are not something to publish a forecast on. */
  const openFixtures = useMemo(() => filterLiveAndScheduledMatches(matches), [matches])

  const competitions = useMemo<CompetitionOption[]>(() => {
    const byId = new Map<string, CompetitionOption>()
    openFixtures.forEach(match => {
      const id = match.league.id || match.league.name
      const existing = byId.get(id)
      if (existing) existing.count += 1
      else byId.set(id, { id, name: match.league.name, logo: match.league.logo ?? null, count: 1 })
    })
    return Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name))
  }, [openFixtures])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return openFixtures.filter(match => {
      if (competitionIds.length > 0 && !competitionIds.includes(match.league.id || match.league.name)) return false
      if (onlyWithoutExpert && match.expertPrediction) return false
      if (!needle) return true
      return match.homeTeam.name.toLowerCase().includes(needle)
        || match.awayTeam.name.toLowerCase().includes(needle)
        || match.league.name.toLowerCase().includes(needle)
    })
  }, [openFixtures, competitionIds, onlyWithoutExpert, query])

  const toggleCompetition = (id: string, next: boolean) => {
    setCompetitionIds(prev => (next ? [...prev, id] : prev.filter(entry => entry !== id)))
  }

  const clearFilters = () => {
    setQuery('')
    setCompetitionIds([])
    setOnlyWithoutExpert(false)
  }

  const filtersActive = query.trim() !== '' || competitionIds.length > 0 || onlyWithoutExpert

  /** Today / Tomorrow / In two days, recomputed each render so a zone change moves them. */
  const dayChips = DAY_OFFSETS.map(offset => ({
    day: localDateString(offset),
    label: offset === 0
      ? t('matchday.relative.today')
      : offset === 1
        ? t('matchday.relative.tomorrow')
        : t('expert.picker.dayAfterTomorrow'),
  }))

  return (
    <div className="card mt-6 overflow-hidden">
      <div className="border-b border-dark-700 p-4">
        <h2 className="text-sm font-semibold text-white">{t('expert.selection.fixturesHeading')}</h2>
        <p className="mt-1 text-xs text-secondary-400">{t('expert.selection.fixturesHint')}</p>
      </div>

      {/* ------------------------------------------------------------------ day */}
      <div className="border-b border-dark-700 p-3 sm:p-4">
        <label htmlFor="picker-date" className="form-label">{t('expert.picker.dayLabel')}</label>
        {/* The date input takes a full line below `sm`: squeezed into a shared row at 390px a
            native date control clips its own value, and "09" is not a date. */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            id="picker-date"
            type="date"
            value={date}
            onChange={event => event.target.value && setDate(event.target.value)}
            className="form-input num w-full py-2 sm:w-auto"
          />
          <div className="flex flex-wrap gap-2">
            {dayChips.map(chip => (
              <button
                key={chip.day}
                type="button"
                onClick={() => setDate(chip.day)}
                aria-pressed={date === chip.day}
                className={clsx(
                  'focus-ring rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
                  date === chip.day ? 'bg-primary-700 text-white' : 'bg-dark-800 text-secondary-200 hover:bg-dark-700',
                )}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>
        {/* Which calendar day, and in which zone, the kick-offs below belong to. A native date
            input states neither in words, and an expert judging whether a fixture is still
            prematch needs both. */}
        <p className="mt-2 text-xs text-secondary-400" data-testid="picker-day-shown">
          {t('expert.picker.dayShown', { date: formatIsoDate(date, false) })}
          {' · '}
          {t('matchday.timesIn', { zone: zoneLabel() })}
        </p>
      </div>

      {/* ------------------------------------------------------------------ filters */}
      <div className="space-y-3 border-b border-dark-700 p-3 sm:p-4">
        <div>
          <label htmlFor="picker-search" className="sr-only">{t('expert.picker.searchLabel')}</label>
          <div className="relative">
            <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-400" aria-hidden="true" />
            <input
              id="picker-search"
              type="search"
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder={t('expert.picker.searchPlaceholder')}
              className="form-input w-full py-2 pl-9"
            />
          </div>
        </div>

        {competitions.length > 1 && (
          // The chip strip scrolls inside itself. The page never scrolls sideways because of it.
          <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 no-scrollbar" role="group" aria-label={t('expert.picker.competitionGroup')}>
            {competitions.map(competition => (
              <CompetitionChip
                key={competition.id}
                name={competition.name}
                logo={competition.logo}
                count={competition.count}
                selected={competitionIds.includes(competition.id)}
                onToggle={next => toggleCompetition(competition.id, next)}
                size="sm"
                className="flex-shrink-0"
              />
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="flex items-center gap-2 text-xs text-secondary-200">
            <input
              type="checkbox"
              checked={onlyWithoutExpert}
              onChange={event => setOnlyWithoutExpert(event.target.checked)}
              className="focus-ring h-4 w-4 rounded border-dark-600 bg-dark-800 text-primary-500"
            />
            {t('expert.picker.onlyWithoutExpert')}
          </label>
          {filtersActive && (
            <button type="button" onClick={clearFilters} className="focus-ring text-xs font-medium text-primary-300 hover:text-primary-200">
              {t('expert.picker.clearFilters')}
            </button>
          )}
        </div>

        {/* One sentence, not a sentence assembled around a styled number: the count sits inside
            the message so each language decides where it goes and what agrees with it. */}
        <p className="num text-xs text-secondary-400" aria-live="polite" data-testid="picker-count">
          {loading
            ? t('expert.picker.loading')
            : t('expert.picker.showing', {
              shown: formatNumber(visible.length),
              total: formatNumber(openFixtures.length),
            })}
        </p>
      </div>

      {/* ------------------------------------------------------------------ the list */}
      {loading ? (
        <div className="p-8"><LoadingSpinner /></div>
      ) : error !== null ? (
        <div className="p-4">
          <EmptyState
            tone="failed"
            title={t('expert.picker.loadFailed')}
            description={error || undefined}
            variant="inline"
            action={
              <button type="button" onClick={retry} className="btn btn-sm btn-secondary">
                {t('expert.retry')}
              </button>
            }
          />
        </div>
      ) : visible.length === 0 ? (
        <div className="p-4">
          <EmptyState
            tone="empty"
            title={filtersActive ? t('expert.picker.emptyFilteredTitle') : t('expert.picker.emptyDayTitle')}
            description={filtersActive ? t('expert.picker.emptyFilteredBody') : t('expert.picker.emptyDayBody')}
            variant="inline"
            action={filtersActive
              ? <button type="button" onClick={clearFilters} className="btn btn-sm btn-secondary">{t('expert.picker.clearFilters')}</button>
              : undefined}
          />
        </div>
      ) : (
        <ul>
          {visible.map(match => (
            <PickerRow key={match.id} match={match} actionLabel={actionLabel} onChoose={onChoose} />
          ))}
        </ul>
      )}
    </div>
  )
}

const ExpertMatchSelectionPage: React.FC = () => {
  const t = useT()
  const navigate = useNavigate()

  const openComposer = (match: Match) => {
    navigate(`/expert/predictions/create?matchId=${encodeURIComponent(match.id)}`)
  }

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8" data-testid="expert-match-selection">
      <Link to="/expert/dashboard" className="focus-ring mb-4 inline-flex items-center gap-1 text-sm text-primary-300 hover:text-primary-200">
        <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
        {t('expert.backToDashboard')}
      </Link>

      <h1 className="text-2xl font-bold text-white sm:text-3xl">{t('expert.dashboard.chooseMatch')}</h1>
      <p className="mt-1 text-sm text-secondary-300">{t('expert.selection.intro')}</p>

      <FixtureList onChoose={openComposer} actionLabel={t('expert.action.writePrediction')} />

      <div className="card mt-6 p-4">
        <h2 className="text-sm font-semibold text-white">{t('expert.selection.howHeading')}</h2>
        <ol className="mt-2 list-inside list-decimal space-y-1 text-xs text-secondary-300">
          <li>{t('expert.selection.how1')}</li>
          <li>
            {t('expert.selection.how2', {
              typed: formatNumber(55),
              whole: formatPercentValue(55, 0),
              decimal: formatNumber(0.55),
            })}
          </li>
          <li>{t('expert.selection.how3')}</li>
        </ol>
        <p className="mt-3 text-xs text-secondary-400">
          {/* `{zero}` is the thing an omitted market must never be shown as. It is formatted so
              that the sentence warning against "0%" does not itself print an English "0%" to a
              French reader. */}
          {t('expert.selection.howNote', { zero: formatPercentValue(0, 0) })}
        </p>
      </div>
    </div>
  )
}

export default ExpertMatchSelectionPage
