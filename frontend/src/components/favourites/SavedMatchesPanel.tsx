import React, { useEffect, useMemo, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import EmptyState from '@/components/ui/EmptyState'
import FixtureRow from '@/components/ui/FixtureRow'
import useAuth from '@/hooks/useAuth'
import useFavourites from '@/hooks/useFavourites'
import {
  buildFeed, followedFixturesStore, usePersonalPreferences, FEED_DAYS_AHEAD, FEED_DAYS_BACK,
  type FeedEntry, type FeedGroup, type FeedPhase, type FeedReason,
} from '@/services/favourites.service'
import SavedMatchNote from './SavedMatchNote'
import useMatchSaving from './useMatchSaving'

/**
 * The dashboard feed: one ordered list of what this reader saved and what the teams and
 * competitions they follow are about to play or have just played.
 *
 * WHAT THIS USED TO BE. Two separate directories. Saved matches were split into three fixed
 * buckets here, and following was a list of links somewhere else on the page — so the fixtures
 * that make a follow worth having were never shown at all, and the end of the journey a reader
 * actually takes (find a match, save it, come back after it is played, see the result) took a
 * scroll past everything still to come. The feed merges both into one list and puts the answer
 * near the top.
 *
 * THE ORDER IS ARGUED IN ONE PLACE, NOT TWO. `buildFeed` in services/favourites.service.ts owns
 * it — in play, then results, then what is coming up — and the reasoning lives in its doc comment
 * so the rule and its justification cannot drift apart. This component renders what it is handed.
 *
 * WHY EACH ROW SAYS WHY IT IS THERE. A feed that mixes three sources without labelling them is a
 * list nobody can predict: a reader seeing a fixture they never saved needs to know it is here
 * because they follow one of the clubs, and that unfollowing removes it. The reasons are words on
 * the row, not a colour or an icon.
 *
 * EMPTY IS NOT THE SAME AS UNKNOWN, AND NEITHER IS "NOT IN THE WINDOW". Three different states
 * reach this component and each gets its own sentence: the load failed (we do not know), there is
 * nothing saved or followed (there is genuinely nothing), and there are follows but nothing stored
 * for them inside the feed's window (there is something — just not in the next few days).
 *
 * NOTHING HERE IS A RECORD OF HOW THE READER DID. A finished fixture shows the final score and
 * what each source published beforehand. Saving a match is a bookmark, not a bet: no stake, no
 * odds, and this panel marks nothing right or wrong. Model forecasts ARE scored on this
 * installation, and how they have done is published on the home page with the sample behind every
 * figure — but a saved match is not a prediction the reader made, so no such figure belongs here.
 */

export interface SavedMatchesPanelProps {
  className?: string
}

/*
 * `unresolved` holds a fixture whose result passed its deadline and never arrived. Its row still
 * carries a status of LIVE or SCHEDULED, because that is the last thing a provider said about it,
 * and under "In play now" this page would assert in a heading a match that finished hours ago.
 * The heading says what is actually true of every fixture under it: a result was expected and is
 * not here. Each row then says which of the two states it is in and how late it is.
 */
const GROUP_TITLE: Record<FeedPhase, string> = {
  live: 'In play now',
  unresolved: 'Awaiting a result',
  result: 'Results',
  upcoming: 'Coming up',
}

/** The short word used in the summary line at the top, where space is tight. */
const GROUP_SUMMARY: Record<FeedPhase, (count: number) => string> = {
  live: count => `${count} in play`,
  unresolved: count => `${count} awaiting a result`,
  result: count => (count === 1 ? '1 result' : `${count} results`),
  upcoming: count => `${count} coming up`,
}

const groupAnchor = (phase: FeedPhase) => `feed-${phase}`

/**
 * Why this fixture is in the feed, in words.
 *
 * At most three are shown: a fixture can be saved AND reached through both clubs and its
 * competition, and five pills on a phone row is noise. The rest are counted rather than dropped
 * silently, because "+2" is a fact and a truncated list is not.
 */
const FeedReasons: React.FC<{ reasons: FeedReason[] }> = ({ reasons }) => {
  const ordered = [...reasons].sort((a, b) => (a.kind === 'saved' ? -1 : b.kind === 'saved' ? 1 : 0))
  const shown = ordered.slice(0, 3)
  const extra = ordered.length - shown.length

  return (
    <ul className="flex flex-wrap items-center gap-1" data-testid="feed-reasons">
      <li className="sr-only">In your feed because:</li>
      {shown.map(reason => (
        <li
          key={`${reason.kind}:${reason.id}`}
          className={clsx(
            'rounded-full px-2 py-0.5 text-[11px] font-medium',
            reason.kind === 'saved'
              ? 'bg-primary-900 text-primary-200'
              : 'border border-dark-700 text-secondary-300',
          )}
          data-reason={reason.kind}
        >
          {reason.label}
        </li>
      ))}
      {extra > 0 && (
        <li className="num text-[11px] text-secondary-400">
          and <span className="num">{extra}</span> more you follow
        </li>
      )}
    </ul>
  )
}

/**
 * THE SCORE-ONLY PATH, AT THE ONE PLACE IT CAN BE HONEST.
 *
 * With forecasts switched off, the row's expandable detail is not rendered at all — `expandable`
 * is the prop `FixtureRow` already offers for exactly that, and it keeps the brief, the per-source
 * probabilities and the other-markets list out of the DOM entirely.
 *
 * The compact per-source markers on the row itself have no such prop, so they are hidden with a
 * rule scoped to this wrapper. Hidden, NOT replaced: rendering `FixtureRow` with the forecast
 * fields stripped off the match would make its markers say the source published nothing, which is
 * a claim about the data and would be false. A reader who turned forecasts off asked not to see
 * them, not to be told they do not exist. Widening `FixtureRowProps` with a `showPreview` prop is
 * the clean fix and belongs to that file's owner; the note is in the package report.
 */
const HIDE_FORECAST_PREVIEW = '[&_[data-testid=fixture-row-preview]]:hidden'

const FeedRow: React.FC<{ entry: FeedEntry; showForecasts: boolean }> = ({ entry, showForecasts }) => {
  const { isSaved, isPending, toggleSave, signedIn, requireSignIn } = useMatchSaving()
  const label = `${entry.match.homeTeam.name} versus ${entry.match.awayTeam.name}`

  return (
    <li
      className={clsx(
        'rounded-lg border border-dark-800 bg-dark-900/40',
        !showForecasts && HIDE_FORECAST_PREVIEW,
      )}
      // `saved-match` is the anchor the live save journey asserts on, and it marks exactly one
      // thing: a row the reader saved themselves. A fixture that is only here because of a follow
      // must not carry it, or "the match I saved is on my dashboard once" stops being provable.
      data-testid={entry.saved ? 'saved-match' : 'feed-match'}
      data-feed-phase={entry.phase}
      data-match-id={entry.matchId}
    >
      <FixtureRow
        match={entry.match}
        saved={isSaved(entry.matchId)}
        savePending={isPending(entry.matchId)}
        onToggleSave={(matchId, next) => toggleSave(matchId, next, entry.match)}
        signedIn={signedIn}
        onRequireSignIn={() => requireSignIn({ matchId: entry.matchId, label })}
        expandable={showForecasts}
      />
      {/* A row that is only here because of a follow carries one short line; a saved row carries
          its note as well, so it gets the taller treatment and the other does not. */}
      <div className={clsx('space-y-2 border-t border-dark-800 px-3', entry.saved ? 'py-2' : 'py-1.5')}>
        <FeedReasons reasons={entry.reasons} />
        {/* The private note belongs to the save row, so only a saved fixture has one to show. */}
        {entry.saved && <SavedMatchNote entry={entry.saved} matchLabel={label} />}
      </div>
    </li>
  )
}

const FeedSection: React.FC<{
  group: FeedGroup
  showForecasts: boolean
  showPrompts: boolean
  liveUpdates: boolean
}> = ({ group, showForecasts, showPrompts, liveUpdates }) => (
  <section aria-labelledby={groupAnchor(group.phase)} data-testid={`feed-group-${group.phase}`}>
    <h3
      id={groupAnchor(group.phase)}
      className="mb-2 flex items-baseline gap-2 scroll-mt-4 text-sm font-semibold text-white"
      tabIndex={-1}
    >
      {GROUP_TITLE[group.phase]}
      <span className="num text-xs font-normal text-secondary-400">{group.total}</span>
    </h3>
    {group.phase === 'result' && (
      // Said once, where a reader might otherwise expect a verdict beside the score. With
      // forecasts off the first half of that sentence would describe something not on the page,
      // so the claim shrinks to what is actually shown rather than staying and going stale.
      <p className="mb-2 text-xs text-secondary-400">
        {showForecasts
          ? 'Final scores, with what each source published before kick-off. Whether a forecast was '
            + 'right is settled separately and reported on the home page with its sample size; '
            + 'nothing on this page is marked right or wrong, and a saved match is not a '
            + 'prediction you made.'
          : 'Final scores. Nothing on this page is marked right or wrong, and a saved match is not '
            + 'a prediction you made.'}
      </p>
    )}
    {group.phase === 'live' && !liveUpdates && (
      /*
       * "Never present cached data as live." With automatic updates off, these scores are
       * whatever arrived when the page loaded, and a row headed "In play now" beside a minute and
       * a scoreline is otherwise read as current. The reader switched this off; they are not
       * nagged to switch it back, only told what they are looking at.
       */
      <p className="mb-2 text-xs text-warning-200" data-testid="feed-live-not-updating">
        These scores are as they were when this page loaded. Automatic updates are off, so nothing
        here is refreshing; reload the page to read them again.
      </p>
    )}
    <ul className="space-y-2">
      {group.entries.map(entry => (
        <FeedRow key={entry.matchId} entry={entry} showForecasts={showForecasts} />
      ))}
    </ul>
    {group.hidden > 0 && (
      // The count is a fact about this list being short, so it stays whatever the reader has
      // switched off. Only the invitation to go somewhere else is a prompt, and only it goes.
      <p className="mt-2 text-xs text-secondary-400" data-testid={`feed-hidden-${group.phase}`}>
        <span className="num">{group.hidden}</span> more from the teams and competitions you follow
        are not listed here.{' '}
        {showPrompts && (
          <Link to="/matches" className="focus-ring rounded text-primary-300 underline-offset-2 hover:underline">
            Browse all matches
          </Link>
        )}
      </p>
    )}
  </section>
)

const SavedMatchesPanel: React.FC<SavedMatchesPanelProps> = ({ className }) => {
  const { data, loading, failed, error, reload } = useFavourites()
  const { user } = useAuth()
  const prefs = usePersonalPreferences(user?.id ?? null)
  const showForecasts = prefs.isOn('forecasts')
  const showPrompts = prefs.isOn('prompts')
  const liveUpdates = prefs.isOn('liveUpdates')
  const followed = useSyncExternalStore(
    followedFixturesStore.subscribe,
    followedFixturesStore.getState,
    followedFixturesStore.getState,
  )

  // The follows have to be known before their fixtures can be read, so this waits for the
  // favourites snapshot rather than racing it. `ensureLoaded` is a no-op once the feed matches the
  // follows it was built from, which is what makes it safe to call on every render.
  useEffect(() => {
    if (data) followedFixturesStore.ensureLoaded()
  }, [data])

  const groups = useMemo(() => buildFeed(data, followed.fixtures), [data, followed.fixtures])

  if (loading) {
    return (
      <div className={className} data-testid="feed-loading">
        <p className="py-6 text-center text-sm text-secondary-400" role="status">
          Loading your feed…
        </p>
      </div>
    )
  }

  if (failed) {
    return (
      <div className={className}>
        <EmptyState
          tone="failed"
          title="Your feed could not be loaded."
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

  const followsAnything = (data?.teamIds.length ?? 0) > 0 || (data?.leagueIds.length ?? 0) > 0
  /**
   * Two different counts, and they can disagree. `counts.total` is what the server holds; the
   * lists are what it could serialise, and a save whose fixture row is gone appears in the first
   * and not the second. Conflating them is how a panel ends up telling a reader they saved
   * nothing while the server still holds their saves.
   */
  const savedHeld = data?.savedMatches.counts.total ?? 0
  const shown = groups.reduce((sum, group) => sum + group.entries.length, 0)

  if (savedHeld === 0 && !followsAnything) {
    return (
      <div className={className}>
        <EmptyState
          tone="empty"
          title="Nothing in your feed yet."
          description={
            <>
              Save a match and it appears here — with a private note if you want one — and again
              with its result once it has been played. Follow a team or a competition and their
              fixtures appear here too.
            </>
          }
          /* The description above already says what saving and following do, so the reader is
             not left without an answer; these two are invitations to go elsewhere, which is the
             thing the prompts switch turns off. */
          action={showPrompts ? (
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
          ) : undefined}
          data-testid="saved-matches-empty"
        />
      </div>
    )
  }

  /**
   * THE FOLLOW FAN-OUT IS A SECOND LOAD, WITH ITS OWN OUTCOME.
   *
   * `loading`/`failed` above are the favourites snapshot's; the fixtures behind the follows are a
   * separate request per follow that finishes later and can fail on its own. Until that load has
   * an outcome there is nothing true to say about what the follows hold — and when every one of
   * those reads has FAILED, what we know is that we do not know.
   *
   * Both were being answered with "nothing you follow has a fixture stored in it": a positive
   * claim about the data, made before the read that would establish it had returned, and made
   * again when the read had come back 500. That is rule 1 of services/favourites.service.ts — a
   * failure is never an empty result — broken in the one panel built on top of it.
   */
  const feedPending = followsAnything && (followed.status === 'idle' || followed.status === 'loading')
  const feedFailed = followsAnything && followed.status === 'error'

  if (shown === 0 && feedPending) {
    return (
      <div className={className} data-testid="feed-loading">
        <p className="py-6 text-center text-sm text-secondary-400" role="status">
          Loading your feed…
        </p>
      </div>
    )
  }

  if (shown === 0 && feedFailed) {
    return (
      <div className={className}>
        <EmptyState
          tone="failed"
          title="Your feed could not be loaded."
          // The store's own sentence, which names what failed: the fixtures behind the follows,
          // not the follows themselves — those loaded, and the panel below still lists them.
          description={followed.error ?? 'The fixtures behind the teams and competitions you follow could not be read, so we cannot say what they have coming up.'}
          action={
            <button
              type="button"
              onClick={() => { void followedFixturesStore.load() }}
              className="focus-ring rounded-lg border border-dark-700 px-3 py-1.5 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white"
            >
              Try again
            </button>
          }
          data-testid="feed-failed"
        />
      </div>
    )
  }

  /**
   * The follows whose own request failed, named.
   *
   * PARTLY UNREADABLE IS A THIRD STATE, and it used to fall through to the empty one. `feedFailed`
   * above is EVERY follow having failed; a feed where one of two teams came back 500 stays
   * 'ready', and with nothing else to show it reached the sentence below — "nothing you follow has
   * a fixture stored in it" — which is a claim about a follow whose fixtures nobody had managed to
   * read. The claim is now limited to the follows that actually answered.
   */
  const unreadable = followed.unreadable
  const unreadableNames = unreadable.map(follow => follow.label).join(', ')

  if (shown === 0) {
    return (
      <div className={className}>
        <EmptyState
          tone={unreadable.length > 0 ? 'failed' : 'empty'}
          // Not "you follow nothing" and not "there are no matches": what is true is that nothing
          // we hold for these follows falls inside the days this feed covers. Reached only once
          // the fan-out has genuinely come back — see feedPending/feedFailed above.
          title={unreadable.length > 0
            ? 'Nothing stored for the follows we could read.'
            : 'Nothing stored for your follows in the next few days.'}
          description={
            <>
              This feed covers the next <span className="num">{FEED_DAYS_AHEAD}</span> days and the
              last <span className="num">{FEED_DAYS_BACK}</span>, and{' '}
              {unreadable.length > 0
                ? <>nothing we could read for your follows has a fixture stored in it. Fixtures
                  for {unreadableNames} could not be loaded, so nothing is claimed about{' '}
                  {unreadable.length === 1 ? 'it' : 'them'} either way.</>
                : <>nothing you follow has a fixture stored in it.</>}
              {savedHeld > 0 && (
                <>
                  {' '}You have <span className="num">{savedHeld}</span> saved{' '}
                  {savedHeld === 1 ? 'match' : 'matches'}, but we no longer hold the fixture behind{' '}
                  {savedHeld === 1 ? 'it' : 'them'}, so there is nothing to show.
                </>
              )}
            </>
          }
          action={unreadable.length > 0 ? (
            /*
             * The same control as the two below and beside it — the short-feed Retry and the one
             * on each unreadable follow's own row — and it now answers the way they do. Going
             * grey is not an answer: a disabled button is what a page looks like when it has
             * decided not to let you press something, not when it is working, so a reader who
             * pressed this was left with the very doubt Retry exists to settle.
             */
            <button
              type="button"
              onClick={() => { void followedFixturesStore.load() }}
              disabled={followed.refreshing}
              className="focus-ring rounded-lg border border-dark-700 px-3 py-1.5 text-sm font-medium text-secondary-100 transition-colors hover:bg-dark-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
              data-testid="feed-partly-unreadable-retry"
            >
              {followed.refreshing ? 'Trying again…' : 'Try again'}
            </button>
          ) : (showPrompts ? (
            <Link
              to="/matches"
              className="focus-ring rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-500"
            >
              Browse all matches
            </Link>
          ) : undefined)}
          data-testid={unreadable.length > 0 ? 'feed-partly-unreadable' : 'feed-window-empty'}
        />
      </div>
    )
  }

  const populated = groups.filter(group => group.entries.length > 0)

  return (
    <div className={clsx('space-y-6', className)} data-testid="saved-matches">
      {/*
        THE SCORE-ONLY STATE, STATED AND NOT SOLD.

        Without this, a reader who turned forecasts off a week ago and came back to a feed with no
        probabilities on it has no way to tell a preference from a data outage — and this build
        genuinely has outages worth distinguishing from it. One sentence of fact, no control, no
        invitation to change it back. The switch is on this same page, under the follow list,
        where they set it.
      */}
      {!showForecasts && (
        <p className="text-xs text-secondary-400" data-testid="feed-scores-only">
          Scores only. Forecasts and tips are switched off for your pages
          {prefs.paused ? ', along with everything else optional' : ''}.
        </p>
      )}
      {/*
        The short way to the thing the reader came back for. A result is usually the answer to a
        question they asked days ago by saving the match, and without this it sits below however
        many fixtures happen to be in play — so the counts are also the jump links.
      */}
      <nav aria-label="Jump to a part of your feed" data-testid="feed-summary">
        <ul className="flex flex-wrap items-center gap-2 text-xs">
          {/* Named in the page, not only in the aria-label: a row of words that turn out to be
              controls only when the pointer touches them is not discoverable on a phone. */}
          <li className="text-secondary-400">Jump to</li>
          {populated.map(group => (
            <li key={group.phase}>
              <a
                href={`#${groupAnchor(group.phase)}`}
                className="focus-ring inline-block rounded-full border border-dark-600 px-2.5 py-1 font-medium text-secondary-100 underline underline-offset-2 transition-colors hover:border-primary-500 hover:bg-dark-800 hover:text-white"
                data-testid={`feed-jump-${group.phase}`}
              >
                {GROUP_SUMMARY[group.phase](group.total)}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {unreadable.length > 0 && (
        /*
         * A short feed and an incomplete one look identical, so the difference is stated — and
         * now the follows themselves are named, because the store carries them rather than a
         * count. Which follow is missing is the fact a reader can act on; "some of them" is not.
         */
        <p className="text-xs text-warning-200" role="status" data-testid="feed-incomplete">
          Fixtures for {unreadableNames} could not be loaded, so this list is short by whatever
          they hold.{' '}
          <button
            type="button"
            onClick={() => { void followedFixturesStore.load() }}
            disabled={followed.refreshing}
            className="focus-ring rounded font-medium text-primary-300 underline underline-offset-2 transition-colors hover:text-primary-200 disabled:cursor-not-allowed disabled:opacity-60"
            data-testid="feed-incomplete-retry"
          >
            {followed.refreshing ? 'Trying again…' : 'Try again'}
          </button>
        </p>
      )}

      {populated.map(group => (
        <FeedSection
          key={group.phase}
          group={group}
          showForecasts={showForecasts}
          showPrompts={showPrompts}
          liveUpdates={liveUpdates}
        />
      ))}
    </div>
  )
}

export default SavedMatchesPanel
