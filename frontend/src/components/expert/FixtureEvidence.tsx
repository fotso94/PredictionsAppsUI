import React from 'react'
import clsx from 'clsx'
import { BriefMarketKey, Match } from '@/types'
import {
  freshnessLine, marketBlock, marketLabel, missingReasonLabel, percentDisplay, refreshBlockedNote,
} from '@/utils/brief'
import { fixturePreview, SourcePreview } from '@/utils/matchPreview'
import { onTeamLogoError } from '@/components/ui/imageFallback'
import { formatDateTime } from '@/i18n'
import { useLocale } from '@/i18n/react'

/**
 * What is already known about a fixture, sitting beside the editor while the expert forms a view.
 *
 * This is the SAME evidence a reader sees on the public match page — the same fixture facts, the
 * same model forecast, the same freshness wording — so the expert is writing against what the
 * audience will read, not against a private summary.
 *
 * IT IS CONTEXT, NOT A STARTING VALUE. Nothing here writes into the composer. There is no "copy
 * the model's numbers" control and no field is seeded from a figure on this panel, because a
 * prediction that begins as the model's is the model's prediction wearing an expert's name.
 *
 * A market the model did not supply appears with the brief's own reason for being absent. It never
 * appears as 0%, and no missing number is filled in from odds, from history, or from anything else.
 *
 * IN THE READER'S LANGUAGE, WITH THE BACKEND'S OWN WORDS LEFT AS THEY ARE. The panel's labels and
 * sentences are the catalogue's, each percentage is written the reader's way, and the kick-off is
 * the UTC instant formatted in the zone the reader chose (it used to be the ISO date the mapper
 * wrote, beside a time mapped once at fetch). What the BACKEND wrote — a brief block's `detail`,
 * the freshness `state_reason`, the reason a refresh is paused — is shown verbatim, by the policy
 * in docs/known-limitations.md, inside `<span lang="en" data-verbatim="backend">`: a screen reader
 * then voices it in English rather than mispronouncing it in French, and a test can tell the
 * backend's sentence from an untranslated one of ours.
 */
export interface FixtureEvidenceProps {
  match: Match
  className?: string
}

const TONE_CLASS = {
  ok: 'text-success-300',
  ageing: 'text-warning-200',
  unknown: 'text-secondary-300',
  problem: 'text-danger-300',
} as const

/** A sentence the backend wrote, shown exactly as written and marked as English. */
const Verbatim: React.FC<{ text: string }> = ({ text }) => (
  <span lang="en" data-verbatim="backend">{text}</span>
)

