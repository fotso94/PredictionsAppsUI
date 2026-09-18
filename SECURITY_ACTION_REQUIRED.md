# One thing needs you, not me

**Your API-Football key is published on the internet right now, and it is the same key your local
setup is still using.**

I found this while checking a claim in the independent review. I verified it by fingerprint and never
printed the value.

## What is exposed

| | |
|---|---|
| Where | `http://soccer-predictions-app-7787.s3-website-us-east-1.amazonaws.com/assets/index-48183f90.js` |
| What | The API-Football key, sitting next to the `x-apisports-key` header name |
| Also published | The matching `.js.map` source map, which exposes the old prototype's full source |
| Still in use? | Yes. It matches `API_FOOTBALL_KEY` in both `backend/.env` and `frontend/.env` |
| Since | The bundle was last modified 8 October 2025, so assume roughly a year of exposure |

Anyone who finds that file can spend your API-Football quota. The practical damage is limited,
because API-Football is only a retained fallback and its free plan will not serve the current season
anyway, but the key is yours and it is readable by anyone.

**Your other credentials are not exposed.** I checked each one against the published bundle: the Live
Score API key and secret, the GameForecastAPI key and the application's signing secret are all
absent. The Phase 1 work keeps them server-side, and that held.

## What to do

Two steps, both yours, neither of which I can or should do for you.

1. **Rotate the API-Football key.** Sign in at [dashboard.api-football.com](https://dashboard.api-football.com),
   regenerate it, then put the new value in `backend/.env` and `frontend/.env` and restart the
   backend. Nothing else reads it.
2. **Decide what happens to the old site.** It is a prototype from October 2025 that still shows
   invented accuracy figures, and its deep links are broken. Either take the bucket down or replace
   it with a current build. Until then, rotating the key leaves a dead key on a stale page, which is
   the safe end state.

I did not rotate the key, change the bucket, or touch anything in AWS. Rotation needs your
API-Football account, and removing a public site is your call, not mine.

## What I did fix

While confirming the above I found and closed a related hole: **the public registration endpoint
accepted `role=admin`**. It is unauthenticated and returns a signed token, so anyone who could reach
the API could create an administrator and be logged in as one in the same request. I reproduced it
against the running local backend, got HTTP 201 and a token whose role claim was `admin`, then fixed
it. Only `regular` and `expert` are self-selectable now.

No administrator account exists in your local database, so nothing was created through that hole
here. If the API was ever reachable from outside this machine, check for administrators you do not
recognise:

```bash
cd backend && ./venv/bin/python scripts/grant_admin.py --list
```

That script is also how you now create the first administrator, since the endpoint no longer hands
them out. It needs database access, which is the point.

```bash
cd backend && ./venv/bin/python scripts/grant_admin.py --email you@example.com
```
