import React, { useId, useMemo, useState } from 'react'
import clsx from 'clsx'
import useAuth from '@/hooks/useAuth'
import useFavourites from '@/hooks/useFavourites'
import { buildSavedFixturesCalendar } from '@/services/calendar'
import { favouritesApi, personalPreferencesStore, usePersonalPreferences } from '@/services/favourites.service'
import { getErrorMessage } from '@/utils/errors'
import type { SavedMatch } from '@/types'

/**
 * What this reader's own pages are allowed to show them, and what they can do with their data.
 *
 * It sits beside the follow list because that is where somebody already comes to change what
 * their pages contain; it is deliberately not a settings route of its own, which is where
 * controls like these go to be never found.
 *
 * FOUR THINGS LIVE HERE
 *
 *  1. A SCORE-ONLY PATH. Forecasts, tips and probabilities off, football on. A reader who wants
 *     fixtures, results and the clubs they follow, and does not want a probability beside them,
 *     switches one thing and keeps everything else. It persists, it is offered as a preference
 *     rather than as a warning, and nothing in this build ever asks them to turn it back on.
 *
 *  2. A PAUSE. One switch that stops everything optional at once, immediately, and puts it all
 *     back when they say so — with their own settings, not defaults. The wording around it is the
 *     most carefully chosen text in this file and is explained where it is written.
 *
 *  3. EXPORT. Their data, in formats that open in a text editor and in a spreadsheet, plus the
 *     calendar snapshot. Available at all times, and available from inside the deletion
 *     confirmation, because the moment somebody is leaving is exactly when they need it.
 *
 *  4. DELETION. Of everything this application holds under these pages. Asked once, in plain
 *     words, saying what goes and what stays. No second pleading step, no greyed-out button that
 *     comes alive after a countdown, no "are you sure you want to lose your progress".
 *
 * WHAT NONE OF THIS DOES, ENFORCED BY READING IT BACK
 *
 * Nothing on this panel congratulates, counts up a streak, marks an absence, or suggests
 * following one more team. The numbers it shows are there because a reader about to delete
 * something is owed a count of what will go. A reader who pauses, exports and leaves has used
 * this panel exactly as intended.
 */

