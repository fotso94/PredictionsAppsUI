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

/**
 * Create an account — and then carry on with whatever the visitor was doing.
 *
 * This form had no navigation of its own at all: everyone landed on the role landing page
 * AuthContext picks, whatever they had been doing when they were sent here. It now honours the
 * same handoff as LoginPage, because "create a new account" is one click away from that form and
 * a visitor who takes it has not changed their mind about the match they were saving. The contract
 * and the destination validation both live in components/favourites/useMatchSaving.ts.
 */

const RegisterPage: React.FC = () => {
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
      toast.error('Passwords do not match')
      return
    }

    // Validate terms agreement
    if (!formData.agreeToTerms) {
      toast.error('Please agree to the terms and conditions')
      return
    }

    // Validate password strength (minimum 8 characters)
    if (formData.password.length < 8) {
      toast.error('Password must be at least 8 characters long')
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
      toast.success('Account created successfully! Welcome email sent to your inbox.')
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
        <title>Create Account - Soccer Predictions</title>
        <meta name="description" content="Create your Soccer Predictions account to access premium features and personalized predictions." />
      </Helmet>

      <div className="min-h-screen bg-dark-950 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full space-y-8">
          {/* Header */}
          <div className="text-center">
            <Link to="/" className="flex items-center justify-center space-x-2 mb-8">
              <div className="h-10 w-10 rounded-lg bg-gradient-to-r from-primary-500 to-primary-600 flex items-center justify-center">
                <span className="text-white font-bold text-xl">SP</span>
              </div>
              <span className="text-2xl font-bold text-white">Soccer Predictions</span>
            </Link>
            <h2 className="text-3xl font-bold text-white">Create your account</h2>
            <p className="mt-2 text-secondary-400">
              Already have an account?{' '}
              {/* The handoff rides along, so going back to sign in still finishes the save and
                  still returns to the same page. */}
              <Link to="/login" state={location.state} className="text-primary-400 hover:text-primary-300">
                Sign in
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
              Saving a match needs an account. Create one and we will finish saving{' '}
              <span className="font-medium text-white">{interruptedSave.label ?? 'that match'}</span>
              {' '}and take you back to where you were.
            </p>
          )}

          {/* Form */}
          <Card>
            <Card.Body>
              <form className="space-y-6" onSubmit={handleSubmit}>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="firstName" className="form-label">
                      First name
                    </label>
                    <input
                      id="firstName"
                      name="firstName"
                      type="text"
                      required
                      className="form-input"
                      placeholder="First name"
                      value={formData.firstName}
                      onChange={(e) => setFormData({ ...formData, firstName: e.target.value })}
                    />
                  </div>
                  <div>
                    <label htmlFor="lastName" className="form-label">
                      Last name
                    </label>
                    <input
                      id="lastName"
                      name="lastName"
                      type="text"
                      required
                      className="form-input"
                      placeholder="Last name"
                      value={formData.lastName}
                      onChange={(e) => setFormData({ ...formData, lastName: e.target.value })}
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="email" className="form-label">
                    Email address
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    className="form-input"
                    placeholder="Enter your email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  />
                </div>

                <div>
                  <label htmlFor="username" className="form-label">
                    Username
                  </label>
                  <input
                    id="username"
                    name="username"
                    type="text"
                    required
                    className="form-input"
                    placeholder="Choose a username"
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  />
                </div>

                <div>
                  <label htmlFor="password" className="form-label">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      id="password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      required
                      className="form-input pr-10"
                      placeholder="Create a password"
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    />
                    <button
                      type="button"
                      className="absolute inset-y-0 right-0 pr-3 flex items-center"
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
                    Confirm password
                  </label>
                  <div className="relative">
                    <input
                      id="confirmPassword"
                      name="confirmPassword"
                      type={showConfirmPassword ? 'text' : 'password'}
                      required
                      className="form-input pr-10"
                      placeholder="Confirm your password"
                      value={formData.confirmPassword}
                      onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                    />
                    <button
                      type="button"
                      className="absolute inset-y-0 right-0 pr-3 flex items-center"
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
                    I agree to the{' '}
                    <a href="#" className="text-primary-400 hover:text-primary-300">
                      Terms of Service
                    </a>{' '}
                    and{' '}
                    <a href="#" className="text-primary-400 hover:text-primary-300">
                      Privacy Policy
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
                    {isSubmitting || isLoading ? 'Creating account...' : 'Create account'}
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
