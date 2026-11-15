"""Closed todo contracts and bindings; WorkStore owns durable local mutations."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import UUID

from llm_tools import (
    Available,
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
    PolicyEpoch,
    PromptDocument,
    ReplayPolicy,
    ToolBinding,
    ToolEffect,
    ToolFamily,
    ToolId,
    ToolLimits,
    ToolResult,
    ToolSpec,
    canonical_json_bytes,
)
from llm_tools.schema import strict_decode
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
)

from jarvis.action_requests import CanonicalUuid
from jarvis.work_schedule import RepeatRule, Wake

WORK_STATES = ("doing_now", "blocked", "next_up", "backlog", "done", "cancelled")
ACTIVE_WORK_STATES = WORK_STATES[:4]
type WorkState = Literal[
    "doing_now", "blocked", "next_up", "backlog", "done", "cancelled"
]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def _title(value: str) -> str:
    if not value.strip() or "\0" in value or len(value.encode("utf-8")) > 240:
        raise ValueError("title must be nonblank UTF-8 text within 240 bytes")
    return value


def _content(value: str) -> str:
    if "\0" in value or len(value.encode("utf-8")) > 8_192:
        raise ValueError("content must be UTF-8 text within 8192 bytes")
    return value


def _calendar_date(value: object) -> object:
    if isinstance(value, datetime) or not (
        isinstance(value, date)
        or (
            isinstance(value, str)
            and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
        )
    ):
        raise ValueError("date must use YYYY-MM-DD")
    return date.fromisoformat(value) if isinstance(value, str) else value


def _host_utc(value: datetime) -> datetime:
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("host timestamps must use UTC")
    return value


Title = Annotated[str, AfterValidator(_title)]
Content = Annotated[str, AfterValidator(_content)]
CalendarDate = Annotated[date, BeforeValidator(_calendar_date)]
HostUtc = Annotated[AwareDatetime, AfterValidator(_host_utc)]


class WorkCreateInput(_Closed):
    title: Title
    state: WorkState
    content: Content
    due_date: CalendarDate | None
    wake: Wake | None


class TitleChange(_Closed):
    field: Literal["title"]
    value: Title


class StateChange(_Closed):
    field: Literal["state"]
    value: WorkState


class ContentChange(_Closed):
    field: Literal["content"]
    value: Content


class DueDateChange(_Closed):
    field: Literal["due_date"]
    value: CalendarDate | None


class WakeChange(_Closed):
    field: Literal["wake"]
    value: Wake | None


type WorkChange = Annotated[
    TitleChange | StateChange | ContentChange | DueDateChange | WakeChange,
    Field(discriminator="field"),
]


class WorkUpdateInput(_Closed):
    id: CanonicalUuid
    changes: Annotated[list[WorkChange], Field(min_length=1, max_length=5)]

    @field_validator("changes")
    @classmethod
    def unique_changes(cls, value: list[WorkChange]) -> list[WorkChange]:
        if len({item.field for item in value}) != len(value):
            raise ValueError("change fields must be unique")
        return value


class WorkDeleteInput(_Closed):
    id: CanonicalUuid


class WorkGetInput(_Closed):
    id: CanonicalUuid


class WorkListInput(_Closed):
    states: Annotated[list[WorkState], Field(min_length=1, max_length=6)]
    limit: Annotated[int, Field(strict=True, ge=1, le=100)]
    offset: Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]

    @field_validator("states")
    @classmethod
    def unique_states(cls, value: list[WorkState]) -> list[WorkState]:
        if len(set(value)) != len(value):
            raise ValueError("states must be unique")
        return value


class WorkSummary(_Closed):
    id: CanonicalUuid
    title: Title
    state: WorkState
    due_date: CalendarDate | None
    wake_id: CanonicalUuid | None
    wake_at: HostUtc | None
    repeat: RepeatRule | None
    updated_at: HostUtc


class WorkRecord(WorkSummary):
    content: Content
    created_at: HostUtc


class WorkMutationSuccess(_Closed):
    id: CanonicalUuid
    operation: Literal["created", "updated", "deleted"]
    wake_id: CanonicalUuid | None
    wake_at: HostUtc | None
    repeat: RepeatRule | None
    recorded_at: HostUtc


class WorkGetSuccess(_Closed):
    record: WorkRecord
    as_of: HostUtc


class WorkListSuccess(_Closed):
    items: Annotated[list[WorkSummary], Field(max_length=100)]
    total: Annotated[int, Field(strict=True, ge=0)]
    as_of: HostUtc


class NotFound(_Closed):
    type: Literal["NotFound"] = "NotFound"


class NextUpFull(_Closed):
    type: Literal["NextUpFull"] = "NextUpFull"


class InvalidSchedule(_Closed):
    type: Literal["InvalidSchedule"] = "InvalidSchedule"
    code: Literal["not_future_at_admission", "inactive", "invalid_zone", "out_of_range"]


type WorkError = NotFound | NextUpFull | InvalidSchedule

WORK_CREATE_SPEC = ToolSpec[WorkCreateInput, WorkMutationSuccess, WorkError](
    id=ToolId("work.create"),
    summary="record one outcome, optionally with a separate deadline and wake.",
    documentation=PromptDocument(
        "all fields are explicit: normally backlog, empty content, null due_date "
        "and null wake. due_date is a deadline, not a wake. reuse existing work "
        "for the same outcome. non-null wake.at must follow admission time; admitted "
        "queued schedules can fire late. confirm scheduling only from its committed "
        "receipt, with next local time/zone and material lateness. calendar rules "
        "freeze the named zone; intervals retain elapsed UTC phase."
    ),
    input_type=WorkCreateInput,
    success_type=WorkMutationSuccess,
    error_type=cast(type[WorkError], WorkError),
    effect=ToolEffect.Write,
    limits=ToolLimits(65_536, 4_096, 0, 5.0),
)
WORK_UPDATE_SPEC = ToolSpec[WorkUpdateInput, WorkMutationSuccess, WorkError](
    id=ToolId("work.update"),
    summary="change named todo fields; omitted fields retain their values.",
    documentation=PromptDocument(
        "supply 1-5 unique field changes. null clears due_date or the whole "
        "wake. non-null wake replaces the schedule even when equal; ordinary edits "
        "retain it. validate the final state independently of change order. "
        "NextUpFull changes nothing; do not silently demote another priority. "
        "bookkeeping remains possible while an external effect is uncertain; "
        "record the blocker honestly rather than retrying that effect."
    ),
    input_type=WorkUpdateInput,
    success_type=WorkMutationSuccess,
    error_type=cast(type[WorkError], WorkError),
    effect=ToolEffect.Write,
    limits=ToolLimits(65_536, 4_096, 0, 5.0),
)
WORK_DELETE_SPEC = ToolSpec[WorkDeleteInput, WorkMutationSuccess, WorkError](
    id=ToolId("work.delete"),
    summary="physically delete a todo and disable its future wakes.",
    documentation=PromptDocument(
        "deletion has no undo and stops future wakes, not ongoing work. "
        "already published snapshots and recorded actions survive deletion. "
        "never recreate a deleted todo from an old wake."
    ),
    input_type=WorkDeleteInput,
    success_type=WorkMutationSuccess,
    error_type=cast(type[WorkError], WorkError),
    effect=ToolEffect.Write,
    limits=ToolLimits(1_024, 4_096, 0, 5.0),
)
WORK_GET_SPEC = ToolSpec[WorkGetInput, WorkGetSuccess, WorkError](
    id=ToolId("work.get"),
    summary="observe one todo's current complete content and schedule.",
    documentation=PromptDocument(
        "this new invocation reads current state, including after older wake "
        "snapshots. NotFound is not successful completion."
    ),
    input_type=WorkGetInput,
    success_type=WorkGetSuccess,
    error_type=cast(type[WorkError], WorkError),
    effect=ToolEffect.Read,
    limits=ToolLimits(1_024, 65_536, 0, 5.0),
)
WORK_LIST_SPEC = ToolSpec[WorkListInput, WorkListSuccess, WorkError](
    id=ToolId("work.list"),
    summary="observe a fresh ordered page of todo summaries and its total.",
    documentation=PromptDocument(
        "normally select doing_now, blocked, next_up, backlog with limit=25 "
        "and offset=0. order is state, deadline nulls last, latest edit, id. "
        "summaries omit content/creation time; get retrieves complete content. "
        "total precedes paging. disclose omitted records and group useful states. "
        "later pages are fresh observations, not a frozen export."
    ),
    input_type=WorkListInput,
    success_type=WorkListSuccess,
    error_type=cast(type[WorkError], WorkError),
    effect=ToolEffect.Read,
    limits=ToolLimits(1_024, 262_144, 0, 5.0),
)
WORK_SPECS = (
    WORK_CREATE_SPEC,
    WORK_UPDATE_SPEC,
    WORK_DELETE_SPEC,
    WORK_GET_SPEC,
    WORK_LIST_SPEC,
)
WORK_MUTATION_IDS = frozenset(spec.id for spec in WORK_SPECS[:3])
WORK_READ_IDS = frozenset(spec.id for spec in WORK_SPECS[3:])


class WorkToolStore(Protocol):
    async def get(self, work_id: UUID) -> WorkGetSuccess: ...

    async def list(
        self, states: list[WorkState], limit: int, offset: int
    ) -> WorkListSuccess: ...

    async def mutate(
        self, action_id: UUID, tool_id: ToolId, arguments: BaseModel
    ) -> ToolResult: ...


def validate_work_result(tool_id: ToolId, result: ToolResult) -> None:
    """Validate the exact result before its atomic work/action commit."""
    spec = next(spec for spec in WORK_SPECS if spec.id == tool_id)
    if result["type"] == "Success" and set(result) == {"type", "value"}:
        strict_decode(spec.success_type, spec.success_schema, result["value"])
    elif result["type"] == "Failure" and set(result) == {"type", "error"}:
        if spec.declared_error_schema is None:
            raise RuntimeError("work errors require a declared schema")
        strict_decode(spec.error_type, spec.declared_error_schema, result["error"])
    else:
        raise RuntimeError("invalid work result envelope")
    if len(canonical_json_bytes(result)) > spec.limits.max_output_bytes:
        raise RuntimeError("work result exceeds its declared bound")


def work_family(store: WorkToolStore) -> ToolFamily:
    async def execute(
        value: WorkCreateInput
        | WorkUpdateInput
        | WorkDeleteInput
        | WorkGetInput
        | WorkListInput,
        context: ExecutionContext,
    ) -> HandlerSuccess[Any]:
        if isinstance(value, WorkGetInput):
            return HandlerSuccess(await store.get(UUID(value.id)), actual_attempts=0)
        if isinstance(value, WorkListInput):
            return HandlerSuccess(
                await store.list(value.states, value.limit, value.offset),
                actual_attempts=0,
            )
        if context.effect_id is None or context.position != context.effect_id:
            raise RuntimeError("work position and effect must equal the action id")
        if isinstance(value, WorkCreateInput):
            tool_id = WORK_CREATE_SPEC.id
        elif isinstance(value, WorkUpdateInput):
            tool_id = WORK_UPDATE_SPEC.id
        else:
            tool_id = WORK_DELETE_SPEC.id
        result = await store.mutate(UUID(str(context.effect_id)), tool_id, value)
        validate_work_result(tool_id, result)
        if result["type"] == "Failure":
            spec = next(spec for spec in WORK_SPECS if spec.id == tool_id)
            assert spec.declared_error_schema is not None
            raise DeclaredToolFailure(
                strict_decode(
                    spec.error_type, spec.declared_error_schema, result["error"]
                ),
                actual_attempts=0,
            )
        return HandlerSuccess(
            WorkMutationSuccess.model_validate(result["value"]), actual_attempts=0
        )

    bindings = tuple(
        ToolBinding(
            spec=spec,
            execute=Available(execute),
            replay_policy=ReplayPolicy.ReDispatchable,
            implementation_revision="jarvis-" + str(spec.id).replace(".", "-") + "-v1",
            policy_epoch=PolicyEpoch("jarvis-work-v1"),
            policy_inputs={
                "authority": "delivered-live-request",
                "external_attempts": 0,
                "durability": "atomic-work-and-action-receipt",
                "clock": "host-utc-admission-time-schedule-validation",
                "fresh_reads": "new-invocation-current-work",
            },
        )
        for spec in WORK_SPECS
    )
    return ToolFamily("work", WORK_SPECS, bindings)
