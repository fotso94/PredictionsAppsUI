"""Money semantics: what a figure means, before anybody is allowed to add it up.

Nothing here stores anything, reads anything or talks to anything. There is no journal, no ledger
and no balance in this codebase, and this module does not build one. What it builds is the layer
that would have to be right first: the vocabulary, and the refusals that keep the vocabulary
honest. The prose version, with the reasoning, is ``docs/money-semantics.md``.

The reason it exists as code and not only as a document: every one of these distinctions is the
kind that survives a review and then quietly dies in an expression like ``sum(x.amount for x in
rows)``. A rule that is only written down is a rule that gets averaged away. A rule that raises
does not.

The distinctions this module refuses to collapse:

* a bookmark and an idea are not a placed ticket. Nothing in this product knows that a person put
  money on anything; saving a match is an act of reading, not of spending.
* a transfer is not a result. Moving money into a betting account is not a gain, moving it out is
  not income, and a request to move it is not a receipt.
* a quoted payout is not cash. It is a number a bookmaker printed next to a selection.
* restricted bonus funds are not cash. They may not be withdrawn, so they are not spendable money
  and never enter a cash total.
* a settled cash result is the recorded return minus the stake, with the returned stake handled
  explicitly and costs attributed separately - never folded in silently, because a folded-in cost
  is a cost nobody can see again.
* one charge is counted once. A transfer's fee can be derived from its own sent and credited
  amounts, and the same fee can be written down as a ``Cost`` naming that transfer. Both
  recordings are honest and both are kept; what is refused is adding them. They are reconciled
  by the transfer's reference, and when the two figures disagree the total refuses to exist
  rather than picking one.
* recorded open exposure counts the unresolved stakes recorded HERE. It is not, and must never be
  displayed as, what a person has at risk: what was not recorded is unknown.
* an unmatched leg stays unmatched. A total that balances because a row was dropped is worse than
  no total.
* a missing amount is unknown. It is not zero, it is not a dash, and it is not skipped quietly.

Self-reported versus system-confirmed runs through all of it and is carried on every record as
:class:`FactSource`. This product has no bookmaker integration and no bank connection, so in
practice almost everything about money here would be a person typing what they remember. A figure
a person typed and a figure a system confirmed are both usable, but they are not the same fact and
the code will not let one be presented as the other. Because no system here could confirm a money
fact, the money records refuse ``SYSTEM_CONFIRMED`` outright at construction
(:func:`require_not_confirmed`); a :class:`Leg`'s outcome does not, because a stored match result
genuinely does confirm that one.

Representation. Money is an integer count of minor units plus an ISO currency code
(:class:`Money`), never a float and never a bare number. Three reasons, in order:

1. Float is a defect for currency. ``0.1 + 0.2`` is not ``0.3``, and a rounding drift in somebody's
   money is not a rounding drift, it is a wrong figure. The constructor refuses a ``float``
   outright rather than converting it, because accepting one hides where the drift entered.
2. XAF has no minor unit - 5 050 XAF is 5 050 whole francs, exponent 0 - and that is an argument
   for integers, not for floats. The exponent lives in the currency table, so a 5 050 that means
   francs and a 5 050 that means euro cents can never be mistaken for each other.
3. An integer plus a code cannot be added to the wrong thing by accident, which is the failure this
   whole module exists to prevent. ``Decimal`` would also be exact, but it carries no currency and
   ``Decimal("5050") + Decimal("12.00")`` is a happy, silent, wrong answer.

``Decimal`` is still used for parsing and for exchange rates, where exact decimal text is the input
and no arithmetic crosses currencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union


# ----------------------------------------------------------------------------- refusals
class MoneySemanticsError(Exception):
    """Base class. Every subclass is a refusal to guess, never an internal failure."""


class UnknownCurrency(MoneySemanticsError):
    """A currency code with no known minor-unit exponent. Guessing 2 decimals is how XAF breaks."""


class FloatAmountRefused(MoneySemanticsError):
    """A float was offered as money. Converting it would hide where the drift entered."""


class PrecisionTooFine(MoneySemanticsError):
    """More decimal places than the currency has. Rounding here would invent a figure."""


class CurrencyMismatch(MoneySemanticsError):
    """Two currencies met in one arithmetic operation, or one number was asked of many."""


class AmountUnknown(MoneySemanticsError):
    """A required amount is unknown. Unknown is not zero."""


class NotPlaced(MoneySemanticsError):
    """A bookmark or an idea was treated as a placed ticket. Reading is not spending."""


class NotSettled(MoneySemanticsError):
    """A cash result was asked of something that has not settled."""


class AmbiguousReturn(MoneySemanticsError):
    """The recorded return cannot be read without guessing whether the stake came back."""


class NotReceived(MoneySemanticsError):
    """A transfer that has not been confirmed received was read as money in hand."""


class UnexplainedCredit(MoneySemanticsError):
    """More was credited than was sent. The excess is not a negative cost; name it."""


class NotCash(MoneySemanticsError):
    """Restricted bonus funds, or a quoted payout, were treated as spendable cash."""


class UnmatchedLeg(MoneySemanticsError):
    """A reconciliation does not balance. The unmatched legs are kept, not dropped."""


class UnsourcedConversion(MoneySemanticsError):
    """A currency conversion without a rate, a source and a date is not a conversion."""


class SelfReportedNotConfirmed(MoneySemanticsError):
    """A figure a person typed was about to be presented as one a system confirmed."""


class NotMoney(MoneySemanticsError):
    """Something that is not an amount of money was offered where an amount was required."""


class NotConfirmable(MoneySemanticsError):
    """A money fact was marked system-confirmed. Nothing in this product can confirm one."""


class UnattributedCost(MoneySemanticsError):
    """A cost that names nothing it belongs to cannot be checked against anything."""


class ConflictingCost(MoneySemanticsError):
    """One cost, recorded twice with two different figures. The code may not pick between them."""


class DuplicateRecord(MoneySemanticsError):
    """One record appears twice in a run. Counting it twice is counting the money twice."""


# ----------------------------------------------------------------------------- the unknown
class Unknown:
    """The explicit absence of a figure.

    A separate object rather than ``None`` so that "we never asked", "they left it blank" and
    "it is genuinely zero" stay three different states in the code that reads them.
    """

    _instance: Optional["Unknown"] = None

    def __new__(cls) -> "Unknown":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __str__(self) -> str:
        return "unknown"


UNKNOWN = Unknown()

#: Anywhere a figure may legitimately be absent. ``None`` is accepted and means the same thing.
MaybeMoney = Union["Money", Unknown, None]


def is_unknown(value: MaybeMoney) -> bool:
    """True when a figure is absent. Callers must branch on this, never coerce to zero."""
    return value is None or isinstance(value, Unknown)


def require_amount(value: MaybeMoney, what: str) -> "Money":
    """Return the amount, or refuse. The one function that stands between unknown and 0.

    It refuses two different things, and both are refusals rather than assertions. Unknown is
    not zero. And a value that is not :class:`Money` at all is not an amount: a bare ``500``
    carries no currency, and an :class:`EstimatedMoney` is a converted guess that the module
    keeps out of every total on purpose. An ``assert`` stood here once, which meant callers
    catching :class:`MoneySemanticsError` - the documented way to handle a refusal - never saw
    it, and under ``python -O`` the check was not there at all and the stray value went on to
    fail somewhere further away, or not fail.
    """
    if is_unknown(value):
        raise AmountUnknown(
            f"{what} is unknown. It is not zero: a zero here would be a figure nobody recorded."
        )
    if not isinstance(value, Money):
        raise NotMoney(
            f"{what} is not money; it is a {type(value).__name__}. A bare number carries no "
            f"currency and a converted estimate is not a figure anyone was charged; neither may "
            f"stand in for an amount here."
        )
    return value


# ----------------------------------------------------------------------------- currency table
#: ISO 4217 minor-unit exponents for the currencies this product can plausibly meet. Deliberately
#: short: an unlisted code is refused, because defaulting to 2 decimals silently turns 5 050 XAF
#: into 50.50 of something.
MINOR_UNIT_DIGITS: Dict[str, int] = {
    "XAF": 0,   # Central African CFA franc - Cameroon. No minor unit.
    "XOF": 0,   # West African CFA franc.
    "NGN": 2,
    "GHS": 2,
    "KES": 2,
    "ZAR": 2,
    "MAD": 2,
    "EGP": 2,
    "EUR": 2,
    "USD": 2,
    "GBP": 2,
    "TND": 3,   # three decimals: proof that 2 is not a safe default.
}


def minor_unit_digits(currency: str) -> int:
    """The number of decimal places the currency has, or a refusal."""
    if not isinstance(currency, str) or not currency.strip():
        raise UnknownCurrency("A currency code is required; money without a currency is a number.")
    code = currency.strip().upper()
    if code not in MINOR_UNIT_DIGITS:
        raise UnknownCurrency(
            f"{code} has no known minor-unit exponent here. Add it to MINOR_UNIT_DIGITS with the "
            f"ISO 4217 value rather than assuming two decimals."
        )
    return MINOR_UNIT_DIGITS[code]


# ----------------------------------------------------------------------------- money
@dataclass(frozen=True, order=False)
class Money:
    """An exact amount in one currency, held as whole minor units.

    Construct with :meth:`of` (human amount) or :meth:`minor_units` (already in minor units).
    Neither will take a float: the constructor is deliberately awkward to use with one.
    """

    currency: str
    minor: int

    def __post_init__(self) -> None:
        digits = minor_unit_digits(self.currency)
        object.__setattr__(self, "currency", self.currency.strip().upper())
        if isinstance(self.minor, bool) or not isinstance(self.minor, int):
            raise FloatAmountRefused(
                f"minor units must be a whole int, got {type(self.minor).__name__}. "
                f"Use Money.of({self.currency!r}, \"...\") for a human amount."
            )
        # digits is read here only to force the currency check above to run first.
        assert digits >= 0

    # -- construction
    @classmethod
    def of(cls, currency: str, amount: Union[str, int, Decimal]) -> "Money":
        """Build from a human amount: ``Money.of("XAF", "5050")``, ``Money.of("EUR", "12.50")``."""
        digits = minor_unit_digits(currency)
        if isinstance(amount, float):
            raise FloatAmountRefused(
                "A float is not money. Pass a string, an int or a Decimal: a float amount has "
                "already lost precision by the time it reaches here."
            )
        try:
            dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise MoneySemanticsError(f"{amount!r} is not a readable amount: {exc}") from exc
        if not dec.is_finite():
            raise MoneySemanticsError(f"{amount!r} is not a finite amount.")
        scaled = dec.scaleb(digits)
        if scaled != scaled.to_integral_value():
            raise PrecisionTooFine(
                f"{dec} has more precision than {currency.upper()} has ({digits} decimal "
                f"place(s)). Rounding it here would invent a figure; round it where the rule for "
                f"rounding is known and record that you did."
            )
        return cls(currency, int(scaled))

    @classmethod
    def minor_units(cls, currency: str, minor: int) -> "Money":
        """Build from a count of minor units (francs for XAF, cents for EUR).

        The count is passed through untouched so the constructor's own refusal applies. An
        ``int()`` here would be the one place in the module that quietly converts: ``1.15 * 100``
        is ``114.999...`` in float, and ``int()`` would turn that into 114 cents with nothing
        recorded anywhere to say a centime went missing.
        """
        return cls(currency, minor)

    @classmethod
    def zero(cls, currency: str) -> "Money":
        """A genuine, measured zero. Never use this to stand in for an unknown amount."""
        return cls(currency, 0)

    # -- reading
    @property
    def digits(self) -> int:
        return MINOR_UNIT_DIGITS[self.currency]

    @property
    def amount(self) -> Decimal:
        """The human amount, exactly, as a Decimal. Never a float."""
        return Decimal(self.minor).scaleb(-self.digits)

    def __str__(self) -> str:
        return "{0:.{1}f} {2}".format(self.amount, self.digits, self.currency)

    # -- arithmetic, single currency only
    def _same(self, other: "Money", op: str) -> None:
        if not isinstance(other, Money):
            raise CurrencyMismatch(f"Cannot {op} {type(other).__name__} and money.")
        if other.currency != self.currency:
            raise CurrencyMismatch(
                f"Cannot {op} {self.currency} and {other.currency}. A figure spanning currencies "
                f"is a set of totals, not a number: use total_by_currency()."
            )

    def __add__(self, other: "Money") -> "Money":
        self._same(other, "add")
        return Money(self.currency, self.minor + other.minor)

    def __radd__(self, other: object) -> "Money":
        if isinstance(other, int) and not isinstance(other, bool) and other == 0:
            return self  # lets sum() start, and sum() still refuses at the first mismatch
        raise CurrencyMismatch("Money can only be added to money of the same currency.")

    def __sub__(self, other: "Money") -> "Money":
        self._same(other, "subtract")
        return Money(self.currency, self.minor - other.minor)

    def __neg__(self) -> "Money":
        return Money(self.currency, -self.minor)

    def __lt__(self, other: "Money") -> bool:
        self._same(other, "compare")
        return self.minor < other.minor

    def __le__(self, other: "Money") -> bool:
        self._same(other, "compare")
        return self.minor <= other.minor

    def __gt__(self, other: "Money") -> bool:
        self._same(other, "compare")
        return self.minor > other.minor

    def __ge__(self, other: "Money") -> bool:
        self._same(other, "compare")
        return self.minor >= other.minor

    @property
    def is_zero(self) -> bool:
        return self.minor == 0

    @property
    def is_negative(self) -> bool:
        return self.minor < 0


# ----------------------------------------------------------------------------- totals
@dataclass(frozen=True)
class CurrencyTotals:
    """Totals held one per currency, because a cross-currency total is not a number.

    The object refuses ``int()`` and ``float()`` on purpose: the moment a caller can coerce this to
    a single number, somebody will, and the currency will be whichever one happened to be first.
    """

    by_currency: Tuple[Tuple[str, Money], ...] = ()

    @classmethod
    def of(cls, amounts: Iterable[MaybeMoney], what: str = "amount") -> "CurrencyTotals":
        """Total a run of amounts per currency. Any unknown amount is refused, not skipped."""
        buckets: Dict[str, Money] = {}
        for value in amounts:
            money = require_amount(value, what)
            existing = buckets.get(money.currency)
            buckets[money.currency] = money if existing is None else existing + money
        return cls(tuple(sorted(buckets.items())))

    def __iter__(self):
        return iter(self.by_currency)

    def __len__(self) -> int:
        return len(self.by_currency)

    def __getitem__(self, currency: str) -> Money:
        code = currency.strip().upper()
        for known, money in self.by_currency:
            if known == code:
                return money
        raise KeyError(f"No {code} total recorded. An absent currency is unknown, not zero.")

    @property
    def currencies(self) -> Tuple[str, ...]:
        return tuple(code for code, _ in self.by_currency)

    def get(self, currency: str) -> MaybeMoney:
        """The total in one currency, or UNKNOWN. Never a zero stand-in."""
        try:
            return self[currency]
        except KeyError:
            return UNKNOWN

    def sole(self) -> Money:
        """The single total, when there is exactly one currency. Otherwise a refusal."""
        if len(self.by_currency) != 1:
            raise CurrencyMismatch(
                f"{len(self.by_currency)} currencies here ({', '.join(self.currencies) or 'none'}); "
                f"there is no single figure. Report each currency on its own line."
            )
        return self.by_currency[0][1]

    def __int__(self) -> int:
        raise CurrencyMismatch("A set of totals is not a number. Report each currency separately.")

    def __float__(self) -> float:
        raise CurrencyMismatch("A set of totals is not a number, and money is never a float.")

    def __str__(self) -> str:
        if not self.by_currency:
            return "no recorded amounts"
        return ", ".join(str(money) for _, money in self.by_currency)


# ----------------------------------------------------------------------------- who says so
class FactSource(Enum):
    """Who stands behind a figure. Carried on every record; never inferred."""

    SELF_REPORTED = "self_reported"          # a person typed it from memory or a screenshot
    SYSTEM_CONFIRMED = "system_confirmed"    # a system this product reads produced it
    UNKNOWN = "unknown"                      # provenance itself was not recorded


def require_system_confirmed(source: FactSource, what: str) -> FactSource:
    """Refuse to present a self-reported figure as a confirmed one."""
    if source is not FactSource.SYSTEM_CONFIRMED:
        raise SelfReportedNotConfirmed(
            f"{what} is {source.value}. Say so wherever it is shown; do not present it as "
            f"confirmed."
        )
    return source


def require_not_confirmed(source: FactSource, what: str) -> FactSource:
    """The counterpart refusal: a money fact may not claim a system stood behind it.

    Section 3 of ``docs/money-semantics.md`` lists which facts each source can speak for. Match
    results, leg outcomes and fixture identity are system-confirmed, because this product already
    reads them. Every money fact - that a ticket was placed at all, its stake, its return, a
    transfer's amounts, whether a transfer arrived, bonus terms - is a person typing what they
    remember, because there is no bookmaker integration and no bank or mobile-money connection,
    and none is authorised.

    Marking one of those ``SYSTEM_CONFIRMED`` is not a harmless label. It travels: the record
    then satisfies :func:`require_system_confirmed`, and :func:`provenance_sentence` prints "was
    confirmed by a system" beside a figure somebody typed from memory. That is the exact sentence
    this module exists to prevent, so the refusal belongs at the point the record is built rather
    than in prose that a caller can read and forget.
    """
    if source is FactSource.SYSTEM_CONFIRMED:
        raise NotConfirmable(
            f"{what} cannot be system-confirmed: this product has no bookmaker integration and "
            f"no bank or mobile-money connection, so nothing here could have confirmed it. "
            f"Record it as self_reported, or as unknown when the provenance itself was not "
            f"recorded. A leg's outcome may still be confirmed, from a stored match result; the "
            f"money around it may not."
        )
    return source


def provenance_sentence(source: FactSource, what: str) -> str:
    """The sentence that must accompany a figure whose provenance matters."""
    if source is FactSource.SYSTEM_CONFIRMED:
        return f"{what} was confirmed by a system."
    if source is FactSource.SELF_REPORTED:
        return f"{what} was entered by hand and has not been confirmed by any system."
    return f"It is not recorded where {what.lower()} came from."


# ----------------------------------------------------------------------------- not a bet
@dataclass(frozen=True)
class Bookmark:
    """A saved match. An act of reading. It says nothing about money and never will."""

    match_reference: str
    note: Optional[str] = None


@dataclass(frozen=True)
class Idea:
    """A selection someone is considering. Still not money: nothing has been placed."""

    match_reference: str
    selection: str
    note: Optional[str] = None


# ----------------------------------------------------------------------------- conversion
@dataclass(frozen=True)
class ExchangeRate:
    """A rate is not a number either: without a source and a date it cannot be checked later."""

    base: str
    quote: str
    rate: Decimal
    source: str
    as_of: date

    def __post_init__(self) -> None:
        minor_unit_digits(self.base)
        minor_unit_digits(self.quote)
        if isinstance(self.rate, float):
            raise FloatAmountRefused("An exchange rate must be a Decimal, not a float.")
        if not isinstance(self.rate, Decimal) or not self.rate.is_finite() or self.rate <= 0:
            raise UnsourcedConversion("A rate must be a finite positive Decimal.")
        if not isinstance(self.source, str) or not self.source.strip():
            raise UnsourcedConversion("A rate needs a named source; 'about' is not a source.")
        if not isinstance(self.as_of, date):
            raise UnsourcedConversion("A rate needs the date it was read.")


@dataclass(frozen=True)
class EstimatedMoney:
    """The result of a conversion. Deliberately NOT a :class:`Money`.

    It cannot be added to money, stored as money or shown without its caveat, because a converted
    figure is an estimate on a particular day from a particular source, and it stays one.
    """

    estimate: Money
    original: Money
    rate: ExchangeRate

    def caveat(self) -> str:
        return (
            f"About {self.estimate}, converted from {self.original} at {self.rate.rate} "
            f"({self.rate.source}, {self.rate.as_of.isoformat()}). An estimate, not a figure "
            f"anyone was charged or paid."
        )


def convert_estimate(money: Money, rate: ExchangeRate) -> EstimatedMoney:
    """Convert, and keep the result marked as an estimate. Rounds half-even to the minor unit."""
    if not isinstance(money, Money):
        raise AmountUnknown("Nothing to convert.")
    if money.currency != rate.base:
        raise CurrencyMismatch(f"Rate is {rate.base}->{rate.quote}; the amount is {money.currency}.")
    quote_digits = minor_unit_digits(rate.quote)
    converted = money.amount * rate.rate
    minor = int(converted.scaleb(quote_digits).to_integral_value(rounding="ROUND_HALF_EVEN"))
    return EstimatedMoney(Money(rate.quote, minor), money, rate)


# ----------------------------------------------------------------------------- funds
class FundKind(Enum):
    CASH = "cash"                          # withdrawable money
    RESTRICTED_BONUS = "restricted_bonus"  # credit with conditions; not withdrawable, not cash


@dataclass(frozen=True)
class Funds:
    """An amount held somewhere, with the one attribute that decides whether it is money."""

    amount: MaybeMoney
    kind: FundKind
    source: FactSource = FactSource.SELF_REPORTED
    note: Optional[str] = None

    def __post_init__(self) -> None:
        require_not_confirmed(self.source, "A holding's amount and whether it is withdrawable")


@dataclass(frozen=True)
class QuotedPayout:
    """What a bookmaker printed next to a selection. A quote, not a holding and not a receipt."""

    amount: Money
    selection: Optional[str] = None

    def as_cash(self) -> Money:
        raise NotCash(
            "A quoted payout is not available cash. It is what would be returned if the selection "
            "wins, which is not known."
        )


def cash_amount(funds: Funds) -> Money:
    """The cash in a holding, or a refusal if it is not cash."""
    if funds.kind is FundKind.RESTRICTED_BONUS:
        raise NotCash(
            "Restricted bonus funds are not cash: they cannot be withdrawn, so they are not "
            "money anyone has. Report them on their own line, with their conditions."
        )
    return require_amount(funds.amount, "This holding's amount")


@dataclass(frozen=True)
class HeldFunds:
    """Cash and restricted bonus funds, reported side by side and never summed together."""

    cash: CurrencyTotals
    restricted_bonus: CurrencyTotals
    holdings_with_unknown_amount: int = 0

    def statement(self) -> str:
        parts = [f"Cash: {self.cash}.", f"Bonus credit, which cannot be withdrawn: "
                                        f"{self.restricted_bonus}."]
        if self.holdings_with_unknown_amount:
            parts.append(
                f"{self.holdings_with_unknown_amount} holding(s) have no recorded amount, so they "
                f"are unknown rather than zero."
            )
        return " ".join(parts)


def available_cash(holdings: Sequence[Funds]) -> HeldFunds:
    """Split holdings into cash and bonus credit. Never adds one to the other."""
    cash: List[Money] = []
    bonus: List[Money] = []
    unknown = 0
    for held in holdings:
        if is_unknown(held.amount):
            unknown += 1
            continue
        amount = require_amount(held.amount, "holding amount")
        (bonus if held.kind is FundKind.RESTRICTED_BONUS else cash).append(amount)
    return HeldFunds(CurrencyTotals.of(cash), CurrencyTotals.of(bonus), unknown)


# ----------------------------------------------------------------------------- transfers
class TransferDirection(Enum):
    INTO_BETTING_ACCOUNT = "into_betting_account"   # a deposit
    OUT_OF_BETTING_ACCOUNT = "out_of_betting_account"  # a withdrawal


class TransferStatus(Enum):
    REQUESTED = "requested"                  # asked for; nothing has moved
    PENDING = "pending"                      # in flight
    CONFIRMED_RECEIVED = "confirmed_received"  # arrived, and the arrival was seen
    FAILED = "failed"


@dataclass(frozen=True)
class Transfer:
    """Money moving between two places a person owns. Never a gain and never a loss.

    ``sent`` is what left the sending side; ``credited`` is what arrived. They differ by the cost
    of moving the money - the mobile-money fee - and that difference is a cost, not a result.
    """

    direction: TransferDirection
    status: TransferStatus
    sent: MaybeMoney = UNKNOWN
    credited: MaybeMoney = UNKNOWN
    source: FactSource = FactSource.SELF_REPORTED
    reference: Optional[str] = None

    def __post_init__(self) -> None:
        require_not_confirmed(self.source, "A transfer's amounts and whether it arrived")


def received_amount(transfer: Transfer) -> Money:
    """What actually arrived, or a refusal. A request is not a receipt."""
    if transfer.status is not TransferStatus.CONFIRMED_RECEIVED:
        raise NotReceived(
            f"This transfer is {transfer.status.value}; nothing has been confirmed as received. "
            f"A withdrawal request is not a receipt and must not be shown as money in hand."
        )
    return require_amount(transfer.credited, "The credited amount")


def transfer_cost(transfer: Transfer) -> Money:
    """What moving the money cost: sent minus credited. A cost, never a loss on a bet."""
    credited = received_amount(transfer)
    sent = require_amount(transfer.sent, "The sent amount")
    if sent.currency != credited.currency:
        raise CurrencyMismatch(
            "Sent and credited are in different currencies; the difference is a conversion, not a "
            "cost. Record the rate, its source and its date."
        )
    if credited > sent:
        raise UnexplainedCredit(
            f"{credited} was credited against {sent} sent. The excess is not a negative cost: name "
            f"it, usually as restricted bonus funds."
        )
    return sent - credited


def result_contribution(transfer: Transfer) -> Money:
    """What a transfer contributes to a result: exactly nothing, in its own currency.

    This is a measured zero, not an unknown. A deposit is not a gain; a withdrawal is not income.
    """
    reference = transfer.sent if not is_unknown(transfer.sent) else transfer.credited
    money = require_amount(reference, "This transfer's amount")
    return Money.zero(money.currency)


def _cost_if_known(transfer: Transfer) -> Optional[Money]:
    """The transfer's cost, or ``None`` when the record has not said enough yet.

    ``None`` means exactly two things and nothing else: the transfer has not been confirmed
    received, or one of its two amounts was never recorded. Both are absences.

    It no longer absorbs the refusals :func:`transfer_cost` raises. A credit larger than the send
    and a sent/credited pair in two currencies are not absences - they are things the record
    says, and the module insists both be named (:class:`UnexplainedCredit`, which exists to stop
    a bonus top-up becoming a negative fee, and :class:`CurrencyMismatch`, which exists to stop
    an unsourced conversion hiding in a subtraction). Returning ``None`` for them filed a
    contradiction as a missing figure, so a total that should have refused to exist was published
    with a footnote instead.
    """
    if transfer.status is not TransferStatus.CONFIRMED_RECEIVED:
        return None
    if is_unknown(transfer.sent) or is_unknown(transfer.credited):
        return None
    return transfer_cost(transfer)


def _reference_of(transfer: Transfer) -> Optional[str]:
    """A transfer's reference, or None. A blank one names nothing and is not a name."""
    reference = (transfer.reference or "").strip()
    return reference or None


