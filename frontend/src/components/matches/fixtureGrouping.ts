/**
 * Turning a day's fixtures into the shape the list renders: competitions, each in kickoff order.
 *
 * Pure arithmetic over the payload. Nothing here reads a probability, and nothing here invents a
 * count for a competition that is not in the response — a competition with no fixtures on the
 * chosen day simply is not in the list, which is a different statement from "0 matches".
 */

import type { Match } from '@/types'
import { FixtureKind, competitionKind, fixtureKind } from '@/utils/squads'

export interface CompetitionOption {
  id: string
  name: string
  country: string
  logo: string
  /** Club or national-team football, or `unknown` where the payload does not classify it. */
  kind: FixtureKind
  /** Fixtures this competition contributes to the day, before any filter is applied. */
  count: number
}

/**
 * How much of each kind of football a day holds, counted from the fixtures themselves.
 *
 * WHAT IT IS FOR. A control offering "Club" and "National teams" on a day that holds only one of
 * them can do nothing but empty the list, which is the same reason the competition chip row is
 * withheld for a day with a single competition. So the workspace asks this first and offers the
 * choice only where there is one — and the counts, not a boolean, because the answer to "is this
 * an international break?" is the club count being zero rather than the national count being
 * positive.
 *
 * `unknown` is counted separately and belongs to neither: a fixture whose competition carries no
 * classification is not evidence of club football and not evidence of national-team football.
 */
export interface DayKindCounts {
  club: number
  national: number
  unknown: number
  /** Both kinds are present, so a choice between them narrows the list rather than emptying it. */
  both: boolean
}

export function kindCounts(matches: Match[]): DayKindCounts {
  const counts = { club: 0, national: 0, unknown: 0 }
  for (const match of matches) counts[fixtureKind(match)] += 1
  return { ...counts, both: counts.club > 0 && counts.national > 0 }
}

export interface CompetitionGroup extends CompetitionOption {
  matches: Match[]
}

/** Kickoff order. The ISO instant when we have one, the displayed local time as the tie-break. */
export function byKickoff(a: Match, b: Match): number {
  const left = a.kickoffUtc ?? ''
  const right = b.kickoffUtc ?? ''
  if (left && right && left !== right) return left < right ? -1 : 1
  if (a.time !== b.time) return a.time < b.time ? -1 : 1
  return a.homeTeam.name.localeCompare(b.homeTeam.name)
}

/**
 * Every competition present in `matches`, with how many fixtures each brings.
 *
 * Ordered by the day's own shape — most fixtures first, then alphabetically — so the chip row puts
 * the competitions the reader is most likely to want within reach rather than in payload order.
 */
export function competitionOptions(matches: Match[]): CompetitionOption[] {
  const byId = new Map<string, CompetitionOption>()
  for (const match of matches) {
    const { id, name, country, logo } = match.league
    const existing = byId.get(id)
    if (existing) existing.count += 1
    else byId.set(id, { id, name, country, logo, kind: competitionKind(match.league), count: 1 })
  }
  return [...byId.values()].sort((a, b) => (b.count - a.count) || a.name.localeCompare(b.name))
}

/**
 * The same fixtures grouped for rendering, each group in kickoff order and the groups themselves
 * ordered by their earliest kickoff — so a list read top to bottom is read in time order, which is
 * how somebody deciding what to watch tonight reads it.
 */
export function groupByCompetition(matches: Match[]): CompetitionGroup[] {
  const byId = new Map<string, CompetitionGroup>()
  for (const match of matches) {
    const { id, name, country, logo } = match.league
    const existing = byId.get(id)
    if (existing) { existing.matches.push(match); existing.count += 1 }
    else byId.set(id, { id, name, country, logo, kind: competitionKind(match.league), count: 1, matches: [match] })
  }

  const groups = [...byId.values()]
  for (const group of groups) group.matches.sort(byKickoff)
  return groups.sort((a, b) => {
    const first = byKickoff(a.matches[0], b.matches[0])
    return first !== 0 ? first : a.name.localeCompare(b.name)
  })
}