// --------------------------------------------------------------------------- the switch
const Switch: React.FC<{
  checked: boolean
  onChange: (next: boolean) => void
  label: string
  description: React.ReactNode
  /** Rendered under the description when a pause is overriding this setting. */
  overridden?: boolean
  testId: string
}> = ({ checked, onChange, label, description, overridden = false, testId }) => {
  const labelId = useId()
  const descriptionId = useId()

  return (
    <div className="flex items-start gap-3 py-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        aria-describedby={descriptionId}
        onClick={() => onChange(!checked)}
        data-testid={testId}
        data-checked={checked ? 'true' : 'false'}
        className={clsx(
          'focus-ring mt-0.5 inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full border transition-colors',
          checked
            ? 'border-primary-500 bg-primary-600'
            : 'border-dark-600 bg-dark-700',
        )}
      >
        <span
          aria-hidden="true"
          className={clsx(
            'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
            checked ? 'translate-x-6' : 'translate-x-1',
          )}
        />
      </button>
      <div className="min-w-0 flex-1">
        <p id={labelId} className="text-sm font-medium text-white">{label}</p>
        <p id={descriptionId} className="mt-0.5 text-xs text-secondary-400">{description}</p>
        {overridden && (
          <p className="mt-1 text-[11px] text-warning-200">
            Not showing at the moment: everything optional is paused.
          </p>
        )}
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- downloading
/**
 * Hand the reader a file.
 *
 * A blob URL and a synthetic click, which is the only way a page can produce a file the browser
 * saves without a server round trip — and the point of this panel is that taking your data with
 * you costs nothing and asks nobody. The URL is revoked on a timer rather than immediately:
 * revoking it in the same tick cancels the save in some browsers.
 */
function downloadTextFile(filename: string, mediaType: string, text: string): void {
  const blob = new Blob([text], { type: `${mediaType};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

/** One field of a CSV row: quoted when it has to be, and never able to start a formula. */
function csvField(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return ''
  const text = String(value)
  // A cell beginning =, +, - or @ is executed as a formula by several spreadsheet applications
  // when the file is opened. A note somebody typed is text, and it stays text.
  const guarded = /^[=+\-@]/.test(text) ? `'${text}` : text
  return /[",\n\r]/.test(guarded) ? `"${guarded.replace(/"/g, '""')}"` : guarded
}

const csvRow = (fields: Array<string | number | null | undefined>): string =>
  fields.map(csvField).join(',')

/**
 * A FINISHED fixture's stored score, or null. Assembled from the result row and nothing else.
 *
 * The status check is the whole point and it is not defensive padding. A fixture that is `live`
 * or `halftime` carries a result row too — the score as it stands right now — and returning it
 * from something the JSON calls `finalScoreAsStored` and the spreadsheet heads "Final score as
 * stored" would publish a running score as a settled one. An export is read long after it was
 * taken and never updates, so "Everton 1-0" written under that heading at half time is a claim
 * that outlives the match and is simply wrong by full time. `postponed` and `cancelled` are
 * excluded for the same reason: whatever is in the row, it did not finish that way.
 */
function storedScore(entry: SavedMatch): string | null {
  if (entry.match.status !== 'finished') return null
  const result = entry.match.result
  if (!result) return null
  const { homeScore, awayScore } = result
  if (typeof homeScore !== 'number' || typeof awayScore !== 'number') return null
  return `${homeScore}-${awayScore}`
}

// --------------------------------------------------------------------------- the panel
export interface PersonalControlsProps {
  className?: string
}

type Removal = {
  attempted: number
  removed: number
  failures: string[]
}

const PersonalControls: React.FC<PersonalControlsProps> = ({ className }) => {
  const { user } = useAuth()
  const { data, loaded, failed, error, reload } = useFavourites()
  const prefs = usePersonalPreferences(user?.id ?? null)

  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteOutcome, setDeleteOutcome] = useState<Removal | null>(null)
  const [exportProblem, setExportProblem] = useState<string | null>(null)
  const [calendarOutcome, setCalendarOutcome] = useState<string | null>(null)

  const saved = useMemo<SavedMatch[]>(() => {
    if (!data) return []
    const { upcoming, live, finished } = data.savedMatches
    return [...upcoming, ...live, ...finished]
  }, [data])

  /**
   * Two counts that can disagree, kept apart deliberately.
   *
   * `heldTotal` is what the server says it holds; `saved.length` is what it managed to serialise.
   * A save whose fixture row has gone appears in the first and not the second — so it can be
   * neither exported nor deleted from here, and the reader is told rather than left to assume the
   * difference does not exist.
   */
  const heldTotal = data?.savedMatches.counts.total ?? 0
  const unlistedSaves = Math.max(0, heldTotal - saved.length)
  const followedTeams = data?.teamIds.length ?? 0
  const followedLeagues = data?.leagueIds.length ?? 0

  const takeCalendar = () => {
    setCalendarOutcome(null)
    try {
      const snapshot = buildSavedFixturesCalendar(saved)
      if (snapshot.events === 0) {
        setCalendarOutcome(
          'Nothing was written: none of your saved fixtures has a stored date to put in a '
          + 'calendar, so there was no entry to make.',
        )
        return
      }
      downloadTextFile(snapshot.filename, 'text/calendar', snapshot.text)
      const notes: string[] = [
        `${snapshot.events} ${snapshot.events === 1 ? 'entry' : 'entries'} written.`,
      ]
      if (snapshot.dateOnly > 0) {
        notes.push(
          `${snapshot.dateOnly} of them ${snapshot.dateOnly === 1 ? 'is' : 'are'} all-day, because `
          + 'only a date is stored for those fixtures and no kick-off time.',
        )
      }
      if (snapshot.skipped > 0) {
        notes.push(
          `${snapshot.skipped} saved ${snapshot.skipped === 1 ? 'fixture was' : 'fixtures were'} `
          + 'left out: no date is stored for them, and a date was not going to be invented.',
        )
      }
      if (unlistedSaves > 0) {
        notes.push(
          `${unlistedSaves} further ${unlistedSaves === 1 ? 'save is' : 'saves are'} held that we `
          + 'cannot list, so they are not in the file either.',
        )
      }
      setCalendarOutcome(notes.join(' '))
    } catch (problem) {
      setCalendarOutcome(getErrorMessage(problem, 'The calendar file could not be built, so nothing was downloaded.'))
    }
  }

  const takeJson = () => {
    setExportProblem(null)
    try {
      const takenAt = new Date().toISOString()
      const payload = {
        export: {
          takenAt,
          application: 'Soccer Predictions',
          about:
            'The data this application holds for your account on its personal pages, as it was at '
            + 'the moment above. It is a copy. Downloading it changes nothing and removes nothing.',
          notIncluded: [
            'Your account record and sign-in details, which these pages cannot read.',
            'Model forecasts and expert predictions. Those are published by their sources and '
            + 'measured against results site-wide; they are not your data.',
            unlistedSaves > 0
              ? `${unlistedSaves} saved ${unlistedSaves === 1 ? 'match' : 'matches'} the server `
                + 'holds but could not list, because the fixture behind them is no longer stored.'
              : 'Nothing else: every save and follow the server could list is here.',
          ],
        },
        account: {
          email: user?.email ?? null,
          username: user?.username ?? null,
        },
        preferences: {
          showForecastsAndTips: prefs.forecasts,
          showPromptsToBrowseOrFollow: prefs.prompts,
          liveUpdatesWhileAMatchIsInPlay: prefs.liveUpdates,
          everythingOptionalPaused: prefs.paused,
          storedWhere: 'This browser only. The API has no field for these, so they do not follow '
            + 'you to another device.',
        },
        following: {
          teams: (data?.teams ?? []).map(team => ({ id: team.id, name: team.name, country: team.country ?? null })),
          leagues: (data?.leagues ?? []).map(league => ({ id: league.id, name: league.name, country: league.country ?? null })),
          followedIdsWeHoldNoRecordFor: {
            teams: data?.unresolved.teams ?? [],
            leagues: data?.unresolved.leagues ?? [],
          },
        },
        savedMatches: saved.map(entry => ({
          matchId: entry.matchId,
          savedAt: entry.savedAt,
          noteUpdatedAt: entry.updatedAt,
          yourNote: entry.note,
          fixture: {
            date: entry.match.date,
            kickoffUtc: entry.match.kickoffUtc ?? null,
            status: entry.match.status,
            competition: entry.match.league?.name ?? null,
            home: entry.match.homeTeam?.name ?? null,
            away: entry.match.awayTeam?.name ?? null,
            venue: entry.match.venue || null,
            finalScoreAsStored: storedScore(entry),
          },
        })),
      }
      downloadTextFile(
        `your-data-${takenAt.slice(0, 10)}.json`,
        'application/json',
        `${JSON.stringify(payload, null, 2)}\n`,
      )
    } catch (problem) {
      setExportProblem(getErrorMessage(problem, 'The file could not be built, so nothing was downloaded.'))
    }
  }

  const takeCsv = () => {
    setExportProblem(null)
    try {
      const takenAt = new Date().toISOString()
      const rows = [
        csvRow(['Saved at', 'Kick-off (UTC)', 'Date', 'Status', 'Competition', 'Home', 'Away', 'Final score as stored', 'Your note']),
        ...saved.map(entry => csvRow([
          entry.savedAt,
          entry.match.kickoffUtc ?? '',
          entry.match.date,
          entry.match.status,
          entry.match.league?.name ?? '',
          entry.match.homeTeam?.name ?? '',
          entry.match.awayTeam?.name ?? '',
          storedScore(entry) ?? '',
          entry.note ?? '',
        ])),
      ]
      downloadTextFile(
        `your-saved-matches-${takenAt.slice(0, 10)}.csv`,
        'text/csv',
        `${rows.join('\r\n')}\r\n`,
      )
    } catch (problem) {
      setExportProblem(getErrorMessage(problem, 'The file could not be built, so nothing was downloaded.'))
    }
  }

  /**
   * Remove every save and every follow this page can enumerate, then forget the local settings.
   *
   * One request per record, because that is the only shape the API offers: there is no bulk
   * delete under /api/v1/me. Each outcome is counted separately and a failure is reported with
   * the server's own words — "deleted" when half of it is still there would be the worst lie this
   * panel could tell, given what the reader pressed the button for.
   */
  const deleteEverything = async () => {
    setDeleting(true)
    setDeleteOutcome(null)
    const failures: string[] = []
    let removed = 0
    const savedIds = saved.map(entry => entry.matchId)
    const teamIds = [...(data?.teamIds ?? []), ...(data?.unresolved.teams ?? [])]
    const leagueIds = [...(data?.leagueIds ?? []), ...(data?.unresolved.leagues ?? [])]
    const attempted = savedIds.length + teamIds.length + leagueIds.length

    for (const matchId of savedIds) {
      try {
        await favouritesApi.unsaveMatch(matchId)
        removed += 1
      } catch (problem) {
        failures.push(getErrorMessage(problem, 'a saved match could not be removed'))
      }
    }
    for (const teamId of teamIds) {
      try {
        await favouritesApi.follow('team', teamId, false)
        removed += 1
      } catch (problem) {
        failures.push(getErrorMessage(problem, 'a followed team could not be removed'))
      }
    }
    for (const leagueId of leagueIds) {
      try {
        await favouritesApi.follow('league', leagueId, false)
        removed += 1
      } catch (problem) {
        failures.push(getErrorMessage(problem, 'a followed competition could not be removed'))
      }
    }

    personalPreferencesStore.forget()
    // Whatever happened, the panel above must now show what the SERVER holds, not what this page
    // assumed it would hold. A reload is the only thing that can establish that.
    await reload().catch(() => undefined)

    setDeleting(false)
    setConfirmingDelete(false)
    setDeleteOutcome({ attempted, removed, failures })
  }

  const nothingToRemove = loaded && !failed && heldTotal === 0 && followedTeams === 0
    && followedLeagues === 0 && (data?.unresolved.teams.length ?? 0) === 0
    && (data?.unresolved.leagues.length ?? 0) === 0
  const exportsReady = loaded && !failed
  const paused = prefs.paused

  return (
    <div className={clsx('space-y-8', className)} data-testid="personal-controls">
      {/* ------------------------------------------------------------ what may appear */}
      <section aria-labelledby="personal-controls-showing" className="space-y-1">
        <h3 id="personal-controls-showing" className="text-sm font-semibold text-white">
          What these pages show you
        </h3>
        <p className="text-xs text-secondary-400">
          Everything below is optional and only ever appears while you are on the page. This
          application has no alerts: it sends no push message and no text message, and the only
          email it sends is account email you asked for, such as a password reset.
        </p>

        {/*
          THE PAUSE, AND THE SENTENCE UNDER IT.

          The second sentence is not hedging and it is not legal cover. A control that reads as a
          block on gambling, on a page that can only decide what to draw, would send somebody who
          needs a real tool away believing they already have one. It says exactly what it does and
          exactly what it does not, and it stays in the panel whether the pause is on or off.
        */}
        <div
          className={clsx(
            'mt-3 rounded-lg border px-3 py-3',
            paused ? 'border-warning-200/40 bg-warning-200/5' : 'border-dark-700 bg-dark-800/40',
          )}
          data-testid="personal-pause"
          data-paused={paused ? 'true' : 'false'}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-medium text-white">
                {paused ? 'Everything optional is paused.' : 'Pause everything optional'}
              </p>
              <p className="mt-0.5 text-xs text-secondary-400">
                {paused
                  ? 'No forecasts, no tips, no prompts and no automatic updates on your pages. Your '
                    + 'fixtures, results and follows are untouched, and your settings below are kept '
                    + 'exactly as they were.'
                  : 'One switch. It stops the forecasts, the prompts and the automatic updates on '
                    + 'your pages at once, and puts your own settings back when you turn it off.'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => prefs.setPaused(!paused)}
              data-testid="personal-pause-toggle"
              className={clsx(
                'focus-ring flex-shrink-0 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                paused
                  ? 'border border-dark-600 text-secondary-100 hover:bg-dark-700 hover:text-white'
                  : 'bg-primary-600 text-white hover:bg-primary-500',
              )}
            >
              {paused ? 'Turn it back on' : 'Pause everything'}
            </button>
          </div>
          <p className="mt-2 text-[11px] text-secondary-500">
            This changes what this application shows you here. It is not a bookmaker
            self-exclusion, it does not block any betting site, app or account, and it reaches
            nothing outside this page. If you want a block that does, that has to come from your
            bookmaker or from a tool made for it.
          </p>
        </div>

        <div className="divide-y divide-dark-800" data-testid="personal-surfaces">
          <Switch
            checked={prefs.forecasts}
            onChange={next => prefs.setSurface('forecasts', next)}
            label="Forecasts and tips"
            description={
              <>
                Model probabilities and expert tips beside a fixture on your pages. Turn this off
                for scores only: fixtures, results and the teams you follow stay exactly as they
                are.
              </>
            }
            overridden={paused && prefs.forecasts}
            testId="personal-switch-forecasts"
          />
          <Switch
            checked={prefs.prompts}
            onChange={next => prefs.setSurface('prompts', next)}
            /*
             * Named for what it controls without using the phrasing it exists to prevent. An
             * earlier label read "Invitations to browse or follow more", which described the
             * category accurately and put "follow more" on the page — and the copy check in
             * e2e/live/personal-controls.spec.ts caught it, which is what that check is for.
             */
            label="Invitations to browse elsewhere"
            description="The links on your own pages that point at another page to read, or at another team to follow."
            overridden={paused && prefs.prompts}
            testId="personal-switch-prompts"
          />
          <Switch
            checked={prefs.liveUpdates}
            onChange={next => prefs.setSurface('liveUpdates', next)}
            label="Update a match in play by itself"
            description={
              <>
                While a match you saved is being played, re-read its score about once a minute.
                With this off, scores are whatever they were when the page loaded, and your feed
                says so rather than letting them look current.
              </>
            }
            overridden={paused && prefs.liveUpdates}
            testId="personal-switch-live"
          />
        </div>

        <p className="pt-1 text-[11px] text-secondary-500">
          These three settings are kept in this browser, for this account. They do not follow you
          to another device or another browser.
          {!prefs.durable && (
            <span className="text-warning-200">
              {' '}This browser refused to store the last change, so it will be forgotten when the
              page reloads.
            </span>
          )}
        </p>
      </section>

      {/* ------------------------------------------------------------ taking it with you */}
      <section aria-labelledby="personal-controls-export" className="space-y-2">
        <h3 id="personal-controls-export" className="text-sm font-semibold text-white">
          Take your data with you
        </h3>
        <p className="text-xs text-secondary-400">
          A copy of what this application holds for you, in files that open anywhere. Downloading
          changes nothing and removes nothing.
        </p>

        {failed && (
          <p className="text-xs text-warning-200" data-testid="personal-export-blocked">
            {error ?? 'Your saved matches and follows could not be loaded, so there is nothing to '
              + 'copy from yet.'}{' '}
            An export built now would be short without being able to say by how much, so the
            buttons are held back until the list loads.
          </p>
        )}

        {exportsReady && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={takeJson}
                data-testid="personal-export-json"
                className="focus-ring rounded-lg border border-dark-600 px-3 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
              >
                Everything, as a JSON file
              </button>
              <button
                type="button"
                onClick={takeCsv}
                data-testid="personal-export-csv"
                className="focus-ring rounded-lg border border-dark-600 px-3 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
              >
                Saved matches, as a spreadsheet
              </button>
            </div>
            <p className="text-[11px] text-secondary-500">
              The JSON holds your saved matches with their notes, the teams and competitions you
              follow, and these settings; it opens in any text editor. The spreadsheet file holds
              the saved matches only.
              {unlistedSaves > 0 && (
                <>
                  {' '}
                  <span className="num">{unlistedSaves}</span> further{' '}
                  {unlistedSaves === 1 ? 'save is' : 'saves are'} held that we cannot list, because
                  the fixture behind {unlistedSaves === 1 ? 'it' : 'them'} is no longer stored, so{' '}
                  {unlistedSaves === 1 ? 'it is' : 'they are'} not in either file.
                </>
              )}
            </p>
            {exportProblem && (
              <p className="text-xs text-warning-200" role="status" data-testid="personal-export-problem">
                {exportProblem}
              </p>
            )}

            {/* ------------------------------------------------ the calendar snapshot */}
            <div className="rounded-lg border border-dark-700 bg-dark-800/40 px-3 py-3">
              <p className="text-sm font-medium text-white">Your saved fixtures as a calendar file</p>
              {/*
                E4's whole point, and it is written HERE — above the button, in the same size type
                as everything else on this card. A reader decides whether to import a file before
                they press the button, not after they find a footnote.
              */}
              <p className="mt-1 text-xs text-secondary-300" data-testid="calendar-snapshot-warning">
                This is a one-time snapshot, not a calendar you subscribe to. The entries it makes
                will never update: if a fixture is moved or called off after you download it, your
                calendar will still show the old kick-off. Download it again to take a fresh copy.
              </p>
              <button
                type="button"
                onClick={takeCalendar}
                disabled={saved.length === 0}
                data-testid="personal-export-calendar"
                className="focus-ring mt-2 rounded-lg border border-dark-600 px-3 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                Download the snapshot
              </button>
              {saved.length === 0 && (
                <p className="mt-2 text-[11px] text-secondary-500">
                  There is nothing to put in it: no saved fixture is listed for this account.
                </p>
              )}
              {calendarOutcome && (
                <p className="mt-2 text-xs text-secondary-300" role="status" data-testid="calendar-outcome">
                  {calendarOutcome}
                </p>
              )}
            </div>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------ deletion */}
      <section aria-labelledby="personal-controls-delete" className="space-y-2">
        <h3 id="personal-controls-delete" className="text-sm font-semibold text-white">
          Delete your data
        </h3>

        {!confirmingDelete && (
          <>
            <p className="text-xs text-secondary-400">
              Removes every saved match and its notes, every team and competition you follow, and
              the settings above. It cannot be undone from here.
            </p>
            <button
              type="button"
              onClick={() => { setDeleteOutcome(null); setConfirmingDelete(true) }}
              disabled={!loaded || failed || nothingToRemove}
              data-testid="personal-delete-open"
              className="focus-ring rounded-lg border border-danger-500/60 px-3 py-2 text-sm font-medium text-danger-300 transition-colors hover:bg-danger-500/10 hover:text-danger-200 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Delete my saved matches and follows
            </button>
            {nothingToRemove && (
              <p className="text-[11px] text-secondary-500" data-testid="personal-delete-nothing">
                There is nothing to delete: this account has no saved match and follows nothing.
              </p>
            )}
            {failed && !nothingToRemove && (
              <p className="text-[11px] text-secondary-500">
                Held back until your list loads: deleting what we could not read would leave both
                of us guessing what went.
              </p>
            )}
          </>
        )}

        {confirmingDelete && (
          /*
           * Asked ONCE. Both answers are buttons of the same size, sitting side by side, and
           * neither is pre-selected or hidden behind a delay. The offer to download first is not
           * an attempt to talk anybody out of it — it is the one piece of help somebody about to
           * delete their data actually needs, and it is the same control as the one above.
           */
          <div
            className="rounded-lg border border-danger-500/50 bg-danger-500/5 px-3 py-3"
            role="group"
            aria-labelledby="personal-delete-heading"
            data-testid="personal-delete-confirm"
          >
            <p id="personal-delete-heading" className="text-sm font-semibold text-white">
              Delete your saved matches and follows?
            </p>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <div>
                <p className="text-xs font-medium text-secondary-200">What goes</p>
                <ul className="mt-1 space-y-0.5 text-xs text-secondary-300">
                  <li>
                    <span className="num">{saved.length}</span> saved{' '}
                    {saved.length === 1 ? 'match' : 'matches'}, with the private notes on them.
                  </li>
                  <li>
                    <span className="num">{followedTeams}</span>{' '}
                    {followedTeams === 1 ? 'team' : 'teams'} and{' '}
                    <span className="num">{followedLeagues}</span>{' '}
                    {followedLeagues === 1 ? 'competition' : 'competitions'} you follow.
                  </li>
                  <li>The three settings above, from this browser.</li>
                </ul>
              </div>
              <div>
                <p className="text-xs font-medium text-secondary-200">What stays</p>
                <ul className="mt-1 space-y-0.5 text-xs text-secondary-300">
                  <li>
                    Your account and sign-in details. This build has no way for you to close your
                    own account, so that has to be asked of an administrator.
                  </li>
                  <li>Fixtures, results and everything published by a source. None of it is yours to delete.</li>
                  {unlistedSaves > 0 && (
                    <li className="text-warning-200">
                      <span className="num">{unlistedSaves}</span> saved{' '}
                      {unlistedSaves === 1 ? 'match' : 'matches'} the server holds but cannot list.
                      We cannot remove {unlistedSaves === 1 ? 'it' : 'them'} from here.
                    </li>
                  )}
                </ul>
              </div>
            </div>

            <p className="mt-3 text-xs text-secondary-300">
              You can take a copy first — the buttons above do that, and they stay available after
              you decide.
            </p>

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => { void deleteEverything() }}
                disabled={deleting}
                data-testid="personal-delete-confirm-yes"
                className="focus-ring rounded-lg bg-danger-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-danger-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {deleting ? 'Deleting…' : 'Delete it'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmingDelete(false)}
                disabled={deleting}
                data-testid="personal-delete-confirm-no"
                className="focus-ring rounded-lg border border-dark-600 px-3 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                Keep it
              </button>
            </div>
          </div>
        )}

        {deleteOutcome && (
          <p
            className={clsx('text-xs', deleteOutcome.failures.length > 0 ? 'text-warning-200' : 'text-secondary-300')}
            role="status"
            data-testid="personal-delete-outcome"
          >
            {deleteOutcome.failures.length === 0
              ? (deleteOutcome.attempted === 0
                // "Nothing left to remove" would be false if the server is still holding saves
                // this page cannot enumerate, and that is the one case where the reader would
                // never find out any other way.
                ? (unlistedSaves > 0
                  ? `Your settings in this browser were reset. There was nothing else this page `
                    + `could remove, but the server still holds ${unlistedSaves} saved `
                    + `${unlistedSaves === 1 ? 'match' : 'matches'} it could not list, and those are still there.`
                  : 'There was nothing left to remove. Your settings in this browser were reset.')
                : `Removed ${deleteOutcome.removed} of ${deleteOutcome.attempted} records, and reset your settings in this browser.`
                  + (unlistedSaves > 0
                    ? ` The server still holds ${unlistedSaves} saved `
                      + `${unlistedSaves === 1 ? 'match' : 'matches'} it could not list, and those are still there.`
                    : ''))
              : `Removed ${deleteOutcome.removed} of ${deleteOutcome.attempted} records. `
                + `${deleteOutcome.failures.length} could not be removed: ${deleteOutcome.failures[0]} `
                + 'The rest of your data is unchanged, and the list above now shows what the server still holds.'}
          </p>
        )}
      </section>
    </div>
  )
}

export default PersonalControls
