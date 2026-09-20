import React from 'react'
import type { ExpertPredictionRevision, ExpertPredictionRevisionValues } from '@/types'
import { formatUnitProbability, notSetText } from '@/components/ui/probability'
import { backendInstant, formatDateTime, formatNumber, type MessageKey } from '@/i18n'
import { useT } from '@/i18n/react'

/**
 * Earlier published versions of an expert's view — a correction appends, it does not rewrite.
 *
 * Editing a published prediction replaces the live row, so without this the numbers a reader saw
 * yesterday would simply be gone and the page would show today's numbers as though they had always
 * been there. Every version the correction replaced is kept and shown here, with what changed and
 * when it stopped being the published view.
 *
 * Nothing is recomputed: `values` is the whole earlier view as it was published, so the original is
 * read back rather than reconstructed from a summary of the differences.
 *
 * It is rendered in full rather than behind a disclosure, because "the original is still visible"
 * is the claim this section makes, and a reader should not have to find it.
 */

/**
 * When a version stopped being the published one, in the reader's own zone.
 *
 * `new Date(iso).toLocaleString()` — what this was — read an offset-less timestamp in the
 * DEVICE's zone and then printed it in the device's zone and the device's locale. This is a
 * correction history: "the number you read yesterday was replaced at X" is only meaningful
 * against the reader's own clock, so X is shown in the zone they chose. `backendInstant` reads
 * the value as the UTC the server wrote where the payload named no zone (this one does name
 * one — `iso_utc` in backend/app/schemas/matches.py:22 — but reading it that way costs nothing
 * and stops a naive timestamp being silently shifted if that ever changes).
 */
const stamp = (iso: string | null | undefined): string | null => {
  if (!iso) return null
  const read = backendInstant(iso)
  if (!read.at) return typeof iso === 'string' ? iso : null
  return formatDateTime(read.at)
}

/** One published number from an earlier version. `not set` when that version carried none. */
const Value: React.FC<{ label: MessageKey; value: number | null }> = ({ label, value }) => {
  const t = useT()
  return (
    <div className="rounded bg-dark-900 px-2 py-1">
      <div className="text-[11px] leading-4 text-secondary-500">{t(label)}</div>
      <div className="text-xs text-secondary-200">{formatUnitProbability(value, 0, notSetText())}</div>
    </div>
  )
}

const RevisionValues: React.FC<{ values: ExpertPredictionRevisionValues }> = ({ values }) => (
  <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
    <Value label="reader.revisions.home" value={values.home_win_prob} />
    <Value label="reader.revisions.draw" value={values.draw_prob} />
    <Value label="reader.revisions.away" value={values.away_win_prob} />
    <Value label="reader.revisions.confidence" value={values.confidence_score} />
  </div>
)

const RevisionHistory: React.FC<{ revisions: ExpertPredictionRevision[]; className?: string }> = ({
  revisions,
  className,
}) => {
  const t = useT()
  if (revisions.length === 0) return null

  const corrections = revisions.length
  const latest = revisions.reduce<string | null>(
    (newest, revision) => (revision.replaced_at && (!newest || revision.replaced_at > newest) ? revision.replaced_at : newest),
    null,
  )

  /**
   * FOUR WHOLE SENTENCES, NOT ONE ASSEMBLED FROM PIECES.
   *
   * This was a template literal: an English fragment, a ternary for "once" against "N times", a
   * second ternary for ", most recently on X", then the rest of the English. Every one of those
   * pieces is frozen in English word order, and a language that puts the count or the date
   * somewhere else cannot say so. The catalogue holds each of the four forms in full instead, so
   * the translation decides the order.
   *
   * There is no `{count, plural, …}` here and it is not needed: French « fois » does not
   * inflect, and the branch that exists is the English one between "once" and "N times", which
   * is a different word rather than a different form. See the header of reader.fr.ts for why a
   * plural could not have been used even where one WAS needed.
   */
  const when = stamp(latest)
  const summary: MessageKey = corrections === 1
    ? (when ? 'reader.revisions.summaryOnceWhen' : 'reader.revisions.summaryOnce')
    : (when ? 'reader.revisions.summaryManyWhen' : 'reader.revisions.summaryMany')

  return (
    <section className={className} data-testid="expert-revisions">
      <h4 className="text-sm font-semibold text-white">{t('reader.revisions.heading')}</h4>
      <p className="mt-1 text-xs text-secondary-400">
        {t(summary, { count: formatNumber(corrections), when: when ?? '' })}
      </p>
      <ol className="mt-2 space-y-2">
        {revisions.map(revision => (
          <li
            key={revision.id}
            className="rounded-lg border border-dark-700 bg-dark-800/50 px-3 py-2"
            data-testid="expert-revision"
            data-revision={revision.revision}
          >
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
              <span className="font-medium text-secondary-200">
                {t('reader.revisions.version', { number: formatNumber(revision.revision) })}
                {revision.revision === 1 ? t('reader.revisions.asFirstPublished') : ''}
              </span>
              {revision.replaced_at && (
                <span className="text-secondary-500">
                  {t('reader.revisions.replaced', { when: stamp(revision.replaced_at) ?? '' })}
                </span>
              )}
              {/*
                Only stated when it is true. `null` means the kickoff time is unknown, and saying
                "edited before kick-off" there would be a claim with nothing to compare against.
              */}
              {revision.edited_after_kickoff === true && (
                <span className="rounded-md border border-orange-700 px-1.5 py-0.5 text-[11px] leading-4 text-orange-200">
                  {t('reader.revisions.editedAfterKickoff')}
                </span>
              )}
            </div>
            {revision.changes_summary && (
              <p className="mt-1 text-xs text-secondary-300">
                {/* The expert's own summary of the change, shown as they wrote it. */}
                <span className="text-secondary-500">{t('reader.revisions.whatChanged')}</span>{revision.changes_summary}
              </p>
            )}
            <RevisionValues values={revision.values} />
            {revision.values.reasoning && (
              <p className="mt-2 whitespace-pre-line text-xs text-secondary-400">{revision.values.reasoning}</p>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}

export default RevisionHistory
