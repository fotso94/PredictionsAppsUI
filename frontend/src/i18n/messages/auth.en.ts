/**
 * English — the AUTH AND ACCOUNT area: sign in, register, forgotten password, reset password,
 * change password, profile, subscription.
 *
 * EVERY VALUE HERE IS THE EXACT STRING THOSE SCREENS ALREADY SHIPPED, character for character,
 * with one class of exception recorded below. Localising a product is not a licence to reword
 * it, and the live browser suite pins some of these sentences (`create a new account`, the
 * save-intent notice) by their English.
 *
 * THE EXCEPTION: AGREEMENT. Four strings interpolated a count and were frozen at the plural —
 * "1 predictions/day", "1 days history", "min. 1 characters", "valid for 1 hours". Those were
 * wrong in English too, and the whole point of this package is that a count-bearing sentence
 * states its own branches. They are plurals now, so English reads "1 prediction/day" where it
 * used to read "1 predictions/day". Nothing else about them changed.
 *
 * WHY SOME NEARLY-IDENTICAL STRINGS HAVE TWO KEYS. `auth.field.email` is "Email address" and
 * `auth.forgot.emailLabel` is "Email Address"; one validation toast ends "characters long" and
 * another ends "characters". Those differences shipped, and unifying them here would be a copy
 * change smuggled in under a translation change. They are two keys.
 *
 * WHAT IS NOT IN HERE, DELIBERATELY:
 *   - the backend's own words. `tier.name`, `tier.description`, the subscription status, the
 *     account type and the message a successful tier change returns are all rendered verbatim,
 *     in every language. Translating a server's message is putting words in its mouth.
 *   - a number. "8 characters", "1 hour" and the tier limits are values the component passes in
 *     from a named constant or from the payload (see MIN_PASSWORD_LENGTH in RegisterPage.tsx and
 *     RESET_LINK_VALID_HOURS in ResetPasswordPage.tsx, both of which cite the backend line they
 *     mirror). Nothing counts anything in this file.
 *   - a currency symbol or a date. `formatMoney` and `formatDate` in ../index.ts own those, in
 *     the reader's locale and their chosen time zone.
 */

