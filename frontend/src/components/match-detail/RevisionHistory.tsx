import React from 'react'
import type { ExpertPredictionRevision, ExpertPredictionRevisionChange, ExpertPredictionRevisionValues } from '@/types'
import { formatUnitProbability, isPublished, notSetText } from '@/components/ui/probability'
import { backendInstant, formatDateTime, formatNumber, type MessageKey, type TranslateFn } from '@/i18n'
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
 *
 * EVERY MARKET THE VERSION CARRIED (QA finding 6). This rendered four cells — home, draw, away and
 * the 1X2 conviction — so an expert's earlier both-teams-to-score and total-goals figures, the very
 * ones an edit most often changes, were nowhere on the page. Each market is now a labelled group,
 * and each figure is in one of four states that are never allowed to read as one another:
 *   - a number, INCLUDING 0, is a figure the expert published ("0%" is a claim);
 *   - null is "not set": the version carried the field and the expert published nothing there;
 *   - both halves of a two-way market null is the market LEFT OUT, said once for the market;
 *   - a key the snapshot does not carry at all is "not recorded in this version". Every snapshot
 *     the backend writes carries all twelve fields, so this is defensive, but saying "not set" of
 *     a field nobody recorded would be inventing a fact.
 *
 * WHAT CHANGED IS BUILT FROM `changes`, NEVER FROM `changes_summary`. The summary is the backend's
 * audit text — `btts_yes_prob 0.6 -> 0.4`, column names and Python values — and it was printed
 * here verbatim, in English, under a comment that called it the expert's own words. It is no
 * longer rendered at all. `changes` is the same diff as data, so each line is a sentence in the
 * reader's language with formatted percentages. A row without `changes` (an older backend, or a
 * revision missing a snapshot) shows no change line, because nothing can then be said about what
 * changed, and printing the audit text instead would bring back exactly what this replaced.
 *
 * GROUPED BY PREDICTION, UNDER ITS AUTHOR. The detail payload flattens every expert's revisions into
 * one list numbered per prediction, so two experts' "Version 1" used to sit side by side with no
 * attribution. Each prediction's versions are now a group of their own, headed with the author's
 * public username, in the order the experts appear on the card.
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

/** The twelve numeric fields a revision snapshot carries (REVISION_VALUE_FIELDS in the backend). */
type NumericField =
  | 'home_win_prob' | 'draw_prob' | 'away_win_prob' | 'confidence_score'
  | 'btts_yes_prob' | 'btts_no_prob' | 'btts_confidence'
  | 'total_goals_over_25_prob' | 'total_goals_under_25_prob'
  | 'total_goals_over_35_prob' | 'total_goals_under_35_prob' | 'total_goals_confidence'

/** Which market a field belongs to and what its side is called. `line` is a goal line, formatted per language. */
const FIELD_LABELS: Record<NumericField, { market: MessageKey; side: MessageKey; line?: number }> = {
  home_win_prob: { market: 'market.matchResult', side: 'reader.revisions.home' },
  draw_prob: { market: 'market.matchResult', side: 'reader.revisions.draw' },
  away_win_prob: { market: 'market.matchResult', side: 'reader.revisions.away' },
  confidence_score: { market: 'market.matchResult', side: 'reader.revisions.conviction' },
  btts_yes_prob: { market: 'market.btts', side: 'selections.outcome.yes' },
  btts_no_prob: { market: 'market.btts', side: 'selections.outcome.no' },
  btts_confidence: { market: 'market.btts', side: 'reader.revisions.conviction' },
  total_goals_over_25_prob: { market: 'market.overUnder25', side: 'selections.outcome.over', line: 2.5 },
  total_goals_under_25_prob: { market: 'market.overUnder25', side: 'selections.outcome.under', line: 2.5 },
  total_goals_over_35_prob: { market: 'market.overUnder35', side: 'selections.outcome.over', line: 3.5 },
  total_goals_under_35_prob: { market: 'market.overUnder35', side: 'selections.outcome.under', line: 3.5 },
  total_goals_confidence: { market: 'reader.revisions.totalGoals', side: 'reader.revisions.conviction' },
}

const isNumericField = (field: string): field is NumericField => Object.prototype.hasOwnProperty.call(FIELD_LABELS, field)

const sideLabel = (t: TranslateFn, field: NumericField): string => {
  const { side, line } = FIELD_LABELS[field]
  return line === undefined ? t(side) : t(side, { line: formatNumber(line) })
}

