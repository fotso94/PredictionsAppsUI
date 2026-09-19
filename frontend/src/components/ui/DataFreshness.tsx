import React from 'react'
import clsx from 'clsx'
import { CheckCircleIcon, ChevronRightIcon, ClockIcon, NoSymbolIcon, QuestionMarkCircleIcon } from '@heroicons/react/24/outline'
import type { ProviderStatus } from '@/services/match-data-source'
import type { FreshnessTone } from '@/utils/brief'
import {
  allowanceResetNote, describeTasks, freshnessReport, fixtureProviderLabel, retrievalFact, worseTone,
} from './freshness'
import { forecastAvailability } from './forecastStatus'
import { useT } from '@/i18n/react'

/**
 * "Last updated", where the reader actually needs it — and now as TWO answers, not one.
 *
 * Every page in this application reads stored data. That is deliberate — it is fast, it spends no
 * request allowance and it never invents a number — but it means the one question a reader cannot
 * otherwise answer is how old what they are looking at is. This answers it, quietly, with the
 * detail one tap away.
 *
 * WHY TWO LINES AND NOT ONE. Fixtures and model forecasts refresh on different schedules from
 * different providers, and on this installation they are routinely days apart. A single line took
 * the most recent success across every task, so a live-score pass from a minute ago made a
 * forecast nobody had refreshed in two days read as current. Two lines cost one row of text; one
 * line cost the reader a fact that was not true.
 *
 * WHY THIS IS THE ONLY PLACE THE FORECAST PAUSE IS STATED ON A PAGE. A reader used to meet the
 * same spent allowance three times before reaching any football: a site-wide banner, this block,
 * and the match page's own data-state notice. Three notices about one fact is not three times the
 * honesty — it is a false impression built out of true sentences. The banner now reports only
 * faults that stop data arriving at all, the match page's notice speaks only about THAT fixture,
 * and the state of the refresh is said here, once, beside the ages it explains.
 *
 * WHAT IS IN THE LINES AND WHAT IS BEHIND THE DISCLOSURE. The lines carry the facts that change
 * how the page should be read: that this is stored data, how old each half of it is, and — when
 * one applies — that a refresh is paused and when it comes back. The per-task breakdown, the
 * cadences and the provider bookkeeping go behind the disclosure, because they are operator
 * detail, not a reason to doubt what is on screen.
 *
 * WHAT IS NEVER MERGED. Three different timestamps exist and the panel keeps them apart by name:
 * when the provider's model ran (a fact about the forecast, published per forecast on the match
 * page), when we last retrieved anything from the provider, and when our own scheduled refresh
 * last succeeded. A scheduled pass can succeed without making a single provider request, so the
 * second and third are genuinely different numbers — and where one is unknown the panel says
 * "unknown" rather than showing whichever of the others happens to exist.
 */

/** Colour is confirmation only — each tone always ships with its own words. */
const TONE_CLASS: Record<FreshnessTone, string> = {
  ok: 'text-secondary-300',
  ageing: 'text-warning-200',
  unknown: 'text-secondary-300',
  problem: 'text-orange-200',
}

const TONE_ICON: Record<FreshnessTone, typeof ClockIcon> = {
  ok: CheckCircleIcon,
  ageing: ClockIcon,
  unknown: QuestionMarkCircleIcon,
  problem: NoSymbolIcon,
}

/** One clock, one line. `min-w-0` so a long provider sentence wraps instead of widening the page. */
const StatementLine: React.FC<{ tone: FreshnessTone; testId: string; children: React.ReactNode }> = ({
  tone, testId, children,
}) => {
  const Icon = TONE_ICON[tone]
  return (
    <p className={clsx('flex items-start gap-2 text-xs', TONE_CLASS[tone])}>
      <Icon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
      <span className="min-w-0 break-words" data-testid={testId}>{children}</span>
    </p>
  )
}

export interface DataFreshnessProps {
  /** The backend's provider-status payload. Null means we could not reach it — which is said. */
  status: ProviderStatus | null
  /**
   * `line` is the quiet form for a list: the statements and a disclosure.
   * `panel` adds a heading, for a page where the state of the data is worth its own block.
   */
  variant?: 'line' | 'panel'
  className?: string
}

