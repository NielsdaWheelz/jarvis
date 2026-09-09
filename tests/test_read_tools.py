from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest
from llm_agent_kernel import (
    CancellationToken,
    Checkpoint,
    ClaimId,
    DispatchLineage,
    InputId,
)
from llm_tools import (
    Available,
    CapabilityProfile,
    DeclaredToolFailure,
    ExecutionContext,
    HostTable,
    ProfileId,
    ReplayPolicy,
    RunLimits,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolGrant,
    ToolId,
    ToolLimits,
    ToolPlan,
    web_family,
)
from llm_tools.schema import (
    SchemaDecodeError,
    compile_schema,
    strict_decode,
    strict_encode,
)
from llm_tools.testing import InMemoryBudgetState
from provider_fixture import decision_key
from pydantic import BaseModel, ValidationError

from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder
from jarvis.read_tools import (
    AUTOMATIC_READ_TOOL_IDS,
    AllDayEventTime,
    CalendarCoverage,
    CalendarGetEventSuccess,
    CalendarListCalendarsInput,
    CalendarListCancelledEvent,
    CalendarListEventsInput,
    CalendarListEventsSuccess,
    CalendarListNormalEvent,
    CalendarNormalEvent,
    EventTime,
    GmailSearchInput,
    GmailSearchSuccess,
    GmailThreadHit,
    MapsSearchPlacesInput,
    MapsSearchPlacesSuccess,
    ObservedEventEnd,
    Place,
    ReadResponse,
    TimedEventTime,
    UnspecifiedEventEnd,
    compose_read_catalog,
)


class _Google:
    async def gmail_search(self, value: object) -> object:
        raise AssertionError(value)

    async def gmail_read_thread(self, value: object) -> object:
        raise AssertionError(value)

    async def calendar_list_calendars(self, value: object) -> object:
        raise AssertionError(value)

    async def calendar_list_events(self, value: object) -> object:
        raise AssertionError(value)

    async def calendar_get_event(self, value: object) -> object:
        raise AssertionError(value)


class _Maps:
    async def search_places(
        self, value: MapsSearchPlacesInput
    ) -> ReadResponse[MapsSearchPlacesSuccess]:
        del value
        place = Place(
            place_id="p" * 1_024,
            display_name="d" * 512,
            formatted_address="a" * 1_024,
            location=None,
            types=tuple("t" * 128 for _ in range(32)),
            maps_uri="https://maps.example/" + "u" * 4_075,
        )
        return ReadResponse(
            MapsSearchPlacesSuccess(
                places=tuple(place for _ in range(10)),
                observed_at=datetime(2026, 9, 4, tzinfo=UTC),
            ),
            1,
        )

    async def get_place(self, value: object) -> object:
        raise AssertionError(value)

    async def directions(self, value: object) -> object:
        raise AssertionError(value)


def _catalog() -> ToolCatalog:
    return compose_read_catalog(
        google=cast("Any", _Google()),
        maps=cast("Any", _Maps()),
        web=web_family(),
    )


def _assert_closed(schema: object) -> None:
    if isinstance(schema, dict):
        value_map = cast("dict[object, object]", schema)
        if value_map.get("type") == "object":
            assert value_map.get("additionalProperties") is False
        for value in value_map.values():
            _assert_closed(value)
    elif isinstance(schema, list):
        for value in cast("list[object]", schema):
            _assert_closed(value)


