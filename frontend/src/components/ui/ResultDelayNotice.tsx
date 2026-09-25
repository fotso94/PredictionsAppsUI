import React from 'react'
import clsx from 'clsx'
import type { DeferralCause, ResultDelay } from '@/utils/resultDelay'
import type { MessageKey } from '@/i18n'
import { useT } from '@/i18n/react'
import { absoluteTime, relativeTime } from './freshness'

/**
 * What a fixture says where its score would be, once its result is past due and has not arrived.
 *
 * ── THE VOICE ───────────────────────────────────────────────────────────────────────────────
 *
 * Borrowed from the freshness block, not invented beside it. That block already had to say "we
 * could not read this, so its age is not known" without either hiding the problem or dressing it
 * up: state the fact, and give the time in the reader's own words with the exact instant behind
 * it as a `title`. Both are here, and `relativeTime`/`absoluteTime` are literally its functions —
 * so "5 hours ago" is rounded on the same boundaries, in the same language, on the same page.
 *
 * ── WHAT IT SAYS, AND ONLY THAT ─────────────────────────────────────────────────────────────
 *
 * Facts, each read from a field rather than from prose: the result was due at a moment, it has not
 * reached us, whether we are still asking when the row's record shows it, what our latest check
 * found when the backend says (a call that could not reach the provider, an answer without a
 * result, a check that was never sent - named by whose limit or which wait kept it back - or a
 * stored copy read instead of a call), and — once `gaveUpAt` is set — that we stopped asking at another moment.
 * "Unresolved"
 * is about our asking. It is not a finding about the match or about what the provider holds, and
 * the notice says so in as many words, because "we stopped" read on its own is easily heard as
 * "there is nothing to find".
 *
 * The backend's `gave_up_reason` is NOT printed. It is English prose written for whoever runs the
 * sweep: on a French page it would be the one untranslated line, and nothing reviews what it says
 * about the provider before a reader would see it. A reader is given a sentence this product
 * reviewed, in their language: the retry budget's own sentence where the row says the budget made
 * the stop (`stopped_by: retry_budget`), and one that names no policy where it does not — a stop
 * left by a rule since removed, which the backend undoes on its next recovery pass.
 *
 * ── WHAT IT MAY NOT DO ──────────────────────────────────────────────────────────────────────
 *
 * Name a score, imply one, or write FT. A fixture caught here may be carrying a half-time 0-0
 * that arrived before the feed went quiet, and that number is not the result of the match: nobody
 * has said the match ended, let alone ended there. So the callers withhold the scoreline and this
 * takes its place — the same rule the probability helpers follow for a market a source never
 * published, where the answer is the word "unavailable" and never the number 0.
 */

/*
 * A check that never left, worded by WHY it never left (`deferralCauseOf`). Only `our_allowance`
 * says "our own allowance": the provider's reported limit is not ours, and a pause after an earlier
 * failure is neither a limit nor this check's failure. Anything else says only that it was not sent.
 */
const HELD_BACK_SHORT: Record<DeferralCause, MessageKey> = {
  our_allowance: 'fixture.result.heldBackShort',
  provider_allowance: 'fixture.result.heldBackProviderShort',
  cooling_down: 'fixture.result.heldBackCoolingShort',
  unknown: 'fixture.result.heldBackOtherShort',
}
const HELD_BACK_SENTENCE: Record<DeferralCause, MessageKey> = {
  our_allowance: 'fixture.result.lastCheckHeldBack',
  provider_allowance: 'fixture.result.lastCheckHeldBackProvider',
  cooling_down: 'fixture.result.lastCheckHeldBackCooling',
  unknown: 'fixture.result.lastCheckHeldBackOther',
}

export interface ResultDelayProps {
  delay: ResultDelay
  className?: string
}

/** The two words, one per state. */
function label(delay: ResultDelay, t: ReturnType<typeof useT>): string {
  return t(delay.state === 'given_up' ? 'fixture.result.givenUp' : 'fixture.result.overdue')
}

