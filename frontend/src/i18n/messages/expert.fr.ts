/**
 * Français — the EXPERT area.
 *
 * ── THIS TRANSLATION HAS NOT BEEN REVIEWED BY A NATIVE SPEAKER ──────────────────────────────
 *
 * Same provenance and the same warning as ./core.fr.ts and ./auth.fr.ts: it was written by the
 * author of the English and no francophone has read it. The terms a reviewer is most likely to
 * change are listed in the package report. The three that matter most here are « Exactitude »
 * for the dashboard's accuracy tile (see the note on that key — the obvious alternative is
 * already taken by a different measurement and must not be borrowed), « Dépublier » for
 * Unpublish, and « conviction », which is the word this product uses in English for a claim an
 * expert makes about their own certainty and which carries over into French intact but is not
 * the only possible choice.
 *
 * ── WHAT A WRONG WORD WOULD COST HERE, WHICH IS NOT THE USUAL COST ──────────────────────────
 *
 * These screens are where a person writes down a probability that other people will read. Three
 * translations were chosen against the more natural-sounding option because the natural-sounding
 * one would have changed what the sentence CLAIMS:
 *
 *  1. `expert.dashboard.accuracy` is « Exactitude », not « Taux de réussite ». « Taux de
 *     réussite » is already `measured.hitRate` in ./core.fr.ts — the settlement engine's
 *     measured hit rate, computed from scored predictions against a stated minimum sample. The
 *     tile on this page is `accuracy_rate` from the expert analytics endpoint, a different
 *     number from a different pipeline. Giving them the same French words would let a reader
 *     take an unmeasured figure for the measured one, which is the exact confusion the measured
 *     record was built to prevent.
 *  2. `expert.dashboard.notScoredYet` is « Pas encore évaluée » — feminine, agreeing with « l'
 *     exactitude », and a STATEMENT THAT NO MEASUREMENT EXISTS. It sits in the slot a percentage
 *     would occupy. It may never be shortened to something a reader could scan as a figure, and
 *     it may never become « 0 % ».
 *  3. `expert.dashboard.nonePublished` is « Aucune publiée » — feminine, agreeing with « la
 *     conviction ». It stands in for a NULL `average_confidence`, which means no expert ever
 *     claimed a conviction. A stored 0 is a separate case: an expert who claimed zero
 *     confidence, which the dashboard prints as « 0 % ». « 0 % » is not a wrong rendering of
 *     this slot, it is the rendering of the other case, and the two must not be swapped in
 *     either direction — « Aucune publiée » over a claimed zero erases a judgement somebody made
 *     and contradicts the « Publiés » count beside it, and « 0 % » over a null invents one. The
 *     page and frontend/e2e/mocked/expert-localisation.spec.ts distinguish them.
 *
 * And one that is about force rather than about a number: `expert.compose.publishImmediate` and
 * `expert.published.body` are in the indicative — « Publier rend ceci public immédiatement »,
 * « Rien n'attend de validation ». Not « peut rendre », not a conditional. A prematch deadline
 * and an irreversible publication are not suggestions in either language.
 *
 * ── AGREEMENT, AND WHY NOTHING HERE COUNTS ──────────────────────────────────────────────────
 *
 * No message in this area uses ICU `plural`, in either language, and that is deliberate rather
 * than an omission — see the header of ./expert.en.ts. The counts these screens show sit in
 * fixed list labels (« Vos pronostics (0) », « Signalés pour modération (0) ») exactly as the
 * English shipped them, and « Page » does not agree with its number. Every one of them is still
 * rendered at 0, 1, 2 and 11 in frontend/e2e/mocked/expert-localisation.spec.ts, because "it
 * needs no branch" is a claim that should be checked rather than asserted.
 *
 * Gender still does work here even without plurals. « Pas encore évaluée » and « Aucune
 * publiée » above; « Publiés », « Non publiés », « Dépubliés » and « Signalés » on the record
 * and moderation tiles, agreeing with « les pronostics »; « Créé » and « Publié » on a
 * prediction's own timestamps, agreeing with « le pronostic ».
 *
 * ── TYPOGRAPHY ──────────────────────────────────────────────────────────────────────────────
 *
 * French puts a no-break space before « : », « ; », « ! » and « ? », and inside « guillemets ».
 * It is written as an explicit `\u00a0` escape rather than as an invisible character, so a
 * reviewer can see it in a diff and nobody deletes it by accident. `expert.page.number` carries
 * one too, between the word and the numeral it governs.
 *
 * ── WHAT IS NOT TRANSLATED ──────────────────────────────────────────────────────────────────
 *
 * The backend's own words — a prediction's source, status and priority level, and the text of
 * any API error — are rendered verbatim in both languages. Team, competition and account names
 * come from the provider or the account. Numbers, dates and times are formatted, never written.
 */

