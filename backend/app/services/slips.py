"""
Selection slips: building, keeping, recording and reading back a reader's own combinations.

Every method takes the owner and filters on ``user_id`` first; a slip that belongs to somebody else
is a 404 to everyone else, never a 403 that confirms it exists.

THE THREE THINGS A LEG REMEMBERS. The selection it was taken from is copied at the moment of
adding: the probability then on the page, the forecast snapshot behind it, when that forecast was
produced and retrieved, the price if one was given. A forecast the provider revises afterwards
changes none of that. What the reader sees beside it is the CURRENT probability for the same
selection, computed at read time and labelled as current, with ``forecast_changed`` saying whether
the two differ.

MONEY. A stake is optional, is the reader's own figure, and is kept in the currency's minor units
per app/services/money_semantics.py (XAF has none; EUR has two). Potential return is stake x price,
rounded half-up to the minor unit, and is shown as a gross return and a net profit separately; it is
a quoted figure derived from a price the reader typed or the provider carried, and is labelled with
the price's source. Nothing here places, holds or moves money.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session, selectinload

from app.models.predictions import Match, MatchStatus
from app.models.slips import (
    SETTLEMENT_STATES, SLIP_STATUS_DRAFT, SLIP_STATUS_RECORDED, SLIP_STATUS_SAVED, STATE_PENDING,
    SelectionSlip, SelectionSlipLeg,
)
from app.models.users import User
from app.schemas.matches import serialize_league, serialize_score, serialize_team, status_label
from app.services.forecast_markets import envelopes_for_matches
from app.services.forecast_service import ForecastService
from app.services.markets import find_selection, parse_selection_key
from app.services.match_registry import MatchRegistry
from app.services.money_semantics import UnknownCurrency, minor_unit_digits
from app.services.slip_settlement import effective_price, settle_slip

MAX_LEGS_PER_SLIP = 12


class SlipError(Exception):
    """A refusal with an HTTP status and a reason the reader can be shown."""

    def __init__(self, status_code: int, detail: str, code: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _iso(dt: Optional[datetime]) -> Optional[str]:
    aware = _aware(dt)
    return aware.isoformat().replace("+00:00", "Z") if aware else None


# ------------------------------------------------------------------------------ money
def parse_stake(currency: Optional[str], text: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """A stake typed by the reader -> (currency, minor units). Refuses precision the currency lacks."""
    if text is None or str(text).strip() == "":
        return (currency.upper() if currency else None), None
    if not currency:
        raise SlipError(422, "a stake needs a currency", "currency_required")
    code = currency.strip().upper()
    try:
        digits = minor_unit_digits(code)
    except UnknownCurrency:
        raise SlipError(422, f"unknown currency '{code}'", "unknown_currency")
    try:
        amount = Decimal(str(text).strip().replace(",", "."))
    except InvalidOperation:
        raise SlipError(422, "the stake is not a number", "stake_unreadable")
    if amount <= 0:
        raise SlipError(422, "a stake must be above zero", "stake_not_positive")
    scaled = amount * (Decimal(10) ** digits)
    if scaled != scaled.to_integral_value():
        raise SlipError(422, f"{code} has {digits} decimal place{'s' if digits != 1 else ''}; the stake carries more", "stake_precision")
    return code, int(scaled)


def money_text(currency: str, minor: int) -> str:
    digits = minor_unit_digits(currency)
    value = Decimal(minor) / (Decimal(10) ** digits)
    return f"{value:.{digits}f}"


def potential_return(currency: Optional[str], stake_minor: Optional[int], price: Optional[Decimal]) -> Optional[Dict[str, Any]]:
    if not currency or stake_minor is None or price is None:
        return None
    gross_minor = int((Decimal(stake_minor) * price).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return {
        "currency": currency,
        "stake": money_text(currency, stake_minor),
        "gross_return": money_text(currency, gross_minor),
        "net_profit": money_text(currency, gross_minor - stake_minor),
        "rounding": "half-up to the currency's minor unit",
        "note": "a quoted figure from the price given; not money held or promised by this application",
    }


# ------------------------------------------------------------------------------ the service
class SlipService:
    def __init__(self, db: Session, now: Optional[datetime] = None) -> None:
        self.db = db
        self.now = now or datetime.now(timezone.utc)
        self.registry = MatchRegistry(db)
        self.forecasts = ForecastService(db)

    # ----------------------------------------------------------------- reads
    def _query(self, user: User):
        return (self.db.query(SelectionSlip).options(selectinload(SelectionSlip.legs))
                .filter(SelectionSlip.user_id == user.id))

    def get(self, user: User, slip_id: Any) -> SelectionSlip:
        try:
            key = uuid.UUID(str(slip_id))
        except ValueError:
            raise SlipError(404, "slip not found", "not_found")
        slip = self._query(user).filter(SelectionSlip.id == key).first()
        if slip is None:
            raise SlipError(404, "slip not found", "not_found")
        return slip

    def list(self, user: User, status: Optional[str] = None) -> List[SelectionSlip]:
        query = self._query(user)
        if status:
            query = query.filter(SelectionSlip.status == status)
        return query.order_by(SelectionSlip.updated_at.desc()).all()

    # ----------------------------------------------------------------- settlement on read
    def settle(self, slips: Sequence[SelectionSlip]) -> bool:
        """Bring every pending leg up to date with the stored results. Cheap, idempotent, DB only."""
        ids = {leg.match_id for slip in slips for leg in slip.legs}
        if not ids:
            return False
        matches = {m.id: m for m in self.db.query(Match).filter(Match.id.in_(list(ids))).all()}
        changed = False
        for slip in slips:
            changed = settle_slip(slip, matches, self.now) or changed
        if changed:
            self.db.flush()
        return changed

    # ----------------------------------------------------------------- writes
    def create(self, user: User, name: Optional[str], legs: Sequence[Any]) -> SelectionSlip:
        """Validate every leg BEFORE anything is written: a refused leg leaves no half-made slip behind."""
        slip = SelectionSlip(id=uuid.uuid4(), user_id=user.id, name=_clean(name, 120), status=SLIP_STATUS_DRAFT,
                             state=STATE_PENDING)
        built: List[SelectionSlipLeg] = []
        for leg in legs:
            built.append(self._build_leg(slip, built, leg.match_id, leg.selection_id, leg.odds))
        self.db.add(slip)
        for leg in built:
            slip.legs.append(leg)
        self.db.flush()
        return slip

    def _mutable(self, slip: SelectionSlip) -> None:
        if slip.status == SLIP_STATUS_RECORDED:
            raise SlipError(409, "this combination was recorded as placed and is kept as it was; duplicate it to change it",
                            "recorded_immutable")

    def add_leg(self, user: User, slip: SelectionSlip, match_id: str, selection_id: str,
                odds: Optional[float] = None) -> SelectionSlipLeg:
        self._mutable(slip)
        leg = self._build_leg(slip, list(slip.legs), match_id, selection_id, odds)
        slip.legs.append(leg)
        self.db.flush()
        return leg

    def _build_leg(self, slip: SelectionSlip, existing: Sequence[SelectionSlipLeg], match_id: str, selection_id: str,
                   odds: Optional[float]) -> SelectionSlipLeg:
        """Every check, then the row - nothing is added to the session until all of them pass."""
        if len(existing) >= MAX_LEGS_PER_SLIP:
            raise SlipError(409, f"a slip holds at most {MAX_LEGS_PER_SLIP} selections", "too_many_legs")
        resolved = self.registry.resolve_match_id(str(match_id))
        match = self.db.query(Match).filter(Match.id == resolved).first() if resolved else None
        if match is None:
            raise SlipError(404, "match not found", "match_not_found")
        if any(leg.match_id == match.id for leg in existing):
            raise SlipError(409, "this slip already has a selection on that fixture; one selection per match",
                            "one_per_match")
        if match.status != MatchStatus.SCHEDULED or _aware(match.match_date) <= self.now:
            raise SlipError(409, "that fixture has already kicked off; prematch selections close at kickoff", "kickoff_passed")
        parsed = parse_selection_key(selection_id)
        if parsed is None:
            raise SlipError(422, "unreadable selection id", "selection_unreadable")
        envelope = envelopes_for_matches(self.db, [match], self.forecasts, now=self.now)[match.id]
        selection = find_selection(envelope, selection_id)
        if selection is None:
            raise SlipError(422, "no such selection for this fixture", "selection_unknown")
        if not selection.get("available"):
            raise SlipError(422, f"that selection is not available: {selection.get('unavailable_reason')}",
                            "selection_unavailable")
        forecast = envelope["forecast"]
        leg = SelectionSlipLeg(
            id=uuid.uuid4(), slip_id=slip.id, match_id=match.id, position=len(existing),
            provider=envelope["provider"] or "gameforecast",
            snapshot_id=uuid.UUID(forecast["snapshot_id"]) if forecast.get("snapshot_id") else None,
            market_id=selection["market_id"], outcome=selection["outcome"],
            line=Decimal(str(selection["line"])) if selection.get("line") is not None else None,
            period=selection["period"],
            probability=Decimal(str(round(float(selection["probability"]), 5))) if selection.get("probability") is not None else None,
            probability_source=selection["probability_source"], calculation=selection.get("calculation"),
            model_run_at=_naive(_parse(forecast.get("model_run_at"))),
            forecast_fetched_at=_naive(_parse(forecast.get("retrieved_at"))),
            normalisation_version=envelope["normalisation_version"],
            kickoff_at_add=match.match_date, state=STATE_PENDING,
        )
        self._apply_odds(leg, odds, selection.get("odds"))
        return leg

    def _apply_odds(self, leg: SelectionSlipLeg, odds: Optional[float], provider_odds: Optional[Dict[str, Any]]) -> None:
        if odds is not None:
            leg.odds_value = Decimal(str(round(float(odds), 4)))
            leg.odds_source = "user"
            leg.odds_captured_at = _naive(self.now)
        elif provider_odds and provider_odds.get("value"):
            leg.odds_value = Decimal(str(round(float(provider_odds["value"]), 4)))
            leg.odds_source = "provider_snapshot"
            leg.odds_captured_at = _naive(_parse(provider_odds.get("captured_at")))
        else:
            leg.odds_value = None
            leg.odds_source = None
            leg.odds_captured_at = None

    def remove_leg(self, user: User, slip: SelectionSlip, leg_id: Any) -> None:
        self._mutable(slip)
        leg = self._leg(slip, leg_id)
        slip.legs.remove(leg)
        self.db.delete(leg)
        for position, remaining in enumerate(slip.legs):
            remaining.position = position
        self.db.flush()

    def set_leg_odds(self, user: User, slip: SelectionSlip, leg_id: Any, odds: Optional[float]) -> SelectionSlipLeg:
        self._mutable(slip)
        leg = self._leg(slip, leg_id)
        if odds is None:
            leg.odds_value, leg.odds_source, leg.odds_captured_at = None, None, None
        else:
            leg.odds_value = Decimal(str(round(float(odds), 4)))
            leg.odds_source = "user"
            leg.odds_captured_at = _naive(self.now)
        self.db.flush()
        return leg

    def _leg(self, slip: SelectionSlip, leg_id: Any) -> SelectionSlipLeg:
        try:
            key = uuid.UUID(str(leg_id))
        except ValueError:
            raise SlipError(404, "leg not found", "leg_not_found")
        for leg in slip.legs:
            if leg.id == key:
                return leg
        raise SlipError(404, "leg not found", "leg_not_found")

    def update(self, user: User, slip: SelectionSlip, *, name: Optional[str] = None, note: Optional[str] = None,
               status: Optional[str] = None, currency: Optional[str] = None, stake: Optional[str] = None,
               fields_set: Iterable[str] = ()) -> SelectionSlip:
        fields = set(fields_set)
        if fields & {"status", "currency", "stake"}:
            self._mutable(slip)
        new_name = _clean(name, 120) if "name" in fields else slip.name
        new_status = slip.status
        if "status" in fields and status:
            if status not in (SLIP_STATUS_DRAFT, SLIP_STATUS_SAVED):
                raise SlipError(422, "status may be draft or saved", "bad_status")
            if status == SLIP_STATUS_SAVED and not new_name:
                raise SlipError(422, "a saved combination needs a name", "name_required")
            new_status = status
        new_currency, new_stake = slip.currency, slip.stake_minor
        if "currency" in fields or "stake" in fields:
            code = (currency if "currency" in fields else slip.currency)
            text = stake if "stake" in fields else (money_text(slip.currency, slip.stake_minor)
                                                     if slip.currency and slip.stake_minor is not None else None)
            new_currency, new_stake = parse_stake(code, text)
        # Every refusal above happened before this line; nothing is half-applied.
        slip.name = new_name
        if "note" in fields:
            slip.note = _clean(note, 2000)
        slip.status = new_status
        slip.currency, slip.stake_minor = new_currency, new_stake
        self.db.flush()
        return slip

    def record(self, user: User, slip: SelectionSlip, *, reference: Optional[str] = None, currency: Optional[str] = None,
               stake: Optional[str] = None, price: Optional[float] = None) -> SelectionSlip:
        self._mutable(slip)
        if not slip.legs:
            raise SlipError(409, "nothing to record: the slip has no selections", "no_legs")
        finished = [leg for leg in slip.legs if self._match(leg.match_id).status == MatchStatus.FINISHED]
        if finished:
            raise SlipError(409, "a fixture on this slip has already been played; a bet on it cannot be recorded now",
                            "fixture_finished")
        if currency is not None or stake is not None:
            slip.currency, slip.stake_minor = parse_stake(currency or slip.currency, stake)
        if price is not None:
            slip.price = Decimal(str(round(float(price), 4)))
            slip.price_source = "user"
        else:
            computed, source, _missing = effective_price(slip.legs)
            slip.price, slip.price_source = computed, source
        slip.recorded_reference = _clean(reference, 120)
        slip.recorded_at = _naive(self.now)
        slip.status = SLIP_STATUS_RECORDED
        self.db.flush()
        return slip

    def duplicate(self, user: User, slip: SelectionSlip) -> SelectionSlip:
        copy = SelectionSlip(id=uuid.uuid4(), user_id=user.id, name=slip.name, status=SLIP_STATUS_DRAFT,
                             note=slip.note, currency=slip.currency, stake_minor=slip.stake_minor, state=STATE_PENDING)
        self.db.add(copy)
        self.db.flush()
        for leg in slip.legs:
            twin = SelectionSlipLeg(
                id=uuid.uuid4(), slip_id=copy.id, match_id=leg.match_id, position=leg.position, provider=leg.provider,
                snapshot_id=leg.snapshot_id, market_id=leg.market_id, outcome=leg.outcome, line=leg.line, period=leg.period,
                probability=leg.probability, probability_source=leg.probability_source, calculation=leg.calculation,
                model_run_at=leg.model_run_at, forecast_fetched_at=leg.forecast_fetched_at,
                normalisation_version=leg.normalisation_version, odds_value=leg.odds_value, odds_source=leg.odds_source,
                odds_captured_at=leg.odds_captured_at, kickoff_at_add=leg.kickoff_at_add, state=STATE_PENDING,
            )
            copy.legs.append(twin)
        self.db.flush()
        return copy

    def delete(self, user: User, slip: SelectionSlip) -> None:
        self._mutable(slip)
        self.db.delete(slip)
        self.db.flush()

    def _match(self, match_id: Any) -> Match:
        match = self.db.query(Match).filter(Match.id == match_id).first()
        if match is None:
            raise SlipError(404, "match not found", "match_not_found")
        return match

    # ----------------------------------------------------------------- serialisation
    def serialize_many(self, slips: Sequence[SelectionSlip]) -> List[Dict[str, Any]]:
        ids = list({leg.match_id for slip in slips for leg in slip.legs})
        matches = {m.id: m for m in self.db.query(Match).filter(Match.id.in_(ids)).all()} if ids else {}
        rows = list(matches.values())
        teams = self.registry.team_names(rows) if rows else {}
        leagues = self.registry.leagues_by_id(rows) if rows else {}
        current = envelopes_for_matches(self.db, rows, self.forecasts, now=self.now) if rows else {}
        return [self._serialize(slip, matches, teams, leagues, current) for slip in slips]

    def serialize(self, slip: SelectionSlip) -> Dict[str, Any]:
        return self.serialize_many([slip])[0]

    def _serialize(self, slip: SelectionSlip, matches: Dict, teams: Dict, leagues: Dict, current: Dict) -> Dict[str, Any]:
        legs = [self._serialize_leg(leg, matches.get(leg.match_id), teams, leagues, current.get(leg.match_id))
                for leg in sorted(slip.legs, key=lambda l: l.position)]
        computed, source, missing = effective_price(slip.legs)
        if slip.status == SLIP_STATUS_RECORDED and slip.price is not None:
            price, price_source = Decimal(slip.price), slip.price_source
        else:
            price, price_source = computed, source
        counts = {state: sum(1 for leg in slip.legs if leg.state == state) for state in SETTLEMENT_STATES}
        counts["legs"] = len(slip.legs)
        return {
            "id": str(slip.id), "name": slip.name, "status": slip.status, "note": slip.note,
            "currency": slip.currency,
            "stake": money_text(slip.currency, slip.stake_minor) if slip.currency and slip.stake_minor is not None else None,
            "price": float(price) if price is not None else None, "price_source": price_source,
            "price_missing_legs": missing,
            "price_note": ("the product of the legs' prices; a void leg drops out of it" if price is not None and price_source != "user"
                           else "the combined price the reader recorded" if price is not None else
                           "no combined price: at least one selection has no price for exactly that selection"),
            "potential": potential_return(slip.currency, slip.stake_minor, price),
            "recorded_at": _iso(slip.recorded_at), "recorded_reference": slip.recorded_reference,
            "recorded_note": ("the reader's own statement that this was placed elsewhere; nothing here is confirmed by any bookmaker"
                              if slip.status == SLIP_STATUS_RECORDED else None),
            "state": slip.state, "settled_at": _iso(slip.settled_at), "counts": counts,
            "created_at": _iso(slip.created_at), "updated_at": _iso(slip.updated_at),
            "legs": legs,
        }

    def _serialize_leg(self, leg: SelectionSlipLeg, match: Optional[Match], teams: Dict, leagues: Dict,
                       envelope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        selection_id = f"{leg.market_id}:{leg.outcome}" + (f"@{float(leg.line):g}" if leg.line is not None else "")
        live = find_selection(envelope, selection_id) if envelope else None
        stored = float(leg.probability) if leg.probability is not None else None
        live_probability = live.get("probability") if live else None
        changed = (live_probability is not None and stored is not None and abs(live_probability - stored) > 0.00005) \
            or (live is not None and not live.get("available"))
        kickoff = _aware(match.match_date) if match else _aware(leg.kickoff_at_add)
        body = {
            "id": str(leg.id), "position": leg.position,
            "match": self._match_summary(match, teams, leagues) if match else {"id": str(leg.match_id)},
            "selection": {"selection_id": selection_id, "market_id": leg.market_id, "outcome": leg.outcome,
                          "line": float(leg.line) if leg.line is not None else None, "period": leg.period},
            "probability": stored, "probability_source": leg.probability_source, "calculation": leg.calculation,
            "provider": leg.provider, "snapshot_id": str(leg.snapshot_id) if leg.snapshot_id else None,
            "model_run_at": _iso(leg.model_run_at), "forecast_fetched_at": _iso(leg.forecast_fetched_at),
            "normalisation_version": leg.normalisation_version,
            "odds": ({"value": float(leg.odds_value), "format": "decimal", "source": leg.odds_source,
                      "captured_at": _iso(leg.odds_captured_at)} if leg.odds_value is not None else None),
            "kickoff_utc": _iso(kickoff), "started": bool(kickoff and kickoff <= self.now),
            "current": {
                "probability": live_probability, "available": bool(live and live.get("available")),
                "forecast_changed": bool(changed),
                "state": (envelope or {}).get("forecast", {}).get("state"),
            },
            "state": leg.state, "settled_at": _iso(leg.settled_at), "settlement": leg.settlement,
            "settlement_capability": (live or {}).get("settlement") if live else None,
        }
        return body

    @staticmethod
    def _match_summary(match: Match, teams: Dict, leagues: Dict) -> Dict[str, Any]:
        meta = match.match_metadata or {}
        return {
            "id": str(match.id),
            "home": serialize_team(teams.get(match.home_team_id)), "away": serialize_team(teams.get(match.away_team_id)),
            "competition": serialize_league(leagues.get(match.league_id)),
            "kickoff_utc": _iso(match.match_date), "status": status_label(match), "minute": meta.get("minute"),
            "score": serialize_score(meta),
        }


def _clean(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
