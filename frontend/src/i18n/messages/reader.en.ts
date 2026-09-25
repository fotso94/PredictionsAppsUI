/**
 * English — the READER area: the competition list and one competition, a team, the personal
 * dashboard, and the three panels on a match page that carry provenance, revisions and evidence.
 *
 * EVERY VALUE HERE IS THE STRING THOSE SCREENS ALREADY SHIPPED, character for character, with
 * five exceptions, each recorded at the key itself:
 *   - `reader.team.recentNote`, which asserted that nothing on this installation has been scored.
 *     That was true when it was written and is false now (model forecasts are settled), so it was
 *     a claim about the data frozen into a constant. It now says what stays true whatever the
 *     settlement state is, in the same words core.en.ts already uses for the matchday list.
 *   - `reader.leagues.loadFailed`, which named API-Football as the source of a failure on a read
 *     that goes to our own backend and, through it, to whichever fixture provider is active
 *     (Live Score today). A provider name in a generic failure is a fact about the data written
 *     down as a constant.
 *   - the standings column names, which had no accessible full form at all. The abbreviation is
 *     unchanged in English; the full name beside it is new, and is the only thing that makes the
 *     FRENCH abbreviations readable — French "P" is Perdus (lost) where English "P" is Played.
 *   - `reader.dashboard.welcomeNoName`, which shipped as "Welcome back, there!" — the word
 *     "there" standing in for a name French has no equivalent of. The nameless greeting is now
 *     its own whole sentence in both languages. The reasoning is at the key; the count above was
 *     three when this file was written and this is the fourth.
 *   - `reader.follow.team.count` / `reader.follow.league.count`, whose two numerals were two
 *     `<span>`s glued either side of the word "of" in FollowButton.tsx. The English reads the
 *     same; what changed is that the catalogue now owns where in the line the figures go, which
 *     is the only way French could put them anywhere else. That is the fifth.
 *
 * WHAT MUST NEVER BE PUT IN A CATALOGUE, and is not: a team, competition, venue or person's name;
 * a provider's or the backend's own message; or a number. The backend's prose reaches these
 * screens through `{reason}`, `{detail}` and `{type}` holes and is rendered exactly as it
 * arrived — see 4C in the package brief and `brief-accuracy` / `dashboard-no-record` below.
 *
 * ── WHY NOTHING IN THIS AREA USES `{count, plural, …}` ──────────────────────────────────────
 *
 * It is not that nothing here counts. It is that the table which proves a French plural renders
 * correctly at 0, 1, 2 and 11 — COUNT_CASES in frontend/e2e/mocked/localisation.spec.ts — and the
 * guard that fails when a plural is missing from it both live in a spec this package does not
 * own. A plural added here would fail that guard in another owner's file, and the way to make it
 * pass would be to edit their file.
 *
 * So every count on these screens is a NUMERAL IN AN ELEMENT OF ITS OWN beside a label that does
 * not inflect, which is the same compromise MeasuredRecord.tsx already makes and which
 * localisation.spec.ts already pins there. The French was chosen to be invariable on purpose —
 * « en favoris » rather than « enregistré(s) », « fois » which does not inflect — rather than
 * frozen at one number and hoped over. `reader-localisation.spec.ts` renders every one of them at
 * 0, 1, 2 and 11 and fails if one changes with the count or fakes agreement with "(s)".
 * This is recorded as outstanding work, not as a design: see the package report.
 *
 * The follow control's two count lines, added later, hit the same wall and take the same way
 * round it — a French CATEGORY LABEL (« Compétitions suivies »), which is plural whatever the
 * figure beside it is, rather than a counted noun phrase that would have to inflect. The full
 * reasoning is at `reader.follow.league.count`.
 *
 * DATES AND TIMES ARE NOT STRINGS YOU BUILD. Every timestamp on these screens goes through
 * `backendInstant` and then `formatDate` / `formatDateTime` in ../index.ts, so it is read as the
 * UTC the server wrote and shown in the zone the READER chose. None of them is shown in UTC; the
 * reasoning for each is at its call site.
 */

