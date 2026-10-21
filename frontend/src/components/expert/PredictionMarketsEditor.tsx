import React from 'react'
import clsx from 'clsx'
import PercentField from './PercentField'
import {
  ComposerIssueKey, ComposerMessage, ComposerValidation, ComposerValues, OptionalMarketKey,
  pairAdjustment, PairState, REASONING_MAX,
} from './composer'
import { composerText, goalLine, hundredPercent, optionalMarketLabel } from './composerText'
import { formatPercentTotal, formatWholeNumber } from './percent'
import { currentLocale } from '@/i18n'
import type { MessageKey } from '@/i18n'
import { useLocale } from '@/i18n/react'
import Emphasised from '@/i18n/Emphasised'

/**
 * The markets an expert is publishing, and only those.
 *
 * Match result is always part of a prediction, because the API requires it. Everything else is a
 * tick box that starts OFF. An untouched box means the market is not sent, the API stores null, and
 * every reader shows it as unavailable — which is a different statement from 0%, and the only
 * honest one when the expert offered no view.
 *
 * Complementary pairs are checked as they are typed and the running total is always on screen, so
 * "these must total 100%" is something the expert sees in the form rather than something the API
 * tells them after they press publish.
 *
 * The editor never proposes a number. The model forecast sits beside it as evidence to read; not
 * one of its figures is copied into a field here, and there is no "start from the model" control.
 *
 * IN THE READER'S LANGUAGE. Every label, hint, total and error comes from the catalogue at render
 * time (`expert.editor.*`, `expert.validation.*`, and `market.*` / `outcome.*` from core), and
 * every figure is formatted for the reader's locale — « 101 % au total », « Retirez 1,01. » — while
 * the English is the exact text this component always printed. Team names are the provider's.
 */
export interface PredictionMarketsEditorProps {
  values: ComposerValues
  onChange: (next: ComposerValues) => void
  validation: ComposerValidation
  /** Errors stay hidden until the expert tries to move on, so a half-typed field is not scolded. */
  showErrors: boolean
  homeTeam?: string | null
  awayTeam?: string | null
  /** Unique per editor instance — several can be open at once in the predictions list. */
  idPrefix: string
  /**
   * Markets already published on an existing prediction. They can be re-valued but not removed:
   * the update endpoint ignores a null for an optional market, so unticking would silently keep the
   * old number. Saying so is better than a box that does nothing.
   */
  lockedMarkets?: ReadonlySet<OptionalMarketKey>
  disabled?: boolean
}

/**
 * The running total of a market's sides — the only place the total rule is stated.
 *
 * It is on screen from the first keystroke rather than appearing as an error afterwards, which is
 * the point: the expert watches the total approach 100 instead of being told, after pressing
 * publish, that the API refused it. Once errors are being shown it turns from a caution into a
 * problem, and it is announced, but it is never printed twice.
 *
 * An unbalanced total says how far off it is as well as that it is off. The three match-result
 * outcomes have to reach exactly 100, and "33% + 33% + 33% is wrong" leaves the expert to work
 * out that a point is missing; "Add 1." does not. Which box takes it is theirs to decide, so the
 * hint never names one.
 *
 * The total is the sum the API will hold, not the sum of the digits on screen (see `checkPair`),
 * so it is printed to the same two decimals: a total of 99.99 must not round to "100%" beside a
 * sentence saying it is short.
 */
const PairTotal: React.FC<{ state: PairState; rule: MessageKey; error?: ComposerMessage | null }> = ({ state, rule, error }) => {
  const { t } = useLocale()
  const ruleText = t(rule, { hundred: hundredPercent() })
  if (state.percent === null) {
    return <p className="mt-2 text-xs text-secondary-400">{ruleText}</p>
  }
  // One sentence per state, with the figure inside it, so each language puts the figure where it
  // goes. The figure is then picked out of the rendered sentence to be drawn in bold.
  const figure = formatPercentTotal(state.percent, currentLocale())
  const sentence = state.balanced
    ? t('expert.editor.totalBalanced', { percent: figure })
    : t('expert.editor.totalUnbalanced', { percent: figure, rule: ruleText })
  const adjustment = state.balanced ? null : pairAdjustment(state.gap)
  return (
    <p
      className={clsx('mt-2 text-xs', state.balanced ? 'text-success-300' : error ? 'text-danger-300' : 'text-warning-200')}
      role={error ? 'alert' : undefined}
    >
      <Emphasised sentence={sentence} value={figure} className="num font-semibold" />
      {adjustment ? ` ${composerText(adjustment)}` : ''}
    </p>
  )
}

