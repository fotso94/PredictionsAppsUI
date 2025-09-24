import { Team, League, Match, User, Prediction, MatchOdds, MatchPredictions, HeadToHead } from '@/types';

// Mock Leagues
export const mockLeagues: League[] = [
  {
    id: 'pl',
    name: 'Premier League',
    shortName: 'EPL',
    country: 'England',
    logo: '/leagues/premier-league.svg',
    season: '2024/25',
    type: 'domestic',
    tier: 1,
  },
  {
    id: 'laliga',
    name: 'La Liga',
    shortName: 'LaLiga',
    country: 'Spain',
    logo: '/leagues/la-liga.svg',
    season: '2024/25',
    type: 'domestic',
    tier: 1,
  },
  {
    id: 'bundesliga',
    name: 'Bundesliga',
    shortName: 'BL1',
    country: 'Germany',
    logo: '/leagues/bundesliga.svg',
    season: '2024/25',
    type: 'domestic',
    tier: 1,
  },
  {
    id: 'seriea',
    name: 'Serie A',
    shortName: 'SA',
    country: 'Italy',
    logo: '/leagues/serie-a.svg',
    season: '2024/25',
    type: 'domestic',
    tier: 1,
  },
  {
    id: 'ucl',
    name: 'UEFA Champions League',
    shortName: 'UCL',
    country: 'Europe',
    logo: '/leagues/champions-league.svg',
    season: '2024/25',
    type: 'international',
    tier: 1,
  },
];

// Mock Teams
export const mockTeams: Team[] = [
  {
    id: 'man-city',
    name: 'Manchester City',
    shortName: 'MCI',
    logo: '/teams/man-city.svg',
    country: 'England',
    league: 'Premier League',
    founded: 1880,
    venue: 'Etihad Stadium',
    colors: { primary: '#6CABDD', secondary: '#1C2C5B' },
    stats: {
      matchesPlayed: 15,
      wins: 12,
      draws: 2,
      losses: 1,
      goalsFor: 38,
      goalsAgainst: 12,
      goalDifference: 26,
      points: 38,
      form: ['W', 'W', 'D', 'W', 'W'],
      homeRecord: { played: 8, wins: 7, draws: 1, losses: 0 },
      awayRecord: { played: 7, wins: 5, draws: 1, losses: 1 },
    },
  },
  {
    id: 'arsenal',
    name: 'Arsenal',
    shortName: 'ARS',
    logo: '/teams/arsenal.svg',
    country: 'England',
    league: 'Premier League',
    founded: 1886,
    venue: 'Emirates Stadium',
    colors: { primary: '#EF0107', secondary: '#023474' },
    stats: {
      matchesPlayed: 15,
      wins: 10,
      draws: 3,
      losses: 2,
      goalsFor: 32,
      goalsAgainst: 18,
      goalDifference: 14,
      points: 33,
      form: ['W', 'D', 'W', 'L', 'W'],
      homeRecord: { played: 7, wins: 6, draws: 1, losses: 0 },
      awayRecord: { played: 8, wins: 4, draws: 2, losses: 2 },
    },
  },
  {
    id: 'liverpool',
    name: 'Liverpool',
    shortName: 'LIV',
    logo: '/teams/liverpool.svg',
    country: 'England',
    league: 'Premier League',
    founded: 1892,
    venue: 'Anfield',
    colors: { primary: '#C8102E', secondary: '#F6EB61' },
    stats: {
      matchesPlayed: 15,
      wins: 9,
      draws: 4,
      losses: 2,
      goalsFor: 35,
      goalsAgainst: 20,
      goalDifference: 15,
      points: 31,
      form: ['W', 'W', 'D', 'W', 'D'],
      homeRecord: { played: 8, wins: 6, draws: 2, losses: 0 },
      awayRecord: { played: 7, wins: 3, draws: 2, losses: 2 },
    },
  },
  {
    id: 'real-madrid',
    name: 'Real Madrid',
    shortName: 'RMA',
    logo: '/teams/real-madrid.svg',
    country: 'Spain',
    league: 'La Liga',
    founded: 1902,
    venue: 'Santiago Bernabéu',
    colors: { primary: '#FFFFFF', secondary: '#FEBE10' },
    stats: {
      matchesPlayed: 16,
      wins: 12,
      draws: 3,
      losses: 1,
      goalsFor: 42,
      goalsAgainst: 15,
      goalDifference: 27,
      points: 39,
      form: ['W', 'W', 'W', 'D', 'W'],
      homeRecord: { played: 8, wins: 7, draws: 1, losses: 0 },
      awayRecord: { played: 8, wins: 5, draws: 2, losses: 1 },
    },
  },
  {
    id: 'barcelona',
    name: 'FC Barcelona',
    shortName: 'BAR',
    logo: '/teams/barcelona.svg',
    country: 'Spain',
    league: 'La Liga',
    founded: 1899,
    venue: 'Camp Nou',
    colors: { primary: '#A50044', secondary: '#004D98' },
    stats: {
      matchesPlayed: 16,
      wins: 11,
      draws: 2,
      losses: 3,
      goalsFor: 38,
      goalsAgainst: 22,
      goalDifference: 16,
      points: 35,
      form: ['W', 'L', 'W', 'W', 'D'],
      homeRecord: { played: 8, wins: 7, draws: 1, losses: 0 },
      awayRecord: { played: 8, wins: 4, draws: 1, losses: 3 },
    },
  },
  {
    id: 'bayern',
    name: 'Bayern Munich',
    shortName: 'BAY',
    logo: '/teams/bayern.svg',
    country: 'Germany',
    league: 'Bundesliga',
    founded: 1900,
    venue: 'Allianz Arena',
    colors: { primary: '#DC052D', secondary: '#0066B2' },
    stats: {
      matchesPlayed: 14,
      wins: 11,
      draws: 2,
      losses: 1,
      goalsFor: 45,
      goalsAgainst: 18,
      goalDifference: 27,
      points: 35,
      form: ['W', 'W', 'W', 'D', 'W'],
      homeRecord: { played: 7, wins: 6, draws: 1, losses: 0 },
      awayRecord: { played: 7, wins: 5, draws: 1, losses: 1 },
    },
  },
];

