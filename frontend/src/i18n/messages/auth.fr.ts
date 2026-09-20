/**
 * Français — the AUTH AND ACCOUNT area.
 *
 * ── THIS TRANSLATION HAS NOT BEEN REVIEWED BY A NATIVE SPEAKER ──────────────────────────────
 *
 * Same provenance as ./core.fr.ts and the same warning: it was written by the author of the
 * English and no francophone has read it. The terms I would most expect a reviewer to change are
 * listed in the package report; the ones that matter here are the account and billing
 * vocabulary — « formule » for a subscription tier (and therefore « Formule supérieure » /
 * « Formule inférieure » for upgrade and downgrade), « robustesse » for password strength,
 * « jeton » for a reset token, and « e-mail » rather than « courriel », which is the Canadian
 * standard and not the usual register in Cameroon.
 *
 * ── AGREEMENT IS DONE BY THE PLURAL MACHINERY, NEVER BY HAND ────────────────────────────────
 *
 * FRENCH COUNTS ZERO AS SINGULAR. `Intl.PluralRules('fr').select(0)` is `"one"`, so "0 caractère"
 * and "0 pronostic/jour". Every message below that interpolates a count states its own branches
 * with the whole agreeing phrase inside them, and every one of them is rendered at 0, 1, 2 and
 * 11 by frontend/e2e/mocked/localisation.spec.ts with its expected form written out there.
 *
 * GENDER FOLLOWS THE FRENCH NOUN, NOT THE ENGLISH ONE. Two places here turn on that and neither
 * is visible from the English:
 *   - password strength is « la robustesse », feminine, so the three readings are « Faible »,
 *     « Moyenne » and « Élevée » — not the masculine forms an English "Weak/Medium/Strong" gives
 *     no hint of.
 *   - the badge on the plan a reader is already on says « ACTUELLE », because the noun it
 *     qualifies is « la formule ». "CURRENT" is genderless; its French is not.
 *   - and the consent line agrees TWICE, with two different nouns: « J'accepte les Conditions
 *     d'utilisation et la Politique de confidentialité ». That is why `agreeJoin` is « et la »
 *     and not « et » — the article belongs to the noun that follows it, which is in the next
 *     element.
 *
 * ── TYPOGRAPHY ──────────────────────────────────────────────────────────────────────────────
 *
 * French puts a no-break space before « : », « ; », « ! » and « ? ». It is written as an
 * explicit `\u00a0` escape rather than as an invisible character, so it can be reviewed in a
 * diff and cannot be deleted by accident.
 *
 * ── WHAT IS NOT TRANSLATED ──────────────────────────────────────────────────────────────────
 *
 * The backend's own words: a tier's name and description, the subscription status, the account
 * type, and the message a tier change returns. They are rendered verbatim in both languages.
 * Neither is the team-name label inside the save-intent notice, which the provider publishes.
 */

import type { Area } from './types'

