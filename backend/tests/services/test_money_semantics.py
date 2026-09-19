"""Tests for money semantics: every one of these pins down a specific way money goes wrong.

There is no database here and nothing is stored, because there is nothing to store: this product
has no journal, no ledger and no wallet. These tests are the rules written down in a form that
fails when somebody breaks them.

The spine of the module is the worked example from the product research, in XAF, as it actually
happens on a phone in Douala:

    1. 5 050 XAF leaves a mobile-money wallet and 5 000 XAF arrives in a betting account. The
       50 XAF difference is a fee. Nobody has won or lost anything.
    2. 1 000 XAF is staked and 1 800 XAF comes back, the bookmaker's figure including the stake.
       That is +800, and the 50 XAF fee is still a separate, visible cost.
    3. The 1 800 XAF is withdrawn to the wallet. It is the same money. Counting it again would
       turn one 800 XAF result into a 2 600 XAF fiction.

Everything else here is a refusal: the additions, defaults and quiet roundings that would each
produce a confident, wrong number.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.money_semantics import (
    UNKNOWN,
    AmbiguousReturn,
    AmountUnknown,
    Bookmark,
    CashResult,
    ConflictingCost,
    Cost,
    CostKind,
    CurrencyMismatch,
    CurrencyTotals,
    DuplicateRecord,
    EstimatedMoney,
    ExchangeRate,
    FactSource,
    FloatAmountRefused,
    FundKind,
    Funds,
    Idea,
    Leg,
    LegOutcome,
    Money,
    MoneySemanticsError,
    NotCash,
    NotConfirmable,
    NotMoney,
    NotPlaced,
    NotReceived,
    NotSettled,
    PlacedTicket,
    PrecisionTooFine,
    QuotedPayout,
    ReturnBasis,
    SelfReportedNotConfirmed,
    TicketStatus,
    Transfer,
    TransferDirection,
    TransferStatus,
    UnattributedCost,
    UnexplainedCredit,
    UnknownCurrency,
    UnmatchedLeg,
    UnsourcedConversion,
    available_cash,
    cash_amount,
    convert_estimate,
    recorded_open_exposure,
    reconcile_legs,
    require_amount,
    require_balanced,
    require_not_confirmed,
    require_placed_ticket,
    require_system_confirmed,
    result_contribution,
    settled_cash_result,
    summarise_results,
    transfer_cost,
    received_amount,
)


# ----------------------------------------------------------------------------- helpers
def xaf(amount: str) -> Money:
    return Money.of("XAF", amount)


def confirmed_deposit(sent: str = "5050", credited: str = "5000") -> Transfer:
    """The wallet debit and the book credit from the worked example."""
    return Transfer(
        direction=TransferDirection.INTO_BETTING_ACCOUNT,
        status=TransferStatus.CONFIRMED_RECEIVED,
        sent=xaf(sent),
        credited=xaf(credited),
        source=FactSource.SELF_REPORTED,
        reference="deposit-1",
    )


def settled_winner() -> CashResult:
    """1 000 XAF staked, 1 800 XAF back including the stake."""
    return settled_cash_result(
        PlacedTicket(
            reference="ticket-1",
            stake=xaf("1000"),
            returned=xaf("1800"),
            return_basis=ReturnBasis.INCLUDES_STAKE,
            status=TicketStatus.SETTLED,
        )
    )


# ------------------------------------------------------- the worked example, step by step
def test_wallet_debit_above_the_book_credit_is_a_cost_and_never_a_profit():
    """Prevents: the 50 XAF gap being read as a gain, a loss, or nothing at all."""
    deposit = confirmed_deposit()
    assert transfer_cost(deposit) == xaf("50")
    # And the deposit itself moves the result by exactly nothing.
    assert result_contribution(deposit) == Money.zero("XAF")
    assert result_contribution(deposit).is_zero


def test_a_return_that_includes_the_stake_nets_the_profit_only_never_the_whole_return():
    """Prevents: 1 800 XAF back on a 1 000 XAF stake being recorded as +1 800."""
    result = settled_winner()
    assert result.net == xaf("800")
    assert result.stake == xaf("1000")
    assert result.returned == xaf("1800")
    assert result.costs == ()


def test_withdrawing_the_return_does_not_count_the_same_money_a_second_time():
    """Prevents: the 1 800 XAF wallet receipt turning one 800 XAF result into 2 600 XAF."""
    deposit = confirmed_deposit()
    result = settled_winner()
    withdrawal = Transfer(
        direction=TransferDirection.OUT_OF_BETTING_ACCOUNT,
        status=TransferStatus.CONFIRMED_RECEIVED,
        sent=xaf("1800"),
        credited=xaf("1800"),
        reference="withdrawal-1",
    )

    summary = summarise_results([deposit, result, withdrawal])

    assert summary.results.sole() == xaf("800"), "the return must be counted exactly once"
    assert summary.costs.sole() == xaf("50"), "the deposit fee stays a cost, not a loss"
    assert summary.transfers_counted == 2


def test_the_deposit_fee_is_attributed_separately_and_not_folded_into_the_result():
    """Prevents: a cost disappearing into a net figure where nobody can see it again."""
    fee = Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1")
    result = settled_cash_result(
        PlacedTicket("ticket-1", stake=xaf("1000"), returned=xaf("1800"),
                     status=TicketStatus.SETTLED),
        costs=[fee],
    )
    assert result.net == xaf("800"), "net is before costs, always"
    assert result.net_after_costs() == xaf("750"), "costs subtract only when asked, explicitly"
    assert "separately" in result.statement()


# ----------------------------------------------------------------------------- refusals
def test_adding_two_currencies_is_refused_and_never_silently_summed():
    """Prevents: 5 000 XAF + 10 EUR producing 5 010 of nothing."""
    with pytest.raises(CurrencyMismatch):
        xaf("5000") + Money.of("EUR", "10.00")
    with pytest.raises(CurrencyMismatch):
        xaf("5000") - Money.of("EUR", "10.00")
    with pytest.raises(CurrencyMismatch):
        xaf("5000") < Money.of("EUR", "10.00")


def test_a_total_across_currencies_stays_a_set_of_totals_and_refuses_to_be_one_number():
    """Prevents: a mixed-currency total being coerced into a single headline figure."""
    totals = CurrencyTotals.of([xaf("5000"), Money.of("EUR", "10.00"), xaf("50")])

    assert totals["XAF"] == xaf("5050")
    assert totals["EUR"] == Money.of("EUR", "10.00")
    with pytest.raises(CurrencyMismatch):
        totals.sole()
    with pytest.raises(CurrencyMismatch):
        int(totals)
    with pytest.raises(CurrencyMismatch):
        float(totals)


def test_a_currency_absent_from_a_total_is_unknown_and_not_zero():
    """Prevents: an untouched currency being reported as a 0 balance nobody measured."""
    totals = CurrencyTotals.of([xaf("5000")])
    assert totals.get("EUR") is UNKNOWN
    with pytest.raises(KeyError):
        totals["EUR"]


def test_a_pending_transfer_is_refused_and_never_read_as_money_received():
    """Prevents: money still in flight being shown as money in hand."""
    pending = Transfer(
        direction=TransferDirection.OUT_OF_BETTING_ACCOUNT,
        status=TransferStatus.PENDING,
        sent=xaf("1800"),
        credited=xaf("1800"),
    )
    with pytest.raises(NotReceived):
        received_amount(pending)
    with pytest.raises(NotReceived):
        transfer_cost(pending)


def test_a_withdrawal_request_is_refused_as_a_receipt():
    """Prevents: 'I requested 10 000 XAF' being recorded as 10 000 XAF received."""
    requested = Transfer(
        direction=TransferDirection.OUT_OF_BETTING_ACCOUNT,
        status=TransferStatus.REQUESTED,
        sent=xaf("10000"),
        credited=UNKNOWN,
    )
    with pytest.raises(NotReceived):
        received_amount(requested)


def test_a_bonus_is_refused_as_cash_and_never_enters_a_cash_total():
    """Prevents: non-withdrawable bonus credit being shown as money a person has."""
    bonus = Funds(xaf("2000"), FundKind.RESTRICTED_BONUS, note="deposit-match, 5x turnover")
    with pytest.raises(NotCash):
        cash_amount(bonus)

    held = available_cash([Funds(xaf("5000"), FundKind.CASH), bonus])
    assert held.cash.sole() == xaf("5000"), "the bonus must not be added to cash"
    assert held.restricted_bonus.sole() == xaf("2000"), "and it must still be reported"
    assert "cannot be withdrawn" in held.statement()


def test_a_quoted_payout_is_refused_as_available_cash():
    """Prevents: a bookmaker's 'returns 4 500 XAF' being treated as 4 500 XAF held."""
    with pytest.raises(NotCash):
        QuotedPayout(xaf("4500"), selection="home win").as_cash()


