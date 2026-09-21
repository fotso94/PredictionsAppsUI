/**
 * The expert's workspace: what to do next, then what has been published, then the numbers.
 *
 * THE ORDER OF THE SECTIONS IS THE POINT, AND METRICS DO NOT COME FIRST. Opening with four
 * metric tiles — total, published, pending, accuracy — gives a new expert "0, 0, 0, Not scored"
 * across the whole first screen: four empty boxes are not a starting point, and an accuracy tile
 * in prime space says only that nothing has ever been scored. So the work leads — continue the
 * draft you left, choose a match, what you have recently published — the counts sit below it
 * where they are a record rather than an obstacle, and moderation, which does not gate
 * publication, is last.
 *
 * PUBLICATION IS DIRECT. Nothing on this page waits for an administrator. The moderation section
 * reviews work that is ALREADY public; it is not an approval queue, and it is labelled as such.
 *
 * NO ACCURACY IS CLAIMED. `accuracy_rate` is null until predictions are scored against results, and
 * a null renders as "Not scored yet" with the reason, never as 0% and never as a derived band.
 * In French that stand-in is « Pas encore évaluée » — feminine, agreeing with « l'exactitude »,
 * and still a statement that no measurement exists rather than anything a reader could scan as a
 * figure.
 *
 * THE AVERAGE-CONVICTION TILE SPLITS TWO CASES THE ACCURACY TILE DOES NOT, AND THE SPLIT IS THE
 * POINT. `average_confidence` null means nobody ever claimed a conviction, and the tile stands in
 * with "None published" / « Aucune publiée ». A non-null 0 is a conviction an expert did claim and
 * set to zero, and the tile prints it: "0%" / « 0 % ». Collapsing the two would make the panel
 * contradict the count beside it — "Published 4" next to « Aucune publiée » reports a withdrawal
 * that never happened — and would erase a judgement the expert made under their own name. Both
 * directions are pinned, in both languages, in frontend/e2e/mocked/expert-localisation.spec.ts.
 *
 * THE TILE HOLDS NO CONDITIONAL OF ITS OWN FOR THAT SPLIT, BECAUSE `formatUnitProbability`
 * ALREADY DRAWS IT: it returns the fallback for null and undefined and formats every finite
 * number, zero included. So the tile passes the value with the stand-in wording as the fallback
 * and stops there. An `average_confidence !== null` check in front of it would only re-derive
 * the answer the helper gives; a `> 0` check would be wrong, reporting a deliberate 0% average
 * as though nothing had been published at all. The rule this follows: describe the mechanism
 * that is there, and delete a sentence rather than keep a nearly-true version of it.
 *
 * EVERY DATE ON THIS PAGE IS IN THE READER'S CHOSEN ZONE. Not
 * `new Date(...).toLocaleDateString()`, which formats in the DEVICE's zone and the DEVICE's
 * locale, and not `match_details.match_date` dropped in as the raw ISO string the API sends,
 * "2026-09-20T18:30:00Z", which is not a date in any language. An expert reads a kick-off to
 * decide whether a prediction is still prematch, so a kick-off in the wrong zone is a
 * correctness defect and not a cosmetic one. `backendInstant` reads the instant (this backend
 * anchors these columns with a trailing Z — see the field serialisers in
 * backend/app/schemas/predictions.py) and `formatDate` spells it out in the reader's language and
 * their chosen zone.
 */

import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRightIcon, ClipboardDocumentListIcon, DocumentTextIcon, PencilSquareIcon, PlusIcon,
} from '@heroicons/react/24/outline'
import expertPredictionService from '@/services/expert-prediction.service'
import { ExpertPerformanceMetrics, ExpertPredictionResponse } from '@/types/expert'
import { PredictionSourceBadge, PredictionStatusBadge } from '@/components/PredictionSourceBadge'
import { formatUnitProbability } from '@/components/ui/probability'
import { hideBrokenImage } from '@/components/ui/imageFallback'
import EmptyState from '@/components/ui/EmptyState'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { getErrorMessage } from '@/utils/errors'
import { useAuth } from '@/hooks/useAuth'
import { ComposerDraft, clearDraft, readDraft } from '@/components/expert/draft'
import { relativeTime } from '@/components/ui/freshness'
import { backendInstant, formatDate, formatNumber } from '@/i18n'
import { useT } from '@/i18n/react'
import type { TranslateFn } from '@/i18n'

