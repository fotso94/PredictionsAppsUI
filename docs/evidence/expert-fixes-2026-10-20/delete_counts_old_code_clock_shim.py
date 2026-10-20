"""Old-code clock shim - loaded ONLY for the before-behaviour evidence run of the delete-retry tests.

The old ExpertPredictionService has no ``clock`` argument, so the delete-retry tests in
backend/tests/services/test_expert_history.py cannot even construct it there: they fail with
TypeError, which proves only that the API was missing. This pytest plugin lets the OLD code run the
same timeline instead. It accepts ``clock=`` on the constructor and makes the old module's
``datetime.utcnow()`` return that clock's current value. It changes no product logic: the old
delete_prediction still runs exactly as written, so what the tests then report is its behaviour.

Usage (from backend/, on the unchanged product code only):
    PYTHONPATH=../docs/evidence/expert-fixes-2026-10-20 ... pytest -p delete_counts_old_code_clock_shim ...
"""
from datetime import datetime as _real_datetime

import pytest


@pytest.fixture(autouse=True)
def _old_code_clock(monkeypatch):
    import app.services.expert_prediction as module

    current = {"clock": None}

    class ShimDatetime(_real_datetime):
        @classmethod
        def utcnow(cls):
            clock = current["clock"]
            return clock() if clock is not None else _real_datetime.utcnow()

    original_init = module.ExpertPredictionService.__init__

    def init(self, db, cache_service=None, clock=None):
        original_init(self, db, cache_service)
        if clock is not None:
            current["clock"] = clock

    monkeypatch.setattr(module.ExpertPredictionService, "__init__", init)
    monkeypatch.setattr(module, "datetime", ShimDatetime)
