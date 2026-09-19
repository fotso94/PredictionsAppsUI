import React from 'react'
import type { BriefSourceKey, MatchBrief, MatchPredictions, PredictionMarkets } from '@/types'
import Card from '@/components/ui/Card'
import SourceMarker from '@/components/ui/SourceMarker'
import type { ForecastAvailability } from '@/components/ui/forecastStatus'
import { marketLabel } from '@/utils/brief'
import { providerLabel } from '@/utils/predictionLabels'
import DataStateNotice from './DataStateNotice'
import MissingDataList from './MissingDataList'
import { ACCURACY_STATEMENT, groupMissing } from './evidence'

/**
 * The evidence panel: what is known about this match, what is missing, and why.
 *
 * It answers, before any number is read, the four questions a reader otherwise has to guess at:
 * who published anything at all, which markets they covered, how current it is, and — for every
 * gap — whether the gap means "unknown" or only "not refreshed lately".
 *
 * Nothing here is computed from the numbers. The headline, the missing-data sentences and the
 * confidence and accuracy statements are all the backend's own words; this file arranges them.
 *
 * It degrades on purpose: a payload with no brief (the legacy API-Football source) still gets the
 * coverage row and the single data-state statement, built from the mapped prediction alone.
 */

/** Legacy coverage, for a payload that carries no brief. Same wording as the brief's own labels. */
const LEGACY_MARKETS: Array<[keyof PredictionMarkets, string]> = [
  ['matchResult', 'Match result'],
  ['btts', 'Both teams to score'],
  ['overUnder25', 'Total goals 2.5'],
  ['overUnder35', 'Total goals 3.5'],
  ['exactScore', 'Exact score'],
]

const legacyMarketNames = (prediction: MatchPredictions | null | undefined): string[] => {
  if (!prediction) return []
  const markets = prediction.markets
  if (!markets) return []
  return LEGACY_MARKETS.filter(([key]) => markets[key]).map(([, label]) => label)
}

const CoverageRow: React.FC<{
  source: BriefSourceKey
  present: boolean
  markets: string[]
  /** How this source is tied to the fixture: provider and link confidence, or publication time. */
  note: string | null
  /**
   * The whole statement for an absent source — the backend's own sentence when it gave one.
   *
   * It used to be a short phrase here and the full sentence again in the list below and a third
   * time in a strip further down the page, so "no expert has published a prediction for this
   * fixture" reached the reader four times on one screen (twice in text, twice more to a screen
   * reader through a marker's description). Absence is worth exactly one sentence, and this row —
   * the one that is about who published what — is where it belongs.
   */
  absentText: string
}> = ({ source, present, markets, note, absentText }) => (
  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1" data-testid={`brief-coverage-${source}`}>
    <SourceMarker source={source} state={present ? 'available' : 'unavailable'} />
    <div className="min-w-0 flex-1 text-xs">
      {present ? (
        <span className="text-secondary-200">
          {/* A source can be present without the payload listing its markets; that is not "nothing". */}
          {markets.length > 0 ? markets.join(' · ') : 'Published for this fixture; the markets covered were not listed.'}
        </span>
      ) : (
        <span className="text-secondary-300">{absentText}</span>
      )}
      {note && <span className="block text-secondary-500">{note}</span>}
    </div>
  </div>
)

