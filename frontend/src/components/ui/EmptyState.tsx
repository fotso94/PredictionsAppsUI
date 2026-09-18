import React from 'react'
import clsx from 'clsx'
import { ExclamationTriangleIcon, InboxIcon, SignalSlashIcon } from '@heroicons/react/24/outline'

/**
 * The state a list is in when it has nothing to show.
 *
 * `tone` exists because three situations look identical on screen and are not the same fact:
 *
 *  - `empty`   we asked, and there really is nothing. "No matches on this date."
 *  - `failed`  we asked and could not find out. This must NEVER be dressed as `empty`: telling a
 *              reader "no matches today" after a request failed is a statement about the world made
 *              from a network error. (search.service.ts carries the same warning in prose; it had
 *              to have this exact bug fixed once.)
 *  - `blocked` there is nothing here because of a limit or a paused refresh, not because the world
 *              is empty. The reason belongs in `description`, in the backend's own words.
 *
 * Presentational only: it fetches nothing and decides nothing. The caller, which knows whether the
 * request succeeded, picks the tone.
 */

export type EmptyStateTone = 'empty' | 'failed' | 'blocked'

export interface EmptyStateProps {
  /** One short sentence. Say what is true, not what the reader should do. */
  title: string
  /** The explanation. Pass the server's own wording verbatim where you have it. */
  description?: React.ReactNode
  tone?: EmptyStateTone
  /** Overrides the tone's default icon. */
  icon?: React.ReactNode
  /** A retry button, a link to another date — whatever the caller can offer. */
  action?: React.ReactNode
  /** `inline` drops the border and padding, for use inside a card that already has them. */
  variant?: 'card' | 'inline'
  className?: string
  'data-testid'?: string
}

const TONE_ICON: Record<EmptyStateTone, typeof InboxIcon> = {
  empty: InboxIcon,
  failed: SignalSlashIcon,
  blocked: ExclamationTriangleIcon,
}

/**
 * Colour confirms the tone; the words carry it. Measured on dark-900 #0f172a:
 * secondary-300 #cbd5e1 12.02:1, orange-200 #fed7aa 13.19:1, warning-200 #fde68a 14.33:1.
 */
const TONE_ICON_CLASS: Record<EmptyStateTone, string> = {
  empty: 'text-secondary-400',
  failed: 'text-orange-200',
  blocked: 'text-warning-200',
}

/** Read out before the title, so the tone is not conveyed by colour and icon alone. */
const TONE_PREFIX: Record<EmptyStateTone, string> = {
  empty: '',
  failed: 'Could not load. ',
  blocked: 'Unavailable right now. ',
}

const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  tone = 'empty',
  icon,
  action,
  variant = 'card',
  className,
  'data-testid': testId = 'empty-state',
}) => {
  const Icon = TONE_ICON[tone]

  return (
    <div
      className={clsx(
        'text-center',
        variant === 'card' && 'rounded-xl border border-dashed border-dark-700 bg-dark-900/50 px-4 py-8',
        variant === 'inline' && 'px-2 py-4',
        className,
      )}
      // A failure is announced; an ordinary empty list is not worth interrupting anyone for.
      role={tone === 'failed' ? 'alert' : 'status'}
      data-tone={tone}
      data-testid={testId}
    >
      <div className="flex justify-center">
        {icon ?? <Icon className={clsx('h-8 w-8', TONE_ICON_CLASS[tone])} aria-hidden="true" />}
      </div>
      <p className="mt-3 text-sm font-medium text-white">
        <span className="sr-only">{TONE_PREFIX[tone]}</span>
        {title}
      </p>
      {description && <div className="mt-1 text-sm text-secondary-300">{description}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

export default EmptyState
