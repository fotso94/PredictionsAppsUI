"""
Expert Prediction Service

Handles expert prediction creation, overrides, and management.
"""

import logging
from typing import Iterable, List, Optional, Dict, Any, Tuple
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import uuid

from app.models.predictions import (
    Prediction,
    PredictionAudit,
    PredictionSource,
    PredictionStatus,
    PredictionOverride,
    Match,
    Team,
    League
)
from app.models.users import User
from app.schemas.matches import iso_utc
from app.schemas.predictions import (
    ExpertPredictionCreate,
    ExpertPredictionOverride,
    ExpertPredictionUpdate,
)
from app.services.prediction_cache import PredictionCacheService

logger = logging.getLogger(__name__)

#: `action` written on the append-only revision rows in predictions.prediction_audit. Editing a
#: published prediction rewrites the live row, so without this the version readers saw before the
#: correction would be gone for good.
REVISION_ACTION = "updated"

#: `action` written when a prediction is taken off the public lists or put back on them. Kept
#: distinct from REVISION_ACTION so that settlement's "what stood at kickoff" restore, which reads
#: revisions, is not handed a row that changed no probability.
PUBLICATION_ACTION = "publication_changed"

#: The values that make up a published expert view. A revision preserves all of them, so an earlier
#: version can be read back in full rather than inferred from a diff.
REVISION_VALUE_FIELDS: Tuple[str, ...] = (
    "home_win_prob", "draw_prob", "away_win_prob", "confidence_score",
    "btts_yes_prob", "btts_no_prob", "btts_confidence",
    "total_goals_over_25_prob", "total_goals_under_25_prob",
    "total_goals_over_35_prob", "total_goals_under_35_prob", "total_goals_confidence",
)


class ForeignExpertRecord(Exception):
    """Raised when an expert tries to attach an override to another expert's published record."""


class ClassificationNotAllowed(Exception):
    """Raised when test-data classification is asked for on an installation that does not allow it."""


class RecordClosed(Exception):
    """Raised when a change is refused because the match has already kicked off.

    The measured record closes at kickoff. An expert may still take a prediction down afterwards,
    and it stays scored; what they may not do is reach into the record with a new version and
    claim the fixture for it.
    """


def _decimal_to_float(value) -> Optional[float]:
    return float(value) if value is not None else None


def test_data_classification(requested: Optional[bool]) -> Optional[bool]:
    """Whether to stamp a new record as test data, given what the request asked for.

    Returns TRUE only when the caller explicitly asked AND the installation allows classification
    (``ALLOW_TEST_DATA_CLASSIFICATION``, off by default). Otherwise the record stays unclassified -
    NULL, meaning "nobody has said", which is the honest state and not the same claim as FALSE.

    Everything about this is deliberate. The flag decides whether a record is left out of measured
    performance, so if an ordinary deployment honoured the request an expert could exclude their
    own losses from the leaderboard just by asking. The gate is what makes the mechanism safe;
    being a column rather than a substring of the reasoning text is what makes it exact.
    """
    if not requested:
        return None
    from app.core.config import settings
    if not settings.ALLOW_TEST_DATA_CLASSIFICATION:
        logger.warning("test-data classification was requested but ALLOW_TEST_DATA_CLASSIFICATION "
                       "is off; the record is stored unclassified")
        return None
    return True


def prediction_snapshot(prediction: Prediction) -> Dict[str, Any]:
    """Every published value of one prediction, as JSON, with the times that version carried.

    Stored on both sides of an edit so the earlier version stays retrievable with its own
    ``published_at`` - "this is what was on screen, and this is when" - rather than only as a
    description of what changed.
    """
    metadata = prediction.prediction_metadata or {}
    snapshot: Dict[str, Any] = {
        name: _decimal_to_float(getattr(prediction, name)) for name in REVISION_VALUE_FIELDS}
    snapshot.update({
        "reasoning": prediction.reasoning,
        "key_factors": metadata.get("key_factors"),
        "status": prediction.status.value if hasattr(prediction.status, "value") else str(prediction.status),
        "published_at": iso_utc(prediction.published_at),
        "created_at": iso_utc(prediction.created_at),
        "updated_at": iso_utc(prediction.updated_at),
    })
    return snapshot


def _changes_summary(old: Dict[str, Any], new: Dict[str, Any]) -> str:
    """Human-readable list of what the edit changed. Empty string when nothing of substance did."""
    changed = []
    for name in REVISION_VALUE_FIELDS + ("reasoning", "key_factors"):
        if old.get(name) != new.get(name):
            if name in ("reasoning", "key_factors"):
                changed.append(f"{name} changed")
            else:
                changed.append(f"{name} {old.get(name)} -> {new.get(name)}")
    return "; ".join(changed)


