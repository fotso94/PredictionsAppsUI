import React, { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import { useAuth } from '@/hooks/useAuth'
import toast from 'react-hot-toast'
import type { ReturnedFromSignIn } from '@/components/favourites/useMatchSaving'
import { pendingSaveIntent, safeReturnPath, useResumeSave } from '@/components/favourites/useMatchSaving'
import Emphasised from '@/i18n/Emphasised'
import { useT } from '@/i18n/react'

/**
 * Create an account — and then carry on with whatever the visitor was doing.
 *
 * This form had no navigation of its own at all: everyone landed on the role landing page
 * AuthContext picks, whatever they had been doing when they were sent here. It now honours the
 * same handoff as LoginPage, because "create a new account" is one click away from that form and
 * a visitor who takes it has not changed their mind about the match they were saving. The contract
 * and the destination validation both live in components/favourites/useMatchSaving.ts.
 *
 * ITS STRINGS ARE THE CATALOGUE'S, in src/i18n/messages/auth.en.ts and auth.fr.ts. Two things
 * about them are not visible from the English. The password rule states its own plural, because
 * the minimum is a number this form holds rather than a word in a sentence — MIN_PASSWORD_LENGTH
 * below, which mirrors the backend's own `min_length=8` — and the consent line carries its
 * ARTICLES in the catalogue rather than a bare "and", because French agrees them with the two
 * different nouns that follow: « les Conditions d'utilisation » and « la Politique de
 * confidentialité ».
 */

/**
 * The shortest password this form will submit.
 *
 * It mirrors `min_length=8` on every password field in backend/app/schemas/auth.py, and it is a
 * value rather than a word in a sentence precisely so the sentence can count it: "at least 8
 * characters" and "at least 1 character" are different sentences in both languages, and a
 * catalogue that spelled the number out could not produce the second one.
 */
const MIN_PASSWORD_LENGTH = 8

const RegisterPage: React.FC = () => {
  const t = useT()
  const { register, isAuthenticated, isLoading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const resumeSave = useResumeSave()
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    username: '',
    password: '',
    confirmPassword: '',
    agreeToTerms: false,
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

  // Redirect if already authenticated
  if (isAuthenticated) {
    return <Navigate to={returnTo ?? '/'} state={arrival} replace />
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (isSubmitting) return

    // Validate passwords match
    if (formData.password !== formData.confirmPassword) {
      toast.error(t('auth.validation.passwordsDiffer'))
      return
    }

    // Validate terms agreement
    if (!formData.agreeToTerms) {
      toast.error(t('auth.register.mustAgree'))
      return
    }

    // Validate password strength (minimum 8 characters)
    if (formData.password.length < MIN_PASSWORD_LENGTH) {
      toast.error(t('auth.validation.tooShortLong', { count: MIN_PASSWORD_LENGTH }))
      return
    }

    try {
      setIsSubmitting(true)
      await register({
        email: formData.email,
        username: formData.username, // Send user-provided username
        password: formData.password,
        first_name: formData.firstName,
        last_name: formData.lastName,
        role: 'regular', // Default role for new users
      })
      toast.success(t('auth.register.created'))
      // AuthContext has already navigated to its role landing page, and this component is
      // unmounted by now; replacing that entry is what returns the visitor to the page they were
      // on, and the save they had started goes through the shared store rather than through any
      // state held here. With no return destination, AuthContext's choice stands.
      //
      // The save runs FIRST: the destination reads the saved list as it mounts, and navigating
      // before the write landed would race the two and could show a star that says "not saved"
      // for a match the server had just accepted.
      await resumeSave(location.state)
      if (returnTo) navigate(returnTo, { replace: true, state: arrival })
    } catch (error) {
      // Error is handled by AuthContext (toast notification)
      console.error('Registration failed:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <>
      <Helmet>
        <title>{t('auth.register.documentTitle')}</title>
        <meta name="description" content={t('auth.register.documentDescription')} />
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
            <h2 className="text-3xl font-bold text-white">{t('auth.register.heading')}</h2>
            <p className="mt-2 text-secondary-400">
              {t('auth.register.haveAccountPrompt')}{' '}
              {/* The handoff rides along, so going back to sign in still finishes the save and
                  still returns to the same page. */}
              <Link to="/login" state={location.state} className="text-primary-400 hover:text-primary-300">
                {t('auth.register.signInLink')}
              </Link>
            </p>
          </div>

          {/*
            Why they are on this form. Stated only when a save is genuinely waiting, and worded as
            what will be attempted rather than as a result: the save happens after the account is
            created, and it can still fail.
          */}
          {interruptedSave && (
            <p
              className="rounded-lg border border-dark-700 bg-dark-900/60 px-4 py-3 text-center text-sm text-secondary-200"
              data-testid="register-save-intent"
            >
              {/* One sentence from the catalogue, the fixture's own name picked out inside it
                  wherever the language puts it. See LoginPage.tsx for the reasoning. */}
              <Emphasised
                sentence={t('auth.saveIntent.register', { match: savedLabel })}
                value={savedLabel}
                className="font-medium text-white"
              />
            </p>
          )}

          {/* Form */}
          <Card>
            <Card.Body>
              <form className="space-y-6" onSubmit={handleSubmit}>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="firstName" className="form-label">
                      {t('auth.register.firstName')}
                    </label>
                    <input
                      id="firstName"
                      name="firstName"
                      type="text"
                      required
                      className="form-input"
                      placeholder={t('auth.register.firstNamePlaceholder')}
                      value={formData.firstName}
                      onChange={(e) => setFormData({ ...formData, firstName: e.target.value })}
                    />
                  </div>
                  <div>
                    <label htmlFor="lastName" className="form-label">
                      {t('auth.register.lastName')}
                    </label>
                    <input
                      id="lastName"
                      name="lastName"
                      type="text"
                      required
                      className="form-input"
                      placeholder={t('auth.register.lastNamePlaceholder')}
                      value={formData.lastName}
                      onChange={(e) => setFormData({ ...formData, lastName: e.target.value })}
                    />
                  </div>
                </div>

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
                  <label htmlFor="username" className="form-label">
                    {t('auth.register.username')}
                  </label>
                  <input
                    id="username"
                    name="username"
                    type="text"
                    required
                    className="form-input"
                    placeholder={t('auth.register.usernamePlaceholder')}
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
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
                      required
                      className="form-input pr-10"
                      placeholder={t('auth.register.passwordPlaceholder')}
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    />
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

                <div>
                  <label htmlFor="confirmPassword" className="form-label">
                    {t('auth.register.confirmPassword')}
                  </label>
                  <div className="relative">
                    <input
                      id="confirmPassword"
                      name="confirmPassword"
                      type={showConfirmPassword ? 'text' : 'password'}
                      required
                      className="form-input pr-10"
                      placeholder={t('auth.register.confirmPasswordPlaceholder')}
                      value={formData.confirmPassword}
                      onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                    />
                    <button
                      type="button"
                      className="absolute inset-y-0 right-0 pr-3 flex items-center"
                      aria-label={t(showConfirmPassword ? 'auth.field.hidePassword' : 'auth.field.showPassword')}
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    >
                      {showConfirmPassword ? (
                        <EyeSlashIcon className="h-5 w-5 text-secondary-400" />
                      ) : (
                        <EyeIcon className="h-5 w-5 text-secondary-400" />
                      )}
                    </button>
                  </div>
                </div>

                <div className="flex items-center">
                  <input
                    id="agree-terms"
                    name="agree-terms"
                    type="checkbox"
                    required
                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-dark-600 bg-dark-800 rounded"
                    checked={formData.agreeToTerms}
                    onChange={(e) => setFormData({ ...formData, agreeToTerms: e.target.checked })}
                  />
                  <label htmlFor="agree-terms" className="ml-2 block text-sm text-secondary-300">
                    {/* The ARTICLE travels with each link, not with the join: French agrees it
                        with the noun that follows, and the two nouns disagree. */}
                    {t('auth.register.agreePrefix')}{' '}
                    <a href="#" className="text-primary-400 hover:text-primary-300">
                      {t('footer.termsOfService')}
                    </a>{' '}
                    {t('auth.register.agreeJoin')}{' '}
                    <a href="#" className="text-primary-400 hover:text-primary-300">
                      {t('footer.privacyPolicy')}
                    </a>
                  </label>
                </div>

                <div>
                  <Button
                    type="submit"
                    className="w-full"
                    size="lg"
                    disabled={isSubmitting || isLoading}
                  >
                    {t(isSubmitting || isLoading ? 'auth.register.submitting' : 'auth.register.submit')}
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

export default RegisterPage
