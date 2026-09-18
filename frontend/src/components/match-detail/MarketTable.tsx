import React from 'react'
import type { BriefMarketKey, BriefSourceBlock, BriefSourceKey, MatchBrief, MatchPredictions } from '@/types'
import { ConfidenceBadge } from '@/components/ui/Badge'
import {
  formatPercent, isPublished, marketLead, publishedSide, PublishedSide, UNAVAILABLE_TEXT,
} from '@/components/ui/probability'
import { marketBlock, missingReasonLabel } from '@/utils/brief'
import { confidenceBasis } from './evidence'

/**
 * One source's markets, market by market.
 *
 * Unchanged in substance from the page this was lifted out of, and deliberately so: the numbers are
 * still read from the mapped prediction, so there is exactly ONE place in the app that decides what
 * a probability looks like on screen. The brief is used only for what it alone knows — WHY a market
 * is absent, and whether the source published a confidence — which is added beside the existing
 * "Unavailable", never in place of it.
 *
 * A market the source did not supply renders as unavailable. Never 0%, never the complement of the
 * other half, never borrowed from the other source.
 */

const MarketRow: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex justify-between items-center gap-4">
    <span className="text-secondary-400">{label}</span>
    <div className="flex items-center space-x-2 text-right">{children}</div>
  </div>
)

/**
 * A market this source did not publish.
 *
 * The reason chip comes from the brief when there is one: "Unavailable" alone cannot tell a reader
 * whether the market is unknown or merely absent from the forecast we hold, and those are different
 * facts. The full sentence for each reason is in the evidence panel at the top of the page.
 */
const Unavailable: React.FC<{ block?: BriefSourceBlock | null }> = ({ block = null }) => {
  const reason = block && !block.available ? missingReasonLabel(block.reason) : null
  return (
    <span className="text-right">
      <span className="text-xs text-secondary-500">{UNAVAILABLE_TEXT}</span>
      {reason && <span className="block text-[11px] leading-4 text-secondary-500">{reason}</span>}
    </span>
  )
}

/** "Over 2.5 (Over 58% / Under unavailable)" — every half labelled, none inferred from the other. */
const TwoWayMarket: React.FC<{
  sides: [PublishedSide | null, PublishedSide | null]
  lead: { known: PublishedSide[]; leader: PublishedSide | null }
}> = ({ sides, lead }) => (
  <span className="text-white font-medium">
    {lead.leader ? lead.leader.label : lead.known[0].label}
    <span className="text-secondary-400 font-normal">
      {' ('}
      {sides.map((side, index) => (
        <React.Fragment key={index}>
          {index > 0 && ' / '}
          {side ? `${side.label} ${formatPercent(side.value)}` : UNAVAILABLE_TEXT.toLowerCase()}
        </React.Fragment>
      ))}
      {')'}
    </span>
    {!lead.leader && <span className="text-secondary-500 font-normal"> — one side only</span>}
  </span>
)

