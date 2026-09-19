import React, { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import { Match } from '@/types'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import SaveMatchButton from '@/components/ui/SaveMatchButton'
import useMatchSaving, { arrivedFromSignIn, resultsListFrom } from '@/components/favourites/useMatchSaving'
import { Badge } from '@/components/ui/Badge'
import ForecastProvenance, { ForecastAnomalies } from '@/components/ui/ForecastProvenance'
import DataFreshness from '@/components/ui/DataFreshness'
import { isPublished } from '@/components/ui/probability'
import { forecastAvailability } from '@/components/ui/forecastStatus'
import { onTeamLogoError } from '@/components/ui/imageFallback'
import Disclosure from '@/components/match-detail/Disclosure'
import EvidenceBrief from '@/components/match-detail/EvidenceBrief'
import MarketTable from '@/components/match-detail/MarketTable'
import RevisionHistory from '@/components/match-detail/RevisionHistory'
import SourcePanel from '@/components/match-detail/SourcePanel'
import { confidenceStatement } from '@/components/match-detail/evidence'
import { footballDataService } from '@/services/football-data.service'
import { describeError } from '@/services/backend-match-data.service'
import { ProviderStatus } from '@/services/match-data-source'
import { providerLabel, betLabels } from '@/utils/predictionLabels'
import { isMatchLive, isMatchFinished, getMatchStatusText, getMatchStatusBadgeClasses } from '@/utils/matchFilters'

const DAY_LABEL = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })

/** "Sat 19 Sep" for a YYYY-MM-DD, or the raw value when it is not a date we can read. */
function formatDay(date: string): string {
  const at = new Date(`${date}T12:00:00`)
  return Number.isNaN(at.getTime()) ? date : DAY_LABEL.format(at)
}

/**
 * The way back to the list the reader came from.
 *
 * React Router stamps an index on every history entry it creates, and 0 is the entry this document
 * was opened on. Above 0 there is an in-app entry behind us, and going back to it restores the
 * list exactly as it was — the matchday workspace keeps its date and every filter in the URL, so
 * there is nothing else to remember. That is why this is a real Back rather than a link to a
 * default list: a hardcoded destination would silently drop the filters the reader had set.
 *
 * TWO CASES WHERE BACK IS NOT THE ANSWER:
 *  - the fixture was opened directly (a shared link, a new tab): index 0, nothing behind us, and a
 *    Back would leave the site entirely;
 *  - the reader has just been returned here by the sign-in form: that form replaced its own entry
 *    on the way back, so the entry behind this one no longer leads to the list, and a Back would
 *    look like it did nothing at all.
 *
 * WHAT THOSE TWO CASES GET INSTEAD, in order. The list this fixture was opened from, when the URL
 * carries it (`resultsListFrom`; the fixture rows put it there, and it survives the sign-in round
 * trip because that round trip preserves the whole path and query — see useMatchSaving.ts). The
 * point is the second case: a reader who had narrowed the day to one competition, saved while
 * signed out and signed in used to come back to a control that could only offer them the whole
 * 23-fixture day. Their filter was never theirs to drop.
 *
 * Failing that — a shared link, a URL with no such parameter, or one that does not survive the
 * return-path allow-list — the day's own list. `/matches?date=` is not a guess: it is the list
 * this fixture appears on. The label always says which of the three it is, so the control never
 * promises a destination it cannot reach.
 */
const BackToResults: React.FC<{ date: string }> = ({ date }) => {
  const navigate = useNavigate()
  const location = useLocation()
  // Snapshotted at mount: this page does not navigate within itself, and reading history state on
  // every render would be a side effect in a render pass.
  const [hasInAppHistory] = useState(() => {
    const entry = window.history.state as { idx?: unknown } | null
    return typeof entry?.idx === 'number' && entry.idx > 0
  })

  const style = 'focus-ring inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium ' +
    'text-primary-300 transition-colors hover:bg-dark-800 hover:text-primary-200'

  if (hasInAppHistory && !arrivedFromSignIn(location.state)) {
    return (
      <button type="button" onClick={() => navigate(-1)} className={style} data-testid="back-to-results">
        <ArrowLeftIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
        Back to results
      </button>
    )
  }

  // A real Back is not available, but the list the reader chose still is.
  const cameFrom = resultsListFrom(location.search)
  if (cameFrom) {
    return (
      <Link to={cameFrom} className={style} data-testid="back-to-results">
        <ArrowLeftIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
        Back to results
      </Link>
    )
  }

  return (
    <Link to={`/matches?date=${date}`} className={style} data-testid="back-to-results">
      <ArrowLeftIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
      All matches on {formatDay(date)}
    </Link>
  )
}

