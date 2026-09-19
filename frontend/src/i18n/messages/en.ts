/**
 * English — the source catalogue, and the fallback.
 *
 * EVERY VALUE HERE IS THE EXACT STRING THE INTERFACE ALREADY SHIPPED. Localising a product is not
 * a licence to rewrite its copy: the wording in this application was argued over line by line
 * (what a paused refresh may and may not imply, why a withheld percentage is a sentence rather
 * than a dash, why "kicked off" and "finished" are different verbs), and a translation pass that
 * quietly reworded any of it would be changing the product under cover of changing the language.
 * So English output is byte-identical to what it was, and the browser suite that pins those
 * sentences keeps passing unchanged.
 *
 * WHAT IS NEW here rather than moved: the language and time-zone settings, and the market period
 * notes (`market.period.*`). Both are additions this package is responsible for.
 *
 * HOW TO ADD A STRING. Add the key here first. `Catalog` in ./types.ts is derived from this
 * object, so `fr.ts` stops compiling until the French exists — which is the only mechanism that
 * reliably stops a half-translated page shipping.
 *
 * WHAT MUST NEVER BE PUT IN A CATALOGUE:
 *   - a team name, a competition name, a venue or a person's name. The provider publishes those
 *     and they are reproduced as published.
 *   - a provider's own message. `{reason}` holes are filled with the backend's or the provider's
 *     verbatim words in every language. Only OUR summary of a refusal is translated, and the
 *     verbatim text stays on the page beside it.
 *   - a number. Every figure comes from the payload and is formatted, never written down.
 */

