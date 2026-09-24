import React, { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { ChevronDownIcon } from '@heroicons/react/24/outline'
import { BriefSourceKey, Match } from '@/types'
import { isMatchFinished, isMatchLive } from '@/utils/matchFilters'
import { marketLabel, missingReasonLabel, percentDisplay } from '@/utils/brief'
import { formatTime } from '@/i18n'
import { useT } from '@/i18n/react'
import { fixturePreview, SourcePreview } from '@/utils/matchPreview'
import { onTeamLogoError } from './imageFallback'
import { periodLines } from './scoreline'
import SourceMarker from './SourceMarker'
import SaveMatchButton from './SaveMatchButton'
import ProvenanceLine from './ProvenanceLine'

/**
 * One fixture as a dense row — the unit the matches-first workspace is built from.
 *
 * MatchCard is a tall card that repeats the venue, both team labels, every market, a confidence
 * badge per market and an unavailable-odds line; twenty of them is a scroll, not a scan. This row
 * keeps only what a reader needs to decide whether to look closer — when it kicks off, who is
 * playing, what the sources make most likely, and whether it is saved — and moves everything else
 * behind one expand control. MatchCard stays exactly as it is: other pages still use it.
 *
 * WHAT IS NOT SHOWN, AND WHY
 *  - No confidence badge derived from how strong a probability looks. A band worked out from the
 *    numbers is not a confidence the source claimed, and it is certainly not a measured accuracy —
 *    nothing here has ever been scored against a result. A confidence appears only when the source
 *    actually published one, and it says so in words.
 *  - No 0% for a market a source left out. An absent market shows the brief's own reason for being
 *    absent, which is a different fact from "the source thinks it will not happen".
 *
 * THE SOURCE MARKER IS READABLE ON A PHONE. MatchCard hides its source label below the `sm`
 * breakpoint behind a `title`, which a touch user can never open — so on the screen where most of
 * this is read, who produced the number is unavailable. `SourceMarker` renders the word at every
 * width; this row never hides it.
 */

export interface FixtureRowProps {
  match: Match
  /**
   * Controlled expansion. Omit both this and `onToggleExpanded` and the row manages its own.
   */
  expanded?: boolean
  onToggleExpanded?: (matchId: string, next: boolean) => void
  /** Initial state when uncontrolled. */
  defaultExpanded?: boolean
  /** Whether this match is saved, as the caller believes it to be (optimistic value included). */
  saved?: boolean
  /** A save/unsave write is in flight for this match. */
  savePending?: boolean
  /** Omit to hide the save control entirely (a list where saving makes no sense). */
  onToggleSave?: (matchId: string, next: boolean) => void
  /** False renders the save control as a sign-in prompt instead of a toggle. */
  signedIn?: boolean
  onRequireSignIn?: () => void
  /** Where the fixture's own page lives. Defaults to `/match/{id}`. */
  href?: string
  /** Show the competition name under the teams. Off inside a list already grouped by competition. */
  showCompetition?: boolean
  /** Hide the expand control (and the detail) for a read-only summary list. */
  expandable?: boolean
  className?: string
}

/** A probability the reader can compare at a glance, with the number always present as text. */
const ProbabilityBar: React.FC<{ percent: number; emphasis: boolean }> = ({ percent, emphasis }) => (
  <span
    aria-hidden="true"
    className="block h-1 w-full overflow-hidden rounded-full bg-dark-700"
  >
    <span
      className={clsx('block h-full rounded-full', emphasis ? 'bg-primary-400' : 'bg-secondary-500')}
      style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
    />
  </span>
)

/** One source's match-result view, or the reason it has none. Used only inside the detail panel. */
const SourceDetail: React.FC<{ preview: SourcePreview; homeName: string; awayName: string }> = ({
  preview, homeName, awayName,
}) => {
  const t = useT()
  // The club names are the provider's and stay as published; only "Draw" is a word of ours.
  const nameFor = (key: string) =>
    (key === 'home_win' ? homeName : key === 'away_win' ? awayName : t('outcome.draw'))

  return (
    <div className="min-w-0 flex-1" data-testid={`fixture-detail-${preview.source}`}>
      <div className="flex items-center gap-2">
        <SourceMarker source={preview.source} state={preview.state} />
        {preview.confidence && (
          // Only ever shown when the source PUBLISHED a value, and labelled as the source's own
          // claim — never as an accuracy, which nothing here has measured.
          <span className="num text-[11px] text-secondary-300">
            {t('fixture.confidencePublished', {
              percent: percentDisplay(preview.confidence.percent) ?? String(preview.confidence.percent),
              source: preview.source,
            })}
          </span>
        )}
      </div>

      {preview.outcomes.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {preview.outcomes.map(outcome => (
            <li key={outcome.key}>
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="min-w-0 truncate text-secondary-200">{nameFor(outcome.key)}</span>
                <span className="num font-semibold text-white">
                  {percentDisplay(outcome.percent) ?? `${outcome.percentText}%`}
                </span>
              </div>
              <ProbabilityBar percent={outcome.percent} emphasis={outcome.key === preview.lead?.key} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-secondary-300" data-testid={`fixture-detail-${preview.source}-unavailable`}>
          {/* The backend's own sentence, verbatim. Never "0%", never a blank space. */}
          {preview.detail ?? missingReasonLabel(preview.reason) ?? t('fixture.noMatchResult')}
        </p>
      )}
    </div>
  )
}

const FixtureRow: React.FC<FixtureRowProps> = ({
  match,
  expanded,
  onToggleExpanded,
  defaultExpanded = false,
  saved = false,
  savePending = false,
  onToggleSave,
  signedIn = true,
  onRequireSignIn,
  href,
  showCompetition = true,
  expandable = true,
  className,
}) => {
  const t = useT()
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultExpanded)
  const isControlled = expanded !== undefined
  const open = isControlled ? expanded : uncontrolledOpen
  const detailId = useId()

  const preview = fixturePreview(match)
  const live = isMatchLive(match)
  const finished = isMatchFinished(match)
  const showScore = (live || finished) && Boolean(match.result)
  const fixtureLabel = t('fixture.versus', { home: match.homeTeam.name, away: match.awayTeam.name })

  const toggle = () => {
    const next = !open
    if (!isControlled) setUncontrolledOpen(next)
    onToggleExpanded?.(match.id, next)
  }

  /**
   * The kickoff column. Live shows the word LIVE and the minute; a played match shows FT; anything
   * else shows the local kickoff time. Postponed and cancelled keep their own word rather than a
   * time that is no longer going to happen.
   */
  const statusColumn = () => {
    if (live) {
      return (
        <>
          <span className="text-[11px] font-semibold uppercase tracking-wide text-success-300">{t('fixture.live')}</span>
          {match.minute && <span className="num text-sm font-semibold text-success-300">{match.minute}&rsquo;</span>}
        </>
      )
    }
    if (finished) return <span className="text-[11px] font-semibold uppercase tracking-wide text-secondary-300">{t('fixture.ft')}</span>
    if (match.status === 'postponed') return <span className="text-[11px] font-semibold uppercase text-warning-200">{t('fixture.postponed')}</span>
    if (match.status === 'cancelled') return <span className="text-[11px] font-semibold uppercase text-danger-300">{t('fixture.cancelled')}</span>
    /*
     * THE KICK-OFF IS RE-FORMATTED FROM THE UTC INSTANT ON EVERY RENDER, not read from
     * `match.time`.
     *
     * `match.time` is written once, when the payload is mapped, in whatever zone was chosen at
     * that moment — so a reader who changes zone with a day already on screen would keep the old
     * clock until the data was refetched. Formatting `kickoffUtc` here makes the change immediate
     * and makes the row's `dateTime` attribute and its visible text the same instant by
     * construction. `match.time` remains the fallback for a payload that carries no instant, and
     * the mapper still writes it in the chosen zone for exactly that case.
     */
    return (
      <time className="num text-sm font-semibold text-white" dateTime={match.kickoffUtc ?? undefined}>
        {formatTime(match.kickoffUtc) ?? match.time}
      </time>
    )
  }

  const teamLine = (name: string, logo: string, score: number | undefined, winner: boolean) => (
    <span className="flex items-center gap-2 min-w-0">
      <img src={logo} alt="" aria-hidden="true" className="h-4 w-4 flex-shrink-0 object-contain" onError={onTeamLogoError} />
      <span className={clsx('truncate text-sm', winner ? 'font-semibold text-white' : 'text-secondary-100')}>{name}</span>
      {typeof score === 'number' && (
        <span className={clsx('num ml-auto flex-shrink-0 text-sm font-semibold', winner ? 'text-white' : 'text-secondary-200')}>
          {score}
        </span>
      )}
    </span>
  )

  const homeScore = showScore ? match.result?.homeScore : undefined
  const awayScore = showScore ? match.result?.awayScore : undefined

  /**
   * The rest of a knockout tie, on one short line under the two club names.
   *
   * The two numbers above are the football that was played; a shoot-out is not one of them and is
   * never shown as one. Without this line a tie won 4-3 on penalties reads as the 0-0 it also was,
   * and the reader is left with half the result. Short forms, because a full sentence here pushes
   * the club names off a phone; empty for the ordinary match, which is most of them.
   */
  const periodNote = showScore ? periodLines(match.result, true).join(' · ') : ''

  /**
   * Compact per-source preview: who said it, and what they make most likely.
   *
   * The side is named "Home"/"Draw"/"Away" rather than by club, because a club name is as long as
   * the whole row on a phone and the two clubs are already the line beside it. The team IS named,
   * in the marker's own accessible description, so nothing is lost to anybody reading it aloud.
   */
  const marker = (source: BriefSourceKey) => {
    const side = source === 'model' ? preview.model : preview.expert
    const shortSide = side.lead
      ? t(side.lead.key === 'home_win' ? 'fixture.side.home'
        : side.lead.key === 'away_win' ? 'fixture.side.away'
          : 'fixture.side.draw')
      : null
    const teamName = side.lead
      ? side.lead.key === 'home_win' ? match.homeTeam.name
        : side.lead.key === 'away_win' ? match.awayTeam.name
          : t('fixture.aDraw')
      : null
    return (
      <SourceMarker
        key={source}
        source={source}
        state={side.lead ? side.state : 'unavailable'}
        detail={side.lead && shortSide
          ? `${shortSide} ${percentDisplay(side.lead.percent) ?? `${side.lead.percentText}%`}`
          : null}
        title={side.lead && teamName
          ? t('fixture.leadTitle', {
            source: side.label,
            outcome: teamName,
            percent: percentDisplay(side.lead.percent) ?? `${side.lead.percentText}%`,
          })
          : (side.detail ?? undefined)}
      />
    )
  }

  return (
    <div
      className={clsx('border-b border-dark-800 last:border-b-0', className)}
      data-testid="fixture-row"
      data-match-id={match.id}
    >
      {/*
        `flex-wrap` plus `order-last` on the preview is what keeps this row honest on a phone: below
        `sm` the markers take a full-width second line under the teams instead of squeezing the club
        names out of existence. An earlier version let them share the line and, at 375px, the row
        showed a kickoff time and two probabilities with no teams at all.
      */}
      <div className="tap-target-row flex flex-wrap items-stretch gap-x-2 gap-y-1.5 px-2 py-2 transition-colors hover:bg-dark-800/60 sm:flex-nowrap sm:px-3">
        {/* Kickoff / live status */}
        <div className="flex w-12 flex-col items-center justify-center gap-0 text-center sm:w-14">
          {statusColumn()}
        </div>

        {/* Teams, and the fixture link. The trailing controls sit OUTSIDE this link: nesting a
            button inside an anchor is invalid, and a whole-row overlay link would swallow them. */}
        <Link
          to={href ?? `/match/${match.id}`}
          className="focus-ring -mx-1 flex min-w-0 flex-1 flex-col justify-center gap-0.5 rounded px-1"
          aria-label={t('fixture.openAnalysis', { fixture: fixtureLabel })}
        >
          {teamLine(match.homeTeam.name, match.homeTeam.logo, homeScore, showScore && (homeScore ?? 0) > (awayScore ?? 0))}
          {teamLine(match.awayTeam.name, match.awayTeam.logo, awayScore, showScore && (awayScore ?? 0) > (homeScore ?? 0))}
          {periodNote && (
            <span className="truncate text-[11px] text-secondary-300" data-testid="fixture-row-periods">{periodNote}</span>
          )}
          {showCompetition && (
            <span className="truncate text-[11px] text-secondary-400">{match.league.name}</span>
          )}
        </Link>

        {/* Probability preview. Full width on its own line below `sm`, right-hand column above it. */}
        <div
          className="order-last flex w-full flex-wrap items-center gap-1 pl-14 sm:order-none sm:w-auto sm:flex-col sm:flex-nowrap sm:items-end sm:justify-center sm:pl-0"
          data-testid="fixture-row-preview"
        >
          {marker('model')}
          {marker('expert')}
        </div>

        <div className="flex items-center gap-0.5">
          {onToggleSave && (
            <SaveMatchButton
              saved={saved}
              pending={savePending}
              signedIn={signedIn}
              onRequireSignIn={onRequireSignIn}
              onToggle={next => onToggleSave(match.id, next)}
              matchLabel={fixtureLabel}
              size="sm"
            />
          )}
          {expandable && (
            <button
              type="button"
              onClick={toggle}
              aria-expanded={open}
              aria-controls={detailId}
              aria-label={t(open ? 'fixture.hideDetails' : 'fixture.showDetails', { fixture: fixtureLabel })}
              className="tap-target focus-ring rounded-lg text-secondary-300 transition-colors hover:bg-dark-700 hover:text-white"
              data-testid="fixture-row-expand"
            >
              <ChevronDownIcon
                className={clsx('h-4 w-4 transition-transform', open && 'rotate-180')}
                aria-hidden="true"
              />
            </button>
          )}
        </div>
      </div>

      {expandable && (
        <div id={detailId} hidden={!open} className="px-3 pb-3 pt-1" data-testid="fixture-row-detail">
          {open && (
            <div className="rounded-lg border border-dark-700 bg-dark-900/60 p-3">
              {preview.headline && (
                // The brief's own sentence, assembled by the backend from published numbers.
                <p className="mb-3 text-xs text-secondary-200">{preview.headline}</p>
              )}

              <div className="flex flex-col gap-4 sm:flex-row sm:gap-6">
                <SourceDetail preview={preview.model} homeName={match.homeTeam.name} awayName={match.awayTeam.name} />
                <SourceDetail preview={preview.expert} homeName={match.homeTeam.name} awayName={match.awayTeam.name} />
              </div>

              <OtherMarkets match={match} />

              <ProvenanceLine
                className="mt-3 border-t border-dark-700 pt-2"
                source={match.providerForecast?.providerName ?? match.providerForecast?.source_type ?? null}
                freshness={match.brief?.freshness ?? null}
                compact={match.briefCompact ?? null}
              />

              <div className="mt-2 flex items-center justify-between gap-2">
                {match.venue && <span className="truncate text-[11px] text-secondary-400">{match.venue}</span>}
                <Link
                  to={href ?? `/match/${match.id}`}
                  className="focus-ring ml-auto flex-shrink-0 rounded text-xs font-medium text-primary-300 underline-offset-2 hover:text-primary-200 hover:underline"
                >
                  {t('fixture.fullAnalysis')}
                </Link>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Which other markets each source supplied, from the compact brief's own lists.
 *
 * Names only, not numbers: the compact brief carries no probabilities for these, and the row is not
 * going to work any out. "The model also published both-teams-to-score" is a fact the payload
 * states; the value behind it lives on the match page.
 */
const OtherMarkets: React.FC<{ match: Match }> = ({ match }) => {
  const t = useT()
  const compact = match.briefCompact
  if (!compact) return null
  const rows: Array<[BriefSourceKey, string]> = (['model', 'expert'] as const)
    .map(source => [source, (compact.supplied_markets?.[source] ?? [])
      .filter(key => key !== 'match_result')
      .map(marketLabel)
      .join(', ')] as [BriefSourceKey, string])
    .filter(([, list]) => list.length > 0)

  if (rows.length === 0) return null

  return (
    <dl className="mt-3 space-y-1 border-t border-dark-700 pt-2 text-[11px]">
      {rows.map(([source, list]) => (
        <div key={source} className="flex gap-2">
          <dt className="flex-shrink-0 text-secondary-400">{t('fixture.alsoPublished', { source })}</dt>
          <dd className="min-w-0 text-secondary-200">{list}</dd>
        </div>
      ))}
    </dl>
  )
}

export default FixtureRow
