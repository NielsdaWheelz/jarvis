from __future__ import annotations

from pathlib import Path
from runpy import run_path
from typing import Any

import pytest

from jarvis.read_tools import CalendarCoverage

ROOT = Path(__file__).resolve().parents[1]
_QUALIFIER = run_path(str(ROOT / "scripts" / "qualify_calendars.py"))
_QualificationFailure: Any = _QUALIFIER["QualificationFailure"]
_failure_result = _QUALIFIER["_failure_result"]
_minimum_events = _QUALIFIER["_minimum_events"]


def test_live_calendar_minimum_events_is_bounded_and_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JARVIS_LIVE_MIN_EVENTS", "1000")
    assert _minimum_events() == 1_000
    for invalid in ("0", "1501", "01000", "not-an-integer"):
        monkeypatch.setenv("JARVIS_LIVE_MIN_EVENTS", invalid)
        with pytest.raises(ValueError, match="JARVIS_LIVE_MIN_EVENTS"):
            _minimum_events()


def test_incomplete_calendar_failure_exposes_only_typed_coverage() -> None:
    result = _failure_result(
        _QualificationFailure(
            "calendar.list_events",
            "incomplete_coverage",
            coverage=CalendarCoverage(
                complete=False,
                reasons=("calendar_failure", "event_page_limit"),
                calendars_discovered=35,
                calendars_completed=34,
                matched_events=None,
            ),
        )
    )

    assert result["failure"] == {
        "coverage": {
            "calendars_completed": 34,
            "calendars_discovered": 35,
            "matched_events": None,
            "reasons": ["calendar_failure", "event_page_limit"],
        },
        "reason": "incomplete_coverage",
        "stage": "calendar.list_events",
    }


def test_noncoverage_failure_does_not_invent_coverage() -> None:
    result = _failure_result(
        _QualificationFailure("calendar.list_calendars", "too_few_calendars")
    )

    assert result["failure"] == {
        "reason": "too_few_calendars",
        "stage": "calendar.list_calendars",
    }
