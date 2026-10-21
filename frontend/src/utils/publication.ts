/**
 * Publish and unpublish, the same way on every page that offers them.
 *
 * My Predictions and the dashboard's recent list both let an expert take a published prediction
 * off the public lists (PUBLISHED -> ARCHIVED) and put it back. The backend toggles those two
 * statuses and no others (`toggle_publish_status` in backend/app/services/expert_prediction.py),
 * so that is the rule here too.
 *
 * WHAT A CHANGE DOES DEPENDS ON KICKOFF, and the expert is told before they press OK. Settlement
 * scores what stood at kickoff (`stood_at_kickoff` in backend/app/services/settlement.py): a
 * withdrawal counts only when it was made before kickoff, and once the match has kicked off the
 * recorded withdrawal is frozen. So after kickoff an unpublish, a republish and a deletion change
 * what readers see and do not change the measured record, whichever way it stands: a prediction
 * that counted still counts, and one that never counted still does not. The notes say exactly
 * that ("does not change"), so neither implies a state the prediction is not in (finding #19).
 * Without them, an Unpublish or a Delete button on a lost prediction reads as a way to remove the
 * loss (finding #20).
 *
 * WHETHER A PREDICTION IS IN THE RECORD AT ALL is said on the card and the dashboard row
 * (`notScoredReason`, finding #1), by the same rule settlement applies, for the two ways a
 * prediction that was public falls outside it: published at or after kickoff, or withdrawn before
 * kickoff (including one published again afterwards, whose withdrawal is frozen).
 *
 * The boundary is the backend's: AT kickoff counts as after it (`at_or_after_kickoff`). A
 * prediction whose kickoff is unknown gets no note, because nothing can be said about it.
 */

import { backendInstant } from '@/i18n'
import type { MessageKey, TranslateFn } from '@/i18n'
import type { ExpertPredictionResponse } from '@/types/expert'

const TOGGLEABLE_STATUSES = ['published', 'archived']

/** Can this prediction be unpublished or published again? Case-insensitive, as the API's casing is not guaranteed. */
export const canTogglePublication = (status: string): boolean =>
  TOGGLEABLE_STATUSES.includes((status || '').toLowerCase())

/** True at and after kickoff, false before it, and false when the kickoff is not known. */
export function hasKickedOff(prediction: ExpertPredictionResponse, now: number = Date.now()): boolean {
  const kickoff = backendInstant(prediction.match_details?.match_date).at
  return kickoff !== null && now >= kickoff.getTime()
}

/** The note a publication change made now needs, or null when it needs none (before kickoff). */
export function kickedOffNoteKey(prediction: ExpertPredictionResponse, now: number = Date.now()): MessageKey | null {
  if (!canTogglePublication(prediction.status) || !hasKickedOff(prediction, now)) return null
  return prediction.status.toLowerCase() === 'published'
    ? 'expert.publication.kickedOffUnpublish'
    : 'expert.publication.kickedOffPublish'
}

/**
 * Why this prediction is already known to be outside the expert's measured record, or null.
 *
 * Settlement's `stood_at_kickoff` for a row that was public (published or archived), from the two
 * stored times the expert's own payload carries:
 *   - `publishedAfterKickoff`: `published_at` at or after kickoff. Never prematch evidence.
 *   - `withdrawnBeforeKickoff`: once kickoff has passed, `unpublished_at` before it. Whether the
 *     row is still down (archived) or was published again afterwards (the backend keeps that
 *     withdrawal frozen), nobody could read it when the match started.
 * Null when the row counts, when nothing is decided yet (before kickoff a withdrawal can still be
 * undone, and a republish then clears `unpublished_at`), when either time is unknown, and for a
 * row that was never public (pending, rejected), which is not a record question.
 */
export type NotScoredReason = 'publishedAfterKickoff' | 'withdrawnBeforeKickoff'

export function notScoredReason(prediction: ExpertPredictionResponse, now: number = Date.now()): NotScoredReason | null {
  if (!canTogglePublication(prediction.status)) return null
  const kickoff = backendInstant(prediction.match_details?.match_date).at
  if (kickoff === null) return null
  const published = backendInstant(prediction.published_at).at
  if (published !== null && published.getTime() >= kickoff.getTime()) return 'publishedAfterKickoff'
  if (now < kickoff.getTime()) return null
  // The backend serves this one without a zone; backendInstant reads it as the UTC it is.
  const unpublished = backendInstant(prediction.unpublished_at).at
  return unpublished !== null && unpublished.getTime() < kickoff.getTime() ? 'withdrawnBeforeKickoff' : null
}

/** The label for `notScoredReason`, in the expert's own words. */
export const NOT_SCORED_LABEL: Record<NotScoredReason, MessageKey> = {
  publishedAfterKickoff: 'expert.record.publishedAfterKickoff',
  withdrawnBeforeKickoff: 'expert.record.withdrawnBeforeKickoff',
}

/**
 * The confirmation for deleting this prediction now: the page's question, then, after kickoff on
 * a prediction that was public, the note that a deletion does not change the measured record.
 * A pending or rejected row was never in the record, and before kickoff nothing is decided yet.
 */
export function deleteConfirmText(
  prediction: ExpertPredictionResponse,
  question: MessageKey,
  t: TranslateFn,
  now: number = Date.now(),
): string {
  const note = canTogglePublication(prediction.status) && hasKickedOff(prediction, now)
    ? t('expert.publication.kickedOffDelete')
    : null
  return note ? `${t(question)}\n\n${note}` : t(question)
}

/** The confirmation for publishing or unpublishing this prediction now: the question, then any note. */
export function publicationConfirmText(
  prediction: ExpertPredictionResponse,
  t: TranslateFn,
  now: number = Date.now(),
): string {
  const question = t(prediction.status.toLowerCase() === 'published'
    ? 'expert.publication.confirmUnpublish'
    : 'expert.publication.confirmPublish')
  const note = kickedOffNoteKey(prediction, now)
  return note ? `${question}\n\n${t(note)}` : question
}
