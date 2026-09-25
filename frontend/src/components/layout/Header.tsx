import React, { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Bars3Icon,
  XMarkIcon,
  UserCircleIcon,
  ChevronDownIcon,
  ArrowRightOnRectangleIcon
} from '@heroicons/react/24/outline'
import { Menu, Transition } from '@headlessui/react'
import { Fragment } from 'react'
import clsx from 'clsx'
import { NavItem } from '@/types'
import { useAuth } from '@/hooks/useAuth'
import { LowDataToggle } from '@/contexts/LowDataContext'
import { RegionSettings } from '@/i18n/LocaleProvider'
import { useT } from '@/i18n/react'
import SearchDropdown from './SearchDropdown'

/**
 * Top-level navigation.
 *
 * "Today" and "Tomorrow" used to be two separate entries here. They now resolve to the same
 * matchday workspace with a different day preselected, and the workspace carries its own date
 * strip, so a single "Matches" entry says what the section is without spending two of the four
 * slots a phone has room for on two days of the same list. Both routes still exist and still work;
 * they are simply not the way the header describes the section any more.
 *
 * WHAT HAS TO FIT ON A 360px PHONE. The narrow layout used to carry the full wordmark, BOTH
 * account actions and the menu button on one 16px-tall row. At 360px that came to about 370px of
 * content: the brand wrapped onto two lines, the menu button was clipped by the right edge, and
 * the whole document scrolled sideways — so the one control that reaches every other page could
 * not be tapped. Three responsive rules fix it, and each of them earns its place:
 *
 *  - the wordmark is hidden below `sm` and the square mark stands in for it. The mark is the
 *    widest part of the brand that fits next to a control on the narrowest phone we support, and
 *    the link keeps the full name as its accessible name at every width;
 *  - ONE account action below `sm`, and it is "Sign in". Signing in is what unblocks a returning
 *    reader, it is where the product already sends anyone who taps Save on a fixture while signed
 *    out (see useMatchSaving), and registering is one tap away in the menu — where "Create
 *    account" now lives — whereas an account you cannot get back into has no other route at all.
 *    "Sign up" returns to the bar at `sm` and above, unchanged;
 *  - the search box is still hidden below `sm` and still offered inside the menu, exactly as
 *    before. That is the only place a phone can search from, so it stays.
 *
 * AND THE OTHER WIDTH NOBODY HAD MEASURED: 768. The four destinations used to join the bar at
 * `md`, and the row they made needs 928px — so from 768 (iPad portrait) to about 950 the header
 * overflowed by up to 184px, the same defect as 360 and on a far more common screen. They now
 * join at `lg`, where there is room for them, and the menu button stays on the bar until then. No
 * entry moved and nothing was renamed: the only change is the width at which the bar stops trying
 * to hold everything at once. Measured after: 0px of overflow at every width from 375 up.
 *
 * The wide row keeps the same entries in the same order.
 *
 * WHERE THE TEXT-ONLY SWITCH SITS, AND THE MEASUREMENT THAT PUT IT THERE. The rule above — a
 * control joins the bar at the width where the row it makes actually fits — decides this too, and
 * it was applied by measuring rather than by picking a breakpoint that felt right. Every figure
 * below is document overflow at that width, and 0 is the only acceptable answer:
 *
 *   switch on the bar at `lg`                       1024: 94px   1100: 18px   1150: 0
 *   switch at `xl`, menu button `xl:hidden`         1024:  0px   1100:  0px
 *     ...the same, signed in as an expert           1024: 46px   1100:  0px
 *   ...and with `lg:space-x-4 xl:space-x-8`         1024:  0px   1100:  0px
 *
 * Three things follow from those numbers. The switch is 126px wide against 32px of slack at 1024,
 * so it does not go on the bar at `lg`; it joins at `xl`. Below `xl` the menu button stays on the
 * bar and the switch lives in the panel — which costs nothing signed out, because the search box
 * gives up the width, but overflowed by 46px for an expert, who carries a sixth entry. Hence the
 * last line: the wide row's spacing is 16px between `lg` and `xl` and returns to 32px at `xl`,
 * which is what buys the expert bar its room back.
 *
 * Between `lg` and `xl` the four destinations are already on the bar, so the panel does not repeat
 * them; there it holds the switch and nothing else.
 *
 * The alternative was to move the destinations back to `xl` and keep the switch beside them at
 * `lg`. That would have taken the inline navigation away from every 1024-1279 laptop to make room
 * for a setting most readers will touch once, which is the wrong way round.
 */
