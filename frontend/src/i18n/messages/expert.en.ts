/**
 * English — the EXPERT area: the workspace, match selection, the composer, my predictions, and
 * the post-publication moderation list.
 *
 * EVERY VALUE HERE IS THE EXACT STRING THOSE SCREENS ALREADY SHIPPED, character for character.
 * Localising a product is not a licence to reword it, and the live browser suite pins some of
 * these by their English: `e2e/live/expert-composer.spec.ts` matches "Write a prediction:" as a
 * button's accessible name, "Choose a fixture" and "Advanced: paste a match id". Two English
 * strings that differ only in capitalisation ("Back to dashboard" on the composer and the
 * selection page, "← Back to Dashboard" on the other two) are deliberately NOT unified here;
 * unifying them would be a copy change smuggled in under a translation change, so there are two
 * keys and the report says so.
 *
 * ── THE ONE RULE THIS AREA EXISTS TO PROTECT ────────────────────────────────────────────────
 *
 * A probability, a sample, a window and a refusal must mean in French exactly what they mean in
 * English. Three wordings on these screens carry that weight and none of them may soften:
 *
 *   - `expert.dashboard.notScoredYet` is what stands where an accuracy would be when nothing has
 *     ever been settled against a result. It must never render as a zero, a band, or "0%".
 *   - `expert.dashboard.nonePublished` is what stands where an average conviction would be when
 *     no conviction was ever claimed. A stored 0 means "nobody claimed one", not "zero per cent
 *     confident", and the French must not turn it into the latter.
 *   - `expert.compose.publishImmediate` and `expert.published.body` state that publication is
 *     immediate and unreviewed. They are a warning, not a reassurance, and the French keeps the
 *     indicative: it says publishing DOES make this public, never that it may.
 *
 * ── WHAT IS NOT IN HERE, DELIBERATELY ───────────────────────────────────────────────────────
 *
 *   - A NUMBER. "type 55 for 55%, not 0.55" reads as three literals and is not: 55 % and 0,55
 *     are written differently in French, so the examples arrive as `{typed}`, `{whole}` and
 *     `{decimal}`, formatted by `formatNumber` and `formatPercentValue`. The goal lines are the
 *     same — `{line}` is 2.5 in English and 2,5 in French, and neither is typed here.
 *   - A TEAM, COMPETITION OR PERSON'S NAME. They arrive as `{home}`, `{away}`, `{who}` and are
 *     rendered as the provider or the account published them.
 *   - THE BACKEND'S OWN WORDS. A prediction's `source`, `status` and `priority_level`, and every
 *     message an API error carries, are shown verbatim in both languages. The status FILTER
 *     labels below are ours — they are the options on our own select — but the badge beside each
 *     prediction renders what the server sent, in `PredictionStatusBadge`, which this package
 *     does not own and has not translated.
 *   - A DATE OR A TIME. `formatDate`, `formatDateTime` and `backendInstant` in ../index.ts own
 *     those, in the reader's language and their CHOSEN zone — which for an expert deciding
 *     whether a fixture is still prematch is not a cosmetic matter.
 *
 * ── NO MESSAGE HERE COUNTS ANYTHING ─────────────────────────────────────────────────────────
 *
 * Several interpolate a count — `expert.mine.listHeading`, `expert.queue.listHeading`,
 * `expert.page.number` — and none of them needs a plural branch, in either language: the noun in
 * each is a fixed list label ("Your Predictions (0)", « Vos pronostics (0) ») exactly as the
 * screens already shipped it, and "Page" does not agree with its number. That is why this area
 * adds nothing to COUNT_CASES in frontend/e2e/mocked/localisation.spec.ts, whose guard fails on
 * any catalogue string using ICU `plural` that is not listed there. If a later change gives an
 * expert string a real plural branch, it must be registered in THAT file as well as covered in
 * frontend/e2e/mocked/expert-localisation.spec.ts, which holds this area's 0 / 1 / 2 / 11 table.
 */

