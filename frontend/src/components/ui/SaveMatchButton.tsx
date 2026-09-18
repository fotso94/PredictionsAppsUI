import React from 'react'
import clsx from 'clsx'
import { BookmarkIcon } from '@heroicons/react/24/outline'
import { BookmarkIcon as BookmarkSolidIcon } from '@heroicons/react/24/solid'

/**
 * Save / unsave one match.
 *
 * Presentational: it renders the state it is given and reports the state the user asked for. The
 * optimistic update, the rollback and the error all belong to the caller (see
 * `useFavourites().setMatchSaved`, which applies the change immediately and restores the previous
 * state if the write fails). That division matters: a star that stays filled after a failed save
 * is a lie about what the server holds, and only the caller knows whether the write landed.
 *
 * Accessibility notes:
 *  - The state is in the accessible NAME ("Save …" / "Saved …"), not only in `aria-pressed` and not
 *    only in the fill of an icon, so it survives both a screen reader and a monochrome display.
 *  - 44x44 target via `.tap-target`, visible keyboard focus via `.focus-ring`.
 *  - Signed out, it is still a real button: it invites sign-in rather than silently doing nothing.
 *
 * Measured: filled star warning-300 #fcd34d on dark-900 #0f172a 12.38:1 and on dark-800 10.15:1;
 * unfilled secondary-300 #cbd5e1 12.02:1 / 9.85:1. Both far above the 3:1 an icon needs.
 */

export interface SaveMatchButtonProps {
  /** Current state, as the caller believes it to be (optimistic value included). */
  saved: boolean
  /** Called with the state the user is asking for. */
  onToggle: (next: boolean) => void
  /** A write is in flight. The control stays interactive-looking but is disabled to avoid a double send. */
  pending?: boolean
  disabled?: boolean
  /**
   * False renders a sign-in prompt instead of a toggle: saving is per-user and needs an account.
   * `onRequireSignIn` is called instead of `onToggle`.
   */
  signedIn?: boolean
  onRequireSignIn?: () => void
  /**
   * What is being saved, for the accessible name — e.g. "Bayern Munich versus Union Berlin".
   * Without it the name is just "Save match", which is ambiguous in a list of twenty.
   */
  matchLabel?: string
  /** `icon` is the dense list variant; `labelled` shows the word beside it. */
  variant?: 'icon' | 'labelled'
  size?: 'sm' | 'md'
  className?: string
}

const SaveMatchButton: React.FC<SaveMatchButtonProps> = ({
  saved,
  onToggle,
  pending = false,
  disabled = false,
  signedIn = true,
  onRequireSignIn,
  matchLabel,
  variant = 'icon',
  size = 'md',
  className,
}) => {
  const subject = matchLabel ? ` ${matchLabel}` : ' this match'
  const accessibleName = !signedIn
    ? `Sign in to save${subject}`
    : saved
      ? `Saved${subject}. Select to remove it from your saved matches.`
      : `Save${subject} to your saved matches.`

  const handleClick = () => {
    if (!signedIn) {
      onRequireSignIn?.()
      return
    }
    onToggle(!saved)
  }

  const Icon = signedIn && saved ? BookmarkSolidIcon : BookmarkIcon
  const iconSize = size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'

  return (
    <button
      type="button"
      onClick={handleClick}
      // Disabled only while OUR write is in flight, or when the caller says so. A signed-out user
      // gets a working button that explains itself, not a dead one.
      disabled={disabled || pending}
      aria-pressed={signedIn ? saved : undefined}
      aria-label={variant === 'icon' ? accessibleName : undefined}
      title={accessibleName}
      className={clsx(
        'tap-target focus-ring rounded-lg transition-colors',
        variant === 'labelled' && 'gap-1.5 px-3 text-sm font-medium',
        signedIn && saved ? 'text-warning-300' : 'text-secondary-300',
        (disabled || pending) ? 'cursor-not-allowed opacity-60' : 'hover:bg-dark-700 hover:text-white',
        className,
      )}
      data-testid="save-match-button"
      data-saved={signedIn && saved}
      data-pending={pending}
    >
      <Icon className={clsx(iconSize, 'flex-shrink-0')} aria-hidden="true" />
      {/* The icon variant carries its whole meaning in `aria-label` (which would override any
          content here anyway); the labelled variant puts the same words on screen. */}
      {variant === 'labelled' && (
        <span>{!signedIn ? 'Sign in to save' : saved ? 'Saved' : 'Save'}</span>
      )}
    </button>
  )
}

export default SaveMatchButton
