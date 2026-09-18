/**
 * Local image fallbacks.
 *
 * Logos used to fall back to via.placeholder.com, a third-party host that no longer resolves: the
 * replacement request failed too, fired `onError` again, and (because the handler always assigned a
 * new src) could loop. These handlers swap in a file this app ships, exactly once per element.
 */

import type { SyntheticEvent } from 'react'

export const TEAM_LOGO_FALLBACK = '/teams/default.svg'
export const LEAGUE_LOGO_FALLBACK = '/leagues/default.svg'

/**
 * Build an `onError` handler that substitutes `fallback` the first time an image fails.
 *
 * The element is marked once it has been swapped, so a fallback that itself fails cannot restart
 * the cycle; the handler is detached as well, belt and braces.
 */
export function imageFallbackHandler(fallback: string) {
  return (event: SyntheticEvent<HTMLImageElement>): void => {
    const img = event.currentTarget
    if (img.dataset.fallbackApplied === 'true') {
      img.onerror = null
      return
    }
    img.dataset.fallbackApplied = 'true'
    img.src = fallback
  }
}

/** `onError` for a club crest. */
export const onTeamLogoError = imageFallbackHandler(TEAM_LOGO_FALLBACK)

/** `onError` for a competition badge. */
export const onLeagueLogoError = imageFallbackHandler(LEAGUE_LOGO_FALLBACK)

/**
 * `onError` for a decorative logo that is better hidden than replaced (dense list rows).
 * Hiding cannot loop, but the handler is detached anyway so a re-render cannot re-fire it.
 */
export function hideBrokenImage(event: SyntheticEvent<HTMLImageElement>): void {
  const img = event.currentTarget
  img.onerror = null
  img.style.display = 'none'
}
