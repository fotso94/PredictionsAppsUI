"""
Integration tests for Expert API endpoints

Tests all 5 Expert API endpoints (KAN-149 through KAN-153).
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import uuid

from app.main import app
from app.models.users import User, UserType
from app.models.predictions import Prediction, PredictionSource, PredictionStatus
from decimal import Decimal


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def expert_user_token():
    """Mock expert user token"""
    return "mock-expert-token"


@pytest.fixture
def mock_expert_user():
    """Mock verified expert user"""
    user = Mock(spec=User)
    user.id = uuid.uuid4()
    user.username = "expert_user"
    user.user_type = UserType.EXPERT
    user.account_status = "active"
    
    # Mock expert profile (verified)
    expert_profile = Mock()
    expert_profile.is_verified = True
    user.expert_profile = expert_profile
    
    return user


@pytest.fixture
def mock_prediction():
    """Mock prediction"""
    prediction = Mock(spec=Prediction)
    prediction.id = uuid.uuid4()
    prediction.match_id = uuid.uuid4()
    prediction.source = PredictionSource.EXPERT_MANUAL
    prediction.priority_level = 100
    prediction.home_win_prob = Decimal("0.6000")
    prediction.draw_prob = Decimal("0.2500")
    prediction.away_win_prob = Decimal("0.1500")
    prediction.confidence_score = Decimal("0.8500")
    prediction.reasoning = "Expert analysis"
    prediction.status = PredictionStatus.PENDING
    prediction.created_by = uuid.uuid4()
    prediction.created_at = "2025-10-13T00:00:00"
    prediction.published_at = None
    prediction.superseded_by = None
    prediction.prediction_metadata = {}
    return prediction


class TestCreateManualPrediction:
    """Tests for POST /api/v1/expert/predictions/manual (KAN-149)"""
    
    @patch("app.api.v1.endpoints.expert.get_current_verified_expert_user")
    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_create_manual_prediction_success(
        self, mock_audit_service, mock_expert_service, mock_get_user, client, mock_expert_user, mock_prediction
    ):
        """Test successful manual prediction creation"""
        # Setup mocks
        mock_get_user.return_value = mock_expert_user
        mock_service_instance = Mock()
        mock_service_instance.create_manual_prediction.return_value = mock_prediction
        mock_expert_service.return_value = mock_service_instance
        
        # Make request
        response = client.post(
            "/api/v1/expert/predictions/manual",
            json={
                "match_id": str(uuid.uuid4()),
                "home_win_prob": 0.6,
                "draw_prob": 0.25,
                "away_win_prob": 0.15,
                "confidence_score": 0.85,
                "reasoning": "Strong home form",
            },
            headers={"Authorization": "Bearer mock-token"}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "expert_manual"
        assert data["priority_level"] == 100
        assert data["status"] == "pending"
    
    def test_create_manual_prediction_probabilities_dont_sum_to_one(self, client):
        """Test validation error when probabilities don't sum to 1.0"""
        response = client.post(
            "/api/v1/expert/predictions/manual",
            json={
                "match_id": str(uuid.uuid4()),
                "home_win_prob": 0.5,
                "draw_prob": 0.3,
                "away_win_prob": 0.3,  # Sum = 1.1, invalid
                "confidence_score": 0.85,
            },
            headers={"Authorization": "Bearer mock-token"}
        )
        
        assert response.status_code in [400, 422]  # Validation error