const auth: Area<'auth'> = {
  // ─── champs et commandes communs aux formulaires ────────────────────────────────────────
  'auth.field.email': 'Adresse e-mail',
  'auth.field.emailPlaceholder': 'Saisissez votre e-mail',
  'auth.field.password': 'Mot de passe',
  'auth.field.passwordPlaceholder': 'Saisissez votre mot de passe',
  'auth.field.showPassword': 'Afficher le mot de passe',
  'auth.field.hidePassword': 'Masquer le mot de passe',
  'auth.backToLogin': 'Retour à la connexion',
  'auth.cancel': 'Annuler',

  // Les deux formes anglaises de la même règle donnent la même phrase en français.
  'auth.validation.passwordsDiffer': 'Les mots de passe ne correspondent pas',
  'auth.validation.newPasswordsDiffer': 'Les nouveaux mots de passe ne correspondent pas',
  'auth.validation.tooShortLong': 'Le mot de passe doit comporter au moins {count, plural, one {# caractère} other {# caractères}}',
  'auth.validation.tooShort': 'Le mot de passe doit comporter au moins {count, plural, one {# caractère} other {# caractères}}',

  // ─── se connecter ───────────────────────────────────────────────────────────────────────
  'auth.login.documentTitle': 'Connexion - Soccer Predictions',
  'auth.login.documentDescription': 'Connectez-vous à votre compte Soccer Predictions pour accéder aux fonctionnalités premium et à des pronostics personnalisés.',
  'auth.login.heading': 'Connectez-vous à votre compte',
  'auth.login.newAccountPrompt': 'Ou',
  'auth.login.newAccountLink': 'créer un nouveau compte',
  'auth.login.rememberMe': 'Se souvenir de moi',
  'auth.login.forgotPassword': 'Mot de passe oublié\u00a0?',
  'auth.login.submit': 'Se connecter',
  'auth.login.submitting': 'Connexion en cours...',

  /*
   * La phrase entière, avec le match dedans — pas un préfixe et un suffixe collés autour de lui.
   * Le nom du match reste tel que le fournisseur le publie et n’est pas traduit.
   */
  'auth.saveIntent.signIn': 'Enregistrer un match nécessite un compte. Connectez-vous et nous terminerons l’enregistrement de {match}, puis nous vous ramènerons là où vous étiez.',
  'auth.saveIntent.register': 'Enregistrer un match nécessite un compte. Créez-en un et nous terminerons l’enregistrement de {match}, puis nous vous ramènerons là où vous étiez.',
  'auth.saveIntent.thatMatch': 'ce match',

  // ─── créer un compte ────────────────────────────────────────────────────────────────────
  'auth.register.documentTitle': 'Créer un compte - Soccer Predictions',
  'auth.register.documentDescription': 'Créez votre compte Soccer Predictions pour accéder aux fonctionnalités premium et à des pronostics personnalisés.',
  'auth.register.heading': 'Créez votre compte',
  'auth.register.haveAccountPrompt': 'Vous avez déjà un compte\u00a0?',
  'auth.register.signInLink': 'Se connecter',
  'auth.register.firstName': 'Prénom',
  'auth.register.firstNamePlaceholder': 'Prénom',
  'auth.register.lastName': 'Nom',
  'auth.register.lastNamePlaceholder': 'Nom',
  'auth.register.username': 'Nom d’utilisateur',
  'auth.register.usernamePlaceholder': 'Choisissez un nom d’utilisateur',
  'auth.register.passwordPlaceholder': 'Créez un mot de passe',
  'auth.register.confirmPassword': 'Confirmer le mot de passe',
  'auth.register.confirmPasswordPlaceholder': 'Confirmez votre mot de passe',
  // « les » s’accorde avec « Conditions d’utilisation », « la » avec « Politique de
  // confidentialité ». L’article voyage avec le lien qu’il introduit.
  'auth.register.agreePrefix': 'J’accepte les',
  'auth.register.agreeJoin': 'et la',
  'auth.register.mustAgree': 'Veuillez accepter les conditions générales',
  'auth.register.submit': 'Créer un compte',
  'auth.register.submitting': 'Création du compte...',
  'auth.register.created': 'Compte créé\u00a0! Un e-mail de bienvenue a été envoyé dans votre boîte de réception.',

  // ─── mot de passe oublié ────────────────────────────────────────────────────────────────
  'auth.forgot.heading': 'Mot de passe oublié\u00a0?',
  'auth.forgot.body': 'Pas d’inquiétude\u00a0! Saisissez votre adresse e-mail et nous vous enverrons un lien pour réinitialiser votre mot de passe.',
  'auth.forgot.emailLabel': 'Adresse e-mail',
  'auth.forgot.emailPlaceholder': 'Saisissez votre adresse e-mail',
  'auth.forgot.submit': 'Envoyer le lien',
  'auth.forgot.submitting': 'Envoi en cours...',
  'auth.forgot.missingEmail': 'Veuillez saisir votre adresse e-mail',
  'auth.forgot.sent': 'E-mail de réinitialisation envoyé\u00a0!',
  'auth.forgot.sentIfKnown': 'Si cette adresse e-mail figure dans notre système, nous y avons envoyé un lien de réinitialisation.',
  'auth.forgot.checkHeading': 'Consultez votre messagerie',
  'auth.forgot.checkBody': 'Si un compte existe pour {email}, vous recevrez sous peu un lien de réinitialisation.',
  'auth.forgot.notReceivedTitle': 'Vous n’avez pas reçu l’e-mail\u00a0?',
  'auth.forgot.notReceivedBody': 'Vérifiez votre dossier de courrier indésirable ou réessayez dans quelques minutes.',
  'auth.forgot.tryAnother': 'Essayer une autre adresse',
  'auth.forgot.noAccountPrompt': 'Vous n’avez pas de compte\u00a0?',
  'auth.forgot.signUpLink': 'S’inscrire',

  // ─── réinitialiser depuis un lien ───────────────────────────────────────────────────────
  'auth.reset.verifying': 'Vérification du lien...',
  'auth.reset.noToken': 'Aucun jeton de réinitialisation fourni',
  'auth.reset.invalidToast': 'Ce lien de réinitialisation est invalide ou a expiré.',
  'auth.reset.invalidHeading': 'Lien de réinitialisation invalide',
  'auth.reset.invalidBody': 'Ce lien de réinitialisation est invalide ou a expiré. Les liens de réinitialisation ne sont valables que {hours, plural, one {# heure} other {# heures}}.',
  'auth.reset.requestNew': 'Demander un nouveau lien',
  'auth.reset.heading': 'Réinitialisez votre mot de passe',
  'auth.reset.body': 'Saisissez ci-dessous votre nouveau mot de passe',
  'auth.reset.newPassword': 'Nouveau mot de passe',
  'auth.reset.newPasswordPlaceholder': 'Saisissez un nouveau mot de passe ({count, plural, one {# caractère minimum} other {# caractères minimum}})',
  'auth.reset.confirmPassword': 'Confirmer le nouveau mot de passe',
  'auth.reset.confirmPasswordPlaceholder': 'Confirmez le nouveau mot de passe',
  // « la robustesse » est féminine : Faible (invariable), Moyenne, Élevée.
  'auth.reset.strengthLabel': 'Robustesse du mot de passe\u00a0:',
  'auth.reset.strengthMeter': 'Robustesse du mot de passe',
  'auth.reset.strengthWeak': 'Faible',
  'auth.reset.strengthMedium': 'Moyenne',
  'auth.reset.strengthStrong': 'Élevée',
  'auth.reset.passwordsMatch': 'Les mots de passe correspondent',
  'auth.reset.submit': 'Réinitialiser le mot de passe',
  'auth.reset.submitting': 'Réinitialisation en cours...',
  'auth.reset.success': 'Mot de passe réinitialisé\u00a0! Connectez-vous avec votre nouveau mot de passe.',
  'auth.reset.failed': 'Impossible de réinitialiser le mot de passe. Veuillez réessayer.',

  // ─── changer son mot de passe ───────────────────────────────────────────────────────────
  'auth.change.documentTitle': 'Changer le mot de passe - Soccer Predictions',
  'auth.change.documentDescription': 'Changez le mot de passe de votre compte',
  'auth.change.heading': 'Changer le mot de passe',
  'auth.change.subheading': 'Mettez à jour le mot de passe de votre compte',
  'auth.change.current': 'Mot de passe actuel',
  'auth.change.currentPlaceholder': 'Saisissez le mot de passe actuel',
  'auth.change.new': 'Nouveau mot de passe',
  'auth.change.newPlaceholder': 'Saisissez le nouveau mot de passe',
  'auth.change.confirm': 'Confirmer le nouveau mot de passe',
  'auth.change.confirmPlaceholder': 'Confirmez le nouveau mot de passe',
  'auth.change.rules': 'Doit comporter au moins {count, plural, one {# caractère} other {# caractères}}, dont une majuscule, une minuscule et un chiffre',
  'auth.change.noteLabel': 'Remarque\u00a0:',
  'auth.change.note': 'Changer votre mot de passe vous déconnectera de tous vos appareils. Vous devrez vous reconnecter avec votre nouveau mot de passe.',
  'auth.change.submit': 'Changer le mot de passe',
  'auth.change.submitting': 'Changement en cours...',
  'auth.change.success': 'Mot de passe changé. Vous avez été déconnecté de tous vos appareils.',
  'auth.change.failed': 'Impossible de changer le mot de passe',

  // ─── le profil ──────────────────────────────────────────────────────────────────────────
  'auth.profile.documentTitle': 'Profil - Soccer Predictions',
  'auth.profile.documentDescription': 'Gérez les paramètres de votre profil',
  'auth.profile.loading': 'Chargement du profil...',
  'auth.profile.loadFailed': 'Impossible de charger le profil',
  'auth.profile.heading': 'Paramètres du profil',
  'auth.profile.subheading': 'Gérez les informations de votre compte',
  'auth.profile.email': 'E-mail',
  'auth.profile.emailFixed': 'L’adresse e-mail ne peut pas être modifiée',
  'auth.profile.username': 'Nom d’utilisateur',
  'auth.profile.usernamePlaceholder': 'Saisissez un nom d’utilisateur',
  'auth.profile.firstName': 'Prénom',
  'auth.profile.firstNamePlaceholder': 'Saisissez votre prénom',
  'auth.profile.lastName': 'Nom',
  'auth.profile.lastNamePlaceholder': 'Saisissez votre nom',
  'auth.profile.avatarUrl': 'URL de l’avatar',
  'auth.profile.accountHeading': 'Informations du compte',
  'auth.profile.accountType': 'Type de compte\u00a0:',
  'auth.profile.status': 'Statut\u00a0:',
  'auth.profile.emailVerified': 'E-mail vérifié\u00a0:',
  'auth.profile.memberSince': 'Membre depuis\u00a0:',
  'auth.profile.yes': 'Oui',
  'auth.profile.no': 'Non',
  // « Inconnue » s’accorde avec « la date », qui est ce que cette cellule contient.
  'auth.profile.unknownDate': 'Inconnue',
  'auth.profile.memberSinceUnzoned': 'Le serveur enregistre cette date sans fuseau horaire\u00a0: elle est donc lue en UTC et affichée en {zone}.',
  'auth.profile.edit': 'Modifier le profil',
  'auth.profile.save': 'Enregistrer les modifications',
  'auth.profile.saving': 'Enregistrement...',
  'auth.profile.saved': 'Profil mis à jour',
  'auth.profile.saveFailed': 'Impossible de mettre à jour le profil',

  // ─── l’abonnement ───────────────────────────────────────────────────────────────────────
  'auth.subscription.documentTitle': 'Abonnement - Soccer Predictions',
  'auth.subscription.documentDescription': 'Gérez votre formule d’abonnement',
  'auth.subscription.loading': 'Chargement des informations d’abonnement...',
  'auth.subscription.loadFailed': 'Impossible de charger les informations d’abonnement',
  'auth.subscription.heading': 'Gestion de l’abonnement',
  'auth.subscription.subheading': 'Choisissez la formule qui vous convient',
  'auth.subscription.current': 'Abonnement actuel',
  'auth.subscription.plan': 'Formule',
  'auth.subscription.status': 'Statut',
  'auth.subscription.price': 'Prix',
  'auth.subscription.perPeriod': '/{period, select, day {jour} week {semaine} month {mois} year {an} other {{period}}}',
  'auth.subscription.usageHeading': 'Utilisation aujourd’hui',
  'auth.subscription.predictionsUsed': 'Pronostics utilisés',
  'auth.subscription.unlimited': 'Illimité',
  'auth.subscription.popular': 'POPULAIRE',
  // « ACTUELLE » s’accorde avec « la formule ».
  'auth.subscription.currentBadge': 'ACTUELLE',
  'auth.subscription.predictionsPerDay': '{count, plural, one {# pronostic/jour} other {# pronostics/jour}}',
  'auth.subscription.predictionsPerDayUnlimited': 'Pronostics illimités par jour',
  // Le français met le nom du champ devant : « Marchés : 1N2, BTTS ».
  'auth.subscription.markets': 'Marchés\u00a0: {markets}',
  'auth.subscription.historyDays': '{count, plural, one {# jour d’historique} other {# jours d’historique}}',
  'auth.subscription.historyUnlimited': 'Historique illimité',
  'auth.subscription.confidence': 'Niveaux de confiance',
  'auth.subscription.expertPredictions': 'Pronostics d’experts',
  'auth.subscription.advancedAnalytics': 'Analyses avancées',
  'auth.subscription.apiAccess': 'Accès à l’API',
  'auth.subscription.currentPlan': 'Formule actuelle',
  'auth.subscription.processing': 'Traitement en cours...',
  'auth.subscription.upgrade': 'Formule supérieure',
  'auth.subscription.downgrade': 'Formule inférieure',
  'auth.subscription.alreadyOnTier': 'Vous êtes déjà sur cette formule',
  'auth.subscription.updateFailed': 'Impossible de modifier l’abonnement',
}

export default auth
