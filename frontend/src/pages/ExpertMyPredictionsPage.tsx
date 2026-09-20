/**
 * What this expert has published, and everything they can still do to it.
 *
 * ── IN THE READER'S LANGUAGE ───────────────────────────────────────────────
 *
 * Two things on this page are load-bearing rather than decorative, and both are stated here so a
 * later edit cannot undo them by accident:
 *
 *   - A PROBABILITY THAT WAS NEVER PUBLISHED SAYS SO. Every optional market renders through
 *     `formatUnitProbability`, whose fallback is the catalogue's « non renseigné » /
 *     "not set" — never 0%, in either language. A market an expert declined to offer is not a
 *     market they rated at zero, and the French must not let it be read as one.
 *
 *     THE HEADLINE CONVICTION NOW BEHAVES THE SAME WAY, AND DID NOT USED TO. The fallback under
 *     `expert.details.confidence` was unreachable: predictions.confidence_score was NOT NULL and
 *     the expert service coerced a missing conviction to 0.0000, so the API could not express
 *     "not given" and this page faithfully printed 0% for it. The column, the service, the
 *     response model and this page now carry null end to end, so the fallback fires for real.
 *     Two consequences to keep: `ConfidenceBadge` takes a bare number and bands it, so it is
 *     rendered only for a conviction that exists; and every test here is `isPublished`, never
 *     `value &&`, because 0 is a conviction an expert may deliberately claim.
 *   - THE EDIT NOTICE IS A PROMISE ABOUT READERS. Saving keeps the prediction published and keeps
 *     the superseded version, so a reader can still see what was published before. The French
 *     says exactly that, in the same indicative.
 *
 * ── EVERY DATE HERE IS IN THE READER'S CHOSEN ZONE ────────────────────────────────
 *
 * Four `toLocaleDateString` / `toLocaleString` calls used to render the kick-off, the creation
 * time and two publication times. Every one of them formatted in the DEVICE's zone and the
 * DEVICE's locale, which for an expert judging whether a fixture is still prematch is a
 * correctness defect and not a cosmetic one. They go through `backendInstant` (this backend
 * anchors these columns with a trailing Z — see the field serialisers in
 * backend/app/schemas/predictions.py) and then `formatDate` / `formatDateTime`.
 *
 * ── WHAT IS STILL ENGLISH ──────────────────────────────────────────────────
 *
 * The inline editor is `components/expert/PredictionMarketsEditor`, and its validation messages
 * come from `components/expert/composer.ts`. Neither belongs to this package and neither is
 * translated, so a French expert correcting a number reads this page's frame in French and the
 * field labels and errors in English. The status BADGE beside each prediction renders the
 * backend's own word and is left that way deliberately. The package report lists all of it.
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
import { formatUnitProbability, isPublished } from '@/components/ui/probability';
import { hideBrokenImage } from '@/components/ui/imageFallback';
import { getErrorMessage } from '@/utils/errors';
import { backendInstant, formatDate, formatDateTime, formatNumber, formatPercentValue } from '@/i18n';
import { useT } from '@/i18n/react';
import type { MessageKey } from '@/i18n';
import PredictionMarketsEditor from '@/components/expert/PredictionMarketsEditor';
import {
  buildUpdateRequest, ComposerValues, composerFromPrediction, publishedMarkets, validateComposer,
} from '@/components/expert/composer';

/**
 * Statuses the API lets an expert edit: `update_prediction_with_revision` accepts PENDING,
 * APPROVED, PUBLISHED and ARCHIVED, and refuses REJECTED.
 */
const EDITABLE_STATUSES = ['pending', 'approved', 'published', 'archived'];

/** Statuses the API lets an expert delete: PENDING, REJECTED, PUBLISHED and ARCHIVED. */
const DELETABLE_STATUSES = ['pending', 'rejected', 'published', 'archived'];

