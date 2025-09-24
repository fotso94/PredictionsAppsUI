import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { clsx } from 'clsx';
import {
  Bars3Icon,
  XMarkIcon,
  ChevronDownIcon,
  UserIcon,
  BellIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
} from '@heroicons/react/24/outline';
import type { NavItem } from '../../types';
import Button from '../ui/Button';
import Badge from '../ui/Badge';

interface HeaderProps {
  user?: any;
  onLogin?: () => void;
  onLogout?: () => void;
  onToggleMobileMenu?: () => void;
  isMobileMenuOpen?: boolean;
}

const Header: React.FC<HeaderProps> = ({
  user,
  onLogin,
  onLogout,
  onToggleMobileMenu,
  isMobileMenuOpen = false,
}) => {
  const location = useLocation();
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);

  const navigationItems: NavItem[] = [
    { name: 'Home', href: '/' },
    { 
      name: 'Predictions', 
      href: '/predictions',
      children: [
        { name: 'Today', href: '/predictions/today' },
        { name: 'Tomorrow', href: '/predictions/tomorrow' },
        { name: 'All Predictions', href: '/predictions' },
        { name: 'By League', href: '/predictions/leagues' },
      ]
    },
    { 
      name: 'Leagues', 
      href: '/leagues',
      children: [
        { name: 'Premier League', href: '/leagues/premier-league' },
        { name: 'Champions League', href: '/leagues/champions-league' },
        { name: 'La Liga', href: '/leagues/la-liga' },
        { name: 'All Leagues', href: '/leagues' },
      ]
    },
    { name: 'Statistics', href: '/statistics' },
    { name: 'About', href: '/about' },
  ];

  const userMenuItems = [
    { value: 'profile', label: 'Profile', icon: <UserIcon className="w-4 h-4" /> },
    { value: 'settings', label: 'Settings', icon: <Cog6ToothIcon className="w-4 h-4" /> },
    { value: 'logout', label: 'Logout', icon: <ArrowRightOnRectangleIcon className="w-4 h-4" /> },
  ];

  const handleUserMenuSelect = (value: string) => {
    switch (value) {
      case 'logout':
        onLogout?.();
        break;
      case 'profile':
        // Navigate to profile
        break;
      case 'settings':
        // Navigate to settings
        break;
    }
    setIsUserMenuOpen(false);
  };

  const isActiveLink = (href: string) => {
    if (href === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(href);
  };

  return (
    <header className="sticky top-0 z-50 bg-dark-900/95 backdrop-blur-sm border-b border-dark-700">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center">
            <Link to="/" className="flex items-center space-x-2">
              <div className="w-8 h-8 bg-gradient-to-r from-primary-500 to-success-500 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-lg">P</span>
              </div>
              <span className="text-xl font-bold gradient-text">
                PredictionsApp
              </span>
            </Link>
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center space-x-8">
            {navigationItems.map((item) => (
              <div key={item.name} className="relative group">
                <Link
                  to={item.href}
                  className={clsx(
                    'px-3 py-2 text-sm font-medium transition-colors duration-200 flex items-center space-x-1',
                    isActiveLink(item.href)
                      ? 'text-primary-400'
                      : 'text-dark-300 hover:text-white'
                  )}
                >
                  <span>{item.name}</span>
                  {item.children && (
                    <ChevronDownIcon className="w-4 h-4" />
                  )}
                </Link>

                {/* Dropdown Menu */}
                {item.children && (
                  <div className="absolute top-full left-0 mt-1 w-48 bg-dark-800 border border-dark-700 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200">
                    <div className="py-1">
                      {item.children.map((child) => (
                        <Link
                          key={child.name}
                          to={child.href}
                          className="block px-4 py-2 text-sm text-dark-300 hover:text-white hover:bg-dark-700 transition-colors duration-200"
                        >
                          {child.name}
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </nav>

          {/* Right Side */}
          <div className="flex items-center space-x-4">
            {user ? (
              <>
                {/* Notifications */}
                <button className="relative p-2 text-dark-400 hover:text-white transition-colors duration-200">
                  <BellIcon className="w-6 h-6" />
                  <Badge 
                    variant="danger" 
                    size="sm" 
                    className="absolute -top-1 -right-1 min-w-[1.25rem] h-5 flex items-center justify-center text-xs"
                  >
                    3
                  </Badge>
                </button>

                {/* User Menu */}
                <div className="relative">
                  <button
                    onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                    className="flex items-center space-x-2 p-2 rounded-lg hover:bg-dark-800 transition-colors duration-200"
                  >
                    <img
                      src={user.avatar || '/images/default-avatar.png'}
                      alt={user.firstName}
                      className="w-8 h-8 rounded-full"
                    />
                    <span className="hidden sm:block text-white">
                      {user.firstName}
                    </span>
                    <ChevronDownIcon className="w-4 h-4 text-dark-400" />
                  </button>

                  {/* User Dropdown */}
                  {isUserMenuOpen && (
                    <div className="absolute right-0 top-full mt-1 w-48 bg-dark-800 border border-dark-700 rounded-lg shadow-lg">
                      <div className="py-1">
                        {userMenuItems.map((item) => (
                          <button
                            key={item.value}
                            onClick={() => handleUserMenuSelect(item.value)}
                            className="flex items-center w-full px-4 py-2 text-sm text-dark-300 hover:text-white hover:bg-dark-700 transition-colors duration-200"
                          >
                            <span className="mr-2">{item.icon}</span>
                            {item.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex items-center space-x-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onLogin}
                >
                  Login
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={onLogin}
                >
                  Sign Up
                </Button>
              </div>
            )}

            {/* Mobile Menu Button */}
            <button
              onClick={onToggleMobileMenu}
              className="md:hidden p-2 text-dark-400 hover:text-white transition-colors duration-200"
            >
              {isMobileMenuOpen ? (
                <XMarkIcon className="w-6 h-6" />
              ) : (
                <Bars3Icon className="w-6 h-6" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu */}
      {isMobileMenuOpen && (
        <div className="md:hidden border-t border-dark-700 bg-dark-900">
          <div className="px-4 py-2 space-y-1">
            {navigationItems.map((item) => (
              <div key={item.name}>
                <Link
                  to={item.href}
                  className={clsx(
                    'block px-3 py-2 text-base font-medium transition-colors duration-200',
                    isActiveLink(item.href)
                      ? 'text-primary-400 bg-primary-600/10'
                      : 'text-dark-300 hover:text-white hover:bg-dark-800'
                  )}
                  onClick={onToggleMobileMenu}
                >
                  {item.name}
                </Link>
                {item.children && (
                  <div className="ml-4 space-y-1">
                    {item.children.map((child) => (
                      <Link
                        key={child.name}
                        to={child.href}
                        className="block px-3 py-2 text-sm text-dark-400 hover:text-white hover:bg-dark-800 transition-colors duration-200"
                        onClick={onToggleMobileMenu}
                      >
                        {child.name}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </header>
  );
};

export default Header;
