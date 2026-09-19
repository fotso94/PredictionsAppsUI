import React, { useId } from 'react'
import CompetitionChip from '@/components/ui/CompetitionChip'
import type { CompetitionOption } from './fixtureGrouping'
import {
  MARKET_OPTIONS, SOURCE_OPTIONS, STATUS_OPTIONS, WorkspaceState, optionDefinition, optionLabel,
  toggleValue,
} from './workspaceState'
import { marketPeriodNote } from '@/utils/brief'
import { useT } from '@/i18n/react'

/**
 * The filter controls themselves — the body of the bottom sheet.
 *
 * Presentational: it renders the state it is handed and reports the state the reader asked for.
 * It fetches nothing, and it never decides what a filter means.
 *
 * Every control says what it does to the LIST, not what it claims about a prediction. "Has an
 * expert prediction" is a fact the payload states. There is deliberately no confidence control:
 * the level attached to a 1X2 block is derived from the size of the biggest probability, so a
 * "high confidence only" filter would dress that derivation up as a judgement somebody made — and
 * no part of this application has ever scored a prediction against a result.
 *
 * Competitions appear here as well as in the always-visible row above the list, because the row
 * scrolls sideways on a phone and a competition that has scrolled out of sight is one the reader
 * cannot reach from there.
 */

export interface MatchFilterControlsProps {
  state: WorkspaceState
  onChange: (next: WorkspaceState) => void
  /** Every competition on the chosen date, with its fixture count. */
  competitions: CompetitionOption[]
}

const Section: React.FC<{ title: string; hint?: string; children: React.ReactNode }> = ({ title, hint, children }) => {
  const id = useId()
  return (
    <section aria-labelledby={id}>
      <h3 id={id} className="text-sm font-medium text-white">{title}</h3>
      {hint && <p className="mt-0.5 text-xs text-secondary-400">{hint}</p>}
      <div className="mt-2">{children}</div>
    </section>
  )
}

const MatchFilterControls: React.FC<MatchFilterControlsProps> = ({ state, onChange, competitions }) => {
  const statusName = useId()
  const t = useT()

  return (
    <div className="space-y-5" data-testid="match-filter-controls">
      <Section title={t('filters.show')} hint={t('filters.showHint')}>
        {/* Radios, not checkboxes: these three are alternatives, and a keyboard user gets the
            arrow-key behaviour a radio group is supposed to have. */}
        <div role="radiogroup" aria-label={t('filters.whichFixtures')} className="space-y-1">
          {STATUS_OPTIONS.map(option => (
            <label key={option.value} className="tap-target-row flex cursor-pointer items-center gap-2 rounded-lg px-1">
              <input
                type="radio"
                name={statusName}
                value={option.value}
                checked={state.status === option.value}
                onChange={() => onChange({ ...state, status: option.value })}
                className="focus-ring h-4 w-4 border-dark-600 bg-dark-800 text-primary-600"
              />
              <span className="text-sm text-secondary-200">{optionLabel(option)}</span>
            </label>
          ))}
        </div>
      </Section>

      <Section
        title={t('filters.competitions')}
        hint={t(competitions.length === 0 ? 'filters.competitionsHintEmpty' : 'filters.competitionsHint')}
      >
        <div className="flex flex-wrap gap-1.5">
          {competitions.map(competition => (
            <CompetitionChip
              key={competition.id}
              name={competition.name}
              logo={competition.logo}
              country={competition.country}
              count={competition.count}
              size="sm"
              selected={state.competitions.includes(competition.id)}
              onToggle={next => onChange({
                ...state,
                competitions: toggleValue(state.competitions, competition.id, next),
              })}
            />
          ))}
        </div>
      </Section>

      <Section
        title={t('filters.markets')}
        hint={t('filters.marketsHint')}
      >
        <div className="space-y-1">
          {MARKET_OPTIONS.map(option => (
            <label key={option.value} className="tap-target-row flex cursor-pointer items-start gap-2 rounded-lg px-1 py-1">
              <input
                type="checkbox"
                checked={state.markets.includes(option.value)}
                onChange={event => onChange({
                  ...state,
                  markets: toggleValue(state.markets, option.value, event.target.checked),
                })}
                className="focus-ring mt-0.5 h-4 w-4 rounded border-dark-600 bg-dark-800 text-primary-600"
              />
              <span className="min-w-0">
                <span className="block text-sm text-secondary-200">{optionLabel(option)}</span>
                {/* What the market counts. The PERIOD it covers is stated once for the whole
                    group below, because no source publishes one and saying so four times would
                    read as four separate problems. */}
                <span className="block text-xs text-secondary-400">{optionDefinition(option)}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-secondary-400" data-testid="market-period-note">
          {marketPeriodNote()}
        </p>
      </Section>

      <Section title={t('filters.sources')} hint={t('filters.sourcesHint')}>
        <div className="space-y-1">
          {SOURCE_OPTIONS.map(option => (
            <label key={option.value} className="tap-target-row flex cursor-pointer items-center gap-2 rounded-lg px-1">
              <input
                type="checkbox"
                checked={state.sources.includes(option.value)}
                onChange={event => onChange({
                  ...state,
                  sources: toggleValue(state.sources, option.value, event.target.checked),
                })}
                className="focus-ring h-4 w-4 rounded border-dark-600 bg-dark-800 text-primary-600"
              />
              <span className="text-sm text-secondary-200">{optionLabel(option)}</span>
            </label>
          ))}
        </div>
      </Section>
    </div>
  )
}

export default MatchFilterControls