def test_an_unmatched_leg_is_kept_and_never_dropped_to_make_a_total_balance():
    """Prevents: a reconciliation 'balancing' because an inconvenient leg was discarded."""
    recorded = [Leg("leg-1", "home win", LegOutcome.WON),
                Leg("leg-2", "both teams score", LegOutcome.LOST)]
    confirmed = [Leg("leg-1", "home win", LegOutcome.WON, FactSource.SYSTEM_CONFIRMED)]

    reconciliation = reconcile_legs(recorded, confirmed)

    assert len(reconciliation.matched) == 1
    assert reconciliation.unmatched_recorded == (recorded[1],), "the leg survives"
    assert reconciliation.balanced is False
    with pytest.raises(UnmatchedLeg):
        require_balanced(reconciliation)


def test_a_missing_amount_is_unknown_and_never_defaults_to_zero():
    """Prevents: a blank stake field quietly becoming a 0 XAF stake in a total."""
    with pytest.raises(AmountUnknown):
        require_amount(UNKNOWN, "The stake")
    with pytest.raises(AmountUnknown):
        require_amount(None, "The stake")
    with pytest.raises(AmountUnknown):
        settled_cash_result(PlacedTicket("t", stake=UNKNOWN, returned=xaf("1800"),
                                         status=TicketStatus.SETTLED))
    with pytest.raises(AmountUnknown):
        CurrencyTotals.of([xaf("100"), UNKNOWN])


