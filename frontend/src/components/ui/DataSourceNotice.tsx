import React from 'react'
import { ExclamationTriangleIcon, InformationCircleIcon } from '@heroicons/react/24/outline'
import { DataSourceMeta } from '@/services/match-data-source'
// One provider vocabulary for the whole interface: the same feed must not be called two different
// things on one page, so this notice and the freshness panel read from the same map.
import { fixtureProviderLabel as providerName } from './freshness'

interface DataSourceNoticeProps {
  meta: DataSourceMeta | null
  className?: string
}

/**
 * Tells the user where the fixtures came from and whether they are stale.
 * Silent when the data is fresh and came from the primary provider or its cache.
 */
const DataSourceNotice: React.FC<DataSourceNoticeProps> = ({ meta, className = '' }) => {
  if (!meta) return null
  const fetched = meta.fetchedAt ? new Date(meta.fetchedAt).toLocaleString() : null

  if (meta.stale || meta.source === 'stale-cache') {
    return (
      <div className={`flex items-start space-x-2 rounded-lg border border-yellow-700/60 bg-yellow-900/20 px-4 py-3 text-sm text-yellow-200 ${className}`} role="status" data-testid="data-source-notice">
        <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" />
        <div>
          <p className="font-medium">Showing the last saved fixtures{fetched ? ` (from ${fetched})` : ''}.</p>
          <p className="text-yellow-300/80">The data provider could not be reached; kick-off times and scores may be out of date.</p>
          {meta.errors.length > 0 && <p className="text-xs text-yellow-300/60 mt-1">{meta.errors[0]}</p>}
        </div>
      </div>
    )
  }

  if (meta.source === 'database' && meta.errors.length > 0) {
    return (
      <div className={`flex items-start space-x-2 rounded-lg border border-red-700/60 bg-red-900/20 px-4 py-3 text-sm text-red-200 ${className}`} role="alert" data-testid="data-source-notice">
        <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" />
        <div>
          <p className="font-medium">Live fixture data is unavailable right now.</p>
          <p className="text-red-300/80">{meta.errors[0]}</p>
        </div>
      </div>
    )
  }

  if (meta.provider === 'sample' || meta.provider === 'api_football' || meta.provider === 'thesportsdb') {
    return (
      <div className={`flex items-start space-x-2 rounded-lg border border-dark-700 bg-dark-800 px-4 py-3 text-sm text-secondary-300 ${className}`} role="status" data-testid="data-source-notice">
        <InformationCircleIcon className="h-5 w-5 flex-shrink-0" />
        <p>Fixtures provided by {providerName(meta.provider)}.</p>
      </div>
    )
  }

  return null
}

export default DataSourceNotice
