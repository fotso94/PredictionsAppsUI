import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ComposerDraft, draftKickedOff } from '@/components/expert/draft'
import { relativeTime } from '@/components/ui/freshness'
import { useT } from '@/i18n/react'
import Emphasised from '@/i18n/Emphasised'

/**
 * The expert's unpublished drafts, one row per fixture, each with Continue and Discard.
 *
 * Used by the dashboard (the newest three) and by the composer's fixture picker (all of them), so
 * the two can never disagree about what a draft says or how it is thrown away.
 *
 * DISCARD ALWAYS ASKS. The first press only opens an inline confirmation that names the fixture
 * and says it cannot be undone; nothing is removed until "Discard draft" is pressed. Focus moves
 * to "Keep it", the choice that loses nothing, and comes back to Discard if the expert keeps it.
 * A confirmed discard removes the row that holds focus, so the PARENT moves focus to its
 * "Draft discarded." line (the dashboard and the composer's picker both do).
 *
 * NO `truncate` ON THE SUMMARY LINE: see the comment on it below. e2e/mocked/reader-localisation
 * .spec.ts measures `draft-saved-ago` against `draft-summary`, and that against its own box.
 *
 * The duration comes from `relativeTime`, which lets the catalogue put the frame where the
 * language wants it: "3 minutes ago", « il y a 3 minutes ».
 */
export interface DraftListProps {
  drafts: ComposerDraft[]
  /** The composer's picker continues in place; the dashboard links to it. Exactly one is given. */
  onContinue?: (draft: ComposerDraft) => void
  continueHref?: (draft: ComposerDraft) => string
  /** Called only after the expert confirmed. */
  onDiscard: (draft: ComposerDraft) => void
  className?: string
}

const DraftRow: React.FC<{
  draft: ComposerDraft
  onContinue?: (draft: ComposerDraft) => void
  continueHref?: (draft: ComposerDraft) => string
  onDiscard: (draft: ComposerDraft) => void
}> = ({ draft, onContinue, continueHref, onDiscard }) => {
  const t = useT()
  const [confirming, setConfirming] = useState(false)
  const keepRef = useRef<HTMLButtonElement>(null)
  const discardRef = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)

  useEffect(() => {
    if (confirming) keepRef.current?.focus()
    else if (returnFocus.current) {
      returnFocus.current = false
      discardRef.current?.focus()
    }
  }, [confirming])

  const fixture = draft.fixture && draft.fixture.homeTeam
    ? t('expert.fixtureShort', { home: draft.fixture.homeTeam, away: draft.fixture.awayTeam })
    : ''
  const ago = relativeTime(draft.savedAt)
  const sentence = fixture
    ? t('expert.draft.discardConfirm', { fixture })
    : t('expert.draft.discardConfirmNoFixture')

  return (
    <li className="border-t border-dark-800 py-3 first:border-t-0 first:pt-0 last:pb-0" data-testid="draft-row">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/*
            NO `truncate` HERE, AND THAT IS LOAD-BEARING RATHER THAN A TIDY-UP.

            `truncate` is `white-space: nowrap` with `overflow: hidden`, and on this line
            it loses words outright: at 360px in French the saved-ago run ends 106px past
            the paragraph it lives in, and because the clipping is on this paragraph and
            not on the page, the DOCUMENT does not scroll sideways to show it or any test
            that measures the document. « il y a 7 minutes » is half as long again as
            "7 minutes ago", and that is the normal case, not a pathological one: French
            runs reliably longer than English, so a single-line box measured in English
            is a box that loses a French sentence.

            The answer is to let the line wrap. Nothing here needs to be one line: it is a
            card, not a table row, and a fixture name over two lines costs a few pixels of
            height where a clipped line costs the reader the information. `break-words`
            covers the one case wrapping cannot — a single token longer than the card.

            Shortening the French to fit is the other way to make the measurement pass,
            and it is the wrong one: it makes the language that needs
            the room the one that has to give it up, and the next longer string — a
            two-hour-old draft, a longer team name — breaks it again.
          */}
          <p className="break-words text-sm text-secondary-200" data-testid="draft-summary">
            {fixture || t('expert.draft.noFixture')}
            {ago && (
              <span className="text-secondary-400" data-testid="draft-saved-ago">
                {' · '}{t('expert.draft.savedAgo', { ago })}
              </span>
            )}
          </p>
          {draftKickedOff(draft) && (
            <p className="mt-1 text-xs text-warning-200" data-testid="draft-kicked-off">{t('expert.draft.kickedOff')}</p>
          )}
        </div>
        {!confirming && (
          <div className="flex flex-shrink-0 flex-wrap gap-2">
            {continueHref ? (
              <Link to={continueHref(draft)} className="btn btn-sm btn-primary">{t('expert.draft.continue')}</Link>
            ) : (
              <button type="button" onClick={() => onContinue?.(draft)} className="btn btn-sm btn-primary">
                {t('expert.draft.continue')}
              </button>
            )}
            <button ref={discardRef} type="button" onClick={() => setConfirming(true)} className="btn btn-sm btn-ghost">
              {t('expert.draft.discard')}
            </button>
          </div>
        )}
      </div>
      {confirming && (
        <div className="mt-2 rounded-lg border border-danger-700 bg-danger-900/30 p-3" role="group" aria-label={sentence}>
          <p className="text-sm text-white">
            <Emphasised sentence={sentence} value={fixture} className="font-semibold" />
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" onClick={() => onDiscard(draft)} className="btn btn-sm btn-danger">
              {t('expert.draft.confirmDiscard')}
            </button>
            <button
              ref={keepRef}
              type="button"
              onClick={() => { returnFocus.current = true; setConfirming(false) }}
              className="btn btn-sm btn-secondary"
            >
              {t('expert.draft.keep')}
            </button>
          </div>
        </div>
      )}
    </li>
  )
}

const DraftList: React.FC<DraftListProps> = ({ drafts, onContinue, continueHref, onDiscard, className }) => (
  <ul className={className}>
    {drafts.map(draft => (
      <DraftRow
        key={draft.slot}
        draft={draft}
        onContinue={onContinue}
        continueHref={continueHref}
        onDiscard={onDiscard}
      />
    ))}
  </ul>
)

export default DraftList
