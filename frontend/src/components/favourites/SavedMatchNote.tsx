import React, { useId, useState } from 'react'
import clsx from 'clsx'
import { LockClosedIcon, PencilSquareIcon } from '@heroicons/react/24/outline'
import type { SavedMatch } from '@/types'
import { NOTE_MAX_LENGTH } from '@/services/favourites.service'
import useFavourites from '@/hooks/useFavourites'
import { getErrorMessage } from '@/utils/errors'

/**
 * The private note on one saved match.
 *
 * This is the beginning of a research journal: somewhere to write down why this fixture was worth
 * keeping and what to look at again later. It is stored on the user's own save row
 * (PUT /api/v1/me/saved-matches/{id}), behind authentication, and it is read back by exactly one
 * endpoint, which only ever answers with the caller's own rows.
 *
 * THE PRIVACY CLAIM IS LOAD-BEARING, SO IT IS MADE IN WORDS, NOT BY A PADLOCK GLYPH.
 * "Private" printed next to a text box is a promise about who can read it. It is kept by the
 * backend — the note lives on `saved_matches`, keyed by user id, and no public, expert or match
 * endpoint serialises it — and this component is only ever mounted on the signed-in owner's own
 * dashboard. If a note ever needs to appear anywhere a second person can reach, the wording here
 * has to change first.
 *
 * A note is a reminder, not a stake. There is no amount, no odds, no return: saving a match records
 * that you want to come back to it, and nothing about it is scored, settled or wagered.
 */

export interface SavedMatchNoteProps {
  entry: SavedMatch
  /** For the accessible name, e.g. "Arsenal versus Chelsea". */
  matchLabel: string
  className?: string
}

const SavedMatchNote: React.FC<SavedMatchNoteProps> = ({ entry, matchLabel, className }) => {
  const { saveMatch } = useFavourites()
  const fieldId = useId()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(entry.note ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const stored = entry.note ?? ''
  const open = () => {
    setDraft(stored)
    setError(null)
    setEditing(true)
  }
  const cancel = () => {
    setDraft(stored)
    setError(null)
    setEditing(false)
  }

  const commit = (value: string) => {
    setSaving(true)
    setError(null)
    // '' clears the note; the service maps it to null, which is what the API takes as "no note".
    void saveMatch(entry.matchId, { note: value })
      .then(() => { setEditing(false) })
      .catch((err: unknown) => {
        // The note the user typed stays in the box: losing it to a failed request would be the
        // second thing to go wrong.
        setError(getErrorMessage(err, 'Your note could not be saved. Nothing was changed.'))
      })
      .finally(() => { setSaving(false) })
  }

  const remaining = NOTE_MAX_LENGTH - draft.length

  if (!editing) {
    return (
      /*
        Stacked, not a row. An earlier version put the whole fixture name inside the button ("Add a
        private note on Bayern Munich versus Union Berlin"); at 390px that one unbreakable control
        pushed the note itself to zero width and gave the dashboard 68px of sideways scroll. The
        fixture name still reaches a screen reader, in the button's own accessible name.
      */
      <div className={clsx('space-y-1', className)} data-testid="saved-match-note">
        <div className="flex items-start gap-2">
          <LockClosedIcon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-secondary-400" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            {stored ? (
              <>
                <p className="whitespace-pre-wrap break-words text-xs text-secondary-200" data-testid="saved-match-note-text">
                  {stored}
                </p>
                <p className="mt-0.5 text-[11px] text-secondary-500">
                  Your private note. Only you can see it.
                </p>
              </>
            ) : (
              <p className="text-[11px] text-secondary-500">
                No note yet. Notes are private to you and are never shown to anyone else.
              </p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={open}
          className="focus-ring rounded px-1.5 py-1 text-xs font-medium text-primary-300 hover:text-primary-200 hover:underline"
          data-testid="saved-match-note-edit"
        >
          <PencilSquareIcon className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />
          {stored ? 'Edit note' : 'Add a private note'}
          <span className="sr-only"> on {matchLabel}</span>
        </button>
      </div>
    )
  }

  return (
    <div className={clsx('space-y-2', className)} data-testid="saved-match-note">
      <label htmlFor={fieldId} className="flex items-center gap-1.5 text-xs font-medium text-secondary-200">
        <LockClosedIcon className="h-3.5 w-3.5 flex-shrink-0 text-secondary-400" aria-hidden="true" />
        Your private note on {matchLabel}
      </label>
      <textarea
        id={fieldId}
        value={draft}
        onChange={event => setDraft(event.target.value.slice(0, NOTE_MAX_LENGTH))}
        maxLength={NOTE_MAX_LENGTH}
        rows={3}
        disabled={saving}
        aria-describedby={`${fieldId}-help`}
        placeholder="What you want to look at again — a team-news question, a market you did not understand, anything worth a second look."
        className="focus-ring w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-white placeholder:text-secondary-500"
        data-testid="saved-match-note-input"
      />
      <p id={`${fieldId}-help`} className="text-[11px] text-secondary-400">
        Private to you. This note is stored on your own saved match and is never shown to other
        users, to experts, or anywhere on the public pages.{' '}
        <span className="num">{remaining}</span> characters left.
      </p>

      {error && <p role="alert" className="text-xs text-danger-300">{error}</p>}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => commit(draft)}
          disabled={saving}
          className="focus-ring rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-primary-500 disabled:cursor-not-allowed disabled:opacity-60"
          data-testid="saved-match-note-save"
        >
          {saving ? 'Saving…' : 'Save note'}
        </button>
        <button
          type="button"
          onClick={cancel}
          disabled={saving}
          className="focus-ring rounded-lg border border-dark-700 px-3 py-1.5 text-xs font-medium text-secondary-200 transition-colors hover:bg-dark-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          Cancel
        </button>
        {stored && (
          <button
            type="button"
            onClick={() => { setDraft(''); commit('') }}
            disabled={saving}
            className="focus-ring rounded-lg px-3 py-1.5 text-xs font-medium text-secondary-300 transition-colors hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
            data-testid="saved-match-note-clear"
          >
            Delete note
          </button>
        )}
      </div>
    </div>
  )
}

export default SavedMatchNote
