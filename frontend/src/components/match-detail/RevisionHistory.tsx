import React from 'react'
import type { ExpertPredictionRevision, ExpertPredictionRevisionValues } from '@/types'
import { formatUnitProbability, NOT_SET_TEXT } from '@/components/ui/probability'

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

const stamp = (iso: string | null | undefined): string | null => {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

/** One published number from an earlier version. `not set` when that version carried none. */
const Value: React.FC<{ label: string; value: number | null }> = ({ label, value }) => (
  <div className="rounded bg-dark-900 px-2 py-1">
    <div className="text-[11px] leading-4 text-secondary-500">{label}</div>
    <div className="text-xs text-secondary-200">{formatUnitProbability(value, 0, NOT_SET_TEXT)}</div>
  </div>
)

const RevisionValues: React.FC<{ values: ExpertPredictionRevisionValues }> = ({ values }) => (
  <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
    <Value label="Home" value={values.home_win_prob} />
    <Value label="Draw" value={values.draw_prob} />
    <Value label="Away" value={values.away_win_prob} />
    <Value label="Confidence" value={values.confidence_score} />
  </div>
)

const RevisionHistory: React.FC<{ revisions: ExpertPredictionRevision[]; className?: string }> = ({
  revisions,
  className,
}) => {
  if (revisions.length === 0) return null

  const corrections = revisions.length
  const latest = revisions.reduce<string | null>(
    (newest, revision) => (revision.replaced_at && (!newest || revision.replaced_at > newest) ? revision.replaced_at : newest),
    null,
  )

  return (
    <section className={className} data-testid="expert-revisions">
      <h4 className="text-sm font-semibold text-white">Earlier published versions</h4>
      <p className="mt-1 text-xs text-secondary-400">
        This view was updated {corrections === 1 ? 'once' : `${corrections} times`}
        {latest ? `, most recently on ${stamp(latest)}` : ''}. Each earlier version is kept exactly as
        it was published; a correction is added to the record rather than replacing it.
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
                Version {revision.revision}{revision.revision === 1 ? ' · as first published' : ''}
              </span>
              {revision.replaced_at && (
                <span className="text-secondary-500">replaced {stamp(revision.replaced_at)}</span>
              )}
              {/*
                Only stated when it is true. `null` means the kickoff time is unknown, and saying
                "edited before kick-off" there would be a claim with nothing to compare against.
              */}
              {revision.edited_after_kickoff === true && (
                <span className="rounded-md border border-orange-700 px-1.5 py-0.5 text-[11px] leading-4 text-orange-200">
                  edited after kick-off
                </span>
              )}
            </div>
            {revision.changes_summary && (
              <p className="mt-1 text-xs text-secondary-300">
                <span className="text-secondary-500">What changed: </span>{revision.changes_summary}
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
