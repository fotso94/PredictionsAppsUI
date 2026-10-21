/**
 * The expert composer: choose a fixture, state a view, preview it, publish it.
 *
 * WHAT WAS WRONG WITH THE OLD FORM, AND WHAT REPLACED IT
 *
 *  1. The first thing an expert met was "Match ID *" with the placeholder "Enter match UUID". A
 *     fixture is now chosen the way a person thinks about football — by day, competition and the
 *     two clubs — and no UUID appears anywhere in the flow. Pasting an id is still possible for the
 *     rare case where somebody has one, but it sits behind an advanced disclosure at the bottom.
 *
 *  2. Probabilities were 0-1 decimals, so an expert meaning 55% had to type 0.55 and one who typed
 *     55 was told after submitting that their probabilities summed to 5500%. Every field is now a
 *     percentage: type 55, and 0.55 is what is stored.
 *
 *  3. The form arrived prefilled with home 0.33 / draw 0.33 / away 0.34 and confidence 0.75. That
 *     anchors the expert's judgement before they have thought about the match, and it put an
 *     accidental submission of three numbers nobody chose one click away. Nothing is prefilled now,
 *     and the model forecast shown beside the editor is never copied into a field.
 *
 * PUBLICATION IS DIRECT. Pressing publish makes the prediction public immediately: there is no
 * approval step, no queue and no pending state. The draft this page keeps is local to the browser
 * and is never sent anywhere; autosaving it cannot publish anything. That is a statement of fact
 * in both languages — the French is « Publier rend ceci public immédiatement », indicative, not a
 * conditional. A warning that softens into a suggestion on the way into another language has been
 * mistranslated whatever else is true of it.
 *
 * THE "55 / 0.55" EXAMPLES ARE FORMATTED VALUES, NOT LITERALS. French writes them « 55 % » and
 * « 0,55 ». The sentence that teaches an expert how to type a number is the last place to ship
 * English number formatting, so the examples arrive through `formatNumber` and
 * `formatPercentValue` and the catalogue only decides where in the sentence they go. Nothing
 * about the composer's own arithmetic changed: 55 typed in a field is still stored as 0.55, which
 * `e2e/live/expert-composer.spec.ts` pins against the API.
 *
 * DRAFTS ARE PER FIXTURE (QA finding 2). The page used to keep one draft per expert, with the
 * fixture as a separate piece of state, so opening fixture B from match selection wrote B's empty
 * form over A's draft in the first render, and changing fixture in the page carried A's numbers
 * and words onto B. Now:
 *  - the URL's `matchId` says which fixture is open, and choosing or changing a fixture changes
 *    the URL, so a reload reopens the same fixture rather than whichever draft was written last;
 *  - the editor is `FixtureComposer`, keyed by (user, fixture). Its values are read from THAT
 *    fixture's draft when it mounts and saved back only under that fixture's key, so no render
 *    can pair one fixture's id with another's values, and leaving a fixture keeps its draft;
 *  - an untouched composer stores nothing, and its autosave runs only once the fixture is loaded
 *    and something was actually typed;
 *  - with no `matchId` the page is the picker, headed by the expert's unpublished drafts;
 *  - every discard asks first, and a publish clears only the published fixture's draft.
 * components/expert/draft.ts holds the storage rules.
 *
 * THE WHOLE PAGE IS IN THE READER'S LANGUAGE NOW (QA finding 7). The editor's children —
 * `components/expert/PredictionMarketsEditor`, `PercentField`, `PublishPreview`, `FixtureEvidence`,
 * `FixturePicker` — read the catalogue themselves, and `components/expert/composer.ts` returns
 * its validation problems as catalogue keys with numbers, which `composerText.ts` writes at render
 * time. That last part is why `validation` below can stay memoised on the values alone: it holds
 * no sentence that a change of language could leave behind. Figures are the reader's (55,5 typed is
 * 0.555 sent, the preview prints « 55,5 % »), and every kick-off on the page — the header, the
 * picker, the evidence panel and the preview — is the UTC instant in the CHOSEN zone. What stays
 * English is the backend's own prose, marked `lang="en"` where the evidence panel shows it.
 * e2e/mocked/expert-composer-localisation.spec.ts walks every state of the page in French and
 * fails on any word the catalogue, the fixtures or the locale cannot account for.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeftIcon, CheckCircleIcon } from '@heroicons/react/24/outline'
import { Match } from '@/types'
import { ExpertPredictionResponse } from '@/types/expert'
import expertPredictionService from '@/services/expert-prediction.service'
import { footballDataService } from '@/services/football-data.service'
import { getErrorMessage } from '@/utils/errors'
import { useAuth } from '@/hooks/useAuth'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import EmptyState from '@/components/ui/EmptyState'
import FixturePicker from '@/components/expert/FixturePicker'
import FixtureEvidence from '@/components/expert/FixtureEvidence'
import PredictionMarketsEditor from '@/components/expert/PredictionMarketsEditor'
import PublishPreview from '@/components/expert/PublishPreview'
import DraftList from '@/components/expert/DraftList'
import {
  buildCreateRequest, ComposerValues, composerIsEmpty, EMPTY_COMPOSER, validateComposer,
} from '@/components/expert/composer'
import {
  assignUnassignedDraft, ComposerDraft, clearDraft, DraftFixture, draftValuesOr, listDrafts, readDraft,
  UNASSIGNED, writeDraft,
} from '@/components/expert/draft'
import { relativeTime } from '@/components/ui/freshness'
import { hasMatchKickedOff } from '@/utils/matchFilters'
import { formatDateTime, formatNumber, formatPercentValue } from '@/i18n'
import { useT } from '@/i18n/react'
import Emphasised from '@/i18n/Emphasised'

/** The little the draft needs to describe the fixture it belongs to. */
function draftFixtureOf(match: Match): DraftFixture {
  return {
    id: match.id,
    homeTeam: match.homeTeam.name,
    awayTeam: match.awayTeam.name,
    competition: match.league.name || null,
    kickoff: `${match.date} ${match.time}`.trim() || null,
    kickoffUtc: match.kickoffUtc ?? null,
  }
}

