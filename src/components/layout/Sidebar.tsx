import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { clsx } from 'clsx';
import {
  HomeIcon,
  ChartBarIcon,
  TrophyIcon,
  CalendarDaysIcon,
  UserGroupIcon,
  Cog6ToothIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
  className?: string;
}

const Sidebar: React.FC<SidebarProps> = ({
  isOpen = true,
  onClose,
  className,
}) => {
  const location = useLocation();

  const sidebarItems = [
    {
      name: 'Dashboard',
      href: '/dashboard',
      icon: HomeIcon,
      description: 'Overview and stats',
    },
    {
      name: 'Predictions',
      href: '/predictions',
      icon: TrophyIcon,
      description: 'Today\'s picks',
      badge: '12',
    },
    {
      name: 'Matches',
      href: '/matches',
      icon: CalendarDaysIcon,
      description: 'Upcoming games',
    },
    {
      name: 'Leagues',
      href: '/leagues',
      icon: UserGroupIcon,
      description: 'All competitions',
    },
    {
      name: 'Statistics',
      href: '/statistics',
      icon: ChartBarIcon,
      description: 'Performance data',
    },
    {
      name: 'Settings',
      href: '/settings',
      icon: Cog6ToothIcon,
      description: 'Preferences',
    },
    {
      name: 'Help',
      href: '/help',
      icon: QuestionMarkCircleIcon,
      description: 'Support center',
    },
  ];

  const isActiveLink = (href: string) => {
    if (href === '/dashboard') {
      return location.pathname === '/dashboard';
    }
    return location.pathname.startsWith(href);
  };

  return (
    <>
      {/* Overlay for mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={clsx(
          'fixed top-0 left-0 z-50 h-full bg-dark-800 border-r border-dark-700 transition-transform duration-300 ease-in-out',
          'lg:translate-x-0 lg:static lg:z-auto',
          isOpen ? 'translate-x-0' : '-translate-x-full',
          'w-64',
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-dark-700">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-gradient-to-r from-primary-500 to-success-500 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-lg">P</span>
            </div>
            <span className="text-lg font-bold gradient-text">
              PredictionsApp
            </span>
          </div>
          
          {/* Close button for mobile */}
          <button
            onClick={onClose}
            className="lg:hidden p-1 text-dark-400 hover:text-white transition-colors duration-200"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
          <ul className="space-y-2">
            {sidebarItems.map((item) => {
              const Icon = item.icon;
              const isActive = isActiveLink(item.href);

              return (
                <li key={item.name}>
                  <Link
                    to={item.href}
                    onClick={onClose}
                    className={clsx(
                      'flex items-center p-3 rounded-lg transition-all duration-200 group',
                      isActive
                        ? 'bg-primary-600/20 text-primary-400 border border-primary-600/30'
                        : 'text-dark-300 hover:text-white hover:bg-dark-700'
                    )}
                  >
                    <Icon className={clsx(
                      'w-5 h-5 mr-3 transition-colors duration-200',
                      isActive ? 'text-primary-400' : 'text-dark-400 group-hover:text-white'
                    )} />
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="font-medium truncate">
                          {item.name}
                        </span>
                        {item.badge && (
                          <span className="ml-2 px-2 py-0.5 text-xs bg-primary-600 text-white rounded-full">
                            {item.badge}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-dark-500 truncate">
                        {item.description}
                      </p>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-dark-700">
          <div className="bg-gradient-to-r from-primary-600/20 to-success-600/20 border border-primary-600/30 rounded-lg p-3">
            <div className="flex items-center space-x-2 mb-2">
              <TrophyIcon className="w-5 h-5 text-primary-400" />
              <span className="text-sm font-medium text-white">Pro Tips</span>
            </div>
            <p className="text-xs text-dark-300 mb-3">
              Upgrade to get premium predictions and advanced analytics.
            </p>
            <Link
              to="/upgrade"
              className="block w-full text-center py-2 px-3 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-md transition-colors duration-200"
            >
              Upgrade Now
            </Link>
          </div>
        </div>
      </aside>
    </>
  );
};

export default Sidebar;