/** The markets of one version, in the order the public card shows them. */
const MARKETS: Array<{ id: string; title: MessageKey; halves: NumericField[]; conviction?: NumericField }> = [
  { id: '1x2', title: 'market.matchResult', halves: ['home_win_prob', 'draw_prob', 'away_win_prob'], conviction: 'confidence_score' },
  { id: 'btts', title: 'market.btts', halves: ['btts_yes_prob', 'btts_no_prob'], conviction: 'btts_confidence' },
  { id: 'ou25', title: 'market.overUnder25', halves: ['total_goals_over_25_prob', 'total_goals_under_25_prob'] },
  { id: 'ou35', title: 'market.overUnder35', halves: ['total_goals_over_35_prob', 'total_goals_under_35_prob'] },
]

type Snapshot = Partial<Record<NumericField, number | null>>

/** Whether the snapshot carries the field at all — null counts as carried, a missing key does not. */
const recorded = (values: Snapshot, field: NumericField): boolean => Object.prototype.hasOwnProperty.call(values, field)

/** The text one cell shows: the percentage, "not set" for null, "not recorded" for a missing key. */
const cellText = (t: TranslateFn, values: Snapshot, field: NumericField): string =>
  recorded(values, field) ? formatUnitProbability(values[field], 0, notSetText()) : t('reader.revisions.notRecorded')

/** One figure from an earlier version, labelled. */
const Value: React.FC<{ field: NumericField; values: Snapshot }> = ({ field, values }) => {
  const t = useT()
  return (
    <div className="rounded bg-dark-900 px-2 py-1" data-testid="revision-value" data-field={field}>
      <div className="text-[11px] leading-4 text-secondary-500">{sideLabel(t, field)}</div>
      <div className="break-words text-xs text-secondary-200">{cellText(t, values, field)}</div>
    </div>
  )
}

/**
 * The state a market is in for this version. `left-out` and `not-recorded` are said once for the
 * whole market; anything else is a cell per side, each in its own state.
 */
function marketState(values: Snapshot, halves: NumericField[]): 'cells' | 'left-out' | 'not-recorded' {
  if (halves.every(field => !recorded(values, field))) return 'not-recorded'
  if (halves.every(field => recorded(values, field) && values[field] === null)) return 'left-out'
  return 'cells'
}

const Market: React.FC<{ id: string; title: MessageKey; state: string; children?: React.ReactNode; note?: string }> = ({
  id, title, state, children, note,
}) => {
  const t = useT()
  return (
    <div data-testid="revision-market" data-market={id} data-state={state}>
      <div className="text-[11px] font-medium leading-4 text-secondary-400">{t(title)}</div>
      {note && <p className="text-xs text-secondary-400">{note}</p>}
      {children && <div className="mt-1 grid grid-cols-2 gap-1.5 sm:grid-cols-4">{children}</div>}
    </div>
  )
}

const RevisionValues: React.FC<{ values: ExpertPredictionRevisionValues }> = ({ values }) => {
  const t = useT()
  const snapshot = (values ?? {}) as unknown as Snapshot
  const states = MARKETS.map(market => marketState(snapshot, market.halves))

  return (
    <div className="mt-2 space-y-2">
      {MARKETS.map((market, index) => {
        const state = states[index]
        const conviction = market.conviction
        // A market that is left out or unrecorded still shows a conviction the version DID carry
        // as a number: hiding a published figure is not this component's call.
        const showConviction = conviction !== undefined
          && (state === 'cells' || isPublished(snapshot[conviction]))
        const note = state === 'left-out'
          ? t('missing.marketNotSupplied')
          : state === 'not-recorded' ? t('reader.revisions.notRecorded') : undefined
        return (
          <Market key={market.id} id={market.id} title={market.title} state={state} note={note}>
            {state === 'cells' || showConviction ? (
              <>
                {state === 'cells' && market.halves.map(field => <Value key={field} field={field} values={snapshot} />)}
                {showConviction && conviction && <Value field={conviction} values={snapshot} />}
              </>
            ) : null}
          </Market>
        )
      })}
      {/*
        The total-goals conviction covers both lines, so it stands on its own — and only when
        there is something for it to qualify, or it is itself a published figure. Both lines left
        out with no conviction is one market left out twice, not a third gap to report.
      */}
      {(states[2] === 'cells' || states[3] === 'cells' || isPublished(snapshot.total_goals_confidence)) && (
        <Market id="totals-conviction" title="reader.revisions.totalGoals" state="cells">
          <Value field="total_goals_confidence" values={snapshot} />
        </Market>
      )}
    </div>
  )
}

