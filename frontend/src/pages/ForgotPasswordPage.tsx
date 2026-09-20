import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { EnvelopeIcon, ArrowLeftIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import authService from '@/services/auth.service'
import { getErrorMessage } from '@/utils/errors'
import Emphasised from '@/i18n/Emphasised'
import { useT } from '@/i18n/react'

/**
 * Ask for a password reset link.
 *
 * WHY THE SUCCESS SCREEN IS SHOWN EVEN WHEN THE REQUEST FAILED. The same answer for a known and
 * an unknown address is what stops this form being an account-enumeration oracle. That is a
 * deliberate property of the page and not a swallowed error; the failure is still logged.
 *
 * Every string is in src/i18n/messages/auth.en.ts and auth.fr.ts. The address the reader typed
 * is picked out inside the confirmation sentence rather than glued between two fragments, so
 * the catalogue decides where in the sentence it goes — see src/i18n/Emphasised.tsx.
 */
const ForgotPasswordPage: React.FC = () => {
  const t = useT()
  const [email, setEmail] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isSubmitted, setIsSubmitted] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!email) {
      toast.error(t('auth.forgot.missingEmail'))
      return
    }

    try {
      setIsSubmitting(true)
      const response = await authService.forgotPassword(email)
      
      setIsSubmitted(true)
      toast.success(t('auth.forgot.sent'))
      
      // Log the message for debugging
      console.log('Password reset response:', response.message)
    } catch (error) {
      console.error('Forgot password error:', getErrorMessage(error, 'Request failed'))
      // Even on error, show success message for security (prevent email enumeration)
      setIsSubmitted(true)
      toast.success(t('auth.forgot.sentIfKnown'))
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isSubmitted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-900 via-secondary-900 to-primary-800 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full space-y-8">
          <div className="bg-secondary-800 rounded-lg shadow-xl p-8">
            <div className="text-center">
              <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-green-100 mb-4">
                <EnvelopeIcon className="h-8 w-8 text-green-600" />
              </div>
              <h2 className="text-3xl font-bold text-white mb-2">
                {t('auth.forgot.checkHeading')}
              </h2>
              <p className="text-secondary-300 mb-6">
                <Emphasised
                  sentence={t('auth.forgot.checkBody', { email })}
                  value={email}
                  as="strong"
                  className="text-white"
                />
              </p>
              <div className="bg-secondary-700 border-l-4 border-primary-400 p-4 mb-6">
                <p className="text-sm text-secondary-200">
                  <strong>{t('auth.forgot.notReceivedTitle')}</strong>
                  <br />
                  {t('auth.forgot.notReceivedBody')}
                </p>
              </div>
              <div className="space-y-3">
                <Link
                  to="/login"
                  className="btn-primary w-full flex items-center justify-center"
                >
                  <ArrowLeftIcon className="h-5 w-5 mr-2" />
                  {t('auth.backToLogin')}
                </Link>
                <button
                  onClick={() => {
                    setIsSubmitted(false)
                    setEmail('')
                  }}
                  className="btn-secondary w-full"
                >
                  {t('auth.forgot.tryAnother')}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-900 via-secondary-900 to-primary-800 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-4xl font-extrabold text-white">
            {t('auth.forgot.heading')}
          </h2>
          <p className="mt-2 text-center text-sm text-secondary-300">
            {t('auth.forgot.body')}
          </p>
        </div>

        <div className="bg-secondary-800 rounded-lg shadow-xl p-8">
          <form className="space-y-6" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="email" className="form-label">
                {t('auth.forgot.emailLabel')}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <EnvelopeIcon className="h-5 w-5 text-secondary-400" />
                </div>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  className="form-input pl-10"
                  placeholder={t('auth.forgot.emailPlaceholder')}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>
            </div>

            <div>
              <button
                type="submit"
                disabled={isSubmitting}
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
                    {t('auth.forgot.submitting')}
                  </>
                ) : (
                  t('auth.forgot.submit')
                )}
              </button>
            </div>

            <div className="text-center">
              <Link
                to="/login"
                className="text-sm text-primary-400 hover:text-primary-300 flex items-center justify-center"
              >
                <ArrowLeftIcon className="h-4 w-4 mr-1" />
                {t('auth.backToLogin')}
              </Link>
            </div>
          </form>
        </div>

        <div className="text-center">
          <p className="text-sm text-secondary-400">
            {t('auth.forgot.noAccountPrompt')}{' '}
            <Link to="/register" className="text-primary-400 hover:text-primary-300 font-medium">
              {t('auth.forgot.signUpLink')}
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}

export default ForgotPasswordPage