def _unreadable_cost_reason(transfer: Transfer) -> str:
    """Why this transfer's cost could not be read. Checked, not offered as an either/or."""
    if transfer.status is not TransferStatus.CONFIRMED_RECEIVED:
        return f"has not been confirmed as received (it is {transfer.status.value})"
    missing = [name for name, value in (("sent", transfer.sent), ("credited", transfer.credited))
               if is_unknown(value)]
    return f"is missing its {' and '.join(missing)} amount"


# ----------------------------------------------------------------------------- tickets and legs
class LegOutcome(Enum):
    WON = "won"
    LOST = "lost"
    VOID = "void"
    UNKNOWN = "unknown"


class TicketStatus(Enum):
    OPEN = "open"            # placed, not resolved
    SETTLED = "settled"      # resolved, and the return is known
    UNKNOWN = "unknown"      # recorded, but nobody said what happened to it


class ReturnBasis(Enum):
    """How to read the recorded return figure. Guessing this wrong doubles or halves a result."""

    INCLUDES_STAKE = "includes_stake"   # what the bookmaker shows: stake + profit
    EXCLUDES_STAKE = "excludes_stake"   # profit only, the stake accounted for separately


class CostKind(Enum):
    TRANSFER_FEE = "transfer_fee"
    WITHDRAWAL_FEE = "withdrawal_fee"
    TAX = "tax"
    OTHER = "other"


