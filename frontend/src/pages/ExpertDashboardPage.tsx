/**
 * Expert Dashboard Page
 * Dashboard for expert users to manage predictions (KAN-156)
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import expertPredictionService from '../services/expert-prediction.service';
import {
  ExpertPredictionResponse,
  ExpertPerformanceMetrics,
} from '../types/expert';
import {
  PredictionSourceBadge,
  PredictionStatusBadge,
  ConfidenceBadge,
} from '../components/PredictionSourceBadge';
import { formatUnitProbability } from '@/components/ui/probability';
import { hideBrokenImage } from '@/components/ui/imageFallback';
import { getErrorMessage } from '@/utils/errors';

/**
 * Expert Dashboard Page Component
 */
const ExpertDashboardPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<ExpertPerformanceMetrics | null>(null);
  const [recentPredictions, setRecentPredictions] = useState<ExpertPredictionResponse[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ExpertPredictionResponse[]>([]);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const loadDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // Load performance metrics
      const metricsData = await expertPredictionService.getPerformanceMetrics();
      setMetrics(metricsData);
      setRecentPredictions(metricsData.recent_predictions || []);

      // Load the post-publication moderation queue
      const queueData = await expertPredictionService.getReviewQueue({ limit: 5 });
      setReviewQueue(queueData);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
      setError(getErrorMessage(err, 'Failed to load dashboard data'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const handleTogglePublish = async (predictionId: string) => {
    try {
      setProcessingId(predictionId);
      setError(null);
      await expertPredictionService.togglePublishStatus(predictionId);
      // Reload dashboard data
      await loadDashboardData();
    } catch (err) {
      console.error('Failed to toggle publish status:', err);
      setError(getErrorMessage(err, 'Failed to toggle publish status'));
    } finally {
      setProcessingId(null);
    }
  };

  const handleDelete = async (predictionId: string) => {
    if (!confirm('Are you sure you want to delete this prediction? This action cannot be undone.')) {
      return;
    }

    try {
      setProcessingId(predictionId);
      setError(null);
      await expertPredictionService.deletePrediction(predictionId);
      // Reload dashboard data
      await loadDashboardData();
    } catch (err) {
      console.error('Failed to delete prediction:', err);
      setError(getErrorMessage(err, 'Failed to delete prediction'));
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="text-red-600 text-xl mb-4">⚠️ Error</div>
          <p className="text-gray-600 dark:text-gray-400">{error}</p>
          <button
            onClick={loadDashboardData}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          Expert Dashboard
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Manage your predictions and track your performance
        </p>
      </div>

      {/* Performance Metrics */}
      {metrics && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {/* Total Predictions */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600 dark:text-gray-400">Total Predictions</p>
                <p className="text-3xl font-bold text-gray-900 dark:text-white mt-2">
                  {metrics.total_predictions}
                </p>
              </div>
              <div className="text-4xl">📊</div>
            </div>
          </div>

          {/* Published */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600 dark:text-gray-400">Published</p>
                <p className="text-3xl font-bold text-green-600 mt-2">
                  {metrics.published_predictions}
                </p>
              </div>
              <div className="text-4xl">✅</div>
            </div>
          </div>

          {/* Pending */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600 dark:text-gray-400">Pending</p>
                <p className="text-3xl font-bold text-yellow-600 mt-2">
                  {metrics.pending_predictions}
                </p>
              </div>
              <div className="text-4xl">⏳</div>
            </div>
          </div>

          {/* Accuracy */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600 dark:text-gray-400">Accuracy</p>
                <p className="text-3xl font-bold text-blue-600 mt-2">
                  {formatUnitProbability(metrics.accuracy_rate, 1, 'Not scored')}
                </p>
                {metrics.accuracy_rate === null && (
                  <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                    No predictions have been settled against final results yet.
                  </p>
                )}
              </div>
              <div className="text-4xl">🎯</div>
            </div>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <Link
          to="/expert/match-selection"
          className="bg-purple-600 hover:bg-purple-700 text-white rounded-lg shadow p-6 flex items-center justify-between transition-colors"
        >
          <div>
            <h3 className="text-lg font-semibold mb-1">Create Prediction</h3>
            <p className="text-sm text-purple-100">Select a match and create prediction</p>
          </div>
          <div className="text-3xl">➕</div>
        </Link>

        <Link
          to="/expert/predictions/review-queue"
          className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow p-6 flex items-center justify-between transition-colors"
        >
          <div>
            <h3 className="text-lg font-semibold mb-1">Moderation Queue</h3>
            <p className="text-sm text-blue-100">
              {reviewQueue.length} flagged for review — your predictions publish without waiting for it
            </p>
          </div>
          <div className="text-3xl">📋</div>
        </Link>

        <Link
          to="/expert/predictions/my-predictions"
          className="bg-green-600 hover:bg-green-700 text-white rounded-lg shadow p-6 flex items-center justify-between transition-colors"
        >
          <div>
            <h3 className="text-lg font-semibold mb-1">My Predictions</h3>
            <p className="text-sm text-green-100">View all your predictions</p>
          </div>
          <div className="text-3xl">📝</div>
        </Link>
      </div>

      {/* Recent Predictions */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow mb-8">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Recent Predictions
          </h2>
        </div>
        <div className="p-6">
          {recentPredictions.length === 0 ? (
            <p className="text-gray-600 dark:text-gray-400 text-center py-8">
              No predictions yet. Create your first prediction!
            </p>
          ) : (
            <div className="space-y-4">
              {recentPredictions.map((prediction) => (
                <div
                  key={prediction.id}
                  className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <PredictionSourceBadge source={prediction.source} size="sm" />
                      <PredictionStatusBadge status={prediction.status} size="sm" />
                    </div>
                    <ConfidenceBadge confidence={prediction.confidence_score} size="sm" />
                  </div>

                  {/* Match Info */}
                  {prediction.match_details && (
                    <div className="flex items-center gap-3 mb-3">
                      {/* Home Team */}
                      <div className="flex items-center gap-2 flex-1">
                        {prediction.match_details.home_team_logo && (
                          <img
                            src={prediction.match_details.home_team_logo}
                            alt={prediction.match_details.home_team_name}
                            className="w-5 h-5 object-contain"
                            onError={hideBrokenImage}
                          />
                        )}
                        <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                          {prediction.match_details.home_team_name}
                        </span>
                      </div>

                      <span className="text-xs text-gray-500 dark:text-gray-400">vs</span>

                      {/* Away Team */}
                      <div className="flex items-center gap-2 flex-1 justify-end">
                        <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                          {prediction.match_details.away_team_name}
                        </span>
                        {prediction.match_details.away_team_logo && (
                          <img
                            src={prediction.match_details.away_team_logo}
                            alt={prediction.match_details.away_team_name}
                            className="w-5 h-5 object-contain"
                            onError={hideBrokenImage}
                          />
                        )}
                      </div>
                    </div>
                  )}

                  {/* Match Outcome (1X2) */}
                  <div className="mb-3">
                    <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">Match Outcome</p>
                    <div className="grid grid-cols-3 gap-4">
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
                  </div>

                  {/* Both Teams to Score (BTTS) - Optional */}
                  {prediction.btts_yes_prob !== null && prediction.btts_yes_prob !== undefined && (
                    <div className="mb-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                      <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Both Teams to Score (BTTS)
                        {prediction.btts_confidence && (
                          <span className="ml-2 text-blue-600 dark:text-blue-400">
                            {formatUnitProbability(prediction.btts_confidence, 0)} confidence
                          </span>
                        )}
                      </p>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs text-gray-600 dark:text-gray-400">Yes</p>
                          <p className="text-base font-semibold text-gray-900 dark:text-white">
                            {formatUnitProbability(prediction.btts_yes_prob, 1)}
                          </p>
                        </div>
                        {prediction.btts_no_prob !== null && prediction.btts_no_prob !== undefined && (
                          <div>
                            <p className="text-xs text-gray-600 dark:text-gray-400">No</p>
                            <p className="text-base font-semibold text-gray-900 dark:text-white">
                              {formatUnitProbability(prediction.btts_no_prob, 1)}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Total Goals - Optional */}
                  {((prediction.total_goals_over_25_prob !== null && prediction.total_goals_over_25_prob !== undefined) ||
                    (prediction.total_goals_under_25_prob !== null && prediction.total_goals_under_25_prob !== undefined) ||
                    (prediction.total_goals_over_35_prob !== null && prediction.total_goals_over_35_prob !== undefined) ||
                    (prediction.total_goals_under_35_prob !== null && prediction.total_goals_under_35_prob !== undefined)) && (
                    <div className="mb-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                      <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Total Goals
                        {prediction.total_goals_confidence && (
                          <span className="ml-2 text-green-600 dark:text-green-400">
                            {formatUnitProbability(prediction.total_goals_confidence, 0)} confidence
                          </span>
                        )}
                      </p>
                      <div className="grid grid-cols-2 gap-4">
                        {prediction.total_goals_over_25_prob !== null && prediction.total_goals_over_25_prob !== undefined && (
                          <div>
                            <p className="text-xs text-gray-600 dark:text-gray-400">Over 2.5</p>
                            <p className="text-base font-semibold text-gray-900 dark:text-white">
                              {formatUnitProbability(prediction.total_goals_over_25_prob, 1)}
                            </p>
                          </div>
                        )}
                        {prediction.total_goals_under_25_prob !== null && prediction.total_goals_under_25_prob !== undefined && (
                          <div>
                            <p className="text-xs text-gray-600 dark:text-gray-400">Under 2.5</p>
                            <p className="text-base font-semibold text-gray-900 dark:text-white">
                              {formatUnitProbability(prediction.total_goals_under_25_prob, 1)}
                            </p>
                          </div>
                        )}
                        {prediction.total_goals_over_35_prob !== null && prediction.total_goals_over_35_prob !== undefined && (
                          <div>
                            <p className="text-xs text-gray-600 dark:text-gray-400">Over 3.5</p>
                            <p className="text-base font-semibold text-gray-900 dark:text-white">
                              {formatUnitProbability(prediction.total_goals_over_35_prob, 1)}
                            </p>
                          </div>
                        )}
                        {prediction.total_goals_under_35_prob !== null && prediction.total_goals_under_35_prob !== undefined && (
                          <div>
                            <p className="text-xs text-gray-600 dark:text-gray-400">Under 3.5</p>
                            <p className="text-base font-semibold text-gray-900 dark:text-white">
                              {formatUnitProbability(prediction.total_goals_under_35_prob, 1)}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Reasoning */}
                  {prediction.reasoning && (
                    <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                      {prediction.reasoning}
                    </p>
                  )}
                  <div className="flex items-center justify-between mt-3">
                    <p className="text-xs text-gray-500 dark:text-gray-500">
                      Created {new Date(prediction.created_at).toLocaleDateString()}
                    </p>
                    <div className="flex items-center gap-2">
                      {/* Toggle Publish/Unpublish Button */}
                      {(prediction.status.toLowerCase() === 'published' || prediction.status.toLowerCase() === 'archived') && (
                        <button
                          onClick={() => handleTogglePublish(prediction.id)}
                          disabled={processingId === prediction.id}
                          className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                            prediction.status.toLowerCase() === 'published'
                              ? 'bg-yellow-100 text-yellow-800 hover:bg-yellow-200 dark:bg-yellow-900 dark:text-yellow-200'
                              : 'bg-green-100 text-green-800 hover:bg-green-200 dark:bg-green-900 dark:text-green-200'
                          } ${processingId === prediction.id ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                          {processingId === prediction.id ? (
                            'Processing...'
                          ) : prediction.status.toLowerCase() === 'published' ? (
                            'Unpublish'
                          ) : (
                            'Publish'
                          )}
                        </button>
                      )}
                      {/* Delete Button */}
                      {(prediction.status.toLowerCase() === 'rejected' || prediction.status.toLowerCase() === 'published' || prediction.status.toLowerCase() === 'archived') && (
                        <button
                          onClick={() => handleDelete(prediction.id)}
                          disabled={processingId === prediction.id}
                          className={`px-3 py-1 text-xs font-medium rounded-md bg-red-100 text-red-800 hover:bg-red-200 dark:bg-red-900 dark:text-red-200 transition-colors ${
                            processingId === prediction.id ? 'opacity-50 cursor-not-allowed' : ''
                          }`}
                        >
                          {processingId === prediction.id ? 'Deleting...' : 'Delete'}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Review Queue Preview */}
      {reviewQueue.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                Flagged for moderation
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Already published — moderation happens after publication, it is not an approval gate.
              </p>
            </div>
            <Link
              to="/expert/predictions/review-queue"
              className="text-blue-600 hover:text-blue-700 text-sm font-medium"
            >
              View All →
            </Link>
          </div>
          <div className="p-6">
            <div className="space-y-3">
              {reviewQueue.slice(0, 3).map((prediction) => (
                <div
                  key={prediction.id}
                  className="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded-lg"
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <PredictionSourceBadge source={prediction.source} size="sm" showLabel={false} />
                    <div className="flex-1 min-w-0">
                      {prediction.match_details ? (
                        <div className="flex items-center gap-2">
                          {prediction.match_details.home_team_logo && (
                            <img
                              src={prediction.match_details.home_team_logo}
                              alt={prediction.match_details.home_team_name}
                              className="w-4 h-4 object-contain flex-shrink-0"
                              onError={hideBrokenImage}
                            />
                          )}
                          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                            {prediction.match_details.home_team_name} vs {prediction.match_details.away_team_name}
                          </p>
                          {prediction.match_details.away_team_logo && (
                            <img
                              src={prediction.match_details.away_team_logo}
                              alt={prediction.match_details.away_team_name}
                              className="w-4 h-4 object-contain flex-shrink-0"
                              onError={hideBrokenImage}
                            />
                          )}
                        </div>
                      ) : (
                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                          Match {prediction.match_id.substring(0, 8)}...
                        </p>
                      )}
                      <p className="text-xs text-gray-500 dark:text-gray-500">
                        {new Date(prediction.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                  <PredictionStatusBadge status={prediction.status} size="sm" />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ExpertDashboardPage;

