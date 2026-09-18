/**
 * Expert Create Prediction Page
 * Page for experts to create manual predictions
 */

import React, { useState, useEffect } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import expertPredictionService from '../services/expert-prediction.service';
import {
  ExpertPredictionCreateRequest,
  validateProbabilities,
} from '../types/expert';
import { formatUnitProbability } from '@/components/ui/probability';
import { getErrorMessage } from '@/utils/errors';

const ExpertCreatePredictionPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [formData, setFormData] = useState<ExpertPredictionCreateRequest>({
    match_id: '',
    // Match Outcome (1X2)
    home_win_prob: 0.33,
    draw_prob: 0.33,
    away_win_prob: 0.34,
    confidence_score: 0.75,
    // Both Teams to Score (BTTS) - Optional
    btts_yes_prob: undefined,
    btts_no_prob: undefined,
    btts_confidence: undefined,
    // Total Goals - Optional
    total_goals_over_25_prob: undefined,
    total_goals_under_25_prob: undefined,
    total_goals_over_35_prob: undefined,
    total_goals_under_35_prob: undefined,
    total_goals_confidence: undefined,
    // Reasoning & Metadata
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
        // Match Outcome (1X2)
        home_win_prob: 0.33,
        draw_prob: 0.33,
        away_win_prob: 0.34,
        confidence_score: 0.75,
        // Both Teams to Score (BTTS) - Optional
        btts_yes_prob: undefined,
        btts_no_prob: undefined,
        btts_confidence: undefined,
        // Total Goals - Optional
        total_goals_over_25_prob: undefined,
        total_goals_under_25_prob: undefined,
        total_goals_over_35_prob: undefined,
        total_goals_under_35_prob: undefined,
        total_goals_confidence: undefined,
        // Reasoning & Metadata
        reasoning: '',
        key_factors: {},
      });

      // Redirect to Expert Dashboard after 1.5 seconds to show success message
      setTimeout(() => {
        navigate('/expert/dashboard');
      }, 1500);
    } catch (err) {
      console.error('Failed to create prediction:', err);
      setError(getErrorMessage(err, 'Failed to create prediction'));
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
          Create a new expert prediction for a match. It publishes straight away — there is no
          approval step, and the optional markets you leave blank stay blank rather than defaulting to zero.
        </p>
      </div>

      {/* Success Message */}
      {success && (
        <div className="mb-6 p-4 bg-green-100 border border-green-400 text-green-700 rounded-lg">
          ✅ Prediction published! It is now live on the public match pages.
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
                  {formatUnitProbability(formData.home_win_prob, 1)}
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
                  {formatUnitProbability(formData.draw_prob, 1)}
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
                  {formatUnitProbability(formData.away_win_prob, 1)}
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
              {formatUnitProbability(formData.confidence_score, 0)} confidence
            </p>
          </div>

          {/* Both Teams to Score (BTTS) - Optional */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Both Teams to Score (BTTS) - Optional
            </h3>

            <div className="grid grid-cols-2 gap-4 mb-4">
              {/* BTTS Yes */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Yes (Both Score)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={formData.btts_yes_prob ?? ''}
                  onChange={(e) => setFormData({ ...formData, btts_yes_prob: e.target.value ? parseFloat(e.target.value) : undefined })}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  placeholder="0.50"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {formatUnitProbability(formData.btts_yes_prob, 1, 'not set')}
                </p>
              </div>

              {/* BTTS No */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  No (At Least One Won't Score)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={formData.btts_no_prob ?? ''}
                  onChange={(e) => setFormData({ ...formData, btts_no_prob: e.target.value ? parseFloat(e.target.value) : undefined })}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  placeholder="0.50"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {formatUnitProbability(formData.btts_no_prob, 1, 'not set')}
                </p>
              </div>
            </div>

            {formData.btts_yes_prob !== undefined && formData.btts_no_prob !== undefined && (
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                Total: {((formData.btts_yes_prob + formData.btts_no_prob) * 100).toFixed(1)}%
                {Math.abs((formData.btts_yes_prob + formData.btts_no_prob) - 1.0) > 0.01 && (
                  <span className="text-red-600 ml-2">⚠️ Must sum to 100%</span>
                )}
              </p>
            )}

            {/* BTTS Confidence */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                BTTS Confidence (0-1)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={formData.btts_confidence ?? ''}
                onChange={(e) => setFormData({ ...formData, btts_confidence: e.target.value ? parseFloat(e.target.value) : undefined })}
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="0.75"
              />
              <p className="text-xs text-gray-500 mt-1">
                {formatUnitProbability(formData.btts_confidence, 0, 'not set')} confidence
              </p>
            </div>
          </div>

          {/* Total Goals - Optional */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Total Goals (Over/Under) - Optional
            </h3>

            <div className="grid grid-cols-2 gap-4 mb-4">
              {/* Over 2.5 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Over 2.5 Goals
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={formData.total_goals_over_25_prob ?? ''}
                  onChange={(e) => setFormData({ ...formData, total_goals_over_25_prob: e.target.value ? parseFloat(e.target.value) : undefined })}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  placeholder="0.50"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {formatUnitProbability(formData.total_goals_over_25_prob, 1, 'not set')}
                </p>
              </div>

              {/* Under 2.5 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Under 2.5 Goals
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={formData.total_goals_under_25_prob ?? ''}
                  onChange={(e) => setFormData({ ...formData, total_goals_under_25_prob: e.target.value ? parseFloat(e.target.value) : undefined })}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  placeholder="0.50"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {formatUnitProbability(formData.total_goals_under_25_prob, 1, 'not set')}
                </p>
              </div>

              {/* Over 3.5 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Over 3.5 Goals
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={formData.total_goals_over_35_prob ?? ''}
                  onChange={(e) => setFormData({ ...formData, total_goals_over_35_prob: e.target.value ? parseFloat(e.target.value) : undefined })}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  placeholder="0.30"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {formatUnitProbability(formData.total_goals_over_35_prob, 1, 'not set')}
                </p>
              </div>

              {/* Under 3.5 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Under 3.5 Goals
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={formData.total_goals_under_35_prob ?? ''}
                  onChange={(e) => setFormData({ ...formData, total_goals_under_35_prob: e.target.value ? parseFloat(e.target.value) : undefined })}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  placeholder="0.70"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {formatUnitProbability(formData.total_goals_under_35_prob, 1, 'not set')}
                </p>
              </div>
            </div>

            {/* Total Goals Confidence */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Total Goals Confidence (0-1)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={formData.total_goals_confidence ?? ''}
                onChange={(e) => setFormData({ ...formData, total_goals_confidence: e.target.value ? parseFloat(e.target.value) : undefined })}
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="0.75"
              />
              <p className="text-xs text-gray-500 mt-1">
                {formatUnitProbability(formData.total_goals_confidence, 0, 'not set')} confidence
              </p>
            </div>
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