// Mock Odds
const generateMockOdds = (): MatchOdds => ({
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
});

// Mock Predictions
const generateMockPredictions = (): MatchPredictions => ({
  outcome: {
    homeWin: 45 + Math.random() * 30,
    draw: 25 + Math.random() * 15,
    awayWin: 30 + Math.random() * 25,
    confidence: ['medium', 'high', 'very-high'][Math.floor(Math.random() * 3)] as any,
  },
  bothTeamsToScore: {
    yes: 60 + Math.random() * 25,
    no: 40 - Math.random() * 25,
    confidence: ['medium', 'high'][Math.floor(Math.random() * 2)] as any,
  },
  totalGoals: {
    over25: 65 + Math.random() * 20,
    under25: 35 - Math.random() * 20,
    over35: 40 + Math.random() * 30,
    under35: 60 - Math.random() * 30,
    confidence: ['high', 'very-high'][Math.floor(Math.random() * 2)] as any,
  },
  correctScore: {
    mostLikely: '2-1',
    probability: 12 + Math.random() * 8,
    confidence: 'medium',
  },
  analysis: 'Based on recent form and head-to-head records, this match promises to be highly competitive with both teams showing strong attacking capabilities.',
  keyFactors: [
    'Home team advantage',
    'Recent form favors home side',
    'Key player injuries for away team',
    'Historical dominance in this fixture',
  ],
});

// Mock Head-to-Head
const generateMockHeadToHead = (_homeTeam: Team, _awayTeam: Team): HeadToHead => ({
  totalMatches: 25,
  homeTeamWins: 10,
  draws: 8,
  awayTeamWins: 7,
  lastMatches: [], // Would be populated with actual match data
  averageGoals: {
    home: 1.8,
    away: 1.4,
    total: 3.2,
  },
});

// Generate today's matches
const generateTodayMatches = (): Match[] => {
  const today = new Date().toISOString().split('T')[0];
  const matches: Match[] = [];
  
  for (let i = 0; i < 8; i++) {
    const homeTeam = mockTeams[Math.floor(Math.random() * mockTeams.length)];
    let awayTeam = mockTeams[Math.floor(Math.random() * mockTeams.length)];
    while (awayTeam.id === homeTeam.id) {
      awayTeam = mockTeams[Math.floor(Math.random() * mockTeams.length)];
    }
    
    const league = mockLeagues.find(l => l.name === homeTeam.league) || mockLeagues[0];
    
    matches.push({
      id: `match-${i + 1}`,
      homeTeam,
      awayTeam,
      league,
      date: today,
      time: `${15 + Math.floor(Math.random() * 6)}:${Math.random() > 0.5 ? '00' : '30'}`,
      status: 'scheduled',
      venue: homeTeam.venue,
      round: `Matchday ${Math.floor(Math.random() * 38) + 1}`,
      season: '2024/25',
      odds: generateMockOdds(),
      predictions: generateMockPredictions(),
      headToHead: generateMockHeadToHead(homeTeam, awayTeam),
    });
  }
  
  return matches;
};

