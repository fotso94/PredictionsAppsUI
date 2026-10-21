# Public expert profile: the smallest version (proposal)

Status: proposal only. Nothing in this document is built. It needs the owner's decision on the
privacy question in section 4 before any of it is built.

Context: the expert-fixes round (brief item P2-8) names each public expert prediction by its
author's username (`author: {id, username}` on the match payloads) and says that a full public
expert profile, being new scope, should be written up as a separate proposal. This is that
proposal. It describes the smallest profile that is useful to a reader and adds no new kind of
data.

## 1. What a reader gets

A reader on a match page sees "By {username}" on an expert prediction. With a profile, that
byline becomes a link to `/experts/:id`. The page shows three things:

1. who the expert is, as far as the public is allowed to know: the username, and nothing else;
2. what they have published: their published predictions, newest first, each linked to its match;
3. how that has measured up: their measured record, the same figures `/performance/sources`
   already publishes for them.

## 2. Scope: one endpoint, one route, no migration

- **Backend:** `GET /api/v1/experts/{user_id}`, public and read-only. It answers 404 for an
  unknown id and for a user who is not an expert. It makes no provider request.
- **Frontend:** the route `/experts/:id`, linked from the existing byline on the match page. It is
  not added to the navigation.
- **Database:** no new table and no new column. Every field below is already stored.

## 3. Fields

| Field | Source | Notes |
|---|---|---|
| `id`, `username` | `users` | Selected column by column, as `_public_authors` (`backend/app/api/v1/endpoints/matches.py`) already does. A blank username is served as `null`, never replaced by anything else. |
| `predictions[]` | `predictions.predictions`: PUBLISHED, `deleted_at IS NULL`, `created_by = user_id` | Each item gives the match (teams, kickoff, status), `published_at`, `published_after_kickoff` and `withdrawn_before_kickoff`. Those two flags come from `serialize_expert_prediction`, which applies settlement's own rule, so the profile labels a not-scored row exactly as the match page does. Paged with `limit`/`offset` and `X-Total-Count`, as My Predictions is. |
| `record` | `settlement.measure_sources` (the data behind `GET /api/v1/performance/sources`), filtered to `source_type == "expert"` and `source_id == user_id` | The measured record comes only from here: eligible, scored, pending, void and refused counts, and per-market hit rate and Brier score, each with its sample size and its withheld-below-minimum reason. The default window is the same as `/performance/sources`. |

The profile serves **nothing else**. In particular it never serves:

- email, first name, last name, avatar URL or biography, unless a later opt-in is added (out of
  scope here);
- the `ExpertProfile` counters (`total_predictions`, `correct_predictions`, `accuracy_score`,
  `roi_percentage`, `reputation_score`, `follower_count`). Nothing in the application writes them,
  so they would show invented zeros. The measured record above is the only performance figure.

## 4. Decision needed from the owner: usernames taken from email addresses

When registration is given no username, it sets the username to the local part of the email
address (`backend/app/api/v1/endpoints/auth.py`, `register`: the text before the `@`). That
username is already public in two places: the byline on every public expert prediction and the
expert's label on `/performance/sources`. The frontend hides only a name that contains an `@`
(`publicExpertName` in `frontend/src/utils/predictionLabels.ts`). It cannot tell when a
username is an email local part, and a local part is often a person's real name.

A profile page would make that name more prominent, so the owner should pick one of these before
it ships:

- **A. Require an explicit username at registration.** Stop deriving it from the email, and ask
  existing experts whose username equals their email's local part to choose one. This is the
  smallest change that closes the gap.
- **B. Opt-in.** Show an expert's profile and byline only after they confirm the username to show.
  Until then, show the generic label the byline already falls back to (`source.expert`), and
  "unknown expert" on `/performance/sources`.
- **C. A generated public handle.** Serve a separate handle that is never derived from the email.
  This needs a new column and a migration, so it is no longer the smallest version.
- **D. Keep the current behaviour knowingly.** Record that decision in docs/known-limitations.md.

This proposal recommends **A**. It does not change what the byline shows today.

There is also a related setting. `UserPreference.profile_visibility` (`backend/app/models/users.py`,
default `"public"`) exists but nothing enforces it. The profile endpoint should either honour it
(`"private"` returns 404) or the proposal should say it is ignored. This proposal recommends
honouring it, since that is one comparison in the endpoint.

## 5. Out of scope

- Biography, expertise areas, avatar, follower counts, reputation, badges.
- Any approval workflow. Experts keep publishing directly, as the brief requires.
- Any change to the scoring rules, the settlement pass or how the measured record is computed.
- Backfilling or rewriting existing rows, including the username repair in option A beyond asking
  experts to choose one.
- Search, listing or ranking of experts (a leaderboard is a separate proposal).
- Notifications or following an expert.

## 6. How it would be tested

- Backend API tests on the test database:
  - a profile serves only `id` and `username` from `users`. Distinctive email, names and avatar
    strings must not appear in the response body, the same check
    `test_each_public_expert_prediction_names_its_author_by_username_only` already makes;
  - the predictions list excludes drafts, archived and deleted rows;
  - `record` equals that expert's entry in `measure_sources` for the same window;
  - a non-expert or unknown id answers 404, and a `"private"` profile_visibility answers 404 if
    that recommendation is accepted.
- Mocked Playwright: the byline links to the profile; a profile with no scored predictions shows
  the record's own withheld reason rather than a zero.
- Live-isolated Playwright on :8001 / soccer_predictions_e2e: the QA expert's profile lists the
  prediction it publishes, and no longer lists it once it is deleted.
