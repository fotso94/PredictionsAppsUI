"""
Expert Prediction Service

Handles expert prediction creation, overrides, and management.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import uuid

from app.models.predictions import (
    Prediction,
    PredictionSource,
    PredictionStatus,
    PredictionOverride,
    Match,
    Team,
    League
)
from app.models.users import User
from app.schemas.predictions import (
    ExpertPredictionCreate,
    ExpertPredictionOverride,
    ExpertPredictionUpdate,
)
from app.services.prediction_cache import PredictionCacheService

logger = logging.getLogger(__name__)


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

        # Convert match_id to UUID if it's not already
        # API-Football provides numeric IDs, so we need to handle both formats
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
            home_win_prob=Decimal(str(data.home_win_prob)),
            draw_prob=Decimal(str(data.draw_prob)),
            away_win_prob=Decimal(str(data.away_win_prob)),
            confidence_score=Decimal(str(data.confidence_score)) if data.confidence_score else Decimal("0.0"),
            reasoning=data.reasoning,
            status=PredictionStatus.PENDING,  # Requires approval
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
        
        # Create new expert override prediction
        override_prediction = Prediction(
            id=uuid.uuid4(),
            match_id=original_prediction.match_id,
            source=PredictionSource.EXPERT_OVERRIDE,
            priority_level=100,  # Expert overrides have highest priority
            created_by=expert_user.id,
            home_win_prob=Decimal(str(data.home_win_prob)),
            draw_prob=Decimal(str(data.draw_prob)),
            away_win_prob=Decimal(str(data.away_win_prob)),
            confidence_score=Decimal(str(data.confidence_score)) if data.confidence_score else Decimal("0.0"),
            reasoning=data.reasoning,
            status=PredictionStatus.PENDING,  # Requires approval
            prediction_metadata={
                "key_factors": data.key_factors or {},
                "created_via": "expert_override",
                "original_prediction_id": str(original_prediction.id),
                "original_source": original_prediction.source.value,
            }
        )
        
        self.db.add(override_prediction)
        
        # Mark original prediction as superseded
        original_prediction.superseded_by = override_prediction.id
        
        # Create override record for audit trail
        override_record = PredictionOverride(
            id=uuid.uuid4(),
            original_prediction_id=original_prediction.id,
            override_prediction_id=override_prediction.id,
            overridden_by=expert_user.id,
            override_reason=data.reasoning,
            override_metadata={
                "original_probabilities": {
                    "home_win": float(original_prediction.home_win_prob),
                    "draw": float(original_prediction.draw_prob),
                    "away_win": float(original_prediction.away_win_prob),
                },
                "new_probabilities": {
                    "home_win": data.home_win_prob,
                    "draw": data.draw_prob,
                    "away_win": data.away_win_prob,
                },
            }
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
        """
        Update an existing prediction (Expert can only update their own pending predictions).

        Args:
            prediction_id: Prediction ID
            data: Update data
            expert_user: Expert user updating the prediction

        Returns:
            Updated prediction

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

        # Check if prediction is editable (only PENDING predictions can be edited)
        if prediction.status not in [PredictionStatus.PENDING]:
            raise ValueError(f"Cannot edit prediction with status {prediction.status}. Only PENDING predictions can be edited.")

        # Update fields
        prediction.home_win_prob = Decimal(str(data.home_win_prob))
        prediction.draw_prob = Decimal(str(data.draw_prob))
        prediction.away_win_prob = Decimal(str(data.away_win_prob))

        if data.confidence_score is not None:
            prediction.confidence_score = Decimal(str(data.confidence_score))

        if data.reasoning is not None:
            prediction.reasoning = data.reasoning

        if data.key_factors is not None:
            metadata = prediction.prediction_metadata or {}
            metadata['key_factors'] = data.key_factors
            prediction.prediction_metadata = metadata

        prediction.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(prediction)

        logger.info(f"Updated prediction {prediction_id} by expert {expert_user.id}")

        # Invalidate cache
        self._invalidate_match_cache(str(prediction.match_id))

        return prediction

    def delete_prediction(
        self,
        prediction_id: str,
        expert_user: User
    ) -> None:
        """
        Delete a prediction (Expert can only delete their own pending predictions).

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

        # Check if prediction is deletable (only PENDING predictions can be deleted)
        if prediction.status not in [PredictionStatus.PENDING]:
            raise ValueError(f"Cannot delete prediction with status {prediction.status}. Only PENDING predictions can be deleted.")

        match_id = str(prediction.match_id)

        # Soft delete
        prediction.deleted_at = datetime.utcnow()

        self.db.commit()

        logger.info(f"Deleted prediction {prediction_id} by expert {expert_user.id}")

        # Invalidate cache
        self._invalidate_match_cache(match_id)

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
            'home_win_prob': float(prediction.home_win_prob),
            'draw_prob': float(prediction.draw_prob),
            'away_win_prob': float(prediction.away_win_prob),
            'confidence_score': float(prediction.confidence_score),
            'reasoning': prediction.reasoning,
            'key_factors': prediction.key_factors,
            'status': prediction.status.value if hasattr(prediction.status, 'value') else prediction.status,
            'created_by': str(prediction.created_by),
            'created_at': prediction.created_at,
            'published_at': prediction.published_at,
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
        from app.models.predictions import Match, MatchStatus, Team, League
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
                # Delete the placeholder match and its teams/league, then recreate with real data
                self._delete_placeholder_match(match_uuid)
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

        # Parse match date
        match_date_str = match_data.get("match_date")
        try:
            match_date = datetime.fromisoformat(match_date_str.replace('Z', '+00:00'))
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

    def _delete_placeholder_match(self, match_uuid: uuid.UUID) -> None:
        """
        Delete a placeholder match and its associated teams and league.

        Args:
            match_uuid: Match UUID to delete
        """
        from app.models.predictions import Match, Team, League

        match = self.db.query(Match).filter(Match.id == match_uuid).first()
        if not match:
            return

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