/**
 * The short word for a status slot — the column that would otherwise read LIVE, a minute, or a
 * kickoff time that has passed.
 *
 * `title` carries the two things the column has no room for: which fixture the word is about, and
 * the exact deadline the claim is made against, so it can be checked rather than taken on trust.
 * The instant is the deadline for both states — a fixture given up on was due at the same moment as
 * one still being waited for, and WHEN it was given up on is the sentence in the notice below.
 * `absoluteTime` cannot fail here: a `ResultDelay` exists only where the deadline parsed.
 */
export const ResultDelayLabel: React.FC<ResultDelayProps & { withTitle?: string }> = ({
  delay, className, withTitle,
}) => {
  const t = useT()
  const text = label(delay, t)
  const due = absoluteTime(delay.expectedBy)
  return (
    <span
      className={clsx(
        'text-[11px] font-semibold uppercase tracking-wide',
        delay.state === 'given_up' ? 'text-secondary-300' : 'text-warning-200',
        className,
      )}
      data-testid="result-delay-label"
      data-result-delay={delay.state}
      title={withTitle
        ? t('fixture.result.title', { fixture: withTitle, state: text, due: due ?? '' })
        : undefined}
    >
      {text}
    </span>
  )
}

/**
 * One line for a dense row: the short form of what happened, and nothing else.
 *
 * The full sentence takes four lines at 360px and pushes the club names out of sight, so the row
 * gets the half that carries the news. The half it drops — "no score is claimed" — is the half
 * the row demonstrates anyway: there is no scoreline beside it to be misread.
 */
export const ResultDelayLine: React.FC<ResultDelayProps> = ({ delay, className }) => {
  const t = useT()
  /*
   * `due` measures the DEADLINE and the sentence around it says so. It is not how long ago the
   * match kicked off, and the two are hours apart: the deadline is the kickoff plus the backend's
   * grace, which on this installation is 150 minutes, so a fixture that started six hours ago was
   * due three and a half hours ago. Both are true statements and only one of them is the one this
   * number supports.
   */
  const due = relativeTime(delay.expectedBy)
  const when = relativeTime(delay.gaveUpAt)
  /*
   * Stopping outranks everything else on the row: "we stopped asking" will still be true tomorrow,
   * and a last check belongs to one pass. On an overdue row, a check that learned nothing is the
   * news, because it is why nothing new is known — so it takes the sentence's second half. There
   * are two of those and they are opposite kinds of fact: a call that went out and failed, and a
   * call that never left. The second is not this check's failure, and its sentence names the cause
   * the backend recorded - ours, the provider's, or a pause after an earlier failure.
   */
  const text = delay.state === 'given_up' && when
    ? t('fixture.result.givenUpShort', { when })
    : delay.lastCheck?.kind === 'unreachable'
      ? t('fixture.result.unreachableShort', { due: due ?? '' })
      : delay.lastCheck?.kind === 'held_back'
        ? t(HELD_BACK_SHORT[delay.lastCheck.heldBackBy ?? 'unknown'], { due: due ?? '' })
        : t('fixture.result.overdueShort', { due: due ?? '' })
  return (
    <span
      className={clsx('text-[11px]', delay.state === 'given_up' ? 'text-secondary-300' : 'text-warning-200', className)}
      data-testid="result-delay-line"
      data-result-delay={delay.state}
      data-last-check={delay.lastCheck?.kind}
      title={absoluteTime(delay.gaveUpAt ?? delay.expectedBy) ?? undefined}
    >
      {text}
    </span>
  )
}

/**
 * The most recent pass's finding, in words, or null when there is nothing to add.
 *
 * An empty answer is not repeated on a fixture already given up on: the attempts line beside it
 * says the same thing with a count. Every other finding is said whenever the row records one,
 * because nothing else in the notice can say it.
 */
