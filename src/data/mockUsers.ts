import type { User } from '../types';

export const mockUser: User = {
  id: 'user-1',
  username: 'soccerfan2024',
  email: 'john.doe@example.com',
  firstName: 'John',
  lastName: 'Doe',
  avatar: '/images/avatars/user-1.jpg',
  role: 'premium',
  subscription: 'premium',
  preferences: {
    favoriteTeams: ['team-1', 'team-3', 'team-6'], // Man United, Liverpool, Real Madrid
    favoriteLeagues: ['league-1', 'league-2', 'league-6'], // Premier League, La Liga, Champions League
    notifications: {
      email: true,
      push: true,
      predictions: true,
      results: true,
    },
    timezone: 'Europe/London',
    language: 'en',
    currency: 'GBP',
  },
  stats: {
    totalPredictions: 156,
    correctPredictions: 98,
    accuracy: 62.8,
    profit: 1250.50,
    roi: 15.2,
    streak: {
      current: 5,
      best: 12,
      type: 'win',
    },
    monthlyStats: [
      {
        month: '2025-01',
        predictions: 45,
        correct: 28,
        accuracy: 62.2,
        profit: 320.75,
      },
      {
        month: '2025-02',
        predictions: 38,
        correct: 25,
        accuracy: 65.8,
        profit: 285.25,
      },
      {
        month: '2025-03',
        predictions: 42,
        correct: 26,
        accuracy: 61.9,
        profit: 195.50,
      },
      {
        month: '2025-04',
        predictions: 31,
        correct: 19,
        accuracy: 61.3,
        profit: 449.00,
      },
    ],
  },
  createdAt: '2024-08-15T10:30:00Z',
  lastLogin: '2025-09-22T14:25:00Z',
};

export const mockUsers: User[] = [
  mockUser,
  {
    id: 'user-2',
    username: 'predictionmaster',
    email: 'sarah.smith@example.com',
    firstName: 'Sarah',
    lastName: 'Smith',
    avatar: '/images/avatars/user-2.jpg',
    role: 'vip',
    subscription: 'vip',
    preferences: {
      favoriteTeams: ['team-2', 'team-7', 'team-8'], // Man City, Barcelona, Bayern
      favoriteLeagues: ['league-1', 'league-3', 'league-6'], // Premier League, Bundesliga, Champions League
      notifications: {
        email: true,
        push: false,
        predictions: true,
        results: true,
      },
      timezone: 'America/New_York',
      language: 'en',
      currency: 'USD',
    },
    stats: {
      totalPredictions: 289,
      correctPredictions: 195,
      accuracy: 67.5,
      profit: 2850.75,
      roi: 22.8,
      streak: {
        current: 8,
        best: 15,
        type: 'win',
      },
      monthlyStats: [
        {
          month: '2025-01',
          predictions: 72,
          correct: 48,
          accuracy: 66.7,
          profit: 680.25,
        },
        {
          month: '2025-02',
          predictions: 68,
          correct: 47,
          accuracy: 69.1,
          profit: 745.50,
        },
        {
          month: '2025-03',
          predictions: 75,
          correct: 50,
          accuracy: 66.7,
          profit: 825.00,
        },
        {
          month: '2025-04',
          predictions: 74,
          correct: 50,
          accuracy: 67.6,
          profit: 600.00,
        },
      ],
    },
    createdAt: '2024-06-10T08:15:00Z',
    lastLogin: '2025-09-22T16:45:00Z',
  },
  {
    id: 'user-3',
    username: 'footballanalyst',
    email: 'mike.johnson@example.com',
    firstName: 'Mike',
    lastName: 'Johnson',
    avatar: '/images/avatars/user-3.jpg',
    role: 'user',
    subscription: 'basic',
    preferences: {
      favoriteTeams: ['team-4', 'team-5'], // Arsenal, Chelsea
      favoriteLeagues: ['league-1'], // Premier League
      notifications: {
        email: false,
        push: true,
        predictions: false,
        results: true,
      },
      timezone: 'Europe/London',
      language: 'en',
      currency: 'GBP',
    },
    stats: {
      totalPredictions: 87,
      correctPredictions: 48,
      accuracy: 55.2,
      profit: 125.25,
      roi: 8.5,
      streak: {
        current: 2,
        best: 7,
        type: 'win',
      },
      monthlyStats: [
        {
          month: '2025-01',
          predictions: 22,
          correct: 12,
          accuracy: 54.5,
          profit: 45.75,
        },
        {
          month: '2025-02',
          predictions: 25,
          correct: 15,
          accuracy: 60.0,
          profit: 85.50,
        },
        {
          month: '2025-03',
          predictions: 20,
          correct: 10,
          accuracy: 50.0,
          profit: -25.00,
        },
        {
          month: '2025-04',
          predictions: 20,
          correct: 11,
          accuracy: 55.0,
          profit: 19.00,
        },
      ],
    },
    createdAt: '2024-12-01T12:00:00Z',
    lastLogin: '2025-09-22T09:30:00Z',
  },
];
