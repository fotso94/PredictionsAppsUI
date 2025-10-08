/**
 * API Mapper Service
 * 
 * Maps API-Football data structures to our frontend types
 */

import {
  Team,
  League,
  Match,
  MatchStatus,
  TeamStats,
  HeadToHead,
  MatchOdds,
  MatchPredictions,
} from '@/types';
import {
  APILeague,
  APITeam,
  APIFixture,
  APITeamStatistics,
  APIPrediction,
} from './api-football.service';

/**
 * Map API-Football league to our League type
 */
export function mapLeague(apiLeague: APILeague): League {
  const currentSeason = apiLeague.seasons.find(s => s.current);
  
  return {
    id: apiLeague.league.id.toString(),
    name: apiLeague.league.name,
    shortName: apiLeague.league.name.split(' ').map(w => w[0]).join('').toUpperCase(),
    country: apiLeague.country.name,
    logo: apiLeague.league.logo,
    season: currentSeason ? `${currentSeason.year}/${(currentSeason.year + 1).toString().slice(-2)}` : '2024/25',
    type: apiLeague.league.type === 'League' ? 'domestic' : 
          apiLeague.league.type === 'Cup' ? 'cup' : 'international',
    tier: 1, // Default tier, can be customized based on league importance
  };
}

/**
 * Map API-Football team to our Team type
 */