# ----------------------------------------------------------------------------- representation
def test_a_float_amount_is_refused_and_never_rounded_into_money():
    """Prevents: 0.1 + 0.2 arithmetic reaching somebody's balance."""
    with pytest.raises(FloatAmountRefused):
        Money.of("EUR", 10.50)
    with pytest.raises(FloatAmountRefused):
        Money("XAF", 5050.0)


def test_the_minor_units_constructor_refuses_a_float_instead_of_truncating_it():
    """Prevents: 1.15 * 100 entering as 114 cents through the back door of minor_units()."""
    with pytest.raises(FloatAmountRefused):
        Money.minor_units("EUR", 1.15 * 100)      # 114.999... in float; int() would say 114
    with pytest.raises(FloatAmountRefused):
        Money.minor_units("XAF", 5050.9)
    with pytest.raises(FloatAmountRefused):
        Money.minor_units("EUR", Decimal("10.5"))  # half a cent, dropped by int()
    assert Money.minor_units("XAF", 5050) == xaf("5050"), "a whole count still works"


def test_sub_unit_precision_is_refused_rather_than_rounded_where_nobody_can_see_it():
    """Prevents: 0.5 XAF or a third cent being invented by a silent round()."""
    with pytest.raises(PrecisionTooFine):
        Money.of("XAF", "5050.5")
    with pytest.raises(PrecisionTooFine):
        Money.of("EUR", "10.505")


def test_xaf_is_stored_in_whole_francs_and_never_as_hundredths():
    """Prevents: 5 050 XAF being stored as 505 000 'cents' by a two-decimal assumption."""
    assert xaf("5050").minor == 5050
    assert xaf("5050").amount == Decimal("5050")
    assert str(xaf("5050")) == "5050 XAF"
    # A currency that does have a minor unit keeps it, and a three-decimal one keeps three.
    assert Money.of("EUR", "10.50").minor == 1050
    assert Money.of("TND", "10.505").minor == 10505
    # Same amount written three ways, one exact result.
    assert Money.of("XAF", 5050) == Money.of("XAF", "5050") == Money.of("XAF", Decimal("5050"))


def test_an_unlisted_currency_is_refused_rather_than_assumed_to_have_two_decimals():
    """Prevents: an unknown code silently inheriting cents it does not have."""
    with pytest.raises(UnknownCurrency):
        Money.of("ZZZ", "100")
    with pytest.raises(UnknownCurrency):
        Money.of("", "100")


def test_money_cannot_be_summed_with_a_bare_number():
    """Prevents: a stray int or float joining a money total through sum()."""
    with pytest.raises(CurrencyMismatch):
        5000 + xaf("50")
    assert sum([xaf("1000"), xaf("800")]) == xaf("1800"), "same-currency sum() stays usable"
    with pytest.raises(CurrencyMismatch):
        sum([xaf("1000"), Money.of("EUR", "8.00")])