@dataclass(frozen=True)
class Cost:
    """A cost, attributed to something, kept visible. Never folded into a result."""

    amount: Money
    kind: CostKind
    attributed_to: str
    source: FactSource = FactSource.SELF_REPORTED

    def __post_init__(self) -> None:
        require_not_confirmed(self.source, "A cost")
        if not isinstance(self.attributed_to, str) or not self.attributed_to.strip():
            raise UnattributedCost(
                "A cost must name what it belongs to. A cost attributed to nothing cannot be "
                "checked against the record it came from, and cannot be explained to a reader."
            )
        # Normalised by the SAME rule as a transfer's reference (:func:`_reference_of`), and for
        # the same reason. The two sides of the fee reconciliation are matched by this string, so
        # if only one side strips, " deposit-1 " and "deposit-1" are two names for one charge:
        # the written cost never meets its transfer, the derived fee is added as well, and the
        # 50 XAF is subtracted twice again - the exact defect this module exists to close,
        # walked around by a space. Two fee costs whose names differ only in whitespace would
        # likewise slip past require_unique_fee_attribution(). Whitespace is not part of a name.
        object.__setattr__(self, "attributed_to", self.attributed_to.strip())


#: The cost kinds that a transfer's own ``sent - credited`` arithmetic already represents. A cost
#: of one of these kinds, naming a transfer, is the SAME charge the module would derive from that
#: transfer's two amounts - which is why the two must be reconciled rather than added. Every other
#: kind (a tax, a stake-level charge) is a separate fact that no transfer arithmetic produces.
FEE_KINDS: Tuple[CostKind, ...] = (CostKind.TRANSFER_FEE, CostKind.WITHDRAWAL_FEE)


