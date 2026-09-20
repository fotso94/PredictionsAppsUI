import React, { useCallback, useId, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { StarIcon } from '@heroicons/react/24/outline'
import { StarIcon as StarSolidIcon } from '@heroicons/react/24/solid'
import useFavourites from '@/hooks/useFavourites'
import { getErrorMessage } from '@/utils/errors'
import type { MessageKey } from '@/i18n'
import { useT } from '@/i18n/react'

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
 *
 * ── EVERY WORD HERE COMES FROM THE CATALOGUE, INCLUDING THE ONES NOBODY SEES ────────────────
 *
 * This control used to hold its English in the JSX — the word on the button, the sentence read
 * out after a write, the accessible name, the toast, and the count against the limit. It is on
 * one competition, on one team and on every row of the follow list, so that was English on three
 * screens at once, two of which had been reported as fully translated. Nothing here is assembled
 * from fragments: each sentence is ONE catalogue entry with holes in it, so a language is free to
 * put the entity's name, the figure or the limit wherever it needs them. See src/i18n/format.ts.
 *
 * THE NOUN IS PART OF THE KEY, NOT PART OF THE SENTENCE. `kind` picks between a `team.` key and a
 * `league.` key for the three messages whose wording depends on which noun they are beside, and
 * the catalogue writes each one out in full. That is what lets French agree — « Suivie » with
 * « une équipe » and « une compétition », and a masculine kind added later would take « Suivi »
 * in a key of its own rather than silently inheriting the wrong ending.
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

/** The keys whose wording depends on which noun the control is beside. */
const BY_KIND: Record<FollowButtonProps['kind'], {
  following: MessageKey
  signInToast: MessageKey
  count: MessageKey
}> = {
  team: {
    following: 'reader.follow.team.following',
    signInToast: 'reader.follow.team.signInToast',
    count: 'reader.follow.team.count',
  },
  league: {
    following: 'reader.follow.league.following',
    signInToast: 'reader.follow.league.signInToast',
    count: 'reader.follow.league.count',
  },
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
  const t = useT()
  const navigate = useNavigate()
  const location = useLocation()
  const messageId = useId()
  const [message, setMessage] = useState<string | null>(null)

  const keys = BY_KIND[kind]
  const following = kind === 'team' ? isTeamFollowed(id) : isLeagueFollowed(id)
  const pending = kind === 'team' ? isTeamPending(id) : isLeaguePending(id)
  // Until a snapshot has really arrived we do not know, and we say so by withholding aria-pressed
  // rather than by defaulting to "not followed".
  const known = signedIn && loaded

  const followedCount = kind === 'team' ? data?.teamIds.length : data?.leagueIds.length
  const limit = kind === 'team' ? data?.limits.teams : data?.limits.leagues

  const handleClick = useCallback(() => {
    if (!signedIn) {
      toast(t(keys.signInToast))
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
        if (result.changed) {
          setMessage(t(next ? 'reader.follow.confirmed' : 'reader.follow.confirmedOff', { name }))
        }
      })
      .catch((err: unknown) => {
        // The server's own refusal, verbatim where it sent one — the follow limit says why, and
        // a paraphrase of it would be less true, not more translated.
        const text = getErrorMessage(err, t(next ? 'reader.follow.failed' : 'reader.follow.failedOff', { name }))
        setMessage(text)
        toast.error(text)
      })
  }, [signedIn, t, keys, navigate, location, following, kind, id, name, setTeamFollowed, setLeagueFollowed])

  const accessibleName = !signedIn
    ? t('reader.follow.namedSignIn', { name })
    : !known
      ? t('reader.follow.namedFollow', { name })
      : following
        ? t('reader.follow.namedFollowing', { name })
        : t('reader.follow.namedFollow', { name })

  const word = !signedIn
    ? t('reader.follow.signIn')
    : known && following
      ? t(keys.following)
      : t('reader.follow.follow')
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
        <p id={messageId} role="status" data-testid="follow-message" className="max-w-xs text-xs text-secondary-300">{message}</p>
      )}

      {signedIn && failed && (
        <p data-testid="follow-state-unknown" className="max-w-xs text-xs text-warning-200">
          {t('reader.follow.unknown', { name })}
        </p>
      )}

      {/*
        THE COUNT AND THE LIMIT, AS ONE SENTENCE WITH TWO HOLES.

        It used to be `<span>{n}</span> of <span>{limit}</span> {noun} followed` — the numerals
        frozen either side of an English "of", which is precisely the assembly src/i18n/format.ts
        exists to stop. `num` is on the paragraph rather than on two spans because
        `font-variant-numeric` only ever reaches digits: the figures are tabular wherever in the
        line the language decides to put them, and there is no substring search to fall silently
        out of step with the sentence.
      */}
      {showCount && known && typeof followedCount === 'number' && typeof limit === 'number' && (
        <p className="num text-xs text-secondary-400" data-testid="follow-count">
          {t(keys.count, { count: followedCount, limit })}
        </p>
      )}
    </div>
  )
}

export default FollowButton
