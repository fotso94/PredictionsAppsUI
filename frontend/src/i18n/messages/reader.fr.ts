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
  // ───────────────────────────────────────────────────────────────── sélections et coupons
  // REVIEW: « coupon » for a slip, « sélection » for a leg, « cote » for a price. Every value
  // states what the number is (a published probability, a price the reader typed, a
  // provider's price) exactly as the English does; nothing here promises a return.
  'selections.nav': 'Sélections',
  'selections.panel.title': 'Marchés de cette rencontre',
  'selections.panel.intro': 'Chaque sélection que la prévision du modèle permet, avec sa probabilité publiée. Ajoutez-en une à votre coupon pour la comparer à celles d’autres rencontres.',
  'selections.panel.noForecast': 'Aucune prévision du modèle n’est enregistrée pour cette rencontre : il n’y a donc aucun marché à choisir.',
  'selections.panel.builtFrom': 'Lu dans la prévision {provider} récupérée {retrieved} ; exécution du modèle : {modelRun}.',
  'selections.panel.modelRunUnknown': 'non précisée',
  'selections.panel.snapshot': 'instantané de prévision {id}',
  'selections.panel.state.stale': 'Cette prévision est périmée ({reason}) ; ses probabilités sont affichées à titre indicatif.',
  'selections.panel.state.kickoffPassed': 'Cette rencontre a commencé. Ses marchés sont affichés à titre indicatif et ne peuvent plus être ajoutés à un coupon.',
  'selections.panel.unavailable': 'Non publié : {reason}',
  'selections.panel.calculated': 'Calculé à partir des probabilités du fournisseur : {formula}',
  'selections.panel.probability': 'Probabilité publiée',
  'selections.panel.priceProvider': 'Cote du fournisseur {price}, relevée {when} (bookmaker non nommé)',
  'selections.panel.noPrice': 'Aucune cote disponible pour cette sélection',
  'selections.panel.settles': 'Règlement : {rule}',
  'selections.panel.notTracked': 'Suivi automatique impossible : {reason}',
  'selections.panel.remainder': 'Autres scores : {value} (le reste attribué par le fournisseur ; ce n’est pas une sélection)',
  'selections.panel.recommended': 'Marchés signalés par le fournisseur dans ses propres données',
  'selections.panel.recommendedUnresolved': '{raw} : non proposé ({reason})',
  'selections.panel.recommendedNote': 'Listés tels que le fournisseur les a publiés, rattachés aux sélections ci-dessus. Ce sont ses signalements, pas les suggestions de ce site.',
  'selections.panel.missing': 'Non proposé ici',
  'selections.panel.missingIntro': 'Familles de marchés qu’aucune source configurée ne publie. Elles ne sont pas déduites d’autres statistiques.',
  'selections.action.add': 'Ajouter au coupon',
  'selections.action.added': 'Sur le coupon',
  'selections.action.replace': 'Remplacer la sélection de cette rencontre',
  'selections.action.remove': 'Retirer',
  'selections.action.addAll': 'Tout ajouter au coupon',
  'selections.action.copy': 'Copier le coupon',
  'selections.action.copied': 'Copié',
  'selections.action.save': 'Enregistrer',
  'selections.action.saveNamed': 'Enregistrer sous…',
  'selections.action.record': 'Marquer comme placé',
  'selections.action.duplicate': 'Dupliquer en brouillon',
  'selections.action.delete': 'Supprimer',
  'selections.action.clear': 'Vider le coupon',
  'selections.action.new': 'Nouveau coupon',
  'selections.action.open': 'Ouvrir',
  'selections.action.showSlip': 'Coupon',
  'selections.action.hideSlip': 'Masquer le coupon',
  'selections.dock.title': 'Votre coupon',
  'selections.dock.empty': 'Rien sur votre coupon pour l’instant. Ouvrez une rencontre et ajoutez une sélection.',
  'selections.dock.count': '{count, plural, one {# sélection} other {# sélections}}',
  'selections.dock.signedOut': 'Conservé dans ce navigateur jusqu’à votre connexion ; la connexion le transfère à votre compte.',
  'selections.dock.handoffRefused': '{count, plural, one {Une sélection de ce navigateur n’a pas pu être ajoutée à votre compte : {reasons}} other {# sélections de ce navigateur n’ont pas pu être ajoutées à votre compte : {reasons}}}',
  'selections.dock.started': 'Coup d’envoi donné : ce n’est plus une sélection d’avant-match ; retirez-la avant d’enregistrer.',
  'selections.dock.forecastChanged': 'La prévision a changé depuis votre choix ({current} désormais) ; votre sélection est inchangée.',
  'selections.dock.unavailableNow': 'La prévision actuelle ne propose plus cette sélection ; votre sélection est inchangée.',
  'selections.dock.oneOnly': 'Une sélection par rencontre. Cette rencontre en a déjà une sur votre coupon.',
  'selections.dock.oddsLabel': 'Cote de votre bookmaker',
  'selections.dock.oddsPlaceholder': 'ex. 2,30',
  'selections.dock.combinedPrice': 'Cote combinée {price}',
  'selections.dock.combinedPriceMissing': 'Pas de cote combinée : {count, plural, one {une sélection n’a} other {# sélections n’ont}} pas de cote. Saisissez les cotes de votre bookmaker.',
  'selections.dock.combinedProbability': 'Chance combinée ≈ {value}',
  'selections.dock.combinedProbabilityNote': 'Produit des probabilités publiées, en supposant les rencontres indépendantes. Une approximation, pas une prévision calibrée.',
  'selections.dock.stakeLabel': 'Mise (facultative)',
  'selections.dock.currencyLabel': 'Devise',
  'selections.dock.potential': 'Retour brut {gross} · gain net {net}',
  'selections.dock.potentialNote': 'D’après la cote indiquée, arrondi à la plus petite unité de la devise. Aucun argent n’est détenu ni promis ici.',
  'selections.dock.nameLabel': 'Nommer ce coupon',
  'selections.dock.saveHint': 'Connectez-vous pour enregistrer ce coupon dans votre compte.',
  'selections.dock.saved': 'Enregistré sous « {name} ».',
  'selections.dock.recorded': 'Marqué comme placé ailleurs. Il est désormais conservé tel quel ; dupliquez-le pour le modifier.',
  'selections.dock.recordHint': 'Notez que vous avez placé ce pari chez votre propre bookmaker. Ce site ne place aucun pari, ne détient aucun argent et ne confirme l’existence d’aucun pari.',
  'selections.dock.referenceLabel': 'Votre référence (facultative)',
  'selections.dock.priceLabel': 'Cote combinée donnée par votre bookmaker (facultative)',
  'selections.dock.error': 'Cela n’a pas abouti : {reason}',
  'selections.dock.disclaimer': 'Les probabilités sont les prévisions publiées par le fournisseur, pas des cotes proposées. Rien ici n’est un conseil de pari.',
  'selections.history.title': 'Mes sélections',
  'selections.history.intro': 'Brouillons, combinaisons enregistrées et paris notés comme placés ailleurs, avec le sort de chaque sélection une fois les résultats enregistrés.',
  'selections.history.empty': 'Aucun coupon pour l’instant.',
  'selections.history.signedOut': 'Connectez-vous pour voir les coupons enregistrés dans votre compte.',
  'selections.history.loadFailed': 'Vos coupons n’ont pas pu être chargés : {reason}',
  'selections.history.filter.all': 'Tous',
  'selections.history.filter.draft': 'Brouillons',
  'selections.history.filter.saved': 'Enregistrés',
  'selections.history.filter.recorded': 'Placés',
  'selections.history.untitled': 'Coupon sans nom',
  'selections.history.updated': 'mis à jour {when}',
  'selections.history.recordedAt': 'noté {when}',
  'selections.history.reference': 'réf. {reference}',
  'selections.history.counts': '{won} gagnée(s) · {lost} perdue(s) · {void} annulée(s) · {unresolved} non résolue(s) · {pending} en attente',
  'selections.history.settlementRule': 'Règle : {rule}',
  'selections.history.settlementReason': '{reason}',
  'selections.history.actual': 'Résultat {actual}',
  'selections.history.awaiting': 'En attente d’un résultat',
  'selections.history.unresolvedNote': 'Non réglée automatiquement : les données que ce marché exige ne sont pas détenues. Rien n’est deviné.',
  'selections.history.voidNote': 'Les sélections annulées sortent de la combinaison et de sa cote.',
  'selections.suggest.title': 'Combinaisons suggérées',
  'selections.suggest.intro': 'Construites uniquement à partir des prévisions enregistrées, selon une règle fixe : une sélection par rencontre, la plus forte probabilité publiée parmi les marchés autorisés, classées puis découpées en ensembles sans rencontre commune. Demander des suggestions ne coûte aucune requête au fournisseur.',
  'selections.suggest.legs': 'Sélections',
  'selections.suggest.minProbability': 'Probabilité publiée minimale',
  'selections.suggest.maxProbability': 'Maximale (les quasi-certitudes sont écartées)',
  'selections.suggest.markets': 'Marchés',
  'selections.suggest.competitions': 'Compétitions',
  'selections.suggest.anyCompetition': 'Toutes les compétitions',
  'selections.suggest.window': 'Fenêtre de coup d’envoi',
  'selections.suggest.days': '{count, plural, one {# prochain jour} other {# prochains jours}}',
  'selections.suggest.oddsRange': 'Cote du fournisseur entre',
  'selections.suggest.oddsRangeNote': 'Seul le marché résultat du match porte une cote du fournisseur ; un intervalle de cotes s’y limite donc.',
  'selections.suggest.includeStale': 'Inclure les prévisions périmées',
  'selections.suggest.generate': 'Générer',
  'selections.suggest.generatedAt': 'Généré {when} à partir de {qualifying} rencontres retenues sur {considered} dans la fenêtre.',
  'selections.suggest.none': 'Aucune combinaison ne convient : {reason}',
  'selections.suggest.shortfall': '{reason}',
  'selections.suggest.combination': 'Combinaison {index}',
  'selections.suggest.rank': 'rang {rank}',
  'selections.suggest.why': 'Probabilité publiée {probability} par {provider} ; prévision vieille de {age} ({state}).',
  'selections.suggest.whyAgeUnknown': 'Probabilité publiée {probability} par {provider} ; âge de la prévision non précisé.',
  'selections.suggest.ageHours': '{count, plural, one {# heure} other {# heures}}',
  'selections.suggest.excluded': 'Écartées : {stale} périmées, {noForecast} sans prévision, {belowThreshold} sous le minimum, {aboveCeiling} au-dessus du maximum, {oddsFilter} hors de l’intervalle de cotes.',
  'selections.suggest.combinedOdds': 'Les cotes du fournisseur se multiplient à {price} (bookmaker non nommé).',
  'selections.suggest.noCombinedOdds': 'Pas de cote combinée : toutes les sélections ne portent pas une cote du fournisseur.',
  'selections.suggest.loadFailed': 'Les suggestions n’ont pas pu être générées : {reason}',
  'selections.suggest.warnings': 'Remarque : {message}',
  'selections.group.outcome': 'Issue du match',
  'selections.group.goals': 'Buts',
  'selections.group.firstHalf': 'Première mi-temps',
  'selections.group.team': 'Marchés par équipe',
  'selections.group.exactScore': 'Score exact',
  'selections.market.matchResult': 'Résultat du match',
  'selections.market.doubleChance': 'Double chance',
  'selections.market.drawNoBet': 'Remboursé si nul',
  'selections.market.totalGoals': 'Total de buts {line}',
  'selections.market.teamGoals': 'Buts de {team} {line}',
  'selections.market.bothTeamsScore': 'Les deux équipes marquent',
  'selections.market.firstHalfResult': 'Résultat à la mi-temps',
  'selections.market.teamToScoreFirst': 'Première équipe à marquer',
  'selections.market.exactScore': 'Score exact',
  'selections.market.homeTeam': 'Équipe à domicile',
  'selections.market.awayTeam': 'Équipe à l’extérieur',
  'selections.outcome.draw': 'Nul',
  'selections.outcome.orDraw': '{team} ou nul',
  'selections.outcome.either': '{home} ou {away}',
  'selections.outcome.drawNoBet': '{team} (mise remboursée si nul)',
  'selections.outcome.over': 'Plus de {line}',
  'selections.outcome.under': 'Moins de {line}',
  'selections.outcome.yes': 'Oui',
  'selections.outcome.no': 'Non',
  'selections.outcome.neither': 'Aucun but',
  'selections.period.regulation': 'Temps réglementaire (90 minutes)',
  'selections.period.firstHalf': '1re mi-temps',
  'selections.state.pending': 'En attente',
  'selections.state.won': 'Gagnée',
  'selections.state.lost': 'Perdue',
  'selections.state.void': 'Annulée',
  'selections.state.unresolved': 'Non résolue',
  'selections.state.draft': 'Brouillon',
  'selections.status.draft': 'Brouillon',
  'selections.status.saved': 'Enregistré',
  'selections.status.recorded': 'Noté comme placé',
  'selections.copy.untitled': 'Coupon',
  'selections.copy.count': '{count, plural, one {# sélection} other {# sélections}}',
  'selections.copy.probability': 'probabilité publiée {value}',
  'selections.copy.noProbability': 'aucune probabilité publiée',
  'selections.copy.priceUser': 'votre cote',
  'selections.copy.priceProvider': 'cote du fournisseur',
  'selections.copy.combinedPrice': 'Cote combinée : {price} (produit des cotes des sélections)',
  'selections.copy.noCombinedPrice': 'Cote combinée : indisponible — toutes les sélections n’ont pas de cote',
  'selections.copy.stake': 'Mise : {stake} {currency}',
  'selections.copy.potential': 'Retour brut {gross} {currency} · gain net {net} {currency} (d’après la cote indiquée)',
  'selections.copy.combinedProbability': 'Chance combinée ≈ {value}, en supposant les rencontres indépendantes (une approximation, pas une prévision calibrée)',
  'selections.copy.disclaimer': 'Les probabilités sont les prévisions publiées par le fournisseur, pas des cotes proposées. Aucun pari n’est placé par cette application.',
}

export default reader