/** One opt-in market: the tick box, and its fields only once it is ticked. */
const MarketSection: React.FC<{
  market: OptionalMarketKey
  enabled: boolean
  locked: boolean
  onToggle: (next: boolean) => void
  disabled: boolean
  idPrefix: string
  children: React.ReactNode
}> = ({ market, enabled, locked, onToggle, disabled, idPrefix, children }) => {
  const { t } = useLocale()
  const boxId = `${idPrefix}-${market}-enabled`
  const label = optionalMarketLabel(market)
  return (
    <fieldset className="rounded-lg border border-dark-700 bg-dark-900/60 p-4">
      <legend className="sr-only">{label}</legend>
      <div className="flex items-start gap-3">
        <input
          id={boxId}
          type="checkbox"
          checked={enabled}
          disabled={disabled || locked}
          onChange={event => onToggle(event.target.checked)}
          className="focus-ring mt-0.5 h-5 w-5 flex-shrink-0 rounded border-dark-600 bg-dark-800 text-primary-500 disabled:cursor-not-allowed disabled:opacity-60"
        />
        <div className="min-w-0">
          <label htmlFor={boxId} className="block text-sm font-medium text-white">
            {label}
          </label>
          <p className="mt-0.5 text-xs text-secondary-400">
            {locked
              ? t('expert.editor.marketLocked')
              : enabled
                ? t('expert.editor.marketOn', { hundred: hundredPercent() })
                : t('expert.editor.marketOff')}
          </p>
        </div>
      </div>
      {enabled && <div className="mt-4">{children}</div>}
    </fieldset>
  )
}

