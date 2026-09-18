"""
The forecast repair must not rewrite history.

A repair re-reads a payload already on disk. It retrieves nothing, so it must never move the
retrieval time forward -- doing so can turn a forecast obtained before kickoff into an apparent
post-kickoff one, destroying exactly the prematch evidence the snapshot table exists to preserve.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts import repair_forecasts


def test_the_repair_carries_the_original_retrieval_time(monkeypatch):
    """Reproduces the defect directly: the snapshot must be stamped when the payload was fetched."""
    retrieved = datetime(2026, 9, 17, 23, 13, tzinfo=timezone.utc)
    kickoff = retrieved + timedelta(hours=6)
    repaired_at = kickoff + timedelta(hours=3)          # the repair runs after the match kicked off

    class Forecast:
        fetched_at = None

    class Record:
        fetched_at = retrieved.replace(tzinfo=None)

    forecast, record = Forecast(), Record()
    # the two lines the script runs before recording a snapshot
    forecast.fetched_at = (record.fetched_at.replace(tzinfo=timezone.utc)
                           if record.fetched_at and record.fetched_at.tzinfo is None
                           else record.fetched_at)

    from app.services.forecast_service import _retrieved_at
    stamped = _retrieved_at(forecast, repaired_at)

    assert stamped == retrieved
    assert stamped < kickoff, "a repair must not turn a prematch forecast into a post-kickoff one"


def test_the_script_sets_fetched_at_from_the_record():
    """Guards the specific line, so removing it fails here rather than silently in production."""
    source = repair_forecasts.__doc__ or ""
    with open(repair_forecasts.__file__, "r", encoding="utf-8") as handle:
        body = handle.read()
    assert "forecast.fetched_at = (record.fetched_at" in body
    assert "retrieves nothing" in body


def test_repair_leaves_provider_timestamps_and_raw_payload_alone():
    """The repair rewrites derived values only: provenance and evidence are not ours to change."""
    with open(repair_forecasts.__file__, "r", encoding="utf-8") as handle:
        body = handle.read()
    for untouched in ("record.model_run_at", "record.provider_updated_at", "record.raw_payload = ",
                      "record.match_id = ", "record.fetched_at = "):
        assert untouched not in body, f"the repair must not assign {untouched.strip()}"
    columns = {column for column, _ in repair_forecasts.FIELDS}
    assert "exact_score_other_prob" in columns and "home_win_prob" in columns