def require_unique_fee_attribution(costs: Sequence["Cost"], where: str) -> Sequence["Cost"]:
    """One movement of money is charged one fee, so one name may carry at most one fee cost.

    Two fee costs against the same name cannot both be that movement's fee. Either the same
    charge was written down twice, or one of them belongs to something else - and summing them
    is wrong under the first reading while dropping one is wrong under the second. The module
    cannot tell which, so it refuses and asks for the names to be fixed.

    Costs of different kinds against one name are untouched: a transfer fee and a tax on the same
    deposit are two charges and stay two.
    """
    seen: Dict[str, Cost] = {}
    for cost in costs:
        if cost.kind not in FEE_KINDS:
            continue
        # Keyed on the name alone, not on (name, kind): one deposit cannot be charged both a
        # transfer fee and a withdrawal fee, and letting the pair through would leave the two
        # indistinguishable downstream, where only one of them could be matched to the transfer.
        first = seen.get(cost.attributed_to)
        if first is not None:
            raise ConflictingCost(
                f"Two fee costs name {cost.attributed_to!r} in {where}: {first.amount} "
                f"({first.kind.value}) and {cost.amount} ({cost.kind.value}). One movement of "
                f"money is charged one fee, so these cannot both be it: either the charge was "
                f"recorded twice, or one belongs to something else. Adding them counts a cost "
                f"nobody paid; dropping one hides a cost somebody did, and this module may not "
                f"choose which mistake to make on a reader's behalf."
            )
        seen[cost.attributed_to] = cost
    return costs