interface FixtureComposerProps {
  userId: string | null
  /** The fixture this instance is about, for its whole life: the parent keys it by this id. */
  fixtureId: string
  /** The fixture as the picker already had it, so the editor does not wait for the fetch. */
  initialMatch: Match | null
  /** A sentence to show above the editor, e.g. why a different draft than expected was opened. */
  notice: string | null
  /** "Change fixture": `keptLabel` names this fixture when its draft is still stored. */
  onChangeFixture: (keptLabel: string | null) => void
  onStartAnother: () => void
}

/**
 * The editor for ONE fixture.
 *
 * Keyed by (user, fixture) in the page, so a different fixture is a different instance: its
 * values come from its own draft in the `useState` initialiser — localStorage is synchronous, so
 * there is no empty first render for an autosave to write — and every save goes under
 * `fixtureId`, never under anything a later render could have changed.
 */
const FixtureComposer: React.FC<FixtureComposerProps> = ({
  userId, fixtureId, initialMatch, notice, onChangeFixture, onStartAnother,
}) => {
  const t = useT()
  const navigate = useNavigate()

  // Read once, when this fixture opens. An empty draft is no draft, so nothing is "restored".
  const [opened] = useState<ComposerDraft | null>(() => readDraft(userId, fixtureId))
  const [values, setValues] = useState<ComposerValues>(() => draftValuesOr(opened))
  const [restoredAt, setRestoredAt] = useState<string | null>(opened?.savedAt ?? null)
  /** The values last written (or read): autosave writes only when the expert changed something. */
  const lastWritten = useRef<ComposerValues>(values)
  const [saveFailed, setSaveFailed] = useState(false)
  const [confirmingDiscard, setConfirmingDiscard] = useState(false)
  const [discarded, setDiscarded] = useState(false)

  const [fixture, setFixture] = useState<Match | null>(initialMatch?.id === fixtureId ? initialMatch : null)
  const [fixtureLoading, setFixtureLoading] = useState(false)
  const [fixtureError, setFixtureError] = useState<string | null>(null)

  const [showErrors, setShowErrors] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)

  const [publishing, setPublishing] = useState(false)
  const [publishError, setPublishError] = useState<string | null>(null)
  const [published, setPublished] = useState<ExpertPredictionResponse | null>(null)

  /*
   * Focus follows the discard confirmation, as in DraftList (review finding #10): into "Keep it",
   * the choice that loses nothing, when it opens; back onto "Start again" when the draft is kept;
   * and, when it is discarded — which unmounts the box that held focus — onto the "Draft discarded."
   * line that says what happened, rather than onto <body>, where the next Tab starts from the top.
   * `discardCount`, not `discarded`, keys that last one, so a second discard here moves focus too.
   */
  const keepRef = useRef<HTMLButtonElement>(null)
  const startAgainRef = useRef<HTMLButtonElement>(null)
  const discardedRef = useRef<HTMLParagraphElement>(null)
  const returnFocus = useRef(false)
  const [discardCount, setDiscardCount] = useState(0)
  useEffect(() => {
    if (confirmingDiscard) keepRef.current?.focus()
    else if (returnFocus.current) {
      returnFocus.current = false
      startAgainRef.current?.focus()
    }
  }, [confirmingDiscard])
  useEffect(() => {
    if (discardCount > 0) discardedRef.current?.focus()
  }, [discardCount])

  // ------------------------------------------------------------------ the fixture
  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setFixtureLoading(true)
      setFixtureError(null)
      try {
        // The match-detail endpoint reads stored rows only — it takes no refresh parameter and
        // makes no provider call — so opening the composer spends nothing from the allowance.
        const found = await footballDataService.getMatch(fixtureId)
        if (cancelled) return
        if (!found) {
          setFixture(null)
          setFixtureError(t('expert.compose.fixtureNotFound'))
          return
        }
        setFixture(found)
      } catch (err) {
        console.error('Failed to load the fixture:', err)
        if (!cancelled) {
          setFixture(null)
          setFixtureError(getErrorMessage(err, t('expert.compose.fixtureLoadFailed')))
        }
      } finally {
        if (!cancelled) setFixtureLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [fixtureId, t])

  // ------------------------------------------------------------------ autosave (local only)
  /*
   * Only once the fixture is loaded (so the stored team names are real, never a placeholder) and
   * only when the values differ from what was last read or written (so merely opening a fixture,
   * or reopening a draft, stores nothing and moves no "saved" time). Always under `fixtureId`:
   * the id this instance was opened with is the id the expert will reopen it by. An empty
   * composer removes this fixture's draft and no other.
   */
  useEffect(() => {
    if (published || !fixture) return
    if (values === lastWritten.current) return
    const result = writeDraft(userId, { ...draftFixtureOf(fixture), id: fixtureId }, values)
    if (result !== 'failed') lastWritten.current = values
    setSaveFailed(result === 'failed')
  }, [published, fixture, fixtureId, userId, values])

  const validation = useMemo(() => validateComposer(values, fixtureId), [values, fixtureId])

  /*
   * The two example figures the composer teaches with, and the kick-off.
   *
   * `percentExamples` is "55" and "55%" in English and « 55 » / « 55 % » in French; the
   * arithmetic behind the fields is untouched, so 55 typed in a box is still stored as 0.55.
   *
   * `kickoffLine` is the fixture's UTC instant formatted in the reader's CHOSEN zone rather than
   * `${fixture.date} ${fixture.time}`, which the match services map at fetch time in whatever
   * zone was current then. An expert reads this line to decide whether a fixture is still
   * prematch; it falls back to the mapped pair only when the payload carried no UTC instant.
   */
  const percentExamples = { typed: formatNumber(55), whole: formatPercentValue(55, 0) }
  const kickoffLine = (fixture && formatDateTime(fixture.kickoffUtc))
    ?? (fixture ? `${fixture.date} ${fixture.time}`.trim() : '')

  /*
   * A fixture that has kicked off is still open to a publish — that is the posting policy, and it
   * is not changed here — but settlement never scores a prediction published at or after kick-off,
   * and readers see it labelled as late. The expert is told so above the editor and in the
   * preview, BEFORE pressing publish rather than by discovering it in their record. Computed on
   * each render, so it appears on the next keystroke if the kick-off passes while the page is open.
   */
  const kickedOff = fixture !== null && hasMatchKickedOff(fixture)
  const kickoffAt = fixture ? formatDateTime(fixture.kickoffUtc) : null

  /** The restore notice is two sentences and keeps both of them whole. */
  const restoredAgo = restoredAt ? relativeTime(restoredAt) : null
  const fixtureLabel = fixture
    ? t('expert.fixtureShort', { home: fixture.homeTeam.name, away: fixture.awayTeam.name })
    : ''
  const discardSentence = fixtureLabel
    ? t('expert.draft.discardConfirm', { fixture: fixtureLabel })
    : t('expert.draft.discardConfirmNoFixture')

  const changeFixture = () => {
    // Whatever was typed here is already in this fixture's own draft; say so only if it is.
    onChangeFixture(readDraft(userId, fixtureId) && fixtureLabel ? fixtureLabel : null)
  }

  const discardDraft = () => {
    clearDraft(userId, fixtureId)
    const blank = { ...EMPTY_COMPOSER }
    lastWritten.current = blank
    setValues(blank)
    setRestoredAt(null)
    setConfirmingDiscard(false)
    setDiscarded(true)
    setDiscardCount(count => count + 1)
    setShowErrors(false)
    setPreviewOpen(false)
  }

  const editValues = useCallback((next: ComposerValues) => {
    setDiscarded(false)
    setValues(next)
  }, [])

  /**
   * The preview is a REVEAL, not a step that locks anything in. Once open it tracks the fields
   * live, so an expert adjusting a number watches the published view change rather than losing the
   * panel on every keystroke. Publishing is still a separate, deliberate press.
   */
  const handlePreview = () => {
    setShowErrors(true)
    setPreviewOpen(true)
  }

  const handlePublish = async () => {
    setShowErrors(true)
    setPublishError(null)
    const request = buildCreateRequest(values, fixtureId)
    if (!validation.ready || !request) return

    try {
      setPublishing(true)
      const result = await expertPredictionService.createManualPrediction(request)
      // This fixture's draft has served its purpose; the published record is the durable one now.
      // Every other fixture's draft is left exactly where it is.
      clearDraft(userId, fixtureId)
      setPublished(result)
      setRestoredAt(null)
    } catch (err) {
      console.error('Failed to publish the prediction:', err)
      setPublishError(getErrorMessage(err, t('expert.compose.publishFailed')))
    } finally {
      setPublishing(false)
    }
  }

  // ------------------------------------------------------------------ published
  if (published) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-8" data-testid="expert-composer">
        <div className="card p-6">
          <div className="flex items-start gap-3">
            <CheckCircleIcon className="mt-0.5 h-6 w-6 flex-shrink-0 text-success-400" aria-hidden="true" />
            <div className="min-w-0">
              <h1 className="text-xl font-bold text-white">{t('expert.published.title')}</h1>
              <p className="mt-1 text-sm text-secondary-300">{t('expert.published.body')}</p>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to={`/match/${published.match_id}`} className="btn btn-md btn-primary">{t('expert.published.viewMatch')}</Link>
            <button type="button" onClick={onStartAnother} className="btn btn-md btn-secondary">{t('expert.published.writeAnother')}</button>
            <Link to="/expert/predictions/my-predictions" className="btn btn-md btn-ghost">{t('expert.dashboard.myPredictions')}</Link>
          </div>
        </div>
      </div>
    )
  }

  // ------------------------------------------------------------------ compose
  return (
    <div className="container mx-auto max-w-6xl px-4 py-8" data-testid="expert-composer">
      <button type="button" onClick={() => navigate('/expert/dashboard')} className="focus-ring mb-4 inline-flex items-center gap-1 text-sm text-primary-300 hover:text-primary-200">
        <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
        {t('expert.backToDashboard')}
      </button>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-white sm:text-3xl">{t('expert.compose.title')}</h1>
          {fixture ? (
            /*
              ONLY THE COMPETITION MAY GIVE WAY (review finding #24). This was one `truncate`d line,
              "{fixture} · {competition} · {kick-off}", and at 360 and 390px the ellipsis fell
              before the kick-off — the value on the line the expert reads to know the fixture is
              still prematch. Now the RecentRow shape (ExpertDashboardPage): the fixture wraps, the
              competition is its own run and truncates, and the kick-off is never cut and never
              broken; when the pair does not fit, the line wraps.
            */
            <p className="mt-1 flex flex-wrap items-baseline gap-x-1 text-sm text-secondary-300" data-testid="composer-fixture-line">
              <span className="min-w-0 break-words font-medium text-white">{fixtureLabel}</span>
              {fixture.league.name && (
                <span className="min-w-0 max-w-full truncate text-secondary-400">· {fixture.league.name}</span>
              )}
              {/* The kick-off in the reader's chosen zone — what tells them it is still prematch. */}
              {kickoffLine && (
                <span className="num whitespace-nowrap text-secondary-400" data-testid="composer-header-kickoff">· {kickoffLine}</span>
              )}
            </p>
          ) : (
            <p className="mt-1 text-sm text-secondary-400">{t('expert.compose.loadingFixture')}</p>
          )}
        </div>
        <button type="button" onClick={changeFixture} className="btn btn-sm btn-secondary flex-shrink-0">
          {t('expert.compose.changeFixture')}
        </button>
      </div>

      {kickedOff && (
        <p
          className="mt-4 rounded-lg border border-warning-700 bg-warning-900/30 px-4 py-2.5 text-sm text-warning-200"
          role="status"
          data-testid="composer-kickoff-warning"
        >
          {kickoffAt
            ? t('expert.compose.kickoffPassed', { time: kickoffAt })
            : t('expert.compose.kickoffPassedNoTime')}
        </p>
      )}

      {notice && (
        <p className="mt-4 rounded-lg border border-primary-800 bg-dark-900/60 px-4 py-2.5 text-xs text-secondary-200" role="status">
          {notice}
        </p>
      )}

      {restoredAt && (
        <div className="mt-4 rounded-lg border border-dark-700 bg-dark-900/60 px-4 py-2.5">
          <p className="text-xs text-secondary-300">
            {restoredAgo
              ? t('expert.draft.restoredSaved', { ago: restoredAgo })
              : t('expert.draft.restored')}
            {!composerIsEmpty(values) && !confirmingDiscard && (
              <button ref={startAgainRef} type="button" onClick={() => setConfirmingDiscard(true)} className="focus-ring ml-2 font-medium text-primary-300 hover:text-primary-200">
                {t('expert.draft.startAgain')}
              </button>
            )}
          </p>
          {/* "Start again" throws the draft away, so it asks first, like every other discard. */}
          {confirmingDiscard && (
            <div className="mt-2" role="group" aria-label={discardSentence}>
              <p className="text-sm text-white">
                <Emphasised sentence={discardSentence} value={fixtureLabel} className="font-semibold" />
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" onClick={discardDraft} className="btn btn-sm btn-danger">
                  {t('expert.draft.confirmDiscard')}
                </button>
                <button
                  ref={keepRef}
                  type="button"
                  onClick={() => { returnFocus.current = true; setConfirmingDiscard(false) }}
                  className="btn btn-sm btn-secondary"
                >
                  {t('expert.draft.keep')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {discarded && (
        <p ref={discardedRef} tabIndex={-1} className="mt-4 text-xs text-secondary-300 focus:outline-none" role="status">
          {t('expert.draft.discarded')}
        </p>
      )}

      {saveFailed && (
        <p className="mt-4 rounded-lg border border-warning-700 bg-warning-900/30 px-4 py-2.5 text-sm text-warning-200" role="alert">
          {t('expert.draft.saveFailed')}
        </p>
      )}

      {fixtureError && (
        <div className="mt-4">
          <EmptyState
            tone="failed"
            title={t('expert.compose.fixtureNotOpened')}
            description={fixtureError}
            variant="inline"
            action={<button type="button" onClick={changeFixture} className="btn btn-sm btn-secondary">{t('expert.compose.chooseFromList')}</button>}
          />
        </div>
      )}

      {fixtureLoading && !fixture && (
        <div className="mt-6 flex justify-center p-8"><LoadingSpinner /></div>
      )}

      {fixture && (
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          {/* ------------------------------------------------------------- the editor */}
          <div className="min-w-0 space-y-6">
            <div className="card p-4 sm:p-6">
              <h2 className="text-lg font-semibold text-white">{t('expert.compose.yourView')}</h2>
              <p className="mb-5 mt-1 text-sm text-secondary-400">
                {t('expert.compose.percentNote', percentExamples)}
              </p>

              <PredictionMarketsEditor
                values={values}
                onChange={editValues}
                validation={validation}
                showErrors={showErrors}
                homeTeam={fixture.homeTeam.name}
                awayTeam={fixture.awayTeam.name}
                idPrefix="composer"
                disabled={publishing}
              />

              {showErrors && !validation.ready && (
                <p className="mt-4 text-sm text-warning-200" role="status">
                  {t('expert.compose.fixThenPreview')}
                </p>
              )}

              <div className="mt-6 flex flex-wrap items-center gap-3">
                <button type="button" onClick={handlePreview} disabled={publishing} className="btn btn-md btn-secondary">
                  {t('expert.action.preview')}
                </button>
                {/* Never disabled for being incomplete: a dead button explains nothing. Pressing it
                    on an incomplete form marks exactly which fields need attention. */}
                <button
                  type="button"
                  onClick={handlePublish}
                  disabled={publishing}
                  className="btn btn-md btn-primary"
                >
                  {publishing ? t('expert.action.publishing') : t('expert.action.publish')}
                </button>
                <span className="text-xs text-secondary-400">{t('expert.compose.publishImmediate')}</span>
              </div>

              {publishError && (
                <p className="form-error mt-3" role="alert">{publishError}</p>
              )}
            </div>

            {previewOpen && <PublishPreview values={values} fixture={draftFixtureOf(fixture)} kickedOff={kickedOff} />}
          </div>

          {/* ------------------------------------------------------------- the evidence */}
          <div className="min-w-0">
            <FixtureEvidence match={fixture} className="lg:sticky lg:top-6" />
          </div>
        </div>
      )}

      <details className="card mt-8 p-4">
        <summary className="focus-ring cursor-pointer text-sm font-medium text-secondary-200">
          {t('expert.compose.advancedIds')}
        </summary>
        <p className="mt-2 break-all text-xs text-secondary-400">
          {t('expert.compose.internalMatchId')} <span className="num">{fixtureId}</span>
          {fixture?.provider && fixture.externalId && (
            <><br />{t('expert.compose.providerId', { provider: fixture.provider })} <span className="num">{fixture.externalId}</span></>
          )}
        </p>
      </details>
    </div>
  )
}

const ExpertCreatePredictionPage: React.FC = () => {
  const t = useT()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const userId = user?.id ?? null
  // The URL is the one place that says which fixture is open: a reload reopens it.
  const matchId = searchParams.get('matchId') || null

  /** The fixture the picker handed over, so the composer can draw it before the fetch returns. */
  const [picked, setPicked] = useState<Match | null>(null)
  /** "Your draft for X is kept", after Change fixture. */
  const [keptLabel, setKeptLabel] = useState<string | null>(null)
  /** Continue was pressed on the draft that has no fixture: the next choice is its fixture. */
  const [assigning, setAssigning] = useState(false)
  /**
   * A sentence for the composer of ONE fixture, e.g. why a different draft than expected opened.
   * Held with the fixture it is about and shown only on that fixture's composer (review finding
   * #9): Back and Forward change `matchId` and leave page state alone, so a bare string written
   * for A was shown on B's editor after two presses of Back.
   */
  const [composerNotice, setComposerNotice] = useState<{ fixtureId: string; text: string } | null>(null)
  const [discarded, setDiscarded] = useState(false)
  /** The picker's "Draft discarded." line, which takes focus after a confirmed discard (finding #10). */
  const discardedRef = useRef<HTMLParagraphElement>(null)
  /** Bumped after a discard so the list is read again. */
  const [listVersion, setListVersion] = useState(0)

  const [manualId, setManualId] = useState('')

  // Read synchronously from this browser, and only while the picker is what is on screen.
  const drafts = useMemo(
    () => (matchId ? [] : listDrafts(userId)),
    // listVersion is the explicit "read it again" after a discard on this screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [matchId, userId, listVersion],
  )

  const openFixture = useCallback((id: string, match: Match | null, notice: string | null = null) => {
    setPicked(match)
    setComposerNotice(notice ? { fixtureId: id, text: notice } : null)
    setKeptLabel(null)
    setDiscarded(false)
    setSearchParams({ matchId: id })
  }, [setSearchParams])

  const chooseFixture = useCallback((match: Match) => {
    if (assigning) {
      setAssigning(false)
      const fixture = draftFixtureOf(match)
      if (!assignUnassignedDraft(userId, fixture) && readDraft(userId, match.id) && readDraft(userId, UNASSIGNED)) {
        // That fixture already has a draft of its own. Open that one and move nothing.
        const label = t('expert.fixtureShort', { home: fixture.homeTeam, away: fixture.awayTeam })
        openFixture(match.id, match, t('expert.draft.assignTaken', { fixture: label }))
        return
      }
    }
    openFixture(match.id, match)
  }, [assigning, openFixture, t, userId])

  const continueDraft = (draft: ComposerDraft) => {
    if (draft.slot === UNASSIGNED) {
      setAssigning(true)
      return
    }
    setAssigning(false)
    openFixture(draft.slot, null)
  }

  const discardFromList = (draft: ComposerDraft) => {
    clearDraft(userId, draft.slot)
    if (draft.slot === UNASSIGNED) setAssigning(false)
    setKeptLabel(null)
    setDiscarded(true)
    setListVersion(version => version + 1)
  }

  const backToPicker = (label: string | null) => {
    setKeptLabel(label)
    setComposerNotice(null)
    setDiscarded(false)
    // Change fixture opens the ordinary picker, never one left in "choose a fixture for the draft
    // without one" mode by a Continue pressed before Back or Forward brought a composer back.
    setAssigning(false)
    setSearchParams({})
  }

  // After a confirmed discard the row that held focus is gone: focus goes to the line that says
  // what happened. Keyed on `listVersion`, which every discard bumps, so a second one moves it too.
  useEffect(() => {
    if (discarded) discardedRef.current?.focus()
  }, [discarded, listVersion])

  // ------------------------------------------------------------------ one fixture
  if (matchId) {
    return (
      <FixtureComposer
        key={`${userId ?? ''}::${matchId}`}
        userId={userId}
        fixtureId={matchId}
        initialMatch={picked}
        notice={composerNotice?.fixtureId === matchId ? composerNotice.text : null}
        onChangeFixture={backToPicker}
        onStartAnother={() => backToPicker(null)}
      />
    )
  }

  // ------------------------------------------------------------------ choose a fixture
  const keptSentence = keptLabel ? t('expert.draft.keptFor', { fixture: keptLabel }) : ''

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8" data-testid="expert-composer">
      <button type="button" onClick={() => navigate('/expert/dashboard')} className="focus-ring mb-4 inline-flex items-center gap-1 text-sm text-primary-300 hover:text-primary-200">
        <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
        {t('expert.backToDashboard')}
      </button>
      <h1 className="text-2xl font-bold text-white sm:text-3xl">{t('expert.compose.title')}</h1>
      <p className="mt-1 text-sm text-secondary-300">{t('expert.compose.chooseIntro')}</p>

      {keptLabel && (
        <p className="mt-4 text-sm text-secondary-200" role="status">
          <Emphasised sentence={keptSentence} value={keptLabel} className="font-semibold text-white" />
        </p>
      )}
      {discarded && (
        <p ref={discardedRef} tabIndex={-1} className="mt-4 text-xs text-secondary-300 focus:outline-none" role="status">
          {t('expert.draft.discarded')}
        </p>
      )}

      {/*
        The expert's unpublished drafts, each under its own fixture. Nothing is restored on its
        own: the expert continues the one they mean, or chooses a fixture below.
      */}
      {drafts.length > 0 && (
        <section className="card mt-6 border-primary-800 p-4" aria-labelledby="drafts-heading">
          <h2 id="drafts-heading" className="text-sm font-semibold text-white">{t('expert.draft.listTitle')}</h2>
          <p className="mt-1 text-xs text-secondary-400">{t('expert.draft.listNote')}</p>
          <DraftList className="mt-3" drafts={drafts} onContinue={continueDraft} onDiscard={discardFromList} />
        </section>
      )}

      {assigning && (
        <div className="card mt-6 border-primary-800 p-4" role="status">
          <p className="text-sm text-white">{t('expert.draft.assignHint')}</p>
          <button type="button" onClick={() => setAssigning(false)} className="btn btn-sm btn-ghost mt-2">
            {t('expert.action.cancel')}
          </button>
        </div>
      )}

      <FixturePicker
        className="mt-6"
        onChoose={chooseFixture}
        actionLabel={t('expert.action.writePrediction')}
        heading={<>
          <h2 className="text-sm font-semibold text-white">{t('expert.compose.chooseFixture')}</h2>
          <p className="mt-1 text-xs text-secondary-400">{t('expert.compose.filterHint')}</p>
        </>}
      />

      <details className="card mt-6 p-4">
        <summary className="focus-ring cursor-pointer text-sm font-medium text-secondary-200">
          {t('expert.compose.advancedPaste')}
        </summary>
        <p className="mt-2 text-xs text-secondary-400">{t('expert.compose.advancedPasteHint')}</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <label htmlFor="manual-match-id" className="sr-only">{t('expert.compose.matchIdLabel')}</label>
          <input
            id="manual-match-id"
            type="text"
            value={manualId}
            onChange={event => setManualId(event.target.value)}
            placeholder={t('expert.compose.matchIdPlaceholder')}
            className="form-input min-w-0 flex-1 py-2"
          />
          <button
            type="button"
            disabled={!manualId.trim()}
            onClick={() => { setAssigning(false); openFixture(manualId.trim(), null) }}
            className="btn btn-md btn-secondary"
          >
            {t('expert.compose.useThisId')}
          </button>
        </div>
      </details>
    </div>
  )
}

export default ExpertCreatePredictionPage
