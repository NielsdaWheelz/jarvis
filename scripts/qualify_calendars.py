#!/usr/bin/env python3
"""Run a sanitized live qualification of all-calendar discovery and aggregation."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
from llm_agent_kernel import (
    CancellationToken,
    Checkpoint,
    ClaimId,
    DispatchLineage,
    InputId,
    require_host_plan,
)
from llm_tools import ToolId
from sqlalchemy import func, select

from jarvis.admission import ExactToolBudgetFactory
from jarvis.db import action, create_engine
from jarvis.definitions import (
    EXPECTED_GIT_PINS,
    EXPECTED_PACKAGE_VERSIONS,
    build_slice2_definitions,
    verify_runtime_dependencies,
)
from jarvis.read_composition import build_read_catalog
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_tools import CalendarListCalendarsInput, CalendarListEventsInput
from jarvis.settings import Settings


class QualificationFailure(RuntimeError):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(stage)
        self.stage = stage
        self.reason = reason


def _minimum_calendars() -> int:
    raw = os.environ.get("JARVIS_LIVE_MIN_CALENDARS", "2")
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("JARVIS_LIVE_MIN_CALENDARS must be an integer") from None
    if not 1 <= value <= 50 or str(value) != raw:
        raise ValueError("JARVIS_LIVE_MIN_CALENDARS must be canonical and in 1..50")
    return value


async def _run(settings: Settings, minimum_calendars: int) -> dict[str, object]:
    verify_runtime_dependencies()
    clients = tuple(
        httpx.AsyncClient(trust_env=False, follow_redirects=False) for _ in range(4)
    )
    engine = create_engine(settings.database_url.get_secret_value())
    stage = "composition"
    try:
        catalog = build_read_catalog(
            settings=settings,
            google_oauth_http=clients[0],
            google_api_http=clients[1],
            maps_http=clients[2],
            brave_http=clients[3],
        )
        definitions = build_slice2_definitions(
            catalog=catalog,
            profile_key=settings.codex_profile_key,
            model=settings.codex_model,
            owner_timezone=settings.owner_timezone,
        )
        plan = definitions.plans["main"]
        require_host_plan(plan, definitions.main.maximum_profile)
        budgets = ExactToolBudgetFactory().create(plan)
        dispatcher = ReadToolDispatcher(host_secrets=settings.host_secrets)

        async def read(
            tool_name: str, value: object, ordinal: int
        ) -> dict[str, object]:
            nonlocal stage
            stage = tool_name
            completed = await dispatcher.dispatch(
                binding=catalog.binding(ToolId(tool_name)),
                validated_input=value,
                plan=plan,
                budgets=budgets,
                cancellation=CancellationToken(),
                lineage=DispatchLineage(
                    ClaimId("all-calendar-live-claim"),
                    Checkpoint("all-calendar-live-checkpoint"),
                    (InputId("all-calendar-live-input"),),
                    ordinal,
                ),
            )
            result = cast("dict[str, object]", completed.result)
            if result.get("type") != "Success":
                error = cast("dict[str, object]", result.get("error"))
                reason = error.get("type")
                raise QualificationFailure(
                    tool_name,
                    reason if isinstance(reason, str) else "invalid_failure",
                )
            output = result.get("value")
            if not isinstance(output, dict):
                raise QualificationFailure(tool_name, "invalid_success")
            return cast("dict[str, object]", output)

        async with engine.connect() as connection:
            actions_before = cast(
                int,
                await connection.scalar(select(func.count()).select_from(action)),
            )

        discovery = await read(
            "calendar.list_calendars", CalendarListCalendarsInput(), 1
        )
        calendars = cast("list[dict[str, object]]", discovery.get("calendars"))
        if len(calendars) < minimum_calendars:
            raise QualificationFailure("calendar.list_calendars", "too_few_calendars")
        calendar_ids = {
            cast(str, item["calendar_id"])
            for item in calendars
            if isinstance(item.get("calendar_id"), str)
        }
        if len(calendar_ids) != len(calendars):
            raise QualificationFailure("calendar.list_calendars", "invalid_identities")
        if discovery.get("truncated") is not False:
            raise QualificationFailure("calendar.list_calendars", "truncated")

        now = datetime.now(UTC)
        aggregate = await read(
            "calendar.list_events",
            CalendarListEventsInput(
                time_min=now - timedelta(days=30),
                time_max=now + timedelta(days=365),
                time_zone=settings.owner_timezone,
                max_results=50,
            ),
            2,
        )
        scanned = cast("list[dict[str, object]]", aggregate.get("calendars"))
        scanned_ids = {
            cast(str, item["calendar_id"])
            for item in scanned
            if isinstance(item.get("calendar_id"), str)
        }
        if scanned_ids != calendar_ids:
            raise QualificationFailure("calendar.list_events", "calendar_set_changed")
        failures = cast("list[dict[str, object]]", aggregate.get("failures"))
        if failures:
            raise QualificationFailure("calendar.list_events", "partial_failure")
        events = cast("list[dict[str, object]]", aggregate.get("events"))
        if any(item.get("calendar_id") not in calendar_ids for item in events):
            raise QualificationFailure("calendar.list_events", "unknown_event_calendar")

        async with engine.connect() as connection:
            actions_after = cast(
                int,
                await connection.scalar(select(func.count()).select_from(action)),
            )
        if actions_after != actions_before:
            raise QualificationFailure("actions", "automatic_read_created_action")
        if dispatcher.recorder.terminal_count != 2:
            raise QualificationFailure("dispatch", "incomplete_terminal_record")
        if dispatcher.recorder.uncertain_count != 0:
            raise QualificationFailure("dispatch", "uncertain_read")

        roles: dict[str, int] = {}
        for calendar in calendars:
            role = calendar.get("access_role")
            if not isinstance(role, str):
                raise QualificationFailure("calendar.list_calendars", "invalid_role")
            roles[role] = roles.get(role, 0) + 1
        return {
            "calendar": {
                "calendars": len(calendars),
                "event_source_calendars": len(
                    {cast(str, item["calendar_id"]) for item in events}
                ),
                "events": len(events),
                "events_truncated": aggregate.get("truncated"),
                "hidden": sum(item.get("hidden") is True for item in calendars),
                "primary": sum(item.get("primary") is True for item in calendars),
                "roles": dict(sorted(roles.items())),
                "selected": sum(item.get("selected") is True for item in calendars),
            },
            "identities": {
                "main_definition_fingerprint": definitions.main.fingerprint,
                "main_plan_revision": plan.plan_revision,
                "session_compatibility_revision": (
                    definitions.main.session_compatibility_revision
                ),
            },
            "revisions": {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS},
            "status": "passed",
            "tool_dispatch": {
                "calls": 2,
                "terminal": dispatcher.recorder.terminal_count,
                "uncertain": dispatcher.recorder.uncertain_count,
                "zero_actions": True,
            },
        }
    except QualificationFailure:
        raise
    except BaseException:
        raise QualificationFailure(stage, "unexpected_exception") from None
    finally:
        await engine.dispose()
        for client in clients:
            await client.aclose()


def main() -> int:
    try:
        if os.environ.get("JARVIS_CALENDAR_LIVE") != "1":
            raise ValueError(
                "live Calendar qualification requires JARVIS_CALENDAR_LIVE=1"
            )
        result = asyncio.run(_run(Settings.from_env(), _minimum_calendars()))
    except QualificationFailure as exc:
        result = {
            "failure": {"reason": exc.reason, "stage": exc.stage},
            "revisions": {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS},
            "status": "failed",
        }
    except BaseException as exc:
        result = {
            "failure": {"reason": type(exc).__name__, "stage": "setup"},
            "revisions": {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS},
            "status": "failed",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
