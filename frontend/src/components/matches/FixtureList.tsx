import React, { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { onLeagueLogoError } from '@/components/ui/imageFallback'
import FixtureRow from '@/components/ui/FixtureRow'
import useFavourites from '@/hooks/useFavourites'
import type { CompetitionGroup } from './fixtureGrouping'

/**
 * The day's fixtures, grouped by competition.
 *
 * Every fixture is one `FixtureRow`: kickoff, the two clubs, what each source makes most likely,
 * and a star. The competition is a sticky heading rather than a line repeated inside all twenty
 * rows, which is what lets the rows stay one scannable height each.
 *
 * SAVING. The star is optimistic and the store owns the rollback: `setMatchSaved` applies the
 * change immediately, reconciles with what the server actually returns, and restores the previous
 * state before rejecting if the write fails. A star that stayed filled after a failed save would
 * be a claim about the server that is not true, so the rejection is caught here and said out loud
 * instead of swallowed. Signed out, the star is a sign-in invitation, never a silent no-op.
 */

export interface FixtureListProps {
  groups: CompetitionGroup[]
  /** Off when the list is already one competition (a competition page, a single-chip filter). */
  showCompetitionHeadings?: boolean
  /** Off for a summary list that should not open. */
  expandable?: boolean
}

const FixtureList: React.FC<FixtureListProps> = ({
  groups,
  showCompetitionHeadings = true,
  expandable = true,
}) => {
  const navigate = useNavigate()
  const location = useLocation()
  const favourites = useFavourites()
  const [saveError, setSaveError] = useState<string | null>(null)

  const onToggleSave = (matchId: string, next: boolean) => {
    setSaveError(null)
    favourites.setMatchSaved(matchId, next).catch((error: unknown) => {
      setSaveError(error instanceof Error
        ? error.message
        : `That match could not be ${next ? 'saved' : 'removed'}. Nothing was changed.`)
    })
  }

  // Back to exactly this list — same date, same filters — once they have signed in.
  const requireSignIn = () => navigate('/login', { state: { from: location } })

  return (
    <div data-testid="fixture-list">
      {saveError && (
        <p
          role="alert"
          className="mb-3 rounded-lg border border-danger-700/60 bg-danger-900/20 px-3 py-2 text-sm text-danger-200"
          data-testid="fixture-list-save-error"
        >
          {saveError}
        </p>
      )}

      <div className="space-y-4">
        {groups.map(group => (
          <section key={group.id} aria-label={group.name} data-testid="fixture-group">
            {showCompetitionHeadings && (
              <h3 className="sticky top-16 z-10 flex items-center gap-2 border-b border-dark-700 bg-dark-950/95 px-2 py-2 backdrop-blur-sm sm:px-3">
                <img
                  src={group.logo}
                  alt=""
                  aria-hidden="true"
                  className="h-4 w-4 flex-shrink-0 rounded-sm object-contain"
                  onError={onLeagueLogoError}
                />
                <span className="min-w-0 truncate text-sm font-semibold text-white">{group.name}</span>
                {group.country && (
                  <span className="hidden flex-shrink-0 text-xs text-secondary-400 sm:inline">{group.country}</span>
                )}
                <span className="num ml-auto flex-shrink-0 rounded bg-dark-800 px-1.5 text-[11px] text-secondary-200">
                  {group.matches.length}
                  <span className="sr-only"> {group.matches.length === 1 ? 'match' : 'matches'}</span>
                </span>
              </h3>
            )}

            <div className="rounded-lg border border-dark-800 bg-dark-900/40">
              {group.matches.map(match => (
                <FixtureRow
                  key={match.id}
                  match={match}
                  showCompetition={!showCompetitionHeadings}
                  expandable={expandable}
                  saved={favourites.isMatchSaved(match.id)}
                  savePending={favourites.isMatchPending(match.id)}
                  signedIn={favourites.signedIn}
                  onRequireSignIn={requireSignIn}
                  onToggleSave={onToggleSave}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}

export default FixtureList