# ----------------------------------------------------------------------------- conversion
def test_a_conversion_without_a_rate_source_and_date_is_refused():
    """Prevents: an unsourced 'about 8 EUR' that nobody can check or reproduce later."""
    with pytest.raises(UnsourcedConversion):
        ExchangeRate("XAF", "EUR", Decimal("0.001524"), "", date(2026, 9, 19))
    with pytest.raises(UnsourcedConversion):
        ExchangeRate("XAF", "EUR", Decimal("0"), "BEAC", date(2026, 9, 19))
    with pytest.raises(FloatAmountRefused):
        ExchangeRate("XAF", "EUR", 0.001524, "BEAC", date(2026, 9, 19))


def test_a_converted_amount_stays_an_estimate_and_cannot_be_added_to_money():
    """Prevents: an estimate hardening into a figure someone believes was paid."""
    rate = ExchangeRate("XAF", "EUR", Decimal("0.001524"), "BEAC published rate",
                        date(2026, 9, 19))
    estimated = convert_estimate(xaf("5000"), rate)

    assert isinstance(estimated, EstimatedMoney)
    assert not isinstance(estimated, Money)
    assert estimated.estimate == Money.of("EUR", "7.62")
    assert "An estimate" in estimated.caveat()
    with pytest.raises(CurrencyMismatch):
        Money.of("EUR", "1.00") + estimated


# ----------------------------------------------------------------------------- not a bet
def test_a_bookmark_is_refused_as_a_placed_ticket():
    """Prevents: saving a match being counted as staking money on it."""
    with pytest.raises(NotPlaced):
        require_placed_ticket(Bookmark("match-42"))


def test_an_idea_is_refused_as_a_placed_ticket():
    """Prevents: a selection someone was considering entering a stake total."""
    with pytest.raises(NotPlaced):
        require_placed_ticket(Idea("match-42", "over 2.5"))
    with pytest.raises(NotPlaced):
        recorded_open_exposure([Idea("match-42", "over 2.5")])


# ----------------------------------------------------------------------------- settlement
def test_an_open_ticket_has_no_cash_result():
    """Prevents: an unresolved stake being settled early as a loss."""
    with pytest.raises(NotSettled):
        settled_cash_result(PlacedTicket("t", stake=xaf("1000"), status=TicketStatus.OPEN))


def test_a_void_ticket_returning_the_stake_nets_zero_and_is_not_a_loss():
    """Prevents: a returned stake being recorded as money lost."""
    result = settled_cash_result(
        PlacedTicket("t", stake=xaf("1000"), returned=xaf("1000"), status=TicketStatus.SETTLED)
    )
    assert result.net == Money.zero("XAF")
    assert result.net.is_zero


def test_a_lost_ticket_nets_the_stake_and_nothing_worse():
    """Prevents: a loss being inflated beyond the money that was actually staked."""
    result = settled_cash_result(
        PlacedTicket("t", stake=xaf("1000"), returned=Money.zero("XAF"),
                     status=TicketStatus.SETTLED)
    )
    assert result.net == xaf("-1000")


def test_a_profit_only_figure_is_refused_unless_the_record_says_the_stake_came_back():
    """Prevents: a profit-only return being read as if it included the stake, or the reverse."""
    profit_only = PlacedTicket("t", stake=xaf("1000"), returned=xaf("800"),
                               return_basis=ReturnBasis.EXCLUDES_STAKE,
                               status=TicketStatus.SETTLED)
    with pytest.raises(AmbiguousReturn):
        settled_cash_result(profit_only)

    from dataclasses import replace
    assert settled_cash_result(replace(profit_only, stake_returned=True)).net == xaf("800")
    with pytest.raises(AmbiguousReturn):
        settled_cash_result(replace(profit_only, stake_returned=False))


def test_a_stake_and_a_return_in_different_currencies_are_refused():
    """Prevents: a cross-currency ticket netting a number that is neither currency."""
    with pytest.raises(CurrencyMismatch):
        settled_cash_result(PlacedTicket("t", stake=xaf("1000"),
                                         returned=Money.of("EUR", "2.00"),
                                         status=TicketStatus.SETTLED))


