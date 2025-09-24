
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import Layout from './components/layout/Layout';
import ErrorBoundary from './components/error/ErrorBoundary';
import HomePage from './pages/HomePage';
import PredictionsPage from './pages/PredictionsPage';
import MatchDetailsPage from './pages/MatchDetailsPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import LeaguePage from './pages/LeaguePage';

function App() {
  return (
    <ErrorBoundary>
      <HelmetProvider>
        <Router>
          <Routes>
            {/* Public Routes */}
            <Route path="/" element={<Layout><HomePage /></Layout>} />
            <Route path="/predictions" element={<Layout><PredictionsPage /></Layout>} />
            <Route path="/predictions/:tab" element={<Layout><PredictionsPage /></Layout>} />
            <Route path="/match/:matchId" element={<Layout><MatchDetailsPage /></Layout>} />
            <Route path="/league/:leagueId" element={<Layout><LeaguePage /></Layout>} />

            {/* Auth Routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            {/* Protected Routes */}
            <Route path="/dashboard" element={<Layout><DashboardPage /></Layout>} />

            {/* 404 Route */}
            <Route path="*" element={
              <Layout>
                <div className="min-h-screen bg-dark-900 flex items-center justify-center">
                  <div className="text-center">
                    <div className="text-6xl mb-4">⚽</div>
                    <h1 className="text-2xl font-bold text-white mb-2">Page Not Found</h1>
                    <p className="text-dark-400">The page you're looking for doesn't exist.</p>
                  </div>
                </div>
              </Layout>
            } />
          </Routes>
        </Router>
      </HelmetProvider>
    </ErrorBoundary>
  );
}

export default App;
