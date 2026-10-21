"""
Health Check Tests
Test health check endpoints
"""

import json
import logging
import re
from datetime import datetime
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.source_identity import source_identity
from app.main import app


def test_root_endpoint(client: TestClient):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "version" in data
    assert "environment" in data


def test_health_check(client: TestClient):
    """Test basic health check"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["environment"] == settings.ENVIRONMENT and "version" in data


def test_health_publishes_what_the_process_loaded(client: TestClient):
    """A file timestamp cannot say what a process loaded; the process can, and does here: the
    record app.core.source_identity made when it started, not a fresh reading."""
    data = client.get("/health").json()
    source = data["source"]
    assert source == source_identity()
    assert re.fullmatch(r"[0-9a-f]{64}", source["app_tree_sha256"]) and source["app_files"] > 0
    assert source["commit"] is None or re.fullmatch(r"[0-9a-f]{40}", source["commit"])
    dirty = source["commit_dirty_app_files"]
    assert dirty is None or all(path.startswith("backend/app/") for path in dirty)
    assert data["started_at"] == source["started_at"]
    assert datetime.strptime(data["started_at"], "%Y-%m-%dT%H:%M:%SZ")


def test_start_up_logs_the_source_identity(caplog):
    """The identity is on the record from the process's first log lines, so a log alone says what
    a process that has since gone away was running."""
    with caplog.at_level(logging.INFO, logger="app.main"):
        with TestClient(app):
            pass
    identity = source_identity()
    lines = [record.getMessage() for record in caplog.records if record.getMessage().startswith("Source identity:")]
    assert len(lines) == 1
    assert identity["app_tree_sha256"] in lines[0] and str(identity["commit"]) in lines[0]
    assert identity["started_at"] in lines[0] and "://" not in lines[0]


def test_health_names_the_database_and_never_its_url(client: TestClient):
    data = client.get("/health").json()
    assert data["database"] == urlsplit(settings.DATABASE_URL).path.lstrip("/")
    rendered = json.dumps(data)
    assert "://" not in rendered
    assert not settings.POSTGRES_PASSWORD or settings.POSTGRES_PASSWORD not in rendered


def test_health_publishes_every_redis_database_the_process_uses(client: TestClient):
    """The browser preflight (frontend/e2e/support/isolation-preflight.ts) refuses an isolated backend
    unless it says which Redis databases it uses - the default client's and the six roles' - on
    which server, and that its scheduler is off. Database indexes and a port, never a host or a URL."""
    from redis.connection import parse_url

    from app.core.redis import redis_url_for

    data = client.get("/health").json()
    used = sorted({parse_url(redis_url_for(db))["db"] for db in (
        None, settings.REDIS_DB_SESSIONS, settings.REDIS_DB_PREDICTIONS, settings.REDIS_DB_EXPERT_TOOLS,
        settings.REDIS_DB_ML_MODELS, settings.REDIS_DB_MATCH_DATA, settings.REDIS_DB_RATE_LIMIT)})
    assert data["redis_databases"] == used
    default = parse_url(redis_url_for(None))
    assert data["redis_server"] == {"port": default["port"],
                                    "loopback": default.get("host", "localhost") in ("localhost", "127.0.0.1", "::1")}
    assert data["scheduler_enabled"] is settings.SYNC_SCHEDULER_ENABLED
    rendered = json.dumps(data)
    assert "://" not in rendered and str(default.get("host")) not in json.dumps(data["redis_server"])


def test_health_names_the_default_redis_database_not_only_the_roles(client: TestClient, monkeypatch):
    """The isolated backend was started with REDIS_DB_* = 10-15 but no REDIS_DB, so its default
    client - the one /api/v1/health/detailed pings - stayed on .env's database 0, the live sessions
    database. That database must show up here."""
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6390/0")
    monkeypatch.setattr(settings, "REDIS_DB", 0)
    for index, role in enumerate(("SESSIONS", "PREDICTIONS", "EXPERT_TOOLS", "ML_MODELS", "MATCH_DATA", "RATE_LIMIT")):
        monkeypatch.setattr(settings, f"REDIS_DB_{role}", 10 + index)
    assert client.get("/health").json()["redis_databases"] == [0, 10, 11, 12, 13, 14, 15]


def test_api_health_check(client: TestClient):
    """Test API v1 health check"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["api_version"] == "v1"