class TestOverridePrediction:
    """Tests for POST /api/v1/expert/predictions/override (KAN-150)"""
    
    @patch("app.api.v1.endpoints.expert.get_current_verified_expert_user")
    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    @patch("app.api.v1.endpoints.expert.get_db")
    def test_override_prediction_success(
        self, mock_get_db, mock_audit_service, mock_expert_service, mock_get_user, 
        client, mock_expert_user, mock_prediction
    ):
        """Test successful prediction override"""
        # Setup mocks
        mock_get_user.return_value = mock_expert_user
        
        # Mock database query
        mock_db = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_prediction
        mock_get_db.return_value = mock_db
        
        # Mock service
        mock_service_instance = Mock()
        override_prediction = Mock(spec=Prediction)
        override_prediction.id = uuid.uuid4()
        override_prediction.source = PredictionSource.EXPERT_OVERRIDE
        override_prediction.priority_level = 100
        override_prediction.status = PredictionStatus.PENDING
        mock_service_instance.override_prediction.return_value = override_prediction
        mock_expert_service.return_value = mock_service_instance
        
        # Make request
        response = client.post(
            "/api/v1/expert/predictions/override",
            json={
                "prediction_id": str(mock_prediction.id),
                "home_win_prob": 0.7,
                "draw_prob": 0.2,
                "away_win_prob": 0.1,
                "confidence_score": 0.9,
                "reasoning": "Updated analysis based on recent team news",
            },
            headers={"Authorization": "Bearer mock-token"}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "expert_override"
        assert data["priority_level"] == 100
    
    @patch("app.api.v1.endpoints.expert.get_current_verified_expert_user")
    @patch("app.api.v1.endpoints.expert.get_db")
    def test_override_prediction_not_found(
        self, mock_get_db, mock_get_user, client, mock_expert_user
    ):
        """Test override fails when original prediction not found"""
        # Setup mocks
        mock_get_user.return_value = mock_expert_user
        
        # Mock database query to return None
        mock_db = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_get_db.return_value = mock_db
        
        # Make request
        response = client.post(
            "/api/v1/expert/predictions/override",
            json={
                "prediction_id": str(uuid.uuid4()),
                "home_win_prob": 0.7,
                "draw_prob": 0.2,
                "away_win_prob": 0.1,
                "reasoning": "Updated analysis",
            },
            headers={"Authorization": "Bearer mock-token"}
        )
        
        # Assertions
        assert response.status_code == 404


class TestReviewQueue:
    """Tests for GET /api/v1/expert/predictions/review-queue (KAN-151)"""
    
    @patch("app.api.v1.endpoints.expert.get_current_expert_user")
    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_get_review_queue_success(
        self, mock_expert_service, mock_get_user, client, mock_expert_user, mock_prediction
    ):
        """Test successful retrieval of review queue"""
        # Setup mocks
        mock_get_user.return_value = mock_expert_user
        mock_service_instance = Mock()
        mock_service_instance.get_review_queue.return_value = [mock_prediction]
        mock_expert_service.return_value = mock_service_instance
        
        # Make request
        response = client.get(
            "/api/v1/expert/predictions/review-queue?limit=50&offset=0",
            headers={"Authorization": "Bearer mock-token"}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["status"] == "pending"
    
    @patch("app.api.v1.endpoints.expert.get_current_expert_user")
    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_get_review_queue_with_pagination(
        self, mock_expert_service, mock_get_user, client, mock_expert_user
    ):
        """Test review queue with pagination parameters"""
        # Setup mocks
        mock_get_user.return_value = mock_expert_user
        mock_service_instance = Mock()
        mock_service_instance.get_review_queue.return_value = []
        mock_expert_service.return_value = mock_service_instance
        
        # Make request
        response = client.get(
            "/api/v1/expert/predictions/review-queue?limit=10&offset=20",
            headers={"Authorization": "Bearer mock-token"}
        )
        
        # Assertions
        assert response.status_code == 200
        mock_service_instance.get_review_queue.assert_called_once_with(limit=10, offset=20)


class TestMyPredictions:
    """Tests for GET /api/v1/expert/predictions/my-predictions (KAN-152)"""
    
    @patch("app.api.v1.endpoints.expert.get_current_expert_user")
    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_get_my_predictions_success(
        self, mock_expert_service, mock_get_user, client, mock_expert_user, mock_prediction
    ):
        """Test successful retrieval of expert's own predictions"""
        # Setup mocks
        mock_get_user.return_value = mock_expert_user
        mock_service_instance = Mock()
        mock_service_instance.get_expert_predictions.return_value = [mock_prediction]
        mock_expert_service.return_value = mock_service_instance
        
        # Make request
        response = client.get(
            "/api/v1/expert/predictions/my-predictions",
            headers={"Authorization": "Bearer mock-token"}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1


class TestExpertPerformance:
    """Tests for GET /api/v1/expert/analytics/performance (KAN-153)"""
    
    @patch("app.api.v1.endpoints.expert.get_current_expert_user")
    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_get_expert_performance_success(
        self, mock_expert_service, mock_get_user, client, mock_expert_user, mock_prediction
    ):
        """Test successful retrieval of expert performance metrics"""
        # Setup mocks
        mock_get_user.return_value = mock_expert_user
        mock_service_instance = Mock()
        mock_service_instance.get_expert_predictions.return_value = [mock_prediction]
        mock_expert_service.return_value = mock_service_instance
        
        # Make request
        response = client.get(
            "/api/v1/expert/analytics/performance",
            headers={"Authorization": "Bearer mock-token"}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "expert_id" in data
        assert "total_predictions" in data
        assert "published_predictions" in data
        assert "pending_predictions" in data
        assert "average_confidence" in data