@dataclass(frozen=True)
class Leg:
    """One selection inside a ticket. Kept individually so a reconciliation can fail loudly."""

    reference: str
    selection: str
    outcome: LegOutcome = LegOutcome.UNKNOWN
    source: FactSource = FactSource.SELF_REPORTED


@dataclass(frozen=True)
class PlacedTicket:
    """A stake a person says was placed with a bookmaker.

    Nothing in this product can confirm one exists. ``source`` says so, on every instance.
    """

    reference: str
    stake: MaybeMoney = UNKNOWN
    returned: MaybeMoney = UNKNOWN
    return_basis: ReturnBasis = ReturnBasis.INCLUDES_STAKE
    stake_returned: Optional[bool] = None
    status: TicketStatus = TicketStatus.OPEN
    legs: Tuple[Leg, ...] = ()
    source: FactSource = FactSource.SELF_REPORTED

    def __post_init__(self) -> None:
        # A leg's outcome can be confirmed from a stored match result, and stays free to say so.
        # That a ticket was placed, for what stake, and what came back, cannot be.
        require_not_confirmed(self.source, "That a ticket was placed, its stake and its return")


def require_placed_ticket(thing: object) -> PlacedTicket:
    """Refuse to read a bookmark or an idea as money that was staked."""
    if isinstance(thing, PlacedTicket):
        return thing
    if isinstance(thing, (Bookmark, Idea)):
        raise NotPlaced(
            f"A {type(thing).__name__.lower()} is not a placed ticket. Saving or considering a "
            f"match says nothing about whether anyone staked anything."
        )
    raise NotPlaced(f"{type(thing).__name__} is not a placed ticket.")


