# Money semantics

**Purpose:** settle what every money word in this product means, and what it may never be added to, before anything stores a franc.
**Status:** definitions and pure functions only. No journal, no ledger, no balance, no schema, no endpoint, no screen. See §8 for what is deliberately not built and what would have to happen first.
**Enforced by:** `backend/app/services/money_semantics.py`, tested in `backend/tests/services/test_money_semantics.py`. Every rule below names the function that refuses when it is broken. A rule with no function beside it is a rule that will be broken.

---

## 1. Why this exists before the feature does

The product research on Cameroonian bettors is blunt about one thing: **a bookmark is not a bet**. Saving a match is an act of reading. It says nothing about whether anybody staked anything, and a product that quietly treats the two as the same has started lying to its readers on day one.

That conflation is not the only one. A deposit gets counted as a win. A withdrawal request gets counted as cash. A bonus gets counted as money. A payout quote gets counted as a balance. A fee disappears into a "net" figure where nobody sees it again. Each of these produces a confident number, and a confident wrong number about somebody's money is worse than no number at all.

The journal itself is gated (§8). The vocabulary is not, because everything later depends on it and it is cheap to get right now. Writing it down is half the job; the other half is that the words are executable, so that the next person to write `sum(row.amount for row in rows)` gets an exception instead of a plausible total.

The same discipline already governs published accuracy figures: nothing is published below a minimum sample of 30, and a withheld percentage is a sentence explaining why, never a `0%`, a dash or an empty chart. Money follows the same rule. **A figure appears only with what it was measured from.**

---

## 2. The vocabulary

| Term | What it is | What it is **not** |
|---|---|---|
| **Bookmark** | A saved match. An act of reading. | Not a bet, not an intention, not money. |
| **Idea** | A selection someone is considering. | Not a placed ticket. Nothing has moved. |
| **Placed ticket** | A stake a person says was placed with a bookmaker. | Not something this product can confirm exists. |
| **Leg** | One selection inside a ticket. | Not divisible into its own cash result, and never droppable. |
| **Settlement** | The bookmaker resolving a ticket: won, lost, void. | Not our scoring of a forecast. Different word, different subject. |
| **Transfer** | Money moving between two places the same person owns. | Never a gain, never a loss. |
| **Receipt** | A transfer confirmed as *arrived*. | Not a request, not a pending transfer, not an intention. |
| **Recorded open exposure** | The unresolved stakes recorded *here*. | Not what a person has at risk. |
| **Settled cash result** | Recorded return minus stake, costs held separately. | Not a "profit" figure, and not a performance claim. |
| **Restricted bonus funds** | Credit with conditions attached; not withdrawable. | Not cash. Not a balance. Not money anyone has. |
| **Cost** | A charge, named for the thing it was charged on. | Not a loss on a bet, and not something that may appear twice under two names. |
| **The unknown** | A figure nobody recorded. | Not zero, not a dash, not an empty cell. |

### Why each distinction exists

**Bookmark and idea, versus a placed ticket.** These are the cheapest and most damaging conflation available, because the app already has a bookmark feature and adding a money column to it would take an afternoon. It would also mean the product asserting that somebody spent money when all they did was read. `require_placed_ticket()` refuses a `Bookmark` or an `Idea` anywhere a stake is expected.

**Leg, versus ticket.** A multi-leg ticket pays out on the whole, so the legs only matter when reconciling what a person recorded against what a bookmaker confirmed. That is exactly when the temptation to drop a leg appears: three recorded, two confirmed, and the total balances beautifully if you discard the third. `reconcile_legs()` keeps every unmatched leg on both sides; `require_balanced()` refuses to publish a total built on a reconciliation that does not balance.

**Settlement.** The word is already used in this codebase for scoring forecasts against results (`app/services/settlement.py`). Here it means only the bookmaker resolving a ticket. The two must never share a figure, a table or a sentence: one measures whether a source was right, the other measures money.

**Transfer, versus result.** Moving 5 000 XAF into a betting account is not a 5 000 XAF gain, and moving it back out is not 5 000 XAF of income. This is the arithmetic error that turns one small win into an impressive-looking ledger, because the same money is counted on the way in, on the way out, and again as a result. `result_contribution()` returns a measured zero for every transfer, and `summarise_results()` counts transfers without ever adding them to results.

