import {
  League,
  Team,
  Match,
  Prediction,
  PredictionMarket,
  ConfidenceLevel,
  MatchStatus,
  PredictionStatus,
  Article,
  ArticleCategory,
  AccuracyStats,
  DashboardStats
} from '../types';

// Mock Leagues
export const mockLeagues: League[] = [
  {
    id: '1',
    name: 'Premier League',
    country: 'England',
    countryCode: 'GB',
    logo: '/leagues/premier-league.png',
    season: '2024/25',
    isActive: true,
    tier: 1
  },
  {
    id: '2',
    name: 'La Liga',
    country: 'Spain',
    countryCode: 'ES',
    logo: '/leagues/la-liga.png',
    season: '2024/25',
    isActive: true,
    tier: 1
  },
  {
    id: '3',
    name: 'Serie A',
    country: 'Italy',
    countryCode: 'IT',
    logo: '/leagues/serie-a.png',
    season: '2024/25',
    isActive: true,
    tier: 1
  },
  {
    id: '4',
    name: 'Bundesliga',
    country: 'Germany',
    countryCode: 'DE',
    logo: '/leagues/bundesliga.png',
    season: '2024/25',
    isActive: true,
    tier: 1
  },
  {
    id: '5',
    name: 'Ligue 1',
    country: 'France',
    countryCode: 'FR',
    logo: '/leagues/ligue-1.png',
    season: '2024/25',
    isActive: true,
    tier: 1
  },
  {
    id: '6',
    name: 'Champions League',
    country: 'Europe',
    countryCode: 'EU',
    logo: '/leagues/champions-league.png',
    season: '2024/25',
    isActive: true,
    tier: 1
  }
];

// Mock Teams
export const mockTeams: Team[] = [
  {
    id: '1',
    name: 'Manchester City',
    logo: '/teams/manchester-city.png',
    country: 'England',
    leagueId: '1',
    form: 'WWWDW',
    position: 1,
    points: 28,
    goalsFor: 31,
    goalsAgainst: 9
  },
  {
    id: '2',
    name: 'Arsenal',
    logo: '/teams/arsenal.png',
    country: 'England',
    leagueId: '1',
    form: 'WWLWW',
    position: 2,
    points: 27,
    goalsFor: 29,
    goalsAgainst: 12
  },
  {
    id: '3',
    name: 'Liverpool',
    logo: '/teams/liverpool.png',
    country: 'England',
    leagueId: '1',
    form: 'WWWWL',
    position: 3,
    points: 25,
    goalsFor: 28,
    goalsAgainst: 11
  },
  {
    id: '4',
    name: 'Chelsea',
    logo: '/teams/chelsea.png',
    country: 'England',
    leagueId: '1',
    form: 'WLWDW',
    position: 4,
    points: 22,
    goalsFor: 24,
    goalsAgainst: 15
  },
  {
    id: '5',
    name: 'Real Madrid',
    logo: '/teams/real-madrid.png',
    country: 'Spain',
    leagueId: '2',
    form: 'WWWWW',
    position: 1,
    points: 30,
    goalsFor: 32,
    goalsAgainst: 8
  },
  {
    id: '6',
    name: 'Barcelona',
    logo: '/teams/barcelona.png',
    country: 'Spain',
    leagueId: '2',
    form: 'WWDWL',
    position: 2,
    points: 27,
    goalsFor: 28,
    goalsAgainst: 10
  }
];

// Mock Matches
export const mockMatches: Match[] = [
  {
    id: '1',
    homeTeam: mockTeams[0], // Manchester City
    awayTeam: mockTeams[1], // Arsenal
    league: mockLeagues[0], // Premier League
    dateTime: '2024-09-22T15:00:00Z',
    status: MatchStatus.SCHEDULED,
    venue: 'Etihad Stadium',
    referee: 'Anthony Taylor',
    odds: {
      home: 2.10,
      draw: 3.40,
      away: 3.20,
      overUnder25: { over: 1.85, under: 1.95 },
      bothTeamsToScore: { yes: 1.75, no: 2.05 }
    }
  },
  {
    id: '2',
    homeTeam: mockTeams[2], // Liverpool
    awayTeam: mockTeams[3], // Chelsea
    league: mockLeagues[0], // Premier League
    dateTime: '2024-09-22T17:30:00Z',
    status: MatchStatus.SCHEDULED,
    venue: 'Anfield',
    referee: 'Michael Oliver',
    odds: {
      home: 1.85,
      draw: 3.60,
      away: 4.20,
      overUnder25: { over: 1.90, under: 1.90 },
      bothTeamsToScore: { yes: 1.70, no: 2.15 }
    }
  },
  {
    id: '3',
    homeTeam: mockTeams[4], // Real Madrid
    awayTeam: mockTeams[5], // Barcelona
    league: mockLeagues[1], // La Liga
    dateTime: '2024-09-23T20:00:00Z',
    status: MatchStatus.SCHEDULED,
    venue: 'Santiago Bernabéu',
    referee: 'José María Sánchez',
    odds: {
      home: 2.45,
      draw: 3.30,
      away: 2.90,
      overUnder25: { over: 1.75, under: 2.05 },
      bothTeamsToScore: { yes: 1.65, no: 2.25 }
    }
  }
];

