import React from 'react';
import { Link } from 'react-router-dom';
import {
  EnvelopeIcon,
  PhoneIcon,
  MapPinIcon,
} from '@heroicons/react/24/outline';

const Footer: React.FC = () => {
  const currentYear = new Date().getFullYear();

  const footerLinks = {
    predictions: [
      { name: 'Today\'s Predictions', href: '/predictions/today' },
      { name: 'Tomorrow\'s Predictions', href: '/predictions/tomorrow' },
      { name: 'Weekend Predictions', href: '/predictions/weekend' },
      { name: 'All Predictions', href: '/predictions' },
    ],
    leagues: [
      { name: 'Premier League', href: '/leagues/premier-league' },
      { name: 'Champions League', href: '/leagues/champions-league' },
      { name: 'La Liga', href: '/leagues/la-liga' },
      { name: 'Bundesliga', href: '/leagues/bundesliga' },
    ],
    company: [
      { name: 'About Us', href: '/about' },
      { name: 'Contact', href: '/contact' },
      { name: 'Privacy Policy', href: '/privacy' },
      { name: 'Terms of Service', href: '/terms' },
    ],
    support: [
      { name: 'Help Center', href: '/help' },
      { name: 'FAQ', href: '/faq' },
      { name: 'Betting Guide', href: '/guide' },
      { name: 'Responsible Gambling', href: '/responsible-gambling' },
    ],
  };

  const socialLinks = [
    { name: 'Twitter', href: '#', icon: '𝕏' },
    { name: 'Facebook', href: '#', icon: 'f' },
    { name: 'Instagram', href: '#', icon: '📷' },
    { name: 'Telegram', href: '#', icon: '✈️' },
  ];

  return (
    <footer className="bg-dark-900 border-t border-dark-700">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Main Footer Content */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-8">
          {/* Brand Section */}
          <div className="lg:col-span-1">
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-8 h-8 bg-gradient-to-r from-primary-500 to-success-500 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-lg">P</span>
              </div>
              <span className="text-xl font-bold gradient-text">
                PredictionsApp
              </span>
            </div>
            <p className="text-dark-400 text-sm mb-4">
              Your trusted source for accurate soccer predictions and betting insights. 
              Join thousands of successful bettors who rely on our expert analysis.
            </p>
            <div className="flex space-x-3">
              {socialLinks.map((social) => (
                <a
                  key={social.name}
                  href={social.href}
                  className="w-8 h-8 bg-dark-800 rounded-lg flex items-center justify-center text-dark-400 hover:text-white hover:bg-primary-600 transition-colors duration-200"
                  aria-label={social.name}
                >
                  {social.icon}
                </a>
              ))}
            </div>
          </div>

          {/* Predictions Links */}
          <div>
            <h3 className="text-white font-semibold mb-4">Predictions</h3>
            <ul className="space-y-2">
              {footerLinks.predictions.map((link) => (
                <li key={link.name}>
                  <Link
                    to={link.href}
                    className="text-dark-400 hover:text-white transition-colors duration-200 text-sm"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Leagues Links */}
          <div>
            <h3 className="text-white font-semibold mb-4">Leagues</h3>
            <ul className="space-y-2">
              {footerLinks.leagues.map((link) => (
                <li key={link.name}>
                  <Link
                    to={link.href}
                    className="text-dark-400 hover:text-white transition-colors duration-200 text-sm"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Company Links */}
          <div>
            <h3 className="text-white font-semibold mb-4">Company</h3>
            <ul className="space-y-2">
              {footerLinks.company.map((link) => (
                <li key={link.name}>
                  <Link
                    to={link.href}
                    className="text-dark-400 hover:text-white transition-colors duration-200 text-sm"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Support & Contact */}
          <div>
            <h3 className="text-white font-semibold mb-4">Support</h3>
            <ul className="space-y-2 mb-4">
              {footerLinks.support.map((link) => (
                <li key={link.name}>
                  <Link
                    to={link.href}
                    className="text-dark-400 hover:text-white transition-colors duration-200 text-sm"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
            
            {/* Contact Info */}
            <div className="space-y-2">
              <div className="flex items-center space-x-2 text-sm text-dark-400">
                <EnvelopeIcon className="w-4 h-4" />
                <span>support@predictionsapp.com</span>
              </div>
              <div className="flex items-center space-x-2 text-sm text-dark-400">
                <PhoneIcon className="w-4 h-4" />
                <span>+1 (555) 123-4567</span>
              </div>
              <div className="flex items-center space-x-2 text-sm text-dark-400">
                <MapPinIcon className="w-4 h-4" />
                <span>New York, NY</span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Section */}
        <div className="mt-8 pt-8 border-t border-dark-700">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <div className="text-dark-400 text-sm mb-4 md:mb-0">
              © {currentYear} PredictionsApp. All rights reserved.
            </div>
            <div className="flex items-center space-x-6 text-sm text-dark-400">
              <Link to="/privacy" className="hover:text-white transition-colors duration-200">
                Privacy Policy
              </Link>
              <Link to="/terms" className="hover:text-white transition-colors duration-200">
                Terms of Service
              </Link>
              <Link to="/cookies" className="hover:text-white transition-colors duration-200">
                Cookie Policy
              </Link>
            </div>
          </div>
          
          {/* Disclaimer */}
          <div className="mt-4 text-xs text-dark-500 text-center">
            <p>
              Gambling can be addictive. Please play responsibly. 
              This website is for entertainment purposes only and does not guarantee winnings.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
