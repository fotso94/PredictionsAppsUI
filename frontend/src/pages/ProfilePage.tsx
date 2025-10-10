import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import { useAuth } from '@/contexts/AuthContext';
import { userService, type UserProfile, type UpdateProfileRequest } from '@/services/user.service';
import Card from '@/components/ui/Card';
import toast from 'react-hot-toast';

const ProfilePage: React.FC = () => {
  const { user } = useAuth();
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
        toast.error('Failed to load profile');
      } finally {
        setIsLoading(false);
      }
    };

    loadProfile();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      setIsSaving(true);
      const updatedProfile = await userService.updateProfile(formData);
      setProfile(updatedProfile);
      setIsEditing(false);
      toast.success('Profile updated successfully');
    } catch (error: any) {
      console.error('Failed to update profile:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to update profile';
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

  if (isLoading) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <div className="text-center text-secondary-400">Loading profile...</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <Helmet>
        <title>Profile - Soccer Predictions</title>
        <meta name="description" content="Manage your profile settings" />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">Profile Settings</h1>
            <p className="text-secondary-400">Manage your account information</p>
          </div>

          <Card className="p-6">
            <form onSubmit={handleSubmit}>
              <div className="space-y-6">
                {/* Email (read-only) */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    Email
                  </label>
                  <input
                    type="email"
                    value={profile?.email || ''}
                    disabled
                    className="w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-secondary-400 cursor-not-allowed"
                  />
                  <p className="mt-1 text-xs text-secondary-500">
                    Email cannot be changed
                  </p>
                </div>

                {/* Username */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    Username
                  </label>
                  <input
                    type="text"
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    disabled={!isEditing}
                    className={`w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white ${
                      isEditing ? '' : 'cursor-not-allowed opacity-75'
                    }`}
                    placeholder="Enter username"
                  />
                </div>

                {/* First Name */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    First Name
                  </label>
                  <input
                    type="text"
                    value={formData.first_name}
                    onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                    disabled={!isEditing}
                    className={`w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white ${
                      isEditing ? '' : 'cursor-not-allowed opacity-75'
                    }`}
                    placeholder="Enter first name"
                  />
                </div>

                {/* Last Name */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    Last Name
                  </label>
                  <input
                    type="text"
                    value={formData.last_name}
                    onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                    disabled={!isEditing}
                    className={`w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white ${
                      isEditing ? '' : 'cursor-not-allowed opacity-75'
                    }`}
                    placeholder="Enter last name"
                  />
                </div>

                {/* Avatar URL */}
                <div>
                  <label className="block text-sm font-medium text-secondary-300 mb-2">
                    Avatar URL
                  </label>
                  <input
                    type="url"
                    value={formData.avatar_url}
                    onChange={(e) => setFormData({ ...formData, avatar_url: e.target.value })}
                    disabled={!isEditing}
                    className={`w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white ${
                      isEditing ? '' : 'cursor-not-allowed opacity-75'
                    }`}
                    placeholder="https://example.com/avatar.jpg"
                  />
                </div>

                {/* Account Info */}
                <div className="pt-4 border-t border-dark-700">
                  <h3 className="text-lg font-semibold text-white mb-4">Account Information</h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-secondary-400">Account Type:</span>
                      <span className="ml-2 text-white capitalize">{profile?.user_type}</span>
                    </div>
                    <div>
                      <span className="text-secondary-400">Status:</span>
                      <span className="ml-2 text-white capitalize">{profile?.account_status}</span>
                    </div>
                    <div>
                      <span className="text-secondary-400">Email Verified:</span>
                      <span className="ml-2 text-white">
                        {profile?.email_verified ? 'Yes' : 'No'}
                      </span>
                    </div>
                    <div>
                      <span className="text-secondary-400">Member Since:</span>
                      <span className="ml-2 text-white">
                        {profile?.created_at
                          ? new Date(profile.created_at).toLocaleDateString()
                          : 'N/A'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex gap-4 pt-4">
                  {!isEditing ? (
                    <button
                      type="button"
                      onClick={() => setIsEditing(true)}
                      className="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors"
                    >
                      Edit Profile
                    </button>
                  ) : (
                    <>
                      <button
                        type="submit"
                        disabled={isSaving}
                        className="px-6 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isSaving ? 'Saving...' : 'Save Changes'}
                      </button>
                      <button
                        type="button"
                        onClick={handleCancel}
                        disabled={isSaving}
                        className="px-6 py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Cancel
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

