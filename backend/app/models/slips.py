"""
Selection slips: a reader's own combination of forecast selections, and what became of it.

Two tables in the ``users`` schema, beside ``saved_matches``, because a slip is personal data in
exactly the way a saved match's note is: it belongs to its author alone, every query is filtered on
``user_id`` before anything else, and nothing aggregates it.

- selection_slips: the combination. Three statuses, which are three different claims:
    draft     being built; nothing is asserted about it.
    saved     named and kept; still editable.
    recorded  the reader says they placed it, elsewhere, with their own bookmaker. From that moment
              the legs, the price and the stake are history and are never rewritten: an edit is a
              new draft (``duplicate``), not a change to what was recorded. This product does not
              place bets, hold funds or confirm that any bet exists - ``recorded`` is the reader's
              own statement (money_semantics.FactSource.SELF_REPORTED) and is served as such.
- selection_slip_legs: one selection per fixture. UNIQUE(slip_id, match_id) is the "one selection
  per match" rule as a constraint rather than a convention, and it is also what makes duplicate and
  contradictory legs impossible inside one slip: two selections on one fixture cannot exist.

Every leg copies what it was taken from - the probability the provider published at the moment it
was added, the forecast snapshot it came from, when that forecast was produced and retrieved, and
the normalisation version that read it - so a forecast the provider later revises never silently
changes a selection a reader already made. The current probability is compared at read time and
served beside the stored one; it never replaces it.
"""

from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, uuid_fk

SLIP_STATUS_DRAFT = "draft"
SLIP_STATUS_SAVED = "saved"
SLIP_STATUS_RECORDED = "recorded"
SLIP_STATUSES = (SLIP_STATUS_DRAFT, SLIP_STATUS_SAVED, SLIP_STATUS_RECORDED)

#: Settlement states shared by a leg and by the slip as a whole.
STATE_PENDING = "pending"
STATE_WON = "won"
STATE_LOST = "lost"
STATE_VOID = "void"
STATE_UNRESOLVED = "unresolved"
SETTLEMENT_STATES = (STATE_PENDING, STATE_WON, STATE_LOST, STATE_VOID, STATE_UNRESOLVED)


class SelectionSlip(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "selection_slips"
    __table_args__ = (
        Index('idx_selection_slips_user_status', 'user_id', 'status', 'updated_at'),
        {'schema': 'users', 'comment': "A reader's own combination of forecast selections; private to its author"}
    )

    user_id = uuid_fk('users.users.id', nullable=False, fk_kwargs={'ondelete': 'CASCADE'},
                      comment="Owner; every read and write is filtered on this first")
    name = Column(String(120), comment="The reader's own name for the combination")
    status = Column(String(20), nullable=False, default=SLIP_STATUS_DRAFT,
                    comment="draft | saved | recorded (recorded is immutable)")
    note = Column(Text, comment="The owner's private note; never returned to another user")

    # Optional money, in the reader's own currency and minor units (see app/services/money_semantics.py:
    # XAF has no minor unit, EUR has two; the exponent lives in the currency table, never here).
    currency = Column(String(3), comment="ISO 4217 code of the stake, when one was entered")
    stake_minor = Column(BigInteger, comment="Stake in the currency's minor units; NULL when none was entered")

    # The combined decimal price at the moment the slip was recorded, and where the prices came from.
    # Only computed when every leg carried a price for exactly its selection; never invented.
    price = Column(DECIMAL(12, 4), comment="Combined decimal price recorded for the slip; NULL when any leg had no price")
    price_source = Column(String(20), comment="user | provider_snapshot | mixed; NULL when no price")

    recorded_at = Column(DateTime, comment="When the reader said they placed this elsewhere (UTC)")
    recorded_reference = Column(String(120), comment="The reader's own reference for the placed bet, if any")

    state = Column(String(20), nullable=False, default=STATE_PENDING,
                   comment="pending | won | lost | void | unresolved, aggregated from the legs")
    settled_at = Column(DateTime, comment="When every leg reached a final state (UTC)")

    user = relationship("User")
    legs = relationship("SelectionSlipLeg", back_populates="slip", cascade="all, delete-orphan",
                        order_by="SelectionSlipLeg.position")


class SelectionSlipLeg(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "selection_slip_legs"
    __table_args__ = (
        UniqueConstraint('slip_id', 'match_id', name='uq_selection_slip_legs_slip_match'),
        Index('idx_selection_slip_legs_match', 'match_id'),
        Index('idx_selection_slip_legs_state', 'state'),
        {'schema': 'users', 'comment': 'One selection on one fixture inside a slip'}
    )

    slip_id = uuid_fk('users.selection_slips.id', nullable=False, fk_kwargs={'ondelete': 'CASCADE'})
    match_id = uuid_fk('predictions.matches.id', nullable=False, fk_kwargs={'ondelete': 'CASCADE'})
    position = Column(Integer, nullable=False, default=0, comment="Display order inside the slip")

    provider = Column(String(50), nullable=False, comment="Forecast provider the selection was read from")
    snapshot_id = uuid_fk('predictions.provider_forecast_snapshots.id', nullable=True,
                          fk_kwargs={'ondelete': 'SET NULL'},
                          comment="The forecast snapshot the probability was read from, when one was identified")

    market_id = Column(String(40), nullable=False)
    outcome = Column(String(20), nullable=False)
    line = Column(DECIMAL(4, 2), comment="The goals line for a totals market; NULL otherwise")
    period = Column(String(20), nullable=False, comment="regulation | first_half")

    probability = Column(DECIMAL(6, 5), comment="The probability shown when the leg was added (0-1); NULL when none was published")
    probability_source = Column(String(20), nullable=False, comment="provider | calculated")
    calculation = Column(JSONB, comment="Formula and inputs of a calculated probability; NULL for a provider one")
    model_run_at = Column(DateTime, comment="When the provider's model produced the forecast (UTC)")
    forecast_fetched_at = Column(DateTime, comment="When this installation retrieved that forecast (UTC)")
    normalisation_version = Column(String(20), nullable=False)

    odds_value = Column(DECIMAL(10, 4), comment="Decimal price for exactly this selection, if one was given")
    odds_source = Column(String(20), comment="user | provider_snapshot")
    odds_captured_at = Column(DateTime, comment="When that price was quoted or entered (UTC)")

    kickoff_at_add = Column(DateTime, comment="The fixture's kickoff known when the leg was added (UTC)")

    state = Column(String(20), nullable=False, default=STATE_PENDING)
    settled_at = Column(DateTime)
    settlement = Column(JSONB, comment="How the state was reached: rule, basis, what happened, or why it could not be settled")

    slip = relationship("SelectionSlip", back_populates="legs")
