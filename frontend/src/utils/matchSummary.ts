/**
 * The compact fixture the slip endpoints take and return, built from the page's `Match`.
 *
 * Only what a slip needs to show a leg: the two names, the competition, the kickoff. Nothing
 * about a forecast — that is the selection's business, not the fixture's.
 */

import type { Match } from '@/types'
import type { ApiMatchSummary } from '@/types/markets'

export function summaryOf(match: Match): ApiMatchSummary {
  return {
    id: match.id,
    home: { id: match.homeTeam.id, name: match.homeTeam.name, short_name: match.homeTeam.shortName ?? null },
    away: { id: match.awayTeam.id, name: match.awayTeam.name, short_name: match.awayTeam.shortName ?? null },
    competition: match.league ? { id: match.league.id, name: match.league.name } : null,
    kickoff_utc: match.kickoffUtc ?? null,
    status: match.status,
  }
}
