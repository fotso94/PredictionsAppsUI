/**
 * Expert Review Queue Page
 * Page for experts to view predictions pending review
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import expertPredictionService from '../services/expert-prediction.service';
import { ExpertPredictionResponse } from '../types/expert';
import {
  PredictionSourceBadge,
  PredictionStatusBadge,
  ConfidenceBadge,
} from '../components/PredictionSourceBadge';

const ExpertReviewQueuePage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [predictions, setPredictions] = useState<ExpertPredictionResponse[]>([]);
  const [page, setPage] = useState(0);
  const [limit] = useState(20);
  const [processingId, setProcessingId] = useState<string | null>(null);

  useEffect(() => {
    loadReviewQueue();
  }, [page]);

  const loadReviewQueue = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await expertPredictionService.getReviewQueue({
        limit,
        offset: page * limit,
      });
      setPredictions(data);
    } catch (err: any) {
      console.error('Failed to load review queue:', err);
      setError(err.response?.data?.detail || 'Failed to load review queue');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (predictionId: string) => {
    try {
      setProcessingId(predictionId);
      setError(null);
      await expertPredictionService.approvePrediction(predictionId);
      // Reload the queue
      await loadReviewQueue();
    } catch (err: any) {
      console.error('Failed to approve prediction:', err);
      setError(err.response?.data?.detail || 'Failed to approve prediction');
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (predictionId: string) => {
    try {
      setProcessingId(predictionId);
      setError(null);
      const reason = prompt('Enter reason for rejection (optional):');
      await expertPredictionService.rejectPrediction(predictionId, reason || undefined);
      // Reload the queue
      await loadReviewQueue();
    } catch (err: any) {
      console.error('Failed to reject prediction:', err);
      setError(err.response?.data?.detail || 'Failed to reject prediction');
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading review queue...</p>
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
          Review Queue
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Predictions pending review and approval
        </p>
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
            Pending Predictions ({predictions.length})
          </h2>
        </div>

        <div className="p-6">
          {predictions.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400 text-lg mb-4">
                📋 No predictions pending review
              </p>
              <p className="text-gray-500 dark:text-gray-500 text-sm">
                All predictions have been reviewed or there are no pending predictions.
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
                              onError={(e) => {
                                e.currentTarget.style.display = 'none';
                              }}
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
                              onError={(e) => {
                                e.currentTarget.style.display = 'none';
                              }}
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
                        {(prediction.home_win_prob * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-600 dark:text-gray-400">Draw</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {(prediction.draw_prob * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-600 dark:text-gray-400">Away Win</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {(prediction.away_win_prob * 100).toFixed(1)}%
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

                  {/* Actions */}
                  <div className="flex gap-2 mt-4">
                    <button
                      onClick={() => handleApprove(prediction.id)}
                      disabled={processingId === prediction.id}
                      className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {processingId === prediction.id ? 'Processing...' : 'Approve'}
                    </button>
                    <button
                      onClick={() => handleReject(prediction.id)}
                      disabled={processingId === prediction.id}
                      className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {processingId === prediction.id ? 'Processing...' : 'Reject'}
                    </button>
                    <Link
                      to={`/expert/predictions/${prediction.id}`}
                      className="px-4 py-2 bg-gray-600 text-white text-sm rounded-lg hover:bg-gray-700 transition-colors inline-block"
                    >
                      View Details
                    </Link>
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

