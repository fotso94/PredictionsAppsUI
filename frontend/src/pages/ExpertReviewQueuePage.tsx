/**
 * Expert Moderation Queue Page
 *
 * This is a POST-PUBLICATION moderation view, not an approval gate: an expert's prediction goes
 * live on the public match pages the moment they publish it, and nothing here has to happen first.
 * Approving marks a prediction as checked; rejecting withdraws one that is already public. The
 * wording throughout says so, because "Review Queue / pending review / Approve" on its own reads as
 * a gate that does not exist.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import expertPredictionService from '../services/expert-prediction.service';
import { ExpertPredictionResponse } from '../types/expert';
import {
  PredictionSourceBadge,
  PredictionStatusBadge,
  ConfidenceBadge,
} from '../components/PredictionSourceBadge';
import { formatUnitProbability } from '@/components/ui/probability';
import { hideBrokenImage } from '@/components/ui/imageFallback';
import { getErrorMessage } from '@/utils/errors';

const ExpertReviewQueuePage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [predictions, setPredictions] = useState<ExpertPredictionResponse[]>([]);
  const [page, setPage] = useState(0);
  const [limit] = useState(20);
  const [processingId, setProcessingId] = useState<string | null>(null);
  /** Ids expanded in place — there is no /expert/predictions/:id route to link to. */
  const [expandedIds, setExpandedIds] = useState<string[]>([]);

  const loadReviewQueue = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await expertPredictionService.getReviewQueue({
        limit,
        offset: page * limit,
      });
      setPredictions(data);
    } catch (err) {
      console.error('Failed to load moderation queue:', err);
      setError(getErrorMessage(err, 'Failed to load the moderation queue'));
    } finally {
      setLoading(false);
    }
  }, [limit, page]);

  useEffect(() => {
    loadReviewQueue();
  }, [loadReviewQueue]);

  const toggleExpanded = (predictionId: string) => {
    setExpandedIds(prev =>
      prev.includes(predictionId) ? prev.filter(id => id !== predictionId) : [...prev, predictionId]
    );
  };

  const handleApprove = async (predictionId: string) => {
    try {
      setProcessingId(predictionId);
      setError(null);
      await expertPredictionService.approvePrediction(predictionId);
      // Reload the queue
      await loadReviewQueue();
    } catch (err) {
      console.error('Failed to approve prediction:', err);
      setError(getErrorMessage(err, 'Failed to approve prediction'));
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (predictionId: string) => {
    try {
      setProcessingId(predictionId);
      setError(null);
      const reason = prompt('Enter reason for withdrawing this prediction (optional):');
      await expertPredictionService.rejectPrediction(predictionId, reason || undefined);
      // Reload the queue
      await loadReviewQueue();
    } catch (err) {
      console.error('Failed to reject prediction:', err);
      setError(getErrorMessage(err, 'Failed to reject prediction'));
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading moderation queue...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <Link
          to="/expert/dashboard"
          className="text-blue-600 hover:text-blue-700 mb-4 inline-block"
        >
          ← Back to Dashboard
        </Link>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          Moderation Queue
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Predictions flagged for a moderator to look at — after they were published.
        </p>
        <div
          className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200"
          role="note"
          data-testid="no-approval-gate-notice"
        >
          <p className="font-semibold">Publishing does not wait for this queue.</p>
          <p className="mt-1">
            Experts publish directly: a prediction is live on the public match pages as soon as its author
            publishes it, whether or not it ever appears here. Approving records that a moderator has
            checked it; rejecting withdraws a prediction that is already public.
          </p>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg">
          ⚠️ {error}
        </div>
      )}

      {/* Predictions List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Flagged for moderation ({predictions.length})
          </h2>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            These are already visible to readers. Nothing here is waiting for permission to go live.
          </p>
        </div>

        <div className="p-6">
          {predictions.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400 text-lg mb-4">
                📋 Nothing waiting for moderation
              </p>
              <p className="text-gray-500 dark:text-gray-500 text-sm">
                Every flagged prediction has been dealt with. Experts&rsquo; predictions publish immediately
                either way, so an empty queue does not hold anything back.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {predictions.map((prediction) => (
                <div
                  key={prediction.id}
                  className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                >
                  {/* Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <PredictionSourceBadge source={prediction.source} size="sm" />
                      <PredictionStatusBadge status={prediction.status} size="sm" />
                    </div>
                    <ConfidenceBadge confidence={prediction.confidence_score} size="sm" />
                  </div>

                  {/* Match Info */}
                  <div className="mb-3">
                    {prediction.match_details ? (
                      <div className="flex items-center gap-3 mb-2">
                        {/* Home Team */}
                        <div className="flex items-center gap-2 flex-1">
                          {prediction.match_details.home_team_logo && (
                            <img
                              src={prediction.match_details.home_team_logo}
                              alt={prediction.match_details.home_team_name}
                              className="w-6 h-6 object-contain"
                              onError={hideBrokenImage}
                            />
                          )}
                          <span className="text-sm font-medium text-gray-900 dark:text-white">
                            {prediction.match_details.home_team_name}
                          </span>
                        </div>

                        <span className="text-sm text-gray-500 dark:text-gray-400">vs</span>

                        {/* Away Team */}
                        <div className="flex items-center gap-2 flex-1 justify-end">
                          <span className="text-sm font-medium text-gray-900 dark:text-white">
                            {prediction.match_details.away_team_name}
                          </span>
                          {prediction.match_details.away_team_logo && (
                            <img
                              src={prediction.match_details.away_team_logo}
                              alt={prediction.match_details.away_team_name}
                              className="w-6 h-6 object-contain"
                              onError={hideBrokenImage}
                            />
                          )}
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                        Match ID: <span className="font-mono">{prediction.match_id}</span>
                      </p>
                    )}

                    {prediction.match_details?.league_name && (
                      <p className="text-xs text-gray-500 dark:text-gray-500 mb-1">
                        {prediction.match_details.league_name}
                        {prediction.match_details.match_date && (
                          <> • {new Date(prediction.match_details.match_date).toLocaleDateString()}</>
                        )}
                      </p>
                    )}

                    <p className="text-xs text-gray-500 dark:text-gray-500">
                      Created by: {prediction.user_details?.username || prediction.created_by}
                      {prediction.user_details?.first_name && prediction.user_details?.last_name && (
                        <> ({prediction.user_details.first_name} {prediction.user_details.last_name})</>
                      )}
                      {' • '}
                      {new Date(prediction.created_at).toLocaleString()}
                    </p>
                  </div>

                  {/* Probabilities */}
                  <div className="grid grid-cols-3 gap-4 mb-3">
                    <div>
                      <p className="text-xs text-gray-600 dark:text-gray-400">Home Win</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {formatUnitProbability(prediction.home_win_prob, 1)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-600 dark:text-gray-400">Draw</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {formatUnitProbability(prediction.draw_prob, 1)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-600 dark:text-gray-400">Away Win</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {formatUnitProbability(prediction.away_win_prob, 1)}
                      </p>
                    </div>
                  </div>

                  {/* Reasoning */}
                  {prediction.reasoning && (
                    <div className="mb-3">
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Reasoning:
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        {prediction.reasoning}
                      </p>
                    </div>
                  )}

                  {/* Expanded record (replaces the old /expert/predictions/:id link, which had no route) */}
                  {expandedIds.includes(prediction.id) && (
                    <div className="mb-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3 text-xs" data-testid="prediction-details">
                      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">Prediction id</dt>
                          <dd className="font-mono text-gray-800 dark:text-gray-200 break-all">{prediction.id}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">Match id</dt>
                          <dd className="font-mono text-gray-800 dark:text-gray-200 break-all">{prediction.match_id}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">Both teams to score (yes / no)</dt>
                          <dd className="text-gray-800 dark:text-gray-200">
                            {formatUnitProbability(prediction.btts_yes_prob, 1, 'not set')} / {formatUnitProbability(prediction.btts_no_prob, 1, 'not set')}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">Over / under 2.5</dt>
                          <dd className="text-gray-800 dark:text-gray-200">
                            {formatUnitProbability(prediction.total_goals_over_25_prob, 1, 'not set')} / {formatUnitProbability(prediction.total_goals_under_25_prob, 1, 'not set')}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">Over / under 3.5</dt>
                          <dd className="text-gray-800 dark:text-gray-200">
                            {formatUnitProbability(prediction.total_goals_over_35_prob, 1, 'not set')} / {formatUnitProbability(prediction.total_goals_under_35_prob, 1, 'not set')}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">Published</dt>
                          <dd className="text-gray-800 dark:text-gray-200">
                            {prediction.published_at ? new Date(prediction.published_at).toLocaleString() : 'not published'}
                          </dd>
                        </div>
                      </dl>
                      {prediction.key_factors && Object.keys(prediction.key_factors).length > 0 && (
                        <div className="mt-3">
                          <p className="text-gray-500 dark:text-gray-400 mb-1">Key factors</p>
                          <ul className="list-disc list-inside space-y-0.5 text-gray-800 dark:text-gray-200">
                            {Object.entries(prediction.key_factors).map(([key, value]) => (
                              <li key={key}>{key}: {String(value)}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2 mt-4">
                    <button
                      onClick={() => handleApprove(prediction.id)}
                      disabled={processingId === prediction.id}
                      title="Records that a moderator has checked this prediction. It is already public."
                      className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {processingId === prediction.id ? 'Processing...' : 'Mark as checked'}
                    </button>
                    <button
                      onClick={() => handleReject(prediction.id)}
                      disabled={processingId === prediction.id}
                      title="Withdraws a prediction that is already visible to readers."
                      className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {processingId === prediction.id ? 'Processing...' : 'Withdraw'}
                    </button>
                    <button
                      onClick={() => toggleExpanded(prediction.id)}
                      aria-expanded={expandedIds.includes(prediction.id)}
                      className="px-4 py-2 bg-gray-600 text-white text-sm rounded-lg hover:bg-gray-700 transition-colors"
                    >
                      {expandedIds.includes(prediction.id) ? 'Hide details' : 'View details'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {predictions.length > 0 && (
          <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-between items-center">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <span className="text-gray-600 dark:text-gray-400">
              Page {page + 1}
            </span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={predictions.length < limit}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ExpertReviewQueuePage;

