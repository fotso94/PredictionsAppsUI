import React from 'react'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { ForecastAnomaly, MatchPredictions } from '@/types'
import { providerLabel } from '@/utils/predictionLabels'
import { backendInstant, formatDateTime, zoneLabel } from '@/i18n'
import { useT } from '@/i18n/react'

/**
 * What the backend observed about the provider payload, shown verbatim.
 *
 * Two different things, kept apart so a sound forecast is not made to look suspect:
 *  - a `warning` means the numbers themselves do not hold together (outcomes that do not sum to
 *    100%, a market published as all zeroes). The forecast is still shown, because it is what the
 *    provider published, but it must not read as authoritative and is never "corrected" to pass.
 *  - a `note` is bookkeeping, such as a 0% scoreline left out of the list. It says nothing about
 *    whether the forecast is trustworthy, so it is a quiet footnote rather than a caution.
 */
export const ForecastAnomalies: React.FC<{ anomalies?: ForecastAnomaly[] | null; className?: string }> = ({
  anomalies,
  className = '',
}) => {
  const t = useT()
  if (!anomalies || anomalies.length === 0) return null
  const warnings = anomalies.filter(a => a.severity === 'warning')
  const notes = anomalies.filter(a => a.severity !== 'warning')

  return (
    <div className={className}>
      {warnings.length > 0 && (
        <div
          className="flex items-start space-x-2 rounded-lg border border-orange-700/60 bg-orange-900/20 px-3 py-2 text-sm text-orange-200"
          role="status"
          data-testid="forecast-anomalies"
        >
          <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" />
          <div>
            <p className="font-medium">{t('reader.anomalies.warning')}</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-orange-300/90">
              {warnings.map(a => <li key={a.code + a.message}>{a.message}</li>)}
            </ul>
          </div>
        </div>
      )}
      {notes.length > 0 && (
        <ul
          className={`space-y-0.5 text-xs text-secondary-500 ${warnings.length > 0 ? 'mt-2' : ''}`}
          data-testid="forecast-notes"
        >
          {notes.map(a => <li key={a.code + a.message}>{a.message}</li>)}
        </ul>
      )}
    </div>
  )
}

/** A timestamp the server sent, and whether the payload said which zone it meant. */
interface Stamp { text: string | null; anchored: boolean }

/**
 * One server timestamp, read as UTC where the payload named no zone and shown in the reader's own.
 *
 * `new Date(iso).toLocaleString()` — what this was — got both halves wrong at once: an
 * offset-less string is parsed in the DEVICE's zone, and then printed in the DEVICE's zone and
 * the DEVICE's locale, so a reader in Douala with a laptop on New York time saw a retrieval time
 * five hours out, written the American way, in English, on a French page.
 *
 * An unparseable value is returned as it arrived rather than as "Invalid Date": showing the raw
 * string tells whoever is looking at it what the server actually sent.
 */
const stamp = (iso: string | null | undefined): Stamp => {
  if (!iso) return { text: null, anchored: true }
  const read = backendInstant(iso)
  if (!read.at) return { text: typeof iso === 'string' ? iso : null, anchored: true }
  return { text: formatDateTime(read.at), anchored: read.anchored }
}

/**
 * The three forecast times, kept apart on purpose.
 *
 * Only `modelRunAt` is when the provider says its model ran. `providerUpdatedAt` is when the
 * provider last touched the record and `fetchedAt` is when we retrieved it — presenting either as
 * the generation time would be a claim the provider never made, so when no model-run time was
 * published the UI says the generation time is unknown rather than quietly showing the fetch time.
 *
 * ── WHY ALL THREE ARE IN THE READER'S ZONE, INCLUDING THE RETRIEVAL TIME ────────────────────
 *
 * Each of the three is an INSTANT — a moment something happened — and a reader judges an instant
 * against their own clock: "was this produced before or after I looked at it", "is this from this
 * morning". That is the reader's zone, not the server's and not the device's.
 *
 * `fetchedAt` is the one worth arguing about, and it was argued about rather than converted by
 * reflex. Our request allowance with a provider is counted per UTC DAY, so there is a real sense
 * in which "when did we retrieve this" is a UTC-shaped question. But that fact is about the
 * BUDGET, not about this forecast, and it is already stated where it belongs and in UTC — see
 * `freshness.allowanceReset` ("counted per UTC day, so it resets at 00:00 UTC") in the freshness
 * panel. Printing one timestamp here in UTC and the two beside it in the reader's zone, with
 * nothing on the row to say which was which, would make the column unreadable to buy a
 * connection the reader cannot see. So the zone is named once, under the list, and all three are
 * in it.
 */
const ForecastProvenance: React.FC<{ prediction: MatchPredictions; className?: string }> = ({
  prediction,
  className = '',
}) => {
  const t = useT()
  const modelRun = prediction.generationTimeKnown ? stamp(prediction.modelRunAt) : { text: null, anchored: true }
  const providerUpdated = stamp(prediction.providerUpdatedAt)
  const fetched = stamp(prediction.fetchedAt)
  const shown = [modelRun, providerUpdated, fetched].filter(entry => entry.text !== null)
  /**
   * True when one of the timestamps on show arrived with no zone on it. This backend serialises
   * all three with an explicit Z (`iso_utc`, backend/app/schemas/matches.py:22), so it should
   * stay false — but the caveat is driven by what the PAYLOAD said rather than by what the
   * backend is believed to do, which is the difference between reporting a claim and hiding one.
   */
  const anyUnzoned = shown.some(entry => !entry.anchored)

  return (
    <div className={className}>
      <dl className="space-y-1 text-xs text-secondary-500" data-testid="forecast-provenance">
        <div className="flex justify-between gap-4">
          {/*
            "Source" is the French word too, spelled identically. A catalogue pair whose two
            sides are the same string reads as a translation nobody did, and localisation.spec.ts
            fails on that — so this one is stated here rather than added to the list of shared
            words in a spec another package owns. See STANDINGS_COLUMNS in LeagueDetailPage.tsx,
            which carries the same note for the two standings labels in the same position.
          */}
          <dt>Source</dt>
          <dd className="text-secondary-400 text-right">{providerLabel(prediction.providerName || prediction.source_type)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>{t('reader.provenance.modelRun')}</dt>
          <dd className="text-secondary-400 text-right">{modelRun.text ?? t('reader.provenance.generationUnknown')}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>{t('reader.provenance.providerUpdated')}</dt>
          <dd className="text-secondary-400 text-right">{providerUpdated.text ?? t('reader.provenance.notReported')}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>{t('reader.provenance.retrieved')}</dt>
          <dd className="text-secondary-400 text-right">{fetched.text ?? t('reader.provenance.notRecorded')}</dd>
        </div>
        {prediction.matchConfidence && (
          <div className="flex justify-between gap-4">
            {/* The provider's own word for how confidently it linked its record to this fixture. */}
            <dt>{t('reader.provenance.fixtureMatch')}</dt>
            <dd className="text-secondary-400 text-right">{prediction.matchConfidence}</dd>
          </div>
        )}
      </dl>
      {/* Which zone these readings are in. Said once, rather than three times on three rows. */}
      {shown.length > 0 && (
        <p className="mt-1 text-[11px] leading-4 text-secondary-600" data-testid="provenance-zone">
          {t('matchday.timesIn', { zone: zoneLabel() })}
          {anyUnzoned ? ` ${t('reader.provenance.unzoned')}` : ''}
        </p>
      )}
    </div>
  )
}

export default ForecastProvenance
