/**
 * Expert Create Prediction Page
 * Page for experts to create manual predictions
 */

import React, { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import expertPredictionService from '../services/expert-prediction.service';
import {
  ExpertPredictionCreateRequest,
  validateProbabilities,
  validateProbabilityRange,
} from '../types/expert';

const ExpertCreatePredictionPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [formData, setFormData] = useState<ExpertPredictionCreateRequest>({
    match_id: '',
    home_win_prob: 0.33,
    draw_prob: 0.33,
    away_win_prob: 0.34,
    confidence_score: 0.75,
    reasoning: '',
    key_factors: {},
  });

  // Pre-fill match ID from query parameter
  useEffect(() => {
    const matchId = searchParams.get('matchId');
    if (matchId) {
      setFormData(prev => ({ ...prev, match_id: matchId }));
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    // Validate probabilities
    const validation = validateProbabilities(
      formData.home_win_prob,
      formData.draw_prob,
      formData.away_win_prob
    );

    if (!validation.valid) {
      setError(validation.error || 'Invalid probabilities');
      return;
    }

    try {
      setLoading(true);
      await expertPredictionService.createManualPrediction(formData);
      setSuccess(true);
      
      // Reset form
      setFormData({
        match_id: '',
        home_win_prob: 0.33,
        draw_prob: 0.33,
        away_win_prob: 0.34,
        confidence_score: 0.75,
        reasoning: '',
        key_factors: {},
      });
    } catch (err: any) {
      console.error('Failed to create prediction:', err);
      setError(err.response?.data?.detail || 'Failed to create prediction');
    } finally {
      setLoading(false);
    }
  };

  const handleProbabilityChange = (field: 'home_win_prob' | 'draw_prob' | 'away_win_prob', value: string) => {
    const numValue = parseFloat(value) || 0;
    setFormData(prev => ({ ...prev, [field]: numValue }));
  };

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
          Create Manual Prediction
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Create a new expert prediction for a match
        </p>
      </div>

      {/* Success Message */}
      {success && (
        <div className="mb-6 p-4 bg-green-100 border border-green-400 text-green-700 rounded-lg">
          ✅ Prediction created successfully! It is now pending approval.
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg">
          ⚠️ {error}
        </div>
      )}

      {/* Form */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 max-w-2xl">
        <form onSubmit={handleSubmit}>
          {/* Match ID */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Match ID *
            </label>
            <input
              type="text"
              value={formData.match_id}
              onChange={(e) => setFormData({ ...formData, match_id: e.target.value })}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
              placeholder="Enter match UUID"
              required
            />
          </div>

          {/* Probabilities */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Probabilities (must sum to 1.0)
            </h3>
            
            <div className="grid grid-cols-3 gap-4">
              {/* Home Win */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Home Win
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={formData.home_win_prob}
                  onChange={(e) => handleProbabilityChange('home_win_prob', e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  {(formData.home_win_prob * 100).toFixed(1)}%
                </p>
              </div>

              {/* Draw */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Draw
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={formData.draw_prob}
                  onChange={(e) => handleProbabilityChange('draw_prob', e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  {(formData.draw_prob * 100).toFixed(1)}%
                </p>
              </div>

              {/* Away Win */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Away Win
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={formData.away_win_prob}
                  onChange={(e) => handleProbabilityChange('away_win_prob', e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  {(formData.away_win_prob * 100).toFixed(1)}%
                </p>
              </div>
            </div>

            <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
              Total: {((formData.home_win_prob + formData.draw_prob + formData.away_win_prob) * 100).toFixed(1)}%
            </p>
          </div>

          {/* Confidence Score */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Confidence Score (0-1)
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={formData.confidence_score}
              onChange={(e) => setFormData({ ...formData, confidence_score: parseFloat(e.target.value) || 0 })}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
            />
            <p className="text-xs text-gray-500 mt-1">
              {((formData.confidence_score || 0) * 100).toFixed(0)}% confidence
            </p>
          </div>

          {/* Reasoning */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Reasoning
            </label>
            <textarea
              value={formData.reasoning}
              onChange={(e) => setFormData({ ...formData, reasoning: e.target.value })}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
              rows={4}
              placeholder="Explain your prediction reasoning..."
            />
          </div>

          {/* Submit Button */}
          <div className="flex gap-4">
            <button
              type="submit"
              disabled={loading}
              className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Creating...' : 'Create Prediction'}
            </button>
            
            <Link
              to="/expert/dashboard"
              className="px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
            >
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ExpertCreatePredictionPage;

