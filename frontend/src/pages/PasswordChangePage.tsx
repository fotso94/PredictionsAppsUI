import React, { useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { useNavigate } from 'react-router-dom';
import { userService, type ChangePasswordRequest } from '@/services/user.service';
import Card from '@/components/ui/Card';
import toast from 'react-hot-toast';
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline';
import { getErrorMessage } from '@/utils/errors';
import { useT } from '@/i18n/react';

/**
 * Change a password while signed in.
 *
 * The rule under the new-password field counts: "at least 8 characters" and "at least 1
 * character" are different sentences, and French puts 0 with the singular too. So the minimum is
 * a named constant the sentence is given, not a digit written into two catalogues — see
 * src/i18n/messages/auth.en.ts, which states the plural branches around the hole.
 */

/** Mirrors `min_length=8` on the change-password fields in backend/app/schemas/users.py:75. */
const MIN_PASSWORD_LENGTH = 8;

const PasswordChangePage: React.FC = () => {
  const t = useT();
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
      toast.error(t('auth.validation.newPasswordsDiffer'));
      return;
    }

    // Validate password strength
    if (formData.new_password.length < MIN_PASSWORD_LENGTH) {
      toast.error(t('auth.validation.tooShort', { count: MIN_PASSWORD_LENGTH }));
      return;
    }

    try {
      setIsSubmitting(true);
      await userService.changePassword(formData);
      toast.success(t('auth.change.success'));
      
      // Redirect to login after 2 seconds
      setTimeout(() => {
        navigate('/login');
      }, 2000);
    } catch (error) {
      console.error('Failed to change password:', error);
      const errorMessage = getErrorMessage(error, t('auth.change.failed'));
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
        <title>{t('auth.change.documentTitle')}</title>
        <meta name="description" content={t('auth.change.documentDescription')} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-2xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">{t('auth.change.heading')}</h1>
            <p className="text-secondary-400">{t('auth.change.subheading')}</p>
          </div>

          <Card className="p-6">
            <form onSubmit={handleSubmit}>
              <div className="space-y-6">
                {/* Current Password */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.change.current')}
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
                      placeholder={t('auth.change.currentPlaceholder')}
                    />
                    <button
                      type="button"
                      onClick={() => togglePasswordVisibility('current')}
                      aria-label={t(showPasswords.current ? 'auth.field.hidePassword' : 'auth.field.showPassword')}
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
                    {t('auth.change.new')}
                  </label>
                  <div className="relative">
                    <input
                      type={showPasswords.new ? 'text' : 'password'}
                      value={formData.new_password}
                      onChange={(e) =>
                        setFormData({ ...formData, new_password: e.target.value })
                      }
                      required
                      minLength={MIN_PASSWORD_LENGTH}
                      className="w-full px-4 py-2 pr-10 bg-dark-800 border border-dark-700 rounded-lg text-white"
                      placeholder={t('auth.change.newPlaceholder')}
                    />
                    <button
                      type="button"
                      onClick={() => togglePasswordVisibility('new')}
                      aria-label={t(showPasswords.new ? 'auth.field.hidePassword' : 'auth.field.showPassword')}
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
                    {t('auth.change.rules', { count: MIN_PASSWORD_LENGTH })}
                  </p>
                </div>

                {/* Confirm New Password */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.change.confirm')}
                  </label>
                  <div className="relative">
                    <input
                      type={showPasswords.confirm ? 'text' : 'password'}
                      value={formData.confirm_password}
                      onChange={(e) =>
                        setFormData({ ...formData, confirm_password: e.target.value })
                      }
                      required
                      minLength={MIN_PASSWORD_LENGTH}
                      className="w-full px-4 py-2 pr-10 bg-dark-800 border border-dark-700 rounded-lg text-white"
                      placeholder={t('auth.change.confirmPlaceholder')}
                    />
                    <button
                      type="button"
                      onClick={() => togglePasswordVisibility('confirm')}
                      aria-label={t(showPasswords.confirm ? 'auth.field.hidePassword' : 'auth.field.showPassword')}
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
                    <strong>{t('auth.change.noteLabel')}</strong> {t('auth.change.note')}
                  </p>
                </div>

                {/* Action Buttons */}
                <div className="flex gap-4 pt-4">
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {t(isSubmitting ? 'auth.change.submitting' : 'auth.change.submit')}
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate(-1)}
                    disabled={isSubmitting}
                    className="px-6 py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {t('auth.cancel')}
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

