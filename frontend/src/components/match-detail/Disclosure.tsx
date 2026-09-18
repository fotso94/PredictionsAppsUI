import React from 'react'
import clsx from 'clsx'
import { ChevronRightIcon } from '@heroicons/react/24/outline'

/**
 * Detail a reader can open, not detail hidden from them.
 *
 * Used for operational wording (quota, cooling-down, provider bookkeeping) that is true but says
 * nothing about whether the numbers on screen are right. Anything that DOES bear on the numbers —
 * a market that is missing, a forecast that is out of date, a payload whose values do not hold
 * together — stays visible above, never behind one of these.
 *
 * A native <details> so it works without JavaScript, is keyboard-operable and is announced as an
 * expandable region by a screen reader.
 */
const Disclosure: React.FC<{
  summary: string
  children: React.ReactNode
  className?: string
  testId?: string
}> = ({ summary, children, className, testId }) => (
  <details className={clsx('group rounded-lg border border-dark-700 bg-dark-800/50', className)} data-testid={testId}>
    <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-xs text-secondary-300 hover:text-white">
      <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
      {summary}
    </summary>
    <div className="space-y-1.5 border-t border-dark-700 px-3 py-2 text-xs text-secondary-400">
      {children}
    </div>
  </details>
)

export default Disclosure
