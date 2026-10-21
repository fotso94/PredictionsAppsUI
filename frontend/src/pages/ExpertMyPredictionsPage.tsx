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
 *     THE HEADLINE CONVICTION BEHAVES THE SAME WAY. `confidence_score` is nullable end to end —
 *     column, expert service, response model and this page — so "not given" is a value the API
 *     can express and the fallback under `expert.details.confidence` really fires.
 *     Two consequences to keep: a conviction nobody gave is not a band, so `ConfidenceBadge`
 *     takes `number | null | undefined` and renders « non renseigné » for the absent cases
 *     rather than banding them; and every test here is `isPublished`, never `value &&`, because
 *     0 is a conviction an expert may deliberately claim.
 *   - THE EDIT NOTICE IS A PROMISE ABOUT READERS. Saving keeps the prediction published and keeps
 *     the superseded version, so a reader can still see what was published before. The French
 *     says exactly that, in the same indicative.
 *
 * ── EVERY DATE HERE IS IN THE READER'S CHOSEN ZONE ────────────────────────────────
 *
 * Four instants are rendered here: the kick-off, the creation time and two publication times.
 * None of them may go through bare `toLocaleDateString` / `toLocaleString`, which format in the
 * DEVICE's zone and the DEVICE's locale — for an expert judging whether a fixture is still
 * prematch, that is a correctness defect and not a cosmetic one. All four go through
 * `backendInstant` (this backend anchors these columns with a trailing Z — see the field
 * serialisers in backend/app/schemas/predictions.py) and then `formatDate` / `formatDateTime`.
 *
 * ── PAGES ARE COUNTED, NOT GUESSED ────────────────────────────────────────────────
 *
 * Twenty to a page. The total for the filter comes from the X-Total-Count header, and each page
 * also asks for ONE extra row, which is never shown: when the header is missing, that row is the
 * only evidence that a next page exists. "This page came back full" is not evidence — it is true
 * of the last page whenever the total is a multiple of twenty, and Next used to lead from exactly
 * twenty predictions into an empty page. So:
 *
 *   - the heading counts every prediction matching the filter, not the rows on this page, and
 *     claims no number when none can be known;
 *   - the page bar shows whenever there is a page before or after this one, and Previous always
 *     works from a later page — including an empty one, which is exactly when it is needed;
 *   - a later page that has emptied (the list shrank after it was counted, in another tab, say)
 *     says so and offers Previous. "You haven't created any predictions yet" is for the first
 *     page, unfiltered, and nowhere else;
 *   - a delete or a publication change that empties a later page steps back ONE page. Only those
 *     two actions do it and they do it once, so an always-empty answer cannot make a loop.
 *
 * The filter's onChange resets to the first page; e2e/mocked/expert-management.spec.ts pins it.
 *
 * ── PUBLISH AND UNPUBLISH ─────────────────────────────────────────────────────────────
 *
 * A published or archived prediction can be taken off the public lists here and put back, with
 * the same confirmation as the dashboard and, after kickoff, a note on the card and in the
 * confirmation that the change does not alter the measured record. utils/publication.ts says why.
 *
 * ── THE EDITOR, IN THE READER'S LANGUAGE ───────────────────────────────────────────
 *
 * The inline editor is `components/expert/PredictionMarketsEditor`, the composer's own, so its
 * labels, totals and validation messages are the catalogue's in both languages (QA finding 7).
 * An edit reopens the stored figures the way the reader types a decimal — « 55,5 » in French,
 * "55.5" in English — because `composerFromPrediction` is given the reader's locale; either
 * separator reads back to the same probability, so an untouched save sends what is stored. The
 * status BADGE beside each prediction renders the backend's own word and is left that way
 * deliberately.
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
import { backendInstant, currentLocale, formatDate, formatDateTime, formatNumber, formatPercentValue } from '@/i18n';
import { useT } from '@/i18n/react';
import type { MessageKey } from '@/i18n';
import { canTogglePublication, hasKickedOff, kickedOffNoteKey, publicationConfirmText } from '@/utils/publication';
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

/** One page of the list, as the page shows it. */
interface ListPage {
  /** At most one page of rows; the probe row is never among them. */
  rows: ExpertPredictionResponse[];
  /** Whether a later page has anything on it. */
  more: boolean;
  /** Every prediction matching the filter, or null when that cannot be known. */
  total: number | null;
}

