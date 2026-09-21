"""
Integration tests for Expert API endpoints

Tests all 5 Expert API endpoints (KAN-149 through KAN-153).

Authentication
--------------
These endpoints authenticate through FastAPI dependencies. Patching the module attribute
``app.api.v1.endpoints.expert.get_current_verified_expert_user`` does **not** replace a dependency:
FastAPI captured the dependency callable when the route was declared, so the real authentication
dependency kept running and rejected every request with 401.

The supported mechanism is ``app.dependency_overrides``, used by the ``client`` fixture below. It
replaces the dependency for this test client only; production authentication is untouched and the
running application still accepts no mock token (see ``TestAuthenticationIsStillEnforced``).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.deps import (
    get_current_expert_user,
    get_current_verified_expert_user,
)
from app.core.deps import get_db as deps_get_db
from app.db.session import get_db as session_get_db
from app.main import app
from app.models.predictions import Prediction, PredictionSource, PredictionStatus
from app.models.users import User, UserType

# Fixed, naive UTC timestamps - the columns are naive UTC, and the response must mark them as UTC.
CREATED_AT = datetime(2025, 10, 13, 22, 30, 0)
KICKOFF = datetime(2025, 10, 13, 23, 45, 0)


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
def mock_db():
    """
    Database session stand-in.

    ``first()`` returns None by default (nothing found); a test that needs a row assigns
    ``mock_db.query.return_value.filter.return_value.first.return_value``.
    """
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


@pytest.fixture
def client(mock_db, mock_expert_user):
    """
    Test client with the database and the expert authentication dependencies overridden.

    Both ``get_db`` callables are overridden (``app.core.deps`` for the expert router,
    ``app.db.session`` for the public routers) so that no test can reach a real database.
    """
    def override_get_db():
        yield mock_db

    overrides = {
        deps_get_db: override_get_db,
        session_get_db: override_get_db,
        get_current_expert_user: lambda: mock_expert_user,
        get_current_verified_expert_user: lambda: mock_expert_user,
    }
    app.dependency_overrides.update(overrides)
    try:
        # No context manager: the startup event initialises the real database, which these tests
        # neither need nor should touch.
        yield TestClient(app)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)


def _make_prediction(
    source: PredictionSource = PredictionSource.EXPERT_MANUAL,
    status: PredictionStatus = PredictionStatus.PENDING,
) -> Mock:
    """
    A prediction as the service returns it.

    Every optional market is explicitly None: a market the expert did not fill in is *unavailable*,
    and must never be serialised as 0.0. Leaving them as auto-created Mock attributes also fails
    response validation.
    """
    prediction = Mock(spec=Prediction)
    prediction.id = uuid.uuid4()
    prediction.match_id = uuid.uuid4()
    prediction.source = source
    prediction.priority_level = 100
    prediction.home_win_prob = Decimal("0.6000")
    prediction.draw_prob = Decimal("0.2500")
    prediction.away_win_prob = Decimal("0.1500")
    prediction.confidence_score = Decimal("0.8500")
    # Unavailable markets - never 0.0
    prediction.btts_yes_prob = None
    prediction.btts_no_prob = None
    prediction.btts_confidence = None
    prediction.total_goals_over_25_prob = None
    prediction.total_goals_under_25_prob = None
    prediction.total_goals_over_35_prob = None
    prediction.total_goals_under_35_prob = None
    prediction.total_goals_confidence = None
    prediction.key_factors = None
    prediction.reasoning = "Expert analysis"
    prediction.status = status
    prediction.created_by = uuid.uuid4()
    prediction.created_at = CREATED_AT
    prediction.published_at = None
    prediction.unpublished_at = None
    prediction.is_test_data = None
    prediction.superseded_by = None
    prediction.prediction_metadata = {}
    return prediction


def _enriched(prediction) -> Dict[str, Any]:
    """
    Stand-in for ``ExpertPredictionService.enrich_prediction_with_details``.

    The real method returns a plain dict; without this stub the mocked service hands the endpoint a
    MagicMock, which cannot be serialised into ExpertPredictionResponse.
    """
    return {
        "id": str(prediction.id),
        "match_id": str(prediction.match_id),
        "source": prediction.source.value,
        "priority_level": prediction.priority_level,
        "home_win_prob": float(prediction.home_win_prob),
        "draw_prob": float(prediction.draw_prob),
        "away_win_prob": float(prediction.away_win_prob),
        # Mirrors the real method, which now guards this: predictions.confidence_score is
        # nullable, so a prediction whose author supplied no conviction reaches here as None and a
        # bare float() would both crash and, if it did not, invent a conviction of zero.
        "confidence_score": (float(prediction.confidence_score)
                             if prediction.confidence_score is not None else None),
        # Unavailable markets stay None
        "btts_yes_prob": None,
        "btts_no_prob": None,
        "btts_confidence": None,
        "total_goals_over_25_prob": None,
        "total_goals_under_25_prob": None,
        "total_goals_over_35_prob": None,
        "total_goals_under_35_prob": None,
        "total_goals_confidence": None,
        "reasoning": prediction.reasoning,
        "key_factors": None,
        "status": prediction.status.value,
        "created_by": str(prediction.created_by),
        "created_at": prediction.created_at,
        "published_at": prediction.published_at,
        "superseded_by": None,
        "match_details": {
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
            "home_team_logo": None,
            "away_team_logo": None,
            "league_name": "Premier League",
            "match_date": KICKOFF,
            "external_match_id": "12345",
        },
        "user_details": {"username": "expert_user", "first_name": None, "last_name": None},
    }


def _service_mock(predictions=None) -> Mock:
    """Mocked ExpertPredictionService instance with a dict-returning enrichment stub."""
    instance = Mock()
    instance.get_review_queue.return_value = list(predictions or [])
    instance.get_expert_predictions.return_value = list(predictions or [])
    instance.enrich_prediction_with_details.side_effect = _enriched
    return instance


@pytest.fixture
def mock_prediction():
    """Mock prediction"""
    return _make_prediction()


class TestCreateManualPrediction:
    """Tests for POST /api/v1/expert/predictions/manual (KAN-149)"""

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_create_manual_prediction_success(
        self, mock_audit_service, mock_expert_service, client, mock_expert_user, mock_prediction
    ):
        """Test successful manual prediction creation"""
        # Setup mocks
        mock_service_instance = _service_mock()
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
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["source"] == "expert_manual"
        assert data["priority_level"] == 100
        assert data["status"] == "pending"

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_create_manual_prediction_leaves_unsupplied_markets_unavailable(
        self, mock_audit_service, mock_expert_service, client, mock_prediction
    ):
        """Markets the expert did not fill in are serialised as null, never as 0%."""
        mock_service_instance = _service_mock()
        mock_service_instance.create_manual_prediction.return_value = mock_prediction
        mock_expert_service.return_value = mock_service_instance

        response = client.post(
            "/api/v1/expert/predictions/manual",
            json={
                "match_id": str(uuid.uuid4()),
                "home_win_prob": 0.6,
                "draw_prob": 0.25,
                "away_win_prob": 0.15,
                "confidence_score": 0.85,
            },
            headers={"Authorization": "Bearer mock-token"}
        )

        assert response.status_code == 200, response.text
        data = response.json()
        for market in ("btts_yes_prob", "btts_no_prob", "btts_confidence",
                       "total_goals_over_25_prob", "total_goals_under_25_prob",
                       "total_goals_over_35_prob", "total_goals_under_35_prob",
                       "total_goals_confidence"):
            assert data[market] is None, f"{market} must be unavailable (null), not {data[market]!r}"

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_a_conviction_the_expert_did_not_supply_is_serialised_as_null(
        self, mock_audit_service, mock_expert_service, client
    ):
        """The headline conviction gets the same treatment every optional market already had.

        It did not used to. predictions.confidence_score was NOT NULL, the service coerced a
        missing conviction to Decimal("0.0") on the way in, and ExpertPredictionResponse declared
        the field a required float - three separate places that made "the author said nothing"
        indistinguishable from "the author said zero". This request supplies no conviction and the
        response must carry null, because that is the only value that means nobody claimed one.
        """
        stored = _make_prediction()
        stored.confidence_score = None
        mock_service_instance = _service_mock()
        mock_service_instance.create_manual_prediction.return_value = stored
        mock_expert_service.return_value = mock_service_instance

        response = client.post(
            "/api/v1/expert/predictions/manual",
            json={
                "match_id": str(uuid.uuid4()),
                "home_win_prob": 0.6,
                "draw_prob": 0.25,
                "away_win_prob": 0.15,
                "reasoning": "No conviction offered on this one",
            },
            headers={"Authorization": "Bearer mock-token"}
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert "confidence_score" in data, "the field must be present and null, not omitted"
        assert data["confidence_score"] is None, (
            f"an unsupplied conviction was serialised as {data['confidence_score']!r}")

        # And the request really did reach the service without one, rather than the endpoint
        # having filled a default in on the way past.
        sent = mock_service_instance.create_manual_prediction.call_args.args[0]
        assert sent.confidence_score is None

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_a_conviction_of_zero_is_still_serialised_as_zero(
        self, mock_audit_service, mock_expert_service, client
    ):
        """The control. An expert who types 0 has claimed something and the API must transmit it.

        If this test and the one above ever agree, the distinction has been collapsed again -
        usually by somebody writing `if data.confidence_score` instead of `is not None`.
        """
        stored = _make_prediction()
        stored.confidence_score = Decimal("0.0000")
        mock_service_instance = _service_mock()
        mock_service_instance.create_manual_prediction.return_value = stored
        mock_expert_service.return_value = mock_service_instance

        response = client.post(
            "/api/v1/expert/predictions/manual",
            json={
                "match_id": str(uuid.uuid4()),
                "home_win_prob": 0.6,
                "draw_prob": 0.25,
                "away_win_prob": 0.15,
                "confidence_score": 0.0,
                "reasoning": "I stand behind this one not at all",
            },
            headers={"Authorization": "Bearer mock-token"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["confidence_score"] == 0.0

        sent = mock_service_instance.create_manual_prediction.call_args.args[0]
        assert sent.confidence_score == 0.0, "a claimed zero was dropped before it reached the service"

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_create_manual_prediction_timestamps_are_utc_with_z(
        self, mock_audit_service, mock_expert_service, client, mock_prediction
    ):
        """Timestamps leave the API as UTC ISO-8601 with a trailing Z (KAN kickoff-day bug)."""
        mock_service_instance = _service_mock()
        mock_service_instance.create_manual_prediction.return_value = mock_prediction
        mock_expert_service.return_value = mock_service_instance

        response = client.post(
            "/api/v1/expert/predictions/manual",
            json={
                "match_id": str(uuid.uuid4()),
                "home_win_prob": 0.6,
                "draw_prob": 0.25,
                "away_win_prob": 0.15,
            },
            headers={"Authorization": "Bearer mock-token"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["created_at"] == "2025-10-13T22:30:00Z"

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

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_a_triple_the_table_would_refuse_never_reaches_the_service(
        self, mock_expert_service, client
    ):
        """34 / 33 / 34 is refused on the request, not by the insert.

        It is inside a 0.99-1.01 tolerance and outside ck_predictions_prob_sum, which is exact
        equality, so a tolerant request validator would send it on to an insert that cannot take
        it. What the expert gets back then is a refusal nobody can act on - the write is lost and
        the reply can only report that the database said no. A 422 naming the field and the total
        is the answer they can act on, and the service is never reached.
        """
        mock_expert_service.return_value = _service_mock()

        response = client.post(
            "/api/v1/expert/predictions/manual",
            json={
                "match_id": str(uuid.uuid4()),
                "home_win_prob": 0.34,
                "draw_prob": 0.33,
                "away_win_prob": 0.34,
            },
            headers={"Authorization": "Bearer mock-token"}
        )

        assert response.status_code == 422, response.text
        assert "sum to exactly 1" in response.text
        assert "CheckViolation" not in response.text and "INSERT" not in response.text
        mock_expert_service.return_value.create_manual_prediction.assert_not_called()


class TestOverridePrediction:
    """Tests for POST /api/v1/expert/predictions/override (KAN-150)"""

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_override_prediction_success(
        self, mock_audit_service, mock_expert_service,
        client, mock_db, mock_expert_user, mock_prediction
    ):
        """Test successful prediction override"""
        # The original prediction is found in the database
        mock_db.query.return_value.filter.return_value.first.return_value = mock_prediction

        # Mock service
        mock_service_instance = _service_mock()
        override_prediction = _make_prediction(source=PredictionSource.EXPERT_OVERRIDE)
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
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["source"] == "expert_override"
        assert data["priority_level"] == 100

    def test_override_prediction_not_found(self, client, mock_db, mock_expert_user):
        """Test override fails when original prediction not found"""
        # Nothing in the database for this id
        mock_db.query.return_value.filter.return_value.first.return_value = None

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

        # Assertions: the 404 must survive the endpoint's catch-all error handling
        assert response.status_code == 404, response.text
        assert "not found" in response.json()["detail"].lower()


#: A constraint violation as psycopg2 reports one, with everything a raw ``str(error)`` would put
#: in front of the caller: the constraint's name, the failing row, and the statement.
def _check_violation() -> IntegrityError:
    return IntegrityError(
        "INSERT INTO predictions.predictions (id, match_id, home_win_prob, draw_prob, "
        "away_win_prob) VALUES (%(id)s, %(match_id)s, %(home_win_prob)s, ...)",
        {},
        Exception('new row for relation "predictions" violates check constraint '
                  '"ck_predictions_prob_sum"\nDETAIL:  Failing row contains '
                  '(3f1c..., 0.3400, 0.3300, 0.3400, expert_manual, ...).'),
    )


#: Nothing the driver said may travel to the caller. Each of these appears in ``str`` of the
#: error above and in none of the replies below.
DRIVER_TEXT = ("ck_predictions", "Failing row", "INSERT", "predictions.predictions", "0.3400")


class TestTheDatabaseRefusalIsNotDescribedWrongly:
    """What the three write endpoints say when the table rejects the row.

    TWO THINGS ARE PINNED, AND THEY FAIL IN OPPOSITE DIRECTIONS.

    The driver's text is not a reply. ``str`` of a psycopg2 IntegrityError carries the constraint
    name, every column of the failing row and the statement that carried it; putting that in
    ``detail`` publishes the schema and the row to whoever made the request, and still tells the
    expert nothing they can do about it.

    Nor may the reply invent a cause. The handler cannot tell which constraint fired without
    parsing the driver's message, and the table carries eight CHECKs. A reply that names two of
    them - "every probability must be within 0-1, and btts_yes_prob and btts_no_prob must sum to
    1.0 when both are present" - reads as the whole list and is a guess. Against a triple that
    violates ck_predictions_prob_sum, both halves of that sentence are true of what the expert
    sent and neither is the rule they broke.

    So each reply reports the refusal, says which record is untouched, and claims nothing about
    the cause. All three paths are covered because all three write a row, and a handler added to
    one of them is not a rule.
    """

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_the_reply_does_not_name_rules_it_cannot_know_were_broken(
        self, mock_audit_service, mock_expert_service, client
    ):
        instance = _service_mock()
        instance.update_prediction_with_revision.side_effect = IntegrityError(
            "INSERT ...", {}, Exception('violates check constraint "ck_predictions_prob_sum"'))
        mock_expert_service.return_value = instance

        response = client.put(
            f"/api/v1/expert/predictions/{uuid.uuid4()}",
            json={"home_win_prob": 0.6, "draw_prob": 0.25, "away_win_prob": 0.15},
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert "nothing was saved" in detail
        assert "the stored prediction is unchanged" in detail
        for claim in ("btts_yes_prob", "btts_no_prob", "within 0-1", "ck_predictions"):
            assert claim not in detail, f"the reply asserts {claim!r} about a failure it cannot identify"

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_a_refused_create_does_not_hand_the_expert_the_drivers_message(
        self, mock_audit_service, mock_expert_service, client
    ):
        """The create path answers a refused insert without quoting the driver.

        A catch-all that formats ``str(exception)`` into the detail cannot tell an IntegrityError
        from anything else, so this path needs its own handler: without one the reply carries the
        constraint name, the failing row and the INSERT statement.
        """
        instance = _service_mock()
        instance.create_manual_prediction.side_effect = _check_violation()
        mock_expert_service.return_value = instance

        response = client.post(
            "/api/v1/expert/predictions/manual",
            json={"match_id": str(uuid.uuid4()),
                  "home_win_prob": 0.6, "draw_prob": 0.25, "away_win_prob": 0.15},
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert "nothing was saved" in detail
        assert "no prediction was created" in detail, "the reply has to say what did not happen"
        for leaked in DRIVER_TEXT:
            assert leaked not in response.text, f"the driver's {leaked!r} reached the caller"

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_a_refused_override_does_not_hand_the_expert_the_drivers_message(
        self, mock_audit_service, mock_expert_service, client, mock_db, mock_prediction
    ):
        """The override path writes a row too, and answers a refusal the same way."""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_prediction
        instance = _service_mock()
        instance.override_prediction.side_effect = _check_violation()
        mock_expert_service.return_value = instance

        response = client.post(
            "/api/v1/expert/predictions/override",
            json={"prediction_id": str(mock_prediction.id),
                  "home_win_prob": 0.6, "draw_prob": 0.25, "away_win_prob": 0.15,
                  "reasoning": "Team news changed after the line was published."},
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert "nothing was saved" in detail
        assert "the original prediction is unchanged" in detail
        for leaked in DRIVER_TEXT:
            assert leaked not in response.text, f"the driver's {leaked!r} reached the caller"


class TestWithdrawingAValueSurvivesTheWire:
    """Tests for PUT /api/v1/expert/predictions/{id} — what the request body actually said.

    The service can only tell "cleared" from "not mentioned" if that distinction survives the
    HTTP boundary, so it is worth pinning here rather than assuming it. FastAPI validates this
    body straight from the request JSON, so ``model_fields_set`` on the schema the endpoint hands
    the service holds exactly the keys the browser sent - an absent key is not in it, an explicit
    ``null`` is. The first two tests are the evidence for that claim; if a future refactor builds
    the schema some other way (from a full-body model, or with defaults filled in first), they
    fail here rather than silently resurrecting the withdrawn conviction in the database.

    The last two are the limit of the withdrawal rule. Clearing is per key, and half a
    complementary market is not a smaller claim but an incoherent one, so the pair has to move
    together - and the caller has to be told which other side is missing, in the answer the
    endpoint actually sends.
    """

    @staticmethod
    def _service_with_revision(stored):
        instance = _service_mock()
        revision = Mock()
        revision.id = uuid.uuid4()
        revision.old_values = {}
        instance.update_prediction_with_revision.return_value = (stored, revision)
        return instance

    @staticmethod
    def _body(**extra):
        return {"home_win_prob": 0.6, "draw_prob": 0.25, "away_win_prob": 0.15, **extra}

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_an_explicit_null_reaches_the_service_as_an_explicit_null(
        self, mock_audit_service, mock_expert_service, client
    ):
        stored = _make_prediction(status=PredictionStatus.PUBLISHED)
        stored.confidence_score = None
        instance = self._service_with_revision(stored)
        mock_expert_service.return_value = instance

        response = client.put(
            f"/api/v1/expert/predictions/{uuid.uuid4()}",
            json=self._body(confidence_score=None),
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 200, response.text
        sent = instance.update_prediction_with_revision.call_args.args[1]
        assert sent.confidence_score is None
        assert "confidence_score" in sent.model_fields_set, (
            "the endpoint lost the difference between a cleared field and an absent one")
        assert response.json()["confidence_score"] is None

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_an_omitted_field_reaches_the_service_as_omitted(
        self, mock_audit_service, mock_expert_service, client
    ):
        """The control. Same None on the model, and it must not be read as a withdrawal."""
        stored = _make_prediction(status=PredictionStatus.PUBLISHED)
        instance = self._service_with_revision(stored)
        mock_expert_service.return_value = instance

        response = client.put(
            f"/api/v1/expert/predictions/{uuid.uuid4()}",
            json=self._body(),
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 200, response.text
        sent = instance.update_prediction_with_revision.call_args.args[1]
        assert sent.confidence_score is None
        assert "confidence_score" not in sent.model_fields_set

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_withdrawing_one_side_of_a_pair_is_refused_before_the_service_is_called(
        self, mock_audit_service, mock_expert_service, client
    ):
        """The half-pair body is stopped at the boundary, and the answer names the other half.

        Refusing here rather than in the service is what makes the answer usable: the database
        would have accepted this row (its BTTS CHECK is satisfied by a NULL), and if it had
        refused, the message would have been a constraint name.
        """
        instance = self._service_with_revision(_make_prediction(status=PredictionStatus.PUBLISHED))
        mock_expert_service.return_value = instance

        response = client.put(
            f"/api/v1/expert/predictions/{uuid.uuid4()}",
            json=self._body(btts_yes_prob=None),
            headers={"Authorization": "Bearer mock-token"},
        )

        # 422 and not 401/403: the exact code matters here, because a body assertion alone would
        # also be satisfied by the endpoint refusing the caller for some unrelated reason.
        assert response.status_code == 422, response.text
        assert "btts_no_prob" in response.text, (
            "the refusal must name the side that was left standing")
        instance.update_prediction_with_revision.assert_not_called()

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_withdrawing_both_sides_of_a_pair_reaches_the_service_as_two_explicit_nulls(
        self, mock_audit_service, mock_expert_service, client
    ):
        """The control: withdrawing the market whole is exactly what the rule has to permit.

        The market's conviction goes down with it. A body that took the two probabilities away
        and said nothing about btts_confidence would leave the expert's stated conviction in
        BTTS standing over a market with no outcomes, so it is refused - the test below.
        """
        stored = _make_prediction(status=PredictionStatus.PUBLISHED)
        instance = self._service_with_revision(stored)
        mock_expert_service.return_value = instance

        response = client.put(
            f"/api/v1/expert/predictions/{uuid.uuid4()}",
            json=self._body(btts_yes_prob=None, btts_no_prob=None, btts_confidence=None),
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 200, response.text
        sent = instance.update_prediction_with_revision.call_args.args[1]
        assert sent.btts_yes_prob is None and sent.btts_no_prob is None
        assert sent.btts_confidence is None
        assert {"btts_yes_prob", "btts_no_prob", "btts_confidence"} <= sent.model_fields_set

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    @patch("app.api.v1.endpoints.expert.PredictionAuditService")
    def test_withdrawing_a_market_while_raising_its_conviction_is_refused_by_the_endpoint(
        self, mock_audit_service, mock_expert_service, client
    ):
        """One PUT took the BTTS market down and put the conviction in it up to 90%.

        Both halves validate on their own, and together they store a stated conviction about a
        market the same request had just emptied. The refusal has to happen on the way in: the
        service writes what the body says, so nothing further down would have caught it.
        """
        instance = self._service_with_revision(_make_prediction(status=PredictionStatus.PUBLISHED))
        mock_expert_service.return_value = instance

        response = client.put(
            f"/api/v1/expert/predictions/{uuid.uuid4()}",
            json=self._body(btts_yes_prob=None, btts_no_prob=None, btts_confidence=0.9),
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 422, response.text
        assert "btts_confidence" in response.text
        instance.update_prediction_with_revision.assert_not_called()


class TestReviewQueue:
    """Tests for GET /api/v1/expert/predictions/review-queue (KAN-151)"""

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_get_review_queue_success(
        self, mock_expert_service, client, mock_expert_user, mock_prediction
    ):
        """Test successful retrieval of review queue"""
        # Setup mocks
        mock_service_instance = _service_mock([mock_prediction])
        mock_expert_service.return_value = mock_service_instance

        # Make request
        response = client.get(
            "/api/v1/expert/predictions/review-queue?limit=50&offset=0",
            headers={"Authorization": "Bearer mock-token"}
        )

        # Assertions
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["status"] == "pending"
        # Kickoff and creation time are UTC-marked, so the browser cannot shift them a day
        assert data[0]["created_at"].endswith("Z")
        assert data[0]["match_details"]["match_date"] == "2025-10-13T23:45:00Z"

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_get_review_queue_with_pagination(
        self, mock_expert_service, client, mock_expert_user
    ):
        """Test review queue with pagination parameters"""
        # Setup mocks
        mock_service_instance = _service_mock([])
        mock_expert_service.return_value = mock_service_instance

        # Make request
        response = client.get(
            "/api/v1/expert/predictions/review-queue?limit=10&offset=20",
            headers={"Authorization": "Bearer mock-token"}
        )

        # Assertions
        assert response.status_code == 200, response.text
        mock_service_instance.get_review_queue.assert_called_once_with(limit=10, offset=20)


class TestMyPredictions:
    """Tests for GET /api/v1/expert/predictions/my-predictions (KAN-152)"""

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_get_my_predictions_success(
        self, mock_expert_service, client, mock_expert_user, mock_prediction
    ):
        """Test successful retrieval of expert's own predictions"""
        # Setup mocks
        mock_service_instance = _service_mock([mock_prediction])
        mock_expert_service.return_value = mock_service_instance

        # Make request
        response = client.get(
            "/api/v1/expert/predictions/my-predictions",
            headers={"Authorization": "Bearer mock-token"}
        )

        # Assertions
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_get_my_predictions_rejects_unknown_status_filter(
        self, mock_expert_service, client, mock_expert_user
    ):
        """An unknown status filter is a client error, not a 500."""
        mock_expert_service.return_value = _service_mock([])

        response = client.get(
            "/api/v1/expert/predictions/my-predictions?status=not-a-status",
            headers={"Authorization": "Bearer mock-token"}
        )

        assert response.status_code == 400, response.text