def test_exact_slice2_catalog_and_binding_manifest() -> None:
    catalog = _catalog()

    assert frozenset(catalog.tool_ids) == AUTOMATIC_READ_TOOL_IDS
    for tool_id in catalog.tool_ids:
        spec = catalog.spec(tool_id)
        binding = catalog.binding(tool_id)
        assert spec.effect is ToolEffect.Read
        _assert_closed(spec.input_schema.semantic)
        _assert_closed(spec.success_schema.semantic)
        if spec.declared_error_schema is not None:
            _assert_closed(spec.declared_error_schema.semantic)
        if not str(tool_id).startswith("web."):
            if tool_id == ToolId("calendar.list_events"):
                expected_revision = "jarvis-calendar-list_events-v6"
            elif tool_id == ToolId("calendar.list_calendars"):
                expected_revision = "jarvis-calendar-list_calendars-v1"
            elif str(tool_id).startswith("calendar."):
                expected_revision = f"jarvis-{str(tool_id).replace('.', '-')}-v2"
            else:
                expected_revision = f"jarvis-{str(tool_id).replace('.', '-')}-v1"
            assert binding.implementation_revision == expected_revision
            assert binding.replay_policy is (
                ReplayPolicy.ReDispatchable
                if str(tool_id).startswith(("gmail.", "calendar."))
                else ReplayPolicy.BilledOnce
            )
        else:
            assert binding.implementation_revision.startswith("llm-tools-web-")

    place_bounds = {
        "display_name_bytes": 512,
        "formatted_address_bytes": 1_024,
        "maps_uri_bytes": 4_096,
        "place_id_bytes": 1_024,
        "type_bytes": 128,
        "types": 32,
    }
    assert catalog.binding(ToolId("maps.search_places")).policy_inputs == {
        "authority": "automatic-read",
        "endpoint": "https://places.googleapis.com/v1/places:searchText",
        "field_mask": (
            "places.id,places.displayName,places.formattedAddress,places.location,"
            "places.types,places.googleMapsLinks.placeUri"
        ),
        "maps_uri_sources": (
            "googleMapsLinks.placeUri",
            "googleMapsUri",
        ),
        "max_results": 10,
        "place_bounds": place_bounds,
    }
    assert catalog.binding(ToolId("maps.get_place")).policy_inputs == {
        "authority": "automatic-read",
        "endpoint": "https://places.googleapis.com/v1/places/{place_id}",
        "field_mask": (
            "id,displayName,formattedAddress,location,types,googleMapsLinks.placeUri"
        ),
        "maps_uri_sources": (
            "googleMapsLinks.placeUri",
            "googleMapsUri",
        ),
        "place_bounds": place_bounds,
    }
    directions = catalog.binding(ToolId("maps.directions"))
    assert directions.implementation_revision == "jarvis-maps-directions-v1"
    assert str(directions.policy_epoch) == "jarvis-read-v1"
    assert directions.policy_inputs == {
        "authority": "automatic-read",
        "compute_alternative_routes": False,
        "duration_rounding": "ceiling-seconds",
        "endpoint": ("https://routes.googleapis.com/directions/v2:computeRoutes"),
        "field_mask": (
            "routes.distanceMeters,routes.duration,routes.description,routes.warnings"
        ),
        "max_description_bytes": 1_000,
        "max_routes": 1,
        "max_warning_bytes": 1_000,
        "max_warnings": 10,
        "polyline": False,
        "route_warnings": "required-user-visible-exact",
        "transit_departure_days": {"future": 100, "past": 7},
    }

    calendar_end_policy = (
        "missing-or-false-parses-end;"
        "true-becomes-unspecified-and-discards-compatibility-end"
    )
    assert (
        catalog.binding(ToolId("calendar.list_events")).policy_inputs["observed_end"]
        == calendar_end_policy
    )
    assert (
        catalog.binding(ToolId("calendar.list_events")).policy_inputs[
            "calendar_selection"
        ]
        == "calendar-list-reader-or-better-v1"
    )
    assert catalog.binding(ToolId("calendar.list_calendars")).policy_inputs == {
        "authority": "automatic-read",
        "calendar_selection": "calendar-list-reader-or-better-v1",
        "endpoint": "https://www.googleapis.com/calendar/v3/users/me/calendarList",
        "include_deleted": False,
        "include_hidden": True,
        "max_calendars": 50,
        "stable_id_max_bytes": 1_024,
    }
    assert (
        catalog.binding(ToolId("calendar.list_events")).policy_inputs[
            "calendar_event_concurrency"
        ]
        == 10
    )
    assert (
        catalog.binding(ToolId("calendar.list_events")).policy_inputs[
            "partial_failures"
        ]
        == "explicit-per-calendar-v1"
    )
    calendar_list_events_policy = catalog.binding(
        ToolId("calendar.list_events")
    ).policy_inputs
    assert calendar_list_events_policy["coverage"] == "calendar-coverage-v1"
    assert calendar_list_events_policy["event_page_size"] == 250
    assert calendar_list_events_policy["event_order"] == (
        "chronological-cancelled-last-calendar-id-event-id-v1"
    )
    assert calendar_list_events_policy["max_event_page_requests"] == 100
    assert calendar_list_events_policy["max_events"] == 1_500
    assert calendar_list_events_policy["max_success_bytes"] == 524_288
    assert calendar_list_events_policy["operation_deadline_seconds"] == 55.0
    assert calendar_list_events_policy["output_clipping"] == (
        "canonical-json-largest-chronological-whole-event-prefix-v1"
    )
    assert calendar_list_events_policy["pagination"] == "calendar-id-rounds-v1"
    assert calendar_list_events_policy["event_projection"] == "compact-overview-v1"
    assert calendar_list_events_policy["full_details_tool"] == "calendar.get_event"
    assert calendar_list_events_policy["compact_event_bounds"] == {
        "location_bytes": 4_096,
        "stable_id_max_bytes": 1_024,
        "summary_bytes": 1_024,
    }
    assert "normal_event_bounds" not in calendar_list_events_policy
    assert (
        catalog.binding(ToolId("calendar.list_events")).implementation_revision
        == "jarvis-calendar-list_events-v6"
    )
    assert (
        catalog.binding(ToolId("calendar.get_event")).policy_inputs["observed_end"]
        == calendar_end_policy
    )
    assert catalog.spec(ToolId("calendar.list_events")).limits == ToolLimits(
        8_192, 524_288, 202, 60.0
    )
    assert catalog.spec(ToolId("calendar.list_events")).tool_contract_revision == (
        "908bb99fd8da9ea022051eddf48fb0e061712738620e6ef8842bc015dd7b7086"
    )
    assert catalog.spec(ToolId("calendar.list_calendars")).tool_contract_revision == (
        "08cc652b133c80a30ee2e9c3be2c64d2321f00533805a4a56213ce95fd911817"
    )
    assert catalog.spec(ToolId("calendar.get_event")).tool_contract_revision == (
        "15dfc456377fe4eaff7de42292c9cddc5a97b1190baa7e7196cb4f1e287f0087"
    )


