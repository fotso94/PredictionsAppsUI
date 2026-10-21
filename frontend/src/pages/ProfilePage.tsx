import React, { useState, useEffect, useRef } from 'react';
import { Helmet } from 'react-helmet-async';
import { userService, type UserProfile, type UpdateProfileRequest } from '@/services/user.service';
import Card from '@/components/ui/Card';
import toast from 'react-hot-toast';
import { getErrorMessage } from '@/utils/errors';
import { backendInstant, formatDate, zoneLabel } from '@/i18n';
import { useT } from '@/i18n/react';
import { useAuth } from '@/hooks/useAuth';

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
 *
 * ── EDIT USED TO SAVE ───────────────────────────────────────────────────────────────────────
 *
 * The action row swapped an unkeyed type="button" Edit for an unkeyed type="submit" Save in the
 * same position. React reused the one <button> and changed its type inside the click, so the
 * browser's default action for that click submitted the form: Edit PUT the unchanged values and
 * closed the editor again, by mouse and by keyboard alike. Now the three buttons carry their own
 * keys, so Save is never the node that was clicked as Edit, Edit's click prevents its default
 * action, and handleSubmit refuses any submit that is not a Save in edit mode.
 *
 * ── WHAT A SAVE SENDS ───────────────────────────────────────────────────────────────────────
 *
 * Every field, explicitly (see toPayload): strings trimmed, and a blank first name, last name or
 * avatar sent as null, which is how the backend's contract clears one. It used to send '' for a
 * name the account never had, which was refused with 422 and took any username change with it.
 * After a save the signed-in user is read again (refreshUser), so the header shows the new name
 * without a reload.
 */

/** The form's own state: what is in each input, always a string. */
interface ProfileForm {
  username: string;
  first_name: string;
  last_name: string;
  avatar_url: string;
}

const toForm = (profile: UserProfile): ProfileForm => ({
  username: profile.username || '',
  first_name: profile.first_name || '',
  last_name: profile.last_name || '',
  avatar_url: profile.avatar_url || '',
});

/** What a save sends: the whole form, trimmed, with a blank optional field as an explicit clear. */
const toPayload = (form: ProfileForm): UpdateProfileRequest => ({
  username: form.username.trim(),
  first_name: form.first_name.trim() || null,
  last_name: form.last_name.trim() || null,
  avatar_url: form.avatar_url.trim() || null,
});

/** Mirror the limits on UserUpdateRequest in backend/app/schemas/users.py. */
const USERNAME_MIN_LENGTH = 3;
const USERNAME_MAX_LENGTH = 50;
const NAME_MAX_LENGTH = 100;
const AVATAR_URL_MAX_LENGTH = 500;

const ProfilePage: React.FC = () => {
  const t = useT();
  const { refreshUser } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [formData, setFormData] = useState<ProfileForm>({
    first_name: '',
    last_name: '',
    username: '',
    avatar_url: '',
  });
  /** Set synchronously when a save starts, so a second submit in the same tick is refused too. */
  const saveInFlight = useRef(false);
  const usernameInput = useRef<HTMLInputElement>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const wasEditing = useRef(false);

  /**
   * Focus follows the mode, so a keyboard reader is never left on a button that just vanished:
   * into the first editable field on Edit, back onto Edit after Save or Cancel.
   */
  useEffect(() => {
    if (isEditing) usernameInput.current?.focus();
    else if (wasEditing.current) editButton.current?.focus();
    wasEditing.current = isEditing;
  }, [isEditing]);

  // Load profile data
  useEffect(() => {
    const loadProfile = async () => {
      try {
        setIsLoading(true);
        const data = await userService.getProfile();
        setProfile(data);
        setFormData(toForm(data));
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
    // Only a Save in edit mode saves: never a submit while the form is read-only, and never a
    // second one while the first is still on its way.
    if (!isEditing || saveInFlight.current) return;
    saveInFlight.current = true;

    try {
      setIsSaving(true);
      const updatedProfile = await userService.updateProfile(toPayload(formData));
      setProfile(updatedProfile);
      // What the server stored, not what was typed: trimmed, and a cleared field empty.
      setFormData(toForm(updatedProfile));
      setIsEditing(false);
      toast.success(t('auth.profile.saved'));
      // The header reads the signed-in user, not this page. The save has already succeeded, so a
      // failed refresh is logged rather than reported as a failed save.
      refreshUser().catch((error) => console.error('Failed to refresh the signed-in user:', error));
    } catch (error) {
      // Still editing, every value kept: the reader can correct, retry or cancel.
      console.error('Failed to update profile:', error);
      const errorMessage = getErrorMessage(error, t('auth.profile.saveFailed'));
      toast.error(errorMessage);
    } finally {
      saveInFlight.current = false;
      setIsSaving(false);
    }
  };

  const handleEdit = (e: React.MouseEvent<HTMLButtonElement>) => {
    // Belt and braces with the keys below: whatever this node becomes, its click submits nothing.
    e.preventDefault();
    setIsEditing(true);
  };

  const handleCancel = () => {
    if (profile) setFormData(toForm(profile));
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
                  <label htmlFor="profile-email" className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.email')}
                  </label>
                  <input
                    id="profile-email"
                    name="email"
                    type="email"
                    autoComplete="email"
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
                  <label htmlFor="profile-username" className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.username')}
                  </label>
                  <input
                    ref={usernameInput}
                    id="profile-username"
                    name="username"
                    type="text"
                    autoComplete="username"
                    required
                    minLength={USERNAME_MIN_LENGTH}
                    maxLength={USERNAME_MAX_LENGTH}
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
                  <label htmlFor="profile-first-name" className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.firstName')}
                  </label>
                  <input
                    id="profile-first-name"
                    name="first_name"
                    type="text"
                    autoComplete="given-name"
                    maxLength={NAME_MAX_LENGTH}
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
                  <label htmlFor="profile-last-name" className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.lastName')}
                  </label>
                  <input
                    id="profile-last-name"
                    name="last_name"
                    type="text"
                    autoComplete="family-name"
                    maxLength={NAME_MAX_LENGTH}
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
                  <label htmlFor="profile-avatar-url" className="block text-sm font-medium text-secondary-300 mb-2">
                    {t('auth.profile.avatarUrl')}
                  </label>
                  <input
                    id="profile-avatar-url"
                    name="avatar_url"
                    type="url"
                    autoComplete="url"
                    maxLength={AVATAR_URL_MAX_LENGTH}
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

                {/* Action Buttons. Each has its own key: unkeyed, Save reused the clicked Edit's
                    node and the click submitted the form (see the note at the top). */}
                <div className="flex gap-4 pt-4">
                  {!isEditing ? (
                    <button
                      key="edit"
                      ref={editButton}
                      type="button"
                      onClick={handleEdit}
                      className="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors"
                    >
                      {t('auth.profile.edit')}
                    </button>
                  ) : (
                    <>
                      <button
                        key="save"
                        type="submit"
                        disabled={isSaving}
                        className="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {t(isSaving ? 'auth.profile.saving' : 'auth.profile.save')}
                      </button>
                      <button
                        key="cancel"
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