@dataclass(frozen=True)
class CashResult:
    """A settled result: what came back, what went in, and the costs kept beside them."""

    stake: Money
    returned: Money
    net: Money                       # recorded return minus stake, BEFORE any cost
    costs: Tuple[Cost, ...] = ()
    source: FactSource = FactSource.SELF_REPORTED

    def __post_init__(self) -> None:
        require_not_confirmed(self.source, "A settled cash result")
        # Checked here rather than only in summarise_results(), because net_after_costs() would
        # subtract a twice-recorded fee twice with no summary anywhere in sight.
        require_unique_fee_attribution(self.costs, "this result's costs")

    def net_after_costs(self) -> Money:
        """Net with costs subtracted, on request only, and only within one currency."""
        total = self.net
        for cost in self.costs:
            total = total - cost.amount  # refuses across currencies
        return total

    def statement(self) -> str:
        line = f"{self.returned} returned on a {self.stake} stake: {self.net}."
        if self.costs:
            line += (
                f" Costs of {CurrencyTotals.of([c.amount for c in self.costs])} are recorded "
                f"separately and are not included in that figure."
            )
        return line


def settled_cash_result(ticket: PlacedTicket, costs: Sequence[Cost] = ()) -> CashResult:
    """The settled cash result of one ticket, refusing every reading that needs a guess."""
    ticket = require_placed_ticket(ticket)
    if ticket.status is not TicketStatus.SETTLED:
        raise NotSettled(
            f"Ticket {ticket.reference} is {ticket.status.value}. An unresolved ticket has no cash "
            f"result; it is open exposure."
        )
    stake = require_amount(ticket.stake, f"The stake on ticket {ticket.reference}")
    returned = require_amount(ticket.returned, f"The return on ticket {ticket.reference}")
    if stake.currency != returned.currency:
        raise CurrencyMismatch(
            f"Ticket {ticket.reference} was staked in {stake.currency} and returned in "
            f"{returned.currency}. That is a conversion and needs a sourced, dated rate."
        )
    if stake.is_negative or returned.is_negative:
        raise MoneySemanticsError("A stake and a return are both amounts, never negative.")

    if ticket.return_basis is ReturnBasis.INCLUDES_STAKE:
        # The bookmaker's own figure: 1 800 returned on a 1 000 stake is +800. A void returns the
        # stake exactly and nets zero, which falls out of the same subtraction.
        net = returned - stake
    else:
        if ticket.stake_returned is None:
            raise AmbiguousReturn(
                f"Ticket {ticket.reference} records a profit-only figure without saying whether "
                f"the stake came back. The two readings differ by the whole stake, so pick one "
                f"from the record rather than here."
            )
        if not ticket.stake_returned:
            raise AmbiguousReturn(
                f"Ticket {ticket.reference} records a profit-only figure and a stake that did not "
                f"come back. That cannot be read without guessing what the figure covers."
            )
        net = returned
    return CashResult(stake=stake, returned=returned, net=net, costs=tuple(costs),
                      source=ticket.source)