def test_calendar_list_contract_has_no_provider_calendar_id() -> None:
    schema = compile_schema(CalendarListEventsInput).semantic
    assert set(schema["properties"]) == {
        "time_max",
        "time_min",
        "time_zone",
    }
    assert set(schema["required"]) == set(schema["properties"])
    discovery = compile_schema(CalendarListCalendarsInput).semantic
    assert discovery == {
        "additionalProperties": False,
        "properties": {},
        "required": [],
        "type": "object",
    }
    with pytest.raises(ValidationError):
        CalendarListEventsInput.model_validate(
            {
                "time_min": "2026-09-08T00:00:00Z",
                "time_max": "2026-09-09T00:00:00Z",
                "time_zone": "UTC",
                "max_results": 50,
            }
        )
    success_schema = compile_schema(CalendarListEventsSuccess).semantic
    assert set(success_schema["properties"]) == {
        "calendars",
        "coverage",
        "events",
        "failures",
        "observed_at",
    }
    with pytest.raises(ValidationError):
        CalendarListEventsSuccess.model_validate(
            {
                "calendars": [],
                "events": [],
                "failures": [],
                "coverage": {
                    "complete": True,
                    "reasons": [],
                    "calendars_discovered": 0,
                    "calendars_completed": 0,
                    "matched_events": 0,
                },
                "observed_at": "2026-09-08T00:00:00Z",
                "truncated": False,
            }
        )


def test_calendar_list_is_compact_and_get_event_retains_full_snapshot() -> None:
    compact = CalendarListEventsSuccess.model_validate(
        {
            "calendars": [
                {
                    "calendar_id": "calendar",
                    "display_name": None,
                    "time_zone": None,
                    "access_role": "reader",
                    "primary": False,
                    "hidden": False,
                    "selected": False,
                }
            ],
            "events": [
                {
                    "type": "event",
                    "calendar_id": "calendar",
                    "event_id": "event",
                    "status": "confirmed",
                    "summary": "Synthetic",
                    "start": {"type": "all_day", "date": "2026-09-08"},
                    "end": {"type": "all_day", "date": "2026-09-09"},
                    "location": None,
                },
                {
                    "type": "cancelled",
                    "calendar_id": "calendar",
                    "event_id": "cancelled",
                },
            ],
            "failures": [],
            "coverage": {
                "complete": True,
                "reasons": [],
                "calendars_discovered": 1,
                "calendars_completed": 1,
                "matched_events": 2,
            },
            "observed_at": "2026-09-08T00:00:00Z",
        }
    )
    assert isinstance(compact.events[0], CalendarListNormalEvent)
    assert isinstance(compact.events[1], CalendarListCancelledEvent)
    with pytest.raises(ValidationError):
        CalendarListNormalEvent.model_validate(
            {
                **compact.events[0].model_dump(mode="json"),
                "description": "not part of the compact contract",
            }
        )
    overbound = compact.model_dump(mode="json")
    overbound["events"] = [overbound["events"][0]] * 1_501
    cast("dict[str, object]", overbound["coverage"])["matched_events"] = 1_501
    with pytest.raises(ValidationError):
        CalendarListEventsSuccess.model_validate(overbound)

    full_schema = compile_schema(CalendarGetEventSuccess).semantic
    full_text = str(full_schema)
    assert "description" in full_text
    assert "attendees" in full_text
    assert "reminders" in full_text


