/**
 * Expert Moderation Queue Page
 *
 * This is a POST-PUBLICATION moderation view, not an approval gate: an expert's prediction goes
 * live on the public match pages the moment they publish it, and nothing here has to happen first.
 * Approving marks a prediction as checked; rejecting withdraws one that is already public. The
 * wording throughout says so, because "Review Queue / pending review / Approve" on its own reads as
 * a gate that does not exist.
 *
 * ── THAT CLAIM HAD TO SURVIVE THE TRANSLATION ───────────────────────────────────
 *
 * The whole point of the notice at the top of this page is that a moderator does not gate
 * publication. « La publication n'attend pas cette file » keeps that in the indicative and keeps
 * the negation on the verb, so it cannot be read as "publication should not wait" or "may not
 * need to wait". A French reader must reach the same conclusion an English one does: whatever
 * happens here, the prediction is already public.
 *
 * ── EVERY DATE IS IN THE READER'S CHOSEN ZONE ──────────────────────────────────
 *
 * Three `toLocaleDateString` / `toLocaleString` calls used to format in the device's zone and the
 * device's locale. A moderator deciding whether a flagged prediction was published before its
 * kick-off is reading those timestamps for a reason, so they go through `backendInstant` (these
 * columns are Z-anchored by `to_utc_iso_z` in backend/app/schemas/predictions.py) and then
 * `formatDate` / `formatDateTime`.
 *
 * ── WHAT IS STILL ENGLISH ──────────────────────────────────────────────────
 *
 * The three badges — source, status and confidence — come from components/PredictionSourceBadge,
 * which this package does not own. The status badge renders the backend's own word deliberately;
 * the other two are untranslated and recorded in the package report.
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
import { backendInstant, formatDate, formatDateTime, formatNumber } from '@/i18n';
import { useT } from '@/i18n/react';

const ExpertReviewQueuePage: React.FC = () => {
  const t = useT();
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
      setError(getErrorMessage(err, t('expert.queue.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [limit, page, t]);

  useEffect(() => {
    loadReviewQueue();
  }, [loadReviewQueue]);

  /*
   * A kick-off as a date and a record timestamp as a date and time, both in the reader's CHOSEN
   * zone. `backendInstant` reads the instant the server actually wrote rather than letting
   * ECMAScript apply the device's offset to an unanchored string.
   */
  const kickoffOn = (value: string | null | undefined): string | null =>
    formatDate(backendInstant(value).at);
  const stampOf = (value: string | null | undefined): string =>
    formatDateTime(backendInstant(value).at) ?? '';

  /**
   * Who wrote it, exactly as the account published it: a username, with the person's own name in
   * brackets when the payload carries both halves. Never translated, never reordered.
   */
  const authorOf = (prediction: ExpertPredictionResponse): string => {
    const handle = prediction.user_details?.username || prediction.created_by;
    const first = prediction.user_details?.first_name;
    const last = prediction.user_details?.last_name;
    return first && last ? `${handle} (${first} ${last})` : handle;
  };

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
      setError(getErrorMessage(err, t('expert.queue.approveFailed')));
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (predictionId: string) => {
    try {
      setProcessingId(predictionId);
      setError(null);
      const reason = prompt(t('expert.queue.withdrawPrompt'));
      await expertPredictionService.rejectPrediction(predictionId, reason || undefined);
      // Reload the queue
      await loadReviewQueue();
    } catch (err) {
      console.error('Failed to reject prediction:', err);
      setError(getErrorMessage(err, t('expert.queue.rejectFailed')));
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">{t('expert.queue.loading')}</p>
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
          ← {t('expert.backToDashboardCaps')}
        </Link>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          {t('expert.queue.title')}
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          {t('expert.queue.intro')}
        </p>
        <div
          className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200"
          role="note"
          data-testid="no-approval-gate-notice"
        >
          <p className="font-semibold">{t('expert.queue.noticeTitle')}</p>
          <p className="mt-1">{t('expert.queue.noticeBody')}</p>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg">
          {/* The error text is the backend's own words, rendered as it sent them. */}
          <span aria-hidden="true">⚠️</span> {error}
        </div>
      )}

      {/* Predictions List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            {t('expert.queue.listHeading', { count: formatNumber(predictions.length) })}
          </h2>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t('expert.queue.listNote')}
          </p>
        </div>

        <div className="p-6">
          {predictions.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400 text-lg mb-4">
                <span aria-hidden="true">📋</span> {t('expert.queue.emptyTitle')}
              </p>
              <p className="text-gray-500 dark:text-gray-500 text-sm">
                {t('expert.queue.emptyBody')}
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

                        <span className="text-sm text-gray-500 dark:text-gray-400">{t('expert.versusShort')}</span>

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
                        {t('expert.mine.matchIdLabel')} <span className="font-mono">{prediction.match_id}</span>
                      </p>
                    )}

                    {prediction.match_details?.league_name && (
                      <p className="text-xs text-gray-500 dark:text-gray-500 mb-1">
                        {prediction.match_details.league_name}
                        {kickoffOn(prediction.match_details.match_date) && (
                          <> • {kickoffOn(prediction.match_details.match_date)}</>
                        )}
                      </p>
                    )}

                    {/* One catalogue sentence with both holes in it, so a language that puts the
                        timestamp before the author can say so. `who` is the account's own name. */}
                    <p className="text-xs text-gray-500 dark:text-gray-500">
                      {t('expert.queue.createdByAt', {
                        who: authorOf(prediction),
                        timestamp: stampOf(prediction.created_at),
                      })}
                    </p>
                  </div>

                  {/* Probabilities */}
                  <div className="grid grid-cols-3 gap-4 mb-3">
                    <div>
                      <p className="text-xs text-gray-600 dark:text-gray-400">{t('expert.mine.homeWin')}</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {formatUnitProbability(prediction.home_win_prob, 1)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-600 dark:text-gray-400">{t('expert.mine.draw')}</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {formatUnitProbability(prediction.draw_prob, 1)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-600 dark:text-gray-400">{t('expert.mine.awayWin')}</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {formatUnitProbability(prediction.away_win_prob, 1)}
                      </p>
                    </div>
                  </div>

                  {/* Reasoning */}
                  {prediction.reasoning && (
                    <div className="mb-3">
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('expert.reasoningLabel')}
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
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.details.predictionId')}</dt>
                          <dd className="font-mono text-gray-800 dark:text-gray-200 break-all">{prediction.id}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.details.matchId')}</dt>
                          <dd className="font-mono text-gray-800 dark:text-gray-200 break-all">{prediction.match_id}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.details.bttsPair')}</dt>
                          {/* Never 0%: a side the expert did not publish says it was not set. */}
                          <dd className="text-gray-800 dark:text-gray-200">
                            {formatUnitProbability(prediction.btts_yes_prob, 1, t('probability.notSet'))} / {formatUnitProbability(prediction.btts_no_prob, 1, t('probability.notSet'))}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.line.overUnder', { line: formatNumber(2.5) })}</dt>
                          <dd className="text-gray-800 dark:text-gray-200">
                            {formatUnitProbability(prediction.total_goals_over_25_prob, 1, t('probability.notSet'))} / {formatUnitProbability(prediction.total_goals_under_25_prob, 1, t('probability.notSet'))}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.line.overUnder', { line: formatNumber(3.5) })}</dt>
                          <dd className="text-gray-800 dark:text-gray-200">
                            {formatUnitProbability(prediction.total_goals_over_35_prob, 1, t('probability.notSet'))} / {formatUnitProbability(prediction.total_goals_under_35_prob, 1, t('probability.notSet'))}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.details.published')}</dt>
                          <dd className="text-gray-800 dark:text-gray-200">
                            {stampOf(prediction.published_at) || t('expert.details.notPublished')}
                          </dd>
                        </div>
                      </dl>
                      {prediction.key_factors && Object.keys(prediction.key_factors).length > 0 && (
                        <div className="mt-3">
                          <p className="text-gray-500 dark:text-gray-400 mb-1">{t('expert.details.keyFactors')}</p>
                          <ul className="list-disc list-inside space-y-0.5 text-gray-800 dark:text-gray-200">
                            {Object.entries(prediction.key_factors).map(([key, value]) => (
                              <li key={key}>{t('expert.details.factor', { name: key, value: String(value) })}</li>
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
                      title={t('expert.queue.markCheckedHint')}
                      className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {processingId === prediction.id ? t('expert.action.processing') : t('expert.queue.markChecked')}
                    </button>
                    <button
                      onClick={() => handleReject(prediction.id)}
                      disabled={processingId === prediction.id}
                      title={t('expert.queue.withdrawHint')}
                      className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {processingId === prediction.id ? t('expert.action.processing') : t('expert.queue.withdraw')}
                    </button>
                    <button
                      onClick={() => toggleExpanded(prediction.id)}
                      aria-expanded={expandedIds.includes(prediction.id)}
                      className="px-4 py-2 bg-gray-600 text-white text-sm rounded-lg hover:bg-gray-700 transition-colors"
                    >
                      {expandedIds.includes(prediction.id) ? t('expert.action.hideDetails') : t('expert.action.viewDetails')}
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
              {t('expert.page.previous')}
            </button>
            <span className="text-gray-600 dark:text-gray-400">
              {t('expert.page.number', { number: formatNumber(page + 1) })}
            </span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={predictions.length < limit}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {t('expert.page.next')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ExpertReviewQueuePage;

