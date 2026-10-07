# Test reports

Each directory here is one run of `scripts/test_evidence.py`. It holds the reports for the backend
suite and the four Playwright projects, scrubbed so they can sit in this public repository. Anyone
with the directory and any Python 3.9 or later can recompute every total in it.

Earlier test totals were stated without reports, because Playwright empties its output directory on
every run and nothing else was kept. Nobody could check those numbers afterwards. These directories
exist so that every total stated from now on can be checked.

## Making a run

From the repository root, at a quiet time with no other test run on the machine:

```
backend/venv311/bin/python scripts/test_evidence.py run --dry-run   # preflight and planned counts only
backend/venv311/bin/python scripts/test_evidence.py run
```

`npm run e2e:evidence` in `frontend/` runs the same command.

The runner refuses to start in these cases, and prints every reason at once:

- the working tree is dirty. `--allow-dirty` runs anyway, and records the changed path names and
  the SHA-256 of `git diff HEAD`;
- another test run is active anywhere on the machine;
- a server under test is missing or serves another commit;
- the backend process started before its newest code change;
- the backend test database or Redis does not answer. The database-backed tests would then skip,
  and the run would still exit green.

Once started, the runner checks the machine every 15 seconds. A test run started elsewhere, a
server restart, a new commit or a changed file marks the run **CONTAMINATED**.

A run with `--suites` set to a subset, or with `--grep`, is published as **PARTIAL - NOT
EVIDENCE**. Its directory name ends in `-partial`.

The runner never stages, commits or pushes anything. It prints the directory it wrote. Read
`summary.md` before committing it.

## Layout

```
docs/evidence/test-reports/<UTC yyyy-mm-ddTHHMMZ>-<short sha>[-dirty][-partial]/
  summary.md                                  human summary, rendered from summary.json
  summary.json                                every figure, check and verdict, machine-readable
  backend.junit.xml                           pytest's JUnit (xunit2), scrubbed
  playwright-<project>.junit.xml              one per project: mocked-desktop, mocked-mobile,
                                              mocked-mobile-360, live
  backend.console-tail.txt                    last 80 console lines, including pytest's -rfEs summary
  playwright-<project>.console-tail.txt       last 40 console lines, including the reporter's summary
  SHA256SUMS                                  checksums of every file above
```

Console tails end in `.txt` because the repository ignores `*.log`. A tail is longer than 80 or 40
lines when the reporter's final summary starts earlier. With many failures, Playwright names each
one under "N failed". `verify` reads the summary back from the tail, so the tail always holds all
of it.

These files stay in the gitignored `.test-runs/<run-id>/` on the machine that ran the suites:

- the full Playwright JSON reports;
- traces, screenshots and error-context files;
- the full console logs;
- `preflight.json`;
- `summary.local.json` (unscrubbed).

`summary.json` records the SHA-256 of each raw file a published file was made from. The owner of
`.test-runs/` can therefore show that a published file came from a raw file they still hold.

## Verifying a directory

```
python3 scripts/test_evidence.py verify docs/evidence/test-reports/<run-id>
```

`verify` takes nothing in `summary.json` on trust that it can work out again. It exits 0 only if
all of these checks pass:

- every file matches `SHA256SUMS`, and no file is missing from it or unlisted. Every report
  belongs to a suite that `summary.json` lists, and `summary.json` records the report's SHA-256;
- every JUnit total, recomputed from the testcases in the committed XML, equals what
  `summary.json` records. It must also agree with the reporter's own buckets:
  - **Playwright:** JUnit tests = planned; failures + errors = failed;
    skipped = skipped + did not run + interrupted; passed = passed + flaky.
  - **pytest:** failed, errors, skipped and xfailed match one for one; passed = passed + xpassed.
- each reporter's own summary, read back from the committed console tail, is the one
  `summary.json` quotes, and the buckets are that summary's:
  - **pytest:** the final "N passed in Xs" line;
  - **Playwright:** the bucket lines, the errors outside tests, and the planned count when the tail
    shows it.
- every post-check is made again from those figures and the recorded exit code, and must come out
  as recorded. No recorded check may be missing or extra. This includes "exit code agrees with
  the results", so changing a failing suite's exit code to 0 does not verify;
- whether the run was partial is worked out three ways, and all must agree with `summary.json`:
  - the suites listed, which must be known, each listed once, in the order they run;
  - each suite's command, which must be exactly the one the runner builds, apart from paths. A
    `-k` or `--grep` in it means the run was filtered;
  - the run id, which ends in `-partial` exactly when the run is partial.

  A full run must also have deselected no backend test. Dropping a suite, or relabelling a
  filtered run as a full one, therefore does not verify;
- a suite that was interrupted or never started means the run is recorded as interrupted;
- each suite's verdict follows from its checks, and the overall verdict follows from the suites,
  the partial flag and the watcher;
- `summary.md` is exactly what `summary.json` renders to.

