import React from 'react'
import { Outlet } from 'react-router-dom'
import Header from './Header'
import Footer from './Footer'
import ProviderStatusBanner from '@/components/ui/ProviderStatusBanner'

/**
 * The shell every page inside the app renders into.
 *
 * The skip link is the one addition worth explaining: the header carries a logo, four navigation
 * entries, a search box and an account menu, and a keyboard or screen-reader user had to tab
 * through all of it on every single page before reaching the fixtures. It is invisible until it
 * receives focus, and it is the first thing in the tab order.
 */
const Layout: React.FC = () => {
  return (
    <div className="min-h-screen bg-dark-950 flex flex-col">
      <a
        href="#main"
        className="focus-ring sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[60] focus:rounded-lg focus:bg-primary-700 focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
      >
        Skip to the matches
      </a>
      <Header />
      <ProviderStatusBanner />
      <main id="main" className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}

export default Layout
