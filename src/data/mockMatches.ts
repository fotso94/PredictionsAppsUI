import type { Match } from '../types';
import { mockTeams } from './mockTeams';
import { mockLeagues } from './mockLeagues';

const getTeamById = (id: string) => mockTeams.find(team => team.id === id)!;
const getLeagueById = (id: string) => mockLeagues.find(league => league.id === id)!;

export const mockMatches: Match[] = [
  {
    id: 'match-1',
    homeTeam: getTeamById('team-1'), // Manchester United
    awayTeam: getTeamById('team-2'), // Manchester City
    league: getLeagueById('league-1'), // Premier League
    date: '2025-09-23',
    time: '16:30',
    status: 'scheduled',
    venue: 'Old Trafford',
    referee: 'Michael Oliver',
    weather: {
      temperature: 18,
      condition: 'Partly Cloudy',
      humidity: 65,
      windSpeed: 12,
    },
    odds: {
      homeWin: 2.80,
      draw: 3.20,
      awayWin: 2.45,
      over25: 1.85,
      under25: 1.95,
      btts: 1.75,
      noGoals: 2.10,
      correctScore: {
        '1-0': 8.50,
        '2-1': 9.00,
        '1-1': 6.50,
        '0-0': 12.00,
        '2-0': 11.00,
      },
    },
    h2h: {
      totalMatches: 10,
      homeWins: 3,
      awayWins: 5,
      draws: 2,
      lastMatches: [],
      averageGoals: 2.8,
      bttsPercentage: 70,
    },
  },
  {
    id: 'match-2',
    homeTeam: getTeamById('team-3'), // Liverpool
    awayTeam: getTeamById('team-4'), // Arsenal
    league: getLeagueById('league-1'), // Premier League
    date: '2025-09-23',
    time: '14:00',
    status: 'scheduled',
    venue: 'Anfield',
    referee: 'Anthony Taylor',
    weather: {
      temperature: 16,
      condition: 'Overcast',
      humidity: 70,
      windSpeed: 8,
    },
    odds: {
      homeWin: 1.95,
      draw: 3.40,
      awayWin: 3.80,
      over25: 1.70,
      under25: 2.15,
      btts: 1.65,
      noGoals: 2.25,
      correctScore: {
        '2-1': 7.50,
        '1-0': 7.00,
        '2-0': 8.50,
        '1-1': 6.00,
        '3-1': 12.00,
      },
    },
    h2h: {
      totalMatches: 8,
      homeWins: 4,
      awayWins: 2,
      draws: 2,
      lastMatches: [],
      averageGoals: 3.1,
      bttsPercentage: 75,
    },
  },
  {
    id: 'match-3',
    homeTeam: getTeamById('team-5'), // Chelsea
    awayTeam: getTeamById('team-1'), // Manchester United
    league: getLeagueById('league-1'), // Premier League
    date: '2025-09-24',
    time: '19:45',
    status: 'scheduled',
    venue: 'Stamford Bridge',
    referee: 'Paul Tierney',
    weather: {
      temperature: 19,
      condition: 'Clear',
      humidity: 60,
      windSpeed: 10,
    },
    odds: {
      homeWin: 2.30,
      draw: 3.10,
      awayWin: 3.20,
      over25: 1.80,
      under25: 2.00,
      btts: 1.70,
      noGoals: 2.15,
    },
    h2h: {
      totalMatches: 12,
      homeWins: 5,
      awayWins: 4,
      draws: 3,
      lastMatches: [],
      averageGoals: 2.5,
      bttsPercentage: 65,
    },
  },
  {
    id: 'match-4',
    homeTeam: getTeamById('team-6'), // Real Madrid
    awayTeam: getTeamById('team-7'), // Barcelona
    league: getLeagueById('league-2'), // La Liga
    date: '2025-09-23',
    time: '21:00',
    status: 'scheduled',
    venue: 'Santiago Bernabéu',
    referee: 'José María Sánchez Martínez',
    weather: {
      temperature: 22,
      condition: 'Clear',
      humidity: 55,
      windSpeed: 5,
    },
    odds: {
      homeWin: 2.10,
      draw: 3.30,
      awayWin: 3.40,
      over25: 1.75,
      under25: 2.05,
      btts: 1.60,
      noGoals: 2.40,
    },
    h2h: {
      totalMatches: 15,
      homeWins: 7,
      awayWins: 5,
      draws: 3,
      lastMatches: [],
      averageGoals: 3.2,
      bttsPercentage: 80,
    },
  },
  {
    id: 'match-5',
    homeTeam: getTeamById('team-8'), // Bayern Munich
    awayTeam: getTeamById('team-1'), // Manchester United (Champions League)
    league: getLeagueById('league-6'), // Champions League
    date: '2025-09-25',
    time: '20:00',
    status: 'scheduled',
    venue: 'Allianz Arena',
    referee: 'Clément Turpin',
    weather: {
      temperature: 15,
      condition: 'Light Rain',
      humidity: 80,
      windSpeed: 15,
    },
    odds: {
      homeWin: 1.70,
      draw: 3.60,
      awayWin: 4.50,
      over25: 1.65,
      under25: 2.25,
      btts: 1.55,
      noGoals: 2.50,
    },
    h2h: {
      totalMatches: 6,
      homeWins: 3,
      awayWins: 2,
      draws: 1,
      lastMatches: [],
      averageGoals: 3.5,
      bttsPercentage: 85,
    },
  },
  // Today's matches (live/finished)
  {
    id: 'match-6',
    homeTeam: getTeamById('team-2'), // Manchester City
    awayTeam: getTeamById('team-5'), // Chelsea
    league: getLeagueById('league-1'), // Premier League
    date: '2025-09-22',
    time: '15:00',
    status: 'finished',
    venue: 'Etihad Stadium',
    referee: 'Craig Pawson',
    result: {
      homeScore: 2,
      awayScore: 1,
      halftimeScore: {
        home: 1,
        away: 0,
      },
    },
    stats: {
      possession: {
        home: 65,
        away: 35,
      },
      shots: {
        home: 18,
        away: 8,
      },
      shotsOnTarget: {
        home: 7,
        away: 3,
      },
      corners: {
        home: 9,
        away: 4,
      },
      fouls: {
        home: 12,
        away: 16,
      },
      yellowCards: {
        home: 2,
        away: 4,
      },
      redCards: {
        home: 0,
        away: 0,
      },
    },
    odds: {
      homeWin: 1.85,
      draw: 3.50,
      awayWin: 4.20,
      over25: 1.75,
      under25: 2.05,
      btts: 1.70,
      noGoals: 2.15,
    },
  },
  {
    id: 'match-7',
    homeTeam: getTeamById('team-3'), // Liverpool
    awayTeam: getTeamById('team-1'), // Manchester United
    league: getLeagueById('league-1'), // Premier League
    date: '2025-09-22',
    time: '17:30',
    status: 'live',
    venue: 'Anfield',
    referee: 'Michael Oliver',
    result: {
      homeScore: 1,
      awayScore: 1,
      halftimeScore: {
        home: 0,
        away: 1,
      },
    },
    stats: {
      possession: {
        home: 58,
        away: 42,
      },
      shots: {
        home: 12,
        away: 9,
      },
      shotsOnTarget: {
        home: 4,
        away: 5,
      },
      corners: {
        home: 6,
        away: 3,
      },
      fouls: {
        home: 8,
        away: 11,
      },
      yellowCards: {
        home: 1,
        away: 2,
      },
      redCards: {
        home: 0,
        away: 0,
      },
    },
    odds: {
      homeWin: 1.90,
      draw: 3.40,
      awayWin: 4.00,
      over25: 1.80,
      under25: 2.00,
      btts: 1.65,
      noGoals: 2.20,
    },
  },
];