# ----------------------------------------------------------------------------- reconciliation
@dataclass(frozen=True)
class LegReconciliation:
    """What matched, and - the part that matters - what did not."""

    matched: Tuple[Tuple[Leg, Leg], ...] = ()
    unmatched_recorded: Tuple[Leg, ...] = ()
    unmatched_confirmed: Tuple[Leg, ...] = ()

    @property
    def balanced(self) -> bool:
        return not self.unmatched_recorded and not self.unmatched_confirmed

    def statement(self) -> str:
        if self.balanced:
            return f"All {len(self.matched)} leg(s) matched."
        return (
            f"{len(self.matched)} leg(s) matched; {len(self.unmatched_recorded)} recorded and "
            f"{len(self.unmatched_confirmed)} confirmed leg(s) did not. They are kept as they are."
        )


def reconcile_legs(recorded: Sequence[Leg], confirmed: Sequence[Leg]) -> LegReconciliation:
    """Pair legs by reference. Everything unpaired is preserved, never dropped to make it fit."""
    remaining: List[Leg] = list(confirmed)
    matched: List[Tuple[Leg, Leg]] = []
    unmatched_recorded: List[Leg] = []
    for leg in recorded:
        found = None
        for candidate in remaining:
            if candidate.reference == leg.reference:
                found = candidate
                break
        if found is None:
            unmatched_recorded.append(leg)
        else:
            remaining.remove(found)
            matched.append((leg, found))
    return LegReconciliation(tuple(matched), tuple(unmatched_recorded), tuple(remaining))


def require_balanced(reconciliation: LegReconciliation) -> LegReconciliation:
    """Refuse to publish a total built on a reconciliation that does not balance."""
    if not reconciliation.balanced:
        raise UnmatchedLeg(
            f"{reconciliation.statement()} A total that balances by dropping a leg is a wrong "
            f"total presented as a right one."
        )
    return reconciliation


# ----------------------------------------------------------------------------- open exposure
@dataclass(frozen=True)
class OpenExposure:
    """Unresolved RECORDED stakes. Not a person's risk, and it must never be labelled as one."""

    totals: CurrencyTotals
    open_tickets: int = 0
    tickets_with_unknown_stake: int = 0
    tickets_with_unknown_status: int = 0

    def statement(self) -> str:
        parts = [
            f"{self.totals} is staked across {self.open_tickets} unresolved ticket(s) recorded "
            f"here.",
            "Anything not recorded here is unknown, so this is not a total of what is at risk.",
        ]
        if self.tickets_with_unknown_stake:
            parts.append(
                f"{self.tickets_with_unknown_stake} recorded ticket(s) have no stake amount; they "
                f"are unknown, not zero, and are not in the figure above."
            )
        if self.tickets_with_unknown_status:
            parts.append(
                f"{self.tickets_with_unknown_status} recorded ticket(s) do not say whether they "
                f"resolved."
            )
        return " ".join(parts)


def recorded_open_exposure(tickets: Sequence[PlacedTicket]) -> OpenExposure:
    """Total the unresolved recorded stakes, and count everything the total cannot speak for."""
    stakes: List[Money] = []
    open_count = 0
    unknown_stake = 0
    unknown_status = 0
    for ticket in tickets:
        ticket = require_placed_ticket(ticket)
        if ticket.status is TicketStatus.SETTLED:
            continue
        if ticket.status is TicketStatus.UNKNOWN:
            unknown_status += 1
        open_count += 1
        if is_unknown(ticket.stake):
            unknown_stake += 1
            continue
        stakes.append(require_amount(ticket.stake, "stake"))
    return OpenExposure(CurrencyTotals.of(stakes), open_count, unknown_stake, unknown_status)


