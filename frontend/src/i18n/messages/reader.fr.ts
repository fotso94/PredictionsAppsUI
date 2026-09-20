/**
 * Français — the READER area: the competition list and one competition, a team, the personal
 * dashboard, and the provenance, revision and evidence panels on a match page.
 *
 * THIS TRANSLATION HAS NOT BEEN REVIEWED BY A NATIVE SPEAKER. The green tests establish that the
 * French is COMPLETE, that it is the only language on the page, that every count-bearing label
 * reads the same at 0, 1, 2 and 11, and that no date is formatted in the device's zone. None of
 * them establishes that it reads WELL. Every term I am less than sure of is listed in the
 * package report under needs_other_owner; the ones most worth a second pair of eyes are marked
 * REVIEW below.
 *
 * One entry here for every entry in ./reader.en.ts. `Area<'reader'>` is derived from that file,
 * so a key added in English and forgotten here is a compile error in THIS file, naming the key.
 *
 * FRENCH COUNTS ZERO AS SINGULAR — `Intl.PluralRules('fr').select(0)` is `"one"`, so "0 match",
 * "0 compétition". Agreement follows the FRENCH noun, not the English one, and the whole
 * agreeing phrase goes inside the branch. French also puts a no-break space before « : », « ; »,
 * « ! » and « ? », written here as an explicit `\u00a0` escape so it survives a diff.
 *
 * NOTHING HERE USES `{count, plural, …}`, AND THAT IS A CONSTRAINT RATHER THAN A PREFERENCE.
 * The table that proves a French plural at 0, 1, 2 and 11 lives in another package's spec (see
 * the header of ./reader.en.ts). So every label here that carries a count was chosen to be
 * INVARIABLE in French — « en favoris » and « en direct », not « enregistré(s) » — and « fois »,
 * which does not inflect, carries the revision count. The follow control's two count lines take
 * the same way round it with a category label, « Compétitions suivies : 1 sur 5 »; the
 * reasoning is at `reader.follow.league.count`. frontend/e2e/mocked/reader-localisation.spec.ts
 * renders each of them at 0, 1, 2 and 11 and fails if one moves or fakes agreement.
 */

import type { Area } from './types'

