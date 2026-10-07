import React, { useEffect, useState } from 'react'
import { ChevronRightIcon, ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { footballDataService } from '@/services/football-data.service'
import { ProviderStatus } from '@/services/match-data-source'
import { forecastAvailability } from './forecastStatus'
import { matchDataNotice, type MatchDataSourceLine } from './matchDataState'
import { useT } from '@/i18n/react'

/**
 * The site-wide banner: FAULTS ONLY, one line, with the operator detail one tap away.
 *
 * WHAT IT NO LONGER SAYS, AND WHY. It used to lead every page — above the fixtures, above the
 * scoreline, above everything — with the model provider's own quota prose, URL and all. On a phone
 * that was two hundred pixels of vendor billing text before any football, and the same fact was
 * then repeated by the freshness block and a third time by the match page's data-state notice. A
 * spent daily allowance is not a fault: nothing on screen is wrong, nothing is unreachable, and
 * new forecasts simply are not arriving for a while. It belongs beside the forecasts it affects,
 * which is where DataFreshness now states it — once, with the time it comes back.
 *
 * So this renders only when something is genuinely BROKEN and a page cannot be refreshed at all:
 * no match-data provider configured, the primary one missing and a fallback standing in, the
 * fixture provider cooling down or failing its last request, its own request budget spent, or the
 * forecast provider not configured (which means no model forecasts exist at all, rather than none
 * arriving today).
 *
 * WHAT IS STILL HERE, JUST NOT IN YOUR FACE. The first fault is the visible line. Everything
 * else — the remaining faults, and any paused refresh — is inside the disclosure, so nothing that
 * was reported before has stopped being reported. A native <details>: keyboard-operable, announced
 * as expandable, and working without JavaScript.
 *
 * Renders nothing when everything is healthy, when the status endpoint is unavailable, or when the
 * only thing to report is a paused refresh.
 *
 * AND WHEN FIXTURE AND RESULT UPDATES ARE BLOCKED, IT SAYS THAT AND ONLY THAT. The backend's
 * `match_data` block reads `blocked` when no configured source can deliver fixtures or results —
 * on 2026-10-07 all three refused at once while the forecast provider answered. The rules above
 * looked at the first source alone and led with "Fixture provider livescore is paused after a
 * failure: livescore: authentication rejected (HTTP 401): …", in English on the French page too: an
 * internal key, a vendor's sentence, a "pause" that was nothing of the kind, and not a word about
 * the other two sources, about since when, or about the forecasts that were still fine. So the lead
 * becomes the one sentence a reader needs, from `matchDataNotice`, and every source's reason —
 * ours, then the provider's own words verbatim and marked as English — moves into the disclosure.
 * Any other state, and a backend that sends no block at all, gets exactly the rules above.
 */

/**
 * One source in the disclosure: our reason, then the provider's own words.
 *
 * The verbatim message is English whatever the page's language, and is marked `lang="en"` so a
 * screen reader reads it in an English voice rather than mispronouncing it as French.
 */
const SourceLine: React.FC<{ source: MatchDataSourceLine }> = ({ source }) => {
  const t = useT()
  const verbatim = source.verbatim
  const said = verbatim ? t('freshness.task.providerSaid', { reason: verbatim }) : null
  const at = said && verbatim ? said.indexOf(verbatim) : -1
  return (
    <li
      className="break-words"
      data-testid="match-data-source"
      data-source={source.name}
      data-answer={source.answer}
      data-kind={source.kind ?? undefined}
    >
      {t('banner.matchData.source', { source: source.label, reason: source.reason })}
      {said && verbatim && (
        <>
          {' '}
          {at < 0 ? said : (
            <>
              {said.slice(0, at)}
              <span lang="en" data-testid="match-data-verbatim">{verbatim}</span>
              {said.slice(at + verbatim.length)}
            </>
          )}
        </>
      )}
    </li>
  )
}

const ProviderStatusBanner: React.FC = () => {
  const [status, setStatus] = useState<ProviderStatus | null>(null)
  const [dismissed, setDismissed] = useState(false)
  const t = useT()

  useEffect(() => {
    let cancelled = false
    footballDataService.getProviderStatus().then(result => {
      if (!cancelled) setStatus(result)
    })
    return () => { cancelled = true }
  }, [])

  if (!status || dismissed) return null

  /** Something is broken: data cannot be refreshed until somebody changes a configuration or a key. */
  const faults: string[] = []
  /** The first source's own failure line — replaced, when blocked, by one line per source. */
  let sourceFault: string | null = null
  const active = status.chain[0]
  if (!active) {
    faults.push(t('banner.noProvider', { provider: status.active_provider }))
  } else {
    if (active.name !== status.active_provider) {
      faults.push(t('banner.fallbackInUse', { provider: status.active_provider, fallback: active.name }))
    }
    if (active.budget && active.budget.enforced && active.budget.remaining_today === 0) {
      faults.push(t('banner.budgetExhausted', { provider: active.name }))
    }
    if (active.cooling_down) {
      // `{reason}` is the provider's own message, carried through verbatim in every language.
      sourceFault = t('banner.providerCoolingDown', { provider: active.name, reason: active.cooling_down })
      faults.push(sourceFault)
    } else if (active.last_error && (!active.last_success_at || (active.last_error_at || '') > active.last_success_at)) {
      sourceFault = t('banner.lastRequestFailed', { provider: active.name, reason: active.last_error })
      faults.push(sourceFault)
    }
  }

  /*
   * Paused refresh vs unavailable forecasts: one shared helper so the two never blur together here
   * and on the match pages. A provider that is not configured at all is a fault and leads; a pause
   * is not, and travels in the disclosure so the banner does not appear for it alone.
   */
  const forecasts = forecastAvailability(status)
  const forecastFault = forecasts && !forecasts.paused ? forecasts.message : null
  if (forecastFault) faults.push(forecastFault)
  const pause = forecasts?.paused
    ? [forecasts.message, forecasts.resume].filter(Boolean).join(' ')
    : null

  const blocked = matchDataNotice(status.match_data, Date.now(), status.chain)
  if (blocked) {
    // The lead promises that forecasts are still shown; when the forecast source has a fault of its
    // own that promise would be false, so the fault takes its place on the visible line instead.
    const lead = forecastFault ? `${blocked.leadWithoutForecasts} ${forecastFault}` : blocked.lead
    // Everything that is not about a source refusing stays, after the sources, in the order above.
    const others = [
      ...faults.filter(line => line !== sourceFault && line !== forecastFault),
      ...(blocked.nextCheck ? [blocked.nextCheck] : []),
      ...(pause ? [pause] : []),
    ]
    const count = blocked.sources.length + others.length
    return (
      <div
        className="bg-yellow-900/30 border-b border-yellow-800 text-yellow-100"
        role="status"
        data-testid="provider-status-banner"
        data-state="blocked"
      >
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-2 text-sm">
          <div className="flex items-start gap-3">
            <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <p className="min-w-0 flex-1 break-words" data-testid="match-data-lead" title={blocked.sinceIso ?? undefined}>
              {lead}
            </p>
            <button
              onClick={() => setDismissed(true)}
              className="focus-ring flex-shrink-0 rounded text-yellow-200 hover:text-white"
              aria-label={t('banner.dismiss')}
            >
              <XMarkIcon className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

          {count > 0 && (
            <details className="group ml-8 mt-1" data-testid="match-data-detail">
              <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs text-yellow-200/90 hover:text-white">
                <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
                {count === 1 ? t('banner.oneMoreDetail') : t('banner.moreDetails', { count })}
              </summary>
              <ul className="mt-1 space-y-0.5 text-xs text-yellow-200/90">
                {blocked.sources.map(source => <SourceLine key={source.name} source={source} />)}
                {others.map(line => <li key={line} className="break-words">{line}</li>)}
              </ul>
            </details>
          )}
        </div>
      </div>
    )
  }

  if (faults.length === 0) return null

  const [lead, ...rest] = faults
  const detail = pause ? [...rest, pause] : rest

  return (
    <div className="bg-yellow-900/30 border-b border-yellow-800 text-yellow-100" role="status" data-testid="provider-status-banner">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-2 text-sm">
        <div className="flex items-start gap-3">
          <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 mt-0.5" aria-hidden="true" />
          {/*
            `min-w-0` is load-bearing. `flex-1` is `flex: 1 1 0%` with the default `min-width:auto`,
            so without it this refuses to shrink below its min-content width — and a provider
            message containing an unbreakable vendor URL made that wider than a 360px phone, which
            scrolled the whole document sideways and clipped the dismiss button off the screen.
            `break-words` makes the URL itself wrap rather than set that minimum.
          */}
          <p className="min-w-0 flex-1 break-words">{lead}</p>
          <button
            onClick={() => setDismissed(true)}
            className="focus-ring flex-shrink-0 rounded text-yellow-200 hover:text-white"
            aria-label={t('banner.dismiss')}
          >
            <XMarkIcon className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {detail.length > 0 && (
          <details className="group ml-8 mt-1">
            <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs text-yellow-200/90 hover:text-white">
              <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
              {detail.length === 1
                ? t('banner.oneMoreDetail')
                : t('banner.moreDetails', { count: detail.length })}
            </summary>
            <ul className="mt-1 space-y-0.5 text-xs text-yellow-200/90">
              {detail.map(line => <li key={line} className="break-words">{line}</li>)}
            </ul>
          </details>
        )}
      </div>
    </div>
  )
}

export default ProviderStatusBanner
