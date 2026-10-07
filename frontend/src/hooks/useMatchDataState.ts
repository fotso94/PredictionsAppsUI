/**
 * Whether fixture and result updates are arriving, for a component that does not already hold the
 * provider-status payload.
 *
 * `enabled` lets a component ask only when the answer could change what it shows: the slip asks
 * only once one of its selections has kicked off and is waiting for a result, so a reader building
 * a slip for next weekend costs no request at all. The fetch is the shared sixty-second memo in
 * src/services/match-data-state.service.ts, so several components asking at once cost one request.
 *
 * Null until it has answered, when it could not answer, and on a backend older than the block:
 * every caller reads null as "say nothing new".
 */

import { useEffect, useState } from 'react'
import type { MatchDataState } from '@/services/match-data-source'
import { getMatchDataState } from '@/services/match-data-state.service'

export function useMatchDataState(enabled = true): MatchDataState | null {
  const [state, setState] = useState<MatchDataState | null>(null)
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    getMatchDataState().then(result => { if (!cancelled) setState(result) })
    return () => { cancelled = true }
  }, [enabled])
  return enabled ? state : null
}

export default useMatchDataState