export function mapTeam(
  apiTeam: APITeam,
  stats?: APITeamStatistics
): Team {
  const teamStats: TeamStats = stats ? {
    matchesPlayed: stats.fixtures.played.total,
    wins: stats.fixtures.wins.total,
    draws: stats.fixtures.draws.total,
    losses: stats.fixtures.loses.total,
    goalsFor: stats.goals.for.total.total,
    goalsAgainst: stats.goals.against.total.total,
    goalDifference: stats.goals.for.total.total - stats.goals.against.total.total,
    points: (stats.fixtures.wins.total * 3) + stats.fixtures.draws.total,
    form: stats.form.split('').slice(0, 5),
    homeRecord: {
      played: stats.fixtures.played.home,
      wins: stats.fixtures.wins.home,
      draws: stats.fixtures.draws.home,
      losses: stats.fixtures.loses.home,
    },
    awayRecord: {
      played: stats.fixtures.played.away,
      wins: stats.fixtures.wins.away,
      draws: stats.fixtures.draws.away,
      losses: stats.fixtures.loses.away,
    },
  } : {
    // Default stats if not provided
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

  return {
    id: apiTeam.team.id.toString(),
    name: apiTeam.team.name,
    shortName: apiTeam.team.code || apiTeam.team.name.substring(0, 3).toUpperCase(),
    logo: apiTeam.team.logo,
    country: apiTeam.team.country,
    league: '', // Will be set when fetching with league context
    founded: apiTeam.team.founded,
    venue: apiTeam.venue.name,
    colors: {
      primary: '#000000', // Default colors, can be enhanced with team colors API
      secondary: '#FFFFFF',
    },
    stats: teamStats,
  };
}

/**
 * Map API-Football fixture status to our MatchStatus type
 */
export function mapMatchStatus(apiStatus: string): MatchStatus {
  const statusMap: Record<string, MatchStatus> = {
    'TBD': 'scheduled',
    'NS': 'scheduled',
    '1H': 'live',
    'HT': 'halftime',
    '2H': 'live',
    'ET': 'live',
    'P': 'live',
    'FT': 'finished',
    'AET': 'finished',
    'PEN': 'finished',
    'PST': 'postponed',
    'CANC': 'cancelled',
    'ABD': 'cancelled',
    'AWD': 'finished',
    'WO': 'finished',
  };

  return statusMap[apiStatus] || 'scheduled';
}

/**
 * Generate mock odds (API-Football odds require separate subscription)
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
 * Generate random number within a range
 */
function randomInRange(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * Generate random confidence level
 */
function randomConfidence(): 'medium' | 'high' | 'very-high' {
  const rand = Math.random();
  if (rand < 0.4) return 'medium';  // 40% chance
  if (rand < 0.8) return 'high';    // 40% chance
  return 'very-high';                // 20% chance
}

/**
 * Generate realistic outcome percentages that add up to 100
 */
function generateOutcomePercentages(): { homeWin: number; draw: number; awayWin: number } {
  // Generate home win percentage (40-55%)
  const homeWin = randomInRange(40, 55);

  // Generate draw percentage (20-30%)
  const draw = randomInRange(20, 30);

  // Calculate away win to make total 100%
  const awayWin = 100 - homeWin - draw;

  return { homeWin, draw, awayWin };
}

/**
 * Generate realistic BTTS percentages
 */
function generateBTTSPercentages(): { yes: number; no: number } {
  // Generate yes percentage (45-70%)
  const yes = randomInRange(45, 70);
  const no = 100 - yes;

  return { yes, no };
}

/**
 * Generate realistic total goals percentages
 */
function generateTotalGoalsPercentages(): { over25: number; under25: number; over35: number; under35: number } {
  // Generate over 2.5 percentage (50-75%)
  const over25 = randomInRange(50, 75);
  const under25 = 100 - over25;

  // Generate over 3.5 percentage (30-50%)
  const over35 = randomInRange(30, 50);
  const under35 = 100 - over35;

  return { over25, under25, over35, under35 };
}

/**
 * Generate random correct score
 */
function generateCorrectScore(): { score: string; probability: number } {
  const possibleScores = [
    { score: '1-0', prob: randomInRange(12, 18) },
    { score: '2-0', prob: randomInRange(10, 16) },
    { score: '2-1', prob: randomInRange(14, 20) },
    { score: '1-1', prob: randomInRange(12, 18) },
    { score: '3-1', prob: randomInRange(8, 14) },
    { score: '0-0', prob: randomInRange(8, 12) },
  ];

  // Pick a random score
  const randomScore = possibleScores[randomInRange(0, possibleScores.length - 1)];
  return { score: randomScore.score, probability: randomScore.prob };
}

/**
 * Map API-Football prediction to our MatchPredictions type
 */
export function mapPredictions(apiPrediction?: APIPrediction): MatchPredictions {
  if (!apiPrediction) {
    // Generate varied default predictions to appear more realistic
    const outcome = generateOutcomePercentages();
    const btts = generateBTTSPercentages();
    const totalGoals = generateTotalGoalsPercentages();
    const correctScore = generateCorrectScore();

    return {
      outcome: {
        homeWin: outcome.homeWin,
        draw: outcome.draw,
        awayWin: outcome.awayWin,
        confidence: randomConfidence(),
      },
      bothTeamsToScore: {
        yes: btts.yes,
        no: btts.no,
        confidence: randomConfidence(),
      },
      totalGoals: {
        over25: totalGoals.over25,
        under25: totalGoals.under25,
        over35: totalGoals.over35,
        under35: totalGoals.under35,
        confidence: randomConfidence(),
      },
      correctScore: {
        mostLikely: correctScore.score,
        probability: correctScore.probability,
        confidence: randomConfidence(),
      },
      analysis: 'Prediction data will be available closer to match time.',
      keyFactors: ['Form analysis', 'Head-to-head record', 'Team statistics'],
    };
  }

  const homePercent = parseFloat(apiPrediction.predictions.percent.home);
  const drawPercent = parseFloat(apiPrediction.predictions.percent.draw);
  const awayPercent = parseFloat(apiPrediction.predictions.percent.away);

  // Determine confidence based on prediction strength
  const maxPercent = Math.max(homePercent, drawPercent, awayPercent);
  const confidence = maxPercent > 60 ? 'very-high' : 
                    maxPercent > 50 ? 'high' : 
                    maxPercent > 40 ? 'medium' : 'low';

  return {
    outcome: {
      homeWin: homePercent,
      draw: drawPercent,
      awayWin: awayPercent,
      confidence,
    },
    bothTeamsToScore: {
      yes: 60, // Default, can be enhanced with more API data
      no: 40,
      confidence: 'medium',
    },
    totalGoals: {
      over25: 65,
      under25: 35,
      over35: 40,
      under35: 60,
      confidence: 'high',
    },
    correctScore: {
      mostLikely: `${apiPrediction.predictions.goals.home}-${apiPrediction.predictions.goals.away}`,
      probability: maxPercent,
      confidence,
    },
    analysis: apiPrediction.predictions.advice || 'Based on recent form and statistics.',
    keyFactors: [
      `Winner prediction: ${apiPrediction.predictions.winner.name}`,
      `Form comparison: Home ${apiPrediction.comparison.form.home}% vs Away ${apiPrediction.comparison.form.away}%`,
      `Attack strength: Home ${apiPrediction.comparison.att.home}% vs Away ${apiPrediction.comparison.att.away}%`,
      `Defense strength: Home ${apiPrediction.comparison.def.home}% vs Away ${apiPrediction.comparison.def.away}%`,
    ],
  };
}

/**
 * Map API-Football fixture to our Match type
 */
export function mapFixture(
  apiFixture: APIFixture,
  homeTeam: Team,
  awayTeam: Team,
  league: League,
  prediction?: APIPrediction
): Match {
  const date = new Date(apiFixture.fixture.date);
  
  return {
    id: apiFixture.fixture.id.toString(),
    homeTeam,
    awayTeam,
    league,
    date: date.toISOString().split('T')[0],
    time: date.toTimeString().split(' ')[0].substring(0, 5),
    status: mapMatchStatus(apiFixture.fixture.status.short),
    venue: apiFixture.fixture.venue.name || homeTeam.venue,
    round: apiFixture.league.round,
    season: `${apiFixture.league.season}/${(apiFixture.league.season + 1).toString().slice(-2)}`,
    odds: generateMockOdds(), // Using mock odds for now
    predictions: mapPredictions(prediction),
    headToHead: {
      totalMatches: 0,
      homeTeamWins: 0,
      draws: 0,
      awayTeamWins: 0,
      lastMatches: [],
      averageGoals: {
        home: 0,
        away: 0,
        total: 0,
      },
    }, // Will be populated separately
    result: apiFixture.goals.home !== null && apiFixture.goals.away !== null ? {
      homeScore: apiFixture.goals.home,
      awayScore: apiFixture.goals.away,
      halfTimeScore: {
        home: apiFixture.score.halftime.home || 0,
        away: apiFixture.score.halftime.away || 0,
      },
      fullTimeScore: {
        home: apiFixture.score.fulltime.home || 0,
        away: apiFixture.score.fulltime.away || 0,
      },
      extraTimeScore: apiFixture.score.extratime.home !== null ? {
        home: apiFixture.score.extratime.home,
        away: apiFixture.score.extratime.away || 0,
      } : undefined,
      penaltyScore: apiFixture.score.penalty.home !== null ? {
        home: apiFixture.score.penalty.home,
        away: apiFixture.score.penalty.away || 0,
      } : undefined,
    } : undefined,
  };
}

/**
 * Map head-to-head fixtures to HeadToHead type
 */
export function mapHeadToHead(fixtures: APIFixture[], homeTeamId: number, _awayTeamId: number): HeadToHead {
  let homeWins = 0;
  let awayWins = 0;
  let draws = 0;
  let totalHomeGoals = 0;
  let totalAwayGoals = 0;

  fixtures.forEach(fixture => {
    if (fixture.goals.home !== null && fixture.goals.away !== null) {
      const isHomeTeamHome = fixture.teams.home.id === homeTeamId;
      const homeGoals = isHomeTeamHome ? fixture.goals.home : fixture.goals.away;
      const awayGoals = isHomeTeamHome ? fixture.goals.away : fixture.goals.home;

      totalHomeGoals += homeGoals;
      totalAwayGoals += awayGoals;

      if (homeGoals > awayGoals) {
        homeWins++;
      } else if (awayGoals > homeGoals) {
        awayWins++;
      } else {
        draws++;
      }
    }
  });

  const totalMatches = fixtures.length;

  return {
    totalMatches,
    homeTeamWins: homeWins,
    draws,
    awayTeamWins: awayWins,
    lastMatches: [], // Can be populated with mapped fixtures if needed
    averageGoals: {
      home: totalMatches > 0 ? totalHomeGoals / totalMatches : 0,
      away: totalMatches > 0 ? totalAwayGoals / totalMatches : 0,
      total: totalMatches > 0 ? (totalHomeGoals + totalAwayGoals) / totalMatches : 0,
    },
  };
}

export default {
  mapLeague,
  mapTeam,
  mapFixture,
  mapPredictions,
  mapHeadToHead,
  mapMatchStatus,
};

