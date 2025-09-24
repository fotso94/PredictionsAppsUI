import React, { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import Header from './Header';
import Footer from './Footer';
import { LoadingOverlay } from '../ui/LoadingSpinner';

interface LayoutProps {
  title?: string;
  description?: string;
  keywords?: string;
  children?: React.ReactNode;
  loading?: boolean;
  user?: any;
  onLogin?: () => void;
  onLogout?: () => void;
}

const Layout: React.FC<LayoutProps> = ({
  title = 'PredictionsApp - Soccer Predictions & Betting Tips',
  description = 'Get accurate soccer predictions, betting tips, and match analysis. Join thousands of successful bettors with our expert insights.',
  keywords = 'soccer predictions, football betting, betting tips, match analysis, sports betting',
  children,
  loading = false,
  user,
  onLogin,
  onLogout,
}) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Close mobile menu on route change
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, []);

  // Prevent scroll when mobile menu is open
  useEffect(() => {
    if (isMobileMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }

    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isMobileMenuOpen]);

  const handleToggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen);
  };

  return (
    <>
      <Helmet>
        <title>{title}</title>
        <meta name="description" content={description} />
        <meta name="keywords" content={keywords} />
        <meta property="og:title" content={title} />
        <meta property="og:description" content={description} />
        <meta property="og:type" content="website" />
        <meta property="og:image" content="/images/og-image.png" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={title} />
        <meta name="twitter:description" content={description} />
        <meta name="twitter:image" content="/images/twitter-image.png" />
        <link rel="canonical" href={window.location.href} />
      </Helmet>

      <div className="min-h-screen bg-dark-900 text-white flex flex-col">
        {/* Header */}
        <Header
          user={user}
          onLogin={onLogin}
          onLogout={onLogout}
          onToggleMobileMenu={handleToggleMobileMenu}
          isMobileMenuOpen={isMobileMenuOpen}
        />

        {/* Main Content */}
        <main className="flex-1">
          <LoadingOverlay isLoading={loading}>
            {children || <Outlet />}
          </LoadingOverlay>
        </main>

        {/* Footer */}
        <Footer />
      </div>
    </>
  );
};

export default Layout;
