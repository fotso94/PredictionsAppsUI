import React from 'react';
import { Helmet } from 'react-helmet-async';
import HeroSection from '../components/home/HeroSection';
import FeaturedPredictions from '../components/home/FeaturedPredictions';
import StatisticsShowcase from '../components/home/StatisticsShowcase';
import FeaturesSection from '../components/home/FeaturesSection';
import TodaysMatches from '../components/home/TodaysMatches';

const HomePage: React.FC = () => {
  return (
    <>
      <Helmet>
        <title>PredictionsApp - Expert Soccer Predictions & Betting Tips</title>
        <meta 
          name="description" 
          content="Get accurate soccer predictions with 68.5% win rate. Expert analysis, real-time updates, and proven betting strategies. Join 12K+ successful bettors today!" 
        />
        <meta 
          name="keywords" 
          content="soccer predictions, football betting tips, match analysis, betting strategies, sports predictions, football tips, soccer betting" 
        />
        <meta property="og:title" content="PredictionsApp - Expert Soccer Predictions & Betting Tips" />
        <meta 
          property="og:description" 
          content="Join thousands of successful bettors with our AI-powered soccer predictions. 68.5% accuracy rate and transparent results tracking." 
        />
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://predictionsapp.com" />
        <meta property="og:image" content="https://predictionsapp.com/images/og-homepage.png" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="PredictionsApp - Expert Soccer Predictions" />
        <meta 
          name="twitter:description" 
          content="AI-powered soccer predictions with 68.5% accuracy. Join 12K+ successful bettors today!" 
        />
        <meta name="twitter:image" content="https://predictionsapp.com/images/twitter-homepage.png" />
        <link rel="canonical" href="https://predictionsapp.com" />
        
        {/* Structured Data */}
        <script type="application/ld+json">
          {JSON.stringify({
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "PredictionsApp",
            "description": "Expert soccer predictions and betting tips with proven accuracy",
            "url": "https://predictionsapp.com",
            "potentialAction": {
              "@type": "SearchAction",
              "target": "https://predictionsapp.com/search?q={search_term_string}",
              "query-input": "required name=search_term_string"
            },
            "publisher": {
              "@type": "Organization",
              "name": "PredictionsApp",
              "logo": {
                "@type": "ImageObject",
                "url": "https://predictionsapp.com/images/logo.png"
              }
            }
          })}
        </script>
      </Helmet>

      <div className="min-h-screen">
        {/* Hero Section */}
        <HeroSection />

        {/* Featured Predictions */}
        <FeaturedPredictions />

        {/* Today's Matches */}
        <TodaysMatches />

        {/* Statistics Showcase */}
        <StatisticsShowcase />

        {/* Features Section */}
        <FeaturesSection />
      </div>
    </>
  );
};

export default HomePage;