function lastCheckSentence(delay: ResultDelay, t: ReturnType<typeof useT>): string | null {
  const check = delay.lastCheck
  const when = relativeTime(check?.at)
  if (!check || !when) return null
  switch (check.kind) {
    case 'unreachable': return t('fixture.result.lastCheckUnreachable', { when })
    case 'held_back': return t(HELD_BACK_SENTENCE[check.heldBackBy ?? 'unknown'], { when })
    case 'stored_copy': return t('fixture.result.lastCheckStoredCopy', { when })
    case 'answered_empty':
      return delay.state === 'overdue' ? t('fixture.result.lastCheckEmpty', { when }) : null
  }
}

/**
 * The whole statement, for a card and for the match page: what state this is, and why.
 *
 * `attempts` and the policy sentence only ever appear on a fixture that was given up on. The count
 * is what separates an admission from an excuse: a reader told that the provider answered three
 * times without a result can judge for themselves how hard it was pursued. It is shown only when
 * above zero — a fixture retired by age can have no answered attempt at all, and "answered 0
 * times" would describe a chase that did not happen.
 */
export const ResultDelayNotice: React.FC<ResultDelayProps> = ({ delay, className }) => {
  const t = useT()
  const givenUp = delay.state === 'given_up'
  // The deadline, not the kickoff — see ResultDelayLine above for why the two must not be swapped.
  const due = relativeTime(delay.expectedBy)
  const when = relativeTime(delay.gaveUpAt)
  const lastCheck = lastCheckSentence(delay, t)
  return (
    <div
      role="status"
      data-testid="result-delay-notice"
      data-result-delay={delay.state}
      className={clsx(
        'rounded-lg border px-3 py-2 text-left',
        givenUp ? 'border-dark-700 bg-dark-800/60' : 'border-warning-500/40 bg-warning-500/10',
        className,
      )}
    >
      <p className={clsx('text-xs font-semibold uppercase tracking-wide',
        givenUp ? 'text-secondary-200' : 'text-warning-200')}>
        {label(delay, t)}
      </p>
      <p
        className="mt-1 text-xs text-secondary-200"
        data-testid="result-delay-detail"
        // The exact instant behind the rounded phrase, for anyone who needs the real value.
        title={absoluteTime(delay.gaveUpAt ?? delay.expectedBy) ?? undefined}
      >
        {givenUp && when
          ? t('fixture.result.givenUpDetail', { when })
          : t('fixture.result.overdueDetail', { due: due ?? '' })}
      </p>
      {/*
        The other half of the difference between the two states, said as plainly as "we stopped
        asking" is on the other one — and only where the row's own record supports it (see
        `stillAsking`). Without it, "Result overdue" on a fixture the backend has just put back
        under its retry schedule would leave the reader to guess which side of the line it is on.
      */}
      {delay.stillAsking && (
        <p className="mt-1 text-xs text-secondary-200" data-testid="result-delay-asking">
          {t('fixture.result.stillAsking')}
        </p>
      )}
      {lastCheck && (
        <p
          className="mt-1 text-xs text-secondary-300"
          data-testid="result-delay-last-check"
          data-last-check={delay.lastCheck?.kind}
          title={absoluteTime(delay.lastCheck?.at) ?? undefined}
        >
          {lastCheck}
        </p>
      )}
      {givenUp && typeof delay.attempts === 'number' && delay.attempts > 0 && (
        <p className="mt-1 text-xs text-secondary-400" data-testid="result-delay-attempts">
          {t('fixture.result.attempts', { count: delay.attempts })}
        </p>
      )}
      {givenUp && (
        <p className="mt-1 text-xs text-secondary-400" data-testid="result-delay-policy">
          {t(delay.budgetStop ? 'fixture.result.givenUpPolicy' : 'fixture.result.givenUpOtherPolicy')}
        </p>
      )}
    </div>
  )
}

export default ResultDelayNotice