`shasum -a 256 -c SHA256SUMS` inside the directory checks the checksums alone.

`verify` makes every check with its own code. `summary.json` records the SHA-256 of the runner
that made the run. When that differs from the runner doing the check, `verify` prints a note. If a
check then fails on a run that looks honest, verify again with the runner from the run's own
commit: `git show <head_at_start>:scripts/test_evidence.py`.

## What the checks mean

Playwright's JSON statistics and its JUnit file count tests that were interrupted, or never started,
as **skipped**. Its human summary counts them separately. So an interrupted run can look like
"2 skipped" in JUnit. The runner sorts every test into the human summary's buckets, using the same
rules as Playwright's own reporter:

- **interrupted:** any result was interrupted;
- **did not run:** the test has no result, or its expected status is not "skipped";
- **skipped:** every other skipped test.

It then requires the human summary, the JSON and the JUnit to agree. A disagreement makes the run
**NOT EVIDENCE**, as does a backend skip whose reason says the database or Redis was "not reachable".

The verdicts:

| Verdict | Meaning |
|---|---|
| PASS | every suite exited 0 and every cross-check agreed |
| FAIL | tests failed, and the reports agree about which ones |
| NOT EVIDENCE | a report is missing or disagrees, a suite did not run, the run was interrupted, or the run was partial |
| CONTAMINATED | the watcher saw another test runner, a server restart, a new HEAD or a changed file during the run |

Live skips depend on the day's data and on the providers. For example, `parlay-journey` needs two
upcoming fixtures with a stored forecast. The backend section of `summary.md` therefore records a
minimal provider-status snapshot: for each provider, its integration status, last success, last
error time and an error kind such as `http_401`. It never records the error text, which can quote a
request URL carrying a key. Compare live totals between runs only together with their skip reasons.

## Scrub policy

Every published file goes through the same deterministic rules. `summary.json` records how many
substitutions each rule made in each file.

| Rule | What it does |
|---|---|
| ansi | removes terminal colour codes |
| repo-root | replaces the repository root and every worktree root with `<repo>` |
| home | replaces the home directory with `~` |
| pytest-hostname | replaces the machine name in pytest's `testsuite@hostname` with `<redacted>` (Playwright puts the project name there, which is kept) |
| bearer-header | replaces the token after `authorization: Bearer` with `<redacted>` |
| jwt | replaces anything shaped like a JWT with `<jwt>` |
| url-credentials | replaces the password in a `postgres…://` or `redis://` URL with `<redacted>` |
| query-secret | replaces the value of `key`, `secret`, `api_key`, `apikey`, `token` and `access_token` query parameters with `<redacted>` |

In XML files the replacements are written escaped (`&lt;repo&gt;`), so the files stay well-formed
and read `<repo>` when parsed.

**Publishing stops and writes nothing** in any of these cases:

- an absolute `/Users/` path survives the scrub;
- an email address appears whose domain is not `example.com` or `predictions-local.dev`;
- after scrubbing, a file contains any value from the deny-list. The deny-list is built from:
  - `backend/.env` and `frontend/.env`: `SECRET_KEY`, `POSTGRES_PASSWORD`, the SMTP and superuser
    settings, and every `*_KEY`, `*_SECRET`, `*_PASSWORD` and `*_TOKEN`;
  - `E2E_QA_PASSWORD` and `E2E_QA_EMAIL`, when set;
  - the QA account's committed fallback password;
  - the git user's email address;
  - the machine name.

The deny-list values are read into memory only. Messages name the file, the line and the variable,
never the value.

Values shorter than six characters would match ordinary words, so they are not scanned. Their
names are listed in `summary.json`, so the gap is visible.

Traces, screenshots, the HTML report and the full JSON are never published. Traces hold the QA
password and bearer tokens. The full JSON can carry storage dumps and base64 attachments.

## Known gaps

- `verify` cannot see what only the run itself saw. Deleting the watcher's anomalies from a
  CONTAMINATED run, or editing the server identities or the provider snapshot, still verifies. It
  also cannot detect a consistent rewrite of a suite's JUnit file, its console tail and its entries
  in `summary.json` together. `summary.json` records the SHA-256 of each raw file a published file
  came from. Only the owner of `.test-runs/` can check those hashes against the raw files.
- A suite's exit code appears in no published report, so `verify` cannot check the number itself.
  It checks that the code agrees with the results: 0 exactly when nothing failed and at least one
  test ran.
- pytest writes its `testsuite@timestamp` in local time with no time zone. `summary.json` carries
  each suite's start and end in UTC.
- No endpoint reports the commit the backend is running. The runner infers it from the process
  start time, the newest `app/**/*.py` change and the git state of the process's working directory.
- The Playwright projects test whatever the Vite server on `:3100` serves. That is a working tree
  that reloads on save, so the watcher's working-tree check is what ties a run to one state of
  the files.
