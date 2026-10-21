# Experts' public names: a decision for the owner

Status: **proposal for the owner's decision. Nothing in this document is built.**

This decision is separate from the expert-fixes bug fixes. Those fixes are complete and none of
them depends on this one (see `docs/evidence/expert-fixes-2026-10-20/HANDOFF.md`, "Limitations
and decisions for the owner", item 1). This document refines section 4 of
`docs/design/public-expert-profile-proposal.md` with what the code and the isolated database show.

## 1. The question

Public pages name an expert by their username, and a username can be copied from the person's
email address. Should a public byline show only a name the person has agreed to show? If so, what
is the smallest way to do that, and what happens to existing accounts?

## 2. What the code does today

### 2.1 Where a username comes from

| Path | What it stores as the username |
|---|---|
| `POST /api/v1/auth/register` with `username` | The supplied value, as sent. It must be 3–50 characters and is not stripped. |
| `POST /api/v1/auth/register` without `username` (absent or null) | The email's local part: `register_data.email.split('@')[0]` (`register` in `backend/app/api/v1/endpoints/auth.py`). |
| `backend/create_expert_user.py` | Always the email's local part. The script has no username option. |
| Web sign-up form (`frontend/src/pages/RegisterPage.tsx`) | The form has a required Username field and always sends it. That has been true since the form was connected to the API (commit `736ab2d9`). |
| `PUT /api/v1/users/me` | A new username: stripped, 3–50 characters, 409 if another account has it. |

How the generation rule works:

- **Email normalisation.** `EmailStr` (pydantic 2.5, email-validator 2.1) normalises the email
  first. It removes surrounding whitespace and lower-cases the domain. The local part keeps its
  case, its dots and any `+tag`.
- **The username.** The username is the text before the `@`, exactly as normalised. Nothing is
  lower-cased, nothing is cut to 50 characters, and no numeric suffix is added.
- **Length.** The 3–50 check applies only to a username the person supplies, so a generated one
  can be 1 or 2 characters long. A local part longer than 50 characters makes the insert fail.
- **Collisions.** Nothing retries a username that is already taken. A clash fails the insert with
  an unhandled unique-constraint error (HTTP 500), and a chosen username clashes the same way. So
  the rule never produces "local part plus digits".
- **Email never changes.** No code path writes `users.email` after registration, so the local part
  of the stored email is exactly what the rule used.

### 2.2 The database does not record whether a username was chosen or generated

- **No column.** `users.users` stores `username VARCHAR(50) NOT NULL UNIQUE` and nothing next to
  it: no flag for where the name came from and no confirmation time. The isolated database's
  `information_schema` confirms this.
- **No log.** Registration writes no log row. Nothing in the application writes
  `users.user_activity_log` or `audit.user_action_log`. `audit.audit_log` is written only for
  predictions (`backend/app/services/prediction_audit.py`).
- **No history.** Changing the username keeps no record of the old value. `updated_at` changes on
  every profile save, not only on a username change.

So the only way to guess is to compare the username with the email's local part, and that proves
nothing in either direction:

- equality does not prove generation, because a person may type their own local part on purpose;
- a mismatch does not prove the person agreed to be shown, because nobody was told the username is
  public, and a generated name may have been changed to another real name.

### 2.3 Where the username is public

1. **Match payloads.** These carry `author: {id, username}` (`_public_authors` in
   `backend/app/api/v1/endpoints/matches.py`), shown as "By {name}" on the match page and in the
   revision history. The frontend shows "Expert" instead of a blank name or one containing `@`
   (`publicExpertName` in `frontend/src/utils/predictionLabels.ts`).
2. **`GET /api/v1/performance/sources`.** An expert's `source_label` is their username, or
   "unknown expert" when it is blank (`measure_sources` in `backend/app/services/settlement.py`).
   `frontend/src/components/ui/MeasuredRecord.tsx` shows it as a heading without the `@` check.

Signed-in views are not public, and this decision does not change them: the expert's own
dashboard (`expert_name`), `user_details.username` in expert and admin views, and the admin user
lists.

## 3. What the isolated database holds

Counted on `soccer_predictions_e2e`, the isolated test database, on 2026-10-21. The query ran in a
read-only transaction (`transaction_read_only = on`), used only SELECT and ended with ROLLBACK. It
printed only counts; the query is in the appendix. **The live database was not queried.** These
figures describe test accounts and say nothing about live.

| Measure | Count |
|---|---|
| Accounts | 4 (none soft-deleted) |
| Experts / regular / admin | 3 / 1 / 0 |
| Usernames with the prefix the QA suites use | 3 of 4 |
| Experts who have published an expert prediction at some time | 2 |
| Experts with an expert prediction public now | 0 (the QA predictions are soft-deleted) |
| Experts with no expert predictions | 1 |
| Username exactly equal to the email's local part (what the rule writes) | 0 |
| Equal ignoring case and surrounding whitespace | 0 |
| Local part followed by digits, or by `.`, `_` or `-` and digits | 0 |
| Local part without its `+tag` | 0 |
| Username containing `@` | 0 |
| Username shorter than 3 characters, or with surrounding whitespace | 0 |
| `users.user_activity_log` / `audit.user_action_log` rows | 0 / 0 |
| `audit.audit_log` rows about users | 0 (all 1,528 rows are about predictions) |

Broken down by role and publication, every account falls in "no match": 1 expert with no expert
predictions, 2 experts who published before but have nothing public now, and 1 regular account
with no expert predictions. With no matches there are no masked examples to give. A match would be
reported only by its shape, for example "letters+digits, 9–16 characters, lower case only, equals
the local part".

The live-isolated suites register their accounts with an explicit username
(`frontend/e2e/support/qa-account.ts`, `frontend/e2e/live-isolated/account-profile.spec.ts`), so
these zeros are expected. To size the change on live, the owner can approve one read-only run of
the appendix query on the live database. It prints counts only.

## 4. Options

| Option | New sign-ups | Existing accounts | Cost |
|---|---|---|---|
| **A. Require a username at registration** (the profile proposal's choice) | No more generated names | Cannot be fixed: the database cannot say which names were generated, so asking "experts whose username equals their local part" relies on a guess | Small |
| **B. A confirmed username** (recommended) | The person types the name on a form that says it is public | "Expert" until the account holder confirms, with a prompt that never blocks | One nullable column, two public serializers, one toggle, one notice |
| **C. A separate optional public name** | A second name to choose | Every byline reads "Expert" until a public name is set | New column, uniqueness and validation for a second name, more UI. It duplicates what the username already does |
| **D. Keep the current behaviour** | Generated names stay possible | Generated names stay public | Record it in `docs/known-limitations.md` |

## 5. Recommendation: B, a confirmed username, plus A

The username stays the only public handle. It is shown publicly only after the account holder has
confirmed that it may be. Until then every public surface shows the neutral label "Expert", which
the byline already falls back to. Registration stops generating names.

### 5.1 Database

- **The column.** One nullable column, `users.users.username_confirmed_at TIMESTAMP NULL`. Null
  means the name is not shown publicly. No index is needed.
- **The migration.** It adds the column and does **not** backfill it (section 6). The downgrade
  drops it.

### 5.2 API

- **`POST /auth/register`.**
  - `username` becomes required: stripped, 3–50 characters, never blank and never containing `@`.
  - A username that is already taken returns 409 "Username already taken", as the profile endpoint
    does, instead of today's 500.
  - The form now says the name is public, so a successful sign-up sets `username_confirmed_at`.
- **`GET /users/me`.** It adds `username_confirmed` (boolean).
- **`PUT /users/me`.** It accepts an optional `username_confirmed`:
  - `true` sets the time if it is not already set, and `false` clears it;
  - changing `username` sets the time to now, unless the same request sends `false`;
  - no other field changes it.
- **Match payloads (`_public_authors`).** They select `username_confirmed_at` as well and serve
  `author.username` only when it is set, and `null` otherwise. The key keeps its name to avoid
  churn; it now means "the public name, or null". The frontend already shows "Expert" for null.
- **`GET /performance/sources` (`measure_sources`).** An expert without a confirmed name gets
  `source_label: null` instead of the English string "unknown expert".
- **`backend/create_expert_user.py`.** It takes the username as an argument and never generates
  one. The operator chooses that name, not the expert, so it stays unconfirmed until the expert
  confirms it.

### 5.3 UI

- **Sign-up.** One hint line under Username, in English and French: "Shown publicly on predictions
  you publish as an expert."
- **Profile, experts only.**
  - The same hint appears under Username.
  - A checkbox, "Show my username on my published predictions", is bound to
    `username_confirmed`.
  - The form keeps sending only the keys that changed.
- **Expert dashboard and composer.** An unconfirmed expert sees a notice they can dismiss:
  "Your published predictions show 'Expert' as the author. Show your username instead?"
  - **Show my username** sends one `PUT {username_confirmed: true}`.
  - **Change it** opens the profile editor.
  - **Not now** hides the notice in this browser.
  - Publishing, editing and unpublishing are never blocked or delayed.
- **`MeasuredRecord`.** A null `source_label` shows the localised "Expert".
- **The `@` guard.** `publicExpertName` stays as a second line of defence.

### 5.4 What stays the same

- Sign-in is by email.
- Usernames stay unique.
- Experts publish directly, with no approval step.
- Email, first and last name and avatar are never served on a public payload.
- Signed-in views keep showing the username to its owner and to admins.

## 6. Existing accounts

**Recommended: no backfill.**

- **After the migration.** Every existing account is unconfirmed, so existing bylines and
  performance labels read "Expert" until the expert confirms.
- **Publishing.** Direct publishing carries on unchanged.
- **The prompt.** The notice in section 5.3 never blocks anything, and one click restores the
  name.
- **Regular accounts.** Nothing public shows them, so they are unaffected.

**Alternative, for the owner to choose instead: a guessed backfill.** The migration would confirm
every account whose username does not resemble the email's local part. This is not recommended:

- it relies on a comparison that proves nothing (section 2.2);
- nobody was ever told the username is public;
- the migration would have to read email addresses.

**What the recommendation costs.**

- **Existing experts.** They lose their name on public pages until they click once.
- **The QA expert on the isolated pair.** It was registered before the column existed, so its setup
  (`frontend/e2e/support/qa-account.ts`) must confirm the name. Otherwise the byline assertions in
  `frontend/e2e/live-isolated/expert-journey.spec.ts` will read "Expert".

Names that were already public cannot be withdrawn from caches, screenshots or search engines.
This change governs what is shown from the moment it is deployed.

## 7. Tests, if approved

- **Backend, on the test database.**
  - Register without a username returns 422, and with a taken one returns 409.
  - A successful sign-up is confirmed.
  - An unconfirmed author is served as `null` on match payloads and as a `null` label on
    `/performance/sources`; a confirmed one is served by name.
  - `PUT /users/me` with `username_confirmed` true or false, and with a changed username.
  - Email, names and avatar never appear on public payloads (the existing check).
  - The migration upgrades and downgrades.
- **Mocked Playwright.**
  - The notice appears only for an unconfirmed expert and never blocks publishing.
  - Confirming sends exactly one PUT.
  - The byline and the performance heading read "Expert" before confirmation and the name after.
- **Live-isolated Playwright** (on the isolated pair at :8001 with `soccer_predictions_e2e`). The QA
  expert's public byline reads "Expert" before confirmation and "By {name}" after it.

## 8. Out of scope

- A separate display name or a generated handle (options C and D of the profile proposal).
- Case-insensitive uniqueness, reserved names and impersonation rules. Today "Name" and "name" can
  both exist.
- Any review or approval of names by an administrator.
- Renaming, rewriting or backfilling existing usernames.
- An email-change flow.
- The public expert profile page (`docs/design/public-expert-profile-proposal.md`).
- Removing names already exposed outside the application.
- A related private-view bug, to be fixed separately. The frontend builds the signed-in user's
  `username` from the email's local part (`mapBackendUserToFrontend` in
  `frontend/src/types/auth.ts`) instead of reading the stored username. That value appears only in
  the dashboard greeting fallback and in the personal data export's `account.username`.

## 9. Decisions for the owner

1. **The approach.** Recommended: **B with A**. The alternatives are A alone, C or D.
2. **Existing accounts.** Recommended: **no backfill**, with the non-blocking notice. The
   alternative is the guessed backfill.
3. **The performance-page label.** Recommended: "Expert" for unconfirmed experts. The alternative
   is to keep "unknown expert".
4. **Measuring live first (optional).** Whether to approve one read-only, counts-only run of the
   appendix query on the live database before deciding item 2.

## Appendix: the count query

The query is read-only and prints counts only. It never selects an email, a local part, a username
or a name.

```sql
BEGIN TRANSACTION READ ONLY;
SELECT current_database(), current_setting('transaction_read_only');

WITH u AS (
  SELECT id, user_type::text AS role, deleted_at IS NOT NULL AS user_deleted,
         username AS un, split_part(email, '@', 1) AS lp
  FROM users.users
), pub AS (
  SELECT created_by,
         bool_or(status::text = 'PUBLISHED' AND deleted_at IS NULL) AS public_now,
         bool_or(published_at IS NOT NULL) AS ever_published
  FROM predictions.predictions
  WHERE source::text IN ('EXPERT_MANUAL', 'EXPERT_OVERRIDE')
  GROUP BY created_by
), c AS (
  SELECT u.*,
    CASE
      WHEN un = lp THEN '1 exact'
      WHEN lower(btrim(un)) = lower(lp) THEN '2 case/space-insensitive'
      WHEN length(lp) > 0 AND left(lower(un), length(lp)) = lower(lp)
           AND substr(lower(un), length(lp) + 1) ~ '^[0-9]+$' THEN '3 local part + digits'
      WHEN length(lp) > 0 AND left(lower(un), length(lp)) = lower(lp)
           AND substr(lower(un), length(lp) + 1) ~ '^[._-][0-9]+$' THEN '4 local part + sep + digits'
      WHEN position('+' in lp) > 0 AND lower(un) = lower(split_part(lp, '+', 1)) THEN '5 without +tag'
      WHEN position('@' in un) > 0 THEN '6 contains @'
      ELSE '7 no match'
    END AS cls,
    CASE WHEN pub.public_now THEN 'public now'
         WHEN pub.ever_published THEN 'published before, not now'
         WHEN pub.created_by IS NOT NULL THEN 'expert rows, never published'
         ELSE 'no expert rows' END AS publication
  FROM u LEFT JOIN pub ON pub.created_by = u.id
)
SELECT cls, role, user_deleted, publication, count(*) FROM c GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;

SELECT count(*) AS all_users,
       count(*) FILTER (WHERE user_type::text = 'EXPERT') AS experts,
       count(*) FILTER (WHERE length(username) < 3) AS shorter_than_3,
       count(*) FILTER (WHERE username <> btrim(username)) AS surrounding_whitespace
FROM users.users;

ROLLBACK;
```

The run on the isolated database printed only the counts in section 3.
