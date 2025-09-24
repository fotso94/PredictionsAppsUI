import React, { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { 
  Bars3Icon, 
  XMarkIcon, 
  MagnifyingGlassIcon,
  UserCircleIcon,
  ChevronDownIcon
} from '@heroicons/react/24/outline'
import { Menu, Transition } from '@headlessui/react'
import { Fragment } from 'react'
import clsx from 'clsx'
import { NavItem } from '@/types'

const navigation: NavItem[] = [
  { name: 'Home', href: '/' },
  { name: 'Today', href: '/predictions/today' },
  { name: 'Tomorrow', href: '/predictions/tomorrow' },
  { name: 'Leagues', href: '/leagues' },
  { name: 'Dashboard', href: '/dashboard' },
]

const Header: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const location = useLocation()

  const isActive = (href: string) => {
    if (href === '/') {
      return location.pathname === '/'
    }
    return location.pathname.startsWith(href)
  }

  return (
    <header className="sticky top-0 z-50 bg-dark-900/95 backdrop-blur-sm border-b border-dark-700">
      <nav className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8" aria-label="Top">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <div className="flex items-center">
            <Link to="/" className="flex items-center space-x-2">
              <div className="h-8 w-8 rounded-lg bg-gradient-to-r from-primary-500 to-primary-600 flex items-center justify-center">
                <span className="text-white font-bold text-lg">SP</span>
              </div>
              <span className="text-xl font-bold text-white">Soccer Predictions</span>
            </Link>
          </div>

          {/* Desktop Navigation */}
          <div className="hidden md:flex md:items-center md:space-x-8">
            {navigation.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                className={clsx(
                  'px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                  isActive(item.href)
                    ? 'bg-primary-900 text-primary-300'
                    : 'text-secondary-300 hover:text-white hover:bg-dark-800'
                )}
              >
                {item.name}
              </Link>
            ))}
          </div>

          {/* Search and User Menu */}
          <div className="flex items-center space-x-4">
            {/* Search */}
            <div className="hidden sm:block">
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                  <MagnifyingGlassIcon className="h-5 w-5 text-secondary-400" aria-hidden="true" />
                </div>
                <input
                  type="text"
                  placeholder="Search teams, leagues..."
                  className="block w-full rounded-lg border-0 bg-dark-800 py-2 pl-10 pr-3 text-white placeholder:text-secondary-400 focus:ring-2 focus:ring-primary-500 sm:text-sm"
                />
              </div>
            </div>

            {/* User Menu */}
            <Menu as="div" className="relative">
              <div>
                <Menu.Button className="flex items-center space-x-2 rounded-lg bg-dark-800 px-3 py-2 text-sm font-medium text-white hover:bg-dark-700 transition-colors">
                  <UserCircleIcon className="h-6 w-6" />
                  <span className="hidden sm:block">Account</span>
                  <ChevronDownIcon className="h-4 w-4" />
                </Menu.Button>
              </div>
              <Transition
                as={Fragment}
                enter="transition ease-out duration-100"
                enterFrom="transform opacity-0 scale-95"
                enterTo="transform opacity-100 scale-100"
                leave="transition ease-in duration-75"
                leaveFrom="transform opacity-100 scale-100"
                leaveTo="transform opacity-0 scale-95"
              >
                <Menu.Items className="absolute right-0 z-10 mt-2 w-48 origin-top-right rounded-lg bg-dark-800 py-1 shadow-lg ring-1 ring-dark-700 focus:outline-none">
                  <Menu.Item>
                    {({ active }) => (
                      <Link
                        to="/dashboard"
                        className={clsx(
                          active ? 'bg-dark-700' : '',
                          'block px-4 py-2 text-sm text-white'
                        )}
                      >
                        Dashboard
                      </Link>
                    )}
                  </Menu.Item>
                  <Menu.Item>
                    {({ active }) => (
                      <Link
                        to="/login"
                        className={clsx(
                          active ? 'bg-dark-700' : '',
                          'block px-4 py-2 text-sm text-white'
                        )}
                      >
                        Sign In
                      </Link>
                    )}
                  </Menu.Item>
                  <Menu.Item>
                    {({ active }) => (
                      <Link
                        to="/register"
                        className={clsx(
                          active ? 'bg-dark-700' : '',
                          'block px-4 py-2 text-sm text-white'
                        )}
                      >
                        Sign Up
                      </Link>
                    )}
                  </Menu.Item>
                </Menu.Items>
              </Transition>
            </Menu>

            {/* Mobile menu button */}
            <div className="md:hidden">
              <button
                type="button"
                className="rounded-lg bg-dark-800 p-2 text-secondary-400 hover:bg-dark-700 hover:text-white"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              >
                <span className="sr-only">Open main menu</span>
                {mobileMenuOpen ? (
                  <XMarkIcon className="h-6 w-6" aria-hidden="true" />
                ) : (
                  <Bars3Icon className="h-6 w-6" aria-hidden="true" />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile menu */}
        {mobileMenuOpen && (
          <div className="md:hidden">
            <div className="space-y-1 px-2 pb-3 pt-2">
              {navigation.map((item) => (
                <Link
                  key={item.name}
                  to={item.href}
                  className={clsx(
                    'block rounded-lg px-3 py-2 text-base font-medium transition-colors',
                    isActive(item.href)
                      ? 'bg-primary-900 text-primary-300'
                      : 'text-secondary-300 hover:bg-dark-800 hover:text-white'
                  )}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {item.name}
                </Link>
              ))}
            </div>
          </div>
        )}
      </nav>
    </header>
  )
}

export default Header
