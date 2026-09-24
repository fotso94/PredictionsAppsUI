/**
 * Club football and national-team football, told apart — and the squad inside a country.
 *
 * ── WHY THIS IS NOT A STRING COMPARISON SOMEWHERE ───────────────────────────────────────────
 *
 * Both answers come off the wire and neither is derivable from anything on screen. A competition
 * is national-team football because the backend's canonical table says so: "National Teams
 * Friendlies", "UEFA Nations League", "World Cup CONCACAF Qualifiers" and "Premier League" share
 * no shape a name rule could read, and guessing on the word "national" would file the Nations
 * League correctly and the Copa América not at all. A team is a country's women's squad because
 * its row says so: "Spain" and "Spain (W)" are one name to the matcher that turns "Ipswich" into
 * "Ipswich Town", which is why the backend stores them as separate rows with separate scopes.
 *
 * ── THREE ANSWERS, NOT TWO ──────────────────────────────────────────────────────────────────
 *
 * `unknown` is a real state and is kept apart from `club` throughout. A payload from before the
 * classification existed carries no `is_national_team` at all, and reading its absence as "a club
 * competition" would put a country in the club list the first time an old cached response is
 * served. A filter therefore narrows to what it can prove and leaves the rest visible only under
 * "All" — see `matchesKind`.
 *
 * ── WHAT IS DELIBERATELY NOT HERE ───────────────────────────────────────────────────────────
 *
 * No wording. Every phrase this file's answers turn into lives in the catalogue, keyed by the
 * scope value, so a language decides its own words for a women's national team rather than
 * receiving an English one assembled from parts. See `squadNote`.
 */

import type { Confederation, League, Match, SquadCategory, TeamScope } from '@/types'
import type { MessageKey } from '@/i18n'
import { t } from '@/i18n'

/** Every scope the backend can store, in the spelling it stores. */
export const TEAM_SCOPES: readonly TeamScope[] = [
  'club_senior_men', 'club_senior_women', 'club_youth',
  'national_senior_men', 'national_senior_women', 'national_youth',
] as const

/** Every squad category the backend can publish for a competition. */
export const SQUAD_CATEGORIES: readonly SquadCategory[] = ['senior_men', 'senior_women', 'youth'] as const

/**
 * A scope this build understands, or undefined.
 *
 * A value we do not recognise is dropped rather than carried: the whole point of the scope is to
 * decide what a reader is shown, and a string nothing here can interpret would decide nothing
 * while looking as though it had.
 */
export function asTeamScope(value: unknown): TeamScope | undefined {
  return typeof value === 'string' && (TEAM_SCOPES as readonly string[]).includes(value)
    ? (value as TeamScope)
    : undefined
}

/** A squad category this build understands, or null. */
export function asSquadCategory(value: unknown): SquadCategory | null {
  return typeof value === 'string' && (SQUAD_CATEGORIES as readonly string[]).includes(value)
    ? (value as SquadCategory)
    : null
}

/** Every confederation the backend can publish, plus FIFA for worldwide competitions. */
export const CONFEDERATIONS: readonly Confederation[] =
  ['FIFA', 'CAF', 'UEFA', 'AFC', 'CONCACAF', 'CONMEBOL', 'OFC'] as const

/** A confederation this build understands, or null. */
export function asConfederation(value: unknown): Confederation | null {
  return typeof value === 'string' && (CONFEDERATIONS as readonly string[]).includes(value)
    ? (value as Confederation)
    : null
}

/** Which kind of football a fixture is. `unknown` is the payload not saying, never a club. */
export type FixtureKind = 'club' | 'national' | 'unknown'

/** The three answers, as the filter offers them. `all` is the absence of the filter. */
export type KindFilter = 'all' | 'club' | 'national'

/** What a competition is, from the classification the backend published for it. */
export function competitionKind(league: League | null | undefined): FixtureKind {
  if (typeof league?.isNationalTeam !== 'boolean') return 'unknown'
  return league.isNationalTeam ? 'national' : 'club'
}

/** What a fixture is, which is what its competition is. */
export function fixtureKind(match: Match): FixtureKind {
  return competitionKind(match.league)
}

/**
 * Does this fixture survive a kind filter?
 *
 * A fixture whose kind is unknown survives only `all`. That is the conservative reading in both
 * directions: it is never counted as club football it might not be, and never counted as national
 * football it might not be either — and it stays reachable, because `all` is the default and no
 * reader is filtered away from a fixture without having asked for a narrower list.
 */
export function matchesKind(match: Match, kind: KindFilter): boolean {
  return kind === 'all' || fixtureKind(match) === kind
}

/**
 * WHICH squad a team is, in the reader's language — or null when there is nothing worth saying.
 *
 * Silence is the answer for a men's senior club, which is what almost every row in this
 * application is: a badge reading "Men's club" on every fixture would be noise on twenty rows to
 * disambiguate none of them. It is also the answer for a row whose scope we do not have, because
 * the phrase would then be a guess.
 *
 * Every other scope gets a key of its own rather than a stem plus a qualifier. French agrees the
 * article and the adjective with a noun that differs per scope ("l'équipe nationale féminine",
 * "l'équipe nationale des moins de 23 ans"), and none of that survives assembling "women" and
 * "national team" in English word order.
 */
export function squadNote(scope: TeamScope | undefined): string | null {
  const key: MessageKey | null = scope === 'national_senior_men' ? 'squad.nationalSeniorMen'
    : scope === 'national_senior_women' ? 'squad.nationalSeniorWomen'
      : scope === 'national_youth' ? 'squad.nationalYouth'
        : scope === 'club_senior_women' ? 'squad.clubSeniorWomen'
          : scope === 'club_youth' ? 'squad.clubYouth'
            : null
  // Resolved at call time, never at import: the catalogue in force is the reader's current one,
  // and a phrase captured when this module was first evaluated would be the language the tab
  // booted in for the life of the tab.
  return key ? t(key) : null
}

/**
 * The one line that goes under a team's name wherever a team is listed.
 *
 * For a club it is the country, whatever its squad — "Barcelona / Spain" tells a reader more than
 * "Barcelona / women's team", and a club's country is the thing that separates two clubs sharing a
 * name. Only a NATIONAL squad trades the country for the squad, and only because a country is
 * exactly what it cannot print: two of Spain's squads carry the same country, so the country is
 * the one fact that cannot tell them apart, which is the whole reason this line exists.
 *
 * Null when neither is known, so a caller renders nothing rather than an empty line.
 */
export function teamSubtitle(team: { country?: string | null; scope?: TeamScope }): string | null {
  const national = team.scope?.startsWith('national_') ? squadNote(team.scope) : null
  return national ?? (team.country || null) ?? squadNote(team.scope)
}