const en = {
  // ─── the product, and the shell ──────────────────────────────────────────────────────────
  'app.name': 'Soccer Predictions',
  'app.htmlLang': 'en',
  'app.defaultTitle': 'Soccer Predictions - Professional Football Analytics',
  'app.defaultDescription': 'Get accurate soccer predictions with advanced analytics and expert insights. Professional football betting tips and match analysis.',
  'app.brandHome': 'Soccer Predictions, home',
  'app.skipToMatches': 'Skip to the matches',
  'app.topNavigation': 'Top',

  'nav.home': 'Home',
  'nav.matches': 'Matches',
  'nav.leagues': 'Leagues',
  'nav.dashboard': 'Dashboard',
  'nav.expert': 'Expert',
  'nav.expertDashboard': 'Expert Dashboard',
  'nav.accountMenu': 'Account menu',
  'nav.profileSettings': 'Profile Settings',
  'nav.changePassword': 'Change Password',
  'nav.subscription': 'Subscription',
  'nav.signOut': 'Sign Out',
  'nav.signIn': 'Sign In',
  'nav.signUp': 'Sign Up',
  'nav.createAccount': 'Create account',
  'nav.openMenu': 'Open main menu',
  'nav.closeMenu': 'Close main menu',

  'search.placeholder': 'Search teams, leagues...',
  'search.searching': 'Searching...',
  'search.failed': 'Failed to search. Please try again.',
  'search.noResults': 'No results found for "{query}"',
  'search.tryAnother': 'Try a different search term',
  'search.teams': 'Teams ({count})',
  'search.leagues': 'Leagues ({count})',
  'search.keyboardHint': 'Use ↑↓ to navigate, Enter to select, Esc to close',

  'footer.tagline': 'Fixtures, results and model forecasts for Europe’s top five leagues and the Champions League, alongside predictions published by registered experts. Every probability names its source. Nothing here is betting advice.',
  'footer.quickLinks': 'Quick Links',
  'footer.todaysMatches': 'Today\'s matches',
  'footer.tomorrowsMatches': 'Tomorrow\'s matches',
  'footer.signInRequired': ' (sign in required)',
  'footer.support': 'Support',
  'footer.helpCentre': 'Help Centre',
  'footer.contactUs': 'Contact Us',
  'footer.privacyPolicy': 'Privacy Policy',
  'footer.termsOfService': 'Terms of Service',
  'footer.notPublishedYet': '(not published yet)',
  'footer.rights': '© {year} Soccer Predictions. All rights reserved.',
  'footer.socialNotSetUp': '{network} account not set up yet',

  // ─── reading settings: language, and the zone every time on screen is in ─────────────────
  'settings.title': 'Reading settings',
  'settings.language': 'Language',
  'settings.languageHelp': 'The words on this site. It does not change team names, competition names or a provider’s own message, which are shown as published.',
  'settings.languageFellBack': 'The French text could not be downloaded, so this page is in English. Your choice has been kept and will be tried again on the next load.',
  'settings.timeZone': 'Time zone',
  'settings.timeZoneHelp': 'Every kick-off time on this site is shown in this zone, and “today” means a day in it.',
  'settings.timeZoneNow': 'Times are shown in {zone}.',
  'settings.useDeviceZone': 'Use this device’s zone ({zone})',
  'settings.zoneObservesDst': 'clocks change during the year',
  'settings.independent': 'Language, time zone and where you are are three separate things, and this site treats them that way: choosing one changes nothing about the others, and none of them is taken as evidence of the others. Your country is not stored and not guessed.',
  'settings.notDurable': 'This browser is not letting us store your choices, so they will apply to this page only and be forgotten when you reload.',
  'settings.openLabel': 'Language and time zone',

  // ─── waiting for, and failing to get, a page ─────────────────────────────────────────────
  'route.loading': 'Loading this page…',
  'route.notDownloadedTitle': 'This page could not be downloaded',
  'route.notDownloadedBody': 'Its code did not finish arriving. Reloading usually fixes it.',
  'route.failedTitle': 'This page could not be shown',
  'route.failedBody': 'Something in it failed while it was being drawn. Reloading may help; if it does not, the fault is ours and not your connection.',
  'route.reload': 'Reload the page',

  'notFound.title': 'Page Not Found',
  'notFound.body': 'The page you\'re looking for doesn\'t exist or has been moved.',
  'notFound.goHome': 'Go Home',
  'notFound.documentTitle': 'Page Not Found - Soccer Predictions',
  'notFound.documentDescription': 'The page you\'re looking for could not be found.',

  // ─── durations, and moments, which most other sentences are built out of ─────────────────
  'duration.minutes': '{count, plural, one {# minute} other {# minutes}}',
  'duration.hours': '{count, plural, one {# hour} other {# hours}}',
  'duration.days': '{count, plural, one {# day} other {# days}}',
  'time.justNow': 'just now',
  'time.inUnderAMinute': 'in under a minute',
  'time.ago': '{duration} ago',
  'time.in': 'in {duration}',

  // ─── the matchday workspace ──────────────────────────────────────────────────────────────
  'matchday.title.today': 'Today\'s matches',
  'matchday.title.tomorrow': 'Tomorrow\'s matches',
  'matchday.title.generic': 'Matches',
  'matchday.relative.today': 'Today',
  'matchday.relative.tomorrow': 'Tomorrow',
  'matchday.relative.yesterday': 'Yesterday',
  'matchday.dateLine': '{relative}, {date}',
  'matchday.timesIn': 'Times in {zone}',
  'matchday.loading': 'Loading matches…',
  'matchday.loadingCompetitions': 'Loading the competitions on this date…',
  'matchday.errorTitle': 'These fixtures could not be loaded.',
  'matchday.errorNote': 'This is a problem reaching our own service. It is not a statement about what is on this date.',
  'matchday.retry': 'Retry',
  'matchday.emptyTitle': 'No matches stored for this date.',
  'matchday.emptyDescription': 'This installation holds no fixtures for {date}. Fixtures appear here once they have been fetched and stored, so this is what we hold rather than a statement that nothing is being played.',
  'matchday.showTomorrow': 'Show tomorrow\'s matches',
  'matchday.showToday': 'Show today\'s matches',
  'matchday.pickAnotherDate': 'Pick another date',
  'matchday.filteredEmptyTitle': 'No matches match your filters.',
  'matchday.filteredEmptyDescription': '{count, plural, one {# fixture is} other {# fixtures are}} stored for {date}; none of them match every filter you have set.',
  'matchday.clearAllFilters': 'Clear all filters',
  'matchday.seeAll': 'See all {count} matches',
  'matchday.openWorkspace': 'Open the matchday workspace',
  'matchday.backToToday': 'Back to today',
  'matchday.moreCompetitions': '{count} more',
  'matchday.moreCompetitionsSr': ' competitions, in the filters',
  'matchday.filterByCompetition': 'Filter by competition',
  'matchday.footnote': 'Every fixture stored for this date. Each probability is shown exactly as the source published it, and a market no source published is marked unavailable rather than shown as zero.',
  'matchday.documentDescription': 'Fixtures for {date} from the top five European leagues and the Champions League, with the model forecast and any expert prediction published for each match. Every probability names its source; a market no source published is shown as unavailable.',

  /*
   * The scoring note, measured from the fixtures actually on screen.
   *
   * THREE MESSAGES, NOT A SENTENCE BUILT FROM PARTS, and this is the clearest case in the whole
   * catalogue for why. The English reads "None of the 12 fixtures … has been played"; the French
   * has to agree a determiner, a pronoun and a past participle with a noun that has not appeared
   * yet, and French counts 0 and 1 as singular where English counts only 1. Every one of those
   * decisions belongs to the language, so each language gets the whole sentence.
   */
  'matchday.scoring.nonePlayed': '{count, plural, one {The fixture listed here has not been played yet} other {None of the # fixtures listed here has been played yet}}, so nothing on this page has been scored against a result and no accuracy is claimed for any of it.',
  'matchday.scoring.allPlayed': '{count, plural, one {The fixture listed here has {verb, select, finished {finished} other {kicked off}}} other {All # fixtures listed here have {verb, select, finished {finished} other {kicked off}}}}. Whether a prediction for one of them has been scored against its result is stated on that match\'s own page; this list claims no accuracy either way.',
  'matchday.scoring.somePlayed': '{started, plural, one {# of the {total} fixtures listed here has} other {# of the {total} fixtures listed here have}} {verb, select, finished {finished} other {kicked off}}. Whether a prediction for one of them has been scored against its result is stated on that match\'s own page; this list claims no accuracy either way.',

  // ─── the date strip ──────────────────────────────────────────────────────────────────────
  'dateStrip.chooseDate': 'Choose a date',
  'dateStrip.previousDay': 'Previous day',
  'dateStrip.nextDay': 'Next day',
  'dateStrip.jumpToDate': 'Jump to a specific date',
  'dateStrip.dayMatches': ', {count, plural, one {# match} other {# matches}}',

  // ─── filters ─────────────────────────────────────────────────────────────────────────────
  'filters.open': 'Filters',
  'filters.title': 'Filters',
  'filters.close': 'Close filters',
  'filters.apply': 'Show results',
  'filters.clearAll': 'Clear all',
  'filters.noneApplied': ', no filters applied',
  'filters.countApplied': ', {count, plural, one {# filter} other {# filters}} applied',
  'filters.removeFilter': 'Remove filter {label}',
  'filters.resultCount': '{count, plural, one {# match} other {# matches}}',
  'filters.show': 'Show',
  'filters.showHint': 'Which fixtures on this date are listed.',
  'filters.whichFixtures': 'Which fixtures to show',
  'filters.competitions': 'Competitions',
  'filters.competitionsHintEmpty': 'Nothing is stored for this date, so there are no competitions to choose from.',
  'filters.competitionsHint': 'Leave all unselected to see every competition.',
  'filters.markets': 'Published markets',
  'filters.marketsHint': 'Keeps only fixtures where a source actually published every market you tick. A market nobody published is absent from the data, never a zero.',
  'filters.sources': 'Sources',
  'filters.sourcesHint': 'Keeps only fixtures that have the source you tick.',
  'filters.group.competition': 'Competition',
  'filters.group.market': 'Market',
  'filters.group.source': 'Source',
  'filters.group.showing': 'Showing',
  'filters.selectedCompetition': 'Selected competition',
  'filters.status.all': 'Everything on this date',
  'filters.status.upcoming': 'Upcoming and in play',
  'filters.status.finished': 'Played',
  'filters.marketOption.1x2': 'Match result (1X2)',
  'filters.marketOption.btts': 'Both teams to score',
  'filters.marketOption.overUnder': 'Over / under goals',
  'filters.marketOption.correctScore': 'Correct score',
  'filters.sourceOption.model': 'Has a model forecast',
  'filters.sourceOption.expert': 'Has an expert prediction',

  /*
   * WHAT PERIOD A MARKET COVERS — and the honest answer, which is that nobody told us.
   *
   * A bettor reading "Over 2.5" needs to know whether extra time counts, because in a cup tie it
   * changes the answer. Neither GameForecastAPI nor an expert composing a prediction on this site
   * publishes a period with a market: there is no such field anywhere in the payload, and the
   * settlement service scores against the stored full-time score. So the definitions below say
   * what is counted, and the note says plainly that the period is not published rather than
   * asserting a convention we have no evidence anybody applied. Inventing "90 minutes plus
   * stoppage time" here would be exactly the defect this codebase has already caught three times:
   * a fact about the data written down as a constant.
   */
  'market.period.note': 'None of the sources publishes the period a market covers. These are scored against the stored full-time score, so where a tie can go to extra time or penalties, whether those count is not stated by the source.',
  'market.definition.1x2': 'Which side is ahead at the end of the match, or a draw.',
  'market.definition.btts': 'Whether both sides score at least one goal.',
  'market.definition.overUnder': 'Whether the two sides’ goals together come to more or fewer than the line.',
  'market.definition.correctScore': 'The exact number of goals each side scores.',

  // ─── one fixture in a list ───────────────────────────────────────────────────────────────
  'fixture.live': 'Live',
  'fixture.ft': 'FT',
  'fixture.postponed': 'Postp.',
  'fixture.cancelled': 'Canc.',
  'fixture.versus': '{home} versus {away}',
  'fixture.openAnalysis': '{fixture}. Open the full analysis.',
  'fixture.fullAnalysis': 'Full analysis',
  'fixture.showDetails': 'Show details for {fixture}',
  'fixture.hideDetails': 'Hide details for {fixture}',
  'fixture.side.home': 'Home',
  'fixture.side.draw': 'Draw',
  'fixture.side.away': 'Away',
  'fixture.aDraw': 'a draw',
  // `{percent}` arrives already formatted, sign included: "85%" in English, "85 %" in French.
  'fixture.confidencePublished': '{percent} confidence, published by the {source}',
  'fixture.leadTitle': '{source}: {outcome} at {percent}, as published by the source.',
  'fixture.noMatchResult': 'This source published nothing for the match result.',
  'fixture.alsoPublished': '{source, select, model {Model} other {Expert}} also published',
  'fixture.groupCount': ' {count, plural, one {match} other {matches}}',

  // ─── who said it ─────────────────────────────────────────────────────────────────────────
  'source.model': 'Model',
  'source.expert': 'Expert',
  'source.description.model': 'Forecast published by the model provider',
  'source.description.expert': 'Prediction published by one of our experts',
  /*
   * `{source}` looks pointless in English and is the whole point in French.
   *
   * These three words sit after the source's name on a chip — "Model · out of date", "Expert ·
   * none" — and in French they agree with the noun each source implies: a model publishes a
   * "prévision" (feminine) and an expert a "pronostic" (masculine). One adjective for both is
   * wrong for one of them, whichever is chosen, and the agreement cannot be recovered after the
   * string is handed over. So the source travels with it.
   */
  'source.state.stale': 'out of date',
  'source.state.referenceOnly': 'for reference',
  'source.state.unavailable': 'none',
  'source.markerDescription': '{description} — {suffix}',

  // ─── markets, outcomes, and the reasons one is missing ───────────────────────────────────
  'market.matchResult': 'Match result',
  'market.btts': 'Both teams to score',
  'market.overUnder25': 'Total goals 2.5',
  'market.overUnder35': 'Total goals 3.5',
  'market.exactScore': 'Exact score',
  'market.correctScore': 'Exact score',

  'outcome.homeWin': 'Home win',
  'outcome.draw': 'Draw',
  'outcome.awayWin': 'Away win',

  'missing.noForecastRetrieved': 'Never retrieved',
  'missing.marketNotInForecast': 'Not in this forecast',
  'missing.forecastStale': 'Out of date',
  'missing.refreshBlocked': 'Refresh paused',
  'missing.noExpertPrediction': 'No expert prediction',
  'missing.marketNotSupplied': 'Expert left this out',
  'missing.notOfferedBySource': 'Not published by this source',

  'preview.noForecastRetrieved': 'No forecast has ever been retrieved for this fixture, so the model\'s view of it is unknown.',
  'preview.marketNotInForecast': 'A forecast was retrieved for this fixture, but it did not include this market.',
  'preview.noExpertPrediction': 'No expert has published a prediction for this fixture.',
  'preview.marketNotSupplied': 'The expert published a prediction for this fixture, but left this market out of it.',
  'preview.refreshBlocked': 'Forecast refreshes are paused right now.',

  'probability.unavailable': 'Unavailable',
  'probability.notSet': 'not set',

  // ─── how old a forecast is ───────────────────────────────────────────────────────────────
  'brief.noForecastHeld': 'No forecast held',
  'brief.noForecastHeldDetail': 'Nothing has been retrieved from the forecast provider for this fixture.',
  'brief.ageUnknown': 'Age unknown',
  'brief.ageUnknownDetail': 'The provider published no model-run time for this forecast, so how old it is cannot be stated.',
  'brief.basisNote': 'The provider published no model-run time, so this age is measured from when we retrieved the forecast, not from when it was produced.',
  'brief.keptForReference': 'Kept for reference',
  'brief.keptForReferenceAged': 'Kept for reference · {age} old',
  'brief.kickoffPassedDetail': 'Kickoff has passed. This is preserved as the forecast that was published, not offered as a current one.',
  'brief.outOfDate': 'Out of date',
  'brief.outOfDateAged': 'Out of date · {age} old',
  'brief.staleDetail': 'This forecast is older than the freshness limit.',
  'brief.staleDetailWithLimit': 'This forecast is older than the freshness limit (limit {hours} hours).',
  'brief.current': 'Current',
  'brief.aged': '{age} old',

  'provenance.sourcePrefix': 'Source: ',
  'provenance.refreshPaused': 'Refresh paused — {reason}',

  // ─── the sources by name ─────────────────────────────────────────────────────────────────
  'provider.gameforecast': 'GameForecast model',
  'provider.apiFootball': 'API-Football model',
  'provider.sample': 'Sample data (not real)',
  'provider.expert': 'Expert',
  'provider.namedModel': '{name} model',
  'provider.model': 'Model',
  'provider.none': 'The forecast provider',

  'prediction.none': 'No prediction',
  'prediction.expert': 'Expert prediction',
  'prediction.placeholder': 'Placeholder (demo)',

  'bet.homeWin': 'Home win',
  'bet.draw': 'Draw',
  'bet.awayWin': 'Away win',
  'bet.bttsYes': 'Both teams to score: Yes',
  'bet.bttsNo': 'Both teams to score: No',
  'bet.overGoals': 'Over {line} goals',
  'bet.underGoals': 'Under {line} goals',

  'generation.modelRun': 'Model run {when}',
  'generation.retrievedOnly': 'Generation time not published; retrieved {when}',
  'generation.published': 'Published {when}',

  // ─── the fixture providers, named once for the whole interface ───────────────────────────
  'fixtureProvider.livescore': 'Live Score API',
  'fixtureProvider.apiFootball': 'API-Football (fallback)',
  'fixtureProvider.thesportsdb': 'TheSportsDB (fallback)',
  'fixtureProvider.sample': 'sample data (not real fixtures)',
  'fixtureProvider.none': 'no provider',

  // ─── the scheduled refresh: what is current, and what is not ─────────────────────────────
  'sync.task.fixtures': 'Fixtures and kick-off times',
  'sync.task.live': 'Live scores',
  'sync.task.results': 'Final results',
  'sync.task.forecasts': 'Model forecasts',

  'freshness.stored': 'Stored data',
  'freshness.summary.unknown': 'Stored data · how current it is cannot be stated',
  'freshness.summary.noSchedule': 'Stored data · no scheduled refresh is reported',
  'freshness.summary.switchedOff': 'Stored data · scheduled refresh is switched off',
  'freshness.summary.noStateStore': 'Stored data · when it last refreshed is unknown',
  'freshness.summary.noFixtureTask': 'Stored data · nothing here refreshes fixtures or scores',
  'freshness.summary.refreshed': 'Stored data · fixtures and scores last refreshed {age}',
  'freshness.summary.neverRun': 'Stored data · no scheduled refresh has run yet',
  'freshness.summary.neverSucceeded': 'Stored data · no scheduled refresh has succeeded yet',

  'freshness.note.noStatus': 'The status service could not be reached, so when this was last refreshed is unknown.',
  'freshness.note.noSchedule': 'This installation reports no refresh schedule, so stored data changes only when a page asks the provider for new data.',
  'freshness.note.switchedOff': 'Automatic refreshes are switched off here. What is stored stays as it is until somebody refreshes it.',
  'freshness.note.noStateStore': 'The scheduler cannot reach its state store, so it cannot report when any task last ran.',
  'freshness.note.noFixtureTask': 'No scheduled task on this installation refreshes fixtures, kick-off times or results.',
  'freshness.note.noPassYet': 'The scheduler is running but no task has completed a pass yet, so there is no refresh time to report.',

  'freshness.forecasts.switchedOff': 'Model forecasts · automatic refresh is switched off',
  'freshness.forecasts.refreshed': 'Model forecasts last refreshed {age}',
  'freshness.forecasts.neverRun': 'Model forecasts · no refresh has run yet',
  'freshness.forecasts.neverSucceeded': 'Model forecasts · no refresh has succeeded yet',
  'freshness.forecasts.ageNotReported': 'Model forecasts · when they last refreshed is not reported',

  'freshness.task.switchedOff': 'switched off',
  'freshness.task.switchedOffDetail': 'This task is not switched on for this installation, so nothing refreshes it automatically.',
  'freshness.task.neverRun': 'has never run',
  'freshness.task.neverSucceeded': 'has not succeeded yet',
  'freshness.task.pausedSuffix': '{state} — paused',
  'freshness.task.updated': 'updated {when}',
  'freshness.task.noFailureReason': 'The backend did not report why the last attempt failed.',
  'freshness.task.pausedDetail': 'Paused: {reason}',
  'freshness.task.failedDetail': 'Last attempt failed: {reason}',
  'freshness.task.behindDetail': 'This task is more than a full interval past due.',
  'freshness.task.providerSaid': 'The provider said: {reason}',

  'freshness.line.failed': '{task}: last attempt failed — {reason}',
  'freshness.line.paused': '{task}: paused — {reason}',
  'freshness.line.behind': '{task}: more than a full interval past due, so what is stored may be older than the schedule intends.',
  'freshness.line.mechanics': '{task}: {detail}',
  'freshness.reason.unstated': 'the backend did not say why',
  'freshness.reason.quota': 'the provider refused the request because our daily allowance with it is spent',
  'freshness.reason.budget': 'our own daily request allowance for this provider is spent',
  'freshness.reason.credentials': 'the provider rejected our credentials',
  'freshness.reason.timeout': 'it timed out before answering',

  'freshness.nextAttempt.ahead': 'The next attempt is {when}.',
  'freshness.nextAttempt.dueNow': 'The next attempt is due now.',
  'freshness.nextAttempt.overdueMinutes': 'The next attempt is overdue by {count, plural, one {# minute} other {# minutes}}.',
  'freshness.nextAttempt.overdueHours': 'The next attempt is overdue by {count, plural, one {# hour} other {# hours}}.',
  'freshness.nextAttempt.overdueDays': 'The next attempt is overdue by {count, plural, one {# day} other {# days}}.',
  'freshness.nextScheduled': 'The next scheduled attempt is {when}.',

  /*
   * "Scheduled every 6 hours" / "every 2 days".
   *
   * `unit` looks redundant in English, where "every" does not change. It is not redundant in
   * French, where the determiner agrees with the gender of the unit — "toutes les 6 heures" but
   * "tous les 2 jours" — and the agreement cannot be derived from the translated duration string
   * after the fact. The parameter exists for the languages that need it.
   */
  'freshness.cadence': 'Scheduled every {duration}.',
  'freshness.backoff.none': 'It is waiting {window} before trying again.',
  'freshness.backoff.afterOne': 'After 1 failure it is waiting {window} before trying again.',
  'freshness.backoff.afterMany': 'After {count, plural, one {# failure} other {# failures}} in a row it is waiting {window} before trying again.',
  'freshness.allowanceReset': 'Our daily request allowance is counted per UTC day, so it resets at 00:00 UTC.',
  'freshness.allowanceResetWhen': 'Our daily request allowance is counted per UTC day, so it resets at 00:00 UTC — {when}.',

  'freshness.panel.heading': 'How current this is',
  'freshness.panel.label': 'How current this page is',
  'freshness.panel.disclosure': 'What was refreshed, and when',
  'freshness.panel.lastAnswerFrom': 'Last answer from {provider}:',
  'freshness.panel.notAnswered': 'it has not answered successfully yet',
  'freshness.panel.pausedAfterFailure': 'Paused after a failure: {reason}',
  'freshness.panel.ourTimes': 'These are our own retrieval and refresh times. When a provider’s model actually ran is a different fact, published with each forecast on its match page.',

  // ─── model forecasts: paused, or unavailable, never both at once ─────────────────────────
  'forecast.notConfigured': 'Prediction provider "{provider}" is not configured; model forecasts are unavailable.',
  'forecast.pausedAllowance': 'Model forecast updates are paused until the daily request allowance resets; forecasts already loaded stay visible.',
  'forecast.pausedError': 'Model forecast updates are paused after a provider error: {reason}. Forecasts already loaded stay visible.',
  'forecastSync.pausedWithReason': '{provider} refresh is paused: {reason}',
  'forecastSync.pausedDeferred': '{provider} refresh is paused; {count} competition(s) wait for the next allowance reset',
  'forecastSync.stayVisible': 'Forecasts already loaded stay visible and are unchanged — they are just not being updated right now.',
  'forecastSync.waitingFor': 'Waiting for the next allowance reset: {competitions}',
  'forecastSync.lastAttempt': 'Last refresh attempt {when}',
  'forecastSync.disclosure': 'What this means for what you are reading',

  // ─── where the fixtures came from ────────────────────────────────────────────────────────
  'dataSource.staleTitle': 'Showing the last saved fixtures.',
  'dataSource.staleTitleWhen': 'Showing the last saved fixtures (from {when}).',
  'dataSource.staleBody': 'The data provider could not be reached; kick-off times and scores may be out of date.',
  'dataSource.unavailableTitle': 'Live fixture data is unavailable right now.',
  'dataSource.providedBy': 'Fixtures provided by {provider}.',

  // ─── the site-wide fault banner ──────────────────────────────────────────────────────────
  'banner.noProvider': 'No match-data provider is configured (DATA_PROVIDER={provider}); fixtures cannot be refreshed.',
  'banner.fallbackInUse': 'Primary provider "{provider}" is not configured; using {fallback} as fallback.',
  'banner.budgetExhausted': 'Daily request budget for {provider} is exhausted; showing cached data until tomorrow.',
  'banner.providerCoolingDown': 'Fixture provider {provider} is paused after a failure: {reason}',
  'banner.lastRequestFailed': 'Last {provider} request failed: {reason}',
  'banner.dismiss': 'Dismiss',
  'banner.oneMoreDetail': 'One more provider detail',
  'banner.moreDetails': '{count} more provider details',

  // ─── empty and failed states ─────────────────────────────────────────────────────────────
  'emptyState.couldNotLoad': 'Could not load. ',
  'emptyState.unavailableNow': 'Unavailable right now. ',

  // ─── errors from a request ───────────────────────────────────────────────────────────────
  'error.serviceUnavailable': 'The service is temporarily unavailable.',
  'error.timedOut': 'The request timed out.',

  // ─── saving a match ──────────────────────────────────────────────────────────────────────
  'save.thisMatch': 'this match',
  'save.signInTo': 'Sign in to save {subject}',
  'save.savedRemove': 'Saved {subject}. Select to remove it from your saved matches.',
  'save.addTo': 'Save {subject} to your saved matches.',
  'save.signInShort': 'Sign in to save',
  'save.saved': 'Saved',
  'save.save': 'Save',

  // ─── the measured record ─────────────────────────────────────────────────────────────────
  'measured.market.matchResult': 'Match result',
  'measured.market.bothTeamsScore': 'Both teams to score',
  'measured.market.overUnder25': 'Total goals 2.5',
  'measured.market.overUnder35': 'Total goals 3.5',
  'measured.market.correctScore': 'Exact score',
  'measured.sourceKind.modelProvider': 'Model provider',
  'measured.sourceKind.expert': 'Expert',
  'measured.window': '{start} to {end}',
  'measured.excluded.pushes': '{count, plural, one {# push} other {# pushes}}',
  'measured.excluded.voids': '{count} void',
  'measured.excluded.notScored': '{count} not scorable',
  'measured.counts': '{eligible} eligible · {parts}',
  'measured.counts.scored': '{count} scored',
  'measured.counts.pending': '{count} awaiting settlement',
  'measured.counts.void': '{count} void',
  'measured.counts.notScored': '{count} not scorable',

  'measured.state.notLoaded': 'The measured record has not been loaded.',
  'measured.state.failed': 'The measured record could not be loaded.',
  'measured.state.failedDetail': '{error} This says nothing about what has or has not been scored — only that we could not ask.',
  'measured.state.none': 'Nothing has been scored yet, so no source has a measured record.',
  'measured.state.noneWhy': 'Why: {reason}.',
  'measured.state.noneDetail': 'No prediction in this window has been settled against a final result.',
  'measured.state.pending': 'No source has a measured record yet.',
  'measured.state.pendingDetail': 'Predictions from the sources below are in scope, but none of them has been scored against a final result yet. The counts are real; there is simply no rate to report.',
  'measured.state.measured': '{measured} of {total, plural, one {{total} source has} other {{total} sources have}} a measured record.',
  'measured.state.measuredDetail': 'Every figure below is counted from settled results and carries the sample it was counted from. It is a record of what happened, not a forecast of what will.',

  'measured.heading': 'How the sources have actually done',
  'measured.intro': 'Counted from settled results by comparing what a source published before kick-off with what happened. Scoring a forecast is arithmetic against a real result — it is not a new prediction, and none of it says what will happen next.',
  'measured.loading': 'Loading the measured record…',
  'measured.windowLine': 'Window: {window} — {basis}. Measured {when}.',
  'measured.hitRate': 'hit rate from {sample} scored',
  'measured.hitRateWithheld': 'no hit rate published',
  'measured.needMore': '{sample} of {minimum} scored predictions needed before a rate is published.',
  'measured.howCounted': 'How this market is counted and settled',
  'measured.countedAs': 'Counted as: ',
  'measured.settledBy': 'Settled by: ',
  'measured.sampleSize': 'Sample size: ',
  'measured.sampleSizeValue': '{count, plural, one {scored prediction} other {scored predictions}}',
  'measured.correctOutcomes': 'Correct outcomes: ',
  // The hit count and the sample it is out of, as ONE message. It was two `<span>`s with the
  // words "of those" hardcoded between them in the JSX, which is the fragment assembly this
  // package exists to remove: a string that never entered a catalogue is invisible both to a
  // translator and to the catalogue-generated stray-language check, so it shipped in English on
  // a French page.
  'measured.hitCount': '{hits} of those {scored}',
  'measured.nothingScoredInMarket': 'nothing in this market has been scored yet, so none of it is right or wrong',
  'measured.notInSample': 'Not in the sample: ',
  'measured.brier': 'Brier score: ',
  'measured.brierFrom': 'from',
  'measured.brierPredictions': 'predictions',
  'measured.brierBaseline': ' · an uninformative forecast scores',
  'measured.brierWithheld': 'computable for {sample} predictions so far; {minimum} needed before a Brier score is published',
  'measured.sourceUnmeasured': 'Nothing from this source has been scored in this window yet.',
  'measured.notScoredReason': 'not scored — {reason}',
  'measured.rulesDisclosure': 'The rules every figure here was settled by',
  'measured.rules.ruleset': 'Ruleset: ',
  'measured.rules.basis': 'Basis: ',
  'measured.rules.prematchOnly': 'Only pre-kickoff evidence: ',
  'measured.rules.void': 'Void fixtures: ',
  'measured.rules.unsuppliedMarket': 'A market a source did not publish: ',
  'measured.rules.hitRate': 'Hit rate: ',
  'measured.rules.brier': 'Brier score: ',

  // ─── the home page ───────────────────────────────────────────────────────────────────────
  'home.documentTitle': 'Soccer Predictions - Fixtures, Model Forecasts and Expert Analysis',
  'home.documentDescription': 'Fixtures and results for the top five European leagues and the Champions League, with GameForecastAPI model forecasts and predictions published by registered experts.',
  'home.coverageHeading': 'How much football is loaded right now',
  'home.coverageCounting': 'Counting what is stored…',
  'home.coverageFailed': 'The stored-data counts could not be loaded, so nothing is claimed about how much is here.',
  'home.coverageStored': '{fixtures} upcoming fixtures stored across {competitions} competitions.',
  'home.coverageForecasts': '{withForecast} of them carry a model forecast; the other {without} have none.',
  'home.coverageExperts': '{count} expert predictions have been published.',
  'home.coverageNoExperts': 'No expert has published a prediction yet.',
  'home.coverageDisclosure': 'The counts one by one',
  'home.coverageCountedFrom': 'Counted from the stored data.',
  'home.coverageCountedFromWhen': 'Counted from the stored data on {when}.',
  'home.stat.competitions': 'Competitions covered',
  'home.stat.competitionsDetail': 'Top five European leagues and the Champions League',
  'home.stat.fixtures': 'Upcoming fixtures loaded',
  'home.stat.fixturesDetail': 'Scheduled and in-play matches currently stored',
  'home.stat.forecasts': 'Model forecasts available',
  'home.stat.forecastsDetail': 'Upcoming matches with a GameForecast model prediction attached',
  'home.stat.forecastsDetailOf': 'Of the {total} upcoming matches stored; the rest have no model forecast attached',
  'home.stat.expertPredictions': 'Expert predictions published',
  'home.stat.expertPredictionsDetail': 'Published by experts registered on this site',
  'home.statUnavailable': 'Unavailable',
  'home.aboutHeading': 'Where these numbers come from',
  'home.aboutBody': 'Fixtures and results from Europe’s top five leagues and the Champions League, with model forecasts from GameForecastAPI and predictions published by registered experts. Every probability comes from a named source and is reproduced as that source published it. None of this is betting advice.',
  'home.methodDisclosure': 'The rules this site holds itself to',
  'home.method1': 'Nothing here is computed on your behalf. When a source did not publish a market, the match says so in the source’s own words instead of showing a zero, and when a forecast is older than it should be, the fixture says that too.',
  'home.method2': 'How often each source has been right is not guessed at either: it is counted from settled results, and the measured record below shows exactly how much has been counted so far. Below the minimum sample no rate is published at all — the counts are shown and the percentage is withheld, because a rate from a handful of results would mislead.',
  'home.method3': 'A probability is not a forecast of what will happen, and a probability published for one fixture is not a record of how often its source has been right.',
  'home.browseByDate': 'Browse matches by date',
  'home.competitions': 'Competitions',
  'home.followHeading': 'Follow the fixtures that matter',
  'home.followBody': 'Create an account to save matches and follow the teams and competitions you care about. Forecasts and expert analysis are public either way, on every fixture where a source has published them.',
  'home.createAccount': 'Create an account',
  'home.tomorrowsMatches': 'Tomorrow’s matches',
} as const

export default en