class TestExpertPerformance:
    """Tests for GET /api/v1/expert/analytics/performance (KAN-153)"""

    @patch("app.api.v1.endpoints.expert.ExpertPredictionService")
    def test_get_expert_performance_success(
        self, mock_expert_service, client, mock_expert_user, mock_prediction
    ):
        """Test successful retrieval of expert performance metrics"""
        # Setup mocks
        mock_service_instance = _service_mock([mock_prediction])
        mock_expert_service.return_value = mock_service_instance

        # Make request
        response = client.get(
            "/api/v1/expert/analytics/performance",
            headers={"Authorization": "Bearer mock-token"}
        )

        # Assertions
        assert response.status_code == 200, response.text
        data = response.json()
        assert "expert_id" in data
        assert "total_predictions" in data
        assert "published_predictions" in data
        assert "pending_predictions" in data
        assert "average_confidence" in data


class TestAuthenticationIsStillEnforced:
    """
    The dependency overrides above are a test-only mechanism: with real authentication in place the
    application accepts neither a missing token nor the fake "Bearer mock-token".
    """

    @pytest.fixture
    def unauthenticated_client(self, mock_db):
        """Client with only the database overridden - authentication stays real."""
        def override_get_db():
            yield mock_db

        overrides = {deps_get_db: override_get_db, session_get_db: override_get_db}
        app.dependency_overrides.update(overrides)
        try:
            yield TestClient(app)
        finally:
            for dependency in overrides:
                app.dependency_overrides.pop(dependency, None)

    def test_missing_token_is_rejected(self, unauthenticated_client):
        response = unauthenticated_client.get("/api/v1/expert/predictions/my-predictions")
        assert response.status_code in (401, 403), response.text

    def test_mock_token_is_rejected(self, unauthenticated_client):
        response = unauthenticated_client.get(
            "/api/v1/expert/predictions/my-predictions",
            headers={"Authorization": "Bearer mock-token"}
        )
        assert response.status_code == 401, response.text