/**
 * The destinations, named in the reader's language.
 *
 * A function of `t` rather than a module constant, because a module constant is evaluated once at
 * import time — which is before the reader's catalogue has necessarily been applied, and long
 * before they can change it. `href` is not translated: a URL is an address, and translating one
 * would break every existing link, bookmark and test.
 */
const navigationItems = (t: (key: 'nav.home' | 'nav.matches' | 'nav.leagues' | 'nav.dashboard' | 'selections.nav') => string): NavItem[] => [
  { name: t('nav.home'), href: '/' },
  { name: t('nav.matches'), href: '/matches' },
  { name: t('nav.leagues'), href: '/leagues' },
  { name: t('selections.nav'), href: '/selections' },
  { name: t('nav.dashboard'), href: '/dashboard' },
]

/** Other paths a nav entry is the home of, so the highlight follows the reader into them. */
const ALSO_ACTIVE: Record<string, string[]> = {
  '/matches': ['/predictions', '/match/'],
}

const Header: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const location = useLocation()
  const { isAuthenticated, user, logout } = useAuth()
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const t = useT()
  const navigation = navigationItems(t)

  const isActive = (href: string) => {
    if (href === '/') {
      return location.pathname === '/'
    }
    if (location.pathname.startsWith(href)) return true
    return (ALSO_ACTIVE[href] ?? []).some(prefix => location.pathname.startsWith(prefix))
  }

  /**
   * Escape closes the menu and hands focus back to the button that opened it, so a keyboard reader
   * is never left with focus on a panel that is no longer on screen.
   *
   * The search box inside the panel handles Escape for itself — it closes its results list and
   * blurs. Swallowing that first press here would shut the whole menu and throw away the query the
   * reader had typed, so an Escape aimed at a field is left to the field, and the one after it
   * (focus is no longer in the input by then) closes the menu.
   */
  useEffect(() => {
    if (!mobileMenuOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      const target = event.target as HTMLElement | null
      if (target?.tagName === 'INPUT') return
      setMobileMenuOpen(false)
      menuButtonRef.current?.focus()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [mobileMenuOpen])

  /**
   * Close the panel whenever the route changes. Every link inside it already closes it on click,
   * but the search dropdown navigates on its own, and a menu still covering the page it just
   * opened is a dead end on a phone.
   */
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname, location.search])

  const handleLogout = async () => {
    try {
      await logout()
    } catch (error) {
      console.error('Logout failed:', error)
    }
  }

  return (
    <header className="sticky top-0 z-50 bg-dark-900/95 backdrop-blur-sm border-b border-dark-700">
      <nav className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8" aria-label={t('app.topNavigation')}>
        {/*
          `flex-wrap` and a MINIMUM height rather than a fixed one — the one change this
          localisation package made to the header, and the measurement that required it.

          The bar was sized for English. At 200% text zoom on a 360px phone the narrow row holds
          the square mark, one account action and the menu button, and "Sign In" fits it with
          nothing to spare: measured 0px of document overflow. "Connexion" — already the short
          French form, the noun rather than "Se connecter" — does not: 41px of overflow, and what
          the 41px pushed off the right edge was the menu button, which is the one control that
          reaches every other page. That is the same defect the 360px work fixed for English,
          reappearing in the other language.

          Wrapping costs nothing when the row fits, which is every width at normal text size, so
          the widths that package measured are untouched. `h-16` had to become `min-h-[4rem]`
          with it: a fixed height would clip the second line instead of making room for it.
        */}
        <div className="flex min-h-[4rem] flex-wrap items-center justify-between gap-2">
          {/* Brand. The mark carries no text of its own for assistive technology: below `sm` the
              wordmark is not rendered, so the link states the full name itself. */}
          <Link
            to="/"
            aria-label={t('app.brandHome')}
            className="focus-ring flex shrink-0 items-center gap-2 rounded-lg"
          >
            <span
              aria-hidden="true"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-r from-primary-500 to-primary-600 text-lg font-bold text-white"
            >
              SP
            </span>
            <span className="hidden whitespace-nowrap text-xl font-bold text-white sm:inline">
              {t('app.name')}
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden lg:flex lg:items-center lg:space-x-4 xl:space-x-8">
            {navigation.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                className={clsx(
                  'focus-ring px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                  isActive(item.href)
                    ? 'bg-primary-900 text-primary-300'
                    : 'text-secondary-300 hover:text-white hover:bg-dark-800'
                )}
              >
                {item.name}
              </Link>
            ))}

            {/* Expert Dashboard - Only visible to EXPERT and ADMIN users */}
            {(user?.user_type === 'EXPERT' || user?.user_type === 'ADMIN') && (
              <Link
                to="/expert/dashboard"
                className={clsx(
                  'focus-ring px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center space-x-1',
                  isActive('/expert/dashboard')
                    ? 'bg-purple-900 text-purple-300'
                    : 'text-purple-400 hover:text-purple-300 hover:bg-purple-900/50'
                )}
              >
                <span aria-hidden="true">⚡</span>
                <span>{t('nav.expert')}</span>
              </Link>
            )}

            <LowDataToggle variant="bar" />
          </div>

          {/* Search and User Menu */}
          <div className="flex min-w-0 items-center gap-2 sm:gap-4">
            {/* Search */}
            <SearchDropdown className="hidden sm:block" />

            {/* User Menu */}
            {isAuthenticated ? (
              <Menu as="div" className="relative">
                <div>
                  <Menu.Button className="focus-ring flex shrink-0 items-center gap-2 rounded-lg bg-dark-800 px-3 py-2 text-sm font-medium text-white hover:bg-dark-700 transition-colors">
                    <UserCircleIcon className="h-6 w-6 shrink-0" aria-hidden="true" />
                    <span className="hidden max-w-[10rem] truncate sm:block">
                      {user?.first_name || user?.email}
                    </span>
                    <ChevronDownIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {/* Below `sm` the name is not rendered and both icons are hidden from
                        assistive technology, which left this button with no accessible name at
                        all. `sm:hidden` takes this back out of the tree the moment the visible
                        name is there to do the job. */}
                    <span className="sr-only sm:hidden">{t('nav.accountMenu')}</span>
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
                  <Menu.Items className="absolute right-0 z-10 mt-2 w-56 origin-top-right rounded-lg bg-dark-800 py-1 shadow-lg ring-1 ring-dark-700 focus:outline-none">
                    {/* User Info */}
                    <div className="px-4 py-3 border-b border-dark-700">
                      <p className="text-sm font-medium text-white">
                        {user?.first_name} {user?.last_name}
                      </p>
                      <p className="text-xs text-secondary-400 truncate">
                        {user?.email}
                      </p>
                      <p className="text-xs text-primary-400 mt-1">
                        {user?.user_type}
                      </p>
                    </div>

                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/dashboard"
                          className={clsx(
                            active ? 'bg-dark-700' : '',
                            'block px-4 py-2 text-sm text-white'
                          )}
                        >
                          {t('nav.dashboard')}
                        </Link>
                      )}
                    </Menu.Item>

                    {/* Expert Dashboard - Only visible to EXPERT and ADMIN users */}
                    {(user?.user_type === 'EXPERT' || user?.user_type === 'ADMIN') && (
                      <Menu.Item>
                        {({ active }) => (
                          <Link
                            to="/expert/dashboard"
                            className={clsx(
                              active ? 'bg-dark-700' : '',
                              'block px-4 py-2 text-sm text-white'
                            )}
                          >
                            <div className="flex items-center space-x-2">
                              <span aria-hidden="true">⚡</span>
                              <span>{t('nav.expertDashboard')}</span>
                            </div>
                          </Link>
                        )}
                      </Menu.Item>
                    )}

                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/profile"
                          className={clsx(
                            active ? 'bg-dark-700' : '',
                            'block px-4 py-2 text-sm text-white'
                          )}
                        >
                          {t('nav.profileSettings')}
                        </Link>
                      )}
                    </Menu.Item>

                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/password-change"
                          className={clsx(
                            active ? 'bg-dark-700' : '',
                            'block px-4 py-2 text-sm text-white'
                          )}
                        >
                          {t('nav.changePassword')}
                        </Link>
                      )}
                    </Menu.Item>

                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/subscription"
                          className={clsx(
                            active ? 'bg-dark-700' : '',
                            'block px-4 py-2 text-sm text-white'
                          )}
                        >
                          {t('nav.subscription')}
                        </Link>
                      )}
                    </Menu.Item>

                    <div className="border-t border-dark-700 my-1"></div>

                    <Menu.Item>
                      {({ active }) => (
                        <button
                          onClick={handleLogout}
                          className={clsx(
                            active ? 'bg-dark-700' : '',
                            'w-full text-left px-4 py-2 text-sm text-white flex items-center space-x-2'
                          )}
                        >
                          <ArrowRightOnRectangleIcon className="h-5 w-5" aria-hidden="true" />
                          <span>{t('nav.signOut')}</span>
                        </button>
                      )}
                    </Menu.Item>
                  </Menu.Items>
                </Transition>
              </Menu>
            ) : (
              <div className="flex shrink-0 items-center gap-2">
                {/* The single account action on a phone. The border is what makes it read as a
                    control once it is standing on its own; from `sm` up it is the quiet half of
                    the pair again, exactly as before. */}
                <Link
                  to="/login"
                  className="focus-ring whitespace-nowrap rounded-lg border border-dark-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-dark-800 sm:border-transparent sm:px-4 sm:hover:bg-transparent sm:hover:text-primary-300"
                >
                  {t('nav.signIn')}
                </Link>
                <Link
                  to="/register"
                  className="focus-ring hidden whitespace-nowrap rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700 sm:block"
                >
                  {t('nav.signUp')}
                </Link>
              </div>
            )}

            {/* Mobile menu button. `xl:hidden`, not `lg:hidden`: between the two breakpoints it
                is the only way to the reading-mode switch, and it was measured to cost nothing —
                0px of overflow at 1024 and at 1100. */}
            <div className="xl:hidden">
              <button
                ref={menuButtonRef}
                type="button"
                aria-expanded={mobileMenuOpen}
                aria-controls="mobile-menu"
                className="focus-ring tap-target shrink-0 rounded-lg bg-dark-800 p-2 text-secondary-400 hover:bg-dark-700 hover:text-white"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              >
                <span className="sr-only">{t(mobileMenuOpen ? 'nav.closeMenu' : 'nav.openMenu')}</span>
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
          <div className="xl:hidden" id="mobile-menu">
            <div className="space-y-1 px-2 pb-3 pt-2">
              {/* The header search is hidden below the sm breakpoint, so a phone would otherwise
                  have no way to search for a team or a competition at all. */}
              <div className="px-1 pb-3 sm:hidden">
                <SearchDropdown className="block" />
              </div>

              {/* The destinations, for the widths where the bar does not already carry them.
                  From `lg` up they are on the bar, and a panel that repeated them would be
                  offering the reader the same four links twice. */}
              <div className="space-y-1 lg:hidden">
              {navigation.map((item) => (
                <Link
                  key={item.name}
                  to={item.href}
                  className={clsx(
                    'focus-ring tap-target-row flex items-center rounded-lg px-3 py-2 text-base font-medium transition-colors',
                    isActive(item.href)
                      ? 'bg-primary-900 text-primary-300'
                      : 'text-secondary-300 hover:bg-dark-800 hover:text-white'
                  )}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {item.name}
                </Link>
              ))}

              {/* Expert Dashboard - Only visible to EXPERT and ADMIN users */}
              {(user?.user_type === 'EXPERT' || user?.user_type === 'ADMIN') && (
                <Link
                  to="/expert/dashboard"
                  className={clsx(
                    'focus-ring tap-target-row flex items-center gap-2 rounded-lg px-3 py-2 text-base font-medium transition-colors',
                    isActive('/expert/dashboard')
                      ? 'bg-purple-900 text-purple-300'
                      : 'text-purple-400 hover:bg-purple-900/50 hover:text-purple-300'
                  )}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <span aria-hidden="true">⚡</span>
                  <span>{t('nav.expertDashboard')}</span>
                </Link>
              )}
              </div>

              {/* The reading-mode switch: the whole reason this panel is reachable above `lg`. */}
              <div className="mt-2 border-t border-dark-700 pt-2">
                <LowDataToggle variant="menu" />
              </div>

              {/*
                Language and time zone.

                IN THE PANEL, NOT ON THE BAR, and that is a measurement rather than a preference:
                the widths above were established control by control, with 32px of slack at 1024
                once the text-only switch had taken its 126px, and a language control on the bar
                would spend that slack without re-measuring it. The panel is reachable at every
                width below `xl`, and the footer carries the same block for the widths above it —
                so the setting is never more than one control away, at any size.
              */}
              <div className="mt-2 border-t border-dark-700 pt-2">
                <RegionSettings variant="menu" />
              </div>

              {/* The account action the narrow bar has no room for. Without this, registering is
                  unreachable from a phone except by guessing the URL. */}
              {!isAuthenticated && (
                <Link
                  to="/register"
                  className="focus-ring tap-target-row mt-2 flex items-center rounded-lg border-t border-dark-700 px-3 pt-4 text-base font-medium text-primary-300 transition-colors hover:text-primary-200 sm:hidden"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {t('nav.createAccount')}
                </Link>
              )}
            </div>
          </div>
        )}
      </nav>
    </header>
  )
}

export default Header