# ----------------------------------------------------------------------------- exposure
def test_open_exposure_counts_only_recorded_unresolved_stakes_and_says_what_it_cannot_see():
    """Prevents: recorded exposure being presented as everything a person has at risk."""
    exposure = recorded_open_exposure([
        PlacedTicket("t1", stake=xaf("1000"), status=TicketStatus.OPEN),
        PlacedTicket("t2", stake=xaf("500"), status=TicketStatus.OPEN),
        PlacedTicket("t3", stake=xaf("9999"), returned=xaf("0"), status=TicketStatus.SETTLED),
    ])

    assert exposure.totals.sole() == xaf("1500"), "settled tickets are not exposure"
    assert exposure.open_tickets == 2
    statement = exposure.statement()
    assert "not a total of what is at risk" in statement
    assert "unknown" in statement


def test_a_ticket_with_no_recorded_stake_is_counted_as_unknown_not_as_zero_exposure():
    """Prevents: a blank stake quietly lowering the exposure figure."""
    exposure = recorded_open_exposure([
        PlacedTicket("t1", stake=xaf("1000"), status=TicketStatus.OPEN),
        PlacedTicket("t2", stake=UNKNOWN, status=TicketStatus.OPEN),
    ])
    assert exposure.totals.sole() == xaf("1000")
    assert exposure.tickets_with_unknown_stake == 1
    assert "unknown, not zero" in exposure.statement()


# ----------------------------------------------------------------------------- provenance
def test_a_self_reported_figure_is_refused_when_a_confirmed_one_is_required():
    """Prevents: a number someone typed being displayed as one a system verified."""
    with pytest.raises(SelfReportedNotConfirmed):
        require_system_confirmed(FactSource.SELF_REPORTED, "This stake")
    with pytest.raises(SelfReportedNotConfirmed):
        require_system_confirmed(FactSource.UNKNOWN, "This stake")
    assert require_system_confirmed(FactSource.SYSTEM_CONFIRMED, "This result") is (
        FactSource.SYSTEM_CONFIRMED)


def test_a_credit_larger_than_the_send_is_refused_rather_than_becoming_a_negative_cost():
    """Prevents: a bonus top-up appearing as free money through a negative fee."""
    with pytest.raises(UnexplainedCredit):
        transfer_cost(confirmed_deposit(sent="5000", credited="5500"))


def test_summarising_refuses_anything_that_is_neither_a_settled_result_nor_a_transfer():
    """Prevents: an unnamed record being swept into a money total by accident."""
    with pytest.raises(MoneySemanticsError):
        summarise_results([Bookmark("match-42")])


def test_a_transfer_with_an_unreadable_cost_is_reported_rather_than_assumed_free():
    """Prevents: a pending or half-recorded transfer silently contributing a 0 XAF fee."""
    summary = summarise_results([
        settled_winner(),
        Transfer(TransferDirection.INTO_BETTING_ACCOUNT, TransferStatus.PENDING,
                 sent=xaf("5050"), credited=UNKNOWN, reference="deposit-2"),
    ])
    assert summary.results.sole() == xaf("800")
    assert summary.costs.currencies == (), "no cost may be invented"
    assert summary.transfers_with_unknown_cost == 1
    assert summary.unknowns and "unknown" in summary.unknowns[0]


# ------------------------------------------------- one cost, one home: the fee counted twice
def test_one_transfer_fee_recorded_both_ways_is_counted_once_not_twice():
    """Prevents: the 50 XAF deposit fee being subtracted twice because it was written down
    once as a Cost and once as the gap between sent and credited."""
    deposit = confirmed_deposit()                      # 5 050 sent, 5 000 credited: a 50 XAF fee
    fee = Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1")   # the SAME 50 XAF
    result = settled_cash_result(
        PlacedTicket("ticket-1", stake=xaf("1000"), returned=xaf("1800"),
                     status=TicketStatus.SETTLED),
        costs=[fee],
    )

    summary = summarise_results([deposit, result])

    assert summary.costs.sole() == xaf("50"), "one fee was paid, so one fee is counted"
    assert summary.costs_deduplicated == 1
    assert "once" in summary.statement()
    # And the arithmetic the document promises survives: 800 - 50, not 800 - 100.
    assert summary.results.sole() - summary.costs.sole() == xaf("750")