import type { Area } from './types'

const expert: Area<'expert'> = {
  // ─── shared across the expert screens ───────────────────────────────────────────────────
  'expert.backToDashboard': 'Retour au tableau de bord',
  /** French does not title-case a heading, so the two English casings converge here. */
  'expert.backToDashboardCaps': 'Retour au tableau de bord',
  'expert.retry': 'Réessayer',
  'expert.fixtureShort': '{home} contre {away}',
  'expert.versusShort': 'contre',
  'expert.reasoningLabel': 'Justification\u00a0:',
  'expert.deleteFailed': 'Échec de la suppression du pronostic',

  'expert.action.edit': 'Modifier',
  'expert.action.publish': 'Publier',
  'expert.action.unpublish': 'Dépublier',
  'expert.action.working': 'En cours…',
  'expert.action.delete': 'Supprimer',
  'expert.action.deleting': 'Suppression...',
  'expert.action.saving': 'Enregistrement...',
  'expert.action.saveChanges': 'Enregistrer les modifications',
  'expert.action.cancel': 'Annuler',
  'expert.action.viewDetails': 'Voir le détail',
  'expert.action.hideDetails': 'Masquer le détail',
  'expert.action.processing': 'Traitement...',
  'expert.action.preview': 'Aperçu',
  'expert.action.publishing': 'Publication…',
  'expert.action.writePrediction': 'Rédiger un pronostic',

  'expert.publication.confirmUnpublish': 'Dépublier ce pronostic\u00a0? Les lecteurs ne le verront plus sur la page du match. Vous pourrez le publier à nouveau plus tard.',
  'expert.publication.confirmPublish': 'Publier ce pronostic\u00a0? Les lecteurs le verront immédiatement sur la page du match.',
  /** « Bilan mesuré » is the measured record's name in ./core.fr.ts, and this is that record. */
  'expert.publication.kickedOffUnpublish': 'Le coup d’envoi a été donné. Dépublier ce pronostic maintenant le cache aux lecteurs, mais ne le retire pas de votre bilan mesuré, qui dépend de ce qui était publié au coup d’envoi.',
  'expert.publication.kickedOffPublish': 'Le coup d’envoi a été donné. Publier ce pronostic maintenant le montre aux lecteurs, mais ne l’ajoute pas à votre bilan mesuré, qui dépend de ce qui était publié au coup d’envoi.',

  'expert.page.previous': 'Précédent',
  'expert.page.next': 'Suivant',
  /** The insécable keeps the label and its numeral on one line, as French typography asks. */
  'expert.page.number': 'Page\u00a0{number}',

  'expert.line.over': 'Plus de {line}',
  'expert.line.under': 'Moins de {line}',
  'expert.line.overUnder': 'Plus / moins de {line}',

  // ─── the expanded record ────────────────────────────────────────────────────────────────
  'expert.details.predictionId': 'Identifiant du pronostic',
  'expert.details.matchId': 'Identifiant du match',
  'expert.details.priorityLevel': 'Niveau de priorité',
  'expert.details.confidence': 'Confiance',
  'expert.details.bttsConfidence': 'Confiance pour les deux équipes marquent',
  'expert.details.totalGoalsConfidence': 'Confiance pour le total de buts',
  'expert.details.published': 'Publié',
  'expert.details.notPublished': 'non publié',
  'expert.details.keyFactors': 'Facteurs clés',
  'expert.details.bttsPair': 'Les deux équipes marquent (oui / non)',
  'expert.details.factor': '{name}\u00a0: {value}',

  // ─── the status filter's own options ────────────────────────────────────────────────────
  'expert.status.all': 'Tous les statuts',
  'expert.status.pending': 'En attente',
  'expert.status.underReview': 'En cours d’examen',
  'expert.status.approved': 'Approuvé',
  'expert.status.published': 'Publié',
  'expert.status.rejected': 'Rejeté',
  'expert.status.archived': 'Archivé',

  // ─── the workspace ──────────────────────────────────────────────────────────────────────
  'expert.dashboard.title': 'Espace de travail de l’expert',
  'expert.dashboard.intro': 'Rédigez des pronostics et gérez ce que vous avez publié. Vos pronostics deviennent publics dès que vous appuyez sur Publier — rien ici n’attend de validation.',
  'expert.dashboard.loadFailed': 'Échec du chargement des données du tableau de bord',
  'expert.dashboard.toggleFailed': 'Échec du changement de l’état de publication',
  'expert.dashboard.confirmDelete': 'Supprimer ce pronostic\u00a0? Il disparaît de la page publique du match et l’opération est irréversible.',
  'expert.dashboard.nextHeading': 'Que faire ensuite',
  'expert.dashboard.chooseMatch': 'Choisir un match',
  'expert.dashboard.chooseMatchHint': 'Une seule liste filtrée de rencontres. Filtrez par jour, compétition ou équipe.',
  'expert.dashboard.myPredictions': 'Mes pronostics',
  'expert.dashboard.myPredictionsHint': 'Modifiez, dépubliez ou supprimez tout ce que vous avez publié.',
  'expert.dashboard.recentHeading': 'Pronostics récents',
  'expert.dashboard.emptyTitle': 'Vous n’avez encore rien publié',
  'expert.dashboard.emptyBody': 'Choisissez un match et rédigez votre premier pronostic. Il est en ligne dès que vous le publiez.',
  'expert.dashboard.recordHeading': 'Votre bilan',
  'expert.dashboard.statWritten': 'Pronostics rédigés',
  'expert.dashboard.statPublished': 'Publiés',
  'expert.dashboard.statNotPublished': 'Non publiés',
  /** Masculine plural, agreeing with « les pronostics », like « Publiés » and « Non publiés ». */
  'expert.dashboard.statUnpublished': 'Dépubliés',
  'expert.dashboard.statAverageConviction': 'Conviction moyenne',
  /** Feminine: it agrees with « la conviction ». For a NULL `average_confidence` only — a stored
   *  0 is a claimed zero and prints « 0 % ». This wording must never look like a figure. */
  'expert.dashboard.nonePublished': 'Aucune publiée',
  /** NOT « Taux de réussite » — that phrase is the measured hit rate. See the file header. */
  'expert.dashboard.accuracy': 'Exactitude',
  /** Feminine: it agrees with « l’exactitude ». It states that no measurement exists. */
  'expert.dashboard.notScoredYet': 'Pas encore évaluée',
  'expert.dashboard.accuracyNote': 'Aucun pronostic n’a encore été réglé face à un résultat final, il n’y a donc aucune exactitude à rapporter. La conviction moyenne ci-dessus est ce que vous avez revendiqué, pas une mesure de la fréquence à laquelle vous avez eu raison.',
  'expert.dashboard.moderationNote': 'Ceux-ci sont déjà publics. La modération a lieu après la publication — ce n’est pas une étape de validation.',
  'expert.dashboard.moderationLink': 'Voir la liste de modération',

  'expert.row.fixtureUnavailable': 'Détails de la rencontre indisponibles',
  'expert.row.competitionUnavailable': 'Compétition indisponible',
  'expert.row.publishedOn': 'Publié le {date}',

  // ─── the local drafts, one per fixture ───────────────────────────────────────────────────
  'expert.draft.listTitle': 'Vos brouillons non publiés',
  'expert.draft.listNote': 'Chaque rencontre garde son propre brouillon, dans ce navigateur uniquement. Aucun n’a été publié et aucun ne se publiera tout seul.',
  'expert.draft.noFixture': 'Rencontre pas encore choisie',
  'expert.draft.savedAgo': 'enregistré {ago}',
  'expert.draft.continue': 'Reprendre',
  'expert.draft.discard': 'Abandonner',
  'expert.draft.seeAll': 'Voir tous les brouillons',
  /** « d’avant-match », the term reader.fr.ts already uses for a selection made before kickoff. */
  'expert.draft.kickedOff': 'Coup d’envoi passé — ce brouillon ne peut plus être publié comme pronostic d’avant-match.',
  'expert.draft.discardConfirm': 'Abandonner votre brouillon pour {fixture}\u00a0? Cette action est irréversible.',
  'expert.draft.discardConfirmNoFixture': 'Abandonner ce brouillon\u00a0? Cette action est irréversible.',
  'expert.draft.confirmDiscard': 'Abandonner le brouillon',
  'expert.draft.keep': 'Le garder',
  'expert.draft.discarded': 'Brouillon abandonné.',
  'expert.draft.keptFor': 'Votre brouillon pour {fixture} est conservé. Vous pouvez y revenir depuis vos brouillons.',
  'expert.draft.saveFailed': 'Ce navigateur n’a pas voulu enregistrer votre brouillon. Rien n’est perdu tant que cette page reste ouverte, mais il ne survivra pas à un rechargement.',
  'expert.draft.assignHint': 'Choisissez la rencontre à laquelle ce brouillon se rapporte. Il n’y est déplacé que si vous n’avez pas encore de brouillon pour elle.',
  'expert.draft.assignTaken': 'Vous aviez déjà un brouillon pour {fixture}\u00a0: c’est celui-ci qui est ouvert. Le brouillon sans rencontre est toujours conservé.',
  'expert.draft.restored': 'Brouillon restauré. Il ne vit que dans ce navigateur et ne publie rien de lui-même.',
  'expert.draft.restoredSaved': 'Brouillon restauré · enregistré {ago}. Il ne vit que dans ce navigateur et ne publie rien de lui-même.',
  'expert.draft.startAgain': 'Recommencer',

  // ─── choosing a match ───────────────────────────────────────────────────────────────────
  'expert.selection.intro': 'Choisissez la rencontre sur laquelle vous voulez publier un avis. Votre pronostic est en ligne dès que vous appuyez sur Publier — il n’y a aucune étape de validation et rien à attendre.',
  'expert.selection.fixturesHeading': 'Rencontres',
  'expert.selection.fixturesHint': 'Filtrez par jour, compétition ou équipe. Les rencontres terminées, reportées et annulées sont écartées.',
  'expert.selection.howHeading': 'Comment un pronostic parvient aux lecteurs',
  'expert.selection.how1': 'Choisissez la rencontre ici.',
  'expert.selection.how2': 'Saisissez vos pourcentages — tapez {typed} pour {whole}, pas {decimal} — et ne cochez que les marchés que vous voulez publier.',
  'expert.selection.how3': 'Prévisualisez ce que les lecteurs verront, puis publiez.',
  'expert.selection.howNote': 'Les pronostics d’experts sont présentés séparément des prévisions des modèles et ne sont jamais fusionnés avec elles. Un marché que vous laissez de côté est indiqué comme indisponible plutôt que comme {zero}. La liste des rencontres ne couvre que les compétitions configurées.',

  /*
   * ─── le sélecteur de rencontres ────────────────────────────────────────────────────────
   *
   * NOT REVIEWED, like the rest of this file, and three of these are the ones a francophone
   * reviewer is most likely to change. They are listed in the package report as well:
   *
   *  1. « Jour des rencontres » for "Match day". The English is ambiguous — in football a
   *     "match day" is usually a ROUND of a competition, and this control picks a CALENDAR
   *     DATE. « Journée » is the French for the round and would have imported the ambiguity;
   *     « Jour du match » names one match when the list holds forty. « Jour des rencontres »
   *     says which day's fixtures are listed, which is what the control does.
   *  2. « Prévision du modèle détenue » for "Model forecast held". It is built to sit beside
   *     `brief.noForecastHeld` in ./core.fr.ts — « Aucune prévision détenue » — because the
   *     two badges are alternatives in the same slot and a reader compares them at a glance.
   *     « détenue » is deliberate and is the same verb that catalogue already chose: the
   *     forecast is HELD here, which is not the same claim as it having been produced now.
   *  3. « conviction » is not in these keys but governs the badge above them; see the header.
   *
   * AND ONE THAT IS NOT A WORD CHOICE BUT A SENTENCE SHAPE. `expert.picker.showing` counts,
   * and French is singular at 0 AND 1 — so « 1 rencontres » is what a naive translation of
   * "Showing 1 of 1 fixtures on this day." produces. No plural branch is available (see
   * ./expert.en.ts for why), so the noun is attached to NEITHER figure: « Rencontres affichées
   * ce jour-là : 1 sur 1. » is right at every count, not merely at the counts somebody tested.
   * It is still rendered at 0, 1, 2 and 11 in
   * frontend/e2e/mocked/expert-localisation.spec.ts, because that is a claim, not an excuse.
   */
  'expert.picker.dayLabel': 'Jour des rencontres',
  'expert.picker.dayAfterTomorrow': 'Dans deux jours',
  'expert.picker.searchLabel': 'Filtrer par équipe ou compétition',
  'expert.picker.searchPlaceholder': 'Équipe ou compétition',
  'expert.picker.competitionGroup': 'Filtrer par compétition',
  'expert.picker.onlyWithoutExpert': 'Uniquement les rencontres qui n’ont pas encore de pronostic d’expert',
  'expert.picker.clearFilters': 'Effacer les filtres',
  'expert.picker.loading': 'Chargement des rencontres…',
  'expert.picker.showing': 'Rencontres affichées ce jour-là : {shown} sur {total}.',
  'expert.picker.expertPublished': 'Pronostic d’expert publié',
  'expert.picker.modelForecastHeld': 'Prévision du modèle détenue',
  /** « coup d’envoi » is the kick-off; `{time}` is already in the reader's chosen zone. */
  'expert.picker.rowAction': '{action} : {home} contre {away}, {competition}, coup d’envoi à {time}',
  'expert.picker.loadFailed': 'La liste des rencontres n’a pas pu être chargée',
  'expert.picker.emptyFilteredTitle': 'Aucune rencontre ne correspond à ces filtres',
  'expert.picker.emptyFilteredBody': 'Élargissez les filtres, ou passez à un autre jour.',
  'expert.picker.emptyDayTitle': 'Aucune rencontre sur laquelle écrire ce jour-là',
  'expert.picker.emptyDayBody': 'Les rencontres terminées, reportées et annulées sont écartées. Essayez un autre jour.',
  'expert.picker.dayShown': 'Rencontres du {date}',
  'expert.picker.kickedOff': 'Coup d’envoi passé — un pronostic publié maintenant n’est pas comptabilisé',
  /*
   * Built on « Prévision du modèle détenue » above, and with the adjectives ./core.fr.ts already
   * gives a forecast in these two states (`brief.outOfDate` « Périmée », `brief.keptForReference`
   * « Conservée pour référence »), feminine to agree with « la prévision ». A stored forecast that
   * is out of date is still HELD, which is the claim « Aucune prévision détenue » got wrong.
   */
  'expert.picker.modelForecastStale': 'Prévision du modèle détenue · périmée',
  'expert.picker.modelForecastReference': 'Prévision du modèle conservée pour référence',

  // ─── the composer ───────────────────────────────────────────────────────────────────────
  'expert.compose.title': 'Rédiger un pronostic',
  'expert.compose.chooseIntro': 'Commencez par choisir la rencontre. La publication est immédiate dès que vous appuyez sur Publier — il n’y a aucune étape de validation.',
  'expert.compose.chooseFixture': 'Choisir une rencontre',
  'expert.compose.filterHint': 'Filtrez par jour, compétition ou nom d’équipe.',
  'expert.compose.advancedPaste': 'Avancé\u00a0: coller un identifiant de match',
  'expert.compose.advancedPasteHint': 'Utile uniquement si vous avez déjà sous la main un identifiant de match interne ou un identifiant de rencontre d’un fournisseur. La liste ci-dessus est la voie normale.',
  'expert.compose.matchIdLabel': 'Identifiant de match',
  'expert.compose.matchIdPlaceholder': 'Identifiant de match interne ou identifiant de rencontre du fournisseur',
  'expert.compose.useThisId': 'Utiliser cet identifiant',
  'expert.compose.loadingFixture': 'Chargement de la rencontre…',
  'expert.compose.changeFixture': 'Changer de rencontre',
  'expert.compose.fixtureNotFound': 'Cette rencontre est introuvable. Choisissez-en une dans la liste à la place.',
  'expert.compose.fixtureLoadFailed': 'La rencontre n’a pas pu être chargée.',
  'expert.compose.fixtureNotOpened': 'Cette rencontre n’a pas pu être ouverte',
  'expert.compose.chooseFromList': 'Choisir dans la liste',
  'expert.compose.yourView': 'Votre avis',
  'expert.compose.percentNote': 'Saisissez des pourcentages, pas des décimales — tapez {typed} pour {whole}. Seuls les marchés que vous cochez sont publiés\u00a0; les autres restent indisponibles.',
  'expert.compose.fixThenPreview': 'Corrigez les champs signalés ci-dessus, puis affichez l’aperçu.',
  /** Indicative, never a conditional: publishing DOES make this public, right now. */
  'expert.compose.publishImmediate': 'Publier rend ceci public immédiatement.',
  'expert.compose.kickoffPassed': 'Le coup d’envoi a eu lieu le {time}. Un pronostic publié maintenant est signalé aux lecteurs comme publié après le coup d’envoi et n’est pas comptabilisé dans votre bilan mesuré.',
  'expert.compose.kickoffPassedNoTime': 'Ce match a commencé. Un pronostic publié maintenant est signalé aux lecteurs comme publié après le coup d’envoi et n’est pas comptabilisé dans votre bilan mesuré.',
  'expert.preview.kickedOff': 'Publié maintenant, ce pronostic sera signalé comme publié après le coup d’envoi et ne sera pas comptabilisé.',
  'expert.compose.publishFailed': 'Le pronostic n’a pas pu être publié.',
  'expert.compose.advancedIds': 'Avancé\u00a0: identifiants de la rencontre',
  'expert.compose.internalMatchId': 'Identifiant de match interne\u00a0:',
  'expert.compose.providerId': '{provider}\u00a0:',

  /*
   * ─── l’éditeur des marchés, ses champs et ses contrôles ────────────────────────────────
   *
   * NOT REVIEWED. The choices a reviewer is most likely to revisit:
   *
   *  1. « {team} gagne » for "{team} win", rather than « Victoire de {team} »: French elides
   *     « de » before a vowel (« d’Arsenal », « d’Aston Villa ») and a club name is data, so a
   *     fixed « de » would be wrong for every club whose name starts with one.
   *  2. « Les deux options » for "The two sides" of a two-way market, and « Les options plus et
   *     moins » for "Over and under": the English subjects are short nouns French has no exact
   *     equivalent for, and each rule is a whole sentence so the verb agrees with its subject.
   *  3. The character count. « {count} sur {max} caractères » would agree « caractères » with
   *     {max}, read wrong at one, and no plural branch is available to this area (see
   *     ./expert.en.ts); so both counting sentences put the figures after a colon and attach no
   *     noun to them, exactly as `expert.picker.showing` does. Rendered at 0, 1, 2 and 11 in
   *     frontend/e2e/mocked/expert-localisation.spec.ts.
   *  4. `expert.editor.marketLocked` keeps the English claim exactly — that removing a published
   *     market needs the prediction deleted — although composer.ts now withdraws one with null.
   *     Whether the sentence is still true is a copy question for the owner, not a translation.
   */
  'expert.editor.matchResultIntro': 'Vos propres pourcentages pour les trois issues. Chaque pronostic publie ce marché.',
  'expert.editor.teamWin': '{team} gagne',
  'expert.editor.ruleOutcomes': 'Les trois issues doivent totaliser {hundred}.',
  'expert.editor.ruleSides': 'Les deux options doivent totaliser {hundred}.',
  'expert.editor.ruleOverUnder': 'Les options plus et moins doivent totaliser {hundred}.',
  'expert.editor.totalBalanced': '{percent} au total.',
  'expert.editor.totalUnbalanced': '{percent} au total — {rule}',
  'expert.editor.adjustAdd': 'Ajoutez {points}.',
  'expert.editor.adjustRemove': 'Retirez {points}.',
  'expert.editor.convictionLabel': 'Votre conviction sur ce pronostic',
  'expert.editor.convictionHint': 'La force avec laquelle vous défendez cet avis. Laissé vide, aucune conviction n’est publiée — elle n’est jamais déduite de la taille de vos pourcentages, et ce n’est pas une exactitude.',
  'expert.editor.otherMarkets': 'Autres marchés',
  'expert.editor.otherMarketsIntro': 'Ne cochez que les marchés sur lesquels vous voulez publier un avis. Les autres restent indisponibles.',
  'expert.editor.marketLocked': 'Déjà publié. Vous pouvez modifier les chiffres ici\u00a0; retirer ce marché nécessite de supprimer le pronostic.',
  'expert.editor.marketOn': 'Les deux options sont publiées, et elles doivent totaliser {hundred}.',
  'expert.editor.marketOff': 'Non coché, ce marché n’est pas publié et les lecteurs le voient comme indisponible.',
  'expert.editor.overUnderGoals': 'Plus / moins de {line} buts',
  'expert.editor.bttsYes': 'Oui, les deux équipes marquent',
  'expert.editor.bttsNo': 'Au moins une ne marque pas',
  'expert.editor.bttsConviction': 'Conviction pour ce marché',
  'expert.editor.overGoals': 'Plus de {line} buts',
  'expert.editor.underGoals': 'Moins de {line} buts',
  'expert.editor.totalsConviction': 'Conviction pour les lignes de buts',
  'expert.editor.totalsConvictionHint': 'Une seule valeur couvre les deux lignes — c’est ce que l’API enregistre.',
  'expert.editor.reasoningLabel': 'Votre raisonnement',
  'expert.editor.reasoningPlaceholder': 'Ce qui vous a mené à ces chiffres — nouvelles des équipes, forme récente, confrontation.',
  'expert.editor.reasoningCount': 'Caractères\u00a0: {count} sur {max}. Publié avec votre pronostic pour que les lecteurs puissent le prendre en compte.',
  'expert.field.optional': '(facultatif)',

  'expert.validation.notANumber': 'Saisissez un nombre, par exemple {example}.',
  'expert.validation.outOfRange': 'Saisissez un pourcentage entre {min} et {max}.',
  'expert.validation.chooseFixture': 'Choisissez la rencontre concernée par ce pronostic.',
  'expert.validation.homeBlank': 'Saisissez un pourcentage pour la victoire à domicile.',
  'expert.validation.drawBlank': 'Saisissez un pourcentage pour le match nul.',
  'expert.validation.awayBlank': 'Saisissez un pourcentage pour la victoire à l’extérieur.',
  'expert.validation.marketBlank': 'Saisissez un pourcentage, ou décochez ce marché.',
  'expert.validation.lineBlank': 'Saisissez un pourcentage, ou décochez cette ligne.',
  'expert.validation.reasoningTooLong': 'Texte trop long (caractères\u00a0: {count}, maximum\u00a0: {max}). Raccourcissez-le.',

  // ─── l’aperçu avant publication ─────────────────────────────────────────────────────────
  'expert.preview.regionLabel': 'Aperçu de ce qui sera publié',
  'expert.preview.intro': 'Voici ce que verront les lecteurs. La publication le place immédiatement sur la page publique du match.',
  'expert.preview.convictionStated': 'Votre conviction déclarée\u00a0: {value}.',
  'expert.preview.noConviction': 'Aucune conviction publiée — les lecteurs sont informés qu’aucune n’a été donnée, et aucune n’est déduite de vos pourcentages.',
  'expert.preview.notPublished': '{market} — non publié. Les lecteurs voient ce marché comme indisponible, jamais comme {zero}.',
  'expert.preview.needsAttention': 'Certains champs demandent encore votre attention. Les problèmes sont signalés sur le formulaire ci-dessus.',

  // ─── ce que l’on sait déjà ──────────────────────────────────────────────────────────────
  'expert.evidence.regionLabel': 'Ce que l’on sait déjà de cette rencontre',
  'expert.evidence.heading': 'Ce que l’on sait déjà',
  'expert.evidence.intro': 'Les mêmes éléments que la page publique du match. Ils sont là pour être lus, pas copiés — aucun de vos champs n’en est rempli.',
  'expert.evidence.home': 'Domicile',
  'expert.evidence.away': 'Extérieur',
  'expert.evidence.kickoff': 'Coup d’envoi',
  /** « Stade » rather than « Lieu »: the provider's venue is always a ground. */
  'expert.evidence.venue': 'Stade',
  /** « Journée » is the French for a competition's round. */
  'expert.evidence.round': 'Journée',
  'expert.evidence.confidencePublished': 'Confiance de {percent}, publiée par la source',
  'expert.evidence.nothingForResult': 'Cette source n’a rien publié pour le résultat du match.',
  'expert.evidence.modelMarketsHeld': 'Marchés du modèle détenus\u00a0: {markets}.',
  'expert.evidence.notSuppliedByModel': 'Non fournis par le modèle\u00a0: {markets}. Ils restent indisponibles sauf si vous publiez un avis dessus.',

  'expert.published.title': 'Publié',
  'expert.published.body': 'Votre pronostic est maintenant sur la page publique du match. Rien n’attend de validation — les experts publient directement. Vous pouvez le modifier ou le supprimer à tout moment depuis Mes pronostics.',
  'expert.published.viewMatch': 'Voir la page du match',
  'expert.published.writeAnother': 'En rédiger un autre',

  // ─── my predictions ─────────────────────────────────────────────────────────────────────
  'expert.mine.title': 'Mes pronostics',
  'expert.mine.intro': 'Consultez et gérez tous vos pronostics d’expert',
  'expert.mine.loading': 'Chargement des pronostics...',
  'expert.mine.loadFailed': 'Échec du chargement des pronostics',
  'expert.mine.updateFailed': 'Échec de la mise à jour du pronostic',
  'expert.mine.confirmDelete': 'Voulez-vous vraiment supprimer ce pronostic\u00a0? Cette action est irréversible.',
  'expert.mine.filterByStatus': 'Filtrer par statut\u00a0:',
  'expert.mine.listHeading': 'Vos pronostics ({count})',
  'expert.mine.listHeadingUncounted': 'Vos pronostics',
  'expert.mine.emptyTitle': 'Aucun pronostic trouvé',
  'expert.mine.emptyNone': 'Vous n’avez encore créé aucun pronostic.',
  'expert.mine.emptyFiltered': 'Aucun pronostic avec le statut «\u00a0{status}\u00a0».',
  'expert.mine.createFirst': 'Rédiger votre premier pronostic',
  'expert.mine.emptyPageTitle': 'Cette page est vide',
  'expert.mine.emptyPageBody': 'Plus rien n’est listé sur cette page\u00a0: la liste a raccourci depuis son ouverture. Revenez à la page précédente.',
  'expert.mine.matchIdLabel': 'Identifiant du match\u00a0:',
  'expert.mine.created': 'Créé\u00a0: {timestamp}',
  'expert.mine.published': 'Publié\u00a0: {timestamp}',
  'expert.mine.editNote': 'Des pourcentages, pas des décimales — tapez {typed} pour {whole}. Enregistrer garde ce pronostic publié et conserve la version que vous remplacez, afin que les lecteurs puissent encore voir l’avis que vous aviez publié avant.',
  'expert.mine.fixThenSave': 'Corrigez les champs signalés ci-dessus, puis enregistrez.',
  'expert.edit.afterKickoff': 'Ce match a commencé. Les lecteurs verront votre modification, mais elle ne change rien à ce qui est comptabilisé\u00a0: seule la version en place au coup d’envoi peut compter dans votre bilan mesuré.',
  'expert.mine.matchOutcome': 'Issue du match',
  'expert.mine.homeWin': 'Victoire à domicile',
  'expert.mine.draw': 'Match nul',
  'expert.mine.awayWin': 'Victoire à l’extérieur',
  'expert.mine.bttsLong': 'Les deux équipes marquent (BTTS)',
  'expert.mine.marketConfidence': 'confiance\u00a0: {value}',
  'expert.mine.yes': 'Oui',
  'expert.mine.no': 'Non',
  'expert.mine.totalGoals': 'Total de buts',
  'expert.mine.superseded': 'Ce pronostic a été remplacé par une version plus récente',

  // ─── the moderation list ────────────────────────────────────────────────────────────────
  'expert.queue.title': 'File de modération',
  'expert.queue.intro': 'Pronostics signalés à l’attention d’un modérateur — après leur publication.',
  'expert.queue.loading': 'Chargement de la file de modération...',
  'expert.queue.loadFailed': 'Échec du chargement de la file de modération',
  'expert.queue.approveFailed': 'Échec de l’approbation du pronostic',
  'expert.queue.rejectFailed': 'Échec du rejet du pronostic',
  'expert.queue.withdrawPrompt': 'Indiquez la raison du retrait de ce pronostic (facultatif)\u00a0:',
  'expert.queue.noticeTitle': 'La publication n’attend pas cette file.',
  'expert.queue.noticeBody': 'Les experts publient directement\u00a0: un pronostic est en ligne sur les pages publiques des matchs dès que son auteur le publie, qu’il apparaisse ici ou non. Approuver enregistre qu’un modérateur l’a vérifié\u00a0; rejeter retire un pronostic déjà public.',
  'expert.queue.heading': 'Signalés pour modération',
  'expert.queue.listHeading': 'Signalés pour modération ({count})',
  'expert.queue.listNote': 'Ils sont déjà visibles par les lecteurs. Rien ici n’attend l’autorisation d’être mis en ligne.',
  'expert.queue.emptyTitle': 'Rien en attente de modération',
  'expert.queue.emptyBody': 'Tous les pronostics signalés ont été traités. Les pronostics des experts sont publiés immédiatement dans tous les cas, donc une file vide ne retient rien.',
  'expert.queue.createdByAt': 'Créé par\u00a0: {who} • {timestamp}',
  'expert.queue.markChecked': 'Marquer comme vérifié',
  'expert.queue.markCheckedHint': 'Enregistre qu’un modérateur a vérifié ce pronostic. Il est déjà public.',
  'expert.queue.withdraw': 'Retirer',
  'expert.queue.withdrawHint': 'Retire un pronostic déjà visible par les lecteurs.',
}

export default expert
