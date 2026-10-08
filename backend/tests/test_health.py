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


def test_api_health_check(client: TestClient):
    """Test API v1 health check"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["api_version"] == "v1"

