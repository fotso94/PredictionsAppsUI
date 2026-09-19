import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

/**
 * The site-wide footer, and the second place the site names its own sections.
 *
 * TERMINOLOGY. This list used to say "Today's Predictions" and "Tomorrow's Predictions" while the
 * header called the very same destination "Matches" and the destination itself is headed "Today's
 * matches". Three names for one page is three chances to think you have found something new. The
 * word "Predictions" survives in the URL, because /predictions/today is linked from elsewhere and
 * bookmarked, but it is no longer what anything on screen calls the section.
 *
 * "Dashboard" is the one entry here that is NOT the same kind of thing as the others. Matches and
 * Leagues are public; the dashboard is the reader's own saved matches and followed teams and is
 * behind ProtectedRoute, so a signed-out visitor who taps it gets the sign-in form instead of the
 * page they were promised. Rather than rename it — "Dashboard" is its own heading, its navigation
 * entry and what the dashboard spec looks for — the gate is simply stated, in the same voice the
 * unpublished support pages below already use.
 */
const Footer: React.FC = () => {
  const { isAuthenticated } = useAuth()

  return (
    <footer className="bg-dark-900 border-t border-dark-700">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="col-span-1 md:col-span-2">
            <div className="flex items-center space-x-2 mb-4">
              <div className="h-8 w-8 rounded-lg bg-gradient-to-r from-primary-500 to-primary-600 flex items-center justify-center">
                <span className="text-white font-bold text-lg">SP</span>
              </div>
              <span className="text-xl font-bold text-white">Soccer Predictions</span>
            </div>
            <p className="text-secondary-400 max-w-md">
              Fixtures, results and model forecasts for Europe&rsquo;s top five leagues and the
              Champions League, alongside predictions published by registered experts. Every
              probability names its source. Nothing here is betting advice.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h3 className="text-white font-semibold mb-4">Quick Links</h3>
            <ul className="space-y-2">
              <li>
                <Link to="/predictions/today" className="focus-ring rounded text-secondary-400 transition-colors hover:text-white">
                  Today's matches
                </Link>
              </li>
              <li>
                <Link to="/predictions/tomorrow" className="focus-ring rounded text-secondary-400 transition-colors hover:text-white">
                  Tomorrow's matches
                </Link>
              </li>
              <li>
                <Link to="/leagues" className="focus-ring rounded text-secondary-400 transition-colors hover:text-white">
                  Leagues
                </Link>
              </li>
              <li>
                <Link to="/dashboard" className="focus-ring rounded text-secondary-400 transition-colors hover:text-white">
                  Dashboard
                  {/* Inside the link, not beside it: the gate is part of where this goes, and a
                      screen reader reading the link out of context has to hear it too. */}
                  {!isAuthenticated && <span className="text-xs text-secondary-400"> (sign in required)</span>}
                </Link>
              </li>
            </ul>
          </div>

          {/* Support. These pages do not exist yet, so they are listed as text rather than as links
              that go nowhere. Give each one a route and turn it back into a <Link>. */}
          <div>
            <h3 className="text-white font-semibold mb-4">Support</h3>
            {/* Both greys here used to be secondary-500 and secondary-600, which measure 3.75:1
                and 2.36:1 against this background — below the 4.5:1 WCAG AA asks of body text, and
                the annotation was below even the 3:1 for large text. secondary-400 is 6.96:1; the
                size difference is what keeps the annotation secondary, not a grey nobody can read. */}
            <ul className="space-y-2 text-secondary-400">
              {['Help Centre', 'Contact Us', 'Privacy Policy', 'Terms of Service'].map(item => (
                <li key={item}>
                  {item} <span className="text-xs text-secondary-400">(not published yet)</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-8 pt-8 border-t border-dark-700">
          <div className="flex flex-col sm:flex-row justify-between items-center">
            <p className="text-secondary-400 text-sm">
              © {new Date().getFullYear()} Soccer Predictions. All rights reserved.
            </p>
            <div className="flex space-x-6 mt-4 sm:mt-0">
              <span className="text-secondary-600" title="Twitter account not set up yet">
                <span className="sr-only">Twitter</span>
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M6.29 18.251c7.547 0 11.675-6.253 11.675-11.675 0-.178 0-.355-.012-.53A8.348 8.348 0 0020 3.92a8.19 8.19 0 01-2.357.646 4.118 4.118 0 001.804-2.27 8.224 8.224 0 01-2.605.996 4.107 4.107 0 00-6.993 3.743 11.65 11.65 0 01-8.457-4.287 4.106 4.106 0 001.27 5.477A4.073 4.073 0 01.8 7.713v.052a4.105 4.105 0 003.292 4.022 4.095 4.095 0 01-1.853.07 4.108 4.108 0 003.834 2.85A8.233 8.233 0 010 16.407a11.616 11.616 0 006.29 1.84" />
                </svg>
              </span>
              <span className="text-secondary-600" title="Facebook account not set up yet">
                <span className="sr-only">Facebook</span>
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M20 10C20 4.477 15.523 0 10 0S0 4.477 0 10c0 4.991 3.657 9.128 8.438 9.878v-6.987h-2.54V10h2.54V7.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V10h2.773l-.443 2.89h-2.33v6.988C16.343 19.128 20 14.991 20 10z" clipRule="evenodd" />
                </svg>
              </span>
              <span className="text-secondary-600" title="Instagram account not set up yet">
                <span className="sr-only">Instagram</span>
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 0C4.477 0 0 4.484 0 10.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0110 4.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.203 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.942.359.31.678.921.678 1.856 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0020 10.017C20 4.484 15.522 0 10 0z" clipRule="evenodd" />
                </svg>
              </span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}

export default Footer