const DataFreshness: React.FC<DataFreshnessProps> = ({ status, variant = 'line', className }) => {
  const t = useT()
  // One clock for the whole render, so the summaries and the rows cannot disagree by a second.
  const now = Date.now()
  const report = freshnessReport(status, now)
  const tasks = status?.scheduler ? describeTasks(status.scheduler, now) : []
  const retrieval = retrievalFact(status, now)

  /*
   * The budget and cooling-down fields say something the scheduler does not: a backend can have a
   * spent forecast allowance with no scheduler at all, and then the scheduler-derived rows are
   * silent about a pause that is real. This fills exactly that hole — but in TWO halves, decided
   * separately, because folding them together cost the reader the half that matters.
   *
   * THE MESSAGE still defers to the scheduler. When the scheduler has reported a pause or a
   * failure for forecasts, its wording is the more specific of the two and wins outright.
   *
   * THE RESUME TIME does not, and suppressing it with the message was the bug. The scheduler's
   * note only carried a resume when the task was PAUSED, and a task can be failing and paused at
   * once: on this installation the forecasts task failed on the provider's quota refusal, the
   * failure won the note, and the resume went with it. The reader was told the forecasts are
   * stuck and never told when they come back — and it was not behind the disclosure either,
   * because the detail rows drop whatever the summary is supposed to have said.
   *
   * What is borrowed is only the ALLOWANCE RESET, and only when it is not already being printed.
   * Both paths build that sentence from `allowanceResetNote` and this render's single clock, so
   * it is the same string and can be recognised rather than pattern-matched. The next attempt
   * time is left to the scheduler, which is where it is measured and which now always states it.
   */
  const availability = forecastAvailability(status, now)
  const allowanceReset = allowanceResetNote(now)
  const borrowedResume = availability?.resume?.includes(allowanceReset)
    && !(report.note ?? '').includes(allowanceReset)
    ? allowanceReset
    : null
  /*
   * AND NOW THE BORROW IS A FALLBACK RATHER THAN A FIXTURE OF THE NOTE.
   *
   * The scheduler's note states the next attempt in every case that reaches here, so the reader
   * already learns when forecasts come back without being told how our allowance's calendar
   * works. That calendar is mechanics, and mechanics moved into the disclosure. But the
   * guarantee this borrow exists for has to survive the move: when nothing else in the note
   * answers "when does it come back", the reset sentence is still said out loud, because a pause
   * with no end stated is the failure this whole block was built to stop.
   */
  const resumeStated = Boolean(report.resume)
  const availabilityNote = availability
    ? (report.forecasts?.note
      ? (resumeStated ? null : borrowedResume)
      : [availability.message, availability.resume].filter(Boolean).join(' '))
    : null
  // Said quietly, where the rest of the arithmetic lives, whenever it is not said out loud.
  const mechanics = [
    ...(report.mechanics ?? []),
    ...(borrowedResume && availabilityNote !== borrowedResume ? [borrowedResume] : []),
  ].filter((line, index, all) => all.indexOf(line) === index)

  /**
   * A pause the scheduler cannot see still gets a line of its own, rather than no line at all.
   * With no task behind it there is no age to state, and none is invented: the line says only
   * that the age is not reported, and the note below it says what the budget does know.
   */
  const forecastLine = report.forecasts
    ?? (availability
      ? { text: t('freshness.forecasts.ageNotReported'), tone: 'unknown' as FreshnessTone }
      : null)

  const tone = availabilityNote ? worseTone(report.tone, 'ageing') : report.tone
  /*
   * ONE LINE PER TASK IN TROUBLE, not one paragraph for all of them.
   *
   * With two tasks stopped the note carries two failures, two next-attempt times and two backoff
   * windows. Each sentence now names its own task, but eight facts run together in a single
   * paragraph are still work to read, and a reader scanning for "which refresh is stuck" should
   * not have to do that work. `report.notes` is the same text already grouped per task; the
   * testid stays on the one container so the statements are still asserted as a whole.
   */
  const noteLines = [...report.notes, availabilityNote].filter((line): line is string => Boolean(line))

  return (
    <section
      className={clsx('rounded-lg border border-dark-700 bg-dark-800/40', className)}
      data-testid="data-freshness"
      data-tone={tone}
      aria-label={t('freshness.panel.label')}
    >
      <div className="px-3 py-2">
        {variant === 'panel' && (
          <h2 className="mb-1 text-sm font-semibold text-white">{t('freshness.panel.heading')}</h2>
        )}
        <StatementLine tone={report.fixtures.tone} testId="freshness-summary">
          {report.fixtures.text}
        </StatementLine>
        {/*
          The forecast clock, always on its own row when there is one to read. It is not folded
          into the line above even when the two happen to agree today: a reader who cannot see
          which half a timestamp belongs to cannot tell tomorrow, when they disagree.
        */}
        {forecastLine && (
          <StatementLine tone={forecastLine.tone} testId="freshness-forecasts">
            {forecastLine.text}
          </StatementLine>
        )}
        {/*
          The resume time, and the "we do not know" statements, stay OUT of the disclosure: a
          reader who never opens it must still learn that a refresh is paused and when it returns.
        */}
        {noteLines.length > 0 && (
          <div className="mt-1 space-y-1 pl-5" data-testid="freshness-note">
            {noteLines.map((line, index) => (
              <p key={index} className="text-xs break-words text-secondary-300">{line}</p>
            ))}
          </div>
        )}
      </div>

      {(tasks.length > 0 || retrieval) && (
        <details className="group border-t border-dark-700" data-testid="freshness-detail">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-xs text-secondary-400 hover:text-white">
            <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
            {t('freshness.panel.disclosure')}
          </summary>
          <div className="space-y-2 border-t border-dark-700 px-3 py-2 text-xs">
            {/*
              HOW THE RESUME TIME WAS WORKED OUT, and the provider's own words, both live here.

              The note above says what a reader can act on: which refresh is stuck and when it
              next tries. The arithmetic behind that — which calendar our allowance resets on, how
              long the backoff window is — and the upstream message verbatim are kept here rather
              than deleted. A reviewer counted those sentences among the technical explanations
              filling a phone screen before any football; nobody diagnosing a stuck refresh can
              afford to lose them.
            */}
            {mechanics.length > 0 && (
              <ul className="space-y-0.5 text-secondary-500" data-testid="freshness-mechanics">
                {mechanics.map(line => (
                  <li key={line} className="break-words">{line}</li>
                ))}
              </ul>
            )}
            <dl className="space-y-2">
              {tasks.map(task => (
                <div key={task.name} data-testid="freshness-task" data-task={task.name} data-tone={task.tone}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                    <dt className="text-secondary-300">{task.label}</dt>
                    <dd className={clsx('text-right', TONE_CLASS[task.tone])} title={task.exact ?? undefined}>
                      {task.text}
                    </dd>
                  </div>
                  {/*
                    Anything the summary lines above already said is dropped here rather than
                    printed twice. The same sentence appearing twice within one small block reads
                    as two separate problems, which is how a single paused task starts to look
                    like a broken site.
                  */}
                  {(() => {
                    /*
                     * WHAT THE SUMMARY ABOVE ALREADY SAID, matched by identity rather than by
                     * prefix.
                     *
                     * This used to be a list of English prefixes — 'Paused:', 'Last attempt
                     * failed:' — which is a language-shaped test: in French the same three lines
                     * begin "En pause :" and "Dernière tentative en échec :", so every prefix
                     * missed and the reader met each sentence twice, once in the note and once
                     * a few pixels below. `describeTask` builds those lines from the same three
                     * catalogue entries the check below rebuilds, so comparing the finished
                     * strings works in any language and cannot drift from the wording.
                     */
                    const alreadySaid = [
                      t('freshness.task.pausedDetail', { reason: task.pauseReason }),
                      t('freshness.task.failedDetail', { reason: task.failureReason }),
                      t('freshness.task.behindDetail'),
                    ].map(line => line.replace(/[.\s]+$/, ''))
                    // The upstream message word for word. The note above carries a readable
                    // summary of it instead, without the vendor's name, plan tier or upgrade link.
                    const verbatim = [task.failureReason, task.pauseReason]
                      .filter((line): line is string => Boolean(line))
                    const lines = report.noteTasks.includes(task.name)
                      ? task.detail.filter(line =>
                        line !== task.resume
                        && !alreadySaid.some(said => line.replace(/[.\s]+$/, '') === said))
                      : task.detail
                    const all = [
                      ...lines,
                      ...verbatim.map(line => t('freshness.task.providerSaid', { reason: line })),
                    ]
                    return all.length > 0
                      ? <p className="mt-0.5 break-words text-secondary-500">{all.join(' ')}</p>
                      : null
                  })()}
                </div>
              ))}
            </dl>

            {retrieval && (
              <div className="border-t border-dark-700 pt-2 text-secondary-500" data-testid="freshness-retrieval">
                {/*
                  A different fact from every row above, and labelled as one: a scheduled pass can
                  succeed without asking the provider for anything.
                */}
                <p>
                  {t('freshness.panel.lastAnswerFrom', { provider: fixtureProviderLabel(retrieval.provider) })}{' '}
                  <span className={retrieval.relative ? 'text-secondary-400' : undefined} title={retrieval.exact ?? undefined}>
                    {retrieval.relative ?? t('freshness.panel.notAnswered')}
                  </span>
                </p>
                {retrieval.coolingDown && (
                  <p className="mt-0.5 break-words">
                    {/* The provider's own words in `{reason}`; only the frame is translated. */}
                    {t('freshness.panel.pausedAfterFailure', { reason: retrieval.coolingDown })}
                  </p>
                )}
              </div>
            )}

            <p className="border-t border-dark-700 pt-2 text-secondary-500">
              {/*
                Said plainly, because it is the distinction most easily lost: none of the times
                above is when a provider's model ran. That is a property of each forecast and is
                published beside it on the match page — often as "not published by the provider",
                which is the honest answer when the provider gave none.
              */}
              {t('freshness.panel.ourTimes')}
            </p>
          </div>
        </details>
      )}
    </section>
  )
}

export default DataFreshness
