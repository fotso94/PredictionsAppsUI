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
 * recorded withdrawal is frozen. So after kickoff an unpublish hides the prediction from readers
 * and does not take it out of the measured record, and a republish shows it again and does not
 * put it in. Without saying so, an Unpublish button on a lost prediction reads as a way to delete
 * the loss.
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