**Receipt.** A withdrawal that has been *requested* is not money in hand; mobile money fails, bookmakers hold withdrawals, and the gap between "requested" and "arrived" is exactly where someone decides they can afford another stake. `received_amount()` refuses anything not `CONFIRMED_RECEIVED`.

**Recorded open exposure.** We can total the unresolved stakes somebody typed in. We cannot see the ticket they placed on their cousin's phone. The figure is therefore always a floor, never a total, and it is reported with that sentence attached. It is never labelled "total risk", "total staked" or anything else that implies completeness. `recorded_open_exposure()` returns the statement along with the number, and counts separately the recorded tickets whose stake is unknown.

**Settled cash result.** Recorded return minus stake, with the returned stake handled explicitly, and costs attributed separately rather than folded in. A cost folded into a net figure is a cost nobody can ever see again — and the fees are the whole point in this market, where a deposit can cost 1% before anything is staked. `settled_cash_result()` computes `net` *before* costs; `net_after_costs()` exists but must be asked for.

**Restricted bonus funds.** A 2 000 XAF bonus with a 5x turnover condition is not 2 000 XAF. Adding it to cash produces a balance that cannot be withdrawn, which is a promise the product cannot keep. `cash_amount()` refuses it; `available_cash()` reports cash and bonus on separate lines and never sums them.

**Cost.** A cost is the one thing here that has *two* honest representations, which is exactly why it needs a rule of its own — see §5.9. A cost always names what it was charged on: `Cost.attributed_to` has no default, a blank one raises `UnattributedCost`, and the name is stripped at construction so that whitespace cannot make one charge look like two — because a charge attributed to nothing cannot be checked against the record it came from and cannot be explained to a reader.

**The unknown.** A blank field is the most common state in anything self-reported, and `0` is the most common way it gets stored. A zero stake lowers an exposure total; a zero return turns a win into a loss. `UNKNOWN` is a distinct object, `require_amount()` refuses it rather than defaulting, and every total reports how many records it could not speak for.

---

## 3. Who says so: self-reported versus system-confirmed

This is the whole point of the section, so it is stated flatly: **this product has no bookmaker integration, no odds feed and no bank or mobile-money connection, and none is authorised.** Therefore essentially every money fact here would be a person typing what they remember or what a screenshot said.

| Fact | Source | Why it matters |
|---|---|---|
| That a ticket was placed at all | **Self-reported** | Nothing can confirm it. The product must never say "you staked X", only "you recorded X". |
| Stake amount | **Self-reported** | Typed from memory or a screenshot. |
| Return amount, and whether it includes the stake | **Self-reported** | The single biggest source of double-counting. |
| Transfer sent / credited amounts, and fees | **Self-reported** | Mobile-money fees vary; only the person can see the SMS. |
| Whether a transfer arrived | **Self-reported** | No payment integration exists. |
| Bonus terms and withdrawability | **Self-reported** | Bookmaker terms are not machine-readable here. |
| Match result (score, status) | **System-confirmed** (Live Score API) | Already in the product and already used for scoring. |
| Whether a leg's selection actually won | **System-confirmed** where a result exists, otherwise unknown | A match with no stored result cannot settle a leg. |
| Fixture identity, kickoff time | **System-confirmed** | Already in the product. |
| Model forecast and its accuracy | **System-confirmed** | Scored by `app/services/settlement.py` under its own published rules. |

`FactSource` is carried on every record in the module — `SELF_REPORTED`, `SYSTEM_CONFIRMED`, `UNKNOWN` — and provenance is never inferred from context. `require_system_confirmed()` refuses to let a typed figure be presented as a verified one, and `provenance_sentence()` produces the words that must accompany the figure wherever it is shown.

**The table above is enforced, not advisory.** It used to be prose only, and prose let a caller build `PlacedTicket(..., source=SYSTEM_CONFIRMED)` — a claim no part of this product could have produced, since there is no bookmaker integration to produce it. The label then travelled: the record satisfied `require_system_confirmed()`, `settled_cash_result()` copied it onto the `CashResult`, and `provenance_sentence()` printed *"was confirmed by a system"* beside a figure somebody typed from memory. That is the precise sentence this module exists to prevent, reached without breaking a single rule as written. So `require_not_confirmed()` now refuses `SYSTEM_CONFIRMED` at construction on every money record — `PlacedTicket`, `Transfer`, `Funds`, `Cost`, `CashResult`. `UNKNOWN` stays allowed: not recording who said so is not the same as claiming a system did.