/** One change as a sentence, or null for a field this build cannot name (never shown by its column name). */
function changeSentence(t: TranslateFn, change: ExpertPredictionRevisionChange): string | null {
  if (change.field === 'reasoning') return t('reader.revisions.change.reasoning')
  if (change.field === 'key_factors') return t('reader.revisions.change.keyFactors')
  if (!isNumericField(change.field)) return null
  const field = t('reader.revisions.fieldLabel', {
    market: t(FIELD_LABELS[change.field].market),
    side: sideLabel(t, change.field),
  })
  // Whole percentages, as the cells show them — unless that would print "55% → 55%" for a real
  // change (0.551 to 0.554), in which case one decimal place says what moved.
  const digits = isPublished(change.from) && isPublished(change.to)
    && formatUnitProbability(change.from, 0) === formatUnitProbability(change.to, 0) ? 1 : 0
  const from = isPublished(change.from) ? formatUnitProbability(change.from, digits) : null
  const to = isPublished(change.to) ? formatUnitProbability(change.to, digits) : null
  if (from !== null && to !== null) return t('reader.revisions.change.value', { field, from, to })
  if (to !== null) return t('reader.revisions.change.set', { field, to })
  if (from !== null) return t('reader.revisions.change.withdrawn', { field, from })
  return null
}

const Changes: React.FC<{ changes: ExpertPredictionRevisionChange[] | null | undefined }> = ({ changes }) => {
  const t = useT()
  const sentences = (Array.isArray(changes) ? changes : [])
    .map(change => changeSentence(t, change))
    .filter((sentence): sentence is string => sentence !== null)
  if (sentences.length === 0) return null
  return (
    <div className="mt-1 text-xs text-secondary-300" data-testid="revision-changes">
      <span className="text-secondary-500">{t('reader.revisions.whatChanged')}</span>
      <ul className="mt-0.5 list-inside list-disc space-y-0.5">
        {sentences.map(sentence => <li key={sentence} data-testid="revision-change">{sentence}</li>)}
      </ul>
    </div>
  )
}

/** Whose prediction a group of versions belongs to, in the order the card lists the experts. */
export interface RevisionAuthor {
  predictionId: string | null | undefined
  /** The public username, or null when there is none to show (see `publicExpertName`). */
  name: string | null
}

/** One prediction's earlier versions, under its author. */
const RevisionGroup: React.FC<{ predictionId: string; name: string | null; revisions: ExpertPredictionRevision[] }> = ({
  predictionId, name, revisions,
}) => {
  const t = useT()
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
   *
   * Counted per prediction: "this view was updated twice" is a claim about ONE expert's view.
   */
  const when = stamp(latest)
  const summary: MessageKey = corrections === 1
    ? (when ? 'reader.revisions.summaryOnceWhen' : 'reader.revisions.summaryOnce')
    : (when ? 'reader.revisions.summaryManyWhen' : 'reader.revisions.summaryMany')

  return (
    <div data-testid="expert-revision-group" data-prediction-id={predictionId}>
      <h5 className="mt-2 text-xs font-semibold text-secondary-200">
        {name ? t('reader.revisions.byAuthor', { name }) : t('reader.revisions.byUnnamed')}
      </h5>
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
            <Changes changes={revision.changes} />
            <RevisionValues values={revision.values} />
            {revision.values?.reasoning && (
              <p className="mt-2 whitespace-pre-line break-words text-xs text-secondary-400">{revision.values.reasoning}</p>
            )}
          </li>
        ))}
      </ol>
    </div>
  )
}

const RevisionHistory: React.FC<{ revisions: ExpertPredictionRevision[]; authors?: RevisionAuthor[]; className?: string }> = ({
  revisions,
  authors = [],
  className,
}) => {
  const t = useT()
  if (revisions.length === 0) return null

  // The card's experts first, in its order; a prediction the card does not list (it should not
  // happen — both come from one payload) still keeps its versions, after them and unnamed.
  const order = authors.map(author => author.predictionId).filter((id): id is string => Boolean(id))
  revisions.forEach(revision => { if (!order.includes(revision.prediction_id)) order.push(revision.prediction_id) })
  const groups = order
    .map(predictionId => ({
      predictionId,
      name: authors.find(author => author.predictionId === predictionId)?.name ?? null,
      revisions: revisions
        .filter(revision => revision.prediction_id === predictionId)
        .sort((a, b) => a.revision - b.revision),
    }))
    .filter(group => group.revisions.length > 0)

  return (
    <section className={className} data-testid="expert-revisions">
      <h4 className="text-sm font-semibold text-white">{t('reader.revisions.heading')}</h4>
      <div className="space-y-3">
        {groups.map(group => (
          <RevisionGroup key={group.predictionId} predictionId={group.predictionId} name={group.name} revisions={group.revisions} />
        ))}
      </div>
    </section>
  )
}

export default RevisionHistory
