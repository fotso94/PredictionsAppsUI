# Market capability matrix

What this installation can serve as a selection, what it can only calculate, what it cannot
settle, and what it does not have at all — market family by market family, with the evidence.
Verified against the checkout and the stored data on 2026-09-25 (92 stored GameForecastAPI
events, 143 forecast snapshots, all prematch). The machine form of the same statement is served by
`GET /api/v1/suggestions/capabilities` (`app/services/markets.py::CAPABILITIES`).

Four products are kept apart throughout, because they are different things:

| Product | What it is | Where it comes from here |
| --- | --- | --- |
| Prediction probability | a model's published chance of an outcome | GameForecastAPI `predictions[]` (served) |
| Bookmaker odds | a price somebody will take a bet at | GameForecastAPI carries an unnamed `odds[]` 1X2 snapshot; the reader types their own bookmaker's prices; **no odds feed is configured** |
| Historical statistics | what happened in past matches | `match_results` (goals, half-time score; corner and card columns exist but the active provider does not fill them) |
| Expert opinion | a person's published view | the expert predictions, kept separate on the match page |

## What the stored payload actually carries

Every one of the 92 stored events has exactly one `predictions[]` entry with these blocks:
`match_result{home,draw,away}`, `total_goals{over/under 0.5, 1.5, 2.5, 3.5}`,
`home_team_goals` and `away_team_goals` (same four lines), `both_teams_score{yes,no}`,
`first_half_winner{home,draw,away}`, `team_to_score_first{home,away,neither}`, `exact_score`
(listed scorelines plus an `other` remainder), `recommended_bets` (references such as
`matchResult.homeWinProbability`) and `reasoning` in six languages. 86 of the 92 also carry one
`odds[]` entry, `match_winner` / `3_ways`, with decimal Home/Draw/Away prices and a `run_at` date;
no bookmaker is named. Codex's observation was correct on every field. "Occurs in the payload" is
not "usable": each block is validated per event (absent, all-zero placeholder, out-of-range value,
partial, or inconsistent sum), and only what passes is served as available.

## The matrix

Columns: **Provider / field** · **Documented** (publicly, by the provider) · **On our plan**
(the free tier we hold) · **Observed usable** (in the stored payloads, after validation) ·
**Competitions verified** · **Displayed & selectable** · **Settlement data held** · **Extra cost**.

| Market family | Provider / field | Documented | On our plan | Observed usable | Competitions verified | Displayed & selectable | Settlement data held | Extra cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full-time result (1X2) | GameForecast `match_result` | yes | yes | 92/92 | UEFA Nations League (51 forecasts), 5 domestic leagues (41), see note 1 | yes | regulation-time score (`match_results.home/away_score_ft`, fallback rule in `settlement.py`) | none |
| First-half result | GameForecast `first_half_winner` | yes | yes | 92/92 | same | yes, period `first_half` | half-time score (`home/away_score_ht`) — stored for Live Score results; unresolved when absent | none |
| Double chance | calculated from 1X2 | n/a | n/a | wherever 1X2 is complete and sums to 1 | same | yes, labelled *calculated from provider probabilities* with formula and inputs | regulation-time score | none |
| Draw no bet | calculated from 1X2 | n/a | n/a | same | same | yes, labelled calculated; void on a draw | regulation-time score | none |
| Match goal totals | GameForecast `total_goals` 0.5 / 1.5 / 2.5 / 3.5 | yes | yes | 92/92 | same | yes | regulation-time score | none |
| Team goal totals | GameForecast `home_team_goals`, `away_team_goals` 0.5–3.5 | yes | yes | 92/92 | same | yes | regulation-time score | none |
| Both teams to score | GameForecast `both_teams_score` | yes | yes | 92/92 | same | yes | regulation-time score | none |
| Clean sheet | — | no | no | — | — | **not offered as such**; "team under 0.5 goals" is the same event and is served under team totals | regulation-time score | none |
| Teams to score (either/both) | covered by BTTS and team over 0.5 | — | — | — | — | via those markets | regulation-time score | none |
| Exact score | GameForecast `exact_score` | yes | yes | 92/92 (listed scorelines; 0% entries dropped per adapter rule) | same | yes; the `other` remainder is shown as a line, never a selection | regulation-time score | none |
| Half-time / full-time | — | no source | no | — | — | **unavailable**; not derived by multiplying the first-half and full-time markets, which are not independent | both scores are stored, so settlement would be possible if a source published it | would need a provider that publishes it |
| First team to score | GameForecast `team_to_score_first` | yes | yes | 92/92 | same | displayed and selectable, marked **not tracked automatically** | needs the order of goals; no configured source records it. A 0-0 settles `neither` | none |
| Corners | — | GameForecast: no. Boggio: no. Sportmonks/FootyStats: statistics, not predictions (see research) | no | — | — | **unavailable** | `match_results.home/away_corners` exist but the active provider does not fill them | paid data; no prediction source found |
| Cards | — | as corners | no | — | — | **unavailable** | card columns exist, unfilled | paid data |
| Shots / shots on target | — | none of the four researched publish predictions for them | no | — | — | **unavailable** | none | paid data, statistics only |
| Fouls, penalties, player-specific | — | none | no | — | — | **unavailable** | none | none found within budget |