const expert = {
  // ─── shared across the expert screens ───────────────────────────────────────────────────
  'expert.backToDashboard': 'Back to dashboard',
  /** The older two pages shipped this capitalisation. Not unified; see the header. */
  'expert.backToDashboardCaps': 'Back to Dashboard',
  'expert.retry': 'Try again',
  /** The compact fixture line these screens use. "v", not "versus": it shipped short. */
  'expert.fixtureShort': '{home} v {away}',
  /** The standalone separator between two team blocks on the list screens. */
  'expert.versusShort': 'vs',
  'expert.reasoningLabel': 'Reasoning:',
  'expert.deleteFailed': 'Failed to delete prediction',

  'expert.action.edit': 'Edit',
  'expert.action.publish': 'Publish',
  'expert.action.unpublish': 'Unpublish',
  'expert.action.working': 'Working…',
  'expert.action.delete': 'Delete',
  'expert.action.deleting': 'Deleting...',
  'expert.action.saving': 'Saving...',
  'expert.action.saveChanges': 'Save Changes',
  'expert.action.cancel': 'Cancel',
  'expert.action.viewDetails': 'View details',
  'expert.action.hideDetails': 'Hide details',
  'expert.action.processing': 'Processing...',
  'expert.action.preview': 'Preview',
  'expert.action.publishing': 'Publishing…',
  /** Also the FixturePicker's action label, which the live suite matches as "Write a prediction:". */
  'expert.action.writePrediction': 'Write a prediction',

  'expert.page.previous': 'Previous',
  'expert.page.next': 'Next',
  'expert.page.number': 'Page {number}',

  // Goal lines. `{line}` is formatted, never written: 2.5 here is 2,5 in French.
  'expert.line.over': 'Over {line}',
  'expert.line.under': 'Under {line}',
  'expert.line.overUnder': 'Over / under {line}',

  // ─── the expanded record, shared by my-predictions and the moderation list ──────────────
  'expert.details.predictionId': 'Prediction id',
  'expert.details.matchId': 'Match id',
  /*
   * There is no `expert.details.source` key. The label is the single word "Source", which is the
   * same word in French, and `the two catalogues hold the same keys, and no French entry is
   * still its English` in frontend/e2e/mocked/localisation.spec.ts fails on an identical pair
   * unless it is listed in that file's SAME_IN_BOTH_ON_PURPOSE — which belongs to another
   * package. Rather than invent a worse French word to dodge a test, or reach into a file this
   * package does not own, ExpertMyPredictionsPage renders `filters.group.source` from
   * ./core.en.ts: the same word, already declared identical on purpose, and already meaning
   * exactly this — which source a prediction came from.
   */
  'expert.details.priorityLevel': 'Priority level',
  'expert.details.confidence': 'Confidence',
  'expert.details.bttsConfidence': 'BTTS confidence',
  'expert.details.totalGoalsConfidence': 'Total goals confidence',
  'expert.details.published': 'Published',
  /** Stands where a publication date would be. Not a date, and never rendered as one. */
  'expert.details.notPublished': 'not published',
  'expert.details.keyFactors': 'Key factors',
  'expert.details.bttsPair': 'Both teams to score (yes / no)',
  /** One key factor. Both halves are the backend's own words. */
  'expert.details.factor': '{name}: {value}',

  // ─── the status filter's own options ────────────────────────────────────────────────────
  'expert.status.all': 'All Statuses',
  'expert.status.pending': 'Pending',
  'expert.status.underReview': 'Under Review',
  'expert.status.approved': 'Approved',
  'expert.status.published': 'Published',
  'expert.status.rejected': 'Rejected',
  'expert.status.archived': 'Archived',

  // ─── the workspace ──────────────────────────────────────────────────────────────────────
  'expert.dashboard.title': 'Expert workspace',
  'expert.dashboard.intro': 'Write predictions and manage what you have published. Your predictions go public the moment you press publish — nothing here waits for approval.',
  'expert.dashboard.loadFailed': 'Failed to load dashboard data',
  'expert.dashboard.toggleFailed': 'Failed to toggle publish status',
  'expert.dashboard.confirmDelete': 'Delete this prediction? It disappears from the public match page and cannot be undone.',
  'expert.dashboard.nextHeading': 'What to do next',
  'expert.dashboard.chooseMatch': 'Choose a match',
  'expert.dashboard.chooseMatchHint': 'One filtered fixture list. Filter by day, competition or team.',
  'expert.dashboard.myPredictions': 'My predictions',
  'expert.dashboard.myPredictionsHint': 'Edit, unpublish or remove anything you have published.',
  'expert.dashboard.recentHeading': 'Recently published',
  'expert.dashboard.emptyTitle': 'You have not published anything yet',
  'expert.dashboard.emptyBody': 'Choose a match and write your first prediction. It goes live as soon as you publish it.',
  'expert.dashboard.recordHeading': 'Your record',
  'expert.dashboard.statWritten': 'Predictions written',
  'expert.dashboard.statPublished': 'Published',
  'expert.dashboard.statNotPublished': 'Not published',
  'expert.dashboard.statAverageConviction': 'Average conviction',
  /** Where an average conviction would be when nobody ever claimed one. NEVER a zero. */
  'expert.dashboard.nonePublished': 'None published',
  'expert.dashboard.accuracy': 'Accuracy',
  /** Where an accuracy would be when nothing has been settled. NEVER a zero, never a band. */
  'expert.dashboard.notScoredYet': 'Not scored yet',
  'expert.dashboard.accuracyNote': 'No prediction has been settled against a final result yet, so there is no accuracy to report. The average conviction above is what you claimed, not a measurement of how often you were right.',
  'expert.dashboard.moderationNote': 'These are already public. Moderation happens after publication — it is not an approval gate.',
  'expert.dashboard.moderationLink': 'View the moderation list',

  'expert.row.fixtureUnavailable': 'Fixture details unavailable',
  'expert.row.competitionUnavailable': 'Competition unavailable',
  'expert.row.publishedOn': 'Published {date}',

  // ─── the local draft ────────────────────────────────────────────────────────────────────
  'expert.draft.continueTitle': 'Continue your draft',
  'expert.draft.noFixture': 'Fixture not chosen yet',
  'expert.draft.savedAgo': 'saved {ago}',
  'expert.draft.localOnly': 'Stored in this browser only. It has not been published and will not publish itself.',
  'expert.draft.continue': 'Continue',
  'expert.draft.discard': 'Discard',
  /*
   * Four whole sentences rather than a stem and two optional tails. The fixture and the "saved"
   * phrase both sit INSIDE the sentence in English, and a language that wants them elsewhere can
   * only say so if it owns the whole sentence.
   */
  'expert.draft.unfinished': 'You have an unfinished draft.',
  'expert.draft.unfinishedSaved': 'You have an unfinished draft · saved {ago}.',
  'expert.draft.unfinishedFor': 'You have an unfinished draft for {fixture}.',
  'expert.draft.unfinishedForSaved': 'You have an unfinished draft for {fixture} · saved {ago}.',
  'expert.draft.notPublishedNote': 'It is stored in this browser only and has not been published.',
  'expert.draft.continueThat': 'Continue that draft',
  'expert.draft.discardIt': 'Discard it',
  'expert.draft.restored': 'Draft restored. It lives in this browser only and publishes nothing by itself.',
  'expert.draft.restoredSaved': 'Draft restored · saved {ago}. It lives in this browser only and publishes nothing by itself.',
  'expert.draft.startAgain': 'Start again',

  // ─── choosing a match ───────────────────────────────────────────────────────────────────
  'expert.selection.intro': 'Pick the fixture you want to publish a view on. Your prediction goes live as soon as you press publish — there is no approval step and nothing to wait for.',
  'expert.selection.fixturesHeading': 'Fixtures',
  'expert.selection.fixturesHint': 'Filter by day, competition or team. Finished, postponed and cancelled fixtures are left out.',
  'expert.selection.howHeading': 'How a prediction reaches readers',
  'expert.selection.how1': 'Choose the fixture here.',
  'expert.selection.how2': 'Enter your percentages — type {typed} for {whole}, not {decimal} — and tick only the markets you want to publish.',
  'expert.selection.how3': 'Preview what readers will see, then publish.',
  'expert.selection.howNote': 'Expert predictions are shown separately from model forecasts and are never merged with them. A market you leave out is shown as unavailable rather than as 0%. The fixture list covers the configured competitions only.',

  /*
   * ─── the fixture picker on the match-selection page ────────────────────────────────────
   *
   * EVERY ENGLISH VALUE BELOW IS THE STRING THAT SCREEN ALREADY SHOWED, character for
   * character, lifted out of `components/expert/FixturePicker.tsx` where it was a literal in
   * the component source. Nothing is reworded on the way in — including two forms that are
   * imperfect English and stay imperfect here, because fixing them is a copy change and this
   * is a translation change:
   *
   *   - `expert.picker.showing` reads "Showing 1 of 1 fixtures on this day." at one. The
   *     English wants "fixture" there and this does not give it one; an ICU plural would, and
   *     `every message with a plural is in the table above` in
   *     frontend/e2e/mocked/localisation.spec.ts — a file this package does not own — fails on
   *     any French plural not registered in ITS table, so adding one on the English side alone
   *     would leave the two languages built differently for no gain. The French avoids the
   *     problem instead of papering over it: it attaches no noun to either figure, so it is
   *     right at every count, and both are rendered at 0, 1, 2 and 11 in
   *     frontend/e2e/mocked/expert-localisation.spec.ts.
   *   - `expert.picker.dayLabel` is "Match day", which in football usually means a ROUND. Here
   *     it labels a calendar date. The French says what the control does rather than repeating
   *     the ambiguity; see the note on that key in ./expert.fr.ts.
   *
   * WHAT IS NOT DECLARED HERE, BECAUSE IT ALREADY EXISTS. The picker's "Today", "Tomorrow",
   * "Live", "No forecast held" and "Try again" are `matchday.relative.today`,
   * `matchday.relative.tomorrow`, `fixture.live`, `brief.noForecastHeld` and `expert.retry` —
   * identical English, already translated, and the page renders those keys rather than adding
   * five duplicates that could drift apart.
   */
  'expert.picker.dayLabel': 'Match day',
  /** The third day chip. "Today" and "Tomorrow" are `matchday.relative.*`. */
  'expert.picker.dayAfterTomorrow': 'In two days',
  /** The search field's label. Visually hidden; a screen reader is the only thing that reads it. */
  'expert.picker.searchLabel': 'Filter by team or competition',
  'expert.picker.searchPlaceholder': 'Team or competition',
  /** The accessible name of the competition chip strip. */
  'expert.picker.competitionGroup': 'Filter by competition',
  'expert.picker.onlyWithoutExpert': 'Only fixtures with no expert prediction yet',
  'expert.picker.clearFilters': 'Clear filters',
  'expert.picker.loading': 'Loading fixtures…',
  /** Announced politely as the filters change. Both figures arrive already formatted. */
  'expert.picker.showing': 'Showing {shown} of {total} fixtures on this day.',
  'expert.picker.expertPublished': 'Expert prediction published',
  'expert.picker.modelForecastHeld': 'Model forecast held',
  /**
   * The accessible name of a fixture row, which is the whole row's only announcement.
   *
   * `{action}` is `expert.action.writePrediction`, and `e2e/live/expert-composer.spec.ts`
   * matches this English by "Write a prediction:" — so the English assembly is unchanged from
   * the literal template this replaces, down to the colon and the comma placement.
   * `{time}` is the kick-off in the reader's CHOSEN zone, formatted by ../index.ts.
   */
  'expert.picker.rowAction': '{action}: {home} versus {away}, {competition}, kick-off {time}',
  'expert.picker.loadFailed': 'The fixture list could not be loaded',
  'expert.picker.emptyFilteredTitle': 'No fixture matches these filters',
  'expert.picker.emptyFilteredBody': 'Widen the filters, or move to another day.',
  'expert.picker.emptyDayTitle': 'No fixtures to write about on this day',
  'expert.picker.emptyDayBody': 'Finished, postponed and cancelled fixtures are left out. Try another day.',
  /**
   * The chosen day, spelled out. NEW on this screen rather than lifted from it: the picker
   * showed the day only as a native date input and three relative chips, so a reader had no way
   * to see which calendar day — in WHICH zone — the kick-offs below belong to. `{date}` is
   * formatted by `formatIsoDate`, and the zone beside it is `matchday.timesIn`.
   */
  'expert.picker.dayShown': 'Fixtures for {date}',

  // ─── the composer ───────────────────────────────────────────────────────────────────────
  'expert.compose.title': 'Write a prediction',
  'expert.compose.chooseIntro': 'Start by choosing the fixture. Publication is immediate once you press publish — there is no approval step.',
  'expert.compose.chooseFixture': 'Choose a fixture',
  'expert.compose.filterHint': 'Filter by day, competition or team name.',
  'expert.compose.advancedPaste': 'Advanced: paste a match id',
  'expert.compose.advancedPasteHint': 'Only needed when you already have an internal match id or a provider fixture id to hand. The list above is the normal way in.',
  'expert.compose.matchIdLabel': 'Match id',
  'expert.compose.matchIdPlaceholder': 'Internal match id or provider fixture id',
  'expert.compose.useThisId': 'Use this id',
  'expert.compose.loadingFixture': 'Loading the fixture…',
  'expert.compose.changeFixture': 'Change fixture',
  'expert.compose.fixtureNotFound': 'That fixture could not be found. Choose one from the list instead.',
  'expert.compose.fixtureLoadFailed': 'The fixture could not be loaded.',
  'expert.compose.fixtureNotOpened': 'That fixture could not be opened',
  'expert.compose.chooseFromList': 'Choose from the list',
  'expert.compose.yourView': 'Your view',
  'expert.compose.percentNote': 'Enter percentages, not decimals — type {typed} for {whole}. Only the markets you tick are published; the rest stay unavailable.',
  'expert.compose.fixThenPreview': 'Fix the fields marked above, then preview.',
  /** A statement of fact about what the button does, and it stays one in every language. */
  'expert.compose.publishImmediate': 'Publishing makes this public immediately.',
  'expert.compose.publishFailed': 'The prediction could not be published.',
  'expert.compose.advancedIds': 'Advanced: fixture identifiers',
  'expert.compose.internalMatchId': 'Internal match id:',
  /** `{provider}` is the provider's own name, never translated. */
  'expert.compose.providerId': '{provider}:',

  'expert.published.title': 'Published',
  'expert.published.body': 'Your prediction is on the public match page now. Nothing is waiting for approval — experts publish directly. You can edit or remove it at any time from My predictions.',
  'expert.published.viewMatch': 'View the match page',
  'expert.published.writeAnother': 'Write another',

  // ─── my predictions ─────────────────────────────────────────────────────────────────────
  'expert.mine.title': 'My Predictions',
  'expert.mine.intro': 'View and manage all your expert predictions',
  'expert.mine.loading': 'Loading predictions...',
  'expert.mine.loadFailed': 'Failed to load predictions',
  'expert.mine.updateFailed': 'Failed to update prediction',
  'expert.mine.confirmDelete': 'Are you sure you want to delete this prediction? This action cannot be undone.',
  'expert.mine.filterByStatus': 'Filter by Status:',
  'expert.mine.listHeading': 'Your Predictions ({count})',
  'expert.mine.emptyTitle': 'No predictions found',
  'expert.mine.emptyNone': "You haven't created any predictions yet.",
  'expert.mine.emptyFiltered': 'No predictions with status "{status}".',
  'expert.mine.createFirst': 'Create Your First Prediction',
  'expert.mine.matchIdLabel': 'Match ID:',
  'expert.mine.created': 'Created: {timestamp}',
  'expert.mine.published': 'Published: {timestamp}',
  'expert.mine.editNote': 'Percentages, not decimals — type {typed} for {whole}. Saving keeps this prediction published and preserves the version you are replacing, so readers can still see the view you published before.',
  'expert.mine.fixThenSave': 'Fix the fields marked above, then save.',
  'expert.mine.matchOutcome': 'Match Outcome',
  'expert.mine.homeWin': 'Home Win',
  'expert.mine.draw': 'Draw',
  'expert.mine.awayWin': 'Away Win',
  'expert.mine.bttsLong': 'Both Teams to Score (BTTS)',
  'expert.mine.marketConfidence': '{value} confidence',
  'expert.mine.yes': 'Yes',
  'expert.mine.no': 'No',
  'expert.mine.totalGoals': 'Total Goals',
  'expert.mine.superseded': 'This prediction has been superseded by a newer version',

  // ─── the moderation list ────────────────────────────────────────────────────────────────
  'expert.queue.title': 'Moderation Queue',
  'expert.queue.intro': 'Predictions flagged for a moderator to look at — after they were published.',
  'expert.queue.loading': 'Loading moderation queue...',
  'expert.queue.loadFailed': 'Failed to load the moderation queue',
  'expert.queue.approveFailed': 'Failed to approve prediction',
  'expert.queue.rejectFailed': 'Failed to reject prediction',
  'expert.queue.withdrawPrompt': 'Enter reason for withdrawing this prediction (optional):',
  'expert.queue.noticeTitle': 'Publishing does not wait for this queue.',
  'expert.queue.noticeBody': 'Experts publish directly: a prediction is live on the public match pages as soon as its author publishes it, whether or not it ever appears here. Approving records that a moderator has checked it; rejecting withdraws a prediction that is already public.',
  'expert.queue.heading': 'Flagged for moderation',
  'expert.queue.listHeading': 'Flagged for moderation ({count})',
  'expert.queue.listNote': 'These are already visible to readers. Nothing here is waiting for permission to go live.',
  'expert.queue.emptyTitle': 'Nothing waiting for moderation',
  'expert.queue.emptyBody': 'Every flagged prediction has been dealt with. Experts’ predictions publish immediately either way, so an empty queue does not hold anything back.',
  'expert.queue.createdByAt': 'Created by: {who} • {timestamp}',
  'expert.queue.markChecked': 'Mark as checked',
  'expert.queue.markCheckedHint': 'Records that a moderator has checked this prediction. It is already public.',
  'expert.queue.withdraw': 'Withdraw',
  'expert.queue.withdrawHint': 'Withdraws a prediction that is already visible to readers.',
} as const

export default expert