def test_the_worked_example_reaches_750_whichever_way_the_fee_was_recorded():
    """Prevents: the answer depending on which of two legitimate recordings the reader chose."""
    deposit = confirmed_deposit()
    withdrawal = Transfer(TransferDirection.OUT_OF_BETTING_ACCOUNT,
                          TransferStatus.CONFIRMED_RECEIVED,
                          sent=xaf("1800"), credited=xaf("1800"), reference="withdrawal-1")
    fee = Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1")

    derived_only = summarise_results([deposit, settled_winner(), withdrawal])
    written_too = summarise_results([
        deposit,
        settled_cash_result(PlacedTicket("ticket-1", stake=xaf("1000"), returned=xaf("1800"),
                                         status=TicketStatus.SETTLED), costs=[fee]),
        withdrawal,
    ])

    assert derived_only.costs.sole() == xaf("50")
    assert written_too.costs.sole() == xaf("50")
    assert derived_only.results.sole() == written_too.results.sole() == xaf("800")
    assert derived_only.costs_deduplicated == 0 and written_too.costs_deduplicated == 1


def test_two_different_figures_for_one_transfer_fee_are_refused_rather_than_one_being_picked():
    """Prevents: a silent 'last one wins' choosing between 50 XAF and 60 XAF for one fee."""
    deposit = confirmed_deposit()                       # arithmetic says the fee was 50 XAF
    wrong = Cost(xaf("60"), CostKind.TRANSFER_FEE, attributed_to="deposit-1")   # the record says 60
    result = settled_cash_result(
        PlacedTicket("t", stake=xaf("1000"), returned=xaf("1800"), status=TicketStatus.SETTLED),
        costs=[wrong],
    )
    with pytest.raises(ConflictingCost) as raised:
        summarise_results([deposit, result])
    assert "deposit-1" in str(raised.value)
    # It is refused from either direction, so the answer cannot depend on the order of the run.
    with pytest.raises(ConflictingCost):
        summarise_results([result, deposit])


def test_a_recorded_fee_against_a_transfer_that_charged_nothing_is_refused():
    """Prevents: a 50 XAF fee surviving beside a transfer whose own figures say none was charged."""
    free = Transfer(TransferDirection.OUT_OF_BETTING_ACCOUNT, TransferStatus.CONFIRMED_RECEIVED,
                    sent=xaf("1800"), credited=xaf("1800"), reference="withdrawal-1")
    claimed = settled_cash_result(
        PlacedTicket("t", stake=xaf("1000"), returned=xaf("1800"), status=TicketStatus.SETTLED),
        costs=[Cost(xaf("50"), CostKind.WITHDRAWAL_FEE, attributed_to="withdrawal-1")],
    )
    with pytest.raises(ConflictingCost):
        summarise_results([free, claimed])


def test_two_recorded_fees_naming_one_transfer_from_two_results_are_refused_not_summed():
    """Prevents: one fee written against two settlements - the shape no single result can see -
    reaching a run total as 100 XAF."""
    def result_with(fee: Cost) -> CashResult:
        return settled_cash_result(
            PlacedTicket("t", stake=xaf("1000"), returned=xaf("1800"),
                         status=TicketStatus.SETTLED),
            costs=[fee],
        )

    first = result_with(Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1"))
    second = result_with(Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1"))
    assert first.net_after_costs() == xaf("750"), "each on its own is a perfectly good record"

    with pytest.raises(ConflictingCost) as raised:
        summarise_results([first, second])
    assert "deposit-1" in str(raised.value)


def test_a_deposit_fee_and_a_withdrawal_fee_against_one_name_are_refused_not_silently_dropped():
    """Prevents: two fee kinds against one name reconciling only one of them and losing the
    other from the cost total altogether."""
    with pytest.raises(ConflictingCost) as raised:
        settled_cash_result(
            PlacedTicket("t", stake=xaf("1000"), returned=xaf("1800"),
                         status=TicketStatus.SETTLED),
            costs=[Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1"),
                   Cost(xaf("30"), CostKind.WITHDRAWAL_FEE, attributed_to="deposit-1")],
        )
    assert "transfer_fee" in str(raised.value) and "withdrawal_fee" in str(raised.value)


def test_a_cost_that_names_nothing_is_refused_when_it_is_written():
    """Prevents: a cost entering a total under a blank attribution, where the reconciliation
    that catches double counting cannot reach it."""
    with pytest.raises(UnattributedCost):
        Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="")
    with pytest.raises(UnattributedCost):
        Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="   ")


