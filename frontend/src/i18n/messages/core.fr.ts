/**
 * Français — the CORE area.
 *
 * The French half of ./core.en.ts, and nothing else: the auth and account screens are in
 * ./auth.fr.ts, the expert screens in ./expert.fr.ts, the reader screens in ./reader.fr.ts, and
 * ./fr.ts composes them. `Area<'core'>` below is derived from ./core.en.ts, so a key added to
 * the English core and forgotten here is a compile error IN THIS FILE rather than an error in a
 * composed object three imports away.
 *
 * ── THIS TRANSLATION HAS NOT BEEN REVIEWED BY A NATIVE SPEAKER ──────────────────────────────
 *
 * It was produced by the same author as the English and has had no francophone review. That is a
 * statement of fact about its provenance, not modesty: this product is read by bettors in
 * Cameroon, and a market term that is merely plausible is worse than an English one, because a
 * reader will act on it without noticing there was ever a doubt. Every term below that I am less
 * than confident about is listed in the package report for a native reviewer, and the ones that
 * matter most are the market and settlement vocabulary:
 *
 *   1N2 · les deux équipes marquent · total de buts · score exact · taux de réussite ·
 *   push (rendered "égalité") · annulé (void) · non calculable (not scorable) ·
 *   réglé / règlement (settled / settlement) · périmé (stale) · quota (allowance)
 *
 * None of those is a guess at a fact — they are all our own words for our own concepts — but
 * "égalité" for a push and "réglé" for settled are the two I would most expect a reviewer to
 * change, and "1N2" is a convention rather than a translation. Added since, and equally unchecked:
 * "sans règlement" (not scored), "non calculable" (not scorable) and "éligible".
 *
 * ── AGREEMENT IS DONE BY THE PLURAL MACHINERY, NEVER BY HAND ────────────────────────────────
 *
 * FRENCH COUNTS ZERO AS SINGULAR. `Intl.PluralRules('fr').select(0)` is `"one"`, so "0 match",
 * "0 pronostic réglé", "0 compétition" — and an English-shaped `count === 1 ? '' : 's'`, or a
 * participle frozen at one number, writes "0 matchs" and "0 réglés" on exactly the screen a
 * reader meets first. Every message in this file that interpolates a count therefore states its
 * own branches, and the WHOLE agreeing phrase lives inside them: the noun, the verb, any
 * participle and any adjective that agrees with it. "Après {n} échec{s} consécutifs" is the shape
 * to avoid — `consécutifs` agrees with `échecs` and cannot be left outside the branch.
 *
 * Three strings here are invariable on purpose rather than agreed, because the component prints
 * the count in its own element and never passes it to the message: `measured.notScoredReason`,
 * and the `measured.brierFrom` / `measured.brierPredictions` pair. The catalogue cannot agree with
 * a number it is not given; the fix belongs in the component and is listed in the package report.
 *
 * Every count-bearing string below is rendered at 0, 1, 2 and 11 by
 * frontend/e2e/mocked/localisation.spec.ts, and the expected form is written out there. A string
 * that is right at 2 and wrong at 1 fails that test.
 *
 * ── TYPOGRAPHY ──────────────────────────────────────────────────────────────────────────────
 *
 * French puts a no-break space before « : », « ; », « ! » and « ? ». It is written here as an
 * explicit ` ` escape rather than as an invisible character in the source, so it can be
 * reviewed in a diff and cannot be deleted by accident.
 *
 * ── WHAT IS NOT TRANSLATED, DELIBERATELY ────────────────────────────────────────────────────
 *
 * Team names, competition names, venue names and the city names in the time-zone picker stay as
 * the provider publishes them. That now includes the one competition this file names in prose:
 * the provider publishes "UEFA Champions League", the fixture list shows those words, and the
 * French prose used to say "la Ligue des champions" beside them — a translated competition name,
 * and a page disagreeing with itself about what the competition is called. It reads "la Champions
 * League" here, which leaves the name exactly as the English prose has it.
 *
 * So does every `{reason}` hole: those are filled with the backend's
 * or the provider's own words in every language, and replacing a source's message with our
 * paraphrase in another language would be putting words in its mouth. Our OWN summary of a
 * provider refusal (`freshness.reason.*`) is translated, because those sentences are ours — and
 * the provider's verbatim message stays on the page beside them, in the disclosure.
 *
 * Numbers, dates and times are not in this file at all. They are formatted by `Intl` in the
 * reader's locale and chosen time zone, which is why "2.5" reads 2,5 and 20:45 is 20:45 in
 * Douala rather than wherever the device happens to think it is.
 */

import type { Area } from './types'

