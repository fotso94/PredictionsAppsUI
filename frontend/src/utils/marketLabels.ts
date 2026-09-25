/**
 * Words for markets and selections, in the reader's language.
 *
 * Team names are the provider's and are never translated; everything else — "Draw", "Over 2.5",
 * "or", "1st half" — is a word of ours and comes from the catalogue. A selection is described with
 * the clubs in it ("Bulgaria or draw"), never with a code ("1X"), because the code is the one thing a
 * reader who has never placed a bet cannot be expected to know.
 */

import type { TranslateFn } from '@/i18n'
import type { MarketGroupId, MarketId, MarketPeriod } from '@/types/markets'

export interface SelectionWords {
  market_id: MarketId
  outcome: string
  line: number | null
  period?: MarketPeriod
}

const lineText = (line: number | null): string => (line === null ? '' : `${line}`)

export function groupTitle(t: TranslateFn, group: MarketGroupId): string {
  switch (group) {
    case 'outcome': return t('selections.group.outcome')
    case 'goals': return t('selections.group.goals')
    case 'first_half': return t('selections.group.firstHalf')
    case 'team': return t('selections.group.team')
    case 'exact_score': return t('selections.group.exactScore')
  }
}

export function marketTitle(t: TranslateFn, marketId: MarketId, line: number | null, home: string, away: string): string {
  switch (marketId) {
    case 'match_result': return t('selections.market.matchResult')
    case 'double_chance': return t('selections.market.doubleChance')
    case 'draw_no_bet': return t('selections.market.drawNoBet')
    case 'total_goals': return t('selections.market.totalGoals', { line: lineText(line) })
    case 'home_team_goals': return t('selections.market.teamGoals', { team: home, line: lineText(line) })
    case 'away_team_goals': return t('selections.market.teamGoals', { team: away, line: lineText(line) })
    case 'both_teams_score': return t('selections.market.bothTeamsScore')
    case 'first_half_result': return t('selections.market.firstHalfResult')
    case 'team_to_score_first': return t('selections.market.teamToScoreFirst')
    case 'exact_score': return t('selections.market.exactScore')
  }
}

/** "Bulgaria", "Draw", "Bulgaria or draw", "Over 2.5", "Yes", "1-0", ... */
export function outcomeLabel(t: TranslateFn, words: SelectionWords, home: string, away: string): string {
  const { market_id, outcome, line } = words
  switch (market_id) {
    case 'match_result':
    case 'first_half_result':
      return outcome === 'home' ? home : outcome === 'away' ? away : t('selections.outcome.draw')
    case 'double_chance':
      if (outcome === '1x') return t('selections.outcome.orDraw', { team: home })
      if (outcome === 'x2') return t('selections.outcome.orDraw', { team: away })
      return t('selections.outcome.either', { home, away })
    case 'draw_no_bet':
      return t('selections.outcome.drawNoBet', { team: outcome === 'home' ? home : away })
    case 'total_goals':
    case 'home_team_goals':
    case 'away_team_goals':
      return outcome === 'over'
        ? t('selections.outcome.over', { line: lineText(line) })
        : t('selections.outcome.under', { line: lineText(line) })
    case 'both_teams_score':
      return outcome === 'yes' ? t('selections.outcome.yes') : t('selections.outcome.no')
    case 'team_to_score_first':
      return outcome === 'home' ? home : outcome === 'away' ? away : t('selections.outcome.neither')
    case 'exact_score':
      return outcome
  }
}

/** The whole description of one leg on a slip: "Match result: Bulgaria" / "Total goals: Under 2.5". */
export function selectionSentence(t: TranslateFn, words: SelectionWords, home: string, away: string): string {
  const market = marketTitle(t, words.market_id, words.line, home, away)
  const outcome = outcomeLabel(t, words, home, away)
  const period = words.period === 'first_half' && words.market_id !== 'first_half_result' ? ` (${t('selections.period.firstHalf')})` : ''
  return `${market}: ${outcome}${period}`
}

export function periodLabel(t: TranslateFn, period: MarketPeriod): string {
  return period === 'first_half' ? t('selections.period.firstHalf') : t('selections.period.regulation')
}

export function stateLabel(t: TranslateFn, state: 'pending' | 'won' | 'lost' | 'void' | 'unresolved' | 'draft'): string {
  switch (state) {
    case 'won': return t('selections.state.won')
    case 'lost': return t('selections.state.lost')
    case 'void': return t('selections.state.void')
    case 'unresolved': return t('selections.state.unresolved')
    case 'draft': return t('selections.state.draft')
    default: return t('selections.state.pending')
  }
}
