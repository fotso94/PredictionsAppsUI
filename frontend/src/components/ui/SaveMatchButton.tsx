import React from 'react'
import clsx from 'clsx'
import { useT } from '@/i18n/react'
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
 *  - A WRITE IN FLIGHT IS `aria-disabled`, NEVER `disabled`. The HTML attribute removes the
 *    element from the focus order, and a browser blurs whatever it disables: pressing Enter on
 *    this control used to hand focus straight back to the document body, so a keyboard or
 *    screen-reader user was dumped at the top of the page for the length of the request and the
 *    `role="status"` announcement arrived with focus nowhere. `aria-disabled` says exactly the
 *    same thing to assistive technology, keeps the control focused and focusable, and the click
 *    handler below is what actually refuses the second press. The `disabled` prop is left as a
 *    real `disabled`, because a caller that asks for one means the control should be out of the
 *    way entirely.
 *  - It stays MOUNTED across the write. Re-keying or conditionally rendering it around the
 *    pending state would throw focus to the body just as surely as disabling it does.
 *
 * Measured: filled star warning-300 #fcd34d on dark-900 #0f172a 12.38:1 and on dark-800 10.15:1;
 * unfilled secondary-300 #cbd5e1 12.02:1 / 9.85:1. Both far above the 3:1 an icon needs.
 */

export interface SaveMatchButtonProps {
  /** Current state, as the caller believes it to be (optimistic value included). */
  saved: boolean
  /** Called with the state the user is asking for. */
  onToggle: (next: boolean) => void
  /**
   * A write is in flight. The control keeps its focus and its place in the focus order, reports
   * itself `aria-disabled`, and refuses a second press until the write has landed.
   */
  pending?: boolean
  /** Out of use entirely, and out of the focus order with it. Not the same thing as `pending`. */
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
  const t = useT()
  /*
   * `subject` used to carry its own leading space so it could be glued onto "Save" / "Saved" —
   * three sentences built by concatenation in English word order. In French the subject lands
   * somewhere else entirely ("Connectez-vous pour enregistrer Arsenal contre Chelsea"), so the
   * whole sentence is one catalogue entry with the subject as a parameter.
   */
  const subject = matchLabel ?? t('save.thisMatch')
  const accessibleName = !signedIn
    ? t('save.signInTo', { subject })
    : saved
      ? t('save.savedRemove', { subject })
      : t('save.addTo', { subject })

  const handleClick = () => {
    // The guard the `disabled` attribute used to provide, without the attribute's side effect on
    // focus. A press while a write is in flight does nothing at all.
    if (pending || disabled) return
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
      // A signed-out user gets a working button that explains itself, not a dead one — and a
      // write in flight is announced without taking the control out from under the keyboard.
      disabled={disabled}
      aria-disabled={pending || undefined}
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
        <span>{t(!signedIn ? 'save.signInShort' : saved ? 'save.saved' : 'save.save')}</span>
      )}
    </button>
  )
}

export default SaveMatchButton