Note 1 — "competitions verified" means a stored forecast exists and its markets were built and
read on this installation: UEFA Nations League and the five domestic leagues (Premier League, La
Liga, Serie A, Bundesliga, Ligue 1). CONCACAF Nations League has fixtures stored but no forecast
yet; the Champions League has neither stored fixtures nor forecasts. Nothing is claimed for any
competition beyond those.

## Rules the served markets follow

* A probability is served only as the provider published it, or as arithmetic on a complete and
  consistent 1X2 with the formula kept on the selection. Nothing is derived from the truncated
  exact-score table.
* A block that is absent, all zeros, out of range, or partial is reported as such. A genuine 0%
  inside a distribution that sums to one is kept as 0%.
* A price appears only on the market-result selections the payload priced, dated with the
  payload's `run_at`, labelled as a provider snapshot with no bookmaker named. No other market's
  price is derived from those.
* Every selection states its settlement basis. Regulation-time markets use the same
  `regulation_score` rule as forecast scoring: a stored 90-minute score wins; a tie that went past
  90 with no 90-minute score is withheld; extra time and shoot-outs settle nothing.
* Reprocessing a stored snapshot stamps the snapshot's own retrieval and model-run times and a
  separate `built_at`; it never presents itself as freshly fetched. `normalisation_version` is
  `markets.v1`.

## Provider research (prices as read on 2026-09-25)

Researched only for the demonstrated gaps: corners, cards, shots, fouls, penalties, player props,
and half-time/full-time. Free first; the owner's ceiling is $25/month.

| Provider | What it adds for the gaps | Price | Verdict |
| --- | --- | --- | --- |
| **GameForecastAPI** (current) | nothing new: every market it publishes is already served. Paid tiers raise the allowance (Pro $19/mo: 5,000 requests/month, 120/min; Ultra $74/mo; Mega $149/mo) and add history; the free tier is 10 requests/day. Its "40+ markets" claim resolves, in the payload we hold, to the families above. | free (held); $19/mo for Pro | **No purchase needed for markets.** A Pro tier would only matter if the 8-a-day allowance blocks forecast coverage — a separate decision. |
| **Boggio Football Prediction API** | 1X2, BTTS, over/under 2.5 and 3.5, home/away over 0.5 and 1.5 — a subset of what GameForecast already gives. No corners, cards or shots. Free: 100 calls/month, 12 h ahead; Pro $14.99, Ultra $24.99, Mega $29.99. | free / $14.99–$29.99 | **Not recommended**: fills no gap. |
| **Sportmonks Predictions add-on** | AI predictions incl. value bets; the add-on is bundled with odds ("Odds & Predictions" €24/mo, €15 on yearly) on top of a base plan from €29/mo (€24 yearly). Predictions cover 1,350+ leagues; corners/cards appear as *statistics*, not as predicted markets. | ≥ €29 + €15–24 /mo (≈ $60+) | **Over budget** and its prediction markets overlap ours; would add an odds feed (50+ bookmakers), which is the one thing this product lacks. Owner's call. |
| **FootyStats API** | statistics (over/unders, BTTS, corners, cards, goals) per team and league — the historical-statistics product, not predictions. From $36.07/mo (official price page returned 403 to us twice; figure from two third-party listings). | ≈ $36/mo | **Over budget**; and statistics are not probabilities — using them as corner "predictions" would be inventing a model, which this product does not do. |

**Recommendation:** no additional provider now. The four gap families (corners, cards, shots,
player props) have no prediction source within the ceiling; the two statistics products would
only supply inputs for a model this product is not allowed to build. The sole purchase with a
demonstrated benefit would be an *odds feed* (Sportmonks bundle), which is out of budget and is
listed for the owner rather than taken.

## Paid-provider decisions left for the owner

1. **Odds feed** (Sportmonks Odds & Predictions bundle, ≈ €44–53/mo incl. base): would let the
   slip quote real prices instead of the reader's own or the provider's unnamed snapshot. Not
   taken: over budget.
2. **GameForecast Pro ($19/mo)**: only if the free tier's 8 requests/day is what limits forecast
   coverage of the added international competitions. Not a markets decision.
3. **Corner/card/shot predictions**: no source found at any price that publishes probabilities
   rather than statistics. Nothing to buy.
