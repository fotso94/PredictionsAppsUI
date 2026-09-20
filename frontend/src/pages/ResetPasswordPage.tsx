import React, { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { LockClosedIcon, EyeIcon, EyeSlashIcon, CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import authService from '@/services/auth.service'
import { getErrorMessage } from '@/utils/errors'
import { useT } from '@/i18n/react'

/**
 * Set a new password from the link in the reset email.
 *
 * TWO NUMBERS ON THIS PAGE ARE VALUES, NOT WORDS. The minimum password length and how long a
 * reset link lasts are both facts about the backend, and both appear inside sentences that have
 * to count them — "8 characters" and "1 character" are different sentences in English and in
 * French, and French puts 0 with the singular as well. So each is a named constant here, cited
 * against the backend line it mirrors, and the catalogue states its own plural branches around
 * the hole. Nothing in src/i18n/messages/auth.*.ts writes either number down.
 */

/** Mirrors `min_length=8` on the reset field in backend/app/schemas/auth.py:124. */
const MIN_PASSWORD_LENGTH = 8

/**
 * How long a reset link stays usable.
 *
 * Mirrors `datetime.utcnow() + timedelta(hours=1)` in backend/app/api/v1/endpoints/auth.py:459.
 * If that changes, this is wrong and the page will say something untrue — which is why it is one
 * named constant with the line it copies written beside it rather than the digit "1" buried in a
 * sentence in two catalogues.
 */
const RESET_LINK_VALID_HOURS = 1

const ResetPasswordPage: React.FC = () => {
  const t = useT()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token')

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isVerifying, setIsVerifying] = useState(true)
  const [isTokenValid, setIsTokenValid] = useState(false)
  const [passwordStrength, setPasswordStrength] = useState(0)

  // Verify token on mount
  useEffect(() => {
    const verifyToken = async () => {
      if (!token) {
        setIsVerifying(false)
        setIsTokenValid(false)
        toast.error(t('auth.reset.noToken'))
        return
      }

      try {
        await authService.verifyResetToken(token)
        setIsTokenValid(true)
      } catch (error) {
        console.error('Token verification error:', error)
        setIsTokenValid(false)
        toast.error(t('auth.reset.invalidToast'))
      } finally {
        setIsVerifying(false)
      }
    }

    verifyToken()
    // `t` is stable for a language and changes only when the catalogue does; the verification
    // must not re-run because the reader switched language mid-check.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  // Calculate password strength
  useEffect(() => {
    if (!newPassword) {
      setPasswordStrength(0)
      return
    }

    let strength = 0
    if (newPassword.length >= MIN_PASSWORD_LENGTH) strength += 25
    if (newPassword.length >= 12) strength += 25
    if (/[a-z]/.test(newPassword) && /[A-Z]/.test(newPassword)) strength += 25
    if (/[0-9]/.test(newPassword)) strength += 15
    if (/[^a-zA-Z0-9]/.test(newPassword)) strength += 10

    setPasswordStrength(Math.min(strength, 100))
  }, [newPassword])

  const getPasswordStrengthColor = () => {
    if (passwordStrength < 40) return 'bg-red-500'
    if (passwordStrength < 70) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  const getPasswordStrengthText = () => {
    if (passwordStrength < 40) return t('auth.reset.strengthWeak')
    if (passwordStrength < 70) return t('auth.reset.strengthMedium')
    return t('auth.reset.strengthStrong')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!token) {
      toast.error(t('auth.reset.noToken'))
      return
    }

    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      toast.error(t('auth.validation.tooShortLong', { count: MIN_PASSWORD_LENGTH }))
      return
    }

    if (newPassword !== confirmPassword) {
      toast.error(t('auth.validation.passwordsDiffer'))
      return
    }

    try {
      setIsSubmitting(true)
      await authService.resetPassword(token, newPassword)
      
      toast.success(t('auth.reset.success'))
      
      // Redirect to login page after 2 seconds
      setTimeout(() => {
        navigate('/login')
      }, 2000)
    } catch (error) {
      console.error('Reset password error:', error)
      const errorMessage = getErrorMessage(error, t('auth.reset.failed'))
      toast.error(errorMessage)
    } finally {
      setIsSubmitting(false)
    }
  }

  // Loading state
  if (isVerifying) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-900 via-secondary-900 to-primary-800">
        <div className="text-center">
          <svg
            className="animate-spin h-12 w-12 text-white mx-auto mb-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            ></circle>
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            ></path>
          </svg>
          <p className="text-white text-lg">{t('auth.reset.verifying')}</p>
        </div>
      </div>
    )
  }

  // Invalid token state
  if (!isTokenValid) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-900 via-secondary-900 to-primary-800 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full space-y-8">
          <div className="bg-secondary-800 rounded-lg shadow-xl p-8">
            <div className="text-center">
              <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-red-100 mb-4">
                <XCircleIcon className="h-8 w-8 text-red-600" />
              </div>
              <h2 className="text-3xl font-bold text-white mb-2">
                {t('auth.reset.invalidHeading')}
              </h2>
              <p className="text-secondary-300 mb-6">
                {t('auth.reset.invalidBody', { hours: RESET_LINK_VALID_HOURS })}
              </p>
              <div className="space-y-3">
                <Link
                  to="/forgot-password"
                  className="btn-primary w-full"
                >
                  {t('auth.reset.requestNew')}
                </Link>
                <Link
                  to="/login"
                  className="btn-secondary w-full"
                >
                  {t('auth.backToLogin')}
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Reset password form
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-900 via-secondary-900 to-primary-800 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-4xl font-extrabold text-white">
            {t('auth.reset.heading')}
          </h2>
          <p className="mt-2 text-center text-sm text-secondary-300">
            {t('auth.reset.body')}
          </p>
        </div>

        <div className="bg-secondary-800 rounded-lg shadow-xl p-8">
          <form className="space-y-6" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="new-password" className="form-label">
                {t('auth.reset.newPassword')}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <LockClosedIcon className="h-5 w-5 text-secondary-400" />
                </div>
                <input
                  id="new-password"
                  name="new-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  className="form-input pl-10 pr-10"
                  placeholder={t('auth.reset.newPasswordPlaceholder', { count: MIN_PASSWORD_LENGTH })}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  disabled={isSubmitting}
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

              {/* Password strength indicator */}
              {newPassword && (
                <div className="mt-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-secondary-400">{t('auth.reset.strengthLabel')}</span>
                    <span className={`text-xs font-medium ${
                      passwordStrength < 40 ? 'text-red-400' :
                      passwordStrength < 70 ? 'text-yellow-400' :
                      'text-green-400'
                    }`}>
                      {getPasswordStrengthText()}
                    </span>
                  </div>
                  {/* The bar was a coloured div and nothing else: a screen reader was given the
                      colour, which is to say nothing. It now has a name and a reading, both in
                      the reader's language. */}
                  <div
                    className="w-full bg-secondary-700 rounded-full h-2"
                    role="progressbar"
                    aria-label={t('auth.reset.strengthMeter')}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={passwordStrength}
                    aria-valuetext={getPasswordStrengthText()}
                  >
                    <div
                      className={`h-2 rounded-full transition-all duration-300 ${getPasswordStrengthColor()}`}
                      style={{ width: `${passwordStrength}%` }}
                    ></div>
                  </div>
                </div>
              )}
            </div>

            <div>
              <label htmlFor="confirm-password" className="form-label">
                {t('auth.reset.confirmPassword')}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <LockClosedIcon className="h-5 w-5 text-secondary-400" />
                </div>
                <input
                  id="confirm-password"
                  name="confirm-password"
                  type={showConfirmPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  className="form-input pl-10 pr-10"
                  placeholder={t('auth.reset.confirmPasswordPlaceholder')}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isSubmitting}
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

              {/* Password match indicator */}
              {confirmPassword && (
                <div className="mt-2 flex items-center">
                  {newPassword === confirmPassword ? (
                    <>
                      <CheckCircleIcon className="h-4 w-4 text-green-400 mr-1" />
                      <span className="text-xs text-green-400">{t('auth.reset.passwordsMatch')}</span>
                    </>
                  ) : (
                    <>
                      <XCircleIcon className="h-4 w-4 text-red-400 mr-1" />
                      <span className="text-xs text-red-400">{t('auth.validation.passwordsDiffer')}</span>
                    </>
                  )}
                </div>
              )}
            </div>

            <div>
              <button
                type="submit"
                disabled={isSubmitting || newPassword !== confirmPassword || newPassword.length < MIN_PASSWORD_LENGTH}
                className="btn-primary w-full"
              >
                {isSubmitting ? (
                  <>
                    <svg
                      className="animate-spin -ml-1 mr-3 h-5 w-5 text-white inline"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      ></circle>
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      ></path>
                    </svg>
                    {t('auth.reset.submitting')}
                  </>
                ) : (
                  t('auth.reset.submit')
                )}
              </button>
            </div>
          </form>
        </div>

        <div className="text-center">
          <Link to="/login" className="text-sm text-primary-400 hover:text-primary-300">
            {t('auth.backToLogin')}
          </Link>
        </div>
      </div>
    </div>
  )
}

export default ResetPasswordPage