const core: Area<'core'> = {
  // ─── le produit, et la coquille ─────────────────────────────────────────────────────────
  'app.name': 'Soccer Predictions',
  'app.htmlLang': 'fr',
  'app.defaultTitle': 'Soccer Predictions - Analyses de football',
  'app.defaultDescription': 'Prévisions de football fondées sur des analyses détaillées et des pronostics d’experts. Analyses de matchs et conseils de paris de football.',
  'app.brandHome': 'Soccer Predictions, accueil',
  'app.skipToMatches': 'Aller directement aux matchs',
  'app.topNavigation': 'Principale',

  'nav.home': 'Accueil',
  'nav.matches': 'Matchs',
  'nav.leagues': 'Compétitions',
  'nav.dashboard': 'Tableau de bord',
  'nav.expert': 'Expert',
  'nav.expertDashboard': 'Tableau de bord expert',
  'nav.accountMenu': 'Menu du compte',
  'nav.profileSettings': 'Paramètres du profil',
  'nav.changePassword': 'Changer le mot de passe',
  'nav.subscription': 'Abonnement',
  'nav.signOut': 'Se déconnecter',
  /*
   * « Connexion » et « Inscription », pas « Se connecter » et « Créer un compte ».
   *
   * Les deux formes longues sont correctes, et elles ne tiennent pas : mesuré à 200 % de zoom
   * texte sur un téléphone de 360 px, la barre étroite (marque, une action de compte, bouton de
   * menu) débordait de 76 px en français et de 0 px en anglais. Les formes nominales sont
   * l’usage courant sur les sites francophones et tiennent. « Créer un compte » reste la
   * formulation du panneau, où il y a la place.
   */
  'nav.signIn': 'Connexion',
  'nav.signUp': 'Inscription',
  'nav.createAccount': 'Créer un compte',
  'nav.openMenu': 'Ouvrir le menu principal',
  'nav.closeMenu': 'Fermer le menu principal',

  'search.placeholder': 'Rechercher une équipe, une compétition...',
  'search.searching': 'Recherche en cours...',
  'search.failed': 'La recherche a échoué. Veuillez réessayer.',
  'search.noResults': 'Aucun résultat pour «\u00a0{query}\u00a0»',
  'search.tryAnother': 'Essayez un autre terme de recherche',
  'search.teams': 'Équipes ({count})',
  'search.leagues': 'Compétitions ({count})',
  'search.keyboardHint': 'Utilisez ↑↓ pour naviguer, Entrée pour choisir, Échap pour fermer',

  'footer.tagline': 'Matchs, résultats et prévisions du modèle pour les cinq grands championnats européens et la Champions League, ainsi que les pronostics publiés par des experts inscrits. Chaque probabilité indique sa source. Rien ici n’est un conseil de pari.',
  'footer.quickLinks': 'Liens rapides',
  'footer.todaysMatches': 'Matchs du jour',
  'footer.tomorrowsMatches': 'Matchs de demain',
  'footer.signInRequired': ' (connexion requise)',
  'footer.support': 'Assistance',
  'footer.helpCentre': 'Centre d’aide',
  'footer.contactUs': 'Nous contacter',
  'footer.privacyPolicy': 'Politique de confidentialité',
  'footer.termsOfService': 'Conditions d’utilisation',
  'footer.notPublishedYet': '(pas encore publié)',
  'footer.rights': '© {year} Soccer Predictions. Tous droits réservés.',
  'footer.socialNotSetUp': 'Compte {network} pas encore créé',

  // ─── réglages de lecture ────────────────────────────────────────────────────────────────
  'settings.title': 'Réglages de lecture',
  'settings.language': 'Langue',
  'settings.languageHelp': 'La langue des textes de ce site. Elle ne change ni les noms d’équipes, ni les noms de compétitions, ni le message d’un fournisseur, qui sont affichés tels que publiés.',
  'settings.languageFellBack': 'Le texte français n’a pas pu être téléchargé, cette page est donc en anglais. Votre choix a été conservé et sera réessayé au prochain chargement.',
  'settings.timeZone': 'Fuseau horaire',
  'settings.timeZoneHelp': 'Toutes les heures de coup d’envoi de ce site sont affichées dans ce fuseau, et «\u00a0aujourd’hui\u00a0» désigne une journée dans ce fuseau.',
  'settings.timeZoneNow': 'Les heures sont affichées en {zone}.',
  'settings.useDeviceZone': 'Utiliser le fuseau de cet appareil ({zone})',
  'settings.zoneObservesDst': 'changement d’heure dans l’année',
  'settings.independent': 'La langue, le fuseau horaire et le lieu où vous êtes sont trois choses distinctes, et ce site les traite ainsi\u00a0: choisir l’un ne change rien aux autres, et aucun n’est considéré comme une preuve des autres. Votre pays n’est ni enregistré ni deviné.',
  'settings.notDurable': 'Ce navigateur ne nous laisse pas enregistrer vos choix\u00a0; ils ne s’appliqueront qu’à cette page et seront oubliés au rechargement.',
  'settings.openLabel': 'Langue et fuseau horaire',

  // ─── attendre une page, et ne pas l’obtenir ─────────────────────────────────────────────
  'route.loading': 'Chargement de cette page…',
  'route.notDownloadedTitle': 'Cette page n’a pas pu être téléchargée',
  'route.notDownloadedBody': 'Son code n’est pas arrivé en entier. Recharger suffit en général.',
  'route.failedTitle': 'Cette page n’a pas pu être affichée',
  'route.failedBody': 'Quelque chose a échoué pendant son affichage. Recharger peut aider\u00a0; sinon, la faute est de notre côté et non de votre connexion.',
  'route.reload': 'Recharger la page',

  'notFound.title': 'Page introuvable',
  'notFound.body': 'La page que vous cherchez n’existe pas ou a été déplacée.',
  'notFound.goHome': 'Retour à l’accueil',
  'notFound.documentTitle': 'Page introuvable - Soccer Predictions',
  'notFound.documentDescription': 'La page que vous cherchez est introuvable.',

  // ─── durées et instants ─────────────────────────────────────────────────────────────────
  // Le français met 0 et 1 au singulier : « 0 minute », « 1 minute », « 2 minutes ».
  'duration.minutes': '{count, plural, one {# minute} other {# minutes}}',
  'duration.hours': '{count, plural, one {# heure} other {# heures}}',
  'duration.days': '{count, plural, one {# jour} other {# jours}}',
  'time.justNow': 'à l’instant',
  'time.inUnderAMinute': 'dans moins d’une minute',
  'time.ago': 'il y a {duration}',
  'time.in': 'dans {duration}',

  // ─── la journée de matchs ───────────────────────────────────────────────────────────────
  'matchday.title.today': 'Matchs du jour',
  'matchday.title.tomorrow': 'Matchs de demain',
  'matchday.title.generic': 'Matchs',
  'matchday.relative.today': 'Aujourd’hui',
  'matchday.relative.tomorrow': 'Demain',
  'matchday.relative.yesterday': 'Hier',
  'matchday.dateLine': '{relative}, {date}',
  'matchday.timesIn': 'Heures en {zone}',
  'matchday.loading': 'Chargement des matchs…',
  'matchday.loadingCompetitions': 'Chargement des compétitions de cette date…',
  'matchday.errorTitle': 'Ces matchs n’ont pas pu être chargés.',
  'matchday.errorNote': 'Il s’agit d’un problème d’accès à notre propre service. Cela ne dit rien de ce qui se joue à cette date.',
  'matchday.retry': 'Réessayer',
  'matchday.emptyTitle': 'Aucun match enregistré pour cette date.',
  'matchday.emptyDescription': 'Cette installation ne contient aucun match pour le {date}. Les matchs apparaissent ici une fois récupérés et enregistrés\u00a0: c’est donc ce que nous détenons, et non une affirmation qu’il ne se joue rien.',
  'matchday.showTomorrow': 'Voir les matchs de demain',
  'matchday.showToday': 'Voir les matchs du jour',
  'matchday.pickAnotherDate': 'Choisir une autre date',
  'matchday.filteredEmptyTitle': 'Aucun match ne correspond à vos filtres.',
  'matchday.filteredEmptyDescription': '{count, plural, one {# match est enregistré} other {# matchs sont enregistrés}} pour le {date}\u00a0; aucun ne correspond à tous les filtres que vous avez posés.',
  'matchday.clearAllFilters': 'Effacer tous les filtres',
  // Le compte n’apparaît qu’au pluriel : « Voir le 1 match » n’est pas du français.
  'matchday.seeAll': '{count, plural, one {Voir le match} other {Voir les # matchs}}',
  'matchday.openWorkspace': 'Ouvrir la journée de matchs',
  'matchday.backToToday': 'Revenir à aujourd’hui',
  'matchday.moreCompetitions': '{count} de plus',
  'matchday.moreCompetitionsSr': ' compétitions, dans les filtres',
  'matchday.filterByCompetition': 'Filtrer par compétition',
  'matchday.footnote': 'Tous les matchs enregistrés pour cette date. Chaque probabilité est affichée exactement telle que la source l’a publiée, et un marché qu’aucune source n’a publié est indiqué comme indisponible plutôt qu’affiché à zéro.',
  'matchday.documentDescription': 'Matchs du {date} dans les cinq grands championnats européens et la Champions League, avec la prévision du modèle et le pronostic d’expert publié pour chaque rencontre. Chaque probabilité indique sa source\u00a0; un marché qu’aucune source n’a publié est affiché comme indisponible.',

  /*
   * L’accord se fait ici sur un nom qui n’apparaît qu’ensuite — « Aucun des 12 matchs » — et le
   * français compte 0 et 1 au singulier. C’est précisément ce qu’une traduction par fragments
   * ne peut pas produire.
   */
  'matchday.scoring.nonePlayed': '{count, plural, =0 {Aucun match n’est listé ici} one {Le match listé ici n’a pas encore été joué} other {Aucun des # matchs listés ici n’a encore été joué}}, donc rien sur cette page n’a été comparé à un résultat et aucune exactitude n’y est revendiquée.',
  'matchday.scoring.allPlayed': '{count, plural, =0 {Aucun match n’est listé ici} one {Le match listé ici {verb, select, finished {est terminé} other {a commencé}}} other {Les # matchs listés ici {verb, select, finished {sont terminés} other {ont commencé}}}}. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',
  'matchday.scoring.somePlayed': '{started, plural, one {# des {total} matchs listés ici {verb, select, finished {est terminé} other {a commencé}}} other {# des {total} matchs listés ici {verb, select, finished {sont terminés} other {ont commencé}}}}. La page de chaque match indique si un pronostic le concernant a été comparé à son résultat\u00a0; cette liste ne revendique aucune exactitude, dans un sens comme dans l’autre.',

  // ─── la barre des dates ─────────────────────────────────────────────────────────────────
  'dateStrip.chooseDate': 'Choisir une date',
  'dateStrip.previousDay': 'Jour précédent',
  'dateStrip.nextDay': 'Jour suivant',
  'dateStrip.jumpToDate': 'Aller à une date précise',
  'dateStrip.dayMatches': ', {count, plural, one {# match} other {# matchs}}',

  // ─── les filtres ────────────────────────────────────────────────────────────────────────
  'filters.open': 'Filtres',
  'filters.title': 'Filtres',
  'filters.close': 'Fermer les filtres',
  'filters.apply': 'Afficher les résultats',
  'filters.clearAll': 'Tout effacer',
  'filters.noneApplied': ', aucun filtre appliqué',
  'filters.countApplied': ', {count, plural, one {# filtre appliqué} other {# filtres appliqués}}',
  'filters.removeFilter': 'Retirer le filtre {label}',
  'filters.resultCount': '{count, plural, one {# match} other {# matchs}}',
  'filters.show': 'Afficher',
  'filters.showHint': 'Quels matchs de cette date sont listés.',
  'filters.whichFixtures': 'Quels matchs afficher',
  'filters.competitions': 'Compétitions',
  'filters.competitionsHintEmpty': 'Rien n’est enregistré pour cette date, il n’y a donc aucune compétition à choisir.',
  'filters.competitionsHint': 'N’en sélectionnez aucune pour voir toutes les compétitions.',
  'filters.markets': 'Marchés publiés',
  'filters.marketsHint': 'Ne garde que les matchs pour lesquels une source a réellement publié chaque marché que vous cochez. Un marché que personne n’a publié est absent des données, jamais un zéro.',
  'filters.sources': 'Sources',
  'filters.sourcesHint': 'Ne garde que les matchs qui ont la source que vous cochez.',
  'filters.group.competition': 'Compétition',
  'filters.group.market': 'Marché',
  'filters.group.source': 'Source',
  'filters.group.showing': 'Affichage',
  'filters.selectedCompetition': 'Compétition sélectionnée',
  'filters.status.all': 'Tout ce qui est à cette date',
  'filters.status.upcoming': 'À venir et en cours',
  'filters.status.finished': 'Joués',
  'filters.marketOption.1x2': 'Résultat du match (1N2)',
  'filters.marketOption.btts': 'Les deux équipes marquent',
  'filters.marketOption.overUnder': 'Plus / moins de buts',
  'filters.marketOption.correctScore': 'Score exact',
  'filters.sourceOption.model': 'A une prévision du modèle',
  'filters.sourceOption.expert': 'A un pronostic d’expert',

  'market.period.note': 'Aucune des sources ne publie la période que couvre un marché. Ils sont réglés d’après le score final enregistré\u00a0; lorsqu’une rencontre peut aller en prolongation ou aux tirs au but, la source ne dit pas si ceux-ci comptent.',
  'market.definition.1x2': 'Quelle équipe mène à la fin du match, ou match nul.',
  'market.definition.btts': 'Si les deux équipes marquent au moins un but.',
  'market.definition.overUnder': 'Si le total des buts des deux équipes dépasse ou non la ligne.',
  'market.definition.correctScore': 'Le nombre exact de buts marqués par chaque équipe.',

  // ─── un match dans la liste ─────────────────────────────────────────────────────────────
  'fixture.live': 'En direct',
  'fixture.ft': 'Fin',
  'fixture.postponed': 'Reporté',
  'fixture.cancelled': 'Annulé',
  'fixture.versus': '{home} contre {away}',
  'fixture.openAnalysis': '{fixture}. Ouvrir l’analyse complète.',
  'fixture.fullAnalysis': 'Analyse complète',
  'fixture.showDetails': 'Afficher le détail de {fixture}',
  'fixture.hideDetails': 'Masquer le détail de {fixture}',
  'fixture.side.home': 'Dom.',
  'fixture.side.draw': 'Nul',
  'fixture.side.away': 'Ext.',
  'fixture.aDraw': 'un match nul',
  'fixture.confidencePublished': 'confiance de {percent}, publiée par {source, select, model {le modèle} other {l’expert}}',
  'fixture.leadTitle': '{source}\u00a0: {outcome} à {percent}, tel que publié par la source.',
  'fixture.noMatchResult': 'Cette source n’a rien publié pour le résultat du match.',
  'fixture.alsoPublished': '{source, select, model {Le modèle} other {L’expert}} a aussi publié',
  'fixture.groupCount': ' {count, plural, one {match} other {matchs}}',

  // ─── qui l’a dit ────────────────────────────────────────────────────────────────────────
  'source.model': 'Modèle',
  'source.expert': 'Expert',
  'source.description.model': 'Prévision publiée par le fournisseur du modèle',
  'source.description.expert': 'Pronostic publié par l’un de nos experts',
  // L’accord se fait sur le nom sous-entendu : « prévision » pour le modèle (féminin),
  // « pronostic » pour l’expert (masculin).
  'source.state.stale': '{source, select, expert {périmé} other {périmée}}',
  'source.state.referenceOnly': 'pour référence',
  'source.state.unavailable': '{source, select, expert {aucun} other {aucune}}',
  'source.markerDescription': '{description} — {suffix}',

  // ─── marchés, issues, et les raisons d’une absence ──────────────────────────────────────
  'market.matchResult': 'Résultat du match',
  'market.btts': 'Les deux équipes marquent',
  'market.overUnder25': 'Total de buts 2,5',
  'market.overUnder35': 'Total de buts 3,5',
  'market.exactScore': 'Score exact',
  'market.correctScore': 'Score exact',

  'outcome.homeWin': 'Victoire à domicile',
  'outcome.draw': 'Match nul',
  'outcome.awayWin': 'Victoire à l’extérieur',

  'missing.noForecastRetrieved': 'Jamais récupérée',
  'missing.marketNotInForecast': 'Absent de cette prévision',
  'missing.forecastStale': 'Périmée',
  'missing.refreshBlocked': 'Actualisation en pause',
  'missing.noExpertPrediction': 'Aucun pronostic d’expert',
  'missing.marketNotSupplied': 'L’expert ne l’a pas renseigné',
  'missing.notOfferedBySource': 'Non publié par cette source',

  'preview.noForecastRetrieved': 'Aucune prévision n’a jamais été récupérée pour ce match\u00a0; la vue du modèle sur cette rencontre est donc inconnue.',
  'preview.marketNotInForecast': 'Une prévision a été récupérée pour ce match, mais elle ne contenait pas ce marché.',
  'preview.noExpertPrediction': 'Aucun expert n’a publié de pronostic pour ce match.',
  'preview.marketNotSupplied': 'L’expert a publié un pronostic pour ce match, mais a laissé ce marché de côté.',
  'preview.refreshBlocked': 'Les actualisations des prévisions sont en pause en ce moment.',

  'probability.unavailable': 'Indisponible',
  'probability.notSet': 'non renseigné',
  'confidence.band.veryHigh': 'Très élevée',
  'confidence.band.high': 'Élevée',
  'confidence.band.medium': 'Moyenne',
  'confidence.band.low': 'Faible',

  // ─── l’âge d’une prévision ──────────────────────────────────────────────────────────────
  'brief.noForecastHeld': 'Aucune prévision détenue',
  'brief.noForecastHeldDetail': 'Rien n’a été récupéré auprès du fournisseur de prévisions pour ce match.',
  'brief.ageUnknown': 'Âge inconnu',
  'brief.ageUnknownDetail': 'Le fournisseur n’a publié aucune heure d’exécution du modèle pour cette prévision\u00a0; son âge ne peut donc pas être indiqué.',
  'brief.basisNote': 'Le fournisseur n’a publié aucune heure d’exécution du modèle\u00a0: cet âge est donc mesuré depuis notre récupération de la prévision, et non depuis sa production.',
  'brief.keptForReference': 'Conservée pour référence',
  'brief.keptForReferenceAged': 'Conservée pour référence · {age} d’ancienneté',
  'brief.kickoffPassedDetail': 'Le coup d’envoi est passé. Ceci est conservé comme la prévision qui avait été publiée, et non proposé comme une prévision actuelle.',
  'brief.outOfDate': 'Périmée',
  'brief.outOfDateAged': 'Périmée · {age} d’ancienneté',
  'brief.staleDetail': 'Cette prévision est plus ancienne que la limite de fraîcheur.',
  'brief.staleDetailWithLimit': 'Cette prévision est plus ancienne que la limite de fraîcheur (limite\u00a0: {hours, plural, one {# heure} other {# heures}}).',
  'brief.current': 'À jour',
  'brief.aged': '{age} d’ancienneté',

  'provenance.sourcePrefix': 'Source\u00a0: ',
  'provenance.refreshPaused': 'Actualisation en pause — {reason}',

  // ─── les sources, nommées ───────────────────────────────────────────────────────────────
  'provider.gameforecast': 'Modèle GameForecast',
  'provider.apiFootball': 'Modèle API-Football',
  'provider.sample': 'Données d’exemple (non réelles)',
  'provider.expert': 'Expert',
  'provider.namedModel': 'Modèle {name}',
  'provider.model': 'Modèle',
  'provider.none': 'Le fournisseur de prévisions',

  'prediction.none': 'Aucun pronostic',
  'prediction.expert': 'Pronostic d’expert',
  'prediction.placeholder': 'Exemple (démonstration)',

  'bet.homeWin': 'Victoire à domicile',
  'bet.draw': 'Match nul',
  'bet.awayWin': 'Victoire à l’extérieur',
  'bet.bttsYes': 'Les deux équipes marquent\u00a0: oui',
  'bet.bttsNo': 'Les deux équipes marquent\u00a0: non',
  'bet.overGoals': 'Plus de {line} buts',
  'bet.underGoals': 'Moins de {line} buts',

  'generation.modelRun': 'Modèle exécuté le {when}',
  'generation.retrievedOnly': 'Heure de production non publiée\u00a0; récupérée le {when}',
  'generation.published': 'Publiée le {when}',

  // ─── les fournisseurs de matchs ─────────────────────────────────────────────────────────
  'fixtureProvider.livescore': 'Live Score API',
  'fixtureProvider.apiFootball': 'API-Football (secours)',
  'fixtureProvider.thesportsdb': 'TheSportsDB (secours)',
  'fixtureProvider.sample': 'données d’exemple (matchs non réels)',
  'fixtureProvider.none': 'aucun fournisseur',

  // ─── l’actualisation programmée ─────────────────────────────────────────────────────────
  'sync.task.fixtures': 'Matchs et heures de coup d’envoi',
  'sync.task.live': 'Scores en direct',
  'sync.task.results': 'Résultats finaux',
  'sync.task.forecasts': 'Prévisions du modèle',

  'freshness.stored': 'Données stockées',
  'freshness.summary.unknown': 'Données stockées · leur actualité ne peut pas être établie',
  'freshness.summary.noSchedule': 'Données stockées · aucune actualisation programmée n’est signalée',
  'freshness.summary.switchedOff': 'Données stockées · l’actualisation programmée est désactivée',
  'freshness.summary.noStateStore': 'Données stockées · la date de la dernière actualisation est inconnue',
  'freshness.summary.noFixtureTask': 'Données stockées · rien ici n’actualise les matchs ni les scores',
  'freshness.summary.refreshed': 'Données stockées · dernière actualisation des matchs et des scores {age}',
  'freshness.summary.neverRun': 'Données stockées · aucune actualisation programmée n’a encore été exécutée',
  'freshness.summary.neverSucceeded': 'Données stockées · aucune actualisation programmée n’a encore réussi',

  'freshness.note.noStatus': 'Le service d’état n’a pas pu être joint\u00a0; la date de la dernière actualisation est donc inconnue.',
  'freshness.note.noSchedule': 'Cette installation ne signale aucune actualisation programmée\u00a0: les données stockées ne changent que lorsqu’une page demande de nouvelles données au fournisseur.',
  'freshness.note.switchedOff': 'Les actualisations automatiques sont désactivées ici. Ce qui est stocké le reste tant que personne ne l’actualise.',
  'freshness.note.noStateStore': 'Le planificateur ne peut pas joindre son magasin d’état\u00a0; il ne peut donc pas indiquer quand une tâche a été exécutée pour la dernière fois.',
  'freshness.note.noFixtureTask': 'Aucune tâche programmée sur cette installation n’actualise les matchs, les heures de coup d’envoi ou les résultats.',
  'freshness.note.noPassYet': 'Le planificateur fonctionne mais aucune tâche n’a encore terminé un passage\u00a0; il n’y a donc aucune heure d’actualisation à indiquer.',

  'freshness.forecasts.switchedOff': 'Prévisions du modèle · l’actualisation automatique est désactivée',
  'freshness.forecasts.refreshed': 'Dernière actualisation des prévisions du modèle {age}',
  'freshness.forecasts.neverRun': 'Prévisions du modèle · aucune actualisation n’a encore été exécutée',
  'freshness.forecasts.neverSucceeded': 'Prévisions du modèle · aucune actualisation n’a encore réussi',
  'freshness.forecasts.ageNotReported': 'Prévisions du modèle · la date de leur dernière actualisation n’est pas indiquée',

  // Tournures nominales, pour qu’aucun participe n’ait à s’accorder avec le nom de la tâche.
  'freshness.task.switchedOff': 'actualisation désactivée',
  'freshness.task.switchedOffDetail': 'Cette tâche n’est pas activée sur cette installation\u00a0; rien ne l’actualise automatiquement.',
  'freshness.task.neverRun': 'aucune exécution à ce jour',
  'freshness.task.neverSucceeded': 'aucune exécution réussie à ce jour',
  'freshness.task.pausedSuffix': '{state} — en pause',
  'freshness.task.updated': 'dernière mise à jour {when}',
  'freshness.task.noFailureReason': 'Le serveur n’a pas indiqué pourquoi la dernière tentative a échoué.',
  'freshness.task.pausedDetail': 'En pause\u00a0: {reason}',
  'freshness.task.failedDetail': 'Dernière tentative en échec\u00a0: {reason}',
  'freshness.task.behindDetail': 'Cette tâche a plus d’un intervalle complet de retard.',
  'freshness.task.providerSaid': 'Le fournisseur a répondu\u00a0: {reason}',

  'freshness.line.failed': '{task}\u00a0: dernière tentative en échec — {reason}',
  'freshness.line.paused': '{task}\u00a0: en pause — {reason}',
  'freshness.line.behind': '{task}\u00a0: plus d’un intervalle complet de retard\u00a0; ce qui est stocké peut donc être plus ancien que ne le prévoit la planification.',
  'freshness.line.mechanics': '{task}\u00a0: {detail}',
  'freshness.reason.unstated': 'le serveur n’a pas dit pourquoi',
  'freshness.reason.quota': 'le fournisseur a refusé la requête car notre quota quotidien auprès de lui est épuisé',
  'freshness.reason.budget': 'notre propre quota quotidien de requêtes pour ce fournisseur est épuisé',
  'freshness.reason.credentials': 'le fournisseur a rejeté nos identifiants',
  'freshness.reason.timeout': 'le délai d’attente a expiré avant toute réponse',

  'freshness.nextAttempt.ahead': 'La prochaine tentative est prévue {when}.',
  'freshness.nextAttempt.dueNow': 'La prochaine tentative est attendue maintenant.',
  'freshness.nextAttempt.overdueMinutes': 'La prochaine tentative a {count, plural, one {# minute} other {# minutes}} de retard.',
  'freshness.nextAttempt.overdueHours': 'La prochaine tentative a {count, plural, one {# heure} other {# heures}} de retard.',
  'freshness.nextAttempt.overdueDays': 'La prochaine tentative a {count, plural, one {# jour} other {# jours}} de retard.',
  'freshness.nextScheduled': 'La prochaine tentative programmée est prévue {when}.',

  // « toutes les 6 heures » mais « tous les 2 jours » : l’accord se fait sur l’unité, que la
  // chaîne de durée traduite ne porte plus une fois assemblée. D’où le paramètre `unit`.
  'freshness.cadence': '{unit, select, day {Exécution programmée tous les {duration}.} other {Exécution programmée toutes les {duration}.}}',
  'freshness.backoff.none': 'Attente de {window} avant une nouvelle tentative.',
  'freshness.backoff.afterOne': 'Après 1 échec, attente de {window} avant une nouvelle tentative.',
  // « consécutifs » s’accorde avec « échecs » : il doit donc vivre dans les branches, pas après.
  'freshness.backoff.afterMany': 'Après {count, plural, one {# échec consécutif} other {# échecs consécutifs}}, attente de {window} avant une nouvelle tentative.',
  'freshness.allowanceReset': 'Notre quota quotidien de requêtes est compté par jour UTC\u00a0; il est donc réinitialisé à 00:00 UTC.',
  'freshness.allowanceResetWhen': 'Notre quota quotidien de requêtes est compté par jour UTC\u00a0; il est donc réinitialisé à 00:00 UTC — {when}.',

  'freshness.panel.heading': 'Actualité de ces données',
  'freshness.panel.label': 'Actualité de cette page',
  'freshness.panel.disclosure': 'Ce qui a été actualisé, et quand',
  'freshness.panel.lastAnswerFrom': 'Dernière réponse de {provider}\u00a0:',
  'freshness.panel.notAnswered': 'aucune réponse réussie à ce jour',
  'freshness.panel.pausedAfterFailure': 'En pause après un échec\u00a0: {reason}',
  'freshness.panel.ourTimes': 'Ce sont nos propres heures de récupération et d’actualisation. L’heure à laquelle le modèle d’un fournisseur a réellement été exécuté est un fait différent, publié avec chaque prévision sur la page de son match.',

  // ─── prévisions du modèle : en pause, ou indisponibles, jamais les deux à la fois ───────
  'forecast.notConfigured': 'Le fournisseur de prévisions «\u00a0{provider}\u00a0» n’est pas configuré\u00a0; les prévisions du modèle sont indisponibles.',
  'forecast.pausedAllowance': 'Les mises à jour des prévisions du modèle sont en pause jusqu’à la réinitialisation du quota quotidien de requêtes\u00a0; les prévisions déjà chargées restent visibles.',
  'forecast.pausedError': 'Les mises à jour des prévisions du modèle sont en pause après une erreur du fournisseur\u00a0: {reason}. Les prévisions déjà chargées restent visibles.',
  'forecastSync.pausedWithReason': 'L’actualisation de {provider} est en pause\u00a0: {reason}',
  // L’anglais écrit « competition(s) ». Le français a de quoi faire l’accord ; il le fait.
  'forecastSync.pausedDeferred': 'L’actualisation de {provider} est en pause\u00a0; {count, plural, one {# compétition attend} other {# compétitions attendent}} la prochaine réinitialisation du quota',
  'forecastSync.stayVisible': 'Les prévisions déjà chargées restent visibles et inchangées — elles ne sont simplement pas mises à jour en ce moment.',
  'forecastSync.waitingFor': 'En attente de la prochaine réinitialisation du quota\u00a0: {competitions}',
  'forecastSync.lastAttempt': 'Dernière tentative d’actualisation {when}',
  'forecastSync.disclosure': 'Ce que cela signifie pour ce que vous lisez',

  // ─── d’où viennent les matchs ───────────────────────────────────────────────────────────
  'dataSource.staleTitle': 'Affichage des derniers matchs enregistrés.',
  'dataSource.staleTitleWhen': 'Affichage des derniers matchs enregistrés (du {when}).',
  'dataSource.staleBody': 'Le fournisseur de données n’a pas pu être joint\u00a0; les heures de coup d’envoi et les scores peuvent être périmés.',
  'dataSource.unavailableTitle': 'Les données de matchs en direct sont indisponibles en ce moment.',
  'dataSource.providedBy': 'Matchs fournis par {provider}.',

  // ─── la bannière de panne ───────────────────────────────────────────────────────────────
  'banner.noProvider': 'Aucun fournisseur de données de matchs n’est configuré (DATA_PROVIDER={provider})\u00a0; les matchs ne peuvent pas être actualisés.',
  'banner.fallbackInUse': 'Le fournisseur principal «\u00a0{provider}\u00a0» n’est pas configuré\u00a0; {fallback} est utilisé en secours.',
  'banner.budgetExhausted': 'Le quota quotidien de requêtes pour {provider} est épuisé\u00a0; les données en cache sont affichées jusqu’à demain.',
  'banner.providerCoolingDown': 'Le fournisseur de matchs {provider} est en pause après un échec\u00a0: {reason}',
  'banner.lastRequestFailed': 'La dernière requête {provider} a échoué\u00a0: {reason}',
  'banner.dismiss': 'Masquer',
  'banner.oneMoreDetail': 'Un détail de fournisseur supplémentaire',
  'banner.moreDetails': '{count, plural, one {# détail de fournisseur supplémentaire} other {# détails de fournisseur supplémentaires}}',

  // ─── états vides et états en échec ──────────────────────────────────────────────────────
  'emptyState.couldNotLoad': 'Chargement impossible. ',
  'emptyState.unavailableNow': 'Indisponible en ce moment. ',

  // ─── erreurs de requête ─────────────────────────────────────────────────────────────────
  'error.serviceUnavailable': 'Le service est temporairement indisponible.',
  'error.timedOut': 'La requête a expiré.',

  // ─── enregistrer un match ───────────────────────────────────────────────────────────────
  'save.thisMatch': 'ce match',
  'save.signInTo': 'Connectez-vous pour enregistrer {subject}',
  'save.savedRemove': '{subject} est enregistré. Sélectionnez pour le retirer de vos matchs enregistrés.',
  'save.addTo': 'Enregistrer {subject} dans vos matchs enregistrés.',
  'save.signInShort': 'Se connecter pour enregistrer',
  'save.saved': 'Enregistré',
  'save.save': 'Enregistrer',

  // ─── le bilan mesuré ────────────────────────────────────────────────────────────────────
  'measured.market.matchResult': 'Résultat du match',
  'measured.market.bothTeamsScore': 'Les deux équipes marquent',
  'measured.market.overUnder25': 'Total de buts 2,5',
  'measured.market.overUnder35': 'Total de buts 3,5',
  'measured.market.correctScore': 'Score exact',
  'measured.sourceKind.modelProvider': 'Fournisseur de modèle',
  'measured.sourceKind.expert': 'Expert',
  'measured.window': 'du {start} au {end}',
  'measured.excluded.pushes': '{count, plural, one {# égalité} other {# égalités}}',
  'measured.excluded.voids': '{count, plural, one {# annulé} other {# annulés}}',
  'measured.excluded.notScored': '{count, plural, one {# non calculable} other {# non calculables}}',
  'measured.counts': '{eligible, plural, one {# éligible} other {# éligibles}} · {parts}',
  'measured.counts.scored': '{count, plural, one {# réglé} other {# réglés}}',
  // « en attente de règlement » ne s’accorde pas : c’est un complément, pas un participe.
  'measured.counts.pending': '{count} en attente de règlement',
  'measured.counts.void': '{count, plural, one {# annulé} other {# annulés}}',
  'measured.counts.notScored': '{count, plural, one {# non calculable} other {# non calculables}}',

  'measured.state.notLoaded': 'Le bilan mesuré n’a pas été chargé.',
  'measured.state.failed': 'Le bilan mesuré n’a pas pu être chargé.',
  'measured.state.failedDetail': '{error} Cela ne dit rien de ce qui a été réglé ou non — seulement que nous n’avons pas pu le demander.',
  'measured.state.none': 'Rien n’a encore été réglé, aucune source n’a donc de bilan mesuré.',
  'measured.state.noneWhy': 'Pourquoi\u00a0: {reason}.',
  'measured.state.noneDetail': 'Aucun pronostic de cette fenêtre n’a été réglé face à un résultat final.',
  'measured.state.pending': 'Aucune source n’a encore de bilan mesuré.',
  'measured.state.pendingDetail': 'Les pronostics des sources ci-dessous entrent dans le champ, mais aucun n’a encore été réglé face à un résultat final. Les comptages sont réels\u00a0; il n’y a simplement aucun taux à indiquer.',
  'measured.state.measured': '{measured, plural, one {# source sur {total} a} other {# sources sur {total} ont}} un bilan mesuré.',
  'measured.state.measuredDetail': 'Chaque chiffre ci-dessous est compté à partir de résultats réglés et porte l’échantillon dont il est issu. C’est un relevé de ce qui s’est passé, pas une prévision de ce qui arrivera.',

  'measured.heading': 'Ce que les sources ont réellement fait',
  'measured.intro': 'Compté à partir des résultats réglés, en comparant ce qu’une source a publié avant le coup d’envoi à ce qui s’est passé. Noter une prévision est un calcul face à un résultat réel — ce n’est pas une nouvelle prévision, et rien de tout cela ne dit ce qui arrivera ensuite.',
  'measured.loading': 'Chargement du bilan mesuré…',
  'measured.windowLine': 'Fenêtre\u00a0: {window} — {basis}. Mesuré le {when}.',
  'measured.hitRate': 'de taux de réussite sur {sample, plural, one {# réglé} other {# réglés}}',
  'measured.hitRateWithheld': 'aucun taux de réussite publié',
  'measured.needMore': '{sample, plural, one {# pronostic réglé} other {# pronostics réglés}} sur {minimum, plural, one {# nécessaire} other {# nécessaires}} avant la publication d’un taux.',
  'measured.howCounted': 'Comment ce marché est compté et réglé',
  'measured.countedAs': 'Compté comme\u00a0: ',
  'measured.settledBy': 'Réglé selon\u00a0: ',
  'measured.sampleSize': 'Taille de l’échantillon\u00a0: ',
  'measured.sampleSizeValue': '{count, plural, one {pronostic réglé} other {pronostics réglés}}',
  'measured.correctOutcomes': 'Issues correctes\u00a0: ',
  /*
   * "sur", not "sur ces". The demonstrative has to agree with what follows, so "{hits} sur ces
   * {scored}" renders "1 sur ces 1" whenever a market has exactly one scored prediction — which
   * is the commonest state on a young installation, not an edge case. "X sur Y" is the ordinary
   * French way to write a ratio, it is correct at every count, and the label above the figure
   * already supplies what the count is of, so nothing is lost with the demonstrative.
   */
  'measured.hitCount': '{hits} sur {scored}',
  'measured.nothingScoredInMarket': 'rien n’a encore été réglé dans ce marché, rien n’y est donc juste ni faux',
  'measured.notInSample': 'Hors échantillon\u00a0: ',
  'measured.brier': 'Score de Brier\u00a0: ',
  'measured.brierFrom': 'sur',
  'measured.brierPredictions': 'pronostics',
  'measured.brierBaseline': ' · une prévision non informative obtient',
  'measured.brierWithheld': 'calculable pour {sample, plural, one {# pronostic} other {# pronostics}} à ce jour\u00a0; {minimum, plural, one {# est nécessaire} other {# sont nécessaires}} avant la publication d’un score de Brier',
  'measured.sourceUnmeasured': 'Rien de cette source n’a encore été réglé dans cette fenêtre.',
  /*
   * UNE TOURNURE INVARIABLE, PARCE QUE LE NOMBRE N’ARRIVE PAS JUSQU’ICI.
   *
   * MeasuredRecord.tsx écrit le compte dans son propre `<span>` et ne passe que `{reason}` :
   * « 1 non réglés » était donc inévitable avec un participe. « sans règlement » ne s’accorde
   * pas et reste juste à 1 comme à 11. La vraie correction est de passer le compte au message ;
   * elle appartient au composant, pas à ce catalogue.
   */
  'measured.notScoredReason': 'sans règlement — {reason}',
  'measured.rulesDisclosure': 'Les règles selon lesquelles chaque chiffre a été réglé',
  'measured.rules.ruleset': 'Jeu de règles\u00a0: ',
  'measured.rules.basis': 'Base\u00a0: ',
  'measured.rules.prematchOnly': 'Uniquement les éléments d’avant coup d’envoi\u00a0: ',
  'measured.rules.void': 'Matchs annulés\u00a0: ',
  'measured.rules.unsuppliedMarket': 'Un marché qu’une source n’a pas publié\u00a0: ',
  'measured.rules.hitRate': 'Taux de réussite\u00a0: ',
  'measured.rules.brier': 'Score de Brier\u00a0: ',

  // ─── la page d’accueil ──────────────────────────────────────────────────────────────────
  'home.documentTitle': 'Soccer Predictions - Matchs, prévisions du modèle et analyses d’experts',
  'home.documentDescription': 'Matchs et résultats des cinq grands championnats européens et de la Champions League, avec les prévisions du modèle GameForecastAPI et les pronostics publiés par des experts inscrits.',
  'home.coverageHeading': 'Combien de football est chargé en ce moment',
  'home.coverageCounting': 'Comptage de ce qui est enregistré…',
  'home.coverageFailed': 'Les comptages des données enregistrées n’ont pas pu être chargés\u00a0; rien n’est donc affirmé sur ce qui se trouve ici.',
  'home.coverageStored': '{fixtures, plural, one {# match à venir enregistré} other {# matchs à venir enregistrés}} dans {competitions, plural, one {# compétition} other {# compétitions}}.',
  /*
   * Deux accords et un cas limite. Le verbe suit `withForecast` (« 1 porte », « 12 portent »),
   * et la seconde moitié ne peut pas garder « les {without} autres » : à 1 cela donnerait « les
   * 1 autres » et à 0 un pluriel que le français ne fait pas. À 0, la phrase anglaise (« the
   * other 0 have none ») se dit en français par l’affirmative, qui énonce exactement le même
   * fait sans écrire un zéro dans un groupe déterminé.
   */
  'home.coverageForecasts': '{withForecast, plural, one {# d’entre eux porte une prévision du modèle} other {# d’entre eux portent une prévision du modèle}}\u00a0; {without, plural, =0 {aucun n’en est dépourvu} one {l’autre n’en a aucune} other {les # autres n’en ont aucune}}.',
  'home.coverageExperts': '{count, plural, one {# pronostic d’expert a été publié} other {# pronostics d’experts ont été publiés}}.',
  'home.coverageNoExperts': 'Aucun expert n’a encore publié de pronostic.',
  'home.coverageDisclosure': 'Les comptages un par un',
  'home.coverageCountedFrom': 'Compté à partir des données enregistrées.',
  'home.coverageCountedFromWhen': 'Compté à partir des données enregistrées le {when}.',
  'home.stat.competitions': 'Compétitions couvertes',
  'home.stat.competitionsDetail': 'Les cinq grands championnats européens et la Champions League',
  'home.stat.fixtures': 'Matchs à venir chargés',
  'home.stat.fixturesDetail': 'Matchs programmés et en cours actuellement enregistrés',
  'home.stat.forecasts': 'Prévisions du modèle disponibles',
  'home.stat.forecastsDetail': 'Matchs à venir auxquels une prévision du modèle GameForecast est rattachée',
  // Sans « les » : « sur les 1 matchs » n’existe pas, et « sur 1 match » est juste à tout compte.
  'home.stat.forecastsDetailOf': '{total, plural, one {Sur # match à venir enregistré} other {Sur # matchs à venir enregistrés}}\u00a0; les autres n’ont aucune prévision du modèle rattachée',
  'home.stat.expertPredictions': 'Pronostics d’experts publiés',
  'home.stat.expertPredictionsDetail': 'Publiés par des experts inscrits sur ce site',
  'home.statUnavailable': 'Indisponible',
  'home.aboutHeading': 'D’où viennent ces chiffres',
  'home.aboutBody': 'Matchs et résultats des cinq grands championnats européens et de la Champions League, avec les prévisions du modèle GameForecastAPI et les pronostics publiés par des experts inscrits. Chaque probabilité provient d’une source nommée et est reproduite telle que cette source l’a publiée. Rien de tout cela n’est un conseil de pari.',
  'home.methodDisclosure': 'Les règles que ce site s’impose',
  'home.method1': 'Rien n’est calculé ici à votre place. Lorsqu’une source n’a pas publié un marché, le match le dit avec les mots de la source plutôt que d’afficher un zéro, et lorsqu’une prévision est plus ancienne qu’elle ne devrait l’être, le match le dit aussi.',
  'home.method2': 'La fréquence à laquelle chaque source a eu raison n’est pas devinée non plus\u00a0: elle est comptée à partir de résultats réglés, et le bilan mesuré ci-dessous montre exactement ce qui a été compté à ce jour. En dessous de l’échantillon minimal, aucun taux n’est publié du tout — les comptages sont affichés et le pourcentage est retenu, car un taux tiré d’une poignée de résultats induirait en erreur.',
  'home.method3': 'Une probabilité n’est pas une prévision de ce qui va se passer, et une probabilité publiée pour un match n’est pas un relevé de la fréquence à laquelle sa source a eu raison.',
  'home.browseByDate': 'Parcourir les matchs par date',
  'home.competitions': 'Compétitions',
  'home.followHeading': 'Suivez les matchs qui comptent',
  'home.followBody': 'Créez un compte pour enregistrer des matchs et suivre les équipes et compétitions qui vous intéressent. Les prévisions et les analyses d’experts sont publiques dans tous les cas, sur chaque match où une source en a publié.',
  'home.createAccount': 'Créer un compte',
  'home.tomorrowsMatches': 'Matchs de demain',
}

export default core
