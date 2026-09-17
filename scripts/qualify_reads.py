#!/usr/bin/env python3
"""Run sanitized live Slice 2 Gmail, Calendar, Maps, and Web reads."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx
from llm_agent_kernel import (
    CancellationToken,
    InitialReadDispatchLineage,
    RunId,
    require_host_plan,
)
from llm_tools import ToolId, WebReadInput, WebSearchInput
from sqlalchemy import func, select

from jarvis.actions import ActionStore
from jarvis.admission import ExactToolBudgetFactory
from jarvis.agent_control import AgentController
from jarvis.db import action, create_engine
from jarvis.definitions import (
    EXPECTED_GIT_PINS,
    EXTERNAL_READ_IDS,
    build_definitions,
    build_write_gate,
    verify_runtime_dependencies,
)
from jarvis.embeddings import OpenAIEmbedder
from jarvis.kernel import build_agent_runtime, resolve_provider_configuration
from jarvis.memory_retrieval import PostgresMemoryRepository
from jarvis.ownership import deployment_ownership
from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder
from jarvis.read_tools import (
    AddressLocation,
    CalendarGetEventInput,
    CalendarListCalendarsInput,
    CalendarListEventsInput,
    GmailReadThreadInput,
    GmailSearchInput,
    MapsDirectionsInput,
    MapsGetPlaceInput,
    MapsSearchPlacesInput,
    PlaceLocation,
)
from jarvis.settings import Settings
from jarvis.tool_composition import build_tool_composition


class QualificationFailure(RuntimeError):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(stage)
        self.stage = stage
        self.reason = reason


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty without edge whitespace")
    return value


def _implementation() -> dict[str, str]:
    lock = Path(__file__).resolve().parents[1] / "uv.lock"
    return {
        "architecture": platform.machine().lower(),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "os": platform.system().lower(),
    }


async def _run(settings: Settings) -> dict[str, object]:
    verify_runtime_dependencies()
    gmail_query = _required("JARVIS_LIVE_GMAIL_QUERY")
    maps_query = _required("JARVIS_LIVE_MAPS_QUERY")
    maps_origin = _required("JARVIS_LIVE_MAPS_ORIGIN")
    web_query = _required("JARVIS_LIVE_WEB_QUERY")
    now = datetime.now(UTC)
    clients = tuple(
        httpx.AsyncClient(trust_env=False, follow_redirects=False) for _ in range(5)
    )
    raw_engine = create_engine(settings.database_url.get_secret_value())
    async with AsyncExitStack() as database_lifetime:
        database_lifetime.push_async_callback(raw_engine.dispose)
        engine = await database_lifetime.enter_async_context(
            deployment_ownership(raw_engine)
        )
        host = settings.codex_host_config
        agent_runtime = build_agent_runtime(
            provider_state_root=settings.runtime_state_directory,
            codex_endpoints=host.endpoints,
        )
        database_lifetime.push_async_callback(agent_runtime.close)
        stage = "composition"
        try:
            provider_configuration = await resolve_provider_configuration(
                runtime=agent_runtime,
                profile_key=settings.codex_profile_key,
                model_key=settings.codex_model,
            )
            gate, _ = build_write_gate(
                provider=provider_configuration,
            )
            catalog = build_tool_composition(
                settings=settings,
                google_oauth_http=clients[0],
                google_api_http=clients[1],
                maps_http=clients[2],
                brave_http=clients[3],
                memory_repository=PostgresMemoryRepository(engine),
                memory_embedder=OpenAIEmbedder(
                    settings.embedding_openai_api_key,
                    http_client=clients[4],
                ),
                actions=ActionStore(engine),
                agents=AgentController(
                    executable=settings.agent_cli_path,
                    client_config=settings.agent_client_config_path,
                    actions=ActionStore(engine),
                ),
                automatic_write_gate_definition_fingerprint=gate.fingerprint,
            ).catalog
            definitions = build_definitions(
                catalog=catalog,
                provider=provider_configuration,
                owner_timezone=settings.owner_timezone,
            )
            plan = definitions.plans["main"]
            require_host_plan(plan, definitions.main.maximum_profile)
            budgets = ExactToolBudgetFactory().create(plan)
            run_id = RunId(str(uuid4()))
            dispatcher = ReadToolDispatcher(
                recorder=RunReadRecorder(), host_secrets=settings.host_secrets
            )
            calls: list[str] = []

            async def read(tool_name: str, value: object) -> dict[str, object]:
                nonlocal stage
                stage = tool_name
                calls.append(tool_name)
                completed = await dispatcher.dispatch(
                    binding=catalog.binding(ToolId(tool_name)),
                    validated_input=value,
                    plan=plan,
                    budgets=budgets,
                    cancellation=CancellationToken(),
                    lineage=InitialReadDispatchLineage(
                        run_id, f"qualification-read:{run_id}:{len(calls)}"
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
                value_result = result.get("value")
                if not isinstance(value_result, dict):
                    raise QualificationFailure(tool_name, "invalid_success")
                return cast("dict[str, object]", value_result)

            async with engine.connect() as connection:
                actions_before = cast(
                    int,
                    await connection.scalar(select(func.count()).select_from(action)),
                )

            gmail_search = await read(
                "gmail.search",
                GmailSearchInput(query=gmail_query, max_results=5),
            )
            threads = cast("list[dict[str, object]]", gmail_search["threads"])
            if not threads or not isinstance(threads[0].get("thread_id"), str):
                raise QualificationFailure("gmail.search", "no_thread")
            gmail_thread = await read(
                "gmail.read_thread",
                GmailReadThreadInput(
                    thread_id=cast(str, threads[0]["thread_id"]),
                    max_messages=10,
                ),
            )

            calendar_discovery = await read(
                "calendar.list_calendars",
                CalendarListCalendarsInput(),
            )
            calendars = cast("list[dict[str, object]]", calendar_discovery["calendars"])
            if not calendars or not all(
                isinstance(item.get("calendar_id"), str) for item in calendars
            ):
                raise QualificationFailure("calendar.list_calendars", "no_calendar")
            if calendar_discovery.get("truncated") is not False:
                raise QualificationFailure("calendar.list_calendars", "truncated")

            calendar_list = await read(
                "calendar.list_events",
                CalendarListEventsInput(
                    time_min=now - timedelta(days=30),
                    time_max=now + timedelta(days=365),
                    time_zone=settings.owner_timezone,
                ),
            )
            events = cast("list[dict[str, object]]", calendar_list["events"])
            calendar_coverage = cast("dict[str, object]", calendar_list.get("coverage"))
            coverage_reasons = cast("list[str]", calendar_coverage.get("reasons"))
            if set(coverage_reasons) & {
                "calendar_failure",
                "deadline",
                "event_page_limit",
            }:
                raise QualificationFailure("calendar.list_events", "incomplete_scan")
            if calendar_coverage.get("calendars_completed") != len(calendars):
                raise QualificationFailure("calendar.list_events", "incomplete_scan")
            unspecified_end_events = sum(
                item.get("type") == "event"
                and isinstance(item.get("writable"), dict)
                and isinstance(
                    cast("dict[str, object]", item["writable"]).get("end"), dict
                )
                and cast(
                    "dict[str, object]",
                    cast("dict[str, object]", item["writable"])["end"],
                ).get("type")
                == "unspecified"
                for item in events
            )
            if unspecified_end_events < 3:
                raise QualificationFailure(
                    "calendar.list_events",
                    "insufficient_unspecified_end_coverage",
                )
            event = next(
                (
                    item
                    for item in events
                    if item.get("type") == "event"
                    and isinstance(item.get("event_id"), str)
                ),
                None,
            )
            if event is None:
                raise QualificationFailure("calendar.list_events", "no_normal_event")
            event_calendar_id = event.get("calendar_id")
            if not isinstance(event_calendar_id, str):
                raise QualificationFailure(
                    "calendar.list_events", "invalid_calendar_id"
                )
            await read(
                "calendar.get_event",
                CalendarGetEventInput(
                    calendar_id=event_calendar_id,
                    event_id=cast(str, event["event_id"]),
                ),
            )

            maps_search = await read(
                "maps.search_places",
                MapsSearchPlacesInput(
                    query=maps_query,
                    location_bias=None,
                    max_results=5,
                ),
            )
            places = cast("list[dict[str, object]]", maps_search["places"])
            if not places or not isinstance(places[0].get("place_id"), str):
                raise QualificationFailure("maps.search_places", "no_place")
            place_id = cast(str, places[0]["place_id"])
            await read("maps.get_place", MapsGetPlaceInput(place_id=place_id))
            directions = await read(
                "maps.directions",
                MapsDirectionsInput(
                    origin=AddressLocation(address=maps_origin),
                    destination=PlaceLocation(place_id=place_id),
                    travel_mode="driving",
                    departure_at=None,
                ),
            )

            web_search = await read(
                "web.search",
                WebSearchInput(query=web_query, freshness_days=None),
            )
            results = cast("list[dict[str, object]]", web_search["results"])
            if not results or not isinstance(results[0].get("url"), str):
                raise QualificationFailure("web.search", "no_result")
            web_read = await read(
                "web.read",
                WebReadInput(url=cast(str, results[0]["url"])),
            )

            async with engine.connect() as connection:
                actions_after = cast(
                    int,
                    await connection.scalar(select(func.count()).select_from(action)),
                )
            if actions_after != actions_before:
                raise QualificationFailure("actions", "automatic_read_created_action")
            if tuple(ToolId(item) for item in calls) != EXTERNAL_READ_IDS:
                raise QualificationFailure("dispatch", "unexpected_tool_sequence")
            if dispatcher.recorder.terminal_count != 10:
                raise QualificationFailure("dispatch", "incomplete_terminal_record")
            if dispatcher.recorder.uncertain_count != 0:
                raise QualificationFailure("dispatch", "uncertain_read")

            messages = cast("list[object]", gmail_thread["messages"])
            routes = cast("list[object]", directions["routes"])
            evidence = cast("dict[str, object]", web_read["evidence"])
            locator_raw = evidence.get("locator")
            if not isinstance(locator_raw, str):
                raise QualificationFailure("web.read", "invalid_evidence_locator")
            locator_value: object = json.loads(locator_raw)
            if not isinstance(locator_value, dict):
                raise QualificationFailure("web.read", "invalid_evidence_locator")
            locator = cast("dict[str, object]", locator_value)
            if locator.get("extraction") not in {
                "plain-text-v2",
                "html-visible-text-v2",
                "json-canonical-v1",
            }:
                raise QualificationFailure("web.read", "invalid_extraction_revision")
            return {
                "implementation": {
                    **_implementation(),
                    "main_definition_fingerprint": definitions.main.fingerprint,
                    "main_plan_revision": plan.plan_revision,
                    "session_compatibility_revision": (
                        definitions.main.session_compatibility_revision
                    ),
                },
                "reads": {
                    "calendar": {
                        "calendars": len(calendars),
                        "coverage": calendar_coverage,
                        "events": len(events),
                        "get_event": True,
                        "unspecified_end_events": unspecified_end_events,
                    },
                    "gmail": {"messages": len(messages), "threads": len(threads)},
                    "maps": {"places": len(places), "routes": len(routes)},
                    "web": {
                        "extraction": locator["extraction"],
                        "results": len(results),
                        "text_bytes": len(cast(str, web_read["text"]).encode()),
                    },
                },
                "revisions": dict(EXPECTED_GIT_PINS),
                "status": "passed",
                "tool_dispatch": {
                    "calls": len(calls),
                    "serial": True,
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
            for client in clients:
                await client.aclose()


def main() -> int:
    stage = "setup"
    try:
        if os.environ.get("JARVIS_LIVE_READS") != "1":
            raise ValueError("live reads require JARVIS_LIVE_READS=1")
        settings = Settings.from_env()
        result = asyncio.run(_run(settings))
    except QualificationFailure as exc:
        result = {
            "failure": {"reason": exc.reason, "stage": exc.stage},
            "implementation": _implementation(),
            "revisions": EXPECTED_GIT_PINS,
            "status": "failed",
        }
    except BaseException as exc:
        result = {
            "failure": {"reason": type(exc).__name__, "stage": stage},
            "implementation": _implementation(),
            "revisions": EXPECTED_GIT_PINS,
            "status": "failed",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
