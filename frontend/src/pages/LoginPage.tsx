import React, { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import { useAuth } from '@/hooks/useAuth'
import type { ReturnedFromSignIn } from '@/components/favourites/useMatchSaving'
import { pendingSaveIntent, safeReturnPath, useResumeSave } from '@/components/favourites/useMatchSaving'
import Emphasised from '@/i18n/Emphasised'
import { useT } from '@/i18n/react'

/**
 * Sign in — and, when something sent the visitor here, carry on with it afterwards.
 *
 * A visitor rarely arrives at this form because they wanted a form. They pressed save on a match,
 * or opened their dashboard, and were sent here with the page they were on in the router's
 * navigation state. Until now that state was dropped: they signed in and landed on a role
 * dashboard, their date and filters gone and the match still unsaved. Both halves are honoured
 * here — see the handoff contract in components/favourites/useMatchSaving.ts, which is also where
 * the return destination is validated.
 *
 * WHY THE EXPLICIT navigate() AFTER login(). AuthContext sends everyone to a role landing page of
 * its own the moment the tokens are stored, which happens inside `login()`. Replacing that entry
 * afterwards is what puts the visitor back where they were without leaving the role page in their
 * history; `replace` rather than `push` so Back does not bounce them forward again. With no return
 * destination nothing is replaced, and AuthContext's role landing page stands exactly as before.
 *
 * EVERY WORD ON THIS PAGE IS NOW IN THE READER'S LANGUAGE. It was the one form a French reader
 * was guaranteed to meet — a save control sends them here — and it was the one page still
 * entirely in English, notice included. The strings are in src/i18n/messages/auth.en.ts and
 * auth.fr.ts; nothing here builds a sentence out of fragments, and the fixture's name inside the
 * notice stays exactly as the provider publishes it.
 */

const LoginPage: React.FC = () => {
  const t = useT()
  const { login, isAuthenticated, isLoading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const resumeSave = useResumeSave()
  const [showPassword, setShowPassword] = useState(false)
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    rememberMe: false,
  })
  const [isSubmitting, setIsSubmitting] = useState(false)

  /** Where this visitor asked to go back to, once it has been proved to be a path on this app. */
  const returnTo = safeReturnPath(location.state)
  /** The save they were in the middle of, if any — used only to say so above the form. */
  const interruptedSave = pendingSaveIntent(location.state)

  /** How the waiting save is named on screen: the provider's words, or ours if it carried none. */
  const savedLabel = interruptedSave?.label ?? t('auth.saveIntent.thatMatch')

  /** Tells the destination it was returned to, not walked to. See ReturnedFromSignIn. */
  const arrival: ReturnedFromSignIn = { resumedFromSignIn: true }

  // Already signed in: there is nothing to do here but honour the destination they came for.
  if (isAuthenticated) {
    return <Navigate to={returnTo ?? '/'} state={arrival} replace />
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (isSubmitting) return

    try {
      setIsSubmitting(true)
      await login(formData.email, formData.password)
      // Both calls below outlive this component: AuthContext has already navigated to its role
      // landing page, so the form is unmounted by the time they run. That is safe and deliberate —
      // `navigate` stays bound to the live router, and the save goes through the shared store
      // rather than through any state held here.
      //
      // THE ORDER MATTERS. The destination loads the saved list the moment it mounts, so
      // navigating first would race that read against this write and could leave the star showing
      // "not saved" for a match the server had just accepted. One extra request on the form is
      // cheaper than a control that lies.
      await resumeSave(location.state)
      if (returnTo) navigate(returnTo, { replace: true, state: arrival })
    } catch (error) {
      // Error is handled by AuthContext (toast notification)
      console.error('Login failed:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <>
      <Helmet>
        <title>{t('auth.login.documentTitle')}</title>
        <meta name="description" content={t('auth.login.documentDescription')} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full space-y-8">
          {/* Header */}
          <div className="text-center">
            <Link to="/" className="flex items-center justify-center space-x-2 mb-8">
              <div className="h-10 w-10 rounded-lg bg-gradient-to-r from-primary-500 to-primary-600 flex items-center justify-center">
                <span className="text-white font-bold text-xl">SP</span>
              </div>
              <span className="text-2xl font-bold text-white">{t('app.name')}</span>
            </Link>
            <h2 className="text-3xl font-bold text-white">{t('auth.login.heading')}</h2>
            <p className="mt-2 text-secondary-400">
              {t('auth.login.newAccountPrompt')}{' '}
              {/* The handoff rides along, so creating an account instead still finishes the save
                  and still returns to the same page. */}
              <Link to="/register" state={location.state} className="text-primary-400 hover:text-primary-300">
                {t('auth.login.newAccountLink')}
              </Link>
            </p>
          </div>

          {/*
            Why they are on this form. Stated only when a save is genuinely waiting, and worded as
            what will be attempted rather than as a result: the save happens after the sign-in, and
            it can still fail.
          */}
          {interruptedSave && (
            <p
              className="rounded-lg border border-dark-700 bg-dark-900/60 px-4 py-3 text-center text-sm text-secondary-200"
              data-testid="login-save-intent"
            >
              {/*
                One sentence from the catalogue, with the fixture's own name emphasised inside
                it wherever the language puts it — not a prefix and a suffix in English order.
                The name itself is the provider's and is never translated; when the handoff
                carried none, the catalogue supplies "that match" in the reader's language.
              */}
              <Emphasised
                sentence={t('auth.saveIntent.signIn', { match: savedLabel })}
                value={savedLabel}
                className="font-medium text-white"
              />
            </p>
          )}

          {/* Form */}
          <Card>
            <Card.Body>
              <form className="space-y-6" onSubmit={handleSubmit}>
                <div>
                  <label htmlFor="email" className="form-label">
                    {t('auth.field.email')}
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    className="form-input"
                    placeholder={t('auth.field.emailPlaceholder')}
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  />
                </div>

                <div>
                  <label htmlFor="password" className="form-label">
                    {t('auth.field.password')}
                  </label>
                  <div className="relative">
                    <input
                      id="password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      required
                      className="form-input pr-10"
                      placeholder={t('auth.field.passwordPlaceholder')}
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    />
                    {/* The eye had no accessible name at all before this: a screen reader was
                        told only "button". */}
                    <button
                      type="button"
                      className="absolute inset-y-0 right-0 pr-3 flex items-center"
                      aria-label={t(showPassword ? 'auth.field.hidePassword' : 'auth.field.showPassword')}
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? (
                        <EyeSlashIcon className="h-5 w-5 text-secondary-400" />
                      ) : (
                        <EyeIcon className="h-5 w-5 text-secondary-400" />
                      )}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <input
                      id="remember-me"
                      name="remember-me"
                      type="checkbox"
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-dark-600 bg-dark-800 rounded"
                      checked={formData.rememberMe}
                      onChange={(e) => setFormData({ ...formData, rememberMe: e.target.checked })}
                    />
                    <label htmlFor="remember-me" className="ml-2 block text-sm text-secondary-300">
                      {t('auth.login.rememberMe')}
                    </label>
                  </div>

                  <div className="text-sm">
                    <Link to="/forgot-password" className="text-primary-400 hover:text-primary-300">
                      {t('auth.login.forgotPassword')}
                    </Link>
                  </div>
                </div>

                <div>
                  <Button
                    type="submit"
                    className="w-full"
                    size="lg"
                    disabled={isSubmitting || isLoading}
                  >
                    {t(isSubmitting || isLoading ? 'auth.login.submitting' : 'auth.login.submit')}
                  </Button>
                </div>
              </form>
            </Card.Body>
          </Card>
        </div>
      </div>
    </>
  )
}

export default LoginPage
