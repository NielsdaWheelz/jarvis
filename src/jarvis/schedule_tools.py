"""The single local Slice 5 scheduling tool contract."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol, cast
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
    ToolSpec,
)
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ScheduleCreateRequest(_StrictModel):
    type: Literal["create"] = "create"
    execute_after: AwareDatetime
    instruction: Annotated[str, Field(min_length=1, max_length=4_000)]

    @field_validator("instruction")
    @classmethod
    def bounded_instruction(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 16_000:
            raise ValueError("schedule instruction exceeds its UTF-8 byte bound")
        return value


class ScheduleCancelRequest(_StrictModel):
    type: Literal["cancel"] = "cancel"
    target_action_id: UUID


type ScheduleRequest = Annotated[
    ScheduleCreateRequest | ScheduleCancelRequest,
    Field(discriminator="type"),
]


class ScheduleWakeInput(_StrictModel):
    request: ScheduleRequest


class ScheduleCreated(_StrictModel):
    type: Literal["created"] = "created"
    action_id: UUID
    execute_after: AwareDatetime
    arguments_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    recorded_at: AwareDatetime


class ScheduleCancelled(_StrictModel):
    type: Literal["cancelled"] = "cancelled"
    target_action_id: UUID
    recorded_at: AwareDatetime


class ScheduleWakeSuccess(_StrictModel):
    receipt: Annotated[
        ScheduleCreated | ScheduleCancelled,
        Field(discriminator="type"),
    ]


class ExecuteAfterNotFuture(_StrictModel):
    type: Literal["ExecuteAfterNotFuture"] = "ExecuteAfterNotFuture"


class TargetNotFound(_StrictModel):
    type: Literal["TargetNotFound"] = "TargetNotFound"


class TargetNotQueued(_StrictModel):
    type: Literal["TargetNotQueued"] = "TargetNotQueued"


class Conflict(_StrictModel):
    type: Literal["Conflict"] = "Conflict"


type ScheduleWakeError = (
    ExecuteAfterNotFuture | TargetNotFound | TargetNotQueued | Conflict
)


class ScheduleTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exists: bool
    is_schedule_create: bool
    status: str | None


class ScheduleTargetReader(Protocol):
    async def schedule_target(self, action_id: UUID) -> ScheduleTarget: ...

    async def schedule_arguments_digest(self, action_id: UUID) -> str: ...


SCHEDULE_WAKE_SPEC = ToolSpec[
    ScheduleWakeInput, ScheduleWakeSuccess, ScheduleWakeError
](
    id=ToolId("schedule.wake"),
    summary="Create one exact due reminder or cancel one queued reminder.",
    documentation=PromptDocument(
        "Create only an owner-requested reminder at an exact offset-aware instant, "
        "or cancel a named queued schedule action. This does not create a recurring "
        "job or monitor an external source."
    ),
    input_type=ScheduleWakeInput,
    success_type=ScheduleWakeSuccess,
    error_type=cast(type[ScheduleWakeError], ScheduleWakeError),
    effect=ToolEffect.Write,
    limits=ToolLimits(16_384, 4_096, 2, 5.0),
)


def schedule_family(
    targets: ScheduleTargetReader,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ToolFamily:
    async def execute(
        value: ScheduleWakeInput,
        context: ExecutionContext,
    ) -> HandlerSuccess[ScheduleWakeSuccess]:
        if context.effect_id is None or context.position != context.effect_id:
            raise RuntimeError("schedule position and effect must be the action ID")
        action_id = UUID(str(context.effect_id))
        recorded_at = clock()
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise RuntimeError("schedule clock must be timezone-aware")
        request = value.request
        if isinstance(request, ScheduleCreateRequest):
            if request.execute_after <= recorded_at:
                raise DeclaredToolFailure(
                    ExecuteAfterNotFuture(),
                    actual_attempts=0,
                )
            result = ScheduleWakeSuccess(
                receipt=ScheduleCreated(
                    action_id=action_id,
                    execute_after=request.execute_after,
                    arguments_digest=await targets.schedule_arguments_digest(action_id),
                    recorded_at=recorded_at,
                )
            )
        else:
            target = await targets.schedule_target(request.target_action_id)
            if not target.exists:
                raise DeclaredToolFailure(TargetNotFound(), actual_attempts=0)
            if not target.is_schedule_create:
                raise DeclaredToolFailure(Conflict(), actual_attempts=0)
            if target.status != "queued":
                raise DeclaredToolFailure(TargetNotQueued(), actual_attempts=0)
            result = ScheduleWakeSuccess(
                receipt=ScheduleCancelled(
                    target_action_id=request.target_action_id,
                    recorded_at=recorded_at,
                )
            )
        return HandlerSuccess(result, actual_attempts=0)

    binding = ToolBinding(
        spec=SCHEDULE_WAKE_SPEC,
        execute=Available(execute),
        replay_policy=ReplayPolicy.ReDispatchable,
        implementation_revision="jarvis-schedule-wake-v1",
        policy_epoch=PolicyEpoch("jarvis-schedule-v1"),
        policy_inputs={
            "action_max_attempts": 2,
            "authority": "automatic-write-gated",
            "clock": "host-utc",
            "durability": "action-creation-receipt-v1",
            "arguments_digest": "frozen-action-request",
        },
    )
    return ToolFamily("schedule", (SCHEDULE_WAKE_SPEC,), (binding,))


__all__ = [
    "SCHEDULE_WAKE_SPEC",
    "Conflict",
    "ExecuteAfterNotFuture",
    "ScheduleCancelRequest",
    "ScheduleCancelled",
    "ScheduleCreateRequest",
    "ScheduleCreated",
    "ScheduleTarget",
    "ScheduleTargetReader",
    "ScheduleWakeInput",
    "TargetNotFound",
    "TargetNotQueued",
    "schedule_family",
]
