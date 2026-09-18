/**
 * TheSportsDB Mapper Service
 * 
 * Maps TheSportsDB V1 API data structures to our frontend types
 */

import {
  Team,
  League,
  Match,
  MatchStatus,
  TeamStats,
  LeagueStanding,
  MatchOdds,
  MatchPredictions,
} from '@/types';
import {
  DBLeague,
  DBTeam,
  DBEvent,
  DBStanding,
} from './thesportsdb.service';

/**
 * Map TheSportsDB league to our League type
 */
export function mapLeague(dbLeague: DBLeague): League {
  return {
    id: dbLeague.idLeague,
    name: dbLeague.strLeague,
    shortName: dbLeague.strLeagueAlternate || dbLeague.strLeague.split(' ').map(w => w[0]).join('').toUpperCase(),
    country: dbLeague.strCountry,
    logo: dbLeague.strBadge || dbLeague.strLogo,
    season: '2025/26',
    type: 'domestic',
    tier: 1,
  };
}

/**
 * Map TheSportsDB team to our Team type
 */
export function mapTeam(dbTeam: DBTeam, stats?: TeamStats): Team {
  const defaultStats: TeamStats = {
    matchesPlayed: 0,
    wins: 0,
    draws: 0,
    losses: 0,
    goalsFor: 0,
    goalsAgainst: 0,
    goalDifference: 0,
    points: 0,
    form: [],
    homeRecord: { played: 0, wins: 0, draws: 0, losses: 0 },
    awayRecord: { played: 0, wins: 0, draws: 0, losses: 0 },
  };

  // Remove /tiny, /small, /medium suffixes from logo URLs to get full-size images
  const cleanLogoUrl = (url: string | undefined) => {
    if (!url) return url || '';
    return url.replace(/\/(tiny|small|medium)$/, '');
  };

  return {
    id: dbTeam.idTeam,
    name: dbTeam.strTeam,
    shortName: dbTeam.strTeamShort || dbTeam.strTeam.substring(0, 3).toUpperCase(),
    logo: cleanLogoUrl(dbTeam.strBadge || dbTeam.strLogo || dbTeam.strTeamBadge || dbTeam.strTeamLogo),
    country: dbTeam.strCountry,
    league: dbTeam.strLeague,
    founded: parseInt(dbTeam.intFormedYear) || 0,
    venue: dbTeam.strStadium,
    colors: {
      primary: '#000000',
      secondary: '#FFFFFF',
    },
    stats: stats || defaultStats,
  };
}

/**
 * Map TheSportsDB event status to our MatchStatus type
 */
export function mapMatchStatus(dbStatus: string): MatchStatus {
  const status = dbStatus?.toLowerCase() || '';
  
  if (status.includes('not started') || status === '' || status === 'ns') {
    return 'scheduled';
  } else if (status.includes('live') || status.includes('1h') || status.includes('2h')) {
    return 'live';
  } else if (status.includes('half') || status === 'ht') {
    return 'halftime';
  } else if (status.includes('finished') || status === 'ft' || status.includes('full')) {
    return 'finished';
  } else if (status.includes('postponed')) {
    return 'postponed';
  } else if (status.includes('cancelled') || status.includes('canceled')) {
    return 'cancelled';
  }
  
  return 'scheduled';
}

/**
 * Generate mock odds (TheSportsDB doesn't provide odds in V1 API)
 */
function generateMockOdds(): MatchOdds {
  return {
    homeWin: 2.1 + Math.random() * 2,
    draw: 3.2 + Math.random() * 1.5,
    awayWin: 2.8 + Math.random() * 2.5,
    bothTeamsToScore: {
      yes: 1.7 + Math.random() * 0.6,
      no: 2.0 + Math.random() * 0.8,
    },
    overUnder: {
      over25: 1.8 + Math.random() * 0.5,
      under25: 1.9 + Math.random() * 0.5,
      over35: 2.4 + Math.random() * 0.8,
      under35: 1.5 + Math.random() * 0.4,
    },
    correctScore: {
      '1-0': 8.5,
      '2-0': 12.0,
      '2-1': 9.5,
      '1-1': 6.5,
      '0-0': 11.0,
      '3-1': 18.0,
    },
  };
}

/**
 * Generate mock predictions (TheSportsDB doesn't provide predictions)
 */
function generateMockPredictions(): MatchPredictions {
  const homeWin = 30 + Math.random() * 40;
  const draw = 20 + Math.random() * 20;
  const awayWin = 100 - homeWin - draw;

  return {
    outcome: {
      homeWin: Math.round(homeWin),
      draw: Math.round(draw),
      awayWin: Math.round(awayWin),
      confidence: homeWin > 50 ? 'high' : homeWin > 40 ? 'medium' : 'low',
    },
    bothTeamsToScore: {
      yes: 55 + Math.random() * 20,
      no: 25 + Math.random() * 20,
      confidence: 'medium',
    },
    totalGoals: {
      over25: 60 + Math.random() * 20,
      under25: 20 + Math.random() * 20,
      over35: 35 + Math.random() * 20,
      under35: 45 + Math.random() * 20,
      confidence: 'high',
    },
    correctScore: {
      mostLikely: '2-1',
      probability: 15,
      confidence: 'medium',
    },
    analysis: 'Prediction based on team form and historical data. Expert analysis available for premium users.',
    keyFactors: ['Recent form', 'Head-to-head record', 'Home advantage'],
  };
}

/**
 * Create a basic team object from event data
 */