const canEdit = (status: string): boolean => EDITABLE_STATUSES.includes((status || '').toLowerCase());
const canDelete = (status: string): boolean => DELETABLE_STATUSES.includes((status || '').toLowerCase());

/**
 * The status filter's own options.
 *
 * The VALUE is what the API is asked for and is never translated; the KEY names the label this
 * interface puts on our own select. The badge beside each prediction is a different thing
 * entirely — it renders the status the server sent, verbatim, in every language.
 */
const STATUS_OPTIONS: Array<{ value: string; key: MessageKey }> = [
  { value: 'all', key: 'expert.status.all' },
  { value: 'pending', key: 'expert.status.pending' },
  { value: 'under_review', key: 'expert.status.underReview' },
  { value: 'approved', key: 'expert.status.approved' },
  { value: 'published', key: 'expert.status.published' },
  { value: 'rejected', key: 'expert.status.rejected' },
  { value: 'archived', key: 'expert.status.archived' },
];

const ExpertMyPredictionsPage: React.FC = () => {
  const t = useT();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [predictions, setPredictions] = useState<ExpertPredictionResponse[]>([]);
  const [page, setPage] = useState(0);
  const [limit] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  /**
   * The prediction being edited, held as PERCENTAGES exactly as the composer holds them, so an
   * expert correcting a typo types 55 here as well and never has to remember that this one form
   * wanted 0.55. Null when nothing is being edited.
   */
  const [editValues, setEditValues] = useState<ComposerValues | null>(null);
  const [editShowErrors, setEditShowErrors] = useState(false);
  /** Ids whose full record is expanded in place — there is no separate detail route. */
  const [expandedIds, setExpandedIds] = useState<string[]>([]);

  /** The label our own select puts on a status value. Falls back to what the API was asked for. */
  const statusLabel = (value: string): string => {
    const option = STATUS_OPTIONS.find(entry => entry.value === value);
    return option ? t(option.key) : value;
  };

  /*
   * A kick-off as a date, and a record timestamp as a date and time — both in the reader's
   * CHOSEN zone and their language, never the device's.
   *
   * `backendInstant` is what makes the reading correct rather than merely localised: it reports
   * whether the payload named a zone, and reads an unanchored value as the UTC this backend
   * writes. These particular columns ARE anchored (`to_utc_iso_z` in
   * backend/app/schemas/predictions.py puts a trailing Z on match_date, created_at and
   * published_at), so `anchored` comes back true and there is nothing to caveat; routing through
   * it anyway means a serialiser that later stops anchoring is read correctly instead of being
   * silently shifted by whatever the expert's laptop is set to.
   */
  const kickoffOn = (value: string | null | undefined): string | null =>
    formatDate(backendInstant(value).at);
  const stampOf = (value: string | null | undefined): string =>
    formatDateTime(backendInstant(value).at) ?? '';

  /** The two examples the edit notice teaches with, formatted rather than written down. */
  const percentExamples = { typed: formatNumber(55), whole: formatPercentValue(55, 0) };

  const loadMyPredictions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await expertPredictionService.getMyPredictions({
        limit,
        offset: page * limit,
        status: statusFilter === 'all' ? undefined : statusFilter,
      });
      setPredictions(data);
    } catch (err) {
      console.error('Failed to load predictions:', err);
      setError(getErrorMessage(err, t('expert.mine.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [limit, page, statusFilter, t]);

  useEffect(() => {
    loadMyPredictions();
  }, [loadMyPredictions]);

  const toggleExpanded = (predictionId: string) => {
    setExpandedIds(prev =>
      prev.includes(predictionId) ? prev.filter(id => id !== predictionId) : [...prev, predictionId]
    );
  };

  const handleEdit = (prediction: ExpertPredictionResponse) => {
    setEditingId(prediction.id);
    // A market the prediction never published reopens unticked and empty — never at zero.
    setEditValues(composerFromPrediction(prediction));
    setEditShowErrors(false);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditValues(null);
    setEditShowErrors(false);
  };

  const handleSaveEdit = async (prediction: ExpertPredictionResponse) => {
    if (!editValues) return;

    // The same complementary-pair rules as the composer, checked here so the expert sees the
    // problem on the form rather than as a 422 after pressing save.
    const validation = validateComposer(editValues, prediction.match_id);
    const request = buildUpdateRequest(editValues);
    if (!validation.ready || !request) {
      setEditShowErrors(true);
      return;
    }

    try {
      setProcessingId(prediction.id);
      setError(null);
      await expertPredictionService.updatePrediction(prediction.id, request);
      setEditingId(null);
      setEditValues(null);
      setEditShowErrors(false);
      // Reload predictions
      await loadMyPredictions();
    } catch (err) {
      console.error('Failed to update prediction:', err);
      setError(getErrorMessage(err, t('expert.mine.updateFailed')));
    } finally {
      setProcessingId(null);
    }
  };

  const handleDelete = async (predictionId: string) => {
    if (!confirm(t('expert.mine.confirmDelete'))) {
      return;
    }

    try {
      setProcessingId(predictionId);
      setError(null);
      await expertPredictionService.deletePrediction(predictionId);
      // Reload predictions
      await loadMyPredictions();
    } catch (err) {
      console.error('Failed to delete prediction:', err);
      setError(getErrorMessage(err, t('expert.deleteFailed')));
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">{t('expert.mine.loading')}</p>
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
          {t('expert.mine.title')}
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          {t('expert.mine.intro')}
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg">
          {/* The error text is the backend's own words, rendered as it sent them. */}
          <span aria-hidden="true">⚠️</span> {error}
        </div>
      )}

      {/* Filters */}
      <div className="mb-6 bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <div className="flex items-center gap-4">
          <label htmlFor="status-filter" className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('expert.mine.filterByStatus')}
          </label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(0);
            }}
            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
          >
            {STATUS_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>{t(option.key)}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Predictions List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            {t('expert.mine.listHeading', { count: formatNumber(predictions.length) })}
          </h2>
        </div>

        <div className="p-6">
          {predictions.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400 text-lg mb-4">
                <span aria-hidden="true">📝</span> {t('expert.mine.emptyTitle')}
              </p>
              <p className="text-gray-500 dark:text-gray-500 text-sm mb-6">
                {/* The status named back to the reader is the LABEL on our own select, not the
                    raw `under_review` the API is asked for. */}
                {statusFilter === 'all'
                  ? t('expert.mine.emptyNone')
                  : t('expert.mine.emptyFiltered', { status: statusLabel(statusFilter) })}
              </p>
              <Link
                to="/expert/predictions/create"
                className="inline-block px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                {t('expert.mine.createFirst')}
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
                    {/*
                      The badge takes a plain number and derives its band from it, so a conviction
                      nobody supplied would come out of it as the lowest band at "0%" — the loudest
                      possible way of stating a figure that was never claimed. It is only rendered
                      for a conviction that exists; otherwise the row says « non renseigné », the
                      same wording the detail panel below uses for the same absence.
                    */}
                    {isPublished(prediction.confidence_score) ? (
                      <ConfidenceBadge confidence={prediction.confidence_score} size="sm" />
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                        {t('probability.notSet')}
                      </span>
                    )}
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

                    <p className="text-xs text-gray-500 dark:text-gray-500">
                      {t('expert.mine.created', { timestamp: stampOf(prediction.created_at) })}
                    </p>
                    {prediction.published_at && stampOf(prediction.published_at) && (
                      <p className="text-xs text-gray-500 dark:text-gray-500">
                        {t('expert.mine.published', { timestamp: stampOf(prediction.published_at) })}
                      </p>
                    )}
                  </div>

                  {/* Probabilities */}
                  {editingId === prediction.id && editValues ? (
                    <div className="mb-3 rounded-lg border border-dark-700 bg-dark-900/60 p-4">
                      <p className="mb-4 text-sm text-secondary-300">
                        {t('expert.mine.editNote', percentExamples)}
                      </p>
                      <PredictionMarketsEditor
                        values={editValues}
                        onChange={setEditValues}
                        validation={validateComposer(editValues, prediction.match_id)}
                        showErrors={editShowErrors}
                        homeTeam={prediction.match_details?.home_team_name}
                        awayTeam={prediction.match_details?.away_team_name}
                        idPrefix={`edit-${prediction.id}`}
                        lockedMarkets={publishedMarkets(prediction)}
                        disabled={processingId === prediction.id}
                      />
                      {editShowErrors && !validateComposer(editValues, prediction.match_id).ready && (
                        <p className="mt-4 text-sm text-warning-200" role="status">
                          {t('expert.mine.fixThenSave')}
                        </p>
                      )}
                    </div>
                  ) : (
                    <>
                      {/* Match Outcome (1X2) */}
                      <div className="mb-3">
                        <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">{t('expert.mine.matchOutcome')}</p>
                        <div className="grid grid-cols-3 gap-4">
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
                      </div>

                      {/* Both Teams to Score (BTTS) - Optional */}
                      {prediction.btts_yes_prob !== null && prediction.btts_yes_prob !== undefined && (
                        <div className="mb-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                            {t('expert.mine.bttsLong')}
                            {/* `is published`, not truthiness: a market rated at 0 was still
                                rated, and `&&` would have silently dropped it. */}
                            {isPublished(prediction.btts_confidence) && (
                              <span className="ml-2 text-blue-600 dark:text-blue-400">
                                {t('expert.mine.marketConfidence', { value: formatUnitProbability(prediction.btts_confidence, 0) })}
                              </span>
                            )}
                          </p>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <p className="text-xs text-gray-600 dark:text-gray-400">{t('expert.mine.yes')}</p>
                              <p className="text-base font-semibold text-gray-900 dark:text-white">
                                {formatUnitProbability(prediction.btts_yes_prob, 1)}
                              </p>
                            </div>
                            {prediction.btts_no_prob !== null && prediction.btts_no_prob !== undefined && (
                              <div>
                                <p className="text-xs text-gray-600 dark:text-gray-400">{t('expert.mine.no')}</p>
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
                            {t('expert.mine.totalGoals')}
                            {isPublished(prediction.total_goals_confidence) && (
                              <span className="ml-2 text-green-600 dark:text-green-400">
                                {t('expert.mine.marketConfidence', { value: formatUnitProbability(prediction.total_goals_confidence, 0) })}
                              </span>
                            )}
                          </p>
                          <div className="grid grid-cols-2 gap-4">
                            {prediction.total_goals_over_25_prob !== null && prediction.total_goals_over_25_prob !== undefined && (
                              <div>
                                <p className="text-xs text-gray-600 dark:text-gray-400">{t('expert.line.over', { line: formatNumber(2.5) })}</p>
                                <p className="text-base font-semibold text-gray-900 dark:text-white">
                                  {formatUnitProbability(prediction.total_goals_over_25_prob, 1)}
                                </p>
                              </div>
                            )}
                            {prediction.total_goals_under_25_prob !== null && prediction.total_goals_under_25_prob !== undefined && (
                              <div>
                                <p className="text-xs text-gray-600 dark:text-gray-400">{t('expert.line.under', { line: formatNumber(2.5) })}</p>
                                <p className="text-base font-semibold text-gray-900 dark:text-white">
                                  {formatUnitProbability(prediction.total_goals_under_25_prob, 1)}
                                </p>
                              </div>
                            )}
                            {prediction.total_goals_over_35_prob !== null && prediction.total_goals_over_35_prob !== undefined && (
                              <div>
                                <p className="text-xs text-gray-600 dark:text-gray-400">{t('expert.line.over', { line: formatNumber(3.5) })}</p>
                                <p className="text-base font-semibold text-gray-900 dark:text-white">
                                  {formatUnitProbability(prediction.total_goals_over_35_prob, 1)}
                                </p>
                              </div>
                            )}
                            {prediction.total_goals_under_35_prob !== null && prediction.total_goals_under_35_prob !== undefined && (
                              <div>
                                <p className="text-xs text-gray-600 dark:text-gray-400">{t('expert.line.under', { line: formatNumber(3.5) })}</p>
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
                        <div className="mb-3">
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            {t('expert.reasoningLabel')}
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
                        <span aria-hidden="true">⚠️</span> {t('expert.mine.superseded')}
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
                          {/* The core catalogue's own word, which is the same in French and is
                              declared identical on purpose there. See the note in expert.en.ts. */}
                          <dt className="text-gray-500 dark:text-gray-400">{t('filters.group.source')}</dt>
                          <dd className="text-gray-800 dark:text-gray-200">{prediction.source}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.details.priorityLevel')}</dt>
                          <dd className="text-gray-800 dark:text-gray-200">{prediction.priority_level}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.details.confidence')}</dt>
                          {/* Never 0%: a conviction nobody claimed is not a conviction of zero. */}
                          <dd className="text-gray-800 dark:text-gray-200">
                            {formatUnitProbability(prediction.confidence_score, 0, t('probability.notSet'))}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.details.bttsConfidence')}</dt>
                          <dd className="text-gray-800 dark:text-gray-200">
                            {formatUnitProbability(prediction.btts_confidence, 0, t('probability.notSet'))}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-gray-500 dark:text-gray-400">{t('expert.details.totalGoalsConfidence')}</dt>
                          <dd className="text-gray-800 dark:text-gray-200">
                            {formatUnitProbability(prediction.total_goals_confidence, 0, t('probability.notSet'))}
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
                          {/* Both halves are the backend's own words; only the punctuation
                              between them belongs to the language. */}
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
                    {editingId === prediction.id ? (
                      <>
                        <button
                          onClick={() => handleSaveEdit(prediction)}
                          disabled={processingId === prediction.id}
                          className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          {processingId === prediction.id ? t('expert.action.saving') : t('expert.action.saveChanges')}
                        </button>
                        <button
                          onClick={handleCancelEdit}
                          disabled={processingId === prediction.id}
                          className="px-4 py-2 bg-gray-600 text-white text-sm rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          {t('expert.action.cancel')}
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => toggleExpanded(prediction.id)}
                          aria-expanded={expandedIds.includes(prediction.id)}
                          className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
                        >
                          {expandedIds.includes(prediction.id) ? t('expert.action.hideDetails') : t('expert.action.viewDetails')}
                        </button>
                        {/*
                          Both controls used to be gated on `status === 'pending'`. Experts publish
                          DIRECTLY, so a prediction is created PUBLISHED and never passes through
                          pending: the effect was that an expert could not edit or delete a single
                          one of their own predictions from this page. The backend has always
                          allowed both — it edits PENDING, APPROVED, PUBLISHED and ARCHIVED (not
                          REJECTED, which is a moderation outcome), and deletes PENDING, REJECTED,
                          PUBLISHED and ARCHIVED — so the gate here is now the backend's own rule,
                          compared case-insensitively because the API's casing is not guaranteed.
                        */}
                        {canEdit(prediction.status) && (
                          <button
                            onClick={() => handleEdit(prediction)}
                            disabled={processingId === prediction.id}
                            className="px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            {t('expert.action.edit')}
                          </button>
                        )}
                        {canDelete(prediction.status) && (
                          <button
                            onClick={() => handleDelete(prediction.id)}
                            disabled={processingId === prediction.id}
                            className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            {processingId === prediction.id ? t('expert.action.deleting') : t('expert.action.delete')}
                          </button>
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

export default ExpertMyPredictionsPage;

