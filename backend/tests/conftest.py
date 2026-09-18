"""
Pytest Configuration
Fixtures and test configuration
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.core.config import settings

# Test database URL
TEST_DATABASE_URL = "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test"

# Create test engine
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def db_engine():
    """Create test database engine"""
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create test database session"""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create test client"""
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _no_real_providers(monkeypatch):
    """
    Tests must never reach real data providers, whatever backend/.env contains.
    Force the sample providers and blank every provider credential; individual tests that want
    to exercise provider construction set their own values with monkeypatch.
    """
    monkeypatch.setattr(settings, "DATA_PROVIDER", "sample")
    monkeypatch.setattr(settings, "DATA_PROVIDER_FALLBACKS", "")
    monkeypatch.setattr(settings, "PREDICTION_PROVIDER", "sample")
    monkeypatch.setattr(settings, "LIVESCORE_API_KEY", "")
    monkeypatch.setattr(settings, "LIVESCORE_API_SECRET", "")
    monkeypatch.setattr(settings, "GAMEFORECAST_API_KEY", "")
    monkeypatch.setattr(settings, "API_FOOTBALL_KEY", "")
    monkeypatch.setattr(settings, "THESPORTSDB_KEY", "")
    monkeypatch.setattr(settings, "GAMEFORECAST_LEAGUE_IDS", "")
    monkeypatch.setattr(settings, "LIVESCORE_COMPETITION_IDS", "")
