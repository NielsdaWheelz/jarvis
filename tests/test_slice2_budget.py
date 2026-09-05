from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from llm_agent_kernel import (
    CancellationToken,
    Checkpoint,
    ClaimId,
    DispatchLineage,
    InputId,
    require_host_plan,
)
from llm_tools import (
    SafeWebReader,
    ToolId,
    WebReadInput,
    WebSearchError,
    WebSearchErrorCode,
    WebSearchInput,
    WebSearchRequest,
    WebSearchResponse,
    bind_brave_web_search,
    bind_web_read,
    web_family,
)

from jarvis.admission import ExactToolBudgetFactory, InProcessBudgetState
from jarvis.definitions import build_slice2_definitions
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_tools import (
    AddressLocation,
    CalendarGetEventInput,
    CalendarListEventsInput,
    ConnectorFailure,
    GmailReadThreadInput,
    GmailSearchInput,
    MapsDirectionsInput,
    MapsGetPlaceInput,
    MapsSearchPlacesInput,
    compose_read_catalog,
)

NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)


class _FailingReads:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def _fail(self, name: str) -> Any:
        self.calls.append(name)
        raise ConnectorFailure("provider_unavailable", attempts=1)

    async def gmail_search(self, value: object) -> Any:
        del value
        return await self._fail("gmail.search")

    async def gmail_read_thread(self, value: object) -> Any:
        del value
        return await self._fail("gmail.read_thread")

    async def calendar_list_events(self, value: object) -> Any:
        del value
        return await self._fail("calendar.list_events")

    async def calendar_get_event(self, value: object) -> Any:
        del value
        return await self._fail("calendar.get_event")

    async def search_places(self, value: object) -> Any:
        del value
        return await self._fail("maps.search_places")

    async def get_place(self, value: object) -> Any:
        del value
        return await self._fail("maps.get_place")

    async def directions(self, value: object) -> Any:
        del value
        return await self._fail("maps.directions")


class _FailingSearch:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def search(
        self,
        request: WebSearchRequest,
        *,
        attempt_started: Callable[[], None] | None = None,
    ) -> WebSearchResponse:
        del request
        self._calls.append("web.search")
        assert attempt_started is not None
        attempt_started()
        raise WebSearchError(
            WebSearchErrorCode.PROVIDER_DOWN,
            "synthetic",
            provider="brave",
            attempts=1,
        )


class _FailingResolver:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        del hostname, port
        self._calls.append("web.read")
        raise OSError("synthetic")


async def test_exact_plan_budget_runs_all_nine_reads_serially() -> None:
    reads = _FailingReads()
    web_calls: list[str] = []
    catalog = compose_read_catalog(
        google=reads,
        maps=reads,
        web=web_family(
            search=bind_brave_web_search(
                _FailingSearch(web_calls),
                operation_deadline_seconds=12.0,
            ),
            read=bind_web_read(SafeWebReader(resolver=_FailingResolver(web_calls))),
        ),
    )
    definitions = build_slice2_definitions(
        catalog=catalog,
        profile_key="synthetic",
        model="gpt-5.6-terra",
        owner_timezone="UTC",
    )
    plan = definitions.plans["main"]
    require_host_plan(plan, definitions.main.maximum_profile)
    budgets = ExactToolBudgetFactory().create(plan)
    assert isinstance(budgets, InProcessBudgetState)
    assert budgets.limits == plan.profile.run_limits
    dispatcher = ReadToolDispatcher(host_secrets=())
    calls = (
        ("gmail.search", GmailSearchInput(query="x", max_results=1)),
        ("gmail.read_thread", GmailReadThreadInput(thread_id="t", max_messages=1)),
        (
            "calendar.list_events",
            CalendarListEventsInput(
                calendar_id="primary",
                time_min=NOW,
                time_max=NOW + timedelta(hours=1),
                time_zone="UTC",
                max_results=1,
            ),
        ),
        (
            "calendar.get_event",
            CalendarGetEventInput(calendar_id="primary", event_id="e"),
        ),
        (
            "maps.search_places",
            MapsSearchPlacesInput(query="x", location_bias=None, max_results=1),
        ),
        ("maps.get_place", MapsGetPlaceInput(place_id="p")),
        (
            "maps.directions",
            MapsDirectionsInput(
                origin=AddressLocation(address="A"),
                destination=AddressLocation(address="B"),
                travel_mode="walking",
                departure_at=None,
            ),
        ),
        ("web.search", WebSearchInput(query="synthetic", freshness_days=None)),
        ("web.read", WebReadInput(url="https://public.example/")),
    )
    results: list[str] = []
    for ordinal, (name, value) in enumerate(calls, 1):
        completed = await dispatcher.dispatch(
            binding=catalog.binding(ToolId(name)),
            validated_input=value,
            plan=plan,
            budgets=budgets,
            cancellation=CancellationToken(),
            lineage=DispatchLineage(
                ClaimId("claim"),
                Checkpoint("checkpoint"),
                (InputId("input"),),
                ordinal,
            ),
        )
        results.append(completed.result["type"])

    assert results == ["Failure"] * 9
    assert reads.calls == [name for name, _ in calls[:7]]
    assert web_calls == ["web.search", "web.read"]
    assert dispatcher.recorder.terminal_count == 9
    assert dispatcher.recorder.uncertain_count == 0
