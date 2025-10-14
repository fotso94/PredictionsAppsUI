/**
 * Expert My Predictions Page
 * Page for experts to view their own predictions
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import expertPredictionService from '../services/expert-prediction.service';
import { ExpertPredictionResponse, PredictionStatus, ExpertPredictionUpdateRequest } from '../types/expert';
import {
  PredictionSourceBadge,
  PredictionStatusBadge,
  ConfidenceBadge,
} from '../components/PredictionSourceBadge';

const ExpertMyPredictionsPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [predictions, setPredictions] = useState<ExpertPredictionResponse[]>([]);
  const [page, setPage] = useState(0);
  const [limit] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<ExpertPredictionUpdateRequest | null>(null);

  useEffect(() => {
    loadMyPredictions();
  }, [page, statusFilter]);

  const loadMyPredictions = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await expertPredictionService.getMyPredictions({
        limit,
        offset: page * limit,
        status: statusFilter === 'all' ? undefined : statusFilter,
      });
      setPredictions(data);
    } catch (err: any) {
      console.error('Failed to load predictions:', err);
      setError(err.response?.data?.detail || 'Failed to load predictions');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (prediction: ExpertPredictionResponse) => {
    setEditingId(prediction.id);
    setEditForm({
      home_win_prob: prediction.home_win_prob,
      draw_prob: prediction.draw_prob,
      away_win_prob: prediction.away_win_prob,
      confidence_score: prediction.confidence_score,
      reasoning: prediction.reasoning || undefined,
      key_factors: prediction.key_factors || undefined,
    });
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditForm(null);
  };

  const handleSaveEdit = async (predictionId: string) => {
    if (!editForm) return;

    try {
      setProcessingId(predictionId);
      setError(null);
      await expertPredictionService.updatePrediction(predictionId, editForm);
      setEditingId(null);
      setEditForm(null);
      // Reload predictions
      await loadMyPredictions();
    } catch (err: any) {
      console.error('Failed to update prediction:', err);
      setError(err.response?.data?.detail || 'Failed to update prediction');
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
      // Reload predictions
      await loadMyPredictions();
    } catch (err: any) {
      console.error('Failed to delete prediction:', err);
      setError(err.response?.data?.detail || 'Failed to delete prediction');
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading predictions...</p>
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
          My Predictions
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          View and manage all your expert predictions
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg">
          ⚠️ {error}
        </div>
      )}

      {/* Filters */}
      <div className="mb-6 bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <div className="flex items-center gap-4">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Filter by Status:
          </label>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(0);
            }}
            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="under_review">Under Review</option>
            <option value="approved">Approved</option>
            <option value="published">Published</option>
            <option value="rejected">Rejected</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </div>

      {/* Predictions List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Your Predictions ({predictions.length})
          </h2>
        </div>

        <div className="p-6">
          {predictions.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400 text-lg mb-4">
                📝 No predictions found
              </p>
              <p className="text-gray-500 dark:text-gray-500 text-sm mb-6">
                {statusFilter === 'all'
                  ? "You haven't created any predictions yet."
                  : `No predictions with status "${statusFilter}".`}
              </p>
              <Link
                to="/expert/predictions/create"
                className="inline-block px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                Create Your First Prediction
              </Link>
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
                      Created: {new Date(prediction.created_at).toLocaleString()}
                    </p>
                    {prediction.published_at && (
                      <p className="text-xs text-gray-500 dark:text-gray-500">
                        Published: {new Date(prediction.published_at).toLocaleString()}
                      </p>
                    )}
                  </div>

                  {/* Probabilities */}
                  {editingId === prediction.id && editForm ? (
                    <div className="mb-3 p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                        Edit Probabilities (must sum to 1.0):
                      </p>
                      <div className="grid grid-cols-3 gap-4 mb-3">
                        <div>
                          <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
                            Home Win
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            value={editForm.home_win_prob}
                            onChange={(e) => setEditForm({ ...editForm, home_win_prob: parseFloat(e.target.value) || 0 })}
                            className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
                            Draw
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            value={editForm.draw_prob}
                            onChange={(e) => setEditForm({ ...editForm, draw_prob: parseFloat(e.target.value) || 0 })}
                            className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
                            Away Win
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            value={editForm.away_win_prob}
                            onChange={(e) => setEditForm({ ...editForm, away_win_prob: parseFloat(e.target.value) || 0 })}
                            className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                          />
                        </div>
                      </div>
                      <div className="mb-3">
                        <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
                          Confidence Score (0-1)
                        </label>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max="1"
                          value={editForm.confidence_score || 0}
                          onChange={(e) => setEditForm({ ...editForm, confidence_score: parseFloat(e.target.value) || undefined })}
                          className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
                          Reasoning
                        </label>
                        <textarea
                          value={editForm.reasoning || ''}
                          onChange={(e) => setEditForm({ ...editForm, reasoning: e.target.value || undefined })}
                          rows={3}
                          className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        />
                      </div>
                    </div>
                  ) : (
                    <>
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
                    </>
                  )}

                  {/* Superseded Info */}
                  {prediction.superseded_by && (
                    <div className="mb-3 p-2 bg-yellow-100 dark:bg-yellow-900 rounded">
                      <p className="text-xs text-yellow-800 dark:text-yellow-200">
                        ⚠️ This prediction has been superseded by a newer version
                      </p>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2 mt-4">
                    {editingId === prediction.id ? (
                      <>
                        <button
                          onClick={() => handleSaveEdit(prediction.id)}
                          disabled={processingId === prediction.id}
                          className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          {processingId === prediction.id ? 'Saving...' : 'Save Changes'}
                        </button>
                        <button
                          onClick={handleCancelEdit}
                          disabled={processingId === prediction.id}
                          className="px-4 py-2 bg-gray-600 text-white text-sm rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <Link
                          to={`/expert/predictions/${prediction.id}`}
                          className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors inline-block"
                        >
                          View Details
                        </Link>
                        {prediction.status === 'pending' && (
                          <>
                            <button
                              onClick={() => handleEdit(prediction)}
                              disabled={processingId === prediction.id}
                              className="px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleDelete(prediction.id)}
                              disabled={processingId === prediction.id}
                              className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                              {processingId === prediction.id ? 'Deleting...' : 'Delete'}
                            </button>
                          </>
                        )}
                      </>
                    )}
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

export default ExpertMyPredictionsPage;