def test_calendar_coverage_contract_is_closed_and_cross_field_strict() -> None:
    schema = compile_schema(CalendarCoverage).semantic

    assert set(schema["properties"]) == {
        "calendars_completed",
        "calendars_discovered",
        "complete",
        "matched_events",
        "reasons",
    }
    _assert_closed(schema)
    assert (
        CalendarCoverage(
            complete=True,
            reasons=(),
            calendars_discovered=35,
            calendars_completed=35,
            matched_events=71,
        ).matched_events
        == 71
    )
    invalid = (
        {
            "complete": True,
            "reasons": ("calendar_limit",),
            "calendars_discovered": 1,
            "calendars_completed": 1,
            "matched_events": 0,
        },
        {
            "complete": False,
            "reasons": (),
            "calendars_discovered": 1,
            "calendars_completed": 1,
            "matched_events": 0,
        },
        {
            "complete": False,
            "reasons": ("event_limit", "calendar_limit"),
            "calendars_discovered": 1,
            "calendars_completed": 1,
            "matched_events": 201,
        },
        {
            "complete": False,
            "reasons": ("deadline",),
            "calendars_discovered": 1,
            "calendars_completed": 2,
            "matched_events": None,
        },
        {
            "complete": False,
            "reasons": ("deadline",),
            "calendars_discovered": 1,
            "calendars_completed": 0,
            "matched_events": 0,
        },
    )
    for value in invalid:
        with pytest.raises(ValidationError):
            CalendarCoverage.model_validate(value)


def test_observed_end_three_variant_union_strictly_round_trips() -> None:
    schema = compile_schema(ObservedEventEnd)
    values = (
        TimedEventTime(
            date_time=datetime(2026, 9, 4, 12, tzinfo=UTC),
            time_zone="UTC",
        ),
        AllDayEventTime(date=date(2026, 9, 4)),
        UnspecifiedEventEnd(),
    )

    assert {
        branch["properties"]["type"]["const"]
        for branch in cast("list[dict[str, Any]]", schema.semantic["oneOf"])
    } == {"timed", "all_day", "unspecified"}
    for value in values:
        encoded = strict_encode(ObservedEventEnd, schema, value)
        assert strict_decode(ObservedEventEnd, schema, encoded) == value
    assert strict_encode(ObservedEventEnd, schema, values[-1]) == {
        "type": "unspecified"
    }

    write_schema = compile_schema(EventTime)
    assert {
        branch["properties"]["type"]["const"]
        for branch in cast("list[dict[str, Any]]", write_schema.semantic["oneOf"])
    } == {"timed", "all_day"}
    with pytest.raises(SchemaDecodeError):
        strict_decode(EventTime, write_schema, {"type": "unspecified"})
    with pytest.raises(SchemaDecodeError):
        strict_decode(
            ObservedEventEnd,
            schema,
            {"type": "unspecified", "date": "2026-09-04"},
        )


def test_calendar_normal_event_requires_direct_observed_end() -> None:
    value: dict[str, object] = {
        "calendar_id": "primary",
        "event_id": "event",
        "etag": "etag",
        "status": "confirmed",
        "writable": {
            "summary": "Synthetic",
            "description": None,
            "location": None,
            "start": {"type": "all_day", "date": "2026-09-04"},
            "end": {"type": "all_day", "date": "2026-09-05"},
            "recurrence": [],
            "attendees": [],
            "use_default_reminders": False,
            "reminders": [],
        },
        "organizer": None,
        "updated_at": "2026-09-04T12:00:00Z",
    }

    assert isinstance(
        CalendarNormalEvent.model_validate(value).writable.end,
        AllDayEventTime,
    )
    writable = cast("dict[str, object]", value["writable"])
    with pytest.raises(ValidationError):
        CalendarNormalEvent.model_validate(
            {
                **value,
                "writable": {
                    key: item for key, item in writable.items() if key != "end"
                },
            }
        )
    with pytest.raises(ValidationError):
        CalendarNormalEvent.model_validate(
            {**value, "writable": {**writable, "end": None}}
        )
    assert isinstance(
        CalendarNormalEvent.model_validate(
            {
                **value,
                "writable": {**writable, "end": {"type": "unspecified"}},
            }
        ).writable.end,
        UnspecifiedEventEnd,
    )