/** One source's match-result view, or the brief's stated reason there is none. */
const SourceView: React.FC<{
  preview: SourcePreview
  homeTeam: string
  awayTeam: string
  /** True when `preview.detail` is the brief's own sentence rather than one of ours. */
  detailFromBackend: boolean
}> = ({ preview, homeTeam, awayTeam, detailFromBackend }) => {
  const { t } = useLocale()
  const nameFor = (key: string) => (key === 'home_win' ? homeTeam : key === 'away_win' ? awayTeam : t('outcome.draw'))
  const confidence = preview.confidence ? percentDisplay(preview.confidence.percent) : null

  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h4 className="text-sm font-semibold text-white">{preview.label}</h4>
        {confidence && (
          // Shown only because the source published it, and labelled as the source's own claim.
          // Nothing here has been scored against a result, so it is never called an accuracy.
          <span className="num text-[11px] text-secondary-300">
            {t('expert.evidence.confidencePublished', { percent: confidence })}
          </span>
        )}
      </div>

      {preview.outcomes.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {preview.outcomes.map(outcome => (
            <li key={outcome.key} className="flex items-baseline justify-between gap-3 text-xs">
              <span className="min-w-0 truncate text-secondary-200">{nameFor(outcome.key)}</span>
              <span
                className={clsx('num flex-shrink-0 font-semibold', outcome.key === preview.lead?.key ? 'text-white' : 'text-secondary-200')}
              >
                {percentDisplay(outcome.percent)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-secondary-300">
          {/* The backend's own sentence wherever it supplied one. Never "0%", never blank. */}
          {preview.detail
            ? (detailFromBackend ? <Verbatim text={preview.detail} /> : preview.detail)
            : missingReasonLabel(preview.reason) ?? t('expert.evidence.nothingForResult')}
        </p>
      )}
    </div>
  )
}

const FixtureEvidence: React.FC<FixtureEvidenceProps> = ({ match, className }) => {
  const { t } = useLocale()
  const preview = fixturePreview(match)
  const freshness = freshnessLine(match.brief?.freshness)
  const paused = refreshBlockedNote(match.brief?.freshness ?? match.briefCompact)

  // Which of these strings the backend wrote. `fixturePreview` takes a source's `detail` from the
  // full brief's block when there is one, and otherwise writes one of the catalogue's sentences.
  const fromBrief = (source: 'model' | 'expert') => marketBlock(match.brief, 'match_result', source) !== null
  const stateReason = match.brief?.freshness?.state_reason ?? null
  const blockedReason = (match.brief?.freshness ?? match.briefCompact)?.refresh_blocked_reason ?? null

  const suppliedByModel: BriefMarketKey[] = match.briefCompact?.supplied_markets?.model ?? []
  const missingForModel: BriefMarketKey[] = match.briefCompact?.missing_markets?.model ?? []

  // The kick-off in the reader's chosen zone, from the instant. The mapped pair stands in only
  // for a payload that carried no instant at all.
  const kickoff = formatDateTime(match.kickoffUtc) ?? `${match.date} ${match.time}`

  return (
    <aside className={clsx('card p-4', className)} aria-label={t('expert.evidence.regionLabel')}>
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-white">{t('expert.evidence.heading')}</h3>
        <p className="mt-1 text-xs text-secondary-400">
          {t('expert.evidence.intro')}
        </p>
      </div>

      {/* ------------------------------------------------------------------ the fixture itself */}
      <div className="rounded-lg border border-dark-700 bg-dark-900/60 p-3">
        <p className="truncate text-xs text-secondary-400">{match.league.name}</p>
        <div className="mt-2 space-y-1.5">
          {[
            { team: match.homeTeam, side: 'home', label: t('expert.evidence.home') },
            { team: match.awayTeam, side: 'away', label: t('expert.evidence.away') },
          ].map(({ team, side, label }) => (
            <div key={side} className="flex min-w-0 items-center gap-2">
              <img src={team.logo} alt="" aria-hidden="true" className="h-4 w-4 flex-shrink-0 object-contain" onError={onTeamLogoError} />
              <span className="min-w-0 truncate text-sm text-white">{team.name}</span>
              <span className="ml-auto flex-shrink-0 text-[11px] uppercase tracking-wide text-secondary-500">{label}</span>
            </div>
          ))}
        </div>
        <dl className="mt-3 space-y-1 text-xs text-secondary-300">
          <div className="flex gap-2">
            <dt className="flex-shrink-0 text-secondary-500">{t('expert.evidence.kickoff')}</dt>
            <dd className="num min-w-0 break-words">{kickoff}</dd>
          </div>
          {match.venue && (
            <div className="flex gap-2">
              <dt className="flex-shrink-0 text-secondary-500">{t('expert.evidence.venue')}</dt>
              <dd className="min-w-0 break-words">{match.venue}</dd>
            </div>
          )}
          {match.round && (
            <div className="flex gap-2">
              <dt className="flex-shrink-0 text-secondary-500">{t('expert.evidence.round')}</dt>
              <dd className="min-w-0 break-words">{match.round}</dd>
            </div>
          )}
        </dl>
      </div>

      {/* ------------------------------------------------------------------ the sources */}
      <div className="mt-4 space-y-4">
        <SourceView
          preview={preview.model}
          homeTeam={match.homeTeam.name}
          awayTeam={match.awayTeam.name}
          detailFromBackend={fromBrief('model')}
        />

        {freshness && (
          <p className={clsx('text-[11px]', TONE_CLASS[freshness.tone])}>
            {freshness.text}
            {freshness.detail && (
              <span className="block text-secondary-400">
                {freshness.detail === stateReason ? <Verbatim text={freshness.detail} /> : freshness.detail}
              </span>
            )}
          </p>
        )}
        {paused && (
          // Deliberately its own line: "nobody has asked recently" is not the same statement as
          // "what is on screen is out of date".
          <p className="text-[11px] text-secondary-400">
            {paused === blockedReason ? <Verbatim text={paused} /> : paused}
          </p>
        )}

        {suppliedByModel.length > 0 && (
          <p className="text-[11px] text-secondary-400">
            {t('expert.evidence.modelMarketsHeld', { markets: suppliedByModel.map(marketLabel).join(', ') })}
          </p>
        )}
        {missingForModel.length > 0 && (
          <p className="text-[11px] text-secondary-400">
            {t('expert.evidence.notSuppliedByModel', { markets: missingForModel.map(marketLabel).join(', ') })}
          </p>
        )}

        <div className="border-t border-dark-700 pt-4">
          <SourceView
            preview={preview.expert}
            homeTeam={match.homeTeam.name}
            awayTeam={match.awayTeam.name}
            detailFromBackend={fromBrief('expert')}
          />
        </div>
      </div>
    </aside>
  )
}

export default FixtureEvidence
