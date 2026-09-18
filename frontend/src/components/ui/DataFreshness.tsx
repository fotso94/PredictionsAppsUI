import React from 'react'
import clsx from 'clsx'
import { CheckCircleIcon, ChevronRightIcon, ClockIcon, NoSymbolIcon, QuestionMarkCircleIcon } from '@heroicons/react/24/outline'
import type { ProviderStatus } from '@/services/match-data-source'
import type { FreshnessTone } from '@/utils/brief'
import { describeTasks, freshnessSummary, fixtureProviderLabel, retrievalFact } from './freshness'

/**
 * "Last updated", where the reader actually needs it.
 *
 * Every page in this application reads stored data. That is deliberate — it is fast, it spends no
 * request allowance and it never invents a number — but it means the one question a reader cannot
 * otherwise answer is how old what they are looking at is. This answers it, in one quiet line,
 * with the detail one tap away.
 *
 * WHAT IS IN THE LINE AND WHAT IS BEHIND THE DISCLOSURE. The line carries the facts that change
 * how the page should be read: that this is stored data, when it was last refreshed, and — when
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

export interface DataFreshnessProps {
  /** The backend's provider-status payload. Null means we could not reach it — which is said. */
  status: ProviderStatus | null
  /**
   * `line` is the quiet form for a list: one sentence and a disclosure.
   * `panel` adds a heading, for a page where the state of the data is worth its own block.
   */
  variant?: 'line' | 'panel'
  className?: string
}

const DataFreshness: React.FC<DataFreshnessProps> = ({ status, variant = 'line', className }) => {
  // One clock for the whole render, so the summary and the rows cannot disagree by a second.
  const now = Date.now()
  const summary = freshnessSummary(status, now)
  const tasks = status?.scheduler ? describeTasks(status.scheduler, now) : []
  const retrieval = retrievalFact(status, now)
  const Icon = TONE_ICON[summary.tone]

  return (
    <section
      className={clsx('rounded-lg border border-dark-700 bg-dark-800/40', className)}
      data-testid="data-freshness"
      data-tone={summary.tone}
      aria-label="How current this page is"
    >
      <div className="px-3 py-2">
        {variant === 'panel' && (
          <h2 className="mb-1 text-sm font-semibold text-white">How current this is</h2>
        )}
        <p className={clsx('flex items-start gap-2 text-xs', TONE_CLASS[summary.tone])}>
          <Icon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
          <span data-testid="freshness-summary">{summary.text}</span>
        </p>
        {/*
          The resume time, and the "we do not know" statements, stay OUT of the disclosure: a
          reader who never opens it must still learn that a refresh is paused and when it returns.
        */}
        {summary.note && (
          <p className="mt-1 pl-5 text-xs text-secondary-300" data-testid="freshness-note">{summary.note}</p>
        )}
      </div>

      {(tasks.length > 0 || retrieval) && (
        <details className="group border-t border-dark-700" data-testid="freshness-detail">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-xs text-secondary-400 hover:text-white">
            <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
            What was refreshed, and when
          </summary>
          <div className="space-y-2 border-t border-dark-700 px-3 py-2 text-xs">
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
                    Anything the summary line above already said is dropped here rather than
                    printed twice. The same sentence appearing twice within one small block reads
                    as two separate problems, which is how a single paused task starts to look
                    like a broken site.
                  */}
                  {(() => {
                    const alreadySaid = ['Paused:', 'Last attempt failed:', 'This task is more than']
                    const lines = task.name === summary.noteTask
                      ? task.detail.filter(line =>
                        line !== task.resume && !alreadySaid.some(prefix => line.startsWith(prefix)))
                      : task.detail
                    return lines.length > 0 ? <p className="mt-0.5 text-secondary-500">{lines.join(' ')}</p> : null
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
                  Last answer from {fixtureProviderLabel(retrieval.provider)}:{' '}
                  <span className={retrieval.relative ? 'text-secondary-400' : undefined} title={retrieval.exact ?? undefined}>
                    {retrieval.relative ?? 'it has not answered successfully yet'}
                  </span>
                </p>
                {retrieval.coolingDown && <p className="mt-0.5">Paused after a failure: {retrieval.coolingDown}</p>}
              </div>
            )}

            <p className="border-t border-dark-700 pt-2 text-secondary-500">
              {/*
                Said plainly, because it is the distinction most easily lost: none of the times
                above is when a provider's model ran. That is a property of each forecast and is
                published beside it on the match page — often as "not published by the provider",
                which is the honest answer when the provider gave none.
              */}
              These are our own retrieval and refresh times. When a provider&rsquo;s model actually
              ran is a different fact, published with each forecast on its match page.
            </p>
          </div>
        </details>
      )}
    </section>
  )
}

export default DataFreshness
