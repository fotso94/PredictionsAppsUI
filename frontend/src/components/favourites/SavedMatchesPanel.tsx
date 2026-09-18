import React from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import type { SavedMatch } from '@/types'
import EmptyState from '@/components/ui/EmptyState'
import FixtureRow from '@/components/ui/FixtureRow'
import useFavourites from '@/hooks/useFavourites'
import SavedMatchNote from './SavedMatchNote'
import useMatchSaving from './useMatchSaving'

/**
 * The saved matches on the personal dashboard, split into live, upcoming and finished.
 *
 * The split is the API's own (GET /api/v1/me/favourites), not one worked out here: `live` is in
 * play now, `finished` has been played, and `upcoming` is everything else — so a postponed or
 * cancelled fixture stays in `upcoming` carrying its real status instead of being reported as
 * finished.
 *
 * EMPTY IS NOT THE SAME AS UNKNOWN. When the load failed, `failed` is true and the buckets are
 * whatever we last held (usually nothing). Rendering that as "you have saved no matches" would be
 * a statement about this user made out of a network error, so the failure gets its own state with
 * the server's own wording and a retry.
 *
 * NOTHING HERE IS SCORED. A finished saved match shows the final score and what each source had
 * published beforehand. It does not say whether that was right: no settlement runs in this build,
 * so there is no accuracy, hit rate, return or streak to show, and a badge implying one would be
 * invented. Saving a match is not a bet; there is no stake anywhere on this page.
 */

export interface SavedMatchesPanelProps {
  className?: string
}

const BUCKET_TITLE = {
  live: 'In play now',
  upcoming: 'Coming up',
  finished: 'Played',
} as const

type BucketKey = keyof typeof BUCKET_TITLE

const SavedRow: React.FC<{ entry: SavedMatch }> = ({ entry }) => {
  const { isSaved, isPending, toggleSave, signedIn, requireSignIn } = useMatchSaving()
  const label = `${entry.match.homeTeam.name} versus ${entry.match.awayTeam.name}`

  return (
    <li className="rounded-lg border border-dark-800 bg-dark-900/40" data-testid="saved-match">
      <FixtureRow
        match={entry.match}
        saved={isSaved(entry.matchId)}
        savePending={isPending(entry.matchId)}
        onToggleSave={(matchId, next) => toggleSave(matchId, next, entry.match)}
        signedIn={signedIn}
        onRequireSignIn={requireSignIn}
      />
      <div className="border-t border-dark-800 px-3 py-2">
        <SavedMatchNote entry={entry} matchLabel={label} />
      </div>
    </li>
  )
}

const SavedMatchesPanel: React.FC<SavedMatchesPanelProps> = ({ className }) => {
  const { savedMatches, loading, failed, error, reload } = useFavourites()

  const buckets: Array<[BucketKey, SavedMatch[]]> = [
    ['live', savedMatches.live],
    ['upcoming', savedMatches.upcoming],
    ['finished', savedMatches.finished],
  ]
  const total = buckets.reduce((sum, [, entries]) => sum + entries.length, 0)

  if (loading) {
    return (
      <div className={className} data-testid="saved-matches-loading">
        <p className="py-6 text-center text-sm text-secondary-400" role="status">
          Loading your saved matches…
        </p>
      </div>
    )
  }

  if (failed) {
    return (
      <div className={className}>
        <EmptyState
          tone="failed"
          title="Your saved matches could not be loaded."
          // The server's own sentence where it gave one; never a reason invented here.
          description={error ?? 'The request did not complete, so we cannot say what you have saved.'}
          action={
            <button
              type="button"
              onClick={() => { void reload().catch(() => undefined) }}
              className="focus-ring rounded-lg border border-dark-700 px-3 py-1.5 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
            >
              Try again
            </button>
          }
          data-testid="saved-matches-failed"
        />
      </div>
    )
  }

  if (total === 0) {
    return (
      <div className={className}>
        <EmptyState
          tone="empty"
          title="You have not saved any matches yet."
          description={
            <>
              Save a match from any fixture list and it appears here, with a private note if you want
              one. Follow a team to see their fixtures here as they are scheduled.
            </>
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Link
                to="/predictions/today"
                className="focus-ring rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-500"
              >
                Browse today&rsquo;s matches
              </Link>
              <Link
                to="/leagues"
                className="focus-ring rounded-lg border border-dark-700 px-3 py-2 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
              >
                Find a team to follow
              </Link>
            </div>
          }
          data-testid="saved-matches-empty"
        />
      </div>
    )
  }

  return (
    <div className={clsx('space-y-6', className)} data-testid="saved-matches">
      {buckets.map(([key, entries]) => (
        entries.length === 0 ? null : (
          <section key={key} aria-labelledby={`saved-${key}`} data-testid={`saved-bucket-${key}`}>
            <h3 id={`saved-${key}`} className="mb-2 flex items-baseline gap-2 text-sm font-semibold text-white">
              {BUCKET_TITLE[key]}
              <span className="num text-xs font-normal text-secondary-400">{entries.length}</span>
            </h3>
            {key === 'finished' && (
              // Said once, where a reader might otherwise expect a verdict beside the score.
              <p className="mb-2 text-xs text-secondary-400">
                Final scores, with what each source published before kick-off. Nothing on this site
                has been scored against a result yet, so no outcome here is marked right or wrong.
              </p>
            )}
            <ul className="space-y-2">
              {entries.map(entry => <SavedRow key={entry.matchId} entry={entry} />)}
            </ul>
          </section>
        )
      ))}
    </div>
  )
}

export default SavedMatchesPanel