const reader: Area<'reader'> = {
  // ─── shared by more than one reader screen ──────────────────────────────────────────────
  'reader.saveStateUnknown': 'Nous n’avons pas pu charger vos matchs enregistrés\u00a0; le bouton d’enregistrement ne peut donc pas indiquer lesquels vous avez déjà enregistrés.',
  'reader.upcomingMatches': 'Matchs à venir',
  'reader.backToHome': 'Retour à l’accueil',

  // ─── the follow control ─────────────────────────────────────────────────────────────────
  /**
   * REVIEW throughout. « Suivre » is the verb every French site uses for this, and the
   * infinitive is what a French button carries where English uses the bare stem.
   *
   * THE STATE WORD AGREES WITH THE THING IT IS BESIDE. English says "Following" for a team and
   * for a competition; French says « Suivie » for both — but only because « une équipe » and
   * « une compétition » are BOTH feminine, and that is a fact about these two nouns rather than
   * about the control. A third kind of entity with a masculine noun (« un joueur ») would take
   * « Suivi », which is why the key is split by kind and not shared. Writing one key and a
   * comment saying "they happen to agree" is how the next kind gets it wrong silently.
   */
  'reader.follow.follow': 'Suivre',
  'reader.follow.signIn': 'Se connecter pour suivre',
  'reader.follow.team.following': 'Suivie',
  'reader.follow.league.following': 'Suivie',
  /**
   * The accessible name and the title. « Vous suivez {name} » rather than a bare participle: a
   * screen reader reads this as a whole utterance with nothing on screen beside it, so the
   * sentence has to stand on its own — and a verb phrase also sidesteps agreeing with a club's
   * name, whose gender the interface does not know and must not guess.
   */
  'reader.follow.namedFollow': 'Suivre {name}',
  'reader.follow.namedSignIn': 'Se connecter pour suivre {name}',
  'reader.follow.namedFollowing': 'Vous suivez {name}. Sélectionnez pour ne plus suivre.',
  'reader.follow.team.signInToast': 'Connectez-vous pour suivre des équipes.',
  'reader.follow.league.signInToast': 'Connectez-vous pour suivre des compétitions.',
  /** Same reason as the accessible name: a verb, so nothing has to agree with {name}. */
  'reader.follow.confirmed': 'Vous suivez désormais {name}.',
  'reader.follow.confirmedOff': 'Vous ne suivez plus {name}.',
  /** « Impossible de … » keeps {name} out of the subject position, where it would need a gender. */
  'reader.follow.failed': 'Impossible de suivre {name}. Rien n’a été modifié.',
  'reader.follow.failedOff': 'Impossible d’arrêter de suivre {name}. Rien n’a été modifié.',
  'reader.follow.unknown': 'Nous n’avons pas pu charger ce que vous suivez\u00a0; ce bouton ne peut donc pas indiquer si {name} figure déjà dans votre liste.',
  /**
   * REVIEW. « Compétitions suivies : 1 sur 5 », not « 1 compétition suivie sur 5 ».
   *
   * The second is the French a French speaker would write, and it is what these two keys should
   * eventually say. It needs a plural — French is singular at 0 and at 1, and « suivie » agrees
   * with the noun — and a plural cannot be written in this area: see the long note at the same
   * key in ./reader.en.ts, and the header of this file.
   *
   * So the form here is a CATEGORY LABEL followed by a ratio. « Compétitions suivies » is
   * plural because it names the category, exactly as a column heading is, and stays plural at
   * 0 and at 1 where a counted noun would not; « 1 sur 5 » carries no noun and therefore no
   * agreement. It is right at every count, which « 0 compétitions suivies » would not have been
   * and which no amount of testing one sample would have caught.
   */
  'reader.follow.team.count': 'Équipes suivies\u00a0: {count, number} sur {limit, number}',
  'reader.follow.league.count': 'Compétitions suivies\u00a0: {count, number} sur {limit, number}',

  // ─── the competition list ───────────────────────────────────────────────────────────────
  /** « Soccer Predictions » is the product's name and is never translated. */
  'reader.leagues.documentTitle': 'Compétitions - Soccer Predictions',
  'reader.leagues.documentDescription': 'Parcourez toutes les compétitions de football disponibles, avec les pronostics et les analyses.',
  'reader.leagues.heading': 'Compétitions',
  'reader.leagues.subheading': 'Parcourez toutes les compétitions disponibles',
  'reader.leagues.loading': 'Chargement des compétitions…',
  'reader.leagues.loadFailed': 'Les compétitions n’ont pas pu être chargées.',
  'reader.leagues.emptyTitle': 'Aucune compétition disponible. Il s’agit peut-être d’un problème de données.',
  'reader.leagues.emptyHint': 'Consultez la console du navigateur pour les détails.',

  // ─── one competition ────────────────────────────────────────────────────────────────────
  'reader.league.documentTitle': '{league} - {app}',
  'reader.league.documentDescription': 'Classement, calendrier et pronostics publiés de {league} pour la saison {season}.',
  'reader.league.loading': 'Chargement de la compétition…',
  'reader.league.notFoundHeading': 'Compétition introuvable',
  'reader.league.notFoundBody': 'La compétition demandée est introuvable.',
  'reader.league.partialStandings': 'Le classement n’a pas pu être chargé, il n’est donc pas affiché.',
  'reader.league.partialFixtures': 'La liste des matchs n’a pas pu être chargée, elle n’est donc pas affichée.',
  'reader.league.loadFailedTitle': 'Cette compétition n’a pas pu être chargée.',
  'reader.league.tryAgain': 'Réessayer',
  'reader.league.noFixturesTitle': 'Aucun match à venir n’est enregistré pour cette compétition.',
  'reader.league.noFixturesBody': 'Rien n’est programmé dans les deux prochaines semaines parmi les données que nous détenons.',
  'reader.league.standings': 'Classement',
  'reader.league.teams': 'Équipes',
  'reader.league.nothingTitle': 'Aucune équipe et aucun match ne sont enregistrés pour cette compétition.',
  'reader.league.nothingBody': 'Rien n’a encore été chargé pour elle.',

  /**
   * REVIEW. The French abbreviations are the ones a French league table uses — J, G, N, P, BP,
   * BC, Diff — and they are NOT a translation of the English letters: French « P » is Perdus
   * (lost) where English "P" is Played. That is precisely why every column also carries its full
   * name, and why translating the letters one for one would have been wrong.
   */
  'reader.standings.position': '#',
  /** REVIEW. « Rang » is what a French league table calls this column; « Position » is also
   *  correct, and if a reviewer prefers it the English and the French become the identical word
   *  and the column has to move to the literals in LeagueDetailPage.tsx with the other two. */
  'reader.standings.positionFull': 'Rang',
  'reader.standings.team': 'Équipe',
  'reader.standings.teamFull': 'Équipe',
  'reader.standings.played': 'J',
  'reader.standings.playedFull': 'Joués',
  'reader.standings.won': 'G',
  'reader.standings.wonFull': 'Gagnés',
  'reader.standings.drawn': 'N',
  'reader.standings.drawnFull': 'Nuls',
  'reader.standings.lost': 'P',
  'reader.standings.lostFull': 'Perdus',
  'reader.standings.goalsFor': 'BP',
  'reader.standings.goalsForFull': 'Buts pour',
  'reader.standings.goalsAgainst': 'BC',
  'reader.standings.goalsAgainstFull': 'Buts contre',
  'reader.standings.goalDifference': 'Diff',
  'reader.standings.goalDifferenceFull': 'Différence de buts',

  // ─── one team ───────────────────────────────────────────────────────────────────────────
  'reader.team.documentTitle': '{team} - {app}',
  'reader.team.loadFailedTitle': 'Cette équipe n’a pas pu être chargée.',
  'reader.team.notFoundTitle': 'Équipe introuvable.',
  'reader.team.notFoundBody': 'Aucune équipe ne porte cet identifiant parmi les données que nous détenons.',
  'reader.team.goHome': 'Aller à l’accueil',
  'reader.team.recentMatches': 'Matchs récents',
  'reader.team.noUpcomingTitle': 'Aucun match à venir n’est enregistré pour cette équipe.',
  'reader.team.noUpcomingBody': 'Rien n’est programmé pour elle dans les compétitions couvertes par ce site.',
  'reader.team.noRecentTitle': 'Aucun résultat n’est encore enregistré pour cette équipe.',
  'reader.team.noRecentBody': 'Rien de ce qu’elle a joué n’est enregistré ici.',
  /** The second half is word for word core.fr.ts's `matchday.scoring.*`, so the two cannot drift. */
  'reader.team.recentNote': 'Scores finaux, avec ce que chaque source avait publié auparavant. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',

  // ─── the personal dashboard ─────────────────────────────────────────────────────────────
  'reader.dashboard.documentTitle': 'Mes matchs - Soccer Predictions',
  'reader.dashboard.documentDescription': 'Les matchs que vous avez enregistrés et les équipes et compétitions que vous suivez.',
  'reader.dashboard.welcome': 'Bon retour, {name}\u00a0!',
  'reader.dashboard.welcomeNoName': 'Bon retour\u00a0!',
  'reader.dashboard.signedInAs': 'Connecté en tant que {email}',
  /** `{type}` is the backend's own word. « compte » precedes it, as French requires. */
  'reader.dashboard.accountKind': ' · compte {type}',
  'reader.dashboard.feedHeading': 'Votre fil',
  'reader.dashboard.feedHint': 'Ce que vous avez enregistré et ce que jouent les équipes et compétitions que vous suivez — en direct d’abord, puis les résultats, puis ce qui arrive.',
  /** REVIEW. « en favoris » rather than « enregistrés », so the label does not move with the count. */
  'reader.dashboard.savedCount': '{count} en favoris',
  'reader.dashboard.liveCount': '{count} en direct',
  'reader.dashboard.followingHeading': 'Équipes et compétitions que vous suivez',
  'reader.dashboard.followingHint': 'Leurs matchs apparaissent dans le fil ci-dessus. Suivre change ce que vous voyez ici\u00a0; cela ne change rien à ce que publie une source.',
  'reader.dashboard.controlsHeading': 'Vos réglages et vos données',
  'reader.dashboard.controlsHint': 'Ce que ces pages ont le droit de vous montrer, comment obtenir une copie de vos données et comment les supprimer.',
  'reader.dashboard.recordHeading': 'Votre bilan de pronostics',
  'reader.dashboard.recordBody1': 'Vos propres pronostics ne sont pas comparés aux résultats finaux pour en tirer un bilan personnel\u00a0: aucun taux d’exactitude, aucune série et aucun gain ne sont affichés pour votre compte. Enregistrer un match note que vous voulez y revenir\u00a0; ce n’est pas un pari et rien n’y est comparé à un résultat.',
  'reader.dashboard.recordBody2': 'Les performances réelles des fournisseurs de modèles et des experts, comptées à partir des résultats réglés, sont publiées sur la page d’accueil avec la taille d’échantillon derrière chaque chiffre.',
  'reader.dashboard.browsePredictions': 'Voir les pronostics du jour',
  'reader.dashboard.browseFixtures': 'Voir les matchs',
  'reader.dashboard.accountSettings': 'Paramètres du compte',
  'reader.dashboard.coverageHeading': 'Ce que ce site contient actuellement',
  'reader.dashboard.coverageHint': 'Comptages à l’échelle du site, mesurés à partir des données enregistrées — et non vos statistiques personnelles.',
  'reader.dashboard.loadingFigure': 'Chargement',
  'reader.dashboard.coverageFailed': 'Le service de couverture n’a pas pu être joint, ces comptages sont donc indisponibles.',
  'reader.dashboard.noAccuracy': 'Aucun taux d’exactitude n’est affiché\u00a0: {reason}',

  // ─── forecast provenance, on a match page ───────────────────────────────────────────────
  'reader.anomalies.warning': 'Ces chiffres ne s’additionnent pas comme ils le devraient. Le pronostic est affiché exactement tel que le fournisseur l’a publié, et rien n’a été ajusté pour le faire correspondre.',
  /** REVIEW. « Exécution du modèle » for a model run; « passage du modèle » is the alternative. */
  'reader.provenance.modelRun': 'Exécution du modèle du fournisseur',
  'reader.provenance.providerUpdated': 'Dernière mise à jour du fournisseur',
  'reader.provenance.retrieved': 'Récupéré par ce site',
  'reader.provenance.fixtureMatch': 'Correspondance du match',
  'reader.provenance.generationUnknown': 'heure de génération inconnue (non publiée par le fournisseur)',
  'reader.provenance.notReported': 'non communiqué',
  'reader.provenance.notRecorded': 'non enregistré',
  'reader.provenance.unzoned': 'L’une de ces heures est arrivée sans fuseau horaire et est lue comme de l’UTC.',

  // ─── an expert's earlier published versions ─────────────────────────────────────────────
  'reader.revisions.heading': 'Versions publiées précédemment',
  /** « fois » is invariable, so the count needs no branch — which is the whole reason for it. */
  'reader.revisions.summaryOnce': 'Cette vue a été mise à jour une fois. Chaque version antérieure est conservée exactement telle qu’elle a été publiée\u00a0; une correction s’ajoute au registre au lieu de le remplacer.',
  'reader.revisions.summaryOnceWhen': 'Cette vue a été mise à jour une fois, la dernière le {when}. Chaque version antérieure est conservée exactement telle qu’elle a été publiée\u00a0; une correction s’ajoute au registre au lieu de le remplacer.',
  'reader.revisions.summaryMany': 'Cette vue a été mise à jour {count} fois. Chaque version antérieure est conservée exactement telle qu’elle a été publiée\u00a0; une correction s’ajoute au registre au lieu de le remplacer.',
  'reader.revisions.summaryManyWhen': 'Cette vue a été mise à jour {count} fois, la dernière le {when}. Chaque version antérieure est conservée exactement telle qu’elle a été publiée\u00a0; une correction s’ajoute au registre au lieu de le remplacer.',
  /** REVIEW. « Version n° 2 » is the usual French form and is not the English word on its own,
   *  which the identical-string guard would read as a translation nobody did. */
  'reader.revisions.version': 'Version n\u00b0 {number}',
  'reader.revisions.asFirstPublished': ' · telle que publiée initialement',
  'reader.revisions.replaced': 'remplacée le {when}',
  'reader.revisions.editedAfterKickoff': 'modifiée après le coup d’envoi',
  'reader.revisions.whatChanged': 'Ce qui a changé\u00a0: ',
  'reader.revisions.home': 'Domicile',
  'reader.revisions.draw': 'Match nul',
  'reader.revisions.away': 'Extérieur',
  'reader.revisions.confidence': 'Confiance',

  // ─── the evidence panel, on a match page ────────────────────────────────────────────────
  'reader.brief.heading': 'Ce que cette page sait du match',
  'reader.brief.marketsNotListed': 'Publié pour ce match\u00a0; les marchés couverts n’ont pas été listés.',
  'reader.brief.noModelForecast': 'Aucun pronostic de modèle n’a été récupéré pour ce match.',
  'reader.brief.expertsAwait': 'Les experts publient directement\u00a0; un pronostic apparaît donc ici dès qu’il est publié.',
  'reader.brief.fixtureLink': 'lien avec le match\u00a0: {confidence}',
  /** Only ever shown above one, so the plural agreement here is always the right one. */
  'reader.brief.expertsPublished': '{count} experts ont publié',
  'reader.brief.published': 'publié le {when}',
  'reader.brief.allMarkets': 'Les deux sources ont publié tous les marchés qu’elles proposent pour ce match.',
}

export default reader