`Leg.source` is deliberately **not** refused. A leg's outcome is one of the few things this product genuinely can confirm, from a stored match result, and the rule must not be widened until a real confirmation becomes unrecordable. The unlock for the rest is the same as §8's: an actual integration. Until one exists and is authorised, nothing here can confirm a franc.

A system-confirmed leg outcome sitting next to a self-reported stake does **not** make the ticket confirmed. Confidence never propagates upward from a part to the whole.

---

## 4. How money is represented, and why

Money is an **integer count of minor units plus an ISO 4217 currency code** (`Money`), with the exponent held in a short, explicit table (`MINOR_UNIT_DIGITS`).

| Candidate | Verdict |
|---|---|
| `float` | **Defect.** `0.1 + 0.2 != 0.3`. A drift in somebody's money is not a rounding artefact, it is a wrong figure. The constructor raises `FloatAmountRefused` on a float rather than converting it, because accepting one hides where the drift entered. |
| bare `int` of "the currency's units" | **Defect.** 5 050 francs and 5 050 cents are the same integer. The code is not optional. |
| `Decimal` alone | Exact, but carries no currency: `Decimal("5050") + Decimal("12.00")` is a silent, happy, wrong answer. Used here only for parsing and for exchange rates. |
| **minor units + currency code** | **Chosen.** Exact, comparable, serialisable, and impossible to add to the wrong thing without an exception. |

XAF has **no minor unit** (exponent 0): 5 050 XAF is the integer 5 050. That is an argument *for* integers, not a licence to use floats. EUR is exponent 2, TND is exponent 3 — which is the standing proof that "assume two decimals" is not safe. An unlisted currency code raises `UnknownCurrency` rather than inheriting cents it does not have, and an amount with more precision than its currency allows raises `PrecisionTooFine` rather than being rounded where nobody can see it.

---

## 5. The invariants

Each is a pure function: no database, no I/O, no clock. Each refuses rather than guesses.

1. **Money in one currency is never added to money in another.** A total across currencies is a *set* of totals, not a number. `CurrencyTotals` holds one figure per currency and raises on `int()`, `float()` and `sole()` when there is more than one, because the moment a caller can coerce it to one number, someone will, and the currency will be whichever happened to be first. Enforced by `Money.__add__`, `CurrencyTotals`.
2. **Any conversion needs a rate, a source and a date, and stays an estimate.** `ExchangeRate` refuses an unsourced, undated or float rate. `convert_estimate()` returns an `EstimatedMoney`, which is deliberately *not* a `Money` and cannot be added to one, so an estimate can never harden into a figure someone believes was paid. It carries its own caveat sentence.
3. **A deposit is a transfer and never a gain; a withdrawal request is not a receipt; a quoted payout is not available cash.** `result_contribution()`, `received_amount()`, `QuotedPayout.as_cash()`.
4. **A settled cash result is the recorded return minus the stake**, with the returned stake handled explicitly and costs attributed separately. A profit-only figure that does not say whether the stake came back raises `AmbiguousReturn` — the two readings differ by the entire stake, so the record must decide, not the code. `settled_cash_result()`.
5. **Recorded open exposure counts unresolved recorded stakes only**, and is reported alongside the fact that unrecorded activity is unknown. It is never presented as a person's total risk. `recorded_open_exposure()`, whose `statement()` carries the caveat with the number.
6. **An unmatched leg is preserved**, never discarded to make a total balance. `reconcile_legs()`, `require_balanced()`.
7. **A missing amount is unknown, not zero** — and something that is not money at all is not an amount either. `require_amount()` refuses both, by name: `AmountUnknown` for the unknown, `NotMoney` for a bare `500` that carries no currency or an `EstimatedMoney` that is a converted guess. Both are `MoneySemanticsError`, which is what callers catch. A bare `assert` stood in for the second check once; it was invisible to those callers and absent entirely under `python -O`.
8. **Restricted bonus funds are not cash.** `cash_amount()`, `available_cash()`.
9. **One charge is counted once, and two figures for one charge are refused rather than chosen between.** `summarise_results()`, `require_unique_fee_attribution()`. This is §5.9 below, and it is long enough to need its own section.
10. **A money fact may not claim a system confirmed it.** `require_not_confirmed()`, enforced at construction on every money record. §3.