const reader = {
  // ─── shared by more than one reader screen ──────────────────────────────────────────────
  /** The same sentence on the competition page and the team page. One key, so they cannot drift. */
  'reader.saveStateUnknown': 'We could not load your saved matches, so the save control cannot show which of these you have already saved.',
  'reader.upcomingMatches': 'Upcoming matches',
  'reader.backToHome': 'Back to Home',

  // ─── the follow control ─────────────────────────────────────────────────────────────────
  /**
   * FollowButton.tsx, which is on one competition, on one team and on every row of the follow
   * list — so one English word left here was English on three screens at once.
   *
   * EVERY VALUE BELOW IS THE STRING THAT COMPONENT ALREADY RENDERED, character for character.
   * Nothing was reworded on the way into the catalogue; the only thing that changed is that a
   * language other than English can now say it. The one shape that had to change is the count
   * line, and that is recorded at its own key.
   *
   * WHY THERE ARE SEPARATE `team.` AND `league.` KEYS FOR THREE OF THEM. English inflects
   * nothing here, so one key would have done for English. French does: « équipe » and
   * « compétition » are different nouns, and a participle beside either has to agree with it.
   * Splitting the key is what lets the French catalogue write the agreement out instead of
   * gluing a translated noun onto an English frame — and `the follow control agrees with the
   * noun it is beside, in both languages` in frontend/e2e/mocked/reader-localisation.spec.ts
   * renders BOTH on a real page so the claim is checked rather than asserted in this comment.
   *
   * THE HALF NOBODY LOOKS AT IS HERE TOO. `reader.follow.namedFollow`, `namedSignIn` and
   * `namedFollowing` are the control's accessible name and its title — what a screen reader
   * actually announces, which was English on a French page with nothing on screen to show it —
   * and `reader.follow.confirmed` / `confirmedOff` are the `role="status"` line that is read out
   * after a write. A button whose visible word is French and whose announced name is English is
   * worse than one that is honestly English throughout.
   */
  'reader.follow.follow': 'Follow',
  'reader.follow.signIn': 'Sign in to follow',
  /** The word for the followed state. Split by kind for the French agreement; see above. */
  'reader.follow.team.following': 'Following',
  'reader.follow.league.following': 'Following',
  /** The accessible name and the title, which carry the entity's own name. */
  'reader.follow.namedFollow': 'Follow {name}',
  'reader.follow.namedSignIn': 'Sign in to follow {name}',
  'reader.follow.namedFollowing': 'Following {name}. Select to stop following.',
  /** Said when a signed-out reader presses the control, before they are sent to sign in. */
  'reader.follow.team.signInToast': 'Sign in to follow teams.',
  'reader.follow.league.signInToast': 'Sign in to follow competitions.',
  /** The outcome of a write, announced once through `role="status"`. */
  'reader.follow.confirmed': 'Following {name}.',
  'reader.follow.confirmedOff': 'No longer following {name}.',
  /**
   * The fallback when the refusal carried no sentence of its own. A refusal that DOES carry one
   * — the follow limit, most often — is still shown exactly as the server wrote it.
   */
  'reader.follow.failed': '{name} could not be followed. Nothing was changed.',
  'reader.follow.failedOff': '{name} could not be unfollowed. Nothing was changed.',
  'reader.follow.unknown': 'We could not load what you follow, so this button cannot show whether {name} is already on your list.',
  /**
   * THE COUNT AGAINST THE LIMIT, AND THE ONE PLACE THIS CONTROL'S WORDING HAD TO MOVE.
   *
   * The English is the sentence that shipped, with the two numerals now holes rather than two
   * `<span>`s glued either side of the word "of" — which is the same fix DashboardPage.tsx made
   * for its own counts, and for the same reason: an assembled line freezes English word order
   * and leaves a language that puts the figures elsewhere nothing to say.
   *
   * THE FRENCH IS A LABEL AND A RATIO, NOT A COUNTED NOUN PHRASE, AND THAT IS A CONSTRAINT
   * RATHER THAN A PREFERENCE. « 1 compétition suivie sur 5 » / « 2 compétitions suivies sur 5 »
   * is the natural French and needs `{count, plural, …}`: French takes the singular at 0 AND 1,
   * and « suivie » agrees with the noun. That plural cannot be written here. `every message with
   * a plural is in the table above` in frontend/e2e/mocked/localisation.spec.ts fails for any
   * catalogue entry that counts and is not listed in COUNT_CASES, and that file belongs to
   * another package — see the header of this file, where the same wall stopped the dashboard's
   * counts. So the French says « Compétitions suivies : 1 sur 5 »: a category label, which is
   * plural in French whatever the figure beside it is, and a ratio that carries no agreement at
   * all. It is correct at every count rather than correct at the count somebody tested.
   *
   * This is recorded as outstanding work, not as a design. The moment COUNT_CASES can take a
   * reader entry, these two become plurals and read as French normally would.
   */
  'reader.follow.team.count': '{count, number} of {limit, number} teams followed',
  'reader.follow.league.count': '{count, number} of {limit, number} competitions followed',

  // ─── the competition list ───────────────────────────────────────────────────────────────
  'reader.leagues.documentTitle': 'Leagues - Soccer Predictions',
  'reader.leagues.documentDescription': 'Browse all available soccer leagues and competitions with predictions and analysis.',
  'reader.leagues.heading': 'Leagues',
  'reader.leagues.subheading': 'Browse all available leagues and competitions',
  'reader.leagues.loading': 'Loading leagues...',
  /**
   * The fallback when the failure carried no message of its own.
   *
   * It used to read "Failed to fetch leagues from API-Football". This read goes to our own
   * backend, which serves it from stored rows and, when it does reach a provider, reaches
   * whichever one is active — Live Score at the time of writing, with API-Football retained only
   * as a fallback. Naming one provider in a generic client-side failure told the reader something
   * about the data that was not true, so the sentence no longer names one. Where the failure DOES
   * carry a message, that message is still what is shown.
   */
  'reader.leagues.loadFailed': 'The competitions could not be loaded.',
  'reader.leagues.emptyTitle': 'No leagues available. This might be a data issue.',
  'reader.leagues.emptyHint': 'Check browser console for details.',

  // ─── one competition ────────────────────────────────────────────────────────────────────
  /**
   * `{app}` rather than the product's name written out, and that is not a nicety.
   *
   * A title of the form "<name> - <product>" has nothing in it to translate: both holes are
   * names. Written out, the two catalogues would hold the identical string, which is
   * indistinguishable from a translation nobody did — and `the two catalogues hold the same keys,
   * and no French entry is still its English` in localisation.spec.ts fails on exactly that,
   * rightly, because that is the shape a missed key hides in. Interpolating `app.name` leaves the
   * catalogue in charge of the ORDER, which is the only thing here a language could differ on,
   * and leaves nothing in it that could be left untranslated.
   */
  'reader.league.documentTitle': '{league} - {app}',
  'reader.league.documentDescription': '{league} standings, fixtures and published forecasts for the {season} season.',
  'reader.league.loading': 'Loading league details...',
  'reader.league.notFoundHeading': 'League Not Found',
  'reader.league.notFoundBody': 'The requested league could not be found.',
  'reader.league.partialStandings': 'The standings table could not be loaded, so it is not shown.',
  'reader.league.partialFixtures': 'The fixture list could not be loaded, so it is not shown.',
  'reader.league.loadFailedTitle': 'This competition could not be loaded.',
  'reader.league.tryAgain': 'Try again',
  'reader.league.noFixturesTitle': 'No upcoming fixtures are stored for this competition.',
  'reader.league.noFixturesBody': 'Nothing is scheduled in the next two weeks in the data we hold.',
  'reader.league.standings': 'Standings',
  'reader.league.teams': 'Teams',
  'reader.league.nothingTitle': 'No teams or fixtures are stored for this competition.',
  'reader.league.nothingBody': 'Nothing has been loaded for it yet.',

  /**
   * The standings columns: the abbreviation that is drawn, and the full name a screen reader is
   * given for it.
   *
   * The English abbreviations are exactly what shipped. The full names are new, and they are not
   * decoration: the French abbreviations are a different set of letters for a different set of
   * words, and "P" means Played in one language and Perdus — lost — in the other. A column of
   * numbers under a single letter nobody can expand is unreadable in either.
   */
  'reader.standings.position': '#',
  'reader.standings.positionFull': 'Position',
  'reader.standings.team': 'Team',
  'reader.standings.teamFull': 'Team',
  'reader.standings.played': 'P',
  'reader.standings.playedFull': 'Played',
  'reader.standings.won': 'W',
  'reader.standings.wonFull': 'Won',
  'reader.standings.drawn': 'D',
  'reader.standings.drawnFull': 'Drawn',
  'reader.standings.lost': 'L',
  'reader.standings.lostFull': 'Lost',
  'reader.standings.goalsFor': 'GF',
  'reader.standings.goalsForFull': 'Goals for',
  'reader.standings.goalsAgainst': 'GA',
  'reader.standings.goalsAgainstFull': 'Goals against',
  'reader.standings.goalDifference': 'GD',
  'reader.standings.goalDifferenceFull': 'Goal difference',

  // ─── one team ───────────────────────────────────────────────────────────────────────────
  /** Same shape, same reason, as `reader.league.documentTitle` above. */
  'reader.team.documentTitle': '{team} - {app}',
  'reader.team.loadFailedTitle': 'This team could not be loaded.',
  'reader.team.notFoundTitle': 'Team not found.',
  'reader.team.notFoundBody': 'There is no team with that identifier in the data we hold.',
  'reader.team.goHome': 'Go to Home',
  'reader.team.recentMatches': 'Recent matches',
  'reader.team.noUpcomingTitle': 'No upcoming matches are stored for this team.',
  'reader.team.noUpcomingBody': 'Nothing is scheduled for them in the competitions this site covers.',
  'reader.team.noRecentTitle': 'No results are recorded for this team yet.',
  'reader.team.noRecentBody': 'Nothing they have played is stored here.',
  /**
   * THIS SENTENCE WAS FALSE AND IS THE ONE COPY CHANGE IN THIS FILE THAT MATTERS.
   *
   * It ended: "Nothing on this site has been scored against a result yet, so no forecast here is
   * marked right or wrong." Settlement exists on this installation and model forecasts have been
   * scored, so the page was telling a reader the opposite of what the home page's measured record
   * tells them — the exact failure DashboardPage.tsx already records having fixed in its own
   * footnote ("a sentence that goes stale silently is worse than no sentence").
   *
   * What replaces it claims only what stays true however much has been settled, and says it in
   * the words core.en.ts already uses for the same fact on the matchday list, so the two cannot
   * drift apart.
   */
  'reader.team.recentNote': 'Final scores, with what each source published beforehand. Whether a prediction for one of them has been scored against its result is stated on that match\'s own page; this list claims no accuracy either way.',

  // ─── the personal dashboard ─────────────────────────────────────────────────────────────
  'reader.dashboard.documentTitle': 'My matches - Soccer Predictions',
  'reader.dashboard.documentDescription': 'The matches you saved and the teams and competitions you follow.',
  'reader.dashboard.welcome': 'Welcome back, {name}!',
  /**
   * The greeting when the account carries no name, no username and no address.
   *
   * It shipped as "Welcome back, there!" — the string "there" standing in for a name. French has
   * no word that does that job, and « Bon retour, vous ! » is not a sentence anyone says; the
   * natural form drops the address entirely. So the nameless case is its own whole sentence in
   * both languages rather than a hole filled with a placeholder word, which also reads better in
   * English. This is a deliberate copy change and is in the package report.
   */
  'reader.dashboard.welcomeNoName': 'Welcome back!',
  'reader.dashboard.signedInAs': 'Signed in as {email}',
  /** `{type}` is the backend's own word for the account type, rendered as it sent it. */
  'reader.dashboard.accountKind': ' · {type} account',
  'reader.dashboard.feedHeading': 'Your feed',
  'reader.dashboard.feedHint': 'What you saved and what the teams and competitions you follow are playing — in play first, then results, then what is coming up.',
  /** A count with a label that does not inflect in either language. See the header. */
  'reader.dashboard.savedCount': '{count} saved',
  'reader.dashboard.liveCount': '{count} in play now',
  'reader.dashboard.followingHeading': 'Teams and competitions you follow',
  'reader.dashboard.followingHint': 'Their fixtures appear in the feed above. Following changes what you see here; it does not change what any source publishes.',
  'reader.dashboard.controlsHeading': 'Your settings and your data',
  'reader.dashboard.controlsHint': 'What these pages are allowed to show you, how to take a copy of your data, and how to delete it.',
  'reader.dashboard.recordHeading': 'Your prediction record',
  'reader.dashboard.recordBody1': 'Your own predictions are not settled against final results into a personal record, so no accuracy rate, streak or profit figure is shown for your account. Saving a match records that you want to come back to it; it is not a wager and nothing about it is scored.',
  'reader.dashboard.recordBody2': 'How the model providers and the experts have actually done, counted from settled results, is published on the home page with the sample size behind every figure.',
  'reader.dashboard.browsePredictions': 'Browse today’s predictions',
  'reader.dashboard.browseFixtures': 'Browse the fixtures',
  'reader.dashboard.accountSettings': 'Account settings',
  'reader.dashboard.coverageHeading': 'What this site currently holds',
  'reader.dashboard.coverageHint': 'Site-wide counts measured from stored data — not your personal statistics.',
  /** The accessible name of the placeholder that stands where a figure will be. */
  'reader.dashboard.loadingFigure': 'Loading',
  'reader.dashboard.coverageFailed': 'The coverage endpoint could not be reached, so these counts are unavailable.',
  /** `{reason}` is the backend's own sentence for why no rate is published. Verbatim. */
  'reader.dashboard.noAccuracy': 'No accuracy figure is shown: {reason}',

  // ─── forecast provenance, on a match page ───────────────────────────────────────────────
  'reader.anomalies.warning': 'These numbers do not add up as they should. The forecast is shown exactly as the provider published it, and nothing has been adjusted to make it fit.',
  'reader.provenance.modelRun': 'Provider’s model run',
  'reader.provenance.providerUpdated': 'Provider last updated',
  'reader.provenance.retrieved': 'Retrieved by this site',
  'reader.provenance.fixtureMatch': 'Fixture match',
  'reader.provenance.generationUnknown': 'generation time unknown (not published by the provider)',
  'reader.provenance.notReported': 'not reported',
  'reader.provenance.notRecorded': 'not recorded',
  /**
   * Said only when it is true of one of the three timestamps above. This backend serialises these
   * three with an explicit Z (`iso_utc` in backend/app/schemas/matches.py:22), so it should not
   * appear — but `backendInstant` reports what the payload actually said rather than what the
   * backend is believed to do, and a silently shifted timestamp is exactly the defect that reached
   * a reader's Member Since date.
   */
  'reader.provenance.unzoned': 'One of these times arrived without a time zone and is read as UTC.',

  // ─── an expert's earlier published versions ─────────────────────────────────────────────
  'reader.revisions.heading': 'Earlier published versions',
  /**
   * Four whole sentences rather than one sentence assembled from pieces: the count and the
   * timestamp each split it in two, and a language that puts either somewhere else has to be able
   * to say so. French « fois » does not inflect, which is why the count does not need a plural.
   */
  'reader.revisions.summaryOnce': 'This view was updated once. Each earlier version is kept exactly as it was published; a correction is added to the record rather than replacing it.',
  'reader.revisions.summaryOnceWhen': 'This view was updated once, most recently on {when}. Each earlier version is kept exactly as it was published; a correction is added to the record rather than replacing it.',
  'reader.revisions.summaryMany': 'This view was updated {count} times. Each earlier version is kept exactly as it was published; a correction is added to the record rather than replacing it.',
  'reader.revisions.summaryManyWhen': 'This view was updated {count} times, most recently on {when}. Each earlier version is kept exactly as it was published; a correction is added to the record rather than replacing it.',
  'reader.revisions.version': 'Version {number}',
  'reader.revisions.asFirstPublished': ' · as first published',
  'reader.revisions.replaced': 'replaced {when}',
  'reader.revisions.editedAfterKickoff': 'edited after kick-off',
  'reader.revisions.whatChanged': 'What changed: ',
  /** The four figures an earlier version carried. Short column labels, not sentences. */
  'reader.revisions.home': 'Home',
  'reader.revisions.draw': 'Draw',
  'reader.revisions.away': 'Away',
  'reader.revisions.confidence': 'Confidence',

  // ─── the evidence panel, on a match page ────────────────────────────────────────────────
  'reader.brief.heading': 'What this page knows about the match',
  'reader.brief.marketsNotListed': 'Published for this fixture; the markets covered were not listed.',
  'reader.brief.noModelForecast': 'No model forecast has been retrieved for this fixture.',
  'reader.brief.expertsAwait': 'Experts publish directly, so one appears here as soon as it is published.',
  /** `{confidence}` is the backend's own word for how the fixture was linked. Verbatim. */
  'reader.brief.fixtureLink': 'fixture link: {confidence}',
  /** Only ever rendered above one, so the French agrees in the plural and needs no branch. */
  'reader.brief.expertsPublished': '{count} experts published',
  'reader.brief.published': 'published {when}',
  'reader.brief.allMarkets': 'Both sources published every market they offer for this fixture.',

  // ───────────────────────────────────────────────────────────────── selections and slips
  // Markets on a match page, the selection dock, suggested combinations and the reader's own
  // slips. Every probability shown is the provider's published figure or arithmetic on it; a
  // price appears only where one was actually given. Nothing here is advice, and nothing here
  // places a bet.
  'selections.nav': 'Selections',
  'selections.panel.title': 'Markets on this fixture',
  'selections.panel.intro': 'Every selection the model forecast supports, with its published probability. Add one to your slip to compare it with selections from other fixtures.',
  'selections.panel.noForecast': 'No model forecast is stored for this fixture, so there are no markets to choose from.',
  'selections.panel.builtFrom': 'Read from the {provider} forecast retrieved {retrieved}; model run {modelRun}.',
  'selections.panel.modelRunUnknown': 'not stated',
  'selections.panel.snapshot': 'forecast snapshot {id}',
  'selections.panel.state.stale': 'This forecast is out of date ({reason}); its probabilities are shown for reference.',
  'selections.panel.state.kickoffPassed': 'This fixture has kicked off. Its markets are shown for reference and cannot be added to a slip.',
  'selections.panel.unavailable': 'Not published: {reason}',
  'selections.panel.calculated': 'Calculated from provider probabilities: {formula}',
  'selections.panel.probability': 'Published probability',
  'selections.panel.priceProvider': 'Provider price {price}, captured {when} (bookmaker not named)',
  'selections.panel.noPrice': 'No price available for this selection',
  'selections.panel.settles': 'Settles: {rule}',
  'selections.panel.notTracked': 'Cannot be tracked automatically: {reason}',
  'selections.panel.remainder': 'Other scorelines: {value} (the provider’s remainder; not a selection)',
  'selections.panel.recommended': 'Markets the provider flagged in its own payload',
  'selections.panel.recommendedUnresolved': '{raw}: not offered ({reason})',
  'selections.panel.recommendedNote': 'Listed as the provider published them, mapped to the selections above. They are the provider’s flags, not this site’s suggestions.',
  'selections.panel.missing': 'Not offered here',
  'selections.panel.missingIntro': 'Market families no configured source publishes. They are not derived from other statistics.',
  'selections.action.add': 'Add to slip',
  'selections.action.added': 'On slip',
  'selections.action.replace': 'Replace selection on this fixture',
  'selections.action.remove': 'Remove',
  'selections.action.addAll': 'Add all to slip',
  'selections.action.copy': 'Copy slip',
  'selections.action.copied': 'Copied',
  'selections.action.save': 'Save',
  'selections.action.saveNamed': 'Save as…',
  'selections.action.record': 'Record as placed',
  'selections.action.duplicate': 'Duplicate as draft',
  'selections.action.delete': 'Delete',
  'selections.action.clear': 'Clear slip',
  'selections.action.new': 'Start a new slip',
  'selections.action.open': 'Open',
  'selections.action.showSlip': 'Slip',
  'selections.action.hideSlip': 'Hide slip',
  'selections.dock.title': 'Your slip',
  'selections.dock.empty': 'Nothing on your slip yet. Open a fixture and add a selection.',
  'selections.dock.count': '{count, plural, one {# selection} other {# selections}}',
  'selections.dock.signedOut': 'Kept in this browser until you sign in; signing in moves it to your account.',
  'selections.dock.handoffRefused': '{count, plural, one {One selection from this browser could not be added to your account: {reasons}} other {# selections from this browser could not be added to your account: {reasons}}}',
  'selections.dock.started': 'Kicked off — no longer a prematch selection; remove it before saving.',
  'selections.dock.forecastChanged': 'The forecast has changed since you chose this ({current} now); your selection is unchanged.',
  'selections.dock.unavailableNow': 'This selection is no longer offered by the current forecast; your selection is unchanged.',
  'selections.dock.oneOnly': 'One selection per fixture. This fixture already has one on your slip.',
  'selections.dock.oddsLabel': 'Your bookmaker’s price',
  'selections.dock.oddsPlaceholder': 'e.g. 2.30',
  'selections.dock.combinedPrice': 'Combined price {price}',
  'selections.dock.combinedPriceMissing': 'No combined price: {count, plural, one {one selection has} other {# selections have}} no price. Enter the prices your bookmaker offers.',
  'selections.dock.combinedProbability': 'Combined chance ≈ {value}',
  'selections.dock.combinedProbabilityNote': 'The product of the published probabilities, assuming the matches are independent. An approximation, not a calibrated prediction.',
  'selections.dock.combinedProbabilityWithheld': 'No combined chance is shown: a draw-no-bet selection’s probability is conditional on there being no draw, and cannot be multiplied with the others. Each selection’s own probability stands.',
  'selections.dock.priceOriginal': 'Recorded price {price}',
  'selections.dock.priceEffective': 'Effective price {price} — a void selection has dropped out',
  'selections.dock.potentialWithheld': 'Adjusted return withheld: {reason}',
  'selections.dock.stakeLabel': 'Stake (optional)',
  'selections.dock.currencyLabel': 'Currency',
  'selections.dock.potential': 'Gross return {gross} · net profit {net}',
  'selections.dock.potentialNote': 'From the price given, rounded to the currency’s smallest unit. Not money held or promised here.',
  'selections.dock.nameLabel': 'Name this slip',
  'selections.dock.saveHint': 'Sign in to save this slip to your account.',
  'selections.dock.saved': 'Saved as “{name}”.',
  'selections.dock.recorded': 'Recorded as placed elsewhere. It is now kept as it was; duplicate it to change anything.',
  'selections.dock.recordHint': 'Record that you placed this with your own bookmaker. This site does not place bets, hold money or confirm that a bet exists.',
  'selections.dock.referenceLabel': 'Your reference (optional)',
  'selections.dock.priceLabel': 'Combined price your bookmaker gave (optional)',
  'selections.dock.error': 'That did not go through: {reason}',
  'selections.dock.disclaimer': 'Probabilities are the provider’s published forecasts, not offered prices. Nothing here is advice to place a bet.',
  'selections.history.title': 'My selections',
  'selections.history.intro': 'Drafts, saved combinations and bets you recorded as placed elsewhere, with what became of each selection once results were stored.',
  'selections.history.empty': 'No slips yet.',
  'selections.history.signedOut': 'Sign in to see the slips saved to your account.',
  'selections.history.loadFailed': 'Your slips could not be loaded: {reason}',
  'selections.history.filter.all': 'All',
  'selections.history.filter.draft': 'Drafts',
  'selections.history.filter.saved': 'Saved',
  'selections.history.filter.recorded': 'Recorded',
  'selections.history.untitled': 'Untitled slip',
  'selections.history.updated': 'updated {when}',
  'selections.history.recordedAt': 'recorded {when}',
  'selections.history.reference': 'ref. {reference}',
  'selections.history.counts': '{won} won · {lost} lost · {void} void · {unresolved} unresolved · {pending} pending',
  'selections.history.settlementRule': 'Rule: {rule}',
  'selections.history.settlementReason': '{reason}',
  'selections.history.actual': 'Result {actual}',
  'selections.history.awaiting': 'Awaiting a result',
  'selections.history.unresolvedNote': 'Not settled automatically: the data this market needs is not held. Nothing is guessed.',
  'selections.history.voidNote': 'Void selections drop out of the combination and its price.',
  'selections.suggest.title': 'Suggested combinations',
  'selections.suggest.intro': 'Built from stored forecasts only, by a fixed rule: one selection per fixture, the highest published probability among the markets you allow, ranked and cut into sets that share no fixture. Asking for suggestions costs no provider request.',
  'selections.suggest.legs': 'Legs',
  'selections.suggest.minProbability': 'Minimum published probability',
  'selections.suggest.maxProbability': 'Maximum (near-certainties left out)',
  'selections.suggest.markets': 'Markets',
  'selections.suggest.competitions': 'Competitions',
  'selections.suggest.anyCompetition': 'Any competition',
  'selections.suggest.window': 'Kickoff window',
  'selections.suggest.days': '{count, plural, one {next # day} other {next # days}}',
  'selections.suggest.oddsRange': 'Provider price between',
  'selections.suggest.oddsRangeNote': 'Only the match-result market carries a provider price, so a price range narrows to it.',
  'selections.suggest.includeStale': 'Include out-of-date forecasts',
  'selections.suggest.generate': 'Generate',
  'selections.suggest.generatedAt': 'Generated {when} from {qualifying} qualifying of {considered} fixtures in the window.',
  'selections.suggest.none': 'No combination qualifies: {reason}',
  'selections.suggest.shortfall': '{reason}',
  'selections.suggest.combination': 'Combination {index}',
  'selections.suggest.rank': 'rank {rank}',
  'selections.suggest.why': 'Published {probability} by {provider}; forecast {age} old ({state}).',
  'selections.suggest.whyAgeUnknown': 'Published {probability} by {provider}; forecast age not stated.',
  'selections.suggest.ageHours': '{count, plural, one {# hour} other {# hours}}',
  'selections.suggest.excluded': 'Left out: {stale} out of date, {noForecast} without a forecast, {belowThreshold} below the minimum, {aboveCeiling} above the maximum, {oddsFilter} outside the price range.',
  'selections.suggest.combinedOdds': 'Provider prices multiply to {price} (bookmaker not named).',
  'selections.suggest.noCombinedOdds': 'No combined price: not every leg carries a provider price.',
  'selections.suggest.loadFailed': 'Suggestions could not be generated: {reason}',
  'selections.suggest.warnings': 'Note: {message}',
  'selections.group.outcome': 'Match outcome',
  'selections.group.goals': 'Goals',
  'selections.group.firstHalf': 'First half',
  'selections.group.team': 'Team markets',
  'selections.group.exactScore': 'Exact score',
  'selections.market.matchResult': 'Match result',
  'selections.market.doubleChance': 'Double chance',
  'selections.market.drawNoBet': 'Draw no bet',
  'selections.market.totalGoals': 'Total goals {line}',
  'selections.market.teamGoals': '{team} goals {line}',
  'selections.market.bothTeamsScore': 'Both teams to score',
  'selections.market.firstHalfResult': 'First-half result',
  'selections.market.teamToScoreFirst': 'Team to score first',
  'selections.market.exactScore': 'Exact score',
  'selections.market.homeTeam': 'Home team',
  'selections.market.awayTeam': 'Away team',
  'selections.outcome.draw': 'Draw',
  'selections.outcome.orDraw': '{team} or draw',
  'selections.outcome.either': '{home} or {away}',
  'selections.outcome.drawNoBet': '{team} (stake returned on a draw)',
  'selections.outcome.over': 'Over {line}',
  'selections.outcome.under': 'Under {line}',
  'selections.outcome.yes': 'Yes',
  'selections.outcome.no': 'No',
  'selections.outcome.neither': 'No goal',
  'selections.period.regulation': '90 minutes',
  'selections.period.firstHalf': '1st half',
  'selections.state.pending': 'Pending',
  'selections.state.won': 'Won',
  'selections.state.lost': 'Lost',
  'selections.state.void': 'Void',
  'selections.state.unresolved': 'Unresolved',
  'selections.state.draft': 'Draft',
  'selections.status.draft': 'Draft',
  'selections.status.saved': 'Saved',
  'selections.status.recorded': 'Recorded as placed',
  'selections.copy.untitled': 'Slip',
  'selections.copy.count': '{count, plural, one {# selection} other {# selections}}',
  'selections.copy.probability': 'published probability {value}',
  'selections.copy.noProbability': 'no published probability',
  'selections.copy.priceUser': 'your price',
  'selections.copy.priceProvider': 'provider price',
  'selections.copy.combinedPrice': 'Combined price: {price} (product of the legs’ prices)',
  'selections.copy.noCombinedPrice': 'Combined price: not available — not every selection has a price',
  'selections.copy.stake': 'Stake: {stake} {currency}',
  'selections.copy.potential': 'Gross return {gross} {currency} · net profit {net} {currency} (from the price given)',
  'selections.copy.combinedProbability': 'Combined chance ≈ {value}, assuming the matches are independent (an approximation, not a calibrated prediction)',
  'selections.copy.disclaimer': 'Probabilities are the provider’s published forecasts, not offered prices. No bet is placed by this application.',
} as const

export default reader
