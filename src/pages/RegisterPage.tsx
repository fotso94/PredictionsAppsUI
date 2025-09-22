import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { EyeIcon, EyeSlashIcon, EnvelopeIcon, LockClosedIcon, UserIcon } from '@heroicons/react/24/outline';
import Container from '../components/layout/Container';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';

interface RegisterFormData {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  confirmPassword: string;
  agreeToTerms: boolean;
  subscribeNewsletter: boolean;
}

interface FormErrors {
  firstName?: string;
  lastName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
  agreeToTerms?: string;
  general?: string;
}

const RegisterPage: React.FC = () => {
  const [formData, setFormData] = useState<RegisterFormData>({
    firstName: '',
    lastName: '',
    email: '',
    password: '',
    confirmPassword: '',
    agreeToTerms: false,
    subscribeNewsletter: true,
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    // First name validation
    if (!formData.firstName.trim()) {
      newErrors.firstName = 'First name is required';
    } else if (formData.firstName.trim().length < 2) {
      newErrors.firstName = 'First name must be at least 2 characters';
    }

    // Last name validation
    if (!formData.lastName.trim()) {
      newErrors.lastName = 'Last name is required';
    } else if (formData.lastName.trim().length < 2) {
      newErrors.lastName = 'Last name must be at least 2 characters';
    }

    // Email validation
    if (!formData.email) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email address';
    }

    // Password validation
    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    } else if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(formData.password)) {
      newErrors.password = 'Password must contain at least one uppercase letter, one lowercase letter, and one number';
    }

    // Confirm password validation
    if (!formData.confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
    } else if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    // Terms agreement validation
    if (!formData.agreeToTerms) {
      newErrors.agreeToTerms = 'You must agree to the terms and conditions';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) return;

    setIsLoading(true);
    setErrors({});

    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // Mock registration logic
      console.log('Registration successful', formData);
      // In real app: navigate('/login') with success message
      
    } catch (error) {
      setErrors({ general: 'An error occurred during registration. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputChange = (field: keyof RegisterFormData, value: string | boolean) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear field error when user starts typing
    if (errors[field as keyof FormErrors]) {
      setErrors(prev => ({ ...prev, [field]: undefined }));
    }
  };

  const getPasswordStrength = (password: string): { strength: number; label: string; color: string } => {
    let strength = 0;
    if (password.length >= 8) strength++;
    if (/[a-z]/.test(password)) strength++;
    if (/[A-Z]/.test(password)) strength++;
    if (/\d/.test(password)) strength++;
    if (/[^a-zA-Z\d]/.test(password)) strength++;

    if (strength <= 2) return { strength, label: 'Weak', color: 'bg-danger-500' };
    if (strength <= 3) return { strength, label: 'Fair', color: 'bg-warning-500' };
    if (strength <= 4) return { strength, label: 'Good', color: 'bg-success-500' };
    return { strength, label: 'Strong', color: 'bg-success-600' };
  };

  const passwordStrength = getPasswordStrength(formData.password);

  return (
    <>
      <Helmet>
        <title>Create Account - PredictionsApp</title>
        <meta name="description" content="Join PredictionsApp today and get access to expert soccer predictions, betting tips, and exclusive insights from professional analysts." />
        <meta name="robots" content="noindex, nofollow" />
      </Helmet>

      <div className="min-h-screen bg-dark-900 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <Container maxWidth="md">
          <div className="bg-dark-800 border border-dark-700 rounded-lg shadow-xl p-8">
            {/* Header */}
            <div className="text-center mb-8">
              <div className="flex justify-center mb-4">
                <div className="w-16 h-16 bg-gradient-to-r from-primary-600 to-success-600 rounded-xl flex items-center justify-center">
                  <span className="text-2xl">⚽</span>
                </div>
              </div>
              <h1 className="text-3xl font-bold text-white mb-2">Create Your Account</h1>
              <p className="text-dark-300">Join thousands of successful bettors today</p>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* General Error */}
              {errors.general && (
                <div className="p-4 bg-danger-600/10 border border-danger-600/20 rounded-lg">
                  <p className="text-sm text-danger-400">{errors.general}</p>
                </div>
              )}

              {/* Name Fields */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="firstName" className="block text-sm font-medium text-dark-300 mb-2">
                    First Name
                  </label>
                  <Input
                    id="firstName"
                    type="text"
                    value={formData.firstName}
                    onChange={(value) => handleInputChange('firstName', value)}
                    placeholder="Enter your first name"
                    error={errors.firstName}
                    icon={<UserIcon className="w-5 h-5" />}
                    autoComplete="given-name"
                    required
                  />
                </div>

                <div>
                  <label htmlFor="lastName" className="block text-sm font-medium text-dark-300 mb-2">
                    Last Name
                  </label>
                  <Input
                    id="lastName"
                    type="text"
                    value={formData.lastName}
                    onChange={(value) => handleInputChange('lastName', value)}
                    placeholder="Enter your last name"
                    error={errors.lastName}
                    icon={<UserIcon className="w-5 h-5" />}
                    autoComplete="family-name"
                    required
                  />
                </div>
              </div>

              {/* Email Field */}
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-dark-300 mb-2">
                  Email Address
                </label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={(value) => handleInputChange('email', value)}
                  placeholder="Enter your email"
                  error={errors.email}
                  icon={<EnvelopeIcon className="w-5 h-5" />}
                  autoComplete="email"
                  required
                />
              </div>

              {/* Password Field */}
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-dark-300 mb-2">
                  Password
                </label>
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={formData.password}
                  onChange={(value) => handleInputChange('password', value)}
                  placeholder="Create a strong password"
                  error={errors.password}
                  icon={<LockClosedIcon className="w-5 h-5" />}
                  rightIcon={
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="text-dark-400 hover:text-dark-300 transition-colors duration-200"
                    >
                      {showPassword ? (
                        <EyeSlashIcon className="w-5 h-5" />
                      ) : (
                        <EyeIcon className="w-5 h-5" />
                      )}
                    </button>
                  }
                  autoComplete="new-password"
                  required
                />
                
                {/* Password Strength Indicator */}
                {formData.password && (
                  <div className="mt-2">
                    <div className="flex items-center space-x-2">
                      <div className="flex-1 h-2 bg-dark-700 rounded-full overflow-hidden">
                        <div 
                          className={`h-full transition-all duration-300 ${passwordStrength.color}`}
                          style={{ width: `${(passwordStrength.strength / 5) * 100}%` }}
                        />
                      </div>
                      <span className={`text-xs font-medium ${
                        passwordStrength.strength <= 2 ? 'text-danger-400' :
                        passwordStrength.strength <= 3 ? 'text-warning-400' : 'text-success-400'
                      }`}>
                        {passwordStrength.label}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Confirm Password Field */}
              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-dark-300 mb-2">
                  Confirm Password
                </label>
                <Input
                  id="confirmPassword"
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={formData.confirmPassword}
                  onChange={(value) => handleInputChange('confirmPassword', value)}
                  placeholder="Confirm your password"
                  error={errors.confirmPassword}
                  icon={<LockClosedIcon className="w-5 h-5" />}
                  rightIcon={
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="text-dark-400 hover:text-dark-300 transition-colors duration-200"
                    >
                      {showConfirmPassword ? (
                        <EyeSlashIcon className="w-5 h-5" />
                      ) : (
                        <EyeIcon className="w-5 h-5" />
                      )}
                    </button>
                  }
                  autoComplete="new-password"
                  required
                />
              </div>

              {/* Checkboxes */}
              <div className="space-y-4">
                <div className="flex items-start">
                  <input
                    id="agreeToTerms"
                    type="checkbox"
                    checked={formData.agreeToTerms}
                    onChange={(e) => handleInputChange('agreeToTerms', e.target.checked)}
                    className="w-4 h-4 text-primary-600 bg-dark-700 border-dark-600 rounded focus:ring-primary-500 focus:ring-2 mt-1"
                  />
                  <label htmlFor="agreeToTerms" className="ml-3 text-sm text-dark-300">
                    I agree to the{' '}
                    <Link to="/terms" className="text-primary-400 hover:text-primary-300">
                      Terms of Service
                    </Link>{' '}
                    and{' '}
                    <Link to="/privacy" className="text-primary-400 hover:text-primary-300">
                      Privacy Policy
                    </Link>
                  </label>
                </div>
                {errors.agreeToTerms && (
                  <p className="text-sm text-danger-400 ml-7">{errors.agreeToTerms}</p>
                )}

                <div className="flex items-start">
                  <input
                    id="subscribeNewsletter"
                    type="checkbox"
                    checked={formData.subscribeNewsletter}
                    onChange={(e) => handleInputChange('subscribeNewsletter', e.target.checked)}
                    className="w-4 h-4 text-primary-600 bg-dark-700 border-dark-600 rounded focus:ring-primary-500 focus:ring-2 mt-1"
                  />
                  <label htmlFor="subscribeNewsletter" className="ml-3 text-sm text-dark-300">
                    Subscribe to our newsletter for the latest predictions and betting tips
                  </label>
                </div>
              </div>

              {/* Submit Button */}
              <Button
                type="submit"
                variant="primary"
                size="lg"
                fullWidth
                isLoading={isLoading}
                disabled={isLoading}
              >
                {isLoading ? 'Creating Account...' : 'Create Account'}
              </Button>
            </form>

            {/* Sign In Link */}
            <div className="mt-8 text-center">
              <p className="text-sm text-dark-400">
                Already have an account?{' '}
                <Link
                  to="/login"
                  className="text-primary-400 hover:text-primary-300 font-medium transition-colors duration-200"
                >
                  Sign in here
                </Link>
              </p>
            </div>
          </div>
        </Container>
      </div>
    </>
  );
};

export default RegisterPage;
