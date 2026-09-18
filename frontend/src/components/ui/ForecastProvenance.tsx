import React from 'react'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { MatchPredictions } from '@/types'
import { providerLabel } from '@/utils/predictionLabels'

/**
 * Consistency problems the backend found in the provider payload, shown verbatim.
 *
 * A forecast that failed a sum check is still shown — it is what the provider published — but it
 * must not be presented as authoritative, and the numbers are never "corrected" to make it pass.
 */
export const ForecastAnomalies: React.FC<{ anomalies?: string[] | null; className?: string }> = ({
  anomalies,
  className = '',
}) => {
  if (!anomalies || anomalies.length === 0) return null
  return (
    <div
      className={`flex items-start space-x-2 rounded-lg border border-orange-700/60 bg-orange-900/20 px-3 py-2 text-sm text-orange-200 ${className}`}
      role="status"
      data-testid="forecast-anomalies"
    >
      <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" />
      <div>
        <p className="font-medium">
          This forecast did not pass our consistency checks. It is shown exactly as the provider published it.
        </p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-orange-300/90">
          {anomalies.map(note => <li key={note}>{note}</li>)}
        </ul>
      </div>
    </div>
  )
}

const stamp = (iso: string | null | undefined): string | null => {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

/**
 * The three forecast times, kept apart on purpose.
 *
 * Only `modelRunAt` is when the provider says its model ran. `providerUpdatedAt` is when the
 * provider last touched the record and `fetchedAt` is when we retrieved it — presenting either as
 * the generation time would be a claim the provider never made, so when no model-run time was
 * published the UI says the generation time is unknown rather than quietly showing the fetch time.
 */
const ForecastProvenance: React.FC<{ prediction: MatchPredictions; className?: string }> = ({
  prediction,
  className = '',
}) => {
  const modelRun = prediction.generationTimeKnown ? stamp(prediction.modelRunAt) : null
  const providerUpdated = stamp(prediction.providerUpdatedAt)
  const fetched = stamp(prediction.fetchedAt)

  return (
    <dl className={`space-y-1 text-xs text-secondary-500 ${className}`} data-testid="forecast-provenance">
      <div className="flex justify-between gap-4">
        <dt>Source</dt>
        <dd className="text-secondary-400 text-right">{providerLabel(prediction.providerName || prediction.source_type)}</dd>
      </div>
      <div className="flex justify-between gap-4">
        <dt>Provider&rsquo;s model run</dt>
        <dd className="text-secondary-400 text-right">{modelRun ?? 'generation time unknown (not published by the provider)'}</dd>
      </div>
      <div className="flex justify-between gap-4">
        <dt>Provider last updated</dt>
        <dd className="text-secondary-400 text-right">{providerUpdated ?? 'not reported'}</dd>
      </div>
      <div className="flex justify-between gap-4">
        <dt>Retrieved by this site</dt>
        <dd className="text-secondary-400 text-right">{fetched ?? 'not recorded'}</dd>
      </div>
      {prediction.matchConfidence && (
        <div className="flex justify-between gap-4">
          <dt>Fixture match</dt>
          <dd className="text-secondary-400 text-right">{prediction.matchConfidence}</dd>
        </div>
      )}
    </dl>
  )
}

export default ForecastProvenance