const auth = {
  // ─── fields and controls the forms share ────────────────────────────────────────────────
  'auth.field.email': 'Email address',
  'auth.field.emailPlaceholder': 'Enter your email',
  'auth.field.password': 'Password',
  'auth.field.passwordPlaceholder': 'Enter your password',
  /** The eye button had no accessible name at all. These are the first it has had. */
  'auth.field.showPassword': 'Show password',
  'auth.field.hidePassword': 'Hide password',
  'auth.backToLogin': 'Back to Login',
  'auth.cancel': 'Cancel',

  // Validation. Two shapes of the same rule, because two shapes of it shipped.
  'auth.validation.passwordsDiffer': 'Passwords do not match',
  'auth.validation.newPasswordsDiffer': 'New passwords do not match',
  'auth.validation.tooShortLong': 'Password must be at least {count, plural, one {# character} other {# characters}} long',
  'auth.validation.tooShort': 'Password must be at least {count, plural, one {# character} other {# characters}}',

  // ─── sign in ────────────────────────────────────────────────────────────────────────────
  'auth.login.documentTitle': 'Sign In - Soccer Predictions',
  'auth.login.documentDescription': 'Sign in to your Soccer Predictions account to access premium features and personalized predictions.',
  'auth.login.heading': 'Sign in to your account',
  'auth.login.newAccountPrompt': 'Or',
  'auth.login.newAccountLink': 'create a new account',
  'auth.login.rememberMe': 'Remember me',
  'auth.login.forgotPassword': 'Forgot your password?',
  'auth.login.submit': 'Sign in',
  'auth.login.submitting': 'Signing in...',

  /**
   * Why the visitor is on this form at all.
   *
   * ONE SENTENCE WITH THE MATCH IN IT, not a prefix and a suffix with the match glued between
   * them. The fixture's name is emphasised on screen, and the component finds it inside the
   * rendered sentence to do that (see ../Emphasised.tsx) — so the hole can sit wherever the
   * language puts it rather than wherever English put it.
   */
  'auth.saveIntent.signIn': 'Saving a match needs an account. Sign in and we will finish saving {match} and take you back to where you were.',
  'auth.saveIntent.register': 'Saving a match needs an account. Create one and we will finish saving {match} and take you back to where you were.',
  /** When the handoff carried no label. Never a team name: those are the provider's. */
  'auth.saveIntent.thatMatch': 'that match',

  // ─── create an account ──────────────────────────────────────────────────────────────────
  'auth.register.documentTitle': 'Create Account - Soccer Predictions',
  'auth.register.documentDescription': 'Create your Soccer Predictions account to access premium features and personalized predictions.',
  'auth.register.heading': 'Create your account',
  'auth.register.haveAccountPrompt': 'Already have an account?',
  'auth.register.signInLink': 'Sign in',
  'auth.register.firstName': 'First name',
  'auth.register.firstNamePlaceholder': 'First name',
  'auth.register.lastName': 'Last name',
  'auth.register.lastNamePlaceholder': 'Last name',
  'auth.register.username': 'Username',
  'auth.register.usernamePlaceholder': 'Choose a username',
  'auth.register.passwordPlaceholder': 'Create a password',
  'auth.register.confirmPassword': 'Confirm password',
  'auth.register.confirmPasswordPlaceholder': 'Confirm your password',
  /**
   * The consent line, in three pieces because two links sit inside it.
   *
   * The pieces are not "I agree to the" + link + "and" + link translated word by word: French
   * agrees its article with the noun that FOLLOWS it, and the two nouns disagree — « les
   * Conditions d'utilisation » is feminine plural and « la Politique de confidentialité » is
   * feminine singular. So the article travels with each piece, and `agreeJoin` carries « et la »
   * rather than a bare « et ». The link labels themselves are the footer's own keys
   * (`footer.termsOfService`, `footer.privacyPolicy`), so the two places that name those
   * documents cannot drift apart.
   */
  'auth.register.agreePrefix': 'I agree to the',
  'auth.register.agreeJoin': 'and',
  'auth.register.mustAgree': 'Please agree to the terms and conditions',
  'auth.register.submit': 'Create account',
  'auth.register.submitting': 'Creating account...',
  'auth.register.created': 'Account created successfully! Welcome email sent to your inbox.',

  // ─── forgotten password ─────────────────────────────────────────────────────────────────
  'auth.forgot.heading': 'Forgot Password?',
  'auth.forgot.body': 'No worries! Enter your email address and we\'ll send you a link to reset your password.',
  'auth.forgot.emailLabel': 'Email Address',
  'auth.forgot.emailPlaceholder': 'Enter your email address',
  'auth.forgot.submit': 'Send Reset Link',
  'auth.forgot.submitting': 'Sending...',
  'auth.forgot.missingEmail': 'Please enter your email address',
  'auth.forgot.sent': 'Password reset email sent!',
  /** Deliberately the same answer whether the address is known or not. Do not make it specific. */
  'auth.forgot.sentIfKnown': 'If that email address is in our system, we have sent a password reset link to it.',
  'auth.forgot.checkHeading': 'Check Your Email',
  'auth.forgot.checkBody': 'If an account exists for {email}, you will receive a password reset link shortly.',
  'auth.forgot.notReceivedTitle': 'Didn\'t receive the email?',
  'auth.forgot.notReceivedBody': 'Check your spam folder or try again in a few minutes.',
  'auth.forgot.tryAnother': 'Try Another Email',
  'auth.forgot.noAccountPrompt': 'Don\'t have an account?',
  'auth.forgot.signUpLink': 'Sign up',

  // ─── resetting a password from a link ───────────────────────────────────────────────────
  'auth.reset.verifying': 'Verifying reset link...',
  'auth.reset.noToken': 'No reset token provided',
  'auth.reset.invalidToast': 'This password reset link is invalid or has expired.',
  'auth.reset.invalidHeading': 'Invalid Reset Link',
  'auth.reset.invalidBody': 'This password reset link is invalid or has expired. Reset links are only valid for {hours, plural, one {# hour} other {# hours}}.',
  'auth.reset.requestNew': 'Request New Reset Link',
  'auth.reset.heading': 'Reset Your Password',
  'auth.reset.body': 'Enter your new password below',
  'auth.reset.newPassword': 'New Password',
  'auth.reset.newPasswordPlaceholder': 'Enter new password (min. {count, plural, one {# character} other {# characters}})',
  'auth.reset.confirmPassword': 'Confirm New Password',
  'auth.reset.confirmPasswordPlaceholder': 'Confirm new password',
  'auth.reset.strengthLabel': 'Password Strength:',
  /** The meter's accessible name. It was a bare coloured bar and said nothing at all. */
  'auth.reset.strengthMeter': 'Password strength',
  'auth.reset.strengthWeak': 'Weak',
  'auth.reset.strengthMedium': 'Medium',
  'auth.reset.strengthStrong': 'Strong',
  'auth.reset.passwordsMatch': 'Passwords match',
  'auth.reset.submit': 'Reset Password',
  'auth.reset.submitting': 'Resetting Password...',
  'auth.reset.success': 'Password reset successful! Please log in with your new password.',
  'auth.reset.failed': 'Failed to reset password. Please try again.',

  // ─── changing a password while signed in ────────────────────────────────────────────────
  'auth.change.documentTitle': 'Change Password - Soccer Predictions',
  'auth.change.documentDescription': 'Change your account password',
  'auth.change.heading': 'Change Password',
  'auth.change.subheading': 'Update your account password',
  'auth.change.current': 'Current Password',
  'auth.change.currentPlaceholder': 'Enter current password',
  'auth.change.new': 'New Password',
  'auth.change.newPlaceholder': 'Enter new password',
  'auth.change.confirm': 'Confirm New Password',
  'auth.change.confirmPlaceholder': 'Confirm new password',
  'auth.change.rules': 'Must be at least {count, plural, one {# character} other {# characters}} with uppercase, lowercase, and number',
  'auth.change.noteLabel': 'Note:',
  'auth.change.note': 'Changing your password will log you out from all devices. You will need to log in again with your new password.',
  'auth.change.submit': 'Change Password',
  'auth.change.submitting': 'Changing Password...',
  'auth.change.success': 'Password changed successfully. You have been logged out from all devices.',
  'auth.change.failed': 'Failed to change password',

  // ─── the profile ────────────────────────────────────────────────────────────────────────
  'auth.profile.documentTitle': 'Profile - Soccer Predictions',
  'auth.profile.documentDescription': 'Manage your profile settings',
  'auth.profile.loading': 'Loading profile...',
  'auth.profile.loadFailed': 'Failed to load profile',
  'auth.profile.heading': 'Profile Settings',
  'auth.profile.subheading': 'Manage your account information',
  'auth.profile.email': 'Email',
  'auth.profile.emailFixed': 'Email cannot be changed',
  'auth.profile.username': 'Username',
  'auth.profile.usernamePlaceholder': 'Enter username',
  'auth.profile.firstName': 'First Name',
  'auth.profile.firstNamePlaceholder': 'Enter first name',
  'auth.profile.lastName': 'Last Name',
  'auth.profile.lastNamePlaceholder': 'Enter last name',
  'auth.profile.avatarUrl': 'Avatar URL',
  'auth.profile.accountHeading': 'Account Information',
  'auth.profile.accountType': 'Account Type:',
  'auth.profile.status': 'Status:',
  'auth.profile.emailVerified': 'Email Verified:',
  'auth.profile.memberSince': 'Member Since:',
  'auth.profile.yes': 'Yes',
  'auth.profile.no': 'No',
  /** Shown where a date is missing. Not "1 January 1970", and not an empty cell either. */
  'auth.profile.unknownDate': 'N/A',
  /**
   * Said out loud rather than left to the reader to discover.
   *
   * The backend writes `created_at` with `datetime.utcnow()` into a `DateTime` column with no
   * zone (backend/app/models/base.py:34), so the string that arrives here carries no offset —
   * and `new Date("2026-01-05T09:00:00")` is read by the browser in the DEVICE's zone, which is
   * how this date used to be a day out for a reader in Douala. It is read as UTC now, because
   * that is what the server actually wrote, and shown in the zone the reader chose. Both halves
   * of that are a claim, so the page makes it instead of implying it.
   */
  'auth.profile.memberSinceUnzoned': 'The server records this date without a time zone, so it is read as UTC and shown in {zone}.',
  'auth.profile.edit': 'Edit Profile',
  'auth.profile.save': 'Save Changes',
  'auth.profile.saving': 'Saving...',
  'auth.profile.saved': 'Profile updated successfully',
  'auth.profile.saveFailed': 'Failed to update profile',

  // ─── the subscription ───────────────────────────────────────────────────────────────────
  'auth.subscription.documentTitle': 'Subscription - Soccer Predictions',
  'auth.subscription.documentDescription': 'Manage your subscription plan',
  'auth.subscription.loading': 'Loading subscription information...',
  'auth.subscription.loadFailed': 'Failed to load subscription information',
  'auth.subscription.heading': 'Subscription Management',
  'auth.subscription.subheading': 'Choose the plan that\'s right for you',
  'auth.subscription.current': 'Current Subscription',
  'auth.subscription.plan': 'Plan',
  'auth.subscription.status': 'Status',
  'auth.subscription.price': 'Price',
  /**
   * The billing period, from the backend's own word for it.
   *
   * The payload says "month" (backend/app/api/v1/endpoints/subscriptions.py:25). A select rather
   * than a translation table so an unrecognised period falls through to the server's word
   * instead of disappearing — if the backend one day bills quarterly, the page says so in the
   * backend's English rather than saying nothing.
   */
  'auth.subscription.perPeriod': '/{period, select, day {day} week {week} month {month} year {year} other {{period}}}',
  'auth.subscription.usageHeading': 'Usage Today',
  'auth.subscription.predictionsUsed': 'Predictions Used',
  'auth.subscription.unlimited': 'Unlimited',
  'auth.subscription.popular': 'POPULAR',
  'auth.subscription.currentBadge': 'CURRENT',
  'auth.subscription.predictionsPerDay': '{count, plural, one {# prediction/day} other {# predictions/day}}',
  'auth.subscription.predictionsPerDayUnlimited': 'Unlimited predictions/day',
  'auth.subscription.markets': '{markets} markets',
  'auth.subscription.historyDays': '{count, plural, one {# day history} other {# days history}}',
  'auth.subscription.historyUnlimited': 'Unlimited days history',
  'auth.subscription.confidence': 'Confidence levels',
  'auth.subscription.expertPredictions': 'Expert predictions',
  'auth.subscription.advancedAnalytics': 'Advanced analytics',
  'auth.subscription.apiAccess': 'API access',
  'auth.subscription.currentPlan': 'Current Plan',
  'auth.subscription.processing': 'Processing...',
  'auth.subscription.upgrade': 'Upgrade',
  'auth.subscription.downgrade': 'Downgrade',
  'auth.subscription.alreadyOnTier': 'You are already on this tier',
  'auth.subscription.updateFailed': 'Failed to update subscription',
} as const

export default auth