export const mockTodayMatches = generateTodayMatches();

// Generate tomorrow's matches
const generateTomorrowMatches = (): Match[] => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowStr = tomorrow.toISOString().split('T')[0];

  const matches: Match[] = [];

  for (let i = 0; i < 6; i++) {
    const homeTeam = mockTeams[Math.floor(Math.random() * mockTeams.length)];
    let awayTeam = mockTeams[Math.floor(Math.random() * mockTeams.length)];
    while (awayTeam.id === homeTeam.id) {
      awayTeam = mockTeams[Math.floor(Math.random() * mockTeams.length)];
    }

    const league = mockLeagues.find(l => l.name === homeTeam.league) || mockLeagues[0];

    matches.push({
      id: `tomorrow-match-${i + 1}`,
      homeTeam,
      awayTeam,
      league,
      date: tomorrowStr,
      time: `${15 + Math.floor(Math.random() * 6)}:${Math.random() > 0.5 ? '00' : '30'}`,
      status: 'scheduled',
      venue: homeTeam.venue,
      round: `Matchday ${Math.floor(Math.random() * 38) + 1}`,
      season: '2024/25',
      odds: generateMockOdds(),
      predictions: generateMockPredictions(),
      headToHead: generateMockHeadToHead(homeTeam, awayTeam),
    });
  }

  return matches;
};

export const mockTomorrowMatches = generateTomorrowMatches();

// Mock User
export const mockUser: User = {
  id: 'user-1',
  email: 'john.doe@example.com',
  username: 'johndoe',
  firstName: 'John',
  lastName: 'Doe',
  avatar: '/avatars/john-doe.jpg',
  role: 'premium',
  subscription: 'premium',
  preferences: {
    favoriteTeams: ['man-city', 'real-madrid'],
    favoriteLeagues: ['pl', 'ucl'],
    notifications: {
      email: true,
      push: true,
      predictions: true,
      results: true,
    },
    theme: 'dark',
    language: 'en',
    timezone: 'UTC',
  },
  stats: {
    totalPredictions: 156,
    correctPredictions: 98,
    accuracy: 62.8,
    streak: {
      current: 5,
      best: 12,
    },
    favoriteMarkets: ['1x2', 'btts', 'over-under'],
    monthlyStats: [
      { month: '2024-01', predictions: 24, correct: 15, accuracy: 62.5 },
      { month: '2024-02', predictions: 28, correct: 18, accuracy: 64.3 },
      { month: '2024-03', predictions: 32, correct: 20, accuracy: 62.5 },
    ],
  },
  createdAt: '2024-01-15T10:30:00Z',
  lastLogin: '2024-03-15T14:22:00Z',
};

// Mock Predictions
export const mockPredictions: Prediction[] = [
  {
    id: 'pred-1',
    matchId: 'match-1',
    userId: 'user-1',
    market: '1x2',
    selection: 'Home Win',
    odds: 2.1,
    confidence: 'high',
    analysis: 'Strong home form and key player availability favor the home team.',
    status: 'pending',
    createdAt: '2024-03-15T10:00:00Z',
  },
  {
    id: 'pred-2',
    matchId: 'match-2',
    userId: 'user-1',
    market: 'btts',
    selection: 'Yes',
    odds: 1.8,
    confidence: 'medium',
    analysis: 'Both teams have strong attacking records and weak defenses.',
    status: 'won',
    createdAt: '2024-03-14T15:30:00Z',
    result: {
      outcome: 'won',
      profit: 0.8,
      settledAt: '2024-03-14T22:00:00Z',
    },
  },
];

// Featured matches for homepage
export const mockFeaturedMatches = mockTodayMatches.slice(0, 3);

// Statistics for homepage
export const mockStats = {
  totalPredictions: 15420,
  accuracy: 68.5,
  activeUsers: 12500,
  successRate: 72.3,
  monthlyGrowth: 15.2,
};
