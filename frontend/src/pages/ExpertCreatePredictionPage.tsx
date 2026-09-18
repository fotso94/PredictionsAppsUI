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
 * and is never sent anywhere; autosaving it cannot publish anything.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react'
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
import {
  buildCreateRequest, ComposerValues, composerIsEmpty, EMPTY_COMPOSER, validateComposer,
} from '@/components/expert/composer'
import { ComposerDraft, clearDraft, DraftFixture, readDraft, savedAgo, writeDraft } from '@/components/expert/draft'

/** The little the draft needs to describe the fixture it belongs to. */
function draftFixtureOf(match: Match | null): DraftFixture | null {
  if (!match) return null
  return {
    id: match.id,
    homeTeam: match.homeTeam.name,
    awayTeam: match.awayTeam.name,
    competition: match.league.name || null,
    kickoff: `${match.date} ${match.time}`.trim() || null,
  }
}

const ExpertCreatePredictionPage: React.FC = () => {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const userId = user?.id ?? null

  const [matchId, setMatchId] = useState<string | null>(searchParams.get('matchId'))
  const [fixture, setFixture] = useState<Match | null>(null)
  const [fixtureLoading, setFixtureLoading] = useState(false)
  const [fixtureError, setFixtureError] = useState<string | null>(null)

  const [values, setValues] = useState<ComposerValues>({ ...EMPTY_COMPOSER })
  const [showErrors, setShowErrors] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)

  const [publishing, setPublishing] = useState(false)
  const [publishError, setPublishError] = useState<string | null>(null)
  const [published, setPublished] = useState<ExpertPredictionResponse | null>(null)

  /** A draft found on this machine that belongs to a DIFFERENT fixture than the one being opened. */
  const [otherDraft, setOtherDraft] = useState<ComposerDraft | null>(null)
  const [restoredAt, setRestoredAt] = useState<string | null>(null)
  /** Autosave must not run before the stored draft has been read, or it would overwrite it. */
  const [hydrated, setHydrated] = useState(false)

  const [manualId, setManualId] = useState('')

  // ------------------------------------------------------------------ draft, read once
  useEffect(() => {
    const draft = readDraft(userId)
    const requested = searchParams.get('matchId')
    if (!draft) {
      setHydrated(true)
      return
    }
    if (!requested || draft.fixture?.id === requested) {
      // Continuing where the expert left off. Nothing has been published by this restore.
      setMatchId(draft.fixture?.id ?? requested)
      setValues(draft.values)
      setRestoredAt(draft.savedAt)
    } else {
      // A different fixture was asked for. The existing draft is left untouched and offered.
      setOtherDraft(draft)
    }
    setHydrated(true)
  }, [userId, searchParams])

  // ------------------------------------------------------------------ the fixture
  useEffect(() => {
    if (!matchId) {
      setFixture(null)
      setFixtureError(null)
      return
    }
    let cancelled = false
    const run = async () => {
      setFixtureLoading(true)
      setFixtureError(null)
      try {
        // The match-detail endpoint reads stored rows only — it takes no refresh parameter and
        // makes no provider call — so opening the composer spends nothing from the allowance.
        const found = await footballDataService.getMatch(matchId)
        if (cancelled) return
        if (!found) {
          setFixture(null)
          setFixtureError('That fixture could not be found. Choose one from the list instead.')
          return
        }
        setFixture(found)
      } catch (err) {
        console.error('Failed to load the fixture:', err)
        if (!cancelled) {
          setFixture(null)
          setFixtureError(getErrorMessage(err, 'The fixture could not be loaded.'))
        }
      } finally {
        if (!cancelled) setFixtureLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [matchId])

  // ------------------------------------------------------------------ autosave (local only)
  useEffect(() => {
    if (!hydrated || published) return
    writeDraft(userId, draftFixtureOf(fixture) ?? (matchId ? { id: matchId, homeTeam: '', awayTeam: '', competition: null, kickoff: null } : null), values)
  }, [hydrated, published, userId, fixture, matchId, values])

  const validation = useMemo(() => validateComposer(values, matchId), [values, matchId])

  const chooseFixture = useCallback((match: Match) => {
    setMatchId(match.id)
    setFixture(match)
    setFixtureError(null)
    setOtherDraft(null)
    setPreviewOpen(false)
  }, [])

  const changeFixture = () => {
    setMatchId(null)
    setFixture(null)
    setPreviewOpen(false)
  }

  const discardDraft = () => {
    clearDraft(userId)
    setValues({ ...EMPTY_COMPOSER })
    setRestoredAt(null)
    setShowErrors(false)
    setPreviewOpen(false)
  }

  const continueOtherDraft = () => {
    if (!otherDraft) return
    setValues(otherDraft.values)
    setMatchId(otherDraft.fixture?.id ?? null)
    setRestoredAt(otherDraft.savedAt)
    setOtherDraft(null)
  }

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
    if (!matchId) return
    const request = buildCreateRequest(values, matchId)
    if (!validation.ready || !request) return

    try {
      setPublishing(true)
      const result = await expertPredictionService.createManualPrediction(request)
      // The local draft has served its purpose; the published record is the durable one now.
      clearDraft(userId)
      setPublished(result)
      setRestoredAt(null)
    } catch (err) {
      console.error('Failed to publish the prediction:', err)
      setPublishError(getErrorMessage(err, 'The prediction could not be published.'))
    } finally {
      setPublishing(false)
    }
  }

  const startAnother = () => {
    setPublished(null)
    setValues({ ...EMPTY_COMPOSER })
    setMatchId(null)
    setFixture(null)
    setShowErrors(false)
    setPreviewOpen(false)
    setPublishError(null)
  }

  // ------------------------------------------------------------------ published
  if (published) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-8">
        <div className="card p-6">
          <div className="flex items-start gap-3">
            <CheckCircleIcon className="mt-0.5 h-6 w-6 flex-shrink-0 text-success-400" aria-hidden="true" />
            <div className="min-w-0">
              <h1 className="text-xl font-bold text-white">Published</h1>
              <p className="mt-1 text-sm text-secondary-300">
                Your prediction is on the public match page now. Nothing is waiting for approval — experts publish
                directly. You can edit or remove it at any time from My predictions.
              </p>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to={`/match/${published.match_id}`} className="btn btn-md btn-primary">View the match page</Link>
            <button type="button" onClick={startAnother} className="btn btn-md btn-secondary">Write another</button>
            <Link to="/expert/predictions/my-predictions" className="btn btn-md btn-ghost">My predictions</Link>
          </div>
        </div>
      </div>
    )
  }

  // ------------------------------------------------------------------ choose a fixture
  if (!matchId) {
    return (
      <div className="container mx-auto max-w-4xl px-4 py-8">
        <button type="button" onClick={() => navigate('/expert/dashboard')} className="focus-ring mb-4 inline-flex items-center gap-1 text-sm text-primary-300 hover:text-primary-200">
          <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
          Back to dashboard
        </button>
        <h1 className="text-2xl font-bold text-white sm:text-3xl">Write a prediction</h1>
        <p className="mt-1 text-sm text-secondary-300">
          Start by choosing the fixture. Publication is immediate once you press publish — there is no approval step.
        </p>

        {otherDraft && (
          <div className="card mt-6 border-primary-800 p-4">
            <p className="text-sm text-white">
              You have an unfinished draft
              {otherDraft.fixture ? <> for <span className="font-semibold">{otherDraft.fixture.homeTeam} v {otherDraft.fixture.awayTeam}</span></> : null}
              {savedAgo(otherDraft.savedAt) ? <span className="text-secondary-400"> · saved {savedAgo(otherDraft.savedAt)}</span> : null}.
            </p>
            <p className="mt-1 text-xs text-secondary-400">It is stored in this browser only and has not been published.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={continueOtherDraft} className="btn btn-sm btn-primary">Continue that draft</button>
              <button type="button" onClick={() => { clearDraft(userId); setOtherDraft(null) }} className="btn btn-sm btn-ghost">Discard it</button>
            </div>
          </div>
        )}

        <FixturePicker
          className="mt-6"
          onChoose={chooseFixture}
          actionLabel="Write a prediction"
          heading={<>
            <h2 className="text-sm font-semibold text-white">Choose a fixture</h2>
            <p className="mt-1 text-xs text-secondary-400">Filter by day, competition or team name.</p>
          </>}
        />

        <details className="card mt-6 p-4">
          <summary className="focus-ring cursor-pointer text-sm font-medium text-secondary-200">
            Advanced: paste a match id
          </summary>
          <p className="mt-2 text-xs text-secondary-400">
            Only needed when you already have an internal match id or a provider fixture id to hand. The list above is
            the normal way in.
          </p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <label htmlFor="manual-match-id" className="sr-only">Match id</label>
            <input
              id="manual-match-id"
              type="text"
              value={manualId}
              onChange={event => setManualId(event.target.value)}
              placeholder="Internal match id or provider fixture id"
              className="form-input min-w-0 flex-1 py-2"
            />
            <button
              type="button"
              disabled={!manualId.trim()}
              onClick={() => setMatchId(manualId.trim())}
              className="btn btn-md btn-secondary"
            >
              Use this id
            </button>
          </div>
        </details>
      </div>
    )
  }

  // ------------------------------------------------------------------ compose
  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <button type="button" onClick={() => navigate('/expert/dashboard')} className="focus-ring mb-4 inline-flex items-center gap-1 text-sm text-primary-300 hover:text-primary-200">
        <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
        Back to dashboard
      </button>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-white sm:text-3xl">Write a prediction</h1>
          {fixture ? (
            <p className="mt-1 truncate text-sm text-secondary-300">
              <span className="font-medium text-white">{fixture.homeTeam.name} v {fixture.awayTeam.name}</span>
              <span className="text-secondary-400"> · {fixture.league.name} · {fixture.date} {fixture.time}</span>
            </p>
          ) : (
            <p className="mt-1 text-sm text-secondary-400">Loading the fixture…</p>
          )}
        </div>
        <button type="button" onClick={changeFixture} className="btn btn-sm btn-secondary flex-shrink-0">
          Change fixture
        </button>
      </div>

      {restoredAt && (
        <div className="mt-4 rounded-lg border border-dark-700 bg-dark-900/60 px-4 py-2.5">
          <p className="text-xs text-secondary-300">
            Draft restored{savedAgo(restoredAt) ? ` · saved ${savedAgo(restoredAt)}` : ''}. It lives in this browser only
            and publishes nothing by itself.
            {!composerIsEmpty(values) && (
              <button type="button" onClick={discardDraft} className="focus-ring ml-2 font-medium text-primary-300 hover:text-primary-200">
                Start again
              </button>
            )}
          </p>
        </div>
      )}

      {fixtureError && (
        <div className="mt-4">
          <EmptyState
            tone="failed"
            title="That fixture could not be opened"
            description={fixtureError}
            variant="inline"
            action={<button type="button" onClick={changeFixture} className="btn btn-sm btn-secondary">Choose from the list</button>}
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
              <h2 className="text-lg font-semibold text-white">Your view</h2>
              <p className="mb-5 mt-1 text-sm text-secondary-400">
                Enter percentages, not decimals — type 55 for 55%. Only the markets you tick are published; the rest
                stay unavailable.
              </p>

              <PredictionMarketsEditor
                values={values}
                onChange={setValues}
                validation={validation}
                showErrors={showErrors}
                homeTeam={fixture.homeTeam.name}
                awayTeam={fixture.awayTeam.name}
                idPrefix="composer"
                disabled={publishing}
              />

              {showErrors && !validation.ready && (
                <p className="mt-4 text-sm text-warning-200" role="status">
                  Fix the fields marked above, then preview.
                </p>
              )}

              <div className="mt-6 flex flex-wrap items-center gap-3">
                <button type="button" onClick={handlePreview} disabled={publishing} className="btn btn-md btn-secondary">
                  Preview
                </button>
                {/* Never disabled for being incomplete: a dead button explains nothing. Pressing it
                    on an incomplete form marks exactly which fields need attention. */}
                <button
                  type="button"
                  onClick={handlePublish}
                  disabled={publishing}
                  className="btn btn-md btn-primary"
                >
                  {publishing ? 'Publishing…' : 'Publish'}
                </button>
                <span className="text-xs text-secondary-400">Publishing makes this public immediately.</span>
              </div>

              {publishError && (
                <p className="form-error mt-3" role="alert">{publishError}</p>
              )}
            </div>

            {previewOpen && <PublishPreview values={values} fixture={draftFixtureOf(fixture)} />}
          </div>

          {/* ------------------------------------------------------------- the evidence */}
          <div className="min-w-0">
            <FixtureEvidence match={fixture} className="lg:sticky lg:top-6" />
          </div>
        </div>
      )}

      <details className="card mt-8 p-4">
        <summary className="focus-ring cursor-pointer text-sm font-medium text-secondary-200">
          Advanced: fixture identifiers
        </summary>
        <p className="mt-2 break-all text-xs text-secondary-400">
          Internal match id: <span className="num">{matchId}</span>
          {fixture?.provider && fixture.externalId && (
            <><br />{fixture.provider}: <span className="num">{fixture.externalId}</span></>
          )}
        </p>
      </details>
    </div>
  )
}

export default ExpertCreatePredictionPage
