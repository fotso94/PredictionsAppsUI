import React, { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import { useAuth } from '@/contexts/AuthContext'
import toast from 'react-hot-toast'

const RegisterPage: React.FC = () => {
  const { register, isAuthenticated, isLoading } = useAuth()
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

  // Redirect if already authenticated
  if (isAuthenticated) {
    return <Navigate to="/" replace />
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
        password: formData.password,
        first_name: formData.firstName,
        last_name: formData.lastName,
      })
      // Navigation is handled by AuthContext
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
              <Link to="/login" className="text-primary-400 hover:text-primary-300">
                Sign in
              </Link>
            </p>
          </div>

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
