/**
 * Turning a day's fixtures into the shape the list renders: competitions, each in kickoff order.
 *
 * Pure arithmetic over the payload. Nothing here reads a probability, and nothing here invents a
 * count for a competition that is not in the response — a competition with no fixtures on the
 * chosen day simply is not in the list, which is a different statement from "0 matches".
 */

import type { Match } from '@/types'

export interface CompetitionOption {
  id: string
  name: string
  country: string
  logo: string
  /** Fixtures this competition contributes to the day, before any filter is applied. */
  count: number
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
    else byId.set(id, { id, name, country, logo, count: 1 })
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
    else byId.set(id, { id, name, country, logo, count: 1, matches: [match] })
  }

  const groups = [...byId.values()]
  for (const group of groups) group.matches.sort(byKickoff)
  return groups.sort((a, b) => {
    const first = byKickoff(a.matches[0], b.matches[0])
    return first !== 0 ? first : a.name.localeCompare(b.name)
  })
}
