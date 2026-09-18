import React from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import EmptyState from '@/components/ui/EmptyState'
import { onLeagueLogoError, onTeamLogoError } from '@/components/ui/imageFallback'
import useFavourites from '@/hooks/useFavourites'
import { getErrorMessage } from '@/utils/errors'
import FollowButton from './FollowButton'

/**
 * The teams and competitions this user follows.
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
 */

export interface FollowingPanelProps {
  className?: string
}

const FollowingPanel: React.FC<FollowingPanelProps> = ({ className }) => {
  const {
    data, loading, failed, error, reload, setTeamFollowed, setLeagueFollowed,
    isTeamPending, isLeaguePending,
  } = useFavourites()

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
        description="Follow a team to see their fixtures here."
        action={
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
        }
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
            No teams followed yet. Follow a team to see their fixtures here.
          </p>
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {teams.map(team => (
              <li
                key={team.id}
                className="flex items-center gap-3 rounded-lg bg-dark-800 px-3 py-2"
                data-testid="followed-team"
              >
                <img src={team.logo} alt="" aria-hidden="true" className="h-6 w-6 flex-shrink-0 object-contain" onError={onTeamLogoError} />
                <Link
                  to={`/teams/${team.id}`}
                  className="focus-ring min-w-0 flex-1 truncate rounded text-sm text-white hover:underline"
                >
                  {team.name}
                  {team.country && <span className="ml-2 text-xs text-secondary-400">{team.country}</span>}
                </Link>
                <FollowButton kind="team" id={team.id} name={team.name} variant="icon" size="sm" />
              </li>
            ))}
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
            No competitions followed yet. Follow one to keep its fixtures within reach.
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
                <Link
                  to={`/league/${league.id}`}
                  className="focus-ring min-w-0 flex-1 truncate rounded text-sm text-white hover:underline"
                >
                  {league.name}
                  {league.country && <span className="ml-2 text-xs text-secondary-400">{league.country}</span>}
                </Link>
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