// Mock Predictions
export const mockPredictions: Prediction[] = [
  {
    id: '1',
    match: mockMatches[0],
    market: PredictionMarket.MATCH_RESULT,
    prediction: 'Manchester City Win',
    confidence: ConfidenceLevel.HIGH,
    accuracy: 89.9,
    analysis: {
      keyFactors: [
        'Manchester City excellent home record',
        'Arsenal defensive vulnerabilities',
        'Head-to-head advantage for City',
        'Recent form favors home team'
      ],
      headToHead: {
        totalMeetings: 20,
        homeWins: 8,
        draws: 4,
        awayWins: 8,
        lastMeeting: {
          date: '2024-04-15',
          result: 'Manchester City Win',
          score: '2-1'
        }
      },
      teamForm: {
        home: {
          last5Games: 'WWWDW',
          goalsScored: 12,
          goalsConceded: 3,
          cleanSheets: 3,
          winPercentage: 80,
          homeAwayForm: 'WWWWW'
        },
        away: {
          last5Games: 'WWLWW',
          goalsScored: 10,
          goalsConceded: 5,
          cleanSheets: 2,
          winPercentage: 80,
          homeAwayForm: 'WLWLW'
        }
      },
      injuries: [
        {
          player: 'Kevin De Bruyne',
          position: 'Midfielder',
          injuryType: 'Hamstring',
          expectedReturn: '2024-10-01',
          impact: 'medium'
        }
      ],
      expertTip: 'Manchester City\'s home advantage and superior squad depth should prove decisive in this top-of-the-table clash.'
    },
    status: PredictionStatus.PENDING,
    createdAt: '2024-09-21T10:00:00Z',
    updatedAt: '2024-09-21T10:00:00Z'
  },
  {
    id: '2',
    match: mockMatches[0],
    market: PredictionMarket.OVER_UNDER_25,
    prediction: 'Over 2.5 Goals',
    confidence: ConfidenceLevel.VERY_HIGH,
    accuracy: 92.3,
    analysis: {
      keyFactors: [
        'Both teams high-scoring attack',
        'Recent matches averaged 3.2 goals',
        'Defensive weaknesses on both sides',
        'Historical high-scoring encounters'
      ],
      headToHead: {
        totalMeetings: 20,
        homeWins: 8,
        draws: 4,
        awayWins: 8,
        lastMeeting: {
          date: '2024-04-15',
          result: 'Manchester City Win',
          score: '2-1'
        }
      },
      teamForm: {
        home: {
          last5Games: 'WWWDW',
          goalsScored: 12,
          goalsConceded: 3,
          cleanSheets: 3,
          winPercentage: 80
        },
        away: {
          last5Games: 'WWLWW',
          goalsScored: 10,
          goalsConceded: 5,
          cleanSheets: 2,
          winPercentage: 80
        }
      },
      injuries: [],
      expertTip: 'Both teams possess lethal attacking options and have shown defensive vulnerabilities recently.'
    },
    status: PredictionStatus.PENDING,
    createdAt: '2024-09-21T10:00:00Z',
    updatedAt: '2024-09-21T10:00:00Z'
  },
  {
    id: '3',
    match: mockMatches[1],
    market: PredictionMarket.BOTH_TEAMS_TO_SCORE,
    prediction: 'Yes',
    confidence: ConfidenceLevel.HIGH,
    accuracy: 87.5,
    analysis: {
      keyFactors: [
        'Liverpool strong attacking record at home',
        'Chelsea improved under new manager',
        'Both teams score regularly',
        'Open, attacking style expected'
      ],
      headToHead: {
        totalMeetings: 18,
        homeWins: 7,
        draws: 5,
        awayWins: 6,
        lastMeeting: {
          date: '2024-03-10',
          result: 'Liverpool Win',
          score: '3-1'
        }
      },
      teamForm: {
        home: {
          last5Games: 'WWWWL',
          goalsScored: 14,
          goalsConceded: 4,
          cleanSheets: 3,
          winPercentage: 80,
          homeAwayForm: 'WWWWW'
        },
        away: {
          last5Games: 'WLWDW',
          goalsScored: 8,
          goalsConceded: 6,
          cleanSheets: 2,
          winPercentage: 60,
          homeAwayForm: 'WLDWL'
        }
      },
      injuries: [
        {
          player: 'Diogo Jota',
          position: 'Forward',
          injuryType: 'Ankle',
          expectedReturn: '2024-09-28',
          impact: 'low'
        }
      ],
      expertTip: 'Liverpool\'s attacking prowess at Anfield combined with Chelsea\'s counter-attacking threat makes this a likely goal fest.'
    },
    status: PredictionStatus.PENDING,
    createdAt: '2024-09-21T10:00:00Z',
    updatedAt: '2024-09-21T10:00:00Z'
  }
];

