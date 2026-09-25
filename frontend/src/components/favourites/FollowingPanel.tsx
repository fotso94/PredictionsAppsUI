import React, { useEffect, useMemo, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import type { Match } from '@/types'
import EmptyState from '@/components/ui/EmptyState'
import { onLeagueLogoError, onTeamLogoError } from '@/components/ui/imageFallback'
import useAuth from '@/hooks/useAuth'
import useFavourites from '@/hooks/useFavourites'
import {
  followedFixturesStore, followIsUnreadable, usePersonalPreferences, FEED_DAYS_AHEAD,
  type FollowedFixture, type FollowedFixturesState,
} from '@/services/favourites.service'
import { getErrorMessage } from '@/utils/errors'
import { isPlayableNow, resultDelay } from '@/utils/resultDelay'
import { teamSubtitle } from '@/utils/squads'
import FollowButton from './FollowButton'

/**
 * The teams and competitions this user follows, and what each of them has next.
 *
 * Three facts are kept apart, because on screen they look the same and they are not:
 *  - a followed team we hold a row for, which can be shown and linked;
 *  - a followed id we hold NO row for, which the API reports under `unresolved` rather than
 *    dropping — "we are following something we cannot show you" is not "you follow nothing", and
 *    silently shortening the list would hide a follow the user could then never remove;
 *  - a load that failed, which is not an empty list at all.
 *
 * The follow limits come from the API (`limits`), never hard-coded here: two places with different
 * numbers is how a UI ends up refusing what the server would have accepted.
 *
 * WHY EACH ROW NOW CARRIES A FIXTURE. This was a directory of links: a name, a logo and a way to
 * unfollow, which told a reader nothing about why the follow was worth keeping. Each row now says
 * what that team or competition plays next, or what they last played — read from the same store
 * the feed above is built from (`followedFixturesStore`), so showing it here costs no extra
 * request. The fixtures themselves live in the feed; this panel stays the place follows are
 * MANAGED, which is a different job from reading them and needs the unfollow control beside every
 * entry.
 */

export interface FollowingPanelProps {
  className?: string
}

/** Day and time of a kick-off, in the reader's own locale and zone. */
const FIXTURE_DAY = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
const FIXTURE_TIME = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' })

const kickoffDate = (match: Match): Date | null => {
  const parsed = match.kickoffUtc ? new Date(match.kickoffUtc) : null
  return parsed && !Number.isNaN(parsed.getTime()) ? parsed : null
}

const isPlayed = (match: Match) => match.status === 'finished'
/*
 * The stored status alone is not enough to say this, and saying it wrongly is the loudest lie on
 * the page: "In play now" is present tense about a match that may have ended hours ago, on a row
 * a reader follows precisely because they care about it. `isPlayableNow` withholds the claim once
 * the result is past its deadline; the fixture then falls through to the next line below, which
 * describes it without asserting anything about right now.
 */
const isInPlay = (match: Match) => isPlayableNow(match)

/** The fixtures in the shared store that this particular follow brought in. */
function fixturesFor(fixtures: FollowedFixture[], kind: 'team' | 'league', id: string): Match[] {
  return fixtures
    .filter(entry => entry.reasons.some(reason => reason.kind === kind && reason.id === id))
    .map(entry => entry.match)
}

/**
 * One line under a followed name: what is happening, what is next, or what was last played.
 *
 * It never says "no fixtures". What it can honestly say is that nothing is STORED for the days
 * this feed covers, which is a statement about our data and not about the competition's calendar.
 *
 * AND A READ THAT FAILED IS NOT AN EMPTY WINDOW. Each follow is a request of its own, and one of
 * them can come back 500 while the others answer. Until the store carried the failed follows by
 * name, this line could not tell the two apart and said "No fixture stored for the next 7 days"
 * for a team whose fixtures nobody had managed to read — a claim about data that never arrived,
 * on the one row where the reader would never think to doubt it. A failure now says it failed and
 * offers the way out the rest of the application already offers: Retry.
 */
const FollowFixtureLine: React.FC<{
  kind: 'team' | 'league'
  id: string
  /** The team's own name, so a team row can name the opponent instead of repeating itself. */
  self?: string
  fixtures: FollowedFixture[]
  status: FollowedFixturesState['status']
  /** True when THIS follow's own request failed, whether or not the others did. */
  unreadable: boolean
  /** True while a rebuild is running, so Retry reports itself instead of looking inert. */
  retrying: boolean
}> = ({ kind, id, self, fixtures, status, unreadable, retrying }) => {
  const mine = useMemo(() => fixturesFor(fixtures, kind, id), [fixtures, kind, id])

  if (status === 'loading' && mine.length === 0) {
    return <p className="truncate text-[11px] text-secondary-500">Loading fixtures…</p>
  }
  /*
   * `status === 'error'` is every follow having failed; `unreadable` is this one having failed.
   * They are the same fact at different scopes and get the same sentence and the same way out —
   * the reader is not helped by learning how many OTHER follows also failed.
   */
  if (status === 'error' || unreadable) {
    return (
      <p className="break-words text-[11px] text-warning-200" data-testid="follow-fixture-failed">
        Its fixtures could not be loaded, so nothing is claimed about them.{' '}
        <button
          type="button"
          onClick={() => { void followedFixturesStore.load() }}
          disabled={retrying}
          className="focus-ring rounded font-medium text-primary-300 underline underline-offset-2 transition-colors hover:text-primary-200 disabled:cursor-not-allowed disabled:opacity-60"
          data-testid="follow-fixture-retry"
        >
          {retrying ? 'Trying again…' : 'Try again'}
        </button>
      </p>
    )
  }

  const opponentOf = (match: Match): string => {
    if (kind !== 'team' || !self) return `${match.homeTeam.name} v ${match.awayTeam.name}`
    const away = match.awayTeam.name === self
    return `${away ? 'away at' : 'at home to'} ${away ? match.homeTeam.name : match.awayTeam.name}`
  }

  const byKickoff = (a: Match, b: Match) =>
    (kickoffDate(a)?.getTime() ?? 0) - (kickoffDate(b)?.getTime() ?? 0)

  const live = mine.filter(isInPlay).sort(byKickoff)[0]
  if (live) {
    return (
      <p className="truncate text-[11px] text-success-300" data-testid="follow-fixture-line">
        In play now, {opponentOf(live)}
      </p>
    )
  }

  /*
   * A fixture past its deadline for a result is not NEXT. Its kickoff has been and gone, and
   * before it was excluded here it sorted to the front of this list and was announced as the
   * team's next match under a date in the past — a second way of saying the same untrue thing the
   * "In play now" line above had just been stopped from saying.
   */
  const next = mine.filter(match => !isPlayed(match) && !resultDelay(match)).sort(byKickoff)[0]
  if (next) {
    const at = kickoffDate(next)
    return (
      <p className="truncate text-[11px] text-secondary-400" data-testid="follow-fixture-line">
        Next {at ? `${FIXTURE_DAY.format(at)}, ${FIXTURE_TIME.format(at)}` : `on ${next.date}`}
        {' — '}{opponentOf(next)}
      </p>
    )
  }

  const last = mine.filter(isPlayed).sort(byKickoff).reverse()[0]
  if (last) {
    const at = kickoffDate(last)
    const score = last.result ? `${last.result.homeScore}–${last.result.awayScore}` : null
    return (
      <p className="truncate text-[11px] text-secondary-400" data-testid="follow-fixture-line">
        Last played {at ? FIXTURE_DAY.format(at) : last.date}
        {score ? `, ${score}` : ''}{' — '}{opponentOf(last)}
      </p>
    )
  }

  /*
   * Said only once there is nothing else to say. A stuck fixture is real and belongs on the page,
   * but it can stay stuck for a fortnight, and letting it hold this line would hide a team's
   * actual upcoming fixtures behind it for that long. The feed's own "Awaiting a result" group
   * carries it either way; this line exists so the follow does not fall through to a flat "no
   * fixture stored", which would be the one reading that is false.
   */
  const stuck = mine.filter(match => resultDelay(match)).sort(byKickoff).reverse()[0]
  if (stuck) {
    return (
      <p className="truncate text-[11px] text-warning-200" data-testid="follow-fixture-line">
        Awaiting a result, {opponentOf(stuck)}
      </p>
    )
  }

  return (
    <p className="truncate text-[11px] text-secondary-500" data-testid="follow-fixture-line">
      No fixture stored for the next <span className="num">{FEED_DAYS_AHEAD}</span> days.
    </p>
  )
}

const FollowingPanel: React.FC<FollowingPanelProps> = ({ className }) => {
  const {
    data, loading, failed, error, reload, setTeamFollowed, setLeagueFollowed,
    isTeamPending, isLeaguePending,
  } = useFavourites()
  // Only the invitations are optional here. A follow row is what the reader came to manage, and
  // no switch on this build hides it.
  const { user } = useAuth()
  const showPrompts = usePersonalPreferences(user?.id ?? null).isOn('prompts')
  const followed = useSyncExternalStore(
    followedFixturesStore.subscribe,
    followedFixturesStore.getState,
    followedFixturesStore.getState,
  )

  // Idempotent once the store matches the follows it was built from, and shared with the feed, so
  // rendering both panels on one page still makes one set of requests.
  useEffect(() => {
    if (data) followedFixturesStore.ensureLoaded()
  }, [data])

  const teams = data?.teams ?? []
  const leagues = data?.leagues ?? []
  const unresolvedTeams = data?.unresolved.teams ?? []
  const unresolvedLeagues = data?.unresolved.leagues ?? []

  const dropUnresolved = (kind: 'team' | 'league', id: string) => {
    const write = kind === 'team' ? setTeamFollowed(id, false) : setLeagueFollowed(id, false)
    void write.catch((err: unknown) => {
      toast.error(getErrorMessage(err, 'That could not be removed. Nothing was changed.'))
    })
  }

  if (loading) {
    return (
      <p className={clsx('py-6 text-center text-sm text-secondary-400', className)} role="status">
        Loading what you follow…
      </p>
    )
  }

  if (failed) {
    return (
      <EmptyState
        className={className}
        tone="failed"
        title="We could not load the teams and competitions you follow."
        description={error ?? 'The request did not complete, so we cannot say what you follow.'}
        action={
          <button
            type="button"
            onClick={() => { void reload().catch(() => undefined) }}
            className="focus-ring rounded-lg border border-dark-700 px-3 py-1.5 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
          >
            Try again
          </button>
        }
        data-testid="following-failed"
      />
    )
  }

  const nothingFollowed = teams.length === 0 && leagues.length === 0
    && unresolvedTeams.length === 0 && unresolvedLeagues.length === 0

  if (nothingFollowed) {
    return (
      <EmptyState
        className={className}
        tone="empty"
        title="You do not follow any teams or competitions yet."
        description="Follow a team and their fixtures join your feed above."
        action={showPrompts ? (
          <div className="flex flex-wrap justify-center gap-2">
            <Link
              to="/leagues"
              className="focus-ring rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-500"
            >
              Browse competitions
            </Link>
            <Link
              to="/predictions/today"
              className="focus-ring rounded-lg border border-dark-700 px-3 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
            >
              See today&rsquo;s matches
            </Link>
          </div>
        ) : undefined}
        data-testid="following-empty"
      />
    )
  }

  return (
    <div className={clsx('space-y-6', className)} data-testid="following">
      <section aria-labelledby="following-teams">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <h3 id="following-teams" className="text-sm font-semibold text-white">Teams</h3>
          {data && (
            <p className="text-xs text-secondary-400">
              <span className="num">{data.teamIds.length}</span> of{' '}
              <span className="num">{data.limits.teams}</span> followed
            </p>
          )}
        </div>
        {teams.length === 0 && unresolvedTeams.length === 0 ? (
          <p className="text-sm text-secondary-400">
            No teams followed yet. Follow a team and their fixtures join your feed above.
          </p>
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {teams.map(team => {
              // The country for a club, the squad for a country — see the note below.
              const subtitle = teamSubtitle(team)
              return (
              <li
                key={team.id}
                className="flex items-center gap-3 rounded-lg bg-dark-800 px-3 py-2"
                data-testid="followed-team"
              >
                <img src={team.logo} alt="" aria-hidden="true" className="h-6 w-6 flex-shrink-0 object-contain" onError={onTeamLogoError} />
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/teams/${team.id}`}
                    className="focus-ring block truncate rounded text-sm text-white hover:underline"
                  >
                    {team.name}
                    {/*
                      WHICH SQUAD, WHERE THE COUNTRY USED TO BE.

                      A country's senior, women's and under-23 squads are three separate rows with
                      one name between them, and a national team carries no country at all — the
                      backend refuses to write a confederation's territory onto a squad — so this
                      slot was blank on exactly the rows where two entries of this list would
                      otherwise read "Spain" twice with nothing to tell them apart. `teamSubtitle`
                      prints the squad for a country and the country for a club, which is what this
                      line always said for a club and still says.
                    */}
                    {subtitle && (
                      <span className="ml-2 text-xs text-secondary-400" data-testid="followed-team-squad">
                        {subtitle}
                      </span>
                    )}
                  </Link>
                  <FollowFixtureLine
                    kind="team"
                    id={team.id}
                    self={team.name}
                    fixtures={followed.fixtures}
                    status={followed.status}
                    unreadable={followIsUnreadable(followed, 'team', team.id)}
                    retrying={followed.refreshing}
                  />
                </div>
                <FollowButton kind="team" id={team.id} name={team.name} variant="icon" size="sm" />
              </li>
              )
            })}
            {unresolvedTeams.map(id => (
              <li key={id} className="flex items-center gap-3 rounded-lg border border-dashed border-dark-700 px-3 py-2" data-testid="followed-team-unresolved">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-secondary-200">A team we no longer hold</p>
                  <p className="truncate text-[11px] text-secondary-500">
                    It is still on your list, but there is no record of it in our data, so we cannot
                    show its name or fixtures.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => dropUnresolved('team', id)}
                  disabled={isTeamPending(id)}
                  className="focus-ring flex-shrink-0 rounded-lg border border-dark-700 px-2 py-1 text-xs font-medium text-secondary-200 transition-colors hover:bg-dark-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="following-competitions">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <h3 id="following-competitions" className="text-sm font-semibold text-white">Competitions</h3>
          {data && (
            <p className="text-xs text-secondary-400">
              <span className="num">{data.leagueIds.length}</span> of{' '}
              <span className="num">{data.limits.leagues}</span> followed
            </p>
          )}
        </div>
        {leagues.length === 0 && unresolvedLeagues.length === 0 ? (
          <p className="text-sm text-secondary-400">
            No competitions followed yet. Follow one and its fixtures join your feed above.
          </p>
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {leagues.map(league => (
              <li
                key={league.id}
                className="flex items-center gap-3 rounded-lg bg-dark-800 px-3 py-2"
                data-testid="followed-league"
              >
                <img src={league.logo} alt="" aria-hidden="true" className="h-6 w-6 flex-shrink-0 object-contain" onError={onLeagueLogoError} />
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/league/${league.id}`}
                    className="focus-ring block truncate rounded text-sm text-white hover:underline"
                  >
                    {league.name}
                    {league.country && <span className="ml-2 text-xs text-secondary-400">{league.country}</span>}
                  </Link>
                  <FollowFixtureLine
                    kind="league"
                    id={league.id}
                    fixtures={followed.fixtures}
                    status={followed.status}
                    unreadable={followIsUnreadable(followed, 'league', league.id)}
                    retrying={followed.refreshing}
                  />
                </div>
                <FollowButton kind="league" id={league.id} name={league.name} variant="icon" size="sm" />
              </li>
            ))}
            {unresolvedLeagues.map(id => (
              <li key={id} className="flex items-center gap-3 rounded-lg border border-dashed border-dark-700 px-3 py-2" data-testid="followed-league-unresolved">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-secondary-200">A competition we no longer hold</p>
                  <p className="truncate text-[11px] text-secondary-500">
                    It is still on your list, but there is no record of it in our data.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => dropUnresolved('league', id)}
                  disabled={isLeaguePending(id)}
                  className="focus-ring flex-shrink-0 rounded-lg border border-dark-700 px-2 py-1 text-xs font-medium text-secondary-200 transition-colors hover:bg-dark-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

export default FollowingPanel