/** One published prediction, compact: the fixture, the leading call, and what can be done with it. */
const RecentRow: React.FC<{
  prediction: ExpertPredictionResponse
  busy: boolean
  t: TranslateFn
  onTogglePublish: (id: string) => void
  onDelete: (id: string) => void
}> = ({ prediction, busy, t, onTogglePublish, onDelete }) => {
  const details = prediction.match_details
  const status = prediction.status.toLowerCase()
  const canToggle = status === 'published' || status === 'archived'
  const canDelete = status === 'published' || status === 'archived' || status === 'rejected'
  // A date in the reader's language and their chosen zone, never the API's raw ISO string.
  const kickoff = formatDate(backendInstant(details?.match_date).at)
  const publishedOn = formatDate(backendInstant(prediction.published_at ?? prediction.created_at).at)

  return (
    <li className="border-b border-dark-800 p-3 last:border-b-0 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {details ? (
            <div className="flex min-w-0 items-center gap-2">
              {details.home_team_logo && (
                <img src={details.home_team_logo} alt="" aria-hidden="true" className="h-4 w-4 flex-shrink-0 object-contain" onError={hideBrokenImage} />
              )}
              {/*
                THE AWAY TEAM IS THE PART THAT FALLS OFF, and only in French.
                "Coton Sport contre Union Douala" overflows a 211px box at 360px while the English
                "Coton Sport v Union Douala" fits with room to spare — the box was measured in
                English and French is reliably longer. Truncating hid nine pixels, which is the
                end of the AWAY team's name, so the row silently named one club and half of
                another.
                Wrapping instead of truncating costs a second line on a narrow screen and keeps
                both names, which is the same trade the kick-off line on this page already makes.
              */}
              <p className="min-w-0 break-words text-sm font-medium text-white">
                {t('expert.fixtureShort', { home: details.home_team_name, away: details.away_team_name })}
              </p>
            </div>
          ) : (
            <p className="text-sm font-medium text-white">{t('expert.row.fixtureUnavailable')}</p>
          )}
          {/*
            THE SAME SHAPE AS THE DRAFT LINE ABOVE, FOUND BY MEASURING RATHER THAN BY READING.

            This was one `truncate`d line holding a competition name joined to a kick-off with
            " · ". Measured at 360px with a real competition name — « Ligue des champions de la
            CAF · 21 septembre 2026 » — it needed 298px and had 211px, and what fell off the end
            was the KICK-OFF, every time: the name is first, so the name always survives and the
            date never does. An expert reads a kick-off to decide whether a prediction is still
            prematch. This page's own header calls a kick-off in the wrong zone a correctness
            defect and not a cosmetic one; a kick-off that is not on the screen at all is the
            same defect with a different cause.

            So the two are separate runs now, and they are NOT treated alike. A competition's
            name is a name: abbreviating it with an ellipsis still leaves it recognisable, and it
            can be arbitrarily long. The kick-off is a value the expert is reading off the page,
            so it never truncates and it never breaks across lines; when the pair does not fit,
            it is the name that gives way, and failing that the line wraps.
          */}
          <p className="mt-0.5 flex flex-wrap items-baseline gap-x-1 text-xs text-secondary-400" data-testid="recent-row-competition">
            {details?.league_name && (
              <span className="min-w-0 max-w-full truncate" data-testid="recent-row-competition-name">{details.league_name}</span>
            )}
            {kickoff && (
              <span className="whitespace-nowrap" data-testid="recent-row-kickoff">
                {details?.league_name ? '· ' : ''}{kickoff}
              </span>
            )}
            {!details?.league_name && !kickoff && <span>{t('expert.row.competitionUnavailable')}</span>}
          </p>
        </div>
        <PredictionStatusBadge status={prediction.status} size="sm" />
      </div>

      {/* Three published probabilities. Nothing here is renormalised on the way to the screen. */}
      <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
        {([
          ['fixture.side.home', prediction.home_win_prob],
          ['fixture.side.draw', prediction.draw_prob],
          ['fixture.side.away', prediction.away_win_prob],
        ] as const).map(([label, value]) => (
          <div key={label} className="min-w-0 rounded bg-dark-800/70 px-2 py-1">
            <p className="truncate text-[11px] text-secondary-400">{t(label)}</p>
            {/* Never "0.0%": a market this expert did not publish says so. */}
            <p className="num font-semibold text-white">{formatUnitProbability(value, 1, t('probability.unavailable'))}</p>
          </div>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <PredictionSourceBadge source={prediction.source} size="sm" />
        {publishedOn && (
          <span className="text-[11px] text-secondary-500">
            {t('expert.row.publishedOn', { date: publishedOn })}
          </span>
        )}
        <span className="ml-auto flex flex-wrap gap-2">
          <Link to="/expert/predictions/my-predictions" className="focus-ring text-xs font-medium text-primary-300 hover:text-primary-200">
            {t('expert.action.edit')}
          </Link>
          {canToggle && (
            <button type="button" disabled={busy} onClick={() => onTogglePublish(prediction.id)} className="focus-ring text-xs font-medium text-secondary-200 hover:text-white disabled:opacity-50">
              {busy ? t('expert.action.working') : status === 'published' ? t('expert.action.unpublish') : t('expert.action.publish')}
            </button>
          )}
          {canDelete && (
            <button type="button" disabled={busy} onClick={() => onDelete(prediction.id)} className="focus-ring text-xs font-medium text-danger-300 hover:text-danger-200 disabled:opacity-50">
              {t('expert.action.delete')}
            </button>
          )}
        </span>
      </div>
    </li>
  )
}

const ExpertDashboardPage: React.FC = () => {
  const t = useT()
  const { user } = useAuth()
  const userId = user?.id ?? null

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [metrics, setMetrics] = useState<ExpertPerformanceMetrics | null>(null)
  const [recentPredictions, setRecentPredictions] = useState<ExpertPredictionResponse[]>([])
  const [reviewQueue, setReviewQueue] = useState<ExpertPredictionResponse[]>([])
  const [processingId, setProcessingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<ComposerDraft | null>(null)

  useEffect(() => {
    setDraft(readDraft(userId))
  }, [userId])

  const loadDashboardData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const metricsData = await expertPredictionService.getPerformanceMetrics()
      setMetrics(metricsData)
      setRecentPredictions(metricsData.recent_predictions || [])
      // Post-publication moderation, not an approval gate.
      const queueData = await expertPredictionService.getReviewQueue({ limit: 5 })
      setReviewQueue(queueData)
    } catch (err) {
      console.error('Failed to load dashboard data:', err)
      setError(getErrorMessage(err, t('expert.dashboard.loadFailed')))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    loadDashboardData()
  }, [loadDashboardData])

  const handleTogglePublish = async (predictionId: string) => {
    try {
      setProcessingId(predictionId)
      setError(null)
      await expertPredictionService.togglePublishStatus(predictionId)
      await loadDashboardData()
    } catch (err) {
      console.error('Failed to toggle publish status:', err)
      setError(getErrorMessage(err, t('expert.dashboard.toggleFailed')))
    } finally {
      setProcessingId(null)
    }
  }

  const handleDelete = async (predictionId: string) => {
    if (!confirm(t('expert.dashboard.confirmDelete'))) return
    try {
      setProcessingId(predictionId)
      setError(null)
      await expertPredictionService.deletePrediction(predictionId)
      await loadDashboardData()
    } catch (err) {
      console.error('Failed to delete prediction:', err)
      setError(getErrorMessage(err, t('expert.deleteFailed')))
    } finally {
      setProcessingId(null)
    }
  }

  const discardDraft = () => {
    clearDraft(userId)
    setDraft(null)
  }

  /** "3 minutes ago" / « il y a 3 minutes », in the reader's language. Null when unreadable. */
  const savedAt = draft ? relativeTime(draft.savedAt) : null

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white sm:text-3xl">{t('expert.dashboard.title')}</h1>
        <p className="mt-1 text-sm text-secondary-300">{t('expert.dashboard.intro')}</p>
      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-danger-700 bg-danger-900/30 px-4 py-3" role="alert">
          <p className="text-sm text-danger-200">{error}</p>
          <button type="button" onClick={loadDashboardData} className="focus-ring mt-2 text-xs font-medium text-primary-300 hover:text-primary-200">
            {t('expert.retry')}
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------------ what to do next */}
      <section aria-labelledby="next-heading">
        <h2 id="next-heading" className="sr-only">{t('expert.dashboard.nextHeading')}</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {draft && (
            <div className="card border-primary-800 p-4 sm:col-span-2">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-semibold text-white">
                    <PencilSquareIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                    {t('expert.draft.continueTitle')}
                  </p>
                  {/*
                    NO `truncate` HERE, AND THAT IS LOAD-BEARING RATHER THAN A TIDY-UP.

                    `truncate` is `white-space: nowrap` with `overflow: hidden`, and on this line
                    it loses words outright: at 360px in French the saved-ago run ends 106px past
                    the paragraph it lives in, and because the clipping is on this paragraph and
                    not on the page, the DOCUMENT does not scroll sideways to show it or any test
                    that measures the document. « il y a 7 minutes » is half as long again as
                    "7 minutes ago", and that is the normal case, not a pathological one: French
                    runs reliably longer than English, so a single-line box measured in English
                    is a box that loses a French sentence.

                    The answer is to let the line wrap. Nothing here needs to be one line: it is a
                    card, not a table row, and a fixture name over two lines costs a few pixels of
                    height where a clipped line costs the reader the information. `break-words`
                    covers the one case wrapping cannot — a single token longer than the card.

                    Shortening the French to fit is the other way to make the measurement pass,
                    and it is the wrong one: it makes the language that needs
                    the room the one that has to give it up, and the next longer string — a
                    two-hour-old draft, a longer team name — breaks it again.
                  */}
                  <p className="mt-1 break-words text-sm text-secondary-200" data-testid="draft-summary">
                    {draft.fixture && draft.fixture.homeTeam
                      ? t('expert.fixtureShort', { home: draft.fixture.homeTeam, away: draft.fixture.awayTeam })
                      : t('expert.draft.noFixture')}
                    {/*
                      `savedAgo` in components/expert/draft.ts returns hard-coded English ("3
                      minutes ago", "yesterday") and that module is another package's. This is
                      `relativeTime`, which is the same idea already translated: it builds the
                      duration first and then lets the catalogue put the frame where the language
                      wants it — "3 minutes ago", « il y a 3 minutes ».
                    */}
                    {savedAt && (
                      <span className="text-secondary-400" data-testid="draft-saved-ago">
                        {' · '}{t('expert.draft.savedAgo', { ago: savedAt })}
                      </span>
                    )}
                  </p>
                  <p className="mt-1 text-xs text-secondary-400">{t('expert.draft.localOnly')}</p>
                </div>
                <div className="flex flex-shrink-0 flex-wrap gap-2">
                  <Link
                    to={draft.fixture?.id ? `/expert/predictions/create?matchId=${encodeURIComponent(draft.fixture.id)}` : '/expert/predictions/create'}
                    className="btn btn-sm btn-primary"
                  >
                    {t('expert.draft.continue')}
                  </Link>
                  <button type="button" onClick={discardDraft} className="btn btn-sm btn-ghost">{t('expert.draft.discard')}</button>
                </div>
              </div>
            </div>
          )}

          <Link
            to="/expert/match-selection"
            className="card focus-ring flex items-center justify-between gap-3 p-4 transition-colors hover:border-dark-600"
          >
            <span className="min-w-0">
              <span className="flex items-center gap-2 text-sm font-semibold text-white">
                <PlusIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                {t('expert.dashboard.chooseMatch')}
              </span>
              <span className="mt-1 block text-xs text-secondary-400">{t('expert.dashboard.chooseMatchHint')}</span>
            </span>
            <ArrowRightIcon className="h-4 w-4 flex-shrink-0 text-primary-300" aria-hidden="true" />
          </Link>

          <Link
            to="/expert/predictions/my-predictions"
            className="card focus-ring flex items-center justify-between gap-3 p-4 transition-colors hover:border-dark-600"
          >
            <span className="min-w-0">
              <span className="flex items-center gap-2 text-sm font-semibold text-white">
                <DocumentTextIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                {t('expert.dashboard.myPredictions')}
              </span>
              <span className="mt-1 block text-xs text-secondary-400">{t('expert.dashboard.myPredictionsHint')}</span>
            </span>
            <ArrowRightIcon className="h-4 w-4 flex-shrink-0 text-primary-300" aria-hidden="true" />
          </Link>
        </div>
      </section>

      {/* ------------------------------------------------------------------ recently published */}
      <section className="mt-8" aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="mb-3 text-lg font-semibold text-white">{t('expert.dashboard.recentHeading')}</h2>
        <div className="card overflow-hidden">
          {loading ? (
            <div className="flex justify-center p-8"><LoadingSpinner /></div>
          ) : recentPredictions.length === 0 ? (
            <div className="p-4">
              <EmptyState
                tone="empty"
                title={t('expert.dashboard.emptyTitle')}
                description={t('expert.dashboard.emptyBody')}
                variant="inline"
                action={<Link to="/expert/match-selection" className="btn btn-sm btn-primary">{t('expert.dashboard.chooseMatch')}</Link>}
              />
            </div>
          ) : (
            <ul>
              {recentPredictions.map(prediction => (
                <RecentRow
                  key={prediction.id}
                  prediction={prediction}
                  busy={processingId === prediction.id}
                  t={t}
                  onTogglePublish={handleTogglePublish}
                  onDelete={handleDelete}
                />
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* ------------------------------------------------------------------ the record */}
      {metrics && (
        <section className="mt-8" aria-labelledby="record-heading">
          <h2 id="record-heading" className="mb-3 text-lg font-semibold text-white">{t('expert.dashboard.recordHeading')}</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {([
              ['expert.dashboard.statWritten', formatNumber(metrics.total_predictions)],
              ['expert.dashboard.statPublished', formatNumber(metrics.published_predictions)],
              ['expert.dashboard.statNotPublished', formatNumber(metrics.pending_predictions)],
              // Null is "nobody has claimed a conviction"; zero is a judgement of zero. Those are
              // different stored values and must stay different on screen, so the split is left
              // to `formatUnitProbability`, which stands in for null and undefined and formats
              // every finite number including 0. A truthiness or `> 0` test here would report a
              // deliberate 0% average as though nothing had been published at all.
              // « Aucune publiée » is not a figure and must never be shortened into one.
              ['expert.dashboard.statAverageConviction',
                formatUnitProbability(metrics.average_confidence, 0, t('expert.dashboard.nonePublished'))],
            ] as const).map(([label, value]) => (
              <div key={label} className="card p-3">
                <p className="truncate text-xs text-secondary-400">{t(label)}</p>
                <p className="num mt-1 text-2xl font-bold text-white">{value}</p>
              </div>
            ))}
          </div>
          <div className="card mt-3 p-3">
            {/*
              « Exactitude », not « Taux de réussite ». The latter is `measured.hitRate` in the
              core catalogue — the settlement engine's measured hit rate over a stated sample.
              This tile is `accuracy_rate` from the expert analytics endpoint, a different number
              from a different pipeline, and giving the two the same French would invite a reader
              to take an unmeasured figure for a measured one.
            */}
            <p className="text-xs text-secondary-400">{t('expert.dashboard.accuracy')}</p>
            <p className="num mt-1 text-2xl font-bold text-white">
              {formatUnitProbability(metrics.accuracy_rate, 1, t('expert.dashboard.notScoredYet'))}
            </p>
            {metrics.accuracy_rate === null && (
              <p className="mt-1 text-xs text-secondary-400">{t('expert.dashboard.accuracyNote')}</p>
            )}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------------ moderation, last */}
      {reviewQueue.length > 0 && (
        <section className="mt-8" aria-labelledby="moderation-heading">
          <h2 id="moderation-heading" className="mb-1 flex items-center gap-2 text-lg font-semibold text-white">
            <ClipboardDocumentListIcon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
            {t('expert.queue.heading')}
          </h2>
          <p className="mb-3 text-xs text-secondary-400">{t('expert.dashboard.moderationNote')}</p>
          <div className="card overflow-hidden">
            <ul>
              {reviewQueue.slice(0, 3).map(prediction => (
                <li key={prediction.id} className="flex flex-wrap items-center gap-2 border-b border-dark-800 p-3 last:border-b-0">
                  {/* Same reason as the published row above: in French the away team's name is
                      what the truncation eats. */}
                  <span className="min-w-0 flex-1 break-words text-sm text-white">
                    {prediction.match_details
                      ? t('expert.fixtureShort', {
                        home: prediction.match_details.home_team_name,
                        away: prediction.match_details.away_team_name,
                      })
                      : t('expert.row.fixtureUnavailable')}
                  </span>
                  <PredictionStatusBadge status={prediction.status} size="sm" />
                </li>
              ))}
            </ul>
            <div className="border-t border-dark-800 p-3">
              <Link to="/expert/predictions/review-queue" className="focus-ring text-xs font-medium text-primary-300 hover:text-primary-200">
                {t('expert.dashboard.moderationLink')}
              </Link>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}

export default ExpertDashboardPage