// Mock Articles
export const mockArticles: Article[] = [
  {
    id: '1',
    title: 'Understanding Football Betting Odds: A Comprehensive Guide',
    slug: 'understanding-football-betting-odds-comprehensive-guide',
    excerpt: 'Learn how to read and interpret different types of betting odds to make more informed decisions.',
    content: `# Understanding Football Betting Odds: A Comprehensive Guide

Football betting odds are the foundation of successful sports betting. Understanding how they work, what they represent, and how to interpret them is crucial for any bettor looking to make informed decisions.

## Types of Betting Odds

### Decimal Odds
Decimal odds are the most common format used in Europe and are easy to understand. The number represents the total return you'll receive for every unit staked, including your original stake.

**Example:** If you see odds of 2.50, you'll receive $2.50 for every $1 wagered if your bet wins.

### Fractional Odds
Popular in the UK, fractional odds show the potential profit relative to your stake.

**Example:** Odds of 3/2 mean you'll win $3 for every $2 staked.

### American Odds
Used primarily in the United States, these odds are expressed as positive or negative numbers.

## How Bookmakers Set Odds

Bookmakers use complex algorithms and expert analysis to set odds that reflect:
- Team strengths and weaknesses
- Historical performance
- Current form
- Injuries and suspensions
- Weather conditions
- Public betting patterns

## Finding Value in Odds

Value betting is about finding odds that you believe are higher than the actual probability of an outcome occurring. This requires:
1. Deep knowledge of the sport
2. Statistical analysis
3. Understanding of market movements
4. Patience and discipline

Remember, successful betting is not about picking winners—it's about finding value in the odds offered.`,
    author: {
      name: 'John Smith',
      avatar: '/authors/john-smith.jpg',
      bio: 'Professional sports analyst with 10+ years experience in football betting markets.'
    },
    category: ArticleCategory.BEGINNER_GUIDE,
    tags: ['odds', 'betting basics', 'value betting'],
    publishedAt: '2024-09-20T10:00:00Z',
    readTime: 8,
    featuredImage: '/articles/betting-odds-guide.jpg',
    isFeature: true
  },
  {
    id: '2',
    title: 'Advanced Bankroll Management Strategies',
    slug: 'advanced-bankroll-management-strategies',
    excerpt: 'Master the art of bankroll management with proven strategies used by professional bettors.',
    content: `# Advanced Bankroll Management Strategies

Bankroll management is arguably the most important aspect of successful sports betting. Without proper management, even the best tipsters can go broke.

## The Kelly Criterion

The Kelly Criterion is a mathematical formula that helps determine the optimal bet size based on the perceived edge and odds.

**Formula:** f = (bp - q) / b

Where:
- f = fraction of bankroll to wager
- b = odds received on the wager
- p = probability of winning
- q = probability of losing (1 - p)

## Fixed Percentage Staking

A simpler approach where you bet a fixed percentage of your bankroll on each wager, typically 1-5%.

**Advantages:**
- Easy to implement
- Naturally adjusts bet sizes as bankroll grows/shrinks
- Reduces risk of ruin

## Unit System

Professional bettors often use a unit system where:
- 1 unit = 1% of bankroll
- Bet sizes range from 1-5 units based on confidence
- Tracks performance in units rather than monetary amounts

## Common Mistakes to Avoid

1. **Chasing losses** - Increasing bet sizes after losses
2. **Over-confidence** - Betting too much after wins
3. **No stop-loss** - Not having predetermined loss limits
4. **Emotional betting** - Making decisions based on feelings

Remember: The goal is long-term profitability, not quick riches.`,
    author: {
      name: 'Sarah Johnson',
      avatar: '/authors/sarah-johnson.jpg',
      bio: 'Former professional bettor turned educator, specializing in risk management and statistical analysis.'
    },
    category: ArticleCategory.BANKROLL_MANAGEMENT,
    tags: ['bankroll management', 'kelly criterion', 'staking plans'],
    publishedAt: '2024-09-19T14:30:00Z',
    readTime: 12,
    featuredImage: '/articles/bankroll-management.jpg',
    isFeature: false
  },
  {
    id: '3',
    title: 'Reading Team Form: Beyond Win/Loss Records',
    slug: 'reading-team-form-beyond-win-loss-records',
    excerpt: 'Discover how to analyze team form using advanced metrics and contextual factors.',
    content: `# Reading Team Form: Beyond Win/Loss Records

While win/loss records provide a basic overview of team performance, successful bettors dig deeper to understand the true form of a team.

## Advanced Form Metrics

### Expected Goals (xG)
xG measures the quality of chances created and conceded, providing insight into underlying performance.

### Shot Conversion Rates
How efficiently teams convert chances into goals can indicate if current form is sustainable.

### Defensive Solidity
- Clean sheets percentage
- Goals conceded per game
- Shots allowed per game

## Contextual Factors

### Strength of Opposition
A team's recent results must be viewed in context of the opposition faced.

### Home vs Away Form
Many teams perform significantly differently at home versus away.

### Injury Impact
Key player injuries can dramatically affect team performance.

### Tactical Changes
New formations or playing styles can take time to implement effectively.

## Practical Application

When analyzing form:
1. Look at the last 6-8 games
2. Consider the quality of opposition
3. Check for any significant changes in personnel
4. Analyze underlying statistics, not just results
5. Consider external factors (weather, travel, etc.)

Remember: Form is temporary, but class is permanent. Look for value when good teams hit temporary rough patches.`,
    author: {
      name: 'Michael Chen',
      avatar: '/authors/michael-chen.jpg',
      bio: 'Data scientist and football analyst with expertise in predictive modeling and team performance metrics.'
    },
    category: ArticleCategory.MARKET_ANALYSIS,
    tags: ['team form', 'xG', 'statistical analysis'],
    publishedAt: '2024-09-18T09:15:00Z',
    readTime: 10,
    featuredImage: '/articles/team-form-analysis.jpg',
    isFeature: false
  }
];

