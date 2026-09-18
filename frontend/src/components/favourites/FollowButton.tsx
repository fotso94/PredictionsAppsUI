import React, { useCallback, useId, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { StarIcon } from '@heroicons/react/24/outline'
import { StarIcon as StarSolidIcon } from '@heroicons/react/24/solid'
import useFavourites from '@/hooks/useFavourites'
import { getErrorMessage } from '@/utils/errors'

/**
 * Follow / unfollow one team or one competition.
 *
 * Wired straight to the shared favourites store, so this control, the star on a fixture row and
 * the personal dashboard read the same state and cannot disagree.
 *
 * FOUR STATES, AND NONE OF THEM PRETENDS TO BE ANOTHER
 *  - signed out: a real button that invites sign-in. It does not stash a follow in the browser to
 *    be "synced later" — there is nowhere to put it, and a follow that quietly disappears on the
 *    next visit is worse than one that was never offered.
 *  - loading: disabled, and the word is "Follow" with no `aria-pressed`, because we do not yet
 *    know. A control that claims "Follow" while the answer is still in flight is a guess.
 *  - known: `aria-pressed` carries the real state; the word changes with it, so the fill of a star
 *    is never the only cue.
 *  - the load failed: the control still works (following is a write, and the write is what the
 *    reader asked for), but the page is told so it can say "we could not check what you follow"
 *    instead of letting an empty star assert "you do not follow this".
 *
 * A refusal — the follow limit, most often — comes back from the server with its own sentence and
 * is shown verbatim. The store has already put the state back to what it was, so the star returns
 * to where it started rather than showing a follow that does not exist.
 */

export interface FollowButtonProps {
  kind: 'team' | 'league'
  /** The INTERNAL id the API stores (a UUID). A competition key works for the write but would not
   *  match the ids the snapshot reports back, so the control would not know its own state. */
  id: string
  /** For the accessible name: "Follow Arsenal", not "Follow". */
  name: string
  /** `labelled` shows the word; `icon` is the dense variant for a grid or a list row. */
  variant?: 'labelled' | 'icon'
  size?: 'sm' | 'md'
  /** Show the follow count against the limit under the button (e.g. "3 of 10 teams followed"). */
  showCount?: boolean
  className?: string
}

const FollowButton: React.FC<FollowButtonProps> = ({
  kind,
  id,
  name,
  variant = 'labelled',
  size = 'md',
  showCount = false,
  className,
}) => {
  const {
    signedIn, loaded, failed, data,
    isTeamFollowed, isLeagueFollowed, isTeamPending, isLeaguePending,
    setTeamFollowed, setLeagueFollowed,
  } = useFavourites()
  const navigate = useNavigate()
  const location = useLocation()
  const messageId = useId()
  const [message, setMessage] = useState<string | null>(null)

  const noun = kind === 'team' ? 'team' : 'competition'
  const following = kind === 'team' ? isTeamFollowed(id) : isLeagueFollowed(id)
  const pending = kind === 'team' ? isTeamPending(id) : isLeaguePending(id)
  // Until a snapshot has really arrived we do not know, and we say so by withholding aria-pressed
  // rather than by defaulting to "not followed".
  const known = signedIn && loaded

  const followedCount = kind === 'team' ? data?.teamIds.length : data?.leagueIds.length
  const limit = kind === 'team' ? data?.limits.teams : data?.limits.leagues

  const handleClick = useCallback(() => {
    if (!signedIn) {
      toast(`Sign in to follow ${noun === 'team' ? 'teams' : 'competitions'}.`)
      navigate('/login', { state: { from: location } })
      return
    }
    const next = !following
    setMessage(null)
    const write = kind === 'team' ? setTeamFollowed(id, next) : setLeagueFollowed(id, next)
    void write
      .then(result => {
        // `changed: false` means the server was already in the state asked for — not a failure,
        // and not worth a message.
        if (result.changed) setMessage(next ? `Following ${name}.` : `No longer following ${name}.`)
      })
      .catch((err: unknown) => {
        const text = getErrorMessage(err, next
          ? `${name} could not be followed. Nothing was changed.`
          : `${name} could not be unfollowed. Nothing was changed.`)
        setMessage(text)
        toast.error(text)
      })
  }, [signedIn, noun, navigate, location, following, kind, id, name, setTeamFollowed, setLeagueFollowed])

  const accessibleName = !signedIn
    ? `Sign in to follow ${name}`
    : !known
      ? `Follow ${name}`
      : following
        ? `Following ${name}. Select to stop following.`
        : `Follow ${name}`

  const word = !signedIn ? 'Sign in to follow' : known && following ? 'Following' : 'Follow'
  const Icon = known && following ? StarSolidIcon : StarIcon
  const iconSize = size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'

  return (
    <div className={clsx('inline-flex flex-col items-start gap-1', className)}>
      <button
        type="button"
        onClick={handleClick}
        disabled={pending}
        aria-pressed={known ? following : undefined}
        aria-label={variant === 'icon' ? accessibleName : undefined}
        aria-describedby={message ? messageId : undefined}
        title={accessibleName}
        className={clsx(
          'tap-target focus-ring rounded-lg transition-colors',
          variant === 'labelled' && 'gap-1.5 px-3 text-sm font-medium',
          known && following ? 'text-warning-300' : 'text-secondary-300',
          pending ? 'cursor-not-allowed opacity-60' : 'hover:bg-dark-700 hover:text-white',
        )}
        data-testid="follow-button"
        data-kind={kind}
        data-entity-id={id}
        data-following={known ? following : undefined}
        data-pending={pending}
      >
        <Icon className={clsx(iconSize, 'flex-shrink-0')} aria-hidden="true" />
        {variant === 'labelled' && <span>{word}</span>}
      </button>

      {/* The outcome of the last write, announced once. Never a toast alone: a toast can be gone
          before a screen reader or a distracted reader reaches it. */}
      {message && (
        <p id={messageId} role="status" className="max-w-xs text-xs text-secondary-300">{message}</p>
      )}

      {signedIn && failed && (
        <p className="max-w-xs text-xs text-warning-200">
          We could not load what you follow, so this button cannot show whether {name} is already on
          your list.
        </p>
      )}

      {showCount && known && typeof followedCount === 'number' && typeof limit === 'number' && (
        <p className="text-xs text-secondary-400">
          <span className="num">{followedCount}</span> of <span className="num">{limit}</span>{' '}
          {kind === 'team' ? 'teams' : 'competitions'} followed
        </p>
      )}
    </div>
  )
}

export default FollowButton
