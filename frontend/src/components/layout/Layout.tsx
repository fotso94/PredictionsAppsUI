import React from 'react'
import { Outlet } from 'react-router-dom'
import Header from './Header'
import Footer from './Footer'
import ProviderStatusBanner from '@/components/ui/ProviderStatusBanner'

const Layout: React.FC = () => {
  return (
    <div className="min-h-screen bg-dark-950 flex flex-col">
      <Header />
      <ProviderStatusBanner />
      <main className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}

export default Layout
