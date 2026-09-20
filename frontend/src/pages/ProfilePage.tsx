import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import { userService, type UserProfile, type UpdateProfileRequest } from '@/services/user.service';
import Card from '@/components/ui/Card';
import toast from 'react-hot-toast';
import { getErrorMessage } from '@/utils/errors';
import { backendInstant, formatDate, zoneLabel } from '@/i18n';
import { useT } from '@/i18n/react';

/**
 * The reader's own account details.
 *
 * ── "MEMBER SINCE" WAS WRONG IN THREE WAYS AT ONCE ──────────────────────────────────────────
 *
 * It was `new Date(profile.created_at).toLocaleDateString()`, which:
 *
 *   1. read the timestamp in the DEVICE's zone. This backend writes `created_at` with
 *      `datetime.utcnow()` into a column with no zone (backend/app/models/base.py:34), so what
 *      arrives has no offset on it — and ECMAScript reads an offset-less date-TIME string as
 *      local time. A reader in Douala was shown a date the server never recorded.
 *   2. formatted it in the DEVICE's zone as well, ignoring the zone the reader chose in the
 *      settings panel, which every kick-off time on this site already honours.
 *   3. formatted it in the DEVICE's locale, so a French reader with an American laptop got
 *      "1/5/2026" — a date that does not even mean the same day here as it does there.
 *
 * `backendInstant` reads it as the UTC the server actually wrote and says whether the payload
 * said so; `formatDate` spells it out in the reader's language and their chosen zone. Because
 * the UTC reading is a claim about the backend rather than something the payload states, the
 * page says so underneath rather than leaving the reader to assume.
 *
 * ── WHAT IS NOT TRANSLATED ──────────────────────────────────────────────────────────────────
 *
 * The account type and the account status are the backend's own words, rendered as it sent them.
 */