/**
 * Save this fixture, and get back to the list — the two things a reader wants from this page that
 * were not here at all. The fixture rows have had a save control since the workspace was built;
 * opening a match made it disappear.
 *
 * It is the same `useMatchSaving` the rows use, so there is one saving path and one store: the
 * control here and the star in the list cannot disagree about what is saved. What is different is
 * where a failure is reported. The rows use a toast; this control shows it in place, because a
 * toast that has already faded cannot answer "did that save work?" while you are still looking at
 * the button.
 *
 * NOTHING HERE IS OPTIMISTIC ABOUT A WRITE IT CANNOT SEE
 *  - while a write is in flight the state line says so, and names the direction, rather than
 *    letting the button assert the new state as though the server had already agreed;
 *  - a failed write is stated, and the store has already put the control back to what the server
 *    actually holds;
 *  - when the saved list itself failed to load, "not saved" is not a fact we have, and the line
 *    below says that instead of letting an empty bookmark imply it.
 */
const MatchActions: React.FC<{ match: Match }> = ({ match }) => {
  const saving = useMatchSaving({ toastErrors: false })
  const [inFlight, setInFlight] = useState<'save' | 'unsave' | null>(null)
  const [writeError, setWriteError] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<string | null>(null)

  const label = `${match.homeTeam.name} versus ${match.awayTeam.name}`
  const saved = saving.isSaved(match.id)
  const pending = saving.isPending(match.id)

  const handleToggle = async (next: boolean) => {
    setWriteError(null)
    setOutcome(null)
    setInFlight(next ? 'save' : 'unsave')
    const failure = await saving.toggleSave(match.id, next, match)
    setInFlight(null)
    if (failure) setWriteError(failure)
    else setOutcome(next ? 'Saved to your dashboard.' : 'Removed from your saved matches.')
  }

  const state = pending && inFlight === 'save' ? 'Saving this match…'
    : pending && inFlight === 'unsave' ? 'Removing this match…'
      : outcome

  return (
    <div className="mb-3 border-b border-dark-800 pb-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <BackToResults date={match.date} />
        <SaveMatchButton
          saved={saved}
          pending={pending}
          signedIn={saving.signedIn}
          onRequireSignIn={() => saving.requireSignIn({ matchId: match.id, label })}
          onToggle={next => { void handleToggle(next) }}
          matchLabel={label}
          variant="labelled"
          className="border border-dark-700"
        />
      </div>

      {/* Announced as it changes, and present in the DOM from the first render so that it is. */}
      <p role="status" aria-live="polite" className="mt-2 min-h-[1rem] text-xs text-secondary-300">
        {state}
      </p>

      {writeError && (
        <p role="alert" className="mt-1 text-xs text-danger-300" data-testid="match-save-error">
          {writeError}
        </p>
      )}

      {saving.signedIn && saving.failed && (
        <p role="status" className="mt-1 text-xs text-warning-200" data-testid="match-save-unknown">
          {/* An unfilled bookmark would otherwise assert "not saved", which is not what a failed
              load tells us. */}
          Your saved matches could not be loaded, so this control cannot say whether this fixture
          is saved.{saving.error ? ` ${saving.error}` : ''}
        </p>
      )}
    </div>
  )
}

/**
 * One match, led by the evidence behind it.
 *
 * The page answers, in this order: what is known about the fixture, what is missing and why, how
 * current the model's view is — and only then the numbers themselves, attributed source by source.
 *
 * Three rules hold everywhere below:
 *  - a market a source did not publish is UNAVAILABLE, with the reason the backend gave. It is
 *    never 0%, never the complement of the other half, never borrowed from the other source;
 *  - a probability, a published confidence and a measured accuracy are three different things and
 *    are never allowed to read as one another (nothing here has been scored against a result yet);
 *  - a paused refresh is not a broken forecast. It is stated once, as its own clause, with the
 *    operational detail behind a disclosure instead of stacked beside the numbers.
 *
 * The fetch is the single-match endpoint, which reads what is stored and never triggers a provider
 * refresh, so opening this page spends no provider allowance.
 */
const MatchDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const [match, setMatch] = useState<Match | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null)
  /** Kept apart from `providerStatus === null`: "not asked yet" is not "we asked and could not". */
  const [statusLoaded, setStatusLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!id) return
      try {
        setLoading(true)
        setError(null)
        const result = await footballDataService.getMatch(id)
        if (!cancelled) setMatch(result)
      } catch (err) {
        if (!cancelled) setError(describeError(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [id])

  /**
   * Whether forecast refreshes are running. The single-match endpoint carries no forecast_sync
   * report, so the provider-status endpoint is what lets this page say "paused" instead of
   * "unavailable" when the daily allowance is spent.
   */
  useEffect(() => {
    let cancelled = false
    footballDataService.getProviderStatus()
      .then(status => { if (!cancelled) setProviderStatus(status) })
      .finally(() => { if (!cancelled) setStatusLoaded(true) })
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
          <div className="text-secondary-400">Loading match...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center py-12">
          <h1 className="text-2xl font-bold text-white mb-4">Match data unavailable</h1>
          <p className="text-red-400 mb-6">{error}</p>
          <Button onClick={() => window.location.reload()}>Retry</Button>
        </div>
      </div>
    )
  }

  if (!match) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center py-12">
            <h1 className="text-2xl font-bold text-white mb-4">Match Not Found</h1>
            <p className="text-secondary-400 mb-6">The requested match could not be found.</p>
            <Link to="/predictions/today" className="text-primary-400 hover:text-primary-300">Browse today's matches →</Link>
          </div>
        </div>
      </div>
    )
  }

  const experts = match.expertPredictions && match.expertPredictions.length > 0
    ? match.expertPredictions
    : match.expertPrediction ? [match.expertPrediction] : []
  const forecast = match.providerForecast ?? null
  const brief = match.brief ?? null
  const revisions = match.expertPredictionRevisions ?? []
  const forecastState = forecast?.state || 'unavailable'
  const showScore = (isMatchLive(match) || isMatchFinished(match)) && match.result
  const forecastAvail = forecastAvailability(providerStatus)

  /**
   * Whether each source stated a confidence of its own. GameForecastAPI publishes none, so its
   * badges are bands derived from the probability — which the panel says in words, because a
   * derived band must never be read as a validated accuracy.
   */
  const expertConfidencePublished = brief
    ? brief.reliability.expert.confidence_published
    : experts.some(expert => isPublished(expert.confidence_score))
  const modelConfidencePublished = brief
    ? brief.reliability.model.confidence_published
    : isPublished(forecast?.confidence_score)

  /**
   * The layout rule (and the reason the panels are built as a list): a source that published
   * nothing collapses to one line AFTER the analysis, so the available analysis gets the column —
   * and, on a phone, is not pushed below an empty box.
   */
  const expertPresent = experts.length > 0
  const modelPresent = forecast !== null
  const presentPanels = Number(expertPresent) + Number(modelPresent)

  return (
    <>
      <Helmet>
        <title>{match.homeTeam.name} vs {match.awayTeam.name} - Match Analysis</title>
        <meta name="description" content={`Predictions for ${match.homeTeam.name} vs ${match.awayTeam.name} in ${match.league.name}`} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-4 sm:py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/*
            THE FIXTURE HEADER, MEASURED RATHER THAN STYLED.

            On a 390px phone this card, the freshness block and the evidence panel together pushed
            the first forecast table more than 1,900px down the document: a reader had to scroll
            past five screens of chrome to reach the numbers they came for. Nothing here has been
            removed to fix that — every fact the old header carried is still on this card. What
            changed is that the phone gets a compact row (smaller crests, the teams and the
            scoreline on one line) and the desktop keeps the large treatment it had room for all
            along, and that the competition, kick-off, matchday and venue are one wrapped line
            instead of two stacked blocks.
          */}
          <Card className="mb-4 sm:mb-6">
            <Card.Body>
              {/* Beside the fixture heading: the way back to the list, and the save control the
                  rows have always had and this page did not. */}
              <MatchActions match={match} />

              <div className="text-center">
                <div className="mb-3 flex items-center justify-center gap-3 sm:mb-6 sm:gap-8">
                  <div className="flex-1 text-center">
                    <img src={match.homeTeam.logo} alt="" aria-hidden="true"
                      className="mx-auto mb-1 h-10 w-10 sm:mb-2 sm:h-16 sm:w-16"
                      onError={onTeamLogoError} />
                    <h2 className="text-base font-bold text-white sm:text-xl">{match.homeTeam.name}</h2>
                    {/* Which end of the fixture each team is at, in text. It is small, but it is
                        not decoration: it is the difference between a home and an away forecast. */}
                    <p className="text-xs uppercase tracking-wide text-secondary-400 sm:text-base sm:normal-case sm:tracking-normal">Home</p>
                  </div>
                  <div className="flex-shrink-0 text-center">
                    {showScore && match.result ? (
                      <div className={`text-2xl font-bold sm:text-3xl ${isMatchLive(match) ? 'text-green-500' : 'text-white'}`}>
                        {match.result.homeScore} - {match.result.awayScore}
                      </div>
                    ) : (
                      <div className="text-xl font-bold text-secondary-400 sm:text-2xl">VS</div>
                    )}
                    <span className={`${getMatchStatusBadgeClasses(match)} mt-1 inline-block sm:mt-2`}>
                      {getMatchStatusText(match)}{isMatchLive(match) && match.minute ? ` ${match.minute}'` : ''}
                    </span>
                  </div>
                  <div className="flex-1 text-center">
                    <img src={match.awayTeam.logo} alt="" aria-hidden="true"
                      className="mx-auto mb-1 h-10 w-10 sm:mb-2 sm:h-16 sm:w-16"
                      onError={onTeamLogoError} />
                    <h2 className="text-base font-bold text-white sm:text-xl">{match.awayTeam.name}</h2>
                    <p className="text-xs uppercase tracking-wide text-secondary-400 sm:text-base sm:normal-case sm:tracking-normal">Away</p>
                  </div>
                </div>
                <p className="text-sm text-secondary-400 sm:text-base">
                  {match.league.id ? <Link to={`/league/${match.league.id}`} className="focus-ring rounded hover:text-white">{match.league.name}</Link> : match.league.name}
                  {/* the provider gives the round as a bare number, which reads as noise without its label */}
                  {' '}• {match.date} • {match.time}
                  {match.round ? ` • ${/^\d+$/.test(String(match.round)) ? `Matchday ${match.round}` : match.round}` : ''}
                  {match.venue ? ` • ${match.venue}` : ''}
                </p>
              </div>
            </Card.Body>
          </Card>

          {/*
            How current the page is, directly under the scoreline — the place the question is
            actually asked. It is a different scope from the evidence panel below, and says so:
            this is about our own refresh process (when fixtures, scores, results and forecasts
            last refreshed across the site), while the panel below is about the forecast held for
            THIS fixture. Neither is allowed to stand in for the other, and neither restates the
            other's facts.
          */}
          {statusLoaded && <DataFreshness status={providerStatus} className="mb-4 sm:mb-6" />}

          {/*
            The evidence first: who published anything, which markets they covered, how current it
            is, and every gap with the reason it exists. One statement about the state of the data,
            with the operational detail behind a disclosure rather than stacked beside the numbers.
          */}
          <EvidenceBrief
            brief={brief}
            forecast={forecast}
            experts={experts}
            availability={forecastAvail}
            className="mb-4 sm:mb-6"
          />

          <div className={`grid grid-cols-1 gap-6 ${presentPanels > 1 ? 'lg:grid-cols-2' : ''}`}>
            {expertPresent && (
              <SourcePanel
                source="expert"
                title="Expert Predictions"
                badge={<Badge variant="info">{experts.length} published</Badge>}
                confidenceNote={confidenceStatement(brief?.reliability.expert.detail, 'expert', experts[0])}
                derivedBands={!expertConfidencePublished}
                testId="expert-predictions"
                /* A correction appends; the view it replaced stays readable. */
                footer={revisions.length > 0
                  ? <RevisionHistory revisions={revisions} className="border-t border-dark-700 pt-4" />
                  : null}
              >
                {experts.map((expert, index) => (
                  <div key={index} className={index > 0 ? 'pt-6 border-t border-dark-700' : ''}>
                    <MarketTable prediction={expert} brief={brief} source="expert" />
                    {expert.analysis && (
                      <p className="mt-4 text-sm text-secondary-300 whitespace-pre-line">{expert.analysis}</p>
                    )}
                    <p className="mt-2 text-xs text-secondary-500">
                      Expert · {expert.source_type || 'expert_manual'}
                      {expert.publishedAt ? ` · published ${new Date(expert.publishedAt).toLocaleString()}` : ''}
                    </p>
                  </div>
                ))}
              </SourcePanel>
            )}

            {modelPresent && forecast && (
              <SourcePanel
                source="model"
                title="Model Forecast"
                badge={
                  <Badge variant={forecastState === 'available' ? 'success' : 'warning'}>
                    {providerLabel(forecast.providerName)}
                    {forecastState === 'stale' ? ' · out of date' : ''}
                    {forecastState === 'kickoff_passed' ? ' · for reference' : ''}
                  </Badge>
                }
                confidenceNote={confidenceStatement(brief?.reliability.model.detail, 'model', forecast)}
                derivedBands={!modelConfidencePublished}
                testId="provider-forecast"
              >
                {/*
                  Payload observations, kept visible and kept apart: a `warning` means the numbers do
                  not hold together and the reader needs it before reading them; a `note` is
                  bookkeeping and stays a quiet footnote.
                */}
                <ForecastAnomalies anomalies={forecast.anomalies} />
                <MarketTable prediction={forecast} brief={brief} source="model" />
                {forecast.analysis && (
                  <p className="text-sm text-secondary-300 whitespace-pre-line">{forecast.analysis}</p>
                )}
                {betLabels(forecast.recommendedBets).length > 0 && (
                  <div className="text-xs text-secondary-400">
                    <span className="text-secondary-300">Markets the provider flagged in its own payload: </span>
                    {betLabels(forecast.recommendedBets).join(' · ')}
                    <span className="block text-secondary-500">
                      Listed as the provider published them. Nothing on this page is advice to place a bet.
                    </span>
                  </div>
                )}
                {/* The three provider times, never collapsed into one "generated at". */}
                <ForecastProvenance prediction={forecast} className="border-t border-dark-700 pt-3" />
              </SourcePanel>
            )}
          </div>

          {/*
            ODDS: A PANEL ONLY WHEN THERE IS A FEED BEHIND IT.

            There is no odds feed configured on this installation, so the panel here was a headed
            card whose entire content was a sentence explaining its own emptiness — above the fold
            on a phone, competing with the forecast for attention. The fact is not deleted (a
            reader who wonders where the odds are deserves an answer, and silence would read as an
            oversight); it is one quiet line at the foot of the page instead of a panel near the
            top. The moment `match.odds` carries anything, the panel comes back on its own.
          */}
          {match.odds && (
            <Card className="mt-4 sm:mt-6" data-testid="odds-panel">
              <Card.Header>
                <h3 className="text-lg font-semibold text-white">Betting Odds</h3>
              </Card.Header>
              <Card.Body>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div><div className="text-secondary-400 text-sm">Home Win</div><div className="text-xl font-bold text-white">{match.odds.homeWin.toFixed(2)}</div></div>
                  <div><div className="text-secondary-400 text-sm">Draw</div><div className="text-xl font-bold text-white">{match.odds.draw.toFixed(2)}</div></div>
                  <div><div className="text-secondary-400 text-sm">Away Win</div><div className="text-xl font-bold text-white">{match.odds.awayWin.toFixed(2)}</div></div>
                </div>
              </Card.Body>
            </Card>
          )}

          {/*
            Where the fixture itself came from. Provider keys, a provider's own fixture id and a
            sync timestamp are operator bookkeeping: true, occasionally essential, and never the
            reason anybody opened this page. Behind a disclosure, with the two links a reader
            actually follows left outside it.
          */}
          <div className="mt-4 sm:mt-6">
            <div className="flex flex-wrap gap-3 text-sm">
              {match.homeTeam.id && <Link to={`/teams/${match.homeTeam.id}`} className="focus-ring rounded text-primary-400 hover:text-primary-300">{match.homeTeam.name} →</Link>}
              {match.awayTeam.id && <Link to={`/teams/${match.awayTeam.id}`} className="focus-ring rounded text-primary-400 hover:text-primary-300">{match.awayTeam.name} →</Link>}
            </div>
            <Disclosure summary="Where this fixture came from" className="mt-3" testId="match-provenance">
              <dl className="space-y-1">
                <div className="flex justify-between gap-3"><dt className="text-secondary-400">Fixture source</dt><dd className="text-white">{match.provider || 'unknown'}</dd></div>
                {match.externalId && <div className="flex justify-between gap-3"><dt className="text-secondary-400">Provider fixture id</dt><dd className="font-mono text-xs text-white">{match.externalId}</dd></div>}
                {match.kickoffUtc && <div className="flex justify-between gap-3"><dt className="text-secondary-400">Kick-off (UTC)</dt><dd className="text-white">{match.kickoffUtc.replace('T', ' ').replace('Z', '')}</dd></div>}
                {match.lastSyncedAt && <div className="flex justify-between gap-3"><dt className="text-secondary-400">Last synced</dt><dd className="text-white">{new Date(match.lastSyncedAt).toLocaleString()}</dd></div>}
              </dl>
            </Disclosure>
            {!match.odds && (
              /*
                One line, and deliberately NOT inside the disclosure above. A reader who wonders
                where the odds went should not have to open anything to find out, and a sentence
                hidden behind a summary is a sentence most people never read.
              */
              <p className="mt-3 text-xs text-secondary-500" data-testid="odds-absent">
                Bookmaker odds are not available: no odds feed is configured on this installation.
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

export default MatchDetailPage