### 5.9 One charge, one home

A transfer fee is the one fact this module can record two ways, and both are honest:

- **derived** — the gap between what left the wallet and what arrived, `sent − credited`, computed by the module from two figures the person read off two SMS messages;
- **written** — a `Cost` of kind `TRANSFER_FEE` or `WITHDRAWAL_FEE` naming that transfer, typed because the person knew the fee directly.

Recorded both ways, the worked example's 50 XAF was **subtracted twice**: `summarise_results()` added `event.costs` from the settlement and `sent − credited` from the transfer, and the run's cost total came to 100 XAF for a 50 XAF charge. The honest 750 XAF of §6 became 700 XAF, and the function's own docstring promise — *"counting nothing twice"* — was false in the one case the worked example makes most likely.

**The rule, and why this one and not the other.** The obvious alternative was to give the cost exactly one home and refuse the other representation. That was rejected: refusing the written `Cost` breaks summarising a settlement whose transfer is not part of the run at all, and refusing the derived figure throws away the one number the module can compute for itself and makes the person retype it. Both recordings are legitimate; only *adding* them is wrong. So the fix belongs where the addition happens, which is also the only place both are visible. `summarise_results()` reconciles them by the transfer's `reference`:

| What the run contains | What happens |
|---|---|
| Both, and they agree | One charge. Counted **once**. `costs_deduplicated` counts it, so the smaller total is explained rather than mysterious. |
| Both, and they disagree | **`ConflictingCost`.** Two figures for one fee cannot both be right and nothing here can tell which is. Whichever-came-last is not a rule. |
| Only one of them | Counted once, which needed no rule. |
| A fee cost naming nothing in this run | An ordinary cost — the transfer it belongs to is simply elsewhere. |

Two refusals make that reconciliation possible rather than decorative:

- **A transfer that actually charged something must carry a `reference`** (`UnattributedCost`). A derived fee with no name cannot be checked against a written one, so it cannot be told apart from a duplicate. This is the same requirement `Cost.attributed_to` already imposes on the written representation; a transfer that charged nothing has no cost to attribute and needs no reference.
- **One reference may name only one transfer in a run** (`DuplicateRecord`). A reference on two movements makes both the fee matching and the transfer count wrong.
- **Both sides of the match are normalised the same way.** The reconciliation is a string comparison between `Transfer.reference` and `Cost.attributed_to`, so the two must agree on what counts as the same name. `_reference_of()` strips a transfer's reference; `Cost.attributed_to` is stripped at construction by the same rule. When only one side stripped, `" deposit-1 "` and `"deposit-1"` were two names for one charge: the written cost never met its transfer, the derived fee was added as well, and the worked example fell back to 700 XAF — this whole section walked around by a space. Two fee costs whose names differed only in whitespace slipped past `require_unique_fee_attribution()` the same way.

And **at most one fee cost may name any one thing** (`require_unique_fee_attribution()`, checked on a `CashResult` at construction and again across a whole run). One movement of money is charged one fee, so two fee costs against the same name cannot both be it: either the charge was recorded twice, or one belongs to something else. Summing them invents a cost nobody paid; dropping one hides a cost somebody did. The module cannot tell which, so it refuses and asks for the names to be fixed.

That check is keyed on the **name alone**, not on the name and the kind together. One deposit cannot be charged both a `TRANSFER_FEE` and a `WITHDRAWAL_FEE`, and admitting the pair would leave two costs competing to be the one reconciled against that transfer — the loser vanishing from the total, which is the same silent "last one wins" this section exists to forbid, only quieter. Costs of a **non-fee** kind are untouched: a transfer fee and a *tax* on the same deposit are two genuinely different charges and stay two.

**A refusal that was documented and then swallowed.** `transfer_cost()` raises `UnexplainedCredit` when more was credited than was sent, and `CurrencyMismatch` when the two sides are in different currencies. The helper `summarise_results()` used returned `None` for both, and `None` meant "cost unknown" — so a total printed *"Transfer deposit-1 is confirmed_received or missing an amount; its cost is unknown"* about a confirmed transfer with both amounts recorded. Two rules broke at once: a contradiction the module insists be named was filed as a missing figure, and the sentence stated a reason nobody had checked. Both refusals now propagate out of `summarise_results()`, `None` means only *not confirmed received* or *an amount was never recorded*, and the message says which of the two it actually is.