const EvidenceBrief: React.FC<{
  brief?: MatchBrief | null
  forecast: MatchPredictions | null
  experts: MatchPredictions[]
  availability: ForecastAvailability | null
  className?: string
}> = ({ brief = null, forecast, experts, availability, className }) => {
  const groups = groupMissing(brief?.missing)
  /**
   * A source-scoped gap ("nothing at all from this source") is stated by the coverage row above;
   * the list below is only about MARKETS and why each one is absent. Splitting them this way is
   * what removed the repetition: before, a wholly-absent source was announced by the coverage row,
   * then again in full by a row of this list, then a third time by a strip further down the page.
   */
  const marketGroups = groups.filter(group => !group.wholeSource)
  const sourceGap = (source: BriefSourceKey): string | null =>
    groups.find(group => group.wholeSource && group.source === source)?.detail ?? null

  const headline = brief?.headline ?? null
  // The headline is the first available summary, or the first missing-data sentence when nothing is
  // available — in which case it is about to be printed again, in full, in the list below.
  const headlineIsRepeated = headline !== null
    && (marketGroups.some(group => group.detail === headline) || headline === sourceGap('model') || headline === sourceGap('expert'))

  const modelPresence = brief?.known.sources.find(entry => entry.source === 'model') ?? null
  const expertPresence = brief?.known.sources.find(entry => entry.source === 'expert') ?? null

  const modelPresent = brief ? Boolean(modelPresence?.present) : forecast !== null
  const expertPresent = brief ? Boolean(expertPresence?.present) : experts.length > 0

  const modelMarkets = brief ? (brief.known.model_markets ?? []).map(marketLabel) : legacyMarketNames(forecast)
  const expertMarkets = brief ? (brief.known.expert_markets ?? []).map(marketLabel) : legacyMarketNames(experts[0])

  const modelNote = modelPresent
    ? [
      providerLabel(modelPresence?.provider ?? forecast?.providerName ?? null),
      modelPresence?.match_confidence ? `fixture link: ${modelPresence.match_confidence}` : null,
    ].filter(Boolean).join(' · ')
    : null
  const expertNote = expertPresent
    ? (() => {
      const published = expertPresence?.published_at ?? experts[0]?.publishedAt ?? null
      const count = experts.length > 1 ? `${experts.length} experts published` : null
      return [count, published ? `published ${new Date(published).toLocaleString()}` : null]
        .filter(Boolean).join(' · ') || null
    })()
    : null

  return (
    <Card className={className} data-testid="match-brief">
      <Card.Body className="space-y-4 sm:space-y-5">
        <div className="space-y-2">
          <h2 className="text-base font-semibold text-white">What this page knows about the match</h2>
          {headline && !headlineIsRepeated && (
            <p className="text-sm text-secondary-200" data-testid="brief-headline">{headline}</p>
          )}
        </div>

        <div className="space-y-2">
          {/*
            The backend's own sentence for a source with nothing here, shown once. What follows
            below is about MARKETS: which ones are missing from a source that did publish, and
            whether each gap means "unknown" or only "not refreshed lately".
          */}
          <CoverageRow
            source="model"
            present={modelPresent}
            markets={modelMarkets}
            note={modelNote}
            absentText={sourceGap('model') ?? 'No model forecast has been retrieved for this fixture.'}
          />
          <CoverageRow
            source="expert"
            present={expertPresent}
            markets={expertMarkets}
            /* What would change this, for the one source a reader can actually wait on. Never a
               promise about when: experts publish directly, and nobody schedules them. */
            note={expertNote ?? (expertPresent ? null : 'Experts publish directly, so one appears here as soon as it is published.')}
            absentText={sourceGap('expert') ?? 'No expert has published a prediction for this fixture.'}
          />
        </div>

        <DataStateNotice
          freshness={brief?.freshness ?? null}
          forecast={forecast}
          availability={availability}
          className="border-t border-dark-700 pt-4"
        />

        {brief && marketGroups.length > 0 && (
          <MissingDataList groups={marketGroups} className="border-t border-dark-700 pt-4" />
        )}
        {/*
          The positive statement, and ONLY when it is true of every source. It used to come from
          the list's own empty state, which could not tell "no market is missing" from "no market
          is missing because a source published nothing at all" — and printed the reassurance in
          the second case too.
        */}
        {brief && groups.length === 0 && (
          <p className="border-t border-dark-700 pt-4 text-sm text-secondary-300" data-testid="brief-missing-none">
            Both sources published every market they offer for this fixture.
          </p>
        )}

        {/*
          Probability is not accuracy, and it is not a claim about this source's record. Said once,
          plainly, at the top of the page — the per-source confidence statements sit beside the
          numbers they qualify.
        */}
        <p className="border-t border-dark-700 pt-4 text-xs text-secondary-400" data-testid="brief-accuracy">
          {brief?.reliability.detail ?? ACCURACY_STATEMENT}
        </p>
      </Card.Body>
    </Card>
  )
}

export default EvidenceBrief