function createBasicTeamFromEvent(
  teamId: string,
  teamName: string,
  leagueName: string
): Team {
  // Use fallback logo - will be replaced when actual team data is fetched
  const fallbackLogo = '/teams/default.svg';

  return {
    id: teamId,
    name: teamName,
    shortName: teamName.substring(0, 3).toUpperCase(),
    logo: fallbackLogo,
    country: '',
    league: leagueName,
    founded: 0,
    venue: '',
    colors: { primary: '#000000', secondary: '#FFFFFF' },
    stats: {
      matchesPlayed: 0,
      wins: 0,
      draws: 0,
      losses: 0,
      goalsFor: 0,
      goalsAgainst: 0,
      goalDifference: 0,
      points: 0,
      form: [],
      homeRecord: { played: 0, wins: 0, draws: 0, losses: 0 },
      awayRecord: { played: 0, wins: 0, draws: 0, losses: 0 },
    },
  };
}

/**
 * Create a basic league object from event data
 */
function createBasicLeagueFromEvent(
  leagueId: string,
  leagueName: string,
  country: string
): League {
  // Use fallback logo - will be replaced when actual league data is fetched
  const fallbackLogo = '/leagues/default.svg';

  return {
    id: leagueId,
    name: leagueName,
    shortName: leagueName.split(' ').map(w => w[0]).join('').toUpperCase(),
    country: country,
    logo: fallbackLogo,
    season: '2025/26',
    type: 'domestic',
    tier: 1,
  };
}

/**
 * Map TheSportsDB event to our Match type
 */
export function mapEvent(
  dbEvent: DBEvent,
  homeTeam?: Team,
  awayTeam?: Team,
  league?: League
): Match {
  // Create basic team/league objects if not provided
  const home = homeTeam || createBasicTeamFromEvent(
    dbEvent.idHomeTeam,
    dbEvent.strHomeTeam,
    dbEvent.strLeague
  );
  
  const away = awayTeam || createBasicTeamFromEvent(
    dbEvent.idAwayTeam,
    dbEvent.strAwayTeam,
    dbEvent.strLeague
  );
  
  const leagueObj = league || createBasicLeagueFromEvent(
    dbEvent.idLeague,
    dbEvent.strLeague,
    dbEvent.strCountry
  );

  // Parse date and time
  const dateStr = dbEvent.dateEvent || dbEvent.strDate;
  const timeStr = dbEvent.strTime || '00:00:00';

  return {
    id: dbEvent.idEvent,
    homeTeam: home,
    awayTeam: away,
    league: leagueObj,
    date: dateStr,
    time: timeStr.substring(0, 5),
    status: mapMatchStatus(dbEvent.strStatus),
    venue: dbEvent.strVenue || home.venue,
    round: `Round ${dbEvent.intRound || '1'}`,
    season: dbEvent.strSeason || '2024-2025',
    odds: generateMockOdds(),
    predictions: generateMockPredictions(),
    headToHead: {
      totalMatches: 0,
      homeTeamWins: 0,
      draws: 0,
      awayTeamWins: 0,
      lastMatches: [],
      averageGoals: { home: 0, away: 0, total: 0 },
    },
    result: dbEvent.intHomeScore !== null && dbEvent.intAwayScore !== null ? {
      homeScore: parseInt(dbEvent.intHomeScore) || 0,
      awayScore: parseInt(dbEvent.intAwayScore) || 0,
      halfTimeScore: { home: 0, away: 0 },
      fullTimeScore: {
        home: parseInt(dbEvent.intHomeScore) || 0,
        away: parseInt(dbEvent.intAwayScore) || 0,
      },
    } : undefined,
  };
}

/**
 * Map TheSportsDB standing to our LeagueStanding type
 */
export function mapStanding(dbStanding: DBStanding): LeagueStanding {
  const form = dbStanding.strForm ? dbStanding.strForm.split('') : [];

  // Remove /tiny, /small, /medium suffixes from logo URLs to get full-size images
  const cleanLogoUrl = (url: string | undefined) => {
    if (!url) return url || '';
    return url.replace(/\/(tiny|small|medium)$/, '');
  };

  return {
    position: parseInt(dbStanding.intRank),
    team: {
      id: dbStanding.idTeam,
      name: dbStanding.strTeam,
      shortName: dbStanding.strTeam.substring(0, 3).toUpperCase(),
      logo: cleanLogoUrl(dbStanding.strBadge || dbStanding.strTeamBadge),
      country: '',
      league: dbStanding.strLeague,
      founded: 0,
      venue: '',
      colors: { primary: '#000000', secondary: '#FFFFFF' },
      stats: {
        matchesPlayed: parseInt(dbStanding.intPlayed),
        wins: parseInt(dbStanding.intWin),
        draws: parseInt(dbStanding.intDraw),
        losses: parseInt(dbStanding.intLoss),
        goalsFor: parseInt(dbStanding.intGoalsFor),
        goalsAgainst: parseInt(dbStanding.intGoalsAgainst),
        goalDifference: parseInt(dbStanding.intGoalDifference),
        points: parseInt(dbStanding.intPoints),
        form: form,
        homeRecord: { played: 0, wins: 0, draws: 0, losses: 0 },
        awayRecord: { played: 0, wins: 0, draws: 0, losses: 0 },
      },
    },
    matchesPlayed: parseInt(dbStanding.intPlayed),
    wins: parseInt(dbStanding.intWin),
    draws: parseInt(dbStanding.intDraw),
    losses: parseInt(dbStanding.intLoss),
    goalsFor: parseInt(dbStanding.intGoalsFor),
    goalsAgainst: parseInt(dbStanding.intGoalsAgainst),
    goalDifference: parseInt(dbStanding.intGoalDifference),
    points: parseInt(dbStanding.intPoints),
    form: form,
  };
}

export default {
  mapLeague,
  mapTeam,
  mapEvent,
  mapStanding,
  mapMatchStatus,
};

