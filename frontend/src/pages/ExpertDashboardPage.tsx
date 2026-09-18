/**
 * The expert's workspace: what to do next, then what has been published, then the numbers.
 *
 * WHAT CHANGED AND WHY. The dashboard used to open with four metric tiles — total, published,
 * pending, accuracy — which for a new expert read "0, 0, 0, Not scored" across the whole first
 * screen. Four empty boxes are not a starting point, and the accuracy tile in particular occupied
 * prime space to say that nothing has ever been scored. The work leads now: continue the draft you
 * left, choose a match, and what you have recently published. The counts moved below it, where they
 * are a record rather than an obstacle, and moderation — which does not gate publication — is last.
 *
 * PUBLICATION IS DIRECT. Nothing on this page waits for an administrator. The moderation section
 * reviews work that is ALREADY public; it is not an approval queue, and it is labelled as such.
 *
 * NO ACCURACY IS CLAIMED. `accuracy_rate` is null until predictions are scored against results, and
 * a null renders as "Not scored yet" with the reason, never as 0% and never as a derived band.
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
import { ComposerDraft, clearDraft, readDraft, savedAgo } from '@/components/expert/draft'

/** One published prediction, compact: the fixture, the leading call, and what can be done with it. */
const RecentRow: React.FC<{
  prediction: ExpertPredictionResponse
  busy: boolean
  onTogglePublish: (id: string) => void
  onDelete: (id: string) => void
}> = ({ prediction, busy, onTogglePublish, onDelete }) => {
  const details = prediction.match_details
  const status = prediction.status.toLowerCase()
  const canToggle = status === 'published' || status === 'archived'
  const canDelete = status === 'published' || status === 'archived' || status === 'rejected'

  return (
    <li className="border-b border-dark-800 p-3 last:border-b-0 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {details ? (
            <div className="flex min-w-0 items-center gap-2">
              {details.home_team_logo && (
                <img src={details.home_team_logo} alt="" aria-hidden="true" className="h-4 w-4 flex-shrink-0 object-contain" onError={hideBrokenImage} />
              )}
              <p className="min-w-0 truncate text-sm font-medium text-white">
                {details.home_team_name} v {details.away_team_name}
              </p>
            </div>
          ) : (
            <p className="text-sm font-medium text-white">Fixture details unavailable</p>
          )}
          <p className="mt-0.5 truncate text-xs text-secondary-400">
            {[details?.league_name, details?.match_date].filter(Boolean).join(' · ') || 'Competition unavailable'}
          </p>
        </div>
        <PredictionStatusBadge status={prediction.status} size="sm" />
      </div>

      {/* Three published probabilities. Nothing here is renormalised on the way to the screen. */}
      <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
        {([
          ['Home', prediction.home_win_prob],
          ['Draw', prediction.draw_prob],
          ['Away', prediction.away_win_prob],
        ] as const).map(([label, value]) => (
          <div key={label} className="min-w-0 rounded bg-dark-800/70 px-2 py-1">
            <p className="truncate text-[11px] text-secondary-400">{label}</p>
            <p className="num font-semibold text-white">{formatUnitProbability(value, 1, 'Unavailable')}</p>
          </div>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <PredictionSourceBadge source={prediction.source} size="sm" />
        <span className="text-[11px] text-secondary-500">
          Published {new Date(prediction.published_at ?? prediction.created_at).toLocaleDateString()}
        </span>
        <span className="ml-auto flex flex-wrap gap-2">
          <Link to="/expert/predictions/my-predictions" className="focus-ring text-xs font-medium text-primary-300 hover:text-primary-200">
            Edit
          </Link>
          {canToggle && (
            <button type="button" disabled={busy} onClick={() => onTogglePublish(prediction.id)} className="focus-ring text-xs font-medium text-secondary-200 hover:text-white disabled:opacity-50">
              {busy ? 'Working…' : status === 'published' ? 'Unpublish' : 'Publish'}
            </button>
          )}
          {canDelete && (
            <button type="button" disabled={busy} onClick={() => onDelete(prediction.id)} className="focus-ring text-xs font-medium text-danger-300 hover:text-danger-200 disabled:opacity-50">
              Delete
            </button>
          )}
        </span>
      </div>
    </li>
  )
}

const ExpertDashboardPage: React.FC = () => {
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
      setError(getErrorMessage(err, 'Failed to load dashboard data'))
    } finally {
      setLoading(false)
    }
  }, [])

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
      setError(getErrorMessage(err, 'Failed to toggle publish status'))
    } finally {
      setProcessingId(null)
    }
  }

  const handleDelete = async (predictionId: string) => {
    if (!confirm('Delete this prediction? It disappears from the public match page and cannot be undone.')) return
    try {
      setProcessingId(predictionId)
      setError(null)
      await expertPredictionService.deletePrediction(predictionId)
      await loadDashboardData()
    } catch (err) {
      console.error('Failed to delete prediction:', err)
      setError(getErrorMessage(err, 'Failed to delete prediction'))
    } finally {
      setProcessingId(null)
    }
  }

  const discardDraft = () => {
    clearDraft(userId)
    setDraft(null)
  }

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white sm:text-3xl">Expert workspace</h1>
        <p className="mt-1 text-sm text-secondary-300">
          Write predictions and manage what you have published. Your predictions go public the moment you press
          publish — nothing here waits for approval.
        </p>
      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-danger-700 bg-danger-900/30 px-4 py-3" role="alert">
          <p className="text-sm text-danger-200">{error}</p>
          <button type="button" onClick={loadDashboardData} className="focus-ring mt-2 text-xs font-medium text-primary-300 hover:text-primary-200">
            Try again
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------------ what to do next */}
      <section aria-labelledby="next-heading">
        <h2 id="next-heading" className="sr-only">What to do next</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {draft && (
            <div className="card border-primary-800 p-4 sm:col-span-2">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-semibold text-white">
                    <PencilSquareIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                    Continue your draft
                  </p>
                  <p className="mt-1 truncate text-sm text-secondary-200">
                    {draft.fixture && draft.fixture.homeTeam
                      ? `${draft.fixture.homeTeam} v ${draft.fixture.awayTeam}`
                      : 'Fixture not chosen yet'}
                    {savedAgo(draft.savedAt) && <span className="text-secondary-400"> · saved {savedAgo(draft.savedAt)}</span>}
                  </p>
                  <p className="mt-1 text-xs text-secondary-400">
                    Stored in this browser only. It has not been published and will not publish itself.
                  </p>
                </div>
                <div className="flex flex-shrink-0 flex-wrap gap-2">
                  <Link
                    to={draft.fixture?.id ? `/expert/predictions/create?matchId=${encodeURIComponent(draft.fixture.id)}` : '/expert/predictions/create'}
                    className="btn btn-sm btn-primary"
                  >
                    Continue
                  </Link>
                  <button type="button" onClick={discardDraft} className="btn btn-sm btn-ghost">Discard</button>
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
                Choose a match
              </span>
              <span className="mt-1 block text-xs text-secondary-400">
                One filtered fixture list. Filter by day, competition or team.
              </span>
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
                My predictions
              </span>
              <span className="mt-1 block text-xs text-secondary-400">
                Edit, unpublish or remove anything you have published.
              </span>
            </span>
            <ArrowRightIcon className="h-4 w-4 flex-shrink-0 text-primary-300" aria-hidden="true" />
          </Link>
        </div>
      </section>

      {/* ------------------------------------------------------------------ recently published */}
      <section className="mt-8" aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="mb-3 text-lg font-semibold text-white">Recently published</h2>
        <div className="card overflow-hidden">
          {loading ? (
            <div className="flex justify-center p-8"><LoadingSpinner /></div>
          ) : recentPredictions.length === 0 ? (
            <div className="p-4">
              <EmptyState
                tone="empty"
                title="You have not published anything yet"
                description="Choose a match and write your first prediction. It goes live as soon as you publish it."
                variant="inline"
                action={<Link to="/expert/match-selection" className="btn btn-sm btn-primary">Choose a match</Link>}
              />
            </div>
          ) : (
            <ul>
              {recentPredictions.map(prediction => (
                <RecentRow
                  key={prediction.id}
                  prediction={prediction}
                  busy={processingId === prediction.id}
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
          <h2 id="record-heading" className="mb-3 text-lg font-semibold text-white">Your record</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {([
              ['Predictions written', String(metrics.total_predictions)],
              ['Published', String(metrics.published_predictions)],
              ['Not published', String(metrics.pending_predictions)],
              // A stored 0 is how "nobody has claimed a conviction" reaches us from the numeric
              // column — printing it as "0%" would report a judgement of zero confidence that no
              // expert ever made.
              ['Average conviction', metrics.average_confidence > 0
                ? formatUnitProbability(metrics.average_confidence, 0, 'None published')
                : 'None published'],
            ] as const).map(([label, value]) => (
              <div key={label} className="card p-3">
                <p className="truncate text-xs text-secondary-400">{label}</p>
                <p className="num mt-1 text-2xl font-bold text-white">{value}</p>
              </div>
            ))}
          </div>
          <div className="card mt-3 p-3">
            <p className="text-xs text-secondary-400">Accuracy</p>
            <p className="num mt-1 text-2xl font-bold text-white">
              {formatUnitProbability(metrics.accuracy_rate, 1, 'Not scored yet')}
            </p>
            {metrics.accuracy_rate === null && (
              <p className="mt-1 text-xs text-secondary-400">
                No prediction has been settled against a final result yet, so there is no accuracy to report. The
                average conviction above is what you claimed, not a measurement of how often you were right.
              </p>
            )}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------------ moderation, last */}
      {reviewQueue.length > 0 && (
        <section className="mt-8" aria-labelledby="moderation-heading">
          <h2 id="moderation-heading" className="mb-1 flex items-center gap-2 text-lg font-semibold text-white">
            <ClipboardDocumentListIcon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
            Flagged for moderation
          </h2>
          <p className="mb-3 text-xs text-secondary-400">
            These are already public. Moderation happens after publication — it is not an approval gate.
          </p>
          <div className="card overflow-hidden">
            <ul>
              {reviewQueue.slice(0, 3).map(prediction => (
                <li key={prediction.id} className="flex flex-wrap items-center gap-2 border-b border-dark-800 p-3 last:border-b-0">
                  <span className="min-w-0 flex-1 truncate text-sm text-white">
                    {prediction.match_details
                      ? `${prediction.match_details.home_team_name} v ${prediction.match_details.away_team_name}`
                      : 'Fixture details unavailable'}
                  </span>
                  <PredictionStatusBadge status={prediction.status} size="sm" />
                </li>
              ))}
            </ul>
            <div className="border-t border-dark-800 p-3">
              <Link to="/expert/predictions/review-queue" className="focus-ring text-xs font-medium text-primary-300 hover:text-primary-200">
                View the moderation list
              </Link>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}

export default ExpertDashboardPage