---

## 6. The worked example

From the research, in XAF, as it happens on a phone:

| Step | What happens | What it means | What it must never mean |
|---|---|---|---|
| 1 | 5 050 XAF leaves the wallet, 5 000 XAF arrives in the betting account | A transfer with a **50 XAF cost**. Result so far: nothing. | A 5 000 XAF spend, a 5 050 XAF loss, or a deposit "bonus" of any kind |
| 2 | 1 000 XAF staked, 1 800 XAF returned (bookmaker's figure, stake included) | **+800 XAF** before costs. The 50 XAF stays a visible cost. | +1 800 XAF |
| 3 | The 1 800 XAF is withdrawn to the wallet | A transfer. **It changes nothing.** | +1 800 again, for a fictional +2 600 |

There is a fourth line the table used to miss, because it is not a step — it is a way of writing step 1 down:

| Step | What happens | What it means | What it must never mean |
|---|---|---|---|
| 1b | The 50 XAF fee is *also* typed in as a cost against the deposit | Still **one 50 XAF charge**, recorded twice. Counted once. | A 100 XAF cost, and a 700 XAF answer |

The test module asserts exactly this sequence, then the traps around it: mixed-currency addition, a pending transfer read as received, a bonus counted as cash, an unmatched leg dropped, a missing amount defaulting to zero, and one charge counted twice. 53 tests, each named for the error it prevents.

Note what the correct figures look like: a person who deposited 5 050 XAF and won a bet is **up 750 XAF after costs**, not up 1 800, and not up 2 600 — and not up 700 either, which is what the double-counted fee produced. The honest number is the small one, but it is not the smallest one you can reach by being careless in the other direction: a total that over-counts a cost is as wrong as one that hides it, and it is harder to notice because it errs towards modesty. That is the whole argument for doing this before building anything on top of it.

---

## 7. How these figures may be presented

Binding on anything that ever displays them:

- **Never celebrate spending.** No confetti on a deposit, no congratulation on a stake, no positive framing of volume. A larger number is not better news.
- **No streaks as pressure, no loss-recovery prompts, no nudge towards another selection.** A reader who pauses, exports their data or turns off alerts has been served well, not lost.
- **Never imply a source, an expert or a figure is guaranteed, safe, or income.** A settled cash result is a record of what happened, not a forecast of what will.
- **Never present cached data as live**, and never present a self-reported figure as a confirmed one.
- **A withheld figure is a sentence.** "You have not recorded a stake for this ticket" — never a `0`, a `—`, or a blank cell that reads as zero.
- **Never label recorded exposure as total risk.** The caveat travels with the number, in the same view, not in a footnote.
- **A total that is smaller than its parts must say why.** When a charge was recorded twice and counted once, the sentence saying so travels with the total (`ResultSummary.statement()`). A cost total that silently does not add up invites the reader to add it up themselves, and they will get the wrong answer and trust it.

---

## 8. What is not built, and what would unlock it

Not built, deliberately: **the wager journal, the money ledger, any balance or profit display, bookmaker integration, receipt scanning, and odds comparison.** No schema, no model, no migration, no endpoint, no screen. This document and its module add no storage of any kind.

The gate is the research brief's own: each of those is conditioned on **owner authorisation and user validation that has not happened.** Nobody here has talked to a bettor about whether they would record a ticket honestly, or at all, and a journal that is filled in selectively produces a *flattering* history — the losing tickets are the ones that do not get typed in. Building the storage before that question is answered would mean shipping a number we already know how to make wrong.

What would unlock it: the owner authorising the feature, and validation with real users establishing that the recording behaviour is honest enough for the resulting figures to mean anything. Until then the rules sit here, executable, costing nothing and blocking nothing.

---

## 9. Where the rules live

| File | Contents |
|---|---|
| `docs/money-semantics.md` | This document: the definitions and the reasoning. |
| `backend/app/services/money_semantics.py` | The vocabulary as types, and the invariants as pure functions that refuse. No I/O, no database, no clock. |
| `backend/tests/services/test_money_semantics.py` | The worked example and every refusal, each test named for the error it prevents. No database required. |

If a rule here changes, it changes in all three places at once, or it has not changed.