const ProfilePage: React.FC = () => {
  const t = useT();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [formData, setFormData] = useState<UpdateProfileRequest>({
    first_name: '',
    last_name: '',
    username: '',
    avatar_url: '',
  });

  // Load profile data
  useEffect(() => {
    const loadProfile = async () => {
      try {
        setIsLoading(true);
        const data = await userService.getProfile();
        setProfile(data);
        setFormData({
          first_name: data.first_name || '',
          last_name: data.last_name || '',
          username: data.username || '',
          avatar_url: data.avatar_url || '',
        });
      } catch (error) {
        console.error('Failed to load profile:', error);
        toast.error(t('auth.profile.loadFailed'));
      } finally {
        setIsLoading(false);
      }
    };

    loadProfile();
    // Loaded once. `t` is only here for the failure toast and must not re-fetch the profile
    // because the reader changed language.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      setIsSaving(true);
      const updatedProfile = await userService.updateProfile(formData);
      setProfile(updatedProfile);
      setIsEditing(false);
      toast.success(t('auth.profile.saved'));
    } catch (error) {
      console.error('Failed to update profile:', error);
      const errorMessage = getErrorMessage(error, t('auth.profile.saveFailed'));
      toast.error(errorMessage);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    if (profile) {
      setFormData({
        first_name: profile.first_name || '',
        last_name: profile.last_name || '',
        username: profile.username || '',
        avatar_url: profile.avatar_url || '',
      });
    }
    setIsEditing(false);
  };

  /**
   * When this account was created, and whether the payload actually said which zone that was in.
   *
   * Read before the early return so both branches below see the same value.
   */
  const joined = backendInstant(profile?.created_at);
  const memberSince = formatDate(joined.at);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <div className="text-center text-secondary-400">{t('auth.profile.loading')}</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <Helmet>
        <title>{t('auth.profile.documentTitle')}</title>
        <meta name="description" content={t('auth.profile.documentDescription')} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">{t('auth.profile.heading')}</h1>
            <p className="text-secondary-400">{t('auth.profile.subheading')}</p>
          </div>

          <Card className="p-6">
            <form onSubmit={handleSubmit}>
              <div className="space-y-6">
                {/* Email (read-only) */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.email')}
                  </label>
                  <input
                    type="email"
                    value={profile?.email || ''}
                    disabled
                    className="w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-secondary-400 cursor-not-allowed"
                  />
                  <p className="mt-1 text-xs text-secondary-500">
                    {t('auth.profile.emailFixed')}
                  </p>
                </div>

                {/* Username */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.username')}
                  </label>
                  <input
                    type="text"
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    disabled={!isEditing}
                    className={`w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white ${
                      isEditing ? '' : 'cursor-not-allowed opacity-75'
                    }`}
                    placeholder={t('auth.profile.usernamePlaceholder')}
                  />
                </div>

                {/* First Name */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.firstName')}
                  </label>
                  <input
                    type="text"
                    value={formData.first_name}
                    onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                    disabled={!isEditing}
                    className={`w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white ${
                      isEditing ? '' : 'cursor-not-allowed opacity-75'
                    }`}
                    placeholder={t('auth.profile.firstNamePlaceholder')}
                  />
                </div>

                {/* Last Name */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.lastName')}
                  </label>
                  <input
                    type="text"
                    value={formData.last_name}
                    onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                    disabled={!isEditing}
                    className={`w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white ${
                      isEditing ? '' : 'cursor-not-allowed opacity-75'
                    }`}
                    placeholder={t('auth.profile.lastNamePlaceholder')}
                  />
                </div>

                {/* Avatar URL */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.avatarUrl')}
                  </label>
                  <input
                    type="url"
                    value={formData.avatar_url}
                    onChange={(e) => setFormData({ ...formData, avatar_url: e.target.value })}
                    disabled={!isEditing}
                    className={`w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white ${
                      isEditing ? '' : 'cursor-not-allowed opacity-75'
                    }`}
                    /* An example URL, not a sentence. It reads the same in both languages and
                       is deliberately not in the catalogue. */
                    placeholder="https://example.com/avatar.jpg"
                  />
                </div>

                {/* Account Info */}
                <div className="pt-4 border-t border-dark-700">
                  <h3 className="text-lg font-semibold text-white mb-4">{t('auth.profile.accountHeading')}</h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-secondary-400">{t('auth.profile.accountType')}</span>
                      {/* The backend's own word for it, in every language. */}
                      <span className="ml-2 text-white capitalize">{profile?.user_type}</span>
                    </div>
                    <div>
                      <span className="text-secondary-400">{t('auth.profile.status')}</span>
                      <span className="ml-2 text-white capitalize">{profile?.account_status}</span>
                    </div>
                    <div>
                      <span className="text-secondary-400">{t('auth.profile.emailVerified')}</span>
                      <span className="ml-2 text-white">
                        {t(profile?.email_verified ? 'auth.profile.yes' : 'auth.profile.no')}
                      </span>
                    </div>
                    <div>
                      <span className="text-secondary-400">{t('auth.profile.memberSince')}</span>
                      <span className="ml-2 text-white" data-testid="profile-member-since">
                        {memberSince ?? t('auth.profile.unknownDate')}
                      </span>
                    </div>
                  </div>
                  {/*
                    Said, not implied. The server sent this timestamp with no zone on it, so the
                    date above rests on reading it as the UTC the server wrote and then showing
                    it in the zone the reader chose — two claims, both of which can move the date
                    by a day.
                  */}
                  {memberSince && !joined.anchored && (
                    <p className="mt-3 text-xs text-secondary-500" data-testid="profile-member-since-note">
                      {t('auth.profile.memberSinceUnzoned', { zone: zoneLabel() })}
                    </p>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex gap-4 pt-4">
                  {!isEditing ? (
                    <button
                      type="button"
                      onClick={() => setIsEditing(true)}
                      className="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors"
                    >
                      {t('auth.profile.edit')}
                    </button>
                  ) : (
                    <>
                      <button
                        type="submit"
                        disabled={isSaving}
                        className="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {t(isSaving ? 'auth.profile.saving' : 'auth.profile.save')}
                      </button>
                      <button
                        type="button"
                        onClick={handleCancel}
                        disabled={isSaving}
                        className="px-6 py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {t('auth.cancel')}
                      </button>
                    </>
                  )}
                </div>
              </div>
            </form>
          </Card>
        </div>
      </div>
    </>
  );
};

export default ProfilePage;

