"""
Unit tests for PredictionAggregatorService

Tests the multi-source prediction priority system with waterfall logic.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal
from datetime import datetime
import uuid

from app.services.prediction_aggregator import PredictionAggregatorService
from app.models.predictions import Prediction, PredictionSource, PredictionStatus
from app.models.users import SubscriptionTier


@pytest.fixture
def mock_db():
    """Mock database session"""
    return Mock()


@pytest.fixture
def mock_cache_service():
    """Mock cache service"""
    cache = Mock()
    cache.get_cached_prediction = Mock(return_value=None)
    cache.cache_prediction = Mock()
    return cache


@pytest.fixture
def aggregator_service(mock_db, mock_cache_service):
    """Create PredictionAggregatorService instance"""
    return PredictionAggregatorService(db=mock_db, cache_service=mock_cache_service)


@pytest.fixture
def sample_expert_prediction():
    """Sample expert prediction"""
    prediction = Mock(spec=Prediction)
    prediction.id = uuid.uuid4()
    prediction.match_id = uuid.uuid4()
    prediction.source = PredictionSource.EXPERT_MANUAL
    prediction.priority_level = 100
    prediction.home_win_prob = Decimal("0.6000")
    prediction.draw_prob = Decimal("0.2500")
    prediction.away_win_prob = Decimal("0.1500")
    prediction.confidence_score = Decimal("0.8500")
    prediction.reasoning = "Expert analysis based on team form"
    prediction.created_at = datetime.utcnow()
    prediction.published_at = datetime.utcnow()
    prediction.created_by = uuid.uuid4()
    prediction.status = PredictionStatus.PUBLISHED
    prediction.deleted_at = None
    prediction.superseded_by = None
    return prediction


@pytest.fixture
def sample_llm_prediction():
    """Sample LLM prediction"""
    prediction = Mock(spec=Prediction)
    prediction.id = uuid.uuid4()
    prediction.match_id = uuid.uuid4()
    prediction.source = PredictionSource.LLM_GENERATED
    prediction.priority_level = 50
    prediction.home_win_prob = Decimal("0.4500")
    prediction.draw_prob = Decimal("0.3000")
    prediction.away_win_prob = Decimal("0.2500")
    prediction.confidence_score = Decimal("0.7000")
    prediction.reasoning = "LLM analysis"
    prediction.created_at = datetime.utcnow()
    prediction.published_at = datetime.utcnow()
    prediction.created_by = uuid.uuid4()
    prediction.status = PredictionStatus.PUBLISHED
    prediction.deleted_at = None
    prediction.superseded_by = None
    return prediction


class TestPredictionAggregatorService:
    """Test suite for PredictionAggregatorService"""
    
    def test_priority_levels_defined(self, aggregator_service):
        """Test that priority levels are correctly defined"""
        assert aggregator_service.PRIORITY_LEVELS[PredictionSource.EXPERT_MANUAL] == 100
        assert aggregator_service.PRIORITY_LEVELS[PredictionSource.EXPERT_OVERRIDE] == 100
        assert aggregator_service.PRIORITY_LEVELS[PredictionSource.ADMIN_MANUAL] == 90
        assert aggregator_service.PRIORITY_LEVELS[PredictionSource.LLM_GENERATED] == 50
        assert aggregator_service.PRIORITY_LEVELS[PredictionSource.ML_BASELINE] == 40
        assert aggregator_service.PRIORITY_LEVELS[PredictionSource.API_FOOTBALL_BASELINE] == 25
        assert aggregator_service.PRIORITY_LEVELS[PredictionSource.DEFAULT_RANDOMIZED] == 0
    
    def test_tier_access_free(self, aggregator_service):
        """Test that FREE tier only has access to API-Football and randomized"""
        free_sources = aggregator_service.TIER_ACCESS[SubscriptionTier.FREE]
        assert PredictionSource.API_FOOTBALL_BASELINE in free_sources
        assert PredictionSource.DEFAULT_RANDOMIZED in free_sources
        assert PredictionSource.EXPERT_MANUAL not in free_sources
        assert PredictionSource.LLM_GENERATED not in free_sources
    
    def test_tier_access_premium(self, aggregator_service):
        """Test that PREMIUM tier has access to expert and LLM predictions"""
        premium_sources = aggregator_service.TIER_ACCESS[SubscriptionTier.PREMIUM]
        assert PredictionSource.EXPERT_MANUAL in premium_sources
        assert PredictionSource.EXPERT_OVERRIDE in premium_sources
        assert PredictionSource.LLM_GENERATED in premium_sources
        assert PredictionSource.API_FOOTBALL_BASELINE in premium_sources
    
    def test_tier_access_pro(self, aggregator_service):
        """Test that PRO tier has access to all prediction sources"""
        pro_sources = aggregator_service.TIER_ACCESS[SubscriptionTier.PRO]
        assert PredictionSource.EXPERT_MANUAL in pro_sources
        assert PredictionSource.ADMIN_MANUAL in pro_sources
        assert PredictionSource.LLM_GENERATED in pro_sources
        assert PredictionSource.ML_BASELINE in pro_sources
        assert PredictionSource.API_FOOTBALL_BASELINE in pro_sources
    
    def test_get_prediction_cache_hit(self, aggregator_service, mock_cache_service):
        """Test that cached prediction is returned when available"""
        match_id = str(uuid.uuid4())
        cached_data = {
            "match_id": match_id,
            "source": "expert_manual",
            "home_win_prob": 0.6,
        }
        mock_cache_service.get_cached_prediction.return_value = cached_data
        
        result = aggregator_service.get_prediction_for_match(match_id, SubscriptionTier.PREMIUM)
        
        assert result == cached_data
        mock_cache_service.get_cached_prediction.assert_called_once()
    
    def test_get_prediction_expert_for_premium_tier(
        self, aggregator_service, mock_db, mock_cache_service, sample_expert_prediction
    ):
        """Test that expert prediction is returned for PREMIUM tier"""
        match_id = str(sample_expert_prediction.match_id)
        
        # Mock database query
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = sample_expert_prediction
        
        result = aggregator_service.get_prediction_for_match(match_id, SubscriptionTier.PREMIUM)
        
        assert result is not None
        assert result["source"] == PredictionSource.EXPERT_MANUAL.value
        assert result["priority_level"] == 100
        assert result["home_win_prob"] == 0.6
        mock_cache_service.cache_prediction.assert_called_once()
    
    def test_get_prediction_llm_for_premium_tier(
        self, aggregator_service, mock_db, mock_cache_service, sample_llm_prediction
    ):
        """Test that LLM prediction is returned for PREMIUM tier when no expert prediction"""
        match_id = str(sample_llm_prediction.match_id)
        
        # Mock database query
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = sample_llm_prediction
        
        result = aggregator_service.get_prediction_for_match(match_id, SubscriptionTier.PREMIUM)
        
        assert result is not None
        assert result["source"] == PredictionSource.LLM_GENERATED.value
        assert result["priority_level"] == 50
    
    def test_get_prediction_randomized_fallback(
        self, aggregator_service, mock_db, mock_cache_service
    ):
        """Test that randomized prediction is generated when no stored predictions"""
        match_id = str(uuid.uuid4())
        
        # Mock database query to return None
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
        
        result = aggregator_service.get_prediction_for_match(match_id, SubscriptionTier.FREE)
        
        assert result is not None
        assert result["source"] == PredictionSource.DEFAULT_RANDOMIZED.value
        assert result["priority_level"] == 0
        assert 0.0 <= result["home_win_prob"] <= 1.0
        assert 0.0 <= result["draw_prob"] <= 1.0
        assert 0.0 <= result["away_win_prob"] <= 1.0
        # Probabilities should sum to ~1.0 (allowing for rounding)
        total = result["home_win_prob"] + result["draw_prob"] + result["away_win_prob"]
        assert 0.99 <= total <= 1.01
    
    def test_get_all_predictions_for_match(
        self, aggregator_service, mock_db, sample_expert_prediction, sample_llm_prediction
    ):
        """Test getting all predictions for a match (Pro tier)"""
        match_id = str(uuid.uuid4())
        
        # Mock database query to return multiple predictions
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [sample_expert_prediction, sample_llm_prediction]
        
        results = aggregator_service.get_all_predictions_for_match(match_id)
        
        assert len(results) == 2
        assert results[0]["source"] == PredictionSource.EXPERT_MANUAL.value
        assert results[1]["source"] == PredictionSource.LLM_GENERATED.value
    
    def test_prediction_to_dict_conversion(self, aggregator_service, sample_expert_prediction):
        """Test conversion of Prediction model to dict"""
        result = aggregator_service._prediction_to_dict(sample_expert_prediction)
        
        assert result["id"] == str(sample_expert_prediction.id)
        assert result["match_id"] == str(sample_expert_prediction.match_id)
        assert result["source"] == PredictionSource.EXPERT_MANUAL.value
        assert result["priority_level"] == 100
        assert result["home_win_prob"] == 0.6
        assert result["draw_prob"] == 0.25
        assert result["away_win_prob"] == 0.15
        assert result["confidence_score"] == 0.85
        assert result["reasoning"] == "Expert analysis based on team form"
    
    def test_generate_randomized_prediction_probabilities_sum_to_one(self, aggregator_service):
        """Test that randomized predictions have probabilities that sum to 1.0"""
        match_id = str(uuid.uuid4())
        
        # Generate multiple randomized predictions to test consistency
        for _ in range(10):
            result = aggregator_service._generate_randomized_prediction(match_id, "match_winner")
            total = result["home_win_prob"] + result["draw_prob"] + result["away_win_prob"]
            assert 0.99 <= total <= 1.01, f"Probabilities sum to {total}, expected ~1.0"