const PredictionMarketsEditor: React.FC<PredictionMarketsEditorProps> = ({
  values, onChange, validation, showErrors, homeTeam, awayTeam, idPrefix, lockedMarkets, disabled = false,
}) => {
  // The subscription: a change of language re-renders this, and everything below reads the new
  // catalogue and locale as it renders.
  const { t } = useLocale()
  const locale = currentLocale()

  const set = <K extends keyof ComposerValues>(key: K, value: ComposerValues[K]) => {
    onChange({ ...values, [key]: value })
  }

  /** The error under one field, as a sentence, only once errors are being shown. */
  const errorFor = (key: ComposerIssueKey): string | null => {
    const message = showErrors ? validation.errors[key] : undefined
    return message ? composerText(message) : null
  }
  /** The same error kept as a message, for the totals, which use it for colour and role only. */
  const issueFor = (key: ComposerIssueKey): ComposerMessage | null =>
    showErrors ? validation.errors[key] ?? null : null

  const locked = (market: OptionalMarketKey) => Boolean(lockedMarkets?.has(market))

  const homeLabel = homeTeam ? t('expert.editor.teamWin', { team: homeTeam }) : t('outcome.homeWin')
  const awayLabel = awayTeam ? t('expert.editor.teamWin', { team: awayTeam }) : t('outcome.awayWin')

  // The count is drawn in the number style; both figures are ungrouped, so English still says 2000.
  const reasoningCount = formatWholeNumber(values.reasoning.length, locale)
  const reasoningSentence = t('expert.editor.reasoningCount', {
    count: reasoningCount,
    max: formatWholeNumber(REASONING_MAX, locale),
  })

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------------ match result */}
      <fieldset className="rounded-lg border border-dark-700 bg-dark-900/60 p-4">
        <legend className="px-1 text-sm font-semibold text-white">{t('market.matchResult')}</legend>
        <p className="mb-4 text-xs text-secondary-400">
          {t('expert.editor.matchResultIntro')}
        </p>
        {/* One column on a phone: three number fields side by side at 390px cannot show a team
            name, and a grid that never wraps is how a page starts scrolling sideways. */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <PercentField
            id={`${idPrefix}-home`}
            label={homeLabel}
            value={values.homeWin}
            onChange={next => set('homeWin', next)}
            error={errorFor('homeWin')}
            disabled={disabled}
            required
          />
          <PercentField
            id={`${idPrefix}-draw`}
            label={t('outcome.draw')}
            value={values.draw}
            onChange={next => set('draw', next)}
            error={errorFor('draw')}
            disabled={disabled}
            required
          />
          <PercentField
            id={`${idPrefix}-away`}
            label={awayLabel}
            value={values.awayWin}
            onChange={next => set('awayWin', next)}
            error={errorFor('awayWin')}
            disabled={disabled}
            required
          />
        </div>
        <PairTotal state={validation.outcome} rule="expert.editor.ruleOutcomes" error={issueFor('outcomeTotal')} />

        <div className="mt-4 max-w-xs">
          <PercentField
            id={`${idPrefix}-conviction`}
            label={t('expert.editor.convictionLabel')}
            value={values.conviction}
            onChange={next => set('conviction', next)}
            error={errorFor('conviction')}
            hint={t('expert.editor.convictionHint')}
            disabled={disabled}
          />
        </div>
      </fieldset>

      {/* ------------------------------------------------------------------ opt-in markets */}
      <div className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-white">{t('expert.editor.otherMarkets')}</h3>
          <p className="mt-1 text-xs text-secondary-400">
            {t('expert.editor.otherMarketsIntro')}
          </p>
        </div>

        <MarketSection
          market="btts"
          enabled={values.bttsEnabled}
          locked={locked('btts')}
          onToggle={next => set('bttsEnabled', next)}
          disabled={disabled}
          idPrefix={idPrefix}
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <PercentField
              id={`${idPrefix}-btts-yes`}
              label={t('expert.editor.bttsYes')}
              value={values.bttsYes}
              onChange={next => set('bttsYes', next)}
              error={errorFor('bttsYes')}
              disabled={disabled}
              required
            />
            <PercentField
              id={`${idPrefix}-btts-no`}
              label={t('expert.editor.bttsNo')}
              value={values.bttsNo}
              onChange={next => set('bttsNo', next)}
              error={errorFor('bttsNo')}
              disabled={disabled}
              required
            />
          </div>
          <PairTotal state={validation.btts} rule="expert.editor.ruleSides" error={issueFor('bttsTotal')} />
            <div className="mt-4 max-w-xs">
            <PercentField
              id={`${idPrefix}-btts-conviction`}
              label={t('expert.editor.bttsConviction')}
              value={values.bttsConviction}
              onChange={next => set('bttsConviction', next)}
              error={errorFor('bttsConviction')}
              disabled={disabled}
            />
          </div>
        </MarketSection>

        <MarketSection
          market="over25"
          enabled={values.over25Enabled}
          locked={locked('over25')}
          onToggle={next => set('over25Enabled', next)}
          disabled={disabled}
          idPrefix={idPrefix}
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <PercentField
              id={`${idPrefix}-over25`}
              label={t('expert.editor.overGoals', { line: goalLine(2.5) })}
              value={values.over25}
              onChange={next => set('over25', next)}
              error={errorFor('over25')}
              disabled={disabled}
              required
            />
            <PercentField
              id={`${idPrefix}-under25`}
              label={t('expert.editor.underGoals', { line: goalLine(2.5) })}
              value={values.under25}
              onChange={next => set('under25', next)}
              error={errorFor('under25')}
              disabled={disabled}
              required
            />
          </div>
          <PairTotal state={validation.totals25} rule="expert.editor.ruleOverUnder" error={issueFor('total25')} />
          </MarketSection>

        <MarketSection
          market="over35"
          enabled={values.over35Enabled}
          locked={locked('over35')}
          onToggle={next => set('over35Enabled', next)}
          disabled={disabled}
          idPrefix={idPrefix}
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <PercentField
              id={`${idPrefix}-over35`}
              label={t('expert.editor.overGoals', { line: goalLine(3.5) })}
              value={values.over35}
              onChange={next => set('over35', next)}
              error={errorFor('over35')}
              disabled={disabled}
              required
            />
            <PercentField
              id={`${idPrefix}-under35`}
              label={t('expert.editor.underGoals', { line: goalLine(3.5) })}
              value={values.under35}
              onChange={next => set('under35', next)}
              error={errorFor('under35')}
              disabled={disabled}
              required
            />
          </div>
          <PairTotal state={validation.totals35} rule="expert.editor.ruleOverUnder" error={issueFor('total35')} />
          </MarketSection>

        {(values.over25Enabled || values.over35Enabled) && (
          <div className="max-w-xs">
            <PercentField
              id={`${idPrefix}-totals-conviction`}
              label={t('expert.editor.totalsConviction')}
              value={values.totalsConviction}
              onChange={next => set('totalsConviction', next)}
              error={errorFor('totalsConviction')}
              hint={t('expert.editor.totalsConvictionHint')}
              disabled={disabled}
            />
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ reasoning */}
      <div>
        <label htmlFor={`${idPrefix}-reasoning`} className="form-label">
          {t('expert.editor.reasoningLabel')}
          <span className="ml-1 text-xs font-normal text-secondary-500">{t('expert.field.optional')}</span>
        </label>
        <textarea
          id={`${idPrefix}-reasoning`}
          rows={4}
          value={values.reasoning}
          disabled={disabled}
          onChange={event => onChange({ ...values, reasoning: event.target.value })}
          aria-invalid={errorFor('reasoning') ? true : undefined}
          aria-describedby={`${idPrefix}-reasoning-count`}
          className="form-input w-full disabled:cursor-not-allowed disabled:opacity-60"
          placeholder={t('expert.editor.reasoningPlaceholder')}
        />
        <p id={`${idPrefix}-reasoning-count`} className="mt-1 text-xs text-secondary-400">
          <Emphasised sentence={reasoningSentence} value={reasoningCount} className="num" />
        </p>
        {errorFor('reasoning') && <p className="form-error">{errorFor('reasoning')}</p>}
      </div>
    </div>
  )
}

export default PredictionMarketsEditor
