import React from 'react'
import clsx from 'clsx'
import { ComposerValues, OptionalMarketKey, publishableValues } from './composer'
import { goalLine, optionalMarketLabel } from './composerText'
import { formatPercentShown, parsePercent } from './percent'
import { currentLocale, formatDateTime, formatPercentValue } from '@/i18n'
import { useLocale } from '@/i18n/react'
import Emphasised from '@/i18n/Emphasised'

/**
 * Exactly what a reader will see, before the expert commits to it.
 *
 * Built from the composer's own values rather than from anything returned by the API, so the
 * preview is the request that is about to be sent. A market the expert did not tick appears here
 * as UNAVAILABLE, in the same words the public pages use — the expert sees the consequence of
 * leaving it out rather than discovering later that readers were shown a blank.
 *
 * No number on this panel is rounded into something friendlier, completed, or renormalised. If the
 * three outcomes do not total 100 the composer refuses to publish; the preview never quietly fixes
 * them on the way past.
 *
 * In the reader's language and locale: every sentence is the catalogue's, every percentage is
 * written the reader's way (55.5% / « 55,5 % »), and the kick-off is formatted from the UTC
 * instant, at render time, in the zone the reader CHOSE — not the string the draft froze in
 * whatever zone was current when it was saved. Team and competition names are the provider's.
 */
export interface PublishPreviewProps {
  values: ComposerValues
  fixture: {
    homeTeam: string
    awayTeam: string
    competition: string | null
    /** The kick-off as text, for a fixture whose instant is unknown. */
    kickoff: string | null
    /** The kick-off instant (ISO, UTC). Preferred whenever it is known. */
    kickoffUtc?: string | null
  } | null
  /**
   * The fixture has kicked off, so what is about to be published will be labelled late and never
   * scored.
   */
  kickedOff?: boolean
  className?: string
}

/** A percentage as it will be published, or null when the field holds nothing readable. */
function shown(text: string): string | null {
  const value = parsePercent(text)
  return value === null ? null : formatPercentShown(value, currentLocale())
}

const Line: React.FC<{ label: string; value: string | null }> = ({ label, value }) => {
  const { t } = useLocale()
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <span className="min-w-0 truncate text-secondary-200">{label}</span>
      <span className={clsx('flex-shrink-0 font-semibold', value ? 'num text-white' : 'text-secondary-400')}>
        {value ?? t('probability.unavailable')}
      </span>
    </div>
  )
}

/** An optional market the expert left out. Named, so its absence is a stated fact, not a gap. */
const NotPublished: React.FC<{ market: OptionalMarketKey }> = ({ market }) => {
  const { t } = useLocale()
  const label = optionalMarketLabel(market)
  // `{zero}` is formatted: the sentence warning against "0%" must not print an English "0%".
  const sentence = t('expert.preview.notPublished', { market: label, zero: formatPercentValue(0, 0) })
  return (
    <div className="rounded-lg border border-dashed border-dark-700 px-3 py-2">
      <p className="text-xs text-secondary-300">
        <Emphasised sentence={sentence} value={label} className="font-medium text-secondary-200" />
      </p>
    </div>
  )
}

/** One opt-in market the expert ticked: its name, then its two sides. */
const TwoWay: React.FC<{ market: OptionalMarketKey; sides: Array<[string, string]> }> = ({ market, sides }) => (
  <div className="rounded-lg border border-dark-700 px-3 py-2">
    <p className="mb-1.5 text-xs font-medium text-secondary-200">{optionalMarketLabel(market)}</p>
    {sides.map(([label, text]) => <Line key={label} label={label} value={shown(text)} />)}
  </div>
)