def test_a_settled_result_carrying_two_fees_for_one_transfer_is_refused_before_it_nets_anything():
    """Prevents: net_after_costs() subtracting one deposit fee twice, with no summary involved."""
    with pytest.raises(ConflictingCost):
        settled_cash_result(
            PlacedTicket("t", stake=xaf("1000"), returned=xaf("1800"),
                         status=TicketStatus.SETTLED),
            costs=[Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1"),
                   Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1")],
        )
    # Two costs of DIFFERENT kinds against one thing are two real costs and stay two.
    both = settled_cash_result(
        PlacedTicket("t", stake=xaf("1000"), returned=xaf("1800"), status=TicketStatus.SETTLED),
        costs=[Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1"),
               Cost(xaf("30"), CostKind.TAX, attributed_to="deposit-1")],
    )
    assert both.net_after_costs() == xaf("720")


def test_a_transfer_fee_with_no_reference_to_attribute_it_to_is_refused():
    """Prevents: a fee entering a total under a name nobody can check it against."""
    anonymous = Transfer(TransferDirection.INTO_BETTING_ACCOUNT,
                         TransferStatus.CONFIRMED_RECEIVED,
                         sent=xaf("5050"), credited=xaf("5000"))      # no reference
    with pytest.raises(UnattributedCost):
        summarise_results([anonymous])
    # A transfer that cost nothing has no cost to attribute, so it needs no reference.
    free = Transfer(TransferDirection.OUT_OF_BETTING_ACCOUNT, TransferStatus.CONFIRMED_RECEIVED,
                    sent=xaf("1800"), credited=xaf("1800"))
    assert summarise_results([free]).costs.currencies == ()


def test_the_same_transfer_recorded_twice_in_one_run_is_refused():
    """Prevents: one 5 050 XAF deposit counted as two movements and its fee as 100 XAF."""
    with pytest.raises(DuplicateRecord) as raised:
        summarise_results([confirmed_deposit(), confirmed_deposit()])
    assert "deposit-1" in str(raised.value)


# ----------------------------------------- refusals that existed but were swallowed in totals
def test_a_credit_larger_than_the_send_is_refused_when_summarising_not_reported_as_unknown():
    """Prevents: an unexplained credit being filed as 'cost unknown' instead of being named."""
    over = confirmed_deposit(sent="5000", credited="5500")
    with pytest.raises(UnexplainedCredit):
        summarise_results([over])


def test_a_cross_currency_transfer_is_refused_when_summarising_not_reported_as_unknown():
    """Prevents: an unrecorded conversion hiding inside a total as a missing fee."""
    converted = Transfer(TransferDirection.OUT_OF_BETTING_ACCOUNT,
                         TransferStatus.CONFIRMED_RECEIVED,
                         sent=xaf("5000"), credited=Money.of("EUR", "7.62"), reference="wd-1")
    with pytest.raises(CurrencyMismatch):
        summarise_results([converted])


def test_an_unreadable_transfer_cost_names_the_reason_it_could_not_be_read():
    """Prevents: a summary asserting a reason nobody checked, e.g. calling a confirmed
    transfer 'confirmed_received or missing an amount'."""
    pending = Transfer(TransferDirection.INTO_BETTING_ACCOUNT, TransferStatus.PENDING,
                       sent=xaf("5050"), credited=UNKNOWN, reference="deposit-2")
    half = Transfer(TransferDirection.INTO_BETTING_ACCOUNT, TransferStatus.CONFIRMED_RECEIVED,
                    sent=xaf("5050"), credited=UNKNOWN, reference="deposit-3")

    said = summarise_results([pending, half]).unknowns

    assert "has not been confirmed as received" in said[0], "the pending one, named as pending"
    assert "missing" in said[1], "the confirmed one, named as missing an amount"
    assert "confirmed_received or missing" not in " ".join(said), "no unchecked either/or"


def test_a_written_fee_covers_a_transfer_whose_own_cost_cannot_be_read():
    """Prevents: a total warning that a cost is missing when the reader already supplied it."""
    half = Transfer(TransferDirection.INTO_BETTING_ACCOUNT, TransferStatus.CONFIRMED_RECEIVED,
                    sent=xaf("5050"), credited=UNKNOWN, reference="deposit-3")
    result = settled_cash_result(
        PlacedTicket("t", stake=xaf("1000"), returned=xaf("1800"), status=TicketStatus.SETTLED),
        costs=[Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-3")],
    )

    summary = summarise_results([half, result])

    assert summary.costs.sole() == xaf("50")
    assert summary.transfers_with_unknown_cost == 0, "nothing is missing, so nothing is warned"
    assert summary.costs_deduplicated == 0, "there was only ever one figure"


# ------------------------------------------------------ refusals stated in prose, now in code
def test_a_bare_number_offered_as_an_amount_is_refused_by_name_not_by_a_bare_assertion():
    """Prevents: a stray int reaching a total as an AssertionError that no caller catches,
    or reaching it at all when assertions are stripped."""
    with pytest.raises(NotMoney):
        require_amount(500, "The stake")
    with pytest.raises(MoneySemanticsError):
        CurrencyTotals.of([xaf("100"), 500])
    rate = ExchangeRate("XAF", "EUR", Decimal("0.001524"), "BEAC", date(2026, 9, 19))
    with pytest.raises(NotMoney):
        require_amount(convert_estimate(xaf("5000"), rate), "The stake")


def test_a_money_fact_cannot_be_recorded_as_system_confirmed():
    """Prevents: a figure somebody typed satisfying require_system_confirmed() and being
    shown with 'confirmed by a system' beside it, in a product with no such system."""
    with pytest.raises(NotConfirmable):
        PlacedTicket("t", stake=xaf("1000"), source=FactSource.SYSTEM_CONFIRMED)
    with pytest.raises(NotConfirmable):
        Transfer(TransferDirection.INTO_BETTING_ACCOUNT, TransferStatus.CONFIRMED_RECEIVED,
                 sent=xaf("5050"), credited=xaf("5000"), source=FactSource.SYSTEM_CONFIRMED)
    with pytest.raises(NotConfirmable):
        Funds(xaf("5000"), FundKind.CASH, source=FactSource.SYSTEM_CONFIRMED)
    with pytest.raises(NotConfirmable):
        Cost(xaf("50"), CostKind.TRANSFER_FEE, "deposit-1", FactSource.SYSTEM_CONFIRMED)
    with pytest.raises(NotConfirmable):
        CashResult(xaf("1000"), xaf("1800"), xaf("800"), source=FactSource.SYSTEM_CONFIRMED)
    # Unknown provenance stays allowed: not recording who said so is not the same as lying.
    assert require_not_confirmed(FactSource.UNKNOWN, "This stake") is FactSource.UNKNOWN


def test_a_legs_outcome_may_still_be_system_confirmed_because_a_stored_result_confirms_it():
    """Prevents: the refusal above being widened until a real confirmation cannot be recorded."""
    leg = Leg("leg-1", "home win", LegOutcome.WON, FactSource.SYSTEM_CONFIRMED)
    assert leg.source is FactSource.SYSTEM_CONFIRMED
    # And it does not travel upward: the ticket holding it is still self-reported.
    ticket = PlacedTicket("t", stake=xaf("1000"), returned=xaf("1800"),
                          status=TicketStatus.SETTLED, legs=(leg,))
    assert settled_cash_result(ticket).source is FactSource.SELF_REPORTED
    with pytest.raises(SelfReportedNotConfirmed):
        require_system_confirmed(settled_cash_result(ticket).source, "This result")


def test_a_fee_name_padded_with_spaces_still_meets_its_transfer_and_is_counted_once():
    """Prevents: the deduplicated fee coming back through whitespace. A transfer's reference is
    normalised by _reference_of(), so a written cost naming ' deposit-1 ' used to miss the
    transfer called 'deposit-1' entirely: the written 50 XAF and the derived 50 XAF were both
    added and the worked example fell back to 700 XAF."""
    deposit = confirmed_deposit()                       # reference 'deposit-1', a 50 XAF fee
    padded = Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="  deposit-1  ")
    result = settled_cash_result(
        PlacedTicket("ticket-1", stake=xaf("1000"), returned=xaf("1800"),
                     status=TicketStatus.SETTLED),
        costs=[padded],
    )

    summary = summarise_results([deposit, result])

    assert summary.costs.sole() == xaf("50"), "one fee was paid, whatever it was typed with"
    assert summary.costs_deduplicated == 1
    assert summary.results.sole() - summary.costs.sole() == xaf("750")


def test_two_fee_costs_whose_names_differ_only_in_whitespace_are_refused_not_summed():
    """Prevents: require_unique_fee_attribution() being walked around with a space, so one
    charge written twice under 'deposit-1' and ' deposit-1' enters a total as two."""
    with pytest.raises(ConflictingCost):
        settled_cash_result(
            PlacedTicket("t", stake=xaf("1000"), returned=xaf("1800"),
                         status=TicketStatus.SETTLED),
            costs=[Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to="deposit-1"),
                   Cost(xaf("50"), CostKind.TRANSFER_FEE, attributed_to=" deposit-1")],
        )