const MarketTable: React.FC<{
  prediction: MatchPredictions
  /** The full brief, when the payload carried one. Supplies the reason a market is absent. */
  brief?: MatchBrief | null
  /** Which side of the brief to read. */
  source: BriefSourceKey
}> = ({ prediction, brief = null, source }) => {
  const { bothTeamsToScore, totalGoals, correctScore } = prediction
  const block = (key: BriefMarketKey): BriefSourceBlock | null => marketBlock(brief, key, source)

  /**
   * Value-based, NOT flag-based: a prediction with no `markets` object at all used to slip past
   * `markets?.matchResult === false` and render a 0% / 0% / 0% match result. The market exists only
   * if the probabilities themselves exist, and an explicit `matchResult: false` also hides it.
   */
  const outcome = prediction.outcome && prediction.markets?.matchResult !== false ? prediction.outcome : null
  const best = outcome ? Math.max(outcome.homeWin, outcome.draw, outcome.awayWin) : null
  const bestLabel = outcome && best !== null
    ? (best === outcome.homeWin ? 'Home Win' : best === outcome.draw ? 'Draw' : 'Away Win')
    : null

  const bttsYes = publishedSide('Yes', bothTeamsToScore?.yes)
  const bttsNo = publishedSide('No', bothTeamsToScore?.no)
  const bttsLead = marketLead({ label: 'Yes', value: bothTeamsToScore?.yes }, { label: 'No', value: bothTeamsToScore?.no })

  const over25 = publishedSide('Over 2.5', totalGoals?.over25)
  const under25 = publishedSide('Under 2.5', totalGoals?.under25)
  const lead25 = marketLead({ label: 'Over 2.5', value: totalGoals?.over25 }, { label: 'Under 2.5', value: totalGoals?.under25 })

  const over35 = publishedSide('Over 3.5', totalGoals?.over35)
  const under35 = publishedSide('Under 3.5', totalGoals?.under35)
  const lead35 = marketLead({ label: 'Over 3.5', value: totalGoals?.over35 }, { label: 'Under 3.5', value: totalGoals?.under35 })

  const outcomeBlock = block('match_result')
  const bttsBlock = block('btts')
  const over25Block = block('over_under_25')
  const over35Block = block('over_under_35')
  const scoreBlock = block('exact_score')

  return (
    <div className="space-y-4">
      <MarketRow label="Match Outcome">
        {outcome && bestLabel !== null && best !== null ? (
          <>
            <span className="text-white font-medium">{bestLabel} <span className="text-secondary-400 font-normal">({formatPercent(best)})</span></span>
            <ConfidenceBadge level={outcome.confidence} basis={confidenceBasis(outcomeBlock, prediction)} />
          </>
        ) : <Unavailable block={outcomeBlock} />}
      </MarketRow>
      {outcome ? (
        <div className="grid grid-cols-3 gap-2 text-center text-sm">
          <div className="rounded bg-dark-800 py-2"><div className="text-secondary-400 text-xs">Home</div><div className="text-white">{formatPercent(outcome.homeWin)}</div></div>
          <div className="rounded bg-dark-800 py-2"><div className="text-secondary-400 text-xs">Draw</div><div className="text-white">{formatPercent(outcome.draw)}</div></div>
          <div className="rounded bg-dark-800 py-2"><div className="text-secondary-400 text-xs">Away</div><div className="text-white">{formatPercent(outcome.awayWin)}</div></div>
        </div>
      ) : (
        <p className="rounded bg-dark-800 px-3 py-2 text-xs text-secondary-500" data-testid="outcome-unavailable">
          {/* The brief's own sentence when there is one: it says WHY, which "unavailable" cannot. */}
          {outcomeBlock?.detail ?? 'This source published no match-result (1X2) market for this fixture.'}
        </p>
      )}
      <MarketRow label="Both Teams to Score">
        {bothTeamsToScore && bttsLead.known.length > 0 ? (
          <>
            <TwoWayMarket sides={[bttsYes, bttsNo]} lead={bttsLead} />
            <ConfidenceBadge level={bothTeamsToScore.confidence} basis={confidenceBasis(bttsBlock, prediction)} />
          </>
        ) : <Unavailable block={bttsBlock} />}
      </MarketRow>
      <MarketRow label="Over/Under 2.5 Goals">
        {totalGoals && lead25.known.length > 0 ? (
          <>
            <TwoWayMarket sides={[over25, under25]} lead={lead25} />
            <ConfidenceBadge level={totalGoals.confidence} basis={confidenceBasis(over25Block, prediction)} />
          </>
        ) : <Unavailable block={over25Block} />}
      </MarketRow>
      <MarketRow label="Over/Under 3.5 Goals">
        {totalGoals && lead35.known.length > 0 ? (
          <TwoWayMarket sides={[over35, under35]} lead={lead35} />
        ) : <Unavailable block={over35Block} />}
      </MarketRow>
      <MarketRow label="Most Likely Score">
        {correctScore ? (
          <span className="text-white font-medium" data-testid="correct-score">
            {correctScore.mostLikely} <span className="text-secondary-400 font-normal">({formatPercent(correctScore.probability)})</span>
            {/*
              The remainder the provider assigned to every scoreline it did not list. Without it a
              short list of scorelines reads as near-certainty; it is never folded into the listed ones.
            */}
            {isPublished(prediction.exactScoreOther) && (
              <span className="text-secondary-400 font-normal"> · other scorelines {formatPercent(prediction.exactScoreOther)}</span>
            )}
          </span>
        ) : <Unavailable block={scoreBlock} />}
      </MarketRow>
    </div>
  )
}

export default MarketTable