const PublishPreview: React.FC<PublishPreviewProps> = ({ values, fixture, kickedOff = false, className }) => {
  const { t } = useLocale()
  const payload = publishableValues(values)
  const conviction = shown(values.conviction)
  const convictionSentence = conviction ? t('expert.preview.convictionStated', { value: conviction }) : ''
  const kickoff = fixture ? formatDateTime(fixture.kickoffUtc) ?? fixture.kickoff : null

  return (
    <section className={clsx('card p-4', className)} aria-label={t('expert.preview.regionLabel')}>
      <h3 className="text-sm font-semibold text-white">{t('expert.action.preview')}</h3>
      <p className="mt-1 text-xs text-secondary-400">
        {t('expert.preview.intro')}
      </p>

      {kickedOff && (
        <p
          className="mt-3 rounded-lg border border-warning-700 bg-warning-900/30 px-3 py-2 text-xs text-warning-200"
          role="status"
          data-testid="preview-kickoff-warning"
        >
          {t('expert.preview.kickedOff')}
        </p>
      )}

      {fixture && (
        <div className="mt-3 rounded-lg border border-dark-700 bg-dark-900/60 p-3">
          {/* Both clubs, whole: a French "contre" line is longer than the box at 360px. */}
          <p className="break-words text-sm font-medium text-white">
            {t('expert.fixtureShort', { home: fixture.homeTeam, away: fixture.awayTeam })}
          </p>
          {/*
            Only the competition may give way (review finding #24): this was one `truncate`d line,
            "{competition} · {kick-off}", and with a long competition the ellipsis took the kick-off.
            The kick-off is never cut and never broken; when the pair does not fit, the line wraps.
          */}
          <p className="mt-0.5 flex flex-wrap items-baseline gap-x-1 text-xs text-secondary-400">
            {fixture.competition && <span className="min-w-0 max-w-full truncate">{fixture.competition}</span>}
            {kickoff && (
              <span className="num whitespace-nowrap" data-testid="preview-kickoff">
                {fixture.competition ? '· ' : ''}{kickoff}
              </span>
            )}
            {!fixture.competition && !kickoff && <span>{t('expert.row.fixtureUnavailable')}</span>}
          </p>
        </div>
      )}

      <div className="mt-4 space-y-4">
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-secondary-400">{t('market.matchResult')}</h4>
          <div className="space-y-1.5">
            <Line
              label={fixture ? t('expert.editor.teamWin', { team: fixture.homeTeam }) : t('outcome.homeWin')}
              value={shown(values.homeWin)}
            />
            <Line label={t('outcome.draw')} value={shown(values.draw)} />
            <Line
              label={fixture ? t('expert.editor.teamWin', { team: fixture.awayTeam }) : t('outcome.awayWin')}
              value={shown(values.awayWin)}
            />
          </div>
          <p className="mt-2 text-xs text-secondary-400">
            {conviction
              // Said as the expert's own claim. It is not an accuracy: nothing here has been scored
              // against a result.
              ? <Emphasised sentence={convictionSentence} value={conviction} className="num font-semibold text-secondary-200" />
              : t('expert.preview.noConviction')}
          </p>
        </div>

        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-secondary-400">{t('expert.editor.otherMarkets')}</h4>

          {values.bttsEnabled ? (
            <TwoWay market="btts" sides={[[t('expert.editor.bttsYes'), values.bttsYes], [t('expert.editor.bttsNo'), values.bttsNo]]} />
          ) : <NotPublished market="btts" />}

          {values.over25Enabled ? (
            <TwoWay
              market="over25"
              sides={[
                [t('expert.editor.overGoals', { line: goalLine(2.5) }), values.over25],
                [t('expert.editor.underGoals', { line: goalLine(2.5) }), values.under25],
              ]}
            />
          ) : <NotPublished market="over25" />}

          {values.over35Enabled ? (
            <TwoWay
              market="over35"
              sides={[
                [t('expert.editor.overGoals', { line: goalLine(3.5) }), values.over35],
                [t('expert.editor.underGoals', { line: goalLine(3.5) }), values.under35],
              ]}
            />
          ) : <NotPublished market="over35" />}
        </div>

        {values.reasoning.trim() && (
          <div>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-secondary-400">{t('expert.editor.reasoningLabel')}</h4>
            {/* The expert's own words, shown back exactly as they wrote them. */}
            <p className="whitespace-pre-wrap break-words text-sm text-secondary-200">{values.reasoning.trim()}</p>
          </div>
        )}

        {!payload && (
          <p className="text-xs text-warning-200">
            {t('expert.preview.needsAttention')}
          </p>
        )}
      </div>
    </section>
  )
}

export default PublishPreview