def test_nested_inputs_reject_unknown_fields_and_preserve_query() -> None:
    value = GmailSearchInput(query='  subject:"two  spaces"  ', max_results=1)

    assert value.query == '  subject:"two  spaces"  '
    with pytest.raises(ValidationError):
        GmailSearchInput.model_validate(
            {"query": "x", "max_results": 1, "unknown": True}
        )
    with pytest.raises(ValidationError):
        MapsSearchPlacesInput.model_validate(
            {
                "query": "x",
                "max_results": 1,
                "location_bias": {
                    "latitude": 1,
                    "longitude": 2,
                    "radius_m": 3,
                    "unknown": True,
                },
            }
        )


def test_observation_times_require_utc_offset() -> None:
    with pytest.raises(ValidationError):
        GmailSearchSuccess(
            threads=(),
            truncated=False,
            observed_at=datetime(2026, 9, 4, 1, tzinfo=timezone(timedelta(hours=1))),
        )


def test_read_response_attempts_are_strictly_nonnegative() -> None:
    value = GmailSearchSuccess(
        threads=(GmailThreadHit(thread_id="t", snippet=""),),
        truncated=False,
        observed_at=datetime(2026, 9, 4, tzinfo=UTC),
    )

    with pytest.raises(ValueError):
        ReadResponse(value, -1)
    with pytest.raises(ValueError):
        ReadResponse(value, cast("Any", True))


@pytest.mark.asyncio
async def test_schema_valid_oversized_success_is_declared_provider_too_large() -> None:
    binding = cast(
        "ToolBinding[MapsSearchPlacesInput, MapsSearchPlacesSuccess, Any]",
        _catalog().binding(ToolId("maps.search_places")),
    )
    assert isinstance(binding.execute, Available)

    with pytest.raises(DeclaredToolFailure) as raised:
        await binding.execute.handler(
            MapsSearchPlacesInput(query="coffee", location_bias=None, max_results=10),
            cast(
                "ExecutionContext",
                SimpleNamespace(grant=SimpleNamespace(limits=binding.spec.limits)),
            ),
        )

    assert isinstance(raised.value.error, BaseModel)
    assert raised.value.error.model_dump() == {"type": "ProviderResponseTooLarge"}
    assert raised.value.actual_attempts == 1


@pytest.mark.asyncio
async def test_tightened_grant_oversize_completes_through_dispatcher() -> None:
    catalog = _catalog()
    tool_id = ToolId("maps.search_places")
    tool_limits = ToolLimits(8_192, 256, 1, 15.0)
    run_limits = RunLimits(1, 1, 8_192, 256, 1, 15.0)
    profile = CapabilityProfile(
        ProfileId("tight_output"),
        (ToolGrant(tool_id, tool_limits),),
        run_limits,
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    dispatcher = ReadToolDispatcher(recorder=RunReadRecorder(), host_secrets=())

    completed = await dispatcher.dispatch(
        binding=catalog.binding(tool_id),
        validated_input=MapsSearchPlacesInput(
            query="coffee",
            location_bias=None,
            max_results=10,
        ),
        plan=plan,
        budgets=InMemoryBudgetState(run_limits),
        cancellation=CancellationToken(),
        lineage=DispatchLineage(
            ClaimId("claim"),
            Checkpoint("checkpoint"),
            (InputId("input"),),
            1,
            definition_fingerprint="a" * 64,
            model_decision_id=decision_key(str(ClaimId("claim")), 1),
        ),
    )

    assert completed.result == {
        "type": "Failure",
        "error": {"type": "ProviderResponseTooLarge"},
    }
    assert dispatcher.recorder.terminal_count == 1
    assert dispatcher.recorder.uncertain_count == 0
