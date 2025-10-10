import React, { useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { useNavigate } from 'react-router-dom';
import { userService, type ChangePasswordRequest } from '@/services/user.service';
import Card from '@/components/ui/Card';
import toast from 'react-hot-toast';
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline';

const PasswordChangePage: React.FC = () => {
  const navigate = useNavigate();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false,
  });
  const [formData, setFormData] = useState<ChangePasswordRequest>({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate passwords match
    if (formData.new_password !== formData.confirm_password) {
      toast.error('New passwords do not match');
      return;
    }

    // Validate password strength
    if (formData.new_password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    try {
      setIsSubmitting(true);
      await userService.changePassword(formData);
      toast.success('Password changed successfully. You have been logged out from all devices.');
      
      // Redirect to login after 2 seconds
      setTimeout(() => {
        navigate('/login');
      }, 2000);
    } catch (error: any) {
      console.error('Failed to change password:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to change password';
      toast.error(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  const togglePasswordVisibility = (field: 'current' | 'new' | 'confirm') => {
    setShowPasswords((prev) => ({ ...prev, [field]: !prev[field] }));
  };

  return (
    <>
      <Helmet>
        <title>Change Password - Soccer Predictions</title>
        <meta name="description" content="Change your account password" />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-2xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">Change Password</h1>
            <p className="text-secondary-400">Update your account password</p>
          </div>

          <Card className="p-6">
            <form onSubmit={handleSubmit}>
              <div className="space-y-6">
                {/* Current Password */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    Current Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPasswords.current ? 'text' : 'password'}
                      value={formData.current_password}
                      onChange={(e) =>
                        setFormData({ ...formData, current_password: e.target.value })
                      }
                      required
                      className="w-full px-4 py-2 pr-10 bg-dark-800 border border-dark-700 rounded-lg text-white"
                      placeholder="Enter current password"
                    />
                    <button
                      type="button"
                      onClick={() => togglePasswordVisibility('current')}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-secondary-400 hover:text-secondary-300"
                    >
                      {showPasswords.current ? (
                        <EyeSlashIcon className="h-5 w-5" />
                      ) : (
                        <EyeIcon className="h-5 w-5" />
                      )}
                    </button>
                  </div>
                </div>

                {/* New Password */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    New Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPasswords.new ? 'text' : 'password'}
                      value={formData.new_password}
                      onChange={(e) =>
                        setFormData({ ...formData, new_password: e.target.value })
                      }
                      required
                      minLength={8}
                      className="w-full px-4 py-2 pr-10 bg-dark-800 border border-dark-700 rounded-lg text-white"
                      placeholder="Enter new password"
                    />
                    <button
                      type="button"
                      onClick={() => togglePasswordVisibility('new')}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-secondary-400 hover:text-secondary-300"
                    >
                      {showPasswords.new ? (
                        <EyeSlashIcon className="h-5 w-5" />
                      ) : (
                        <EyeIcon className="h-5 w-5" />
                      )}
                    </button>
                  </div>
                  <p className="mt-1 text-xs text-secondary-500">
                    Must be at least 8 characters with uppercase, lowercase, and number
                  </p>
                </div>

                {/* Confirm New Password */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    Confirm New Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPasswords.confirm ? 'text' : 'password'}
                      value={formData.confirm_password}
                      onChange={(e) =>
                        setFormData({ ...formData, confirm_password: e.target.value })
                      }
                      required
                      minLength={8}
                      className="w-full px-4 py-2 pr-10 bg-dark-800 border border-dark-700 rounded-lg text-white"
                      placeholder="Confirm new password"
                    />
                    <button
                      type="button"
                      onClick={() => togglePasswordVisibility('confirm')}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-secondary-400 hover:text-secondary-300"
                    >
                      {showPasswords.confirm ? (
                        <EyeSlashIcon className="h-5 w-5" />
                      ) : (
                        <EyeIcon className="h-5 w-5" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Warning */}
                <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-4">
                  <p className="text-sm text-yellow-200">
                    <strong>Note:</strong> Changing your password will log you out from all devices.
                    You will need to log in again with your new password.
                  </p>
                </div>

                {/* Action Buttons */}
                <div className="flex gap-4 pt-4">
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSubmitting ? 'Changing Password...' : 'Change Password'}
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate(-1)}
                    disabled={isSubmitting}
                    className="px-6 py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </form>
          </Card>
        </div>
      </div>
    </>
  );
};

export default PasswordChangePage;