class ExpertPredictionService:
    """
    Service for managing expert predictions.
    
    Handles:
    - Creating manual expert predictions
    - Overriding existing predictions (ML/API-Football)
    - Managing prediction lifecycle (pending → approved → published)
    - Tracking prediction supersession
    """
    
    def __init__(self, db: Session, cache_service: Optional[PredictionCacheService] = None):
        """
        Initialize ExpertPredictionService
        
        Args:
            db: Database session
            cache_service: Optional cache service
        """
        self.db = db
        self.cache_service = cache_service or PredictionCacheService()
    
    @staticmethod
    def _initial_status() -> PredictionStatus:
        """Experts publish directly (EXPERT_DIRECT_PUBLISH=True); otherwise predictions wait for review."""
        from app.core.config import settings
        return PredictionStatus.PUBLISHED if settings.EXPERT_DIRECT_PUBLISH else PredictionStatus.PENDING

    @staticmethod
    def _initial_published_at():
        from app.core.config import settings
        return datetime.utcnow() if settings.EXPERT_DIRECT_PUBLISH else None

    def create_manual_prediction(
        self,
        data: ExpertPredictionCreate,
        expert_user: User
    ) -> Prediction:
        """
        Create a manual expert prediction from scratch.
        
        Args:
            data: Prediction data
            expert_user: Expert user creating the prediction
        
        Returns:
            Created Prediction object
        """
        logger.info(f"Creating manual prediction for match {data.match_id} by expert {expert_user.id}")

        # Phase 1 providers (Live Score API / GameForecastAPI / fallbacks): resolve the identifier
        # through the match registry first. This accepts an internal match UUID, any provider's
        # fixture id recorded in predictions.provider_entity_refs, or a legacy external_api_id, so
        # expert predictions stay attached to the same internal match whichever provider is active.
        match_uuid = None
        try:
            from app.services.match_registry import MatchRegistry
            match_uuid = MatchRegistry(self.db).resolve_match_id(str(data.match_id))
        except Exception as exc:  # registry tables missing (pre-migration) must not block experts
            logger.warning(f"Match registry lookup failed for {data.match_id}: {exc}")

        if match_uuid is None:
            # Legacy path (retained): API-Football numeric ids are mapped to a deterministic UUID
            # and the match row is created from API-Football data or as a placeholder.
            try:
                match_uuid = uuid.UUID(data.match_id)
            except ValueError:
                # If it's not a valid UUID, create a deterministic UUID from the match ID
                # This ensures the same match ID always maps to the same UUID
                namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')  # DNS namespace UUID
                match_uuid = uuid.uuid5(namespace, str(data.match_id))
                logger.info(f"Converted match_id {data.match_id} to UUID {match_uuid}")

            # Ensure match exists in database
            self._ensure_match_exists(match_uuid, str(data.match_id))

        # Create prediction
        prediction = Prediction(
            id=uuid.uuid4(),
            match_id=match_uuid,
            source=PredictionSource.EXPERT_MANUAL,
            priority_level=100,  # Expert predictions have highest priority
            created_by=expert_user.id,
            # Match Outcome (1X2)
            home_win_prob=Decimal(str(data.home_win_prob)),
            draw_prob=Decimal(str(data.draw_prob)),
            away_win_prob=Decimal(str(data.away_win_prob)),
            confidence_score=Decimal(str(data.confidence_score)) if data.confidence_score else Decimal("0.0"),
            # Both Teams to Score (BTTS) - Optional
            btts_yes_prob=Decimal(str(data.btts_yes_prob)) if data.btts_yes_prob is not None else None,
            btts_no_prob=Decimal(str(data.btts_no_prob)) if data.btts_no_prob is not None else None,
            btts_confidence=Decimal(str(data.btts_confidence)) if data.btts_confidence is not None else None,
            # Total Goals - Optional
            total_goals_over_25_prob=Decimal(str(data.total_goals_over_25_prob)) if data.total_goals_over_25_prob is not None else None,
            total_goals_under_25_prob=Decimal(str(data.total_goals_under_25_prob)) if data.total_goals_under_25_prob is not None else None,
            total_goals_over_35_prob=Decimal(str(data.total_goals_over_35_prob)) if data.total_goals_over_35_prob is not None else None,
            total_goals_under_35_prob=Decimal(str(data.total_goals_under_35_prob)) if data.total_goals_under_35_prob is not None else None,
            total_goals_confidence=Decimal(str(data.total_goals_confidence)) if data.total_goals_confidence is not None else None,
            # Reasoning & Metadata
            reasoning=data.reasoning,
            status=self._initial_status(),
            published_at=self._initial_published_at(),
            is_test_data=test_data_classification(data.is_test_data),
            prediction_metadata={
                "key_factors": data.key_factors or {},
                "created_via": "expert_manual",
                "external_match_id": data.match_id,  # Store original match ID
            }
        )
        
        self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)
        
        logger.info(f"Created manual prediction {prediction.id} for match {data.match_id}")
        
        # Invalidate cache for this match
        self._invalidate_match_cache(data.match_id)
        
        return prediction
    
    #: Sources whose predictions an expert is entitled to supersede. This is what the endpoint has
    #: always said it did ("override ML/API-Football/LLM predictions"); until now it checked
    #: nothing, so any verified expert could attach a supersession to any row in the table -
    #: another expert's published work included.
    OVERRIDABLE_SOURCES = (
        PredictionSource.ML_BASELINE,
        PredictionSource.API_FOOTBALL_BASELINE,
        PredictionSource.LLM_GENERATED,
        PredictionSource.DEFAULT_RANDOMIZED,
    )

    def _check_override_allowed(self, original: Prediction, expert_user: User) -> None:
        """Refuse an override that would rewrite somebody else's record, or a closed one.

        Two rules, and neither of them adds an approval step - an expert still publishes, edits
        and withdraws their own work without anyone's sign-off:

        * an expert may supersede a model's prediction (that is the feature) or their own, but not
          another expert's. Superseding is the quietest way to take a prediction out of the public
          view, so being able to do it to a colleague's record is the ability to edit someone
          else's published history;
        * nothing may be superseded once the match has kicked off. After kickoff the record is
          closed: the original keeps being scored on what it said beforehand, and a replacement
          written now is not prematch evidence of anything. Refusing here is clearer than
          accepting the write and silently refusing to score it.
        """
        if (original.source not in self.OVERRIDABLE_SOURCES
                and original.created_by != expert_user.id):
            raise ForeignExpertRecord(
                "This prediction belongs to another expert. You can override a model prediction "
                "or your own, but not another expert's published record.")

        match = self.db.query(Match).filter(Match.id == original.match_id).first()
        if match is not None and match.match_date is not None \
                and match.match_date <= datetime.utcnow():
            raise RecordClosed(
                "This match has already kicked off, so the prediction record is closed. The "
                "prediction stays scored on what it said before kickoff; it cannot be superseded "
                "now.")

    def override_prediction(
        self,
        data: ExpertPredictionOverride,
        expert_user: User
    ) -> Prediction:
        """
        Override an existing prediction (ML/API-Football/LLM).
        
        Creates a new expert prediction and marks the original as superseded.
        
        Args:
            data: Override data
            expert_user: Expert user creating the override
        
        Returns:
            New expert prediction
        
        Raises:
            ValueError: If original prediction not found
        """
        logger.info(f"Overriding prediction {data.prediction_id} by expert {expert_user.id}")
        
        # Get original prediction
        original_prediction = self.db.query(Prediction).filter(
            Prediction.id == uuid.UUID(data.prediction_id)
        ).first()
        
        if not original_prediction:
            raise ValueError(f"Prediction {data.prediction_id} not found")

        self._check_override_allowed(original_prediction, expert_user)

        # Create new expert override prediction
        override_prediction = Prediction(
            id=uuid.uuid4(),
            match_id=original_prediction.match_id,
            source=PredictionSource.EXPERT_OVERRIDE,
            priority_level=100,  # Expert overrides have highest priority
            created_by=expert_user.id,
            # Match Outcome (1X2)
            home_win_prob=Decimal(str(data.home_win_prob)),
            draw_prob=Decimal(str(data.draw_prob)),
            away_win_prob=Decimal(str(data.away_win_prob)),
            confidence_score=Decimal(str(data.confidence_score)) if data.confidence_score else Decimal("0.0"),
            # Both Teams to Score (BTTS) - Optional
            btts_yes_prob=Decimal(str(data.btts_yes_prob)) if data.btts_yes_prob is not None else None,
            btts_no_prob=Decimal(str(data.btts_no_prob)) if data.btts_no_prob is not None else None,
            btts_confidence=Decimal(str(data.btts_confidence)) if data.btts_confidence is not None else None,
            # Total Goals - Optional
            total_goals_over_25_prob=Decimal(str(data.total_goals_over_25_prob)) if data.total_goals_over_25_prob is not None else None,
            total_goals_under_25_prob=Decimal(str(data.total_goals_under_25_prob)) if data.total_goals_under_25_prob is not None else None,
            total_goals_over_35_prob=Decimal(str(data.total_goals_over_35_prob)) if data.total_goals_over_35_prob is not None else None,
            total_goals_under_35_prob=Decimal(str(data.total_goals_under_35_prob)) if data.total_goals_under_35_prob is not None else None,
            total_goals_confidence=Decimal(str(data.total_goals_confidence)) if data.total_goals_confidence is not None else None,
            # Reasoning & Metadata
            reasoning=data.reasoning,
            status=self._initial_status(),
            published_at=self._initial_published_at(),
            is_test_data=test_data_classification(data.is_test_data),
            prediction_metadata={
                "key_factors": data.key_factors or {},
                "created_via": "expert_override",
                "original_prediction_id": str(original_prediction.id),
                "original_source": original_prediction.source.value,
            }
        )
        
        self.db.add(override_prediction)
        # Flush before pointing the original at it: predictions.superseded_by is a foreign key, so
        # the new row has to exist first. Without this the UPDATE can be emitted ahead of the INSERT
        # and Postgres rejects it.
        self.db.flush()

        # Mark original prediction as superseded
        original_prediction.superseded_by = override_prediction.id
        
        # Create override record for audit trail.
        #
        # This block used to pass original_prediction_id, override_prediction_id, overridden_by and
        # override_metadata, none of which are columns on PredictionOverride. SQLAlchemy raised
        # TypeError on every call, the endpoint's own except turned it into a 400 "Failed to create
        # override", and the API test mocks the service, so the endpoint could never have worked and
        # nothing said so. The kwargs below are the model's actual columns.
        from app.core.config import settings
        from app.core.deps import ensure_expert_profile

        profile = ensure_expert_profile(self.db, expert_user, verified=bool(settings.EXPERT_DIRECT_PUBLISH))
        original_confidence = (Decimal(str(original_prediction.confidence_score))
                               if original_prediction.confidence_score is not None else None)
        new_confidence = Decimal(str(data.confidence_score)) if data.confidence_score is not None else Decimal("0")
        override_record = PredictionOverride(
            id=uuid.uuid4(),
            # the resulting expert prediction; original_prediction is reachable from its
            # prediction_metadata["original_prediction_id"] and from original.superseded_by
            prediction_id=override_prediction.id,
            expert_user_id=expert_user.id,
            expert_profile_id=profile.id,
            original_probabilities={
                "home_win": float(original_prediction.home_win_prob) if original_prediction.home_win_prob is not None else None,
                "draw": float(original_prediction.draw_prob) if original_prediction.draw_prob is not None else None,
                "away_win": float(original_prediction.away_win_prob) if original_prediction.away_win_prob is not None else None,
                "prediction_id": str(original_prediction.id),
                "source": original_prediction.source.value if hasattr(original_prediction.source, "value") else str(original_prediction.source),
            },
            original_confidence=original_confidence,
            new_probabilities={
                "home_win": data.home_win_prob,
                "draw": data.draw_prob,
                "away_win": data.away_win_prob,
            },
            new_confidence=new_confidence,
            confidence_adjustment=(new_confidence - original_confidence) if original_confidence is not None else None,
            override_reason=data.reasoning,
            key_insights=data.key_factors or None,
        )

        self.db.add(override_record)
        self.db.commit()
        self.db.refresh(override_prediction)
        
        logger.info(f"Created override prediction {override_prediction.id} for original {original_prediction.id}")
        
        # Invalidate cache for this match
        self._invalidate_match_cache(str(original_prediction.match_id))
        
        return override_prediction
    
    def get_review_queue(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[Prediction]:
        """
        Get predictions pending review/approval.
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
        
        Returns:
            List of pending predictions
        """
        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.status == PredictionStatus.PENDING,
                Prediction.deleted_at.is_(None)
            )
        ).order_by(
            desc(Prediction.created_at)
        ).limit(limit).offset(offset).all()
        
        return predictions
    
    def get_expert_predictions(
        self,
        expert_user: User,
        limit: int = 50,
        offset: int = 0,
        status: Optional[PredictionStatus] = None
    ) -> List[Prediction]:
        """
        Get predictions created by a specific expert.
        
        Args:
            expert_user: Expert user
            limit: Maximum number of results
            offset: Offset for pagination
            status: Optional status filter
        
        Returns:
            List of expert's predictions
        """
        query = self.db.query(Prediction).filter(
            and_(
                Prediction.created_by == expert_user.id,
                Prediction.deleted_at.is_(None)
            )
        )
        
        if status:
            query = query.filter(Prediction.status == status)
        
        predictions = query.order_by(
            desc(Prediction.created_at)
        ).limit(limit).offset(offset).all()
        
        return predictions
    
    def approve_prediction(
        self,
        prediction_id: str,
        admin_user: User
    ) -> Prediction:
        """
        Approve a pending prediction (Admin only).
        
        Args:
            prediction_id: Prediction ID
            admin_user: Admin user approving the prediction
        
        Returns:
            Approved prediction
        
        Raises:
            ValueError: If prediction not found or not pending
        """
        prediction = self.db.query(Prediction).filter(
            Prediction.id == uuid.UUID(prediction_id)
        ).first()
        
        if not prediction:
            raise ValueError(f"Prediction {prediction_id} not found")
        
        if prediction.status != PredictionStatus.PENDING:
            raise ValueError(f"Prediction {prediction_id} is not pending approval")

        # Update status - automatically publish when approved
        now = datetime.utcnow()
        prediction.status = PredictionStatus.PUBLISHED  # Changed from APPROVED to PUBLISHED
        prediction.approved_by = admin_user.id
        prediction.approved_at = now
        prediction.published_at = now  # Set published timestamp

        self.db.commit()
        self.db.refresh(prediction)

        logger.info(f"Approved and published prediction {prediction_id} by admin {admin_user.id}")

        # Invalidate cache
        self._invalidate_match_cache(str(prediction.match_id))
        
        return prediction
    
    def publish_prediction(
        self,
        prediction_id: str
    ) -> Prediction:
        """
        Publish an approved prediction.
        
        Args:
            prediction_id: Prediction ID
        
        Returns:
            Published prediction
        
        Raises:
            ValueError: If prediction not found or not approved
        """
        prediction = self.db.query(Prediction).filter(
            Prediction.id == uuid.UUID(prediction_id)
        ).first()
        
        if not prediction:
            raise ValueError(f"Prediction {prediction_id} not found")
        
        if prediction.status != PredictionStatus.APPROVED:
            raise ValueError(f"Prediction {prediction_id} is not approved")
        
        # Update status
        prediction.status = PredictionStatus.PUBLISHED
        prediction.published_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(prediction)
        
        logger.info(f"Published prediction {prediction_id}")

        # Invalidate cache
        self._invalidate_match_cache(str(prediction.match_id))

        return prediction

    def reject_prediction(
        self,
        prediction_id: str,
        admin_user: User,
        reason: Optional[str] = None
    ) -> Prediction:
        """
        Reject a pending prediction (Admin only).

        Args:
            prediction_id: Prediction ID
            admin_user: Admin user rejecting the prediction
            reason: Optional reason for rejection

        Returns:
            Rejected prediction

        Raises:
            ValueError: If prediction not found or not pending
        """
        prediction = self.db.query(Prediction).filter(
            Prediction.id == uuid.UUID(prediction_id)
        ).first()

        if not prediction:
            raise ValueError(f"Prediction {prediction_id} not found")

        if prediction.status != PredictionStatus.PENDING:
            raise ValueError(f"Prediction {prediction_id} is not pending approval")

        # Update status
        prediction.status = PredictionStatus.REJECTED

        # Store rejection reason in metadata
        if reason:
            metadata = prediction.prediction_metadata or {}
            metadata['rejection_reason'] = reason
            metadata['rejected_by'] = str(admin_user.id)
            metadata['rejected_at'] = datetime.utcnow().isoformat()
            prediction.prediction_metadata = metadata

        self.db.commit()
        self.db.refresh(prediction)

        logger.info(f"Rejected prediction {prediction_id} by admin {admin_user.id}")

        # Invalidate cache
        self._invalidate_match_cache(str(prediction.match_id))

        return prediction

    def update_prediction(
        self,
        prediction_id: str,
        data: ExpertPredictionUpdate,
        expert_user: User
    ) -> Prediction:
        """Update one of the expert's own predictions. See `update_prediction_with_revision`."""
        prediction, _revision = self.update_prediction_with_revision(prediction_id, data, expert_user)
        return prediction

    def update_prediction_with_revision(
        self,
        prediction_id: str,
        data: ExpertPredictionUpdate,
        expert_user: User
    ) -> Tuple[Prediction, PredictionAudit]:
        """
        Update one of the expert's own predictions, preserving the version being replaced.

        Experts publish directly, so a PUBLISHED (or ARCHIVED) prediction stays editable; the edit
        keeps the current status and published_at and only refreshes updated_at.

        An edit used to overwrite the live row and leave nothing behind: the prediction readers had
        already seen simply stopped existing, and the endpoint's audit entry recorded the *new*
        values as both the old and the new ones. A correction must append, not rewrite, so the
        values being replaced are written first to predictions.prediction_audit - the table that was
        built for exactly this and had never received a row - and the edit then proceeds. The
        earlier version stays retrievable with its own timestamp afterwards, including when the edit
        is made after kickoff.

        Args:
            prediction_id: Prediction ID
            data: Update data
            expert_user: Expert user updating the prediction

        Returns:
            (updated prediction, the appended revision holding the previous version)

        Raises:
            ValueError: If prediction not found, not owned by user, or not editable
        """
        prediction = self.db.query(Prediction).filter(
            Prediction.id == uuid.UUID(prediction_id)
        ).first()

        if not prediction:
            raise ValueError(f"Prediction {prediction_id} not found")

        # Check ownership
        if prediction.created_by != expert_user.id:
            raise ValueError("You can only update your own predictions")

        # Experts publish directly (there is no admin approval step), so a PUBLISHED prediction is
        # the normal state of an expert's own work and must stay editable - otherwise a typo can
        # never be corrected. ARCHIVED (unpublished) predictions are editable for the same reason.
        # REJECTED predictions are not: they are a moderation outcome, not a draft.
        editable_statuses = [
            PredictionStatus.PENDING,
            PredictionStatus.APPROVED,
            PredictionStatus.PUBLISHED,
            PredictionStatus.ARCHIVED,
        ]
        if prediction.status not in editable_statuses:
            raise ValueError(
                f"Cannot edit prediction with status {prediction.status}. "
                f"Editable statuses: {', '.join(s.value for s in editable_statuses)}."
            )

        # Captured BEFORE anything is written: once the row is mutated the previous view is gone.
        previous_values = prediction_snapshot(prediction)

        # Update Match Outcome fields
        prediction.home_win_prob = Decimal(str(data.home_win_prob))
        prediction.draw_prob = Decimal(str(data.draw_prob))
        prediction.away_win_prob = Decimal(str(data.away_win_prob))

        if data.confidence_score is not None:
            prediction.confidence_score = Decimal(str(data.confidence_score))

        # Update BTTS fields
        if data.btts_yes_prob is not None:
            prediction.btts_yes_prob = Decimal(str(data.btts_yes_prob))
        if data.btts_no_prob is not None:
            prediction.btts_no_prob = Decimal(str(data.btts_no_prob))
        if data.btts_confidence is not None:
            prediction.btts_confidence = Decimal(str(data.btts_confidence))

        # Update Total Goals fields
        if data.total_goals_over_25_prob is not None:
            prediction.total_goals_over_25_prob = Decimal(str(data.total_goals_over_25_prob))
        if data.total_goals_under_25_prob is not None:
            prediction.total_goals_under_25_prob = Decimal(str(data.total_goals_under_25_prob))
        if data.total_goals_over_35_prob is not None:
            prediction.total_goals_over_35_prob = Decimal(str(data.total_goals_over_35_prob))
        if data.total_goals_under_35_prob is not None:
            prediction.total_goals_under_35_prob = Decimal(str(data.total_goals_under_35_prob))
        if data.total_goals_confidence is not None:
            prediction.total_goals_confidence = Decimal(str(data.total_goals_confidence))

        if data.reasoning is not None:
            prediction.reasoning = data.reasoning

        if data.key_factors is not None:
            metadata = prediction.prediction_metadata or {}
            metadata['key_factors'] = data.key_factors
            prediction.prediction_metadata = metadata

        # Only updated_at moves: status and published_at are left exactly as they were, so editing a
        # published prediction does not unpublish it or restamp its publication time.
        edited_at = datetime.utcnow()
        prediction.updated_at = edited_at

        new_values = prediction_snapshot(prediction)
        revision = PredictionAudit(
            id=uuid.uuid4(),
            prediction_id=prediction.id,
            user_id=expert_user.id,
            action=REVISION_ACTION,
            action_description=(f"Expert {expert_user.id} edited prediction {prediction.id}; "
                                f"the version it replaced is preserved here"),
            old_values=previous_values,
            new_values=new_values,
            changes_summary=_changes_summary(previous_values, new_values),
            # created_at is set explicitly so the revision carries the moment of the edit rather
            # than whatever the flush order happens to produce.
            created_at=edited_at,
            updated_at=edited_at,
        )
        # Appended, never updated in place: a second correction adds a second row, so every earlier
        # published version survives every later edit.
        self.db.add(revision)

        self.db.commit()
        self.db.refresh(prediction)
        self.db.refresh(revision)

        logger.info(f"Updated prediction {prediction_id} (status {prediction.status}) by expert {expert_user.id}; "
                    f"previous version preserved as revision {revision.id}")

        # Invalidate cache
        self._invalidate_match_cache(str(prediction.match_id))

        return prediction, revision

    def revisions_for(self, prediction_ids: Iterable) -> Dict[Any, List[PredictionAudit]]:
        """Preserved earlier versions per prediction, oldest first.

        One query for the whole set, so a payload that lists several predictions does not turn into
        a query per prediction. Ties on the edit time are broken by id so the order a reader sees
        never changes between two identical requests.
        """
        ids = [pid for pid in prediction_ids if pid is not None]
        if not ids:
            return {}
        rows = self.db.query(PredictionAudit).filter(
            PredictionAudit.prediction_id.in_(ids),
            PredictionAudit.action == REVISION_ACTION,
        ).order_by(PredictionAudit.created_at.asc(), PredictionAudit.id.asc()).all()
        grouped: Dict[Any, List[PredictionAudit]] = {}
        for row in rows:
            grouped.setdefault(row.prediction_id, []).append(row)
        return grouped

    def delete_prediction(
        self,
        prediction_id: str,
        expert_user: User
    ) -> None:
        """
        Delete a prediction (Expert can delete their own PENDING, REJECTED, or PUBLISHED predictions).

        Args:
            prediction_id: Prediction ID
            expert_user: Expert user deleting the prediction

        Raises:
            ValueError: If prediction not found, not owned by user, or not deletable
        """
        prediction = self.db.query(Prediction).filter(
            Prediction.id == uuid.UUID(prediction_id)
        ).first()

        if not prediction:
            raise ValueError(f"Prediction {prediction_id} not found")

        # Check ownership
        if prediction.created_by != expert_user.id:
            raise ValueError("You can only delete your own predictions")

        # Check if prediction is deletable (PENDING, REJECTED, PUBLISHED, or ARCHIVED predictions can be deleted)
        if prediction.status not in [PredictionStatus.PENDING, PredictionStatus.REJECTED, PredictionStatus.PUBLISHED, PredictionStatus.ARCHIVED]:
            raise ValueError(f"Cannot delete prediction with status {prediction.status}. Only PENDING, REJECTED, PUBLISHED, or ARCHIVED predictions can be deleted.")

        match_id = str(prediction.match_id)

        # Soft delete
        prediction.deleted_at = datetime.utcnow()

        self.db.commit()

        logger.info(f"Deleted prediction {prediction_id} by expert {expert_user.id}")

        # Invalidate cache
        self._invalidate_match_cache(match_id)

    def _withdrawal_is_frozen(self, prediction: Prediction, now: datetime) -> bool:
        """Is this prediction's recorded withdrawal now a closed fact that must not be rewritten?

        ``unpublished_at`` holds the moment the prediction last came off the public lists, and
        settlement reads it to answer "was a reader seeing this when the ball was kicked?". While
        the match is still ahead, that answer is not yet fixed and the column simply tracks the
        current state. Once the match has kicked off it IS fixed, and a withdrawal that happened
        before kickoff must survive every later toggle:

        * clearing it on a republish would let an expert withdraw everything in advance, wait for
          the results and put back only the winners - the same erasure this change closes, run in
          the profitable direction and inventing a record no reader ever saw;
        * overwriting it with a fresh post-kickoff time on a second unpublish would do the same
          thing by a longer route.

        A withdrawal made AFTER kickoff is not frozen: it says nothing about what stood at kickoff,
        so a later republish is free to clear it. The full sequence of toggles is preserved in the
        PredictionAudit rows written under :data:`PUBLICATION_ACTION` either way.
        """
        if prediction.unpublished_at is None:
            return False
        match = self.db.query(Match).filter(Match.id == prediction.match_id).first()
        kickoff = match.match_date if match is not None else None
        if kickoff is None:
            return False
        return prediction.unpublished_at < kickoff <= now

    def toggle_publish_status(
        self,
        prediction_id: str,
        expert_user: User
    ) -> Prediction:
        """
        Toggle the publication status of a prediction between PUBLISHED and ARCHIVED.

        Args:
            prediction_id: Prediction ID
            expert_user: Expert user toggling the status

        Returns:
            Updated prediction

        Raises:
            ValueError: If prediction not found, not owned by user, or not in a toggleable state
        """
        prediction = self.db.query(Prediction).filter(
            Prediction.id == uuid.UUID(prediction_id)
        ).first()

        if not prediction:
            raise ValueError(f"Prediction {prediction_id} not found")

        # Check ownership
        if prediction.created_by != expert_user.id:
            raise ValueError("You can only toggle publish status for your own predictions")

        # Check if prediction is in a toggleable state (only PUBLISHED or ARCHIVED can be toggled)
        if prediction.status not in [PredictionStatus.PUBLISHED, PredictionStatus.ARCHIVED]:
            raise ValueError(f"Cannot toggle publish status for prediction with status {prediction.status}. Only PUBLISHED or ARCHIVED predictions can be toggled.")

        match_id = str(prediction.match_id)

        # Toggle status.
        #
        # published_at is a historical fact and is written once. This used to clear it on an
        # unpublish and restamp it on a republish, which was the only place in the system where a
        # prematch fact was destroyed rather than merely hidden: settlement proves a prediction
        # predates kickoff from published_at, so an unpublish/republish round trip after the result
        # made a losing prediction permanently unscoreable. The moment of the unpublish goes in its
        # own column instead, so both "when did readers first see this?" and "when did it come
        # down?" survive.
        toggled_at = datetime.utcnow()
        before = {"status": prediction.status.value if hasattr(prediction.status, "value")
                  else str(prediction.status),
                  "published_at": iso_utc(prediction.published_at),
                  "unpublished_at": iso_utc(prediction.unpublished_at)}
        frozen = self._withdrawal_is_frozen(prediction, toggled_at)

        if prediction.status == PredictionStatus.PUBLISHED:
            prediction.status = PredictionStatus.ARCHIVED
            if not frozen:
                prediction.unpublished_at = toggled_at
            logger.info(f"Unpublished prediction {prediction_id} by expert {expert_user.id}; "
                        f"its publication time {prediction.published_at} is kept")
        else:  # ARCHIVED
            prediction.status = PredictionStatus.PUBLISHED
            if not frozen:
                prediction.unpublished_at = None
            if prediction.published_at is None:
                # It has never been published before, so this is its first publication.
                prediction.published_at = toggled_at
            logger.info(f"Published prediction {prediction_id} by expert {expert_user.id}")

        prediction.updated_at = toggled_at

        after = {"status": prediction.status.value if hasattr(prediction.status, "value")
                 else str(prediction.status),
                 "published_at": iso_utc(prediction.published_at),
                 "unpublished_at": iso_utc(prediction.unpublished_at)}
        # Appended, never updated in place, so a prediction toggled several times leaves a full
        # trail of when it was and was not on the public lists.
        self.db.add(PredictionAudit(
            id=uuid.uuid4(),
            prediction_id=prediction.id,
            user_id=expert_user.id,
            action=PUBLICATION_ACTION,
            action_description=(f"Expert {expert_user.id} changed the publication state of "
                                f"prediction {prediction.id} from {before['status']} to "
                                f"{after['status']}"),
            old_values=before,
            new_values=after,
            changes_summary=f"{before['status']} -> {after['status']}",
            created_at=toggled_at,
            updated_at=toggled_at,
        ))

        self.db.commit()
        self.db.refresh(prediction)

        # Invalidate cache
        self._invalidate_match_cache(match_id)

        return prediction

    def classify_as_test_data(self, prediction_id: str, expert_user: User,
                              is_test_data: bool = True) -> Prediction:
        """Classify one of the caller's own records as test data, or clear the classification.

        This is the supported way to classify a record that was not created through the API - one
        made through the composer UI, for instance - so the end-to-end suite never has to rely on
        a marker typed into the reasoning text to tell its own records apart. It is:

        * gated: refused outright unless ``ALLOW_TEST_DATA_CLASSIFICATION`` is on, which it is not
          in any normal deployment. Without the gate this endpoint would be a way for an expert to
          take their own losses off the leaderboard;
        * per record: it marks the one row named, never an account and never a match. The QA
          account here also holds records a person typed by hand, and those must not be swept up
          with the harness's;
        * explicit: a stored boolean, never a guess about what some text means.

        Raises:
            ClassificationNotAllowed: the installation does not allow classification
            ValueError: no such prediction, or it belongs to somebody else
        """
        from app.core.config import settings
        if not settings.ALLOW_TEST_DATA_CLASSIFICATION:
            raise ClassificationNotAllowed(
                "This installation does not allow records to be classified as test data. It is "
                "enabled only where the records genuinely are test data (set "
                "ALLOW_TEST_DATA_CLASSIFICATION), never where real predictions are published.")

        prediction = self.db.query(Prediction).filter(
            Prediction.id == uuid.UUID(prediction_id)
        ).first()
        if not prediction:
            raise ValueError(f"Prediction {prediction_id} not found")
        if prediction.created_by != expert_user.id:
            raise ValueError("You can only classify your own predictions")

        # True or NULL, never False: "nobody has said" and "somebody said this is genuine" are
        # different claims, and only the first one is ever true of a record nobody classified.
        prediction.is_test_data = True if is_test_data else None
        prediction.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(prediction)

        logger.info(f"Prediction {prediction_id} classified is_test_data={prediction.is_test_data} "
                    f"by {expert_user.id}")
        return prediction

    def enrich_prediction_with_details(self, prediction: Prediction) -> Dict[str, Any]:
        """
        Enrich prediction with match and user details.

        Args:
            prediction: Prediction object

        Returns:
            Dictionary with prediction data plus match_details and user_details
        """
        # Get match details
        match = self.db.query(Match).filter(Match.id == prediction.match_id).first()
        match_details = None

        if match:
            # Get teams
            home_team = self.db.query(Team).filter(Team.id == match.home_team_id).first()
            away_team = self.db.query(Team).filter(Team.id == match.away_team_id).first()
            league = self.db.query(League).filter(League.id == match.league_id).first()

            # Extract external match ID from metadata
            external_match_id = None
            if prediction.prediction_metadata:
                external_match_id = prediction.prediction_metadata.get('external_match_id')

            match_details = {
                'home_team_name': home_team.name if home_team else 'Unknown',
                'away_team_name': away_team.name if away_team else 'Unknown',
                'home_team_logo': home_team.logo_url if home_team else None,
                'away_team_logo': away_team.logo_url if away_team else None,
                'league_name': league.display_name if league else None,
                'match_date': match.match_date,
                'external_match_id': external_match_id or match.external_api_id
            }
        else:
            logger.warning(f"No match found for match_id {prediction.match_id}")

        # Get user details
        user = self.db.query(User).filter(User.id == prediction.created_by).first()
        user_details = None

        if user:
            user_details = {
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            }

        # Convert prediction to dict
        prediction_dict = {
            'id': str(prediction.id),
            'match_id': str(prediction.match_id),
            'source': prediction.source.value if hasattr(prediction.source, 'value') else prediction.source,
            'priority_level': prediction.priority_level,
            # Match Outcome (1X2)
            'home_win_prob': float(prediction.home_win_prob),
            'draw_prob': float(prediction.draw_prob),
            'away_win_prob': float(prediction.away_win_prob),
            'confidence_score': float(prediction.confidence_score),
            # Both Teams to Score (BTTS) - Optional
            'btts_yes_prob': float(prediction.btts_yes_prob) if prediction.btts_yes_prob is not None else None,
            'btts_no_prob': float(prediction.btts_no_prob) if prediction.btts_no_prob is not None else None,
            'btts_confidence': float(prediction.btts_confidence) if prediction.btts_confidence is not None else None,
            # Total Goals - Optional
            'total_goals_over_25_prob': float(prediction.total_goals_over_25_prob) if prediction.total_goals_over_25_prob is not None else None,
            'total_goals_under_25_prob': float(prediction.total_goals_under_25_prob) if prediction.total_goals_under_25_prob is not None else None,
            'total_goals_over_35_prob': float(prediction.total_goals_over_35_prob) if prediction.total_goals_over_35_prob is not None else None,
            'total_goals_under_35_prob': float(prediction.total_goals_under_35_prob) if prediction.total_goals_under_35_prob is not None else None,
            'total_goals_confidence': float(prediction.total_goals_confidence) if prediction.total_goals_confidence is not None else None,
            # Reasoning & Metadata
            'reasoning': prediction.reasoning,
            'key_factors': prediction.key_factors,
            'status': prediction.status.value if hasattr(prediction.status, 'value') else prediction.status,
            'created_by': str(prediction.created_by),
            'created_at': prediction.created_at,
            'published_at': prediction.published_at,
            'unpublished_at': prediction.unpublished_at,
            'is_test_data': prediction.is_test_data,
            'superseded_by': str(prediction.superseded_by) if prediction.superseded_by else None,
            'match_details': match_details,
            'user_details': user_details
        }

        return prediction_dict

    def _invalidate_match_cache(self, match_id: str) -> None:
        """
        Invalidate all cached predictions for a match.

        Args:
            match_id: Match ID
        """
        # Invalidate cache for all tiers
        for tier in ["free", "premium", "pro"]:
            cache_key = f"prediction:{match_id}:{tier}:match_winner"
            try:
                # Note: PredictionCacheService doesn't have delete method yet
                # This is a placeholder for cache invalidation
                logger.info(f"Would invalidate cache key: {cache_key}")
            except Exception as e:
                logger.warning(f"Failed to invalidate cache key {cache_key}: {e}")

    def _ensure_match_exists(self, match_uuid: uuid.UUID, external_match_id: str) -> None:
        """
        Ensure match exists in database, fetch from API-Football if not.
        If match exists but is a placeholder, update it with real data from API-Football.

        Args:
            match_uuid: Match UUID
            external_match_id: External API match ID (API-Football fixture ID)
        """
        from app.models.predictions import Match, Team
        from app.services.api_football import APIFootballService

        # Check if match already exists
        match = self.db.query(Match).filter(Match.id == match_uuid).first()
        if match:
            # Check if this is a placeholder match (teams have "TBD" in their names)
            home_team = self.db.query(Team).filter(Team.id == match.home_team_id).first()
            away_team = self.db.query(Team).filter(Team.id == match.away_team_id).first()

            is_placeholder = (
                (home_team and "(TBD)" in home_team.name) or
                (away_team and "(TBD)" in away_team.name)
            )

            if is_placeholder:
                logger.info(f"Match {match_uuid} exists but is a placeholder, updating with real data from API-Football")
                # Delete the placeholder match and its teams/league, then recreate with real data.
                # If anything is attached to it the deletion is refused, and the placeholder is
                # kept as it is: recreating the row here would collide with the existing primary
                # key anyway, and no amount of tidier team names is worth deleting a record.
                if not self._delete_placeholder_match(match_uuid):
                    return
            else:
                logger.debug(f"Match {match_uuid} already exists with real data")
                return

        logger.info(f"Match {match_uuid} not found, fetching from API-Football (fixture ID: {external_match_id})")

        # Try to fetch match data from API-Football
        api_service = APIFootballService()
        match_data = api_service.get_match_data(external_match_id)

        if match_data:
            # Create match with real data from API-Football
            self._create_match_from_api_data(match_uuid, match_data)
            return

        # If API-Football fetch fails, create placeholder
        logger.warning(f"Failed to fetch match {external_match_id} from API-Football, creating placeholder")
        self._create_placeholder_match(match_uuid, external_match_id)

    def _create_match_from_api_data(self, match_uuid: uuid.UUID, match_data: Dict[str, Any]) -> None:
        """
        Create match, teams, and league from API-Football data.

        Args:
            match_uuid: Match UUID
            match_data: Normalized match data from API-Football
        """
        from app.models.predictions import Match, MatchStatus, Team, League
        from datetime import datetime

        logger.info(f"Creating match {match_uuid} from API-Football data")

        # Create or get league
        league_data = match_data.get("league", {})
        league_external_id = league_data.get("external_id")

        league = self.db.query(League).filter(
            League.external_api_id == league_external_id
        ).first()

        if not league:
            league = League(
                id=uuid.uuid4(),
                name=league_data.get("name", "Unknown League"),
                display_name=league_data.get("name", "Unknown League"),
                country=league_data.get("country", "Unknown"),
                logo_url=league_data.get("logo_url"),
                external_api_id=league_external_id,
                external_api_source="api-football",
                is_active=True
            )
            self.db.add(league)
            self.db.flush()
            logger.info(f"Created league {league.id}: {league.name}")

        # Create or get home team
        home_team_data = match_data.get("home_team", {})
        home_team_external_id = home_team_data.get("external_id")

        home_team = self.db.query(Team).filter(
            Team.external_api_id == home_team_external_id
        ).first()

        if not home_team:
            home_team = Team(
                id=uuid.uuid4(),
                name=home_team_data.get("name", "Unknown Team"),
                short_name=home_team_data.get("name", "Unknown")[:10],  # Truncate to 10 chars
                country=league_data.get("country", "Unknown"),
                logo_url=home_team_data.get("logo_url"),
                external_api_id=home_team_external_id,
                external_api_source="api-football",
                is_active=True
            )
            self.db.add(home_team)
            self.db.flush()
            logger.info(f"Created home team {home_team.id}: {home_team.name}")

        # Create or get away team
        away_team_data = match_data.get("away_team", {})
        away_team_external_id = away_team_data.get("external_id")

        away_team = self.db.query(Team).filter(
            Team.external_api_id == away_team_external_id
        ).first()

        if not away_team:
            away_team = Team(
                id=uuid.uuid4(),
                name=away_team_data.get("name", "Unknown Team"),
                short_name=away_team_data.get("name", "Unknown")[:10],  # Truncate to 10 chars
                country=league_data.get("country", "Unknown"),
                logo_url=away_team_data.get("logo_url"),
                external_api_id=away_team_external_id,
                external_api_source="api-football",
                is_active=True
            )
            self.db.add(away_team)
            self.db.flush()
            logger.info(f"Created away team {away_team.id}: {away_team.name}")

        # Map API-Football status to our MatchStatus enum
        status_map = {
            "NS": MatchStatus.SCHEDULED,  # Not Started
            "LIVE": MatchStatus.LIVE,
            "1H": MatchStatus.LIVE,  # First Half
            "HT": MatchStatus.LIVE,  # Halftime
            "2H": MatchStatus.LIVE,  # Second Half
            "ET": MatchStatus.LIVE,  # Extra Time
            "P": MatchStatus.LIVE,   # Penalty
            "FT": MatchStatus.FINISHED,  # Full Time
            "AET": MatchStatus.FINISHED,  # After Extra Time
            "PEN": MatchStatus.FINISHED,  # Penalties
            "PST": MatchStatus.POSTPONED,
            "CANC": MatchStatus.CANCELLED,
            "ABD": MatchStatus.CANCELLED,  # Abandoned
            "AWD": MatchStatus.FINISHED,   # Awarded (technical result)
            "WO": MatchStatus.FINISHED     # Walkover
        }

        api_status = match_data.get("status", "NS")
        match_status = status_map.get(api_status, MatchStatus.SCHEDULED)

        # Parse match date.
        #
        # match_date is a naive column holding UTC wall time, and every prematch test in the
        # system - "was this published before kickoff?", "was it withdrawn before kickoff?" -
        # compares against it. fromisoformat returns an AWARE datetime for any offset the provider
        # sends, and writing that straight in stored local wall time instead, shifting the whole
        # boundary by the offset. Normalised here the way the match registry does it.
        from app.services.match_registry import _naive_utc

        match_date_str = match_data.get("match_date")
        try:
            match_date = _naive_utc(datetime.fromisoformat(match_date_str.replace('Z', '+00:00')))
        except (ValueError, AttributeError):
            match_date = datetime.utcnow()
            logger.warning(f"Could not parse match date '{match_date_str}', using current time")

        # Create match
        match = Match(
            id=match_uuid,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            league_id=league.id,
            match_date=match_date,
            venue=match_data.get("venue"),
            status=match_status,
            external_api_id=match_data.get("external_match_id"),
            external_api_source="api-football",
            match_metadata={
                "fetched_from_api": True,
                "api_status": api_status
            }
        )
        self.db.add(match)
        self.db.flush()
        self.db.commit()  # Commit the match and related data
        logger.info(f"Created match {match_uuid}: {home_team.name} vs {away_team.name}")

    def _create_placeholder_match(self, match_uuid: uuid.UUID, external_match_id: str) -> None:
        """
        Create placeholder match when API-Football fetch fails.

        Args:
            match_uuid: Match UUID
            external_match_id: External API match ID
        """
        from app.models.predictions import Match, MatchStatus, Team, League

        logger.info(f"Creating placeholder match {match_uuid}")

        # Create or get placeholder league
        placeholder_league = self.db.query(League).filter(
            League.external_api_id == "placeholder"
        ).first()

        if not placeholder_league:
            placeholder_league = League(
                id=uuid.uuid4(),
                name="Unknown League",
                display_name="Unknown League",
                country="Unknown",
                external_api_id="placeholder",
                external_api_source="placeholder",
                is_active=True
            )
            self.db.add(placeholder_league)
            self.db.flush()
            logger.info(f"Created placeholder league {placeholder_league.id}")

        # Create or get placeholder teams
        placeholder_home_team = self.db.query(Team).filter(
            Team.external_api_id == f"placeholder-home-{external_match_id}"
        ).first()

        if not placeholder_home_team:
            placeholder_home_team = Team(
                id=uuid.uuid4(),
                name="Home Team (TBD)",
                short_name="HOME",
                country="Unknown",
                external_api_id=f"placeholder-home-{external_match_id}",
                external_api_source="placeholder",
                is_active=True
            )
            self.db.add(placeholder_home_team)
            self.db.flush()
            logger.info(f"Created placeholder home team {placeholder_home_team.id}")

        placeholder_away_team = self.db.query(Team).filter(
            Team.external_api_id == f"placeholder-away-{external_match_id}"
        ).first()

        if not placeholder_away_team:
            placeholder_away_team = Team(
                id=uuid.uuid4(),
                name="Away Team (TBD)",
                short_name="AWAY",
                country="Unknown",
                external_api_id=f"placeholder-away-{external_match_id}",
                external_api_source="placeholder",
                is_active=True
            )
            self.db.add(placeholder_away_team)
            self.db.flush()
            logger.info(f"Created placeholder away team {placeholder_away_team.id}")

        # Create placeholder match
        match = Match(
            id=match_uuid,
            home_team_id=placeholder_home_team.id,
            away_team_id=placeholder_away_team.id,
            league_id=placeholder_league.id,
            match_date=datetime.utcnow(),
            status=MatchStatus.SCHEDULED,
            external_api_id=external_match_id,
            external_api_source="api-football",
            match_metadata={
                "is_placeholder": True,
                "note": "This is a placeholder match created for expert prediction. Match details should be updated from API-Football."
            }
        )
        self.db.add(match)
        self.db.flush()
        self.db.commit()  # Commit the placeholder match and related data
        logger.info(f"Created placeholder match {match_uuid} for external ID {external_match_id}")

    def _delete_placeholder_match(self, match_uuid: uuid.UUID) -> bool:
        """
        Delete a placeholder match and its associated teams and league.

        Args:
            match_uuid: Match UUID to delete

        Returns:
            True when the placeholder was deleted, False when it was kept because records are
            attached to it.
        """
        from app.models.predictions import Match, Team, League

        match = self.db.query(Match).filter(Match.id == match_uuid).first()
        if not match:
            return False

        # Refuse to delete a match anything is attached to.
        #
        # Match.predictions is cascade="all, delete-orphan", so deleting the match row deletes
        # every prediction on it - other experts' included - and with them their scores
        # (prediction_results), their preserved earlier versions (prediction_audit) and, through
        # ON DELETE CASCADE in the database, the provider forecast snapshots for that fixture.
        # None of it is soft-deleted and none of it is recoverable, which makes this by far the
        # largest erasure reachable from an expert action. Upgrading a placeholder is a
        # convenience; it is never worth a record.
        attached = self.db.query(Prediction).filter(Prediction.match_id == match_uuid).count()
        if attached:
            logger.warning(
                f"Refusing to delete placeholder match {match_uuid}: {attached} prediction(s) are "
                f"attached to it and deleting the match would delete them and their scores. The "
                f"placeholder stays; its details can be corrected in place.")
            return False

        # Get team and league IDs before deleting the match
        home_team_id = match.home_team_id
        away_team_id = match.away_team_id
        league_id = match.league_id

        # Delete the match first
        self.db.delete(match)
        self.db.flush()

        # Delete teams if they exist and are placeholders
        if home_team_id:
            home_team = self.db.query(Team).filter(Team.id == home_team_id).first()
            if home_team and "(TBD)" in home_team.name:
                self.db.delete(home_team)
                self.db.flush()

        if away_team_id:
            away_team = self.db.query(Team).filter(Team.id == away_team_id).first()
            if away_team and "(TBD)" in away_team.name:
                self.db.delete(away_team)
                self.db.flush()

        # Delete league if it exists and is a placeholder
        if league_id:
            league = self.db.query(League).filter(League.id == league_id).first()
            if league and "(TBD)" in league.name:
                self.db.delete(league)
                self.db.flush()

        self.db.commit()
        logger.info(f"Deleted placeholder match {match_uuid} and its associated teams/league")
        return True