// Mock Accuracy Stats
export const mockAccuracyStats: AccuracyStats = {
  overall: 89.9,
  byMarket: {
    [PredictionMarket.MATCH_RESULT]: 87.5,
    [PredictionMarket.OVER_UNDER_25]: 92.3,
    [PredictionMarket.BOTH_TEAMS_TO_SCORE]: 88.7,
    [PredictionMarket.CORRECT_SCORE]: 78.9,
    [PredictionMarket.DOUBLE_CHANCE]: 91.2,
    [PredictionMarket.FIRST_HALF_RESULT]: 85.4,
    [PredictionMarket.TOTAL_GOALS]: 89.1,
    [PredictionMarket.ASIAN_HANDICAP]: 86.8
  },
  byLeague: {
    'Premier League': 91.2,
    'La Liga': 88.7,
    'Serie A': 87.9,
    'Bundesliga': 90.1,
    'Ligue 1': 89.5,
    'Champions League': 92.8
  },
  byConfidence: {
    [ConfidenceLevel.LOW]: 76.5,
    [ConfidenceLevel.MEDIUM]: 84.2,
    [ConfidenceLevel.HIGH]: 89.9,
    [ConfidenceLevel.VERY_HIGH]: 94.7
  },
  last30Days: 91.2,
  last7Days: 93.5,
  trend: 'up'
};

// Mock Dashboard Stats
export const mockDashboardStats: DashboardStats = {
  totalPredictions: 1847,
  correctPredictions: 1661,
  accuracy: mockAccuracyStats,
  todaysPredictions: 12,
  activeBets: 8,
  profit: 2847.50,
  roi: 23.8
};