/** After kickoff, what a publication change does not do. Nothing before kickoff. */
const KickoffNote: React.FC<{ prediction: ExpertPredictionResponse }> = ({ prediction }) => {
  const t = useT();
  const key = kickedOffNoteKey(prediction);
  return key ? <p className="mt-3 text-xs text-gray-600 dark:text-gray-400">{t(key)}</p> : null;
};

const ExpertMyPredictionsPage: React.FC = () => {
  const t = useT();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [predictions, setPredictions] = useState<ExpertPredictionResponse[]>([]);
  const [page, setPage] = useState(0);
  const [limit] = useState(20);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [processingId, setProcessingId] = useState<string | null>(null);
  /** Which action `processingId` is busy with, so a toggle in flight is not labelled "Deleting...". */
  const [processingAction, setProcessingAction] = useState<'delete' | 'toggle' | null>(null);
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

  /**
   * One page, and what is known about the rest. See "PAGES ARE COUNTED" above.
   *
   * With the header, the total decides. Without it, the probe row decides whether more follows,
   * and the total is known only when nothing does: then it is this page's offset plus its rows,
   * the earlier pages being full. An empty later page without a header gives no total at all,
   * because the list has shrunk by an amount nothing here can see.
   */
  const fetchPage = useCallback(async (pageIndex: number): Promise<ListPage> => {
    const offset = pageIndex * limit;
    const answer = await expertPredictionService.getMyPredictions({
      limit: limit + 1,
      offset,
      status: statusFilter === 'all' ? undefined : statusFilter,
    });
    const rows = answer.predictions.slice(0, limit);
    const more = answer.total !== null ? offset + limit < answer.total : answer.predictions.length > limit;
    const counted = answer.total !== null
      ? answer.total
      : !more && (rows.length > 0 || pageIndex === 0) ? offset + rows.length : null;
    return { rows, more, total: counted };
  }, [limit, statusFilter]);

  const loadMyPredictions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await fetchPage(page);
      setPredictions(result.rows);
      setHasMore(result.more);
      setTotal(result.total);
    } catch (err) {
      console.error('Failed to load predictions:', err);
      setError(getErrorMessage(err, t('expert.mine.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [fetchPage, page, t]);

  /**
   * Reload after a delete or a publication change, either of which can empty the page it was
   * made on: the last row of a later page deleted, or unpublished under the Published filter.
   * Then the page steps back ONE page and the effect loads it. That load never steps back itself,
   * so this is a single bounded step and an always-empty answer cannot start a loop; whatever
   * the earlier page holds is shown, its own empty state included.
   */
  const reloadAfterChange = async () => {
    let steppedBack = false;
    try {
      setLoading(true);
      const result = await fetchPage(page);
      if (result.rows.length === 0 && page > 0) {
        steppedBack = true;
        setPage(page - 1);
        return;
      }
      setPredictions(result.rows);
      setHasMore(result.more);
      setTotal(result.total);
    } catch (err) {
      console.error('Failed to load predictions:', err);
      setError(getErrorMessage(err, t('expert.mine.loadFailed')));
    } finally {
      // Stepping back leaves the spinner up for the effect's load, rather than showing this
      // page's stale rows under the earlier page's number for one render.
      if (!steppedBack) setLoading(false);
    }
  };

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
    setEditValues(composerFromPrediction(prediction, currentLocale()));
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
      setProcessingAction('delete');
      setError(null);
      await expertPredictionService.deletePrediction(predictionId);
      await reloadAfterChange();
    } catch (err) {
      console.error('Failed to delete prediction:', err);
      setError(getErrorMessage(err, t('expert.deleteFailed')));
    } finally {
      setProcessingId(null);
      setProcessingAction(null);
    }
  };

  const handleTogglePublish = async (prediction: ExpertPredictionResponse) => {
    // Asked first, with what the change does and, after kickoff, what it does not do.
    if (!confirm(publicationConfirmText(prediction, t))) {
      return;
    }

    try {
      setProcessingId(prediction.id);
      setProcessingAction('toggle');
      setError(null);
      await expertPredictionService.togglePublishStatus(prediction.id);
      await reloadAfterChange();
    } catch (err) {
      console.error('Failed to toggle publish status:', err);
      setError(getErrorMessage(err, t('expert.dashboard.toggleFailed')));
    } finally {
      setProcessingId(null);
      setProcessingAction(null);
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
            {/* Every prediction matching the filter, on every page — or no number at all. */}
            {total !== null
              ? t('expert.mine.listHeading', { count: formatNumber(total) })
              : t('expert.mine.listHeadingUncounted')}
          </h2>
        </div>

        <div className="p-6">
          {predictions.length === 0 && page > 0 ? (
            // A later page the list no longer reaches. The account has predictions, so none of
            // the first-page wording below applies; Previous is in the page bar underneath.
            <div className="text-center py-12" role="status">
              <p className="text-gray-600 dark:text-gray-400 text-lg mb-4">
                {t('expert.mine.emptyPageTitle')}
              </p>
              <p className="text-gray-500 dark:text-gray-500 text-sm">
                {t('expert.mine.emptyPageBody')}
              </p>
            </div>
          ) : predictions.length === 0 ? (
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
              {/* "Your first" is true only of an unfiltered empty list. */}
              {statusFilter === 'all' && (
                <Link
                  to="/expert/predictions/create"
                  className="inline-block px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
                >
                  {t('expert.mine.createFirst')}
                </Link>
              )}
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
                      The badge bands whatever number it is handed, and a conviction nobody
                      supplied would band to the lowest level at "0%" — the loudest possible way
                      of stating a figure that was never claimed. Null and undefined the badge
                      refuses itself, so for any payload the API can send this test is
                      belt-and-braces; it is kept because `isPublished` is the single rule this
                      page applies to every conviction, and because it also rejects the
                      non-finite numbers the badge's `=== null` check lets through. Either way
                      the row reads « non renseigné », the same wording the detail panel below
                      uses for the same absence.
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
                    <div className="mb-3 rounded-lg border border-dark-700 bg-dark-900/60 p-4" data-testid="prediction-editor">
                      <p className="mb-4 text-sm text-secondary-300">
                        {t('expert.mine.editNote', percentExamples)}
                      </p>
                      {/*
                        After kickoff an edit changes what readers see, never what is scored:
                        settlement restores the version that stood at kickoff. Said in the editor,
                        before the save, with the same boundary as the publication notes (at
                        kickoff is after it). Nothing before kickoff, and nothing when the kickoff
                        is unknown.
                      */}
                      {hasKickedOff(prediction) && (
                        <p
                          className="mb-4 rounded-lg border border-warning-700 bg-warning-900/30 px-3 py-2 text-sm text-warning-200"
                          role="status"
                          data-testid="edit-after-kickoff"
                        >
                          {t('expert.edit.afterKickoff')}
                        </p>
                      )}
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

                  {/* The full record opens in place: there is no /expert/predictions/:id route to link to. */}
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

                  {editingId !== prediction.id && <KickoffNote prediction={prediction} />}

                  {/* Actions. They wrap: four of them do not fit one line on a phone in French. */}
                  <div className="flex flex-wrap gap-2 mt-4">
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
                          NEITHER CONTROL MAY BE GATED ON `status === 'pending'`. Experts publish
                          DIRECTLY, so a prediction is created PUBLISHED and never passes through
                          pending: that gate hides edit and delete on every prediction an expert
                          owns. The rule here mirrors the backend's instead — it edits PENDING,
                          APPROVED, PUBLISHED and ARCHIVED (not REJECTED, which is a moderation
                          outcome), and deletes PENDING, REJECTED, PUBLISHED and ARCHIVED —
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
                        {/* PUBLISHED <-> ARCHIVED only, as the backend toggles; asked first. */}
                        {canTogglePublication(prediction.status) && (
                          <button
                            onClick={() => handleTogglePublish(prediction)}
                            disabled={processingId === prediction.id}
                            className="px-4 py-2 bg-amber-600 text-white text-sm rounded-lg hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            {processingId === prediction.id && processingAction === 'toggle'
                              ? t('expert.action.working')
                              : prediction.status.toLowerCase() === 'published'
                                ? t('expert.action.unpublish')
                                : t('expert.action.publish')}
                          </button>
                        )}
                        {canDelete(prediction.status) && (
                          <button
                            onClick={() => handleDelete(prediction.id)}
                            disabled={processingId === prediction.id}
                            className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            {processingId === prediction.id && processingAction === 'delete'
                              ? t('expert.action.deleting')
                              : t('expert.action.delete')}
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

        {/* Pagination: whenever there is a page before or after this one, empty or not. */}
        {(page > 0 || hasMore) && (
          <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-between items-center gap-2">
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
              disabled={!hasMore}
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

