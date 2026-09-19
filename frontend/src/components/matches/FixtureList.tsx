import React, { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { onLeagueLogoError } from '@/components/ui/imageFallback'
import FixtureRow from '@/components/ui/FixtureRow'
import useMatchSaving, { fixtureHrefFrom } from '@/components/favourites/useMatchSaving'
import type { Match } from '@/types'
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
 *
 * SIGNED OUT, THE STAR STILL FINISHES THE JOB. This list is the entry point most readers use, and
 * it used to be the one that dead-ended: it pushed a sign-in handoff of its own carrying only
 * where to come back to, so the visitor signed in, landed back on the right filtered list, and
 * found the match exactly as unsaved as they had left it. It now goes through the same
 * `useMatchSaving().requireSignIn` the match page uses, naming the match it was asked to save —
 * one mechanism, one set of guarantees (nothing is saved that was not asked for, and an intent
 * that has gone stale is dropped rather than acted on; see useMatchSaving.ts).
 *
 * AND THE FIXTURE LINK REMEMBERS THIS LIST. `fixtureHrefFrom` puts the reader's own filtered list
 * in the fixture URL, so the way back from the match page survives a sign-in round trip that
 * rewrites the history entry behind it. Without it the reader came back from signing in and the
 * only way back to results was an unfiltered day.
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
  const location = useLocation()
  // The failure is shown in place, beside the list, so a toast saying the same thing twice would
  // be noise — and a toast that has already faded cannot answer "did that save work?".
  const saving = useMatchSaving({ toastErrors: false })
  const [saveError, setSaveError] = useState<string | null>(null)

  // The fixture goes with the write so the saved lists can show it at once, rather than only when
  // the server's own copy comes back.
  const onToggleSave = (match: Match, next: boolean) => {
    setSaveError(null)
    void saving.toggleSave(match.id, next, match).then(failure => {
      if (failure) setSaveError(failure)
    })
  }

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
                  href={fixtureHrefFrom(match.id, location)}
                  showCompetition={!showCompetitionHeadings}
                  expandable={expandable}
                  saved={saving.isSaved(match.id)}
                  savePending={saving.isPending(match.id)}
                  signedIn={saving.signedIn}
                  // Named, so the sign-in form can say which match is waiting and the save can
                  // finish itself afterwards without the reader hunting for the star again.
                  onRequireSignIn={() => saving.requireSignIn({
                    matchId: match.id,
                    label: `${match.homeTeam.name} versus ${match.awayTeam.name}`,
                  })}
                  onToggleSave={(_matchId, next) => onToggleSave(match, next)}
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
