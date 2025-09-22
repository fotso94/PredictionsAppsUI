import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import TodayPredictionsPage from './pages/TodayPredictionsPage';
import TomorrowPredictionsPage from './pages/TomorrowPredictionsPage';
import LeaguesPage from './pages/LeaguesPage';
import LeagueDetailPage from './pages/LeagueDetailPage';
import MatchDetailPage from './pages/MatchDetailPage';
import BettingAcademyPage from './pages/BettingAcademyPage';
import ArticlePage from './pages/ArticlePage';
import StatisticsPage from './pages/StatisticsPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import NotFoundPage from './pages/NotFoundPage';

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          {/* Main Pages */}
          <Route path="/" element={<HomePage />} />
          <Route path="/predictions/today" element={<TodayPredictionsPage />} />
          <Route path="/predictions/tomorrow" element={<TomorrowPredictionsPage />} />

          {/* League Pages */}
          <Route path="/leagues" element={<LeaguesPage />} />
          <Route path="/leagues/:leagueSlug" element={<LeagueDetailPage />} />

          {/* Match Pages */}
          <Route path="/matches/:matchId" element={<MatchDetailPage />} />

          {/* Education */}
          <Route path="/academy" element={<BettingAcademyPage />} />
          <Route path="/academy/:articleSlug" element={<ArticlePage />} />

          {/* Statistics */}
          <Route path="/statistics" element={<StatisticsPage />} />

          {/* Authentication */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* User Dashboard */}
          <Route path="/dashboard" element={<DashboardPage />} />

          {/* 404 Page */}
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;