# ----------------------------------------------------------------------------- summing up
@dataclass(frozen=True)
class ResultSummary:
    """Results and costs, per currency, kept apart; transfers counted but contributing nothing."""

    results: CurrencyTotals
    costs: CurrencyTotals
    transfers_counted: int = 0
    transfers_with_unknown_cost: int = 0
    costs_deduplicated: int = 0
    unknowns: Tuple[str, ...] = field(default_factory=tuple)

    def statement(self) -> str:
        parts = [f"Settled results: {self.results}.", f"Costs, kept separate: {self.costs}."]
        if self.transfers_counted:
            parts.append(
                f"{self.transfers_counted} transfer(s) moved money without changing the result."
            )
        if self.costs_deduplicated:
            parts.append(
                f"{self.costs_deduplicated} fee(s) were recorded both as a written cost and as "
                f"the gap between a transfer's sent and credited amounts; each is one charge and "
                f"is counted once."
            )
        if self.transfers_with_unknown_cost:
            parts.append(
                f"{self.transfers_with_unknown_cost} transfer(s) have no readable cost yet."
            )
        return " ".join(parts)


def summarise_results(events: Iterable[Union[CashResult, Transfer]]) -> ResultSummary:
    """Add up settled results and costs over a run of events, counting nothing twice.

    Two kinds of double count are possible here and both are closed.

    The money. A :class:`Transfer` moves money that a :class:`CashResult` has already accounted
    for - the return credited to a wallet is the same money the settlement recorded - so a
    transfer never adds to results.

    The costs. This module offers two honest ways to record one fee, and the worked example uses
    both: the 50 XAF gap between a 5 050 XAF wallet debit and a 5 000 XAF book credit is derived
    from the :class:`Transfer`'s own two amounts, and the same 50 XAF can be written down as a
    :class:`Cost` naming that transfer. Recorded both ways it used to be subtracted twice, which
    turned the worked example's honest 750 XAF into 700 XAF and made this docstring's own promise
    false. Neither representation is wrong, so neither is refused; instead they are reconciled by
    the transfer's ``reference``:

    * both present and equal - one charge, counted once, and ``costs_deduplicated`` says how
      often that happened so the smaller total is explained rather than mysterious;
    * both present and different - :class:`ConflictingCost`. Two figures for one fee cannot both
      be right and nothing here can tell which is, so the code does not pick. Whichever-came-last
      is not a rule;
    * one present - counted once, which needed no rule;
    * a fee cost naming something that is not a transfer in this run - an ordinary cost. The
      transfer it belongs to may simply not be part of what is being summarised.

    Two refusals make that reconciliation possible rather than decorative. A transfer that
    actually charged something must carry a ``reference``, because a cost attributed to nothing
    cannot be checked against anything - the same rule :class:`Cost` already applies to the
    written representation. And one reference may appear on only one transfer in a run, because
    a reference that names two movements makes both the fee matching and the transfer count
    wrong.
    """
    results: List[Money] = []
    costs: List[Money] = []
    transfers: List[Transfer] = []
    written_fees: Dict[str, Cost] = {}
    all_costs: List[Cost] = []
    seen_references: set = set()
    unreadable = 0
    deduplicated = 0
    unknowns: List[str] = []

    # First pass: sort the run out, and refuse anything that makes the second pass ambiguous.
    for event in events:
        if isinstance(event, CashResult):
            results.append(event.net)
            all_costs.extend(event.costs)
        elif isinstance(event, Transfer):
            reference = _reference_of(event)
            if reference is not None:
                if reference in seen_references:
                    raise DuplicateRecord(
                        f"Transfer {reference!r} appears twice in this run. One reference is one "
                        f"movement of money: counted twice it doubles the transfer count and "
                        f"charges its fee again. If these are two real transfers, give them two "
                        f"references."
                    )
                seen_references.add(reference)
            transfers.append(event)
        else:
            raise MoneySemanticsError(
                f"{type(event).__name__} is neither a settled result nor a transfer. Name it "
                f"before adding it to anything."
            )

    require_unique_fee_attribution(all_costs, "this run")
    for cost in all_costs:
        if cost.kind in FEE_KINDS:
            written_fees[cost.attributed_to] = cost
        else:
            costs.append(cost.amount)

    # Second pass: each transfer's own arithmetic, reconciled against anything written down.
    for transfer in transfers:
        reference = _reference_of(transfer)
        written = written_fees.pop(reference, None) if reference is not None else None
        derived = _cost_if_known(transfer)   # UnexplainedCredit / CurrencyMismatch propagate

        if derived is None:
            if written is not None:
                # The reader supplied the figure the transfer record cannot yet produce. Nothing
                # is missing from the total, so nothing is warned about.
                costs.append(written.amount)
                continue
            unreadable += 1
            unknowns.append(
                f"Transfer {reference or '(no reference)'} "
                f"{_unreadable_cost_reason(transfer)}; its cost is unknown."
            )
            continue

        if written is not None:
            if written.amount != derived:
                raise ConflictingCost(
                    f"Transfer {reference!r} says its fee was {derived} "
                    f"({transfer.sent} sent, {transfer.credited} credited) while a recorded "
                    f"{written.kind.value} against it says {written.amount}. One charge cannot "
                    f"be two figures, and picking either here would be a guess wearing a total's "
                    f"clothes. Correct the record that is wrong."
                )
            deduplicated += 1

        if derived.is_zero:
            continue          # nothing was charged, so there is no cost to attribute or report
        if reference is None:
            raise UnattributedCost(
                f"A transfer of {transfer.sent} credited as {transfer.credited} cost {derived}, "
                f"and has no reference to attribute that cost to. An unattributed cost cannot be "
                f"checked against a written one, so it cannot be told apart from a duplicate, "
                f"and it cannot be explained to a reader. Give the transfer a reference."
            )
        costs.append(derived)

    # Fee costs naming nothing in this run are ordinary costs: the transfer is simply elsewhere.
    costs.extend(cost.amount for cost in written_fees.values())

    return ResultSummary(
        results=CurrencyTotals.of(results),
        costs=CurrencyTotals.of(costs),
        transfers_counted=len(transfers),
        transfers_with_unknown_cost=unreadable,
        costs_deduplicated=deduplicated,
        unknowns=tuple(unknowns),
    )
