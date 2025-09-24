/**
 * Utility functions for handling team and league logos
 * Uses reliable placeholder service for consistent display
 */

// Reliable logo sources with fallbacks
const LOGO_SOURCES = {
  // Primary source - placeholder service (always works)
  fallback: 'https://via.placeholder.com/64x64/334155/ffffff?text='
}

// Team logo mappings with multiple sources
export const TEAM_LOGOS: Record<string, { primary: string; secondary?: string; fallback: string }> = {
  'man-city': {
    primary: 'thumb/e/eb/Manchester_City_FC_badge.svg/64px-Manchester_City_FC_badge.svg.png',
    secondary: 'manchester-city.png',
    fallback: 'MCI'
  },
  'arsenal': {
    primary: 'thumb/5/53/Arsenal_FC.svg/64px-Arsenal_FC.svg.png',
    secondary: 'arsenal.png',
    fallback: 'ARS'
  },
  'liverpool': {
    primary: 'thumb/0/0c/Liverpool_FC.svg/64px-Liverpool_FC.svg.png',
    secondary: 'liverpool.png',
    fallback: 'LIV'
  },
  'real-madrid': {
    primary: 'thumb/c/c7/Real_Madrid_CF.svg/64px-Real_Madrid_CF.svg.png',
    secondary: 'real-madrid.png',
    fallback: 'RMA'
  },
  'barcelona': {
    primary: 'thumb/4/47/FC_Barcelona_%28crest%29.svg/64px-FC_Barcelona_%28crest%29.svg.png',
    secondary: 'barcelona.png',
    fallback: 'BAR'
  },
  'bayern': {
    primary: 'thumb/1/1b/FC_Bayern_M%C3%BCnchen_logo_%282017%29.svg/64px-FC_Bayern_M%C3%BCnchen_logo_%282017%29.svg.png',
    secondary: 'bayern-munich.png',
    fallback: 'BAY'
  }
}

// League logo mappings
export const LEAGUE_LOGOS: Record<string, { primary: string; secondary?: string; fallback: string }> = {
  'pl': {
    primary: 'thumb/f/f2/Premier_League_Logo.svg/64px-Premier_League_Logo.svg.png',
    secondary: 'premier-league.png',
    fallback: 'EPL'
  },
  'laliga': {
    primary: 'thumb/1/13/LaLiga.svg/64px-LaLiga.svg.png',
    secondary: 'la-liga.png',
    fallback: 'LL'
  },
  'bundesliga': {
    primary: 'thumb/d/df/Bundesliga_logo_%282017%29.svg/64px-Bundesliga_logo_%282017%29.svg.png',
    secondary: 'bundesliga.png',
    fallback: 'BL'
  },
  'seriea': {
    primary: 'thumb/b/b5/Serie_A_logo_2022.svg/64px-Serie_A_logo_2022.svg.png',
    secondary: 'serie-a.png',
    fallback: 'SA'
  },
  'ucl': {
    primary: 'thumb/b/bf/UEFA_Champions_League_logo_2.svg/64px-UEFA_Champions_League_logo_2.svg.png',
    secondary: 'uefa-champions-league.png',
    fallback: 'UCL'
  }
}

/**
 * Get team logo URL with fallback handling
 */
export const getTeamLogoUrl = (teamId: string, originalUrl?: string): string => {
  // If we have the original URL from mockData, use it
  if (originalUrl) {
    return originalUrl
  }

  // Fallback to placeholder
  const logoConfig = TEAM_LOGOS[teamId]
  const fallbackText = logoConfig?.fallback || teamId.toUpperCase()
  return `${LOGO_SOURCES.fallback}${fallbackText}`
}

/**
 * Get league logo URL with fallback handling
 */
export const getLeagueLogoUrl = (leagueId: string, originalUrl?: string): string => {
  // If we have the original URL from mockData, use it
  if (originalUrl) {
    return originalUrl
  }

  // Fallback to placeholder
  const logoConfig = LEAGUE_LOGOS[leagueId]
  const fallbackText = logoConfig?.fallback || leagueId.toUpperCase()
  return `${LOGO_SOURCES.fallback}${fallbackText}`
}

/**
 * Get fallback logo URL for teams
 */
export const getTeamFallbackUrl = (teamId: string): string => {
  const logoConfig = TEAM_LOGOS[teamId]
  return `${LOGO_SOURCES.fallback}${logoConfig?.fallback || teamId.toUpperCase()}`
}

/**
 * Get fallback logo URL for leagues
 */
export const getLeagueFallbackUrl = (leagueId: string): string => {
  const logoConfig = LEAGUE_LOGOS[leagueId]
  return `${LOGO_SOURCES.fallback}${logoConfig?.fallback || leagueId.toUpperCase()}`
}

/**
 * Handle image error with fallback
 */
export const handleLogoError = (
  event: React.SyntheticEvent<HTMLImageElement>,
  type: 'team' | 'league',
  id: string
) => {
  const img = event.currentTarget

  // If we're already showing a fallback, don't try again
  if (img.src.includes('placeholder')) {
    return
  }

  // Log the error for debugging
  console.log(`Logo failed to load for ${type} ${id}:`, img.src)

  // Final fallback to placeholder
  const logoConfig = type === 'team' ? TEAM_LOGOS[id] : LEAGUE_LOGOS[id]
  const fallbackText = logoConfig?.fallback || id.toUpperCase()
  img.src = `${LOGO_SOURCES.fallback}${fallbackText}`
}
