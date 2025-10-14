/**
 * Expert Dashboard Page
 * Dashboard for expert users to manage predictions (KAN-156)
 */

import React, { useEffect, useState } from 'react';
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

/**
 * Expert Dashboard Page Component
 */
const ExpertDashboardPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<ExpertPerformanceMetrics | null>(null);
  const [recentPredictions, setRecentPredictions] = useState<ExpertPredictionResponse[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ExpertPredictionResponse[]>([]);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load performance metrics
      const metricsData = await expertPredictionService.getPerformanceMetrics();
      setMetrics(metricsData);
      setRecentPredictions(metricsData.recent_predictions || []);

      // Load review queue
      const queueData = await expertPredictionService.getReviewQueue({ limit: 5 });
      setReviewQueue(queueData);
    } catch (err: any) {
      console.error('Failed to load dashboard data:', err);
      setError(err.response?.data?.detail || 'Failed to load dashboard data');
    } finally {
      setLoading(false);
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
                  {metrics.accuracy_rate !== null
                    ? `${(metrics.accuracy_rate * 100).toFixed(1)}%`
                    : 'N/A'}
                </p>
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
            <h3 className="text-lg font-semibold mb-1">Review Queue</h3>
            <p className="text-sm text-blue-100">{reviewQueue.length} pending review</p>
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
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                            }}
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
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                            }}
                          />
                        )}
                      </div>
                    </div>
                  )}

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
                  {prediction.reasoning && (
                    <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                      {prediction.reasoning}
                    </p>
                  )}
                  <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
                    Created {new Date(prediction.created_at).toLocaleDateString()}
                  </p>
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
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              Pending Review
            </h2>
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
                              onError={(e) => {
                                e.currentTarget.style.display = 'none';
                              }}
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
                              onError={(e) => {
                                e.currentTarget.style.display = 'none';
                              }}
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

