import React, { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { LockClosedIcon, EyeIcon, EyeSlashIcon, CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import authService from '@/services/auth.service'

const ResetPasswordPage: React.FC = () => {
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
        toast.error('No reset token provided')
        return
      }

      try {
        await authService.verifyResetToken(token)
        setIsTokenValid(true)
      } catch (error) {
        console.error('Token verification error:', error)
        setIsTokenValid(false)
        toast.error('This password reset link is invalid or has expired.')
      } finally {
        setIsVerifying(false)
      }
    }

    verifyToken()
  }, [token])

  // Calculate password strength
  useEffect(() => {
    if (!newPassword) {
      setPasswordStrength(0)
      return
    }

    let strength = 0
    if (newPassword.length >= 8) strength += 25
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
    if (passwordStrength < 40) return 'Weak'
    if (passwordStrength < 70) return 'Medium'
    return 'Strong'
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!token) {
      toast.error('No reset token provided')
      return
    }

    if (newPassword.length < 8) {
      toast.error('Password must be at least 8 characters long')
      return
    }

    if (newPassword !== confirmPassword) {
      toast.error('Passwords do not match')
      return
    }

    try {
      setIsSubmitting(true)
      await authService.resetPassword(token, newPassword)
      
      toast.success('Password reset successful! Please log in with your new password.')
      
      // Redirect to login page after 2 seconds
      setTimeout(() => {
        navigate('/login')
      }, 2000)
    } catch (error: any) {
      console.error('Reset password error:', error)
      const errorMessage = error.response?.data?.detail || 'Failed to reset password. Please try again.'
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
          <p className="text-white text-lg">Verifying reset link...</p>
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
                Invalid Reset Link
              </h2>
              <p className="text-secondary-300 mb-6">
                This password reset link is invalid or has expired. Reset links are only valid for 1 hour.
              </p>
              <div className="space-y-3">
                <Link
                  to="/forgot-password"
                  className="btn-primary w-full"
                >
                  Request New Reset Link
                </Link>
                <Link
                  to="/login"
                  className="btn-secondary w-full"
                >
                  Back to Login
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
            Reset Your Password
          </h2>
          <p className="mt-2 text-center text-sm text-secondary-300">
            Enter your new password below
          </p>
        </div>

        <div className="bg-secondary-800 rounded-lg shadow-xl p-8">
          <form className="space-y-6" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="new-password" className="form-label">
                New Password
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
                  placeholder="Enter new password (min. 8 characters)"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  disabled={isSubmitting}
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

              {/* Password strength indicator */}
              {newPassword && (
                <div className="mt-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-secondary-400">Password Strength:</span>
                    <span className={`text-xs font-medium ${
                      passwordStrength < 40 ? 'text-red-400' :
                      passwordStrength < 70 ? 'text-yellow-400' :
                      'text-green-400'
                    }`}>
                      {getPasswordStrengthText()}
                    </span>
                  </div>
                  <div className="w-full bg-secondary-700 rounded-full h-2">
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
                Confirm New Password
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
                  placeholder="Confirm new password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isSubmitting}
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

              {/* Password match indicator */}
              {confirmPassword && (
                <div className="mt-2 flex items-center">
                  {newPassword === confirmPassword ? (
                    <>
                      <CheckCircleIcon className="h-4 w-4 text-green-400 mr-1" />
                      <span className="text-xs text-green-400">Passwords match</span>
                    </>
                  ) : (
                    <>
                      <XCircleIcon className="h-4 w-4 text-red-400 mr-1" />
                      <span className="text-xs text-red-400">Passwords do not match</span>
                    </>
                  )}
                </div>
              )}
            </div>

            <div>
              <button
                type="submit"
                disabled={isSubmitting || newPassword !== confirmPassword || newPassword.length < 8}
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
                    Resetting Password...
                  </>
                ) : (
                  'Reset Password'
                )}
              </button>
            </div>
          </form>
        </div>

        <div className="text-center">
          <Link to="/login" className="text-sm text-primary-400 hover:text-primary-300">
            Back to Login
          </Link>
        </div>
      </div>
    </div>
  )
}

export default ResetPasswordPage

