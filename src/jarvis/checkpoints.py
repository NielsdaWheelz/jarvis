from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from llm_agent_kernel import (
    AlreadyParked,
    AlreadyReleased,
    AppendInputs,
    Checkpoint,
    CheckpointStateDefect,
    ClaimAcquired,
    ClaimBusy,
    ClaimId,
    ClaimNoWork,
    ClaimResult,
    ConversationConclusion,
    DispatchLineage,
    HostConclusion,
    HostInput,
    InputClaim,
    InputId,
    NoNewInput,
    OwnerToken,
    Parked,
    ParkResult,
    PollResult,
    Preempt,
    Released,
    ReleaseResult,
    RunId,
    SettleIdle,
    SettleMoreInput,
    SettleResult,
    StoppedConclusion,
    SuspensionConclusion,
    ThreadId,
)
from llm_tools import (
    FrozenToolPlan,
    PromptAttribute,
    PromptAttributeName,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
)

from jarvis.messages import (
    CircuitOpen,
    ControlSettlement,
    ExhaustedMessage,
    MessageStore,
    NoMessages,
    SettlementTrace,
    StoredMessage,
    render_host_fallback,
)

_REASON_SEPARATOR = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class _ActiveClaim:
    claim: InputClaim
    owner_token: OwnerToken
    route: str
    message_ids: tuple[UUID, ...]
    checkpoint: Checkpoint
    host_inputs: tuple[StoredMessage, ...]
    admitted_inputs: tuple[HostInput, ...]
    current_as_of: datetime
    pending_control: Literal["stop", "pause"] | None = None
    offered_message_ids: tuple[UUID, ...] = ()
    offered_host_inputs: tuple[StoredMessage, ...] = ()
    offered_inputs: tuple[HostInput, ...] = ()
    offered_as_of: datetime | None = None
    offered_checkpoint: Checkpoint | None = None
    batch_as_of: dict[tuple[InputId, ...], datetime] | None = None


class PostgresInputCheckpoint:
    """Kernel checkpoint port backed by canonical PostgreSQL messages."""

    def __init__(
        self,
        *,
        store: MessageStore,
        thread_id: ThreadId,
        run_id: RunId,
        interactive_plan: FrozenToolPlan,
        scheduled_wake_plan: FrozenToolPlan,
        maximum_batch_size: int,
        maximum_attempts: int,
        maximum_response_characters: int = 2_000,
        on_settlement: Callable[[tuple[UUID, ...]], None] | None = None,
    ) -> None:
        if type(maximum_batch_size) is not int or maximum_batch_size <= 0:
            raise ValueError("maximum batch size must be a positive integer")
        if type(maximum_attempts) is not int or maximum_attempts <= 0:
            raise ValueError("maximum attempts must be a positive integer")
        if (
            type(maximum_response_characters) is not int
            or maximum_response_characters <= 0
        ):
            raise ValueError("maximum response characters must be a positive integer")
        self._store = store
        self._thread_id = thread_id
        self._run_id = run_id
        self._interactive_plan = interactive_plan
        self._scheduled_wake_plan = scheduled_wake_plan
        self._maximum_batch_size = maximum_batch_size
        self._maximum_attempts = maximum_attempts
        self._maximum_response_characters = maximum_response_characters
        self._on_settlement = on_settlement
        self._lock = asyncio.Lock()
        self._active: _ActiveClaim | None = None
        self._consumed_message_ids: tuple[UUID, ...] = ()
        self._consumed_owner_message_ids: tuple[UUID, ...] = ()
        self._consumed_owner_groups: tuple[tuple[UUID, ...], ...] = ()

    @property
    def consumed_message_ids(self) -> tuple[UUID, ...]:
        return self._consumed_message_ids

    @property
    def consumed_owner_message_ids(self) -> tuple[UUID, ...]:
        return self._consumed_owner_message_ids

    @property
    def consumed_owner_groups(self) -> tuple[tuple[UUID, ...], ...]:
        return self._consumed_owner_groups

    async def as_of_for_inputs(self, inputs: tuple[HostInput, ...]) -> datetime:
        if not inputs:
            raise CheckpointStateDefect("batch clock lookup requires host input")
        input_ids = tuple(item.input_id for item in inputs)
        async with self._lock:
            active = self._active
            if active is None or active.batch_as_of is None:
                raise CheckpointStateDefect("batch clock lookup has no active claim")
            try:
                return active.batch_as_of[input_ids]
            except KeyError as error:
                raise CheckpointStateDefect(
                    "batch clock lookup names an unknown input batch"
                ) from error

    async def automatic_write_gate_inputs(
        self,
        lineage: DispatchLineage,
    ) -> tuple[tuple[HostInput, ...], datetime]:
        """Return only current owner inputs and the latest admitted batch clock."""

        async with self._lock:
            active = self._active
            if active is None or active.claim.claim_id != lineage.claim_id:
                raise CheckpointStateDefect("write gate lineage has no active claim")
            if active.offered_checkpoint == lineage.through_checkpoint:
                self._promote_offered(active)
            if active.checkpoint != lineage.through_checkpoint:
                raise CheckpointStateDefect("write gate lineage checkpoint is stale")
            if (
                tuple(item.input_id for item in active.admitted_inputs)
                != lineage.input_ids
            ):
                raise CheckpointStateDefect("write gate lineage input IDs differ")
            owners = tuple(
                item
                for item in active.admitted_inputs
                if item.sections.sections
                and str(item.sections.sections[0].kind) == "owner_input"
            )
            if not owners:
                if (
                    active.route == "interactive"
                    and active.host_inputs
                    and all(item.source == "action" for item in active.host_inputs)
                ):
                    return (), active.current_as_of
                raise CheckpointStateDefect("write gate has no current owner authority")
            return owners, active.current_as_of

    async def settle_idle_control(
        self,
        *,
        message_id: UUID,
        control: Literal["stop", "pause", "resume"],
    ) -> ControlSettlement | None:
        async with self._lock:
            if self._active is not None:
                return None
            return await self._store.settle_control(
                message_id=message_id,
                source_conversation_id=str(self._thread_id),
                control=control,
            )

    async def claim(self, thread_id: ThreadId, owner_token: OwnerToken) -> ClaimResult:
        if thread_id != self._thread_id:
            raise CheckpointStateDefect(
                "checkpoint thread does not match configuration"
            )
        async with self._lock:
            if self._active is not None:
                return ClaimBusy()
            while True:
                remaining_run_inputs = self._maximum_batch_size - len(
                    self._consumed_message_ids
                )
                if remaining_run_inputs <= 0:
                    return ClaimNoWork()
                selection = await self._store.claim(
                    source_conversation_id=str(thread_id),
                    maximum_batch_size=remaining_run_inputs,
                    maximum_attempts=self._maximum_attempts,
                )
                if isinstance(selection, CircuitOpen):
                    raise CheckpointStateDefect("the cognitive circuit is parked")
                if isinstance(selection, NoMessages):
                    return ClaimNoWork()
                if isinstance(selection, ExhaustedMessage):
                    await self._settle_exhausted(selection)
                    continue
                break
            plan = (
                self._interactive_plan
                if selection.route == "interactive"
                else self._scheduled_wake_plan
            )
            selected_messages = selection.messages
            pending_control: Literal["stop", "pause"] | None = None
            if selection.route == "interactive":
                for index, value in enumerate(selected_messages):
                    normalized = value.text.strip().casefold()
                    if (
                        value.role == "owner"
                        and value.source == "discord"
                        and normalized
                        in {
                            "stop",
                            "pause",
                        }
                    ):
                        selected_messages = selected_messages[: index + 1]
                        pending_control = cast(Literal["stop", "pause"], normalized)
                        break
            claim = InputClaim(
                claim_id=ClaimId(selection.claim_id),
                inputs=tuple(_host_input(value) for value in selected_messages),
                through_checkpoint=Checkpoint(str(selected_messages[-1].id)),
                as_of=selection.as_of,
                plan=plan,
                attempt_number=selection.attempt_number,
            )
            self._active = _ActiveClaim(
                claim=claim,
                owner_token=owner_token,
                route=selection.route,
                message_ids=tuple(value.id for value in selected_messages),
                checkpoint=claim.through_checkpoint,
                host_inputs=tuple(
                    value for value in selected_messages if value.role == "host"
                ),
                admitted_inputs=claim.inputs,
                current_as_of=claim.as_of,
                pending_control=pending_control,
                batch_as_of={
                    tuple(item.input_id for item in claim.inputs): claim.as_of,
                },
            )
            return ClaimAcquired(claim)

    async def poll(
        self,
        claim: InputClaim,
        through_checkpoint: Checkpoint,
    ) -> PollResult:
        async with self._lock:
            active = self._require_active(
                claim, through_checkpoint, promote_offered=True
            )
            if active.pending_control is not None:
                return Preempt(active.pending_control)
            while True:
                controls = await self._store.pending_controls(
                    source_conversation_id=str(self._thread_id),
                    limit=self._maximum_batch_size,
                )
                found_preempting_control = False
                for control in controls:
                    if control.control != "resume":
                        found_preempting_control = True
                        break
                    await self._store.settle_control(
                        message_id=control.message_id,
                        source_conversation_id=str(self._thread_id),
                        control="resume",
                    )
                if found_preempting_control or not controls:
                    break
            remaining_batch_size = self._maximum_batch_size - len(
                self._consumed_message_ids
                + active.message_ids
                + active.offered_message_ids
            )
            if remaining_batch_size <= 0 and not found_preempting_control:
                return NoNewInput()
            result = await self._store.poll(
                route=(
                    "interactive" if active.route == "interactive" else "scheduled_wake"
                ),
                source_conversation_id=str(self._thread_id),
                known_message_ids=active.message_ids + active.offered_message_ids,
                maximum_batch_size=(
                    self._maximum_batch_size
                    if found_preempting_control
                    else remaining_batch_size
                ),
                include_host_inputs=not (
                    active.host_inputs or active.offered_host_inputs
                ),
            )
            if result is None:
                return NoNewInput()
            if result.preempt_reason in {"stop", "pause"}:
                control = cast(Literal["stop", "pause"], result.preempt_reason)
                active.message_ids += tuple(value.id for value in result.messages)
                active.host_inputs += tuple(
                    value for value in result.messages if value.role == "host"
                )
                active.checkpoint = Checkpoint(result.through_checkpoint)
                active.pending_control = control
                return Preempt(control)
            if result.preempt_reason is not None:
                return Preempt(result.preempt_reason)
            appended = tuple(_host_input(value) for value in result.messages)
            active.offered_message_ids = tuple(value.id for value in result.messages)
            active.offered_host_inputs = tuple(
                value for value in result.messages if value.role == "host"
            )
            active.offered_inputs = appended
            active.offered_as_of = result.as_of
            new_checkpoint = Checkpoint(result.through_checkpoint)
            active.offered_checkpoint = new_checkpoint
            assert active.batch_as_of is not None
            if tuple(item.input_id for item in appended) in active.batch_as_of:
                raise CheckpointStateDefect("polled input batch identity was reused")
            active.batch_as_of[tuple(item.input_id for item in appended)] = result.as_of
            return AppendInputs(
                inputs=appended,
                new_checkpoint=new_checkpoint,
                new_as_of=result.as_of,
            )

    async def settle(
        self,
        claim: InputClaim,
        through_checkpoint: Checkpoint,
        conclusion: HostConclusion,
    ) -> SettleResult:
        async with self._lock:
            active = self._require_active(
                claim, through_checkpoint, promote_offered=True
            )
            kind, outcome, conclusion_text = _conclusion(conclusion)
            if active.host_inputs and not (kind == "conversation" and outcome == "say"):
                conclusion_text = render_host_fallback(
                    source=active.host_inputs[0].source,
                    text=active.host_inputs[0].text,
                    maximum_characters=self._maximum_response_characters,
                    suffix=conclusion_text,
                )
                if not (kind == "suspension" and outcome == "system"):
                    kind = "conversation"
                    outcome = "host_fallback"
            if (
                conclusion_text is not None
                and len(conclusion_text) > self._maximum_response_characters
            ):
                if active.host_inputs:
                    conclusion_text = render_host_fallback(
                        source=active.host_inputs[0].source,
                        text=active.host_inputs[0].text,
                        maximum_characters=self._maximum_response_characters,
                    )
                    kind = "conversation"
                    outcome = "host_fallback"
                else:
                    kind = "stopped"
                    outcome = "response_too_long"
                    conclusion_text = (
                        "I stopped because the response exceeded Discord's message "
                        "limit."
                    )
            conclusion_message_id = None
            if conclusion_text is not None:
                identity = json.dumps(
                    [
                        str(self._thread_id),
                        str(self._run_id),
                        str(claim.claim_id),
                        str(through_checkpoint),
                        kind,
                        outcome,
                        sha256(conclusion_text.encode()).hexdigest(),
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                conclusion_message_id = uuid5(
                    NAMESPACE_URL,
                    f"jarvis-conclusion-v1:{identity}",
                )
            result = await self._store.settle(
                consumed_message_ids=active.message_ids,
                source_conversation_id=str(self._thread_id),
                trace=SettlementTrace(
                    run_id=str(self._run_id),
                    through_checkpoint=str(through_checkpoint),
                    conclusion_kind=kind,
                    outcome=outcome,
                ),
                conclusion_text=conclusion_text,
                conclusion_message_id=conclusion_message_id,
            )
            self._record_consumed(active.message_ids)
            owner_group: tuple[UUID, ...] = ()
            if (
                kind == "conversation" and outcome in {"say", "finish", "host_fallback"}
            ) or (kind == "suspension" and outcome == "user"):
                owner_group = self._record_consumed_owners(active)
            self._active = None
            if self._on_settlement is not None:
                self._on_settlement(owner_group)
            return SettleMoreInput() if result.more_input else SettleIdle()

    async def release(self, claim: InputClaim, reason: str) -> ReleaseResult:
        async with self._lock:
            if self._active is None:
                return AlreadyReleased()
            active = self._require_active(claim, self._active.checkpoint)
            if active.pending_control is not None:
                if reason != "preempted by host policy":
                    raise CheckpointStateDefect(
                        "control preemption was released for an unexpected reason"
                    )
                control_text = (
                    "Paused." if active.pending_control == "pause" else "Stopped."
                )
                if active.host_inputs:
                    control_text = render_host_fallback(
                        source=active.host_inputs[0].source,
                        text=active.host_inputs[0].text,
                        maximum_characters=self._maximum_response_characters,
                        suffix=control_text,
                    )
                await self._store.settle(
                    consumed_message_ids=active.message_ids,
                    source_conversation_id=str(self._thread_id),
                    trace=SettlementTrace(
                        run_id=str(self._run_id),
                        through_checkpoint=str(active.checkpoint),
                        conclusion_kind="stopped",
                        outcome=f"owner_{active.pending_control}",
                    ),
                    conclusion_text=control_text,
                    conclusion_message_id=_control_conclusion_id(
                        active.message_ids,
                        active.pending_control,
                    ),
                )
                self._record_consumed(active.message_ids)
            self._active = None
            return Released()

    async def park(self, claim: InputClaim, reason: str) -> ParkResult:
        async with self._lock:
            if self._active is None:
                return AlreadyParked()
            active = self._require_active(claim, self._active.checkpoint)
            parked = await self._store.park(
                claimed_message_ids=active.message_ids,
                reason_code=_reason_code(reason),
            )
            self._active = None
            return Parked() if parked else AlreadyParked()

    async def _settle_exhausted(self, exhausted: ExhaustedMessage) -> None:
        value = exhausted.message
        conclusion_text = (
            render_host_fallback(
                source=value.source,
                text=value.text,
                maximum_characters=self._maximum_response_characters,
                suffix=(
                    "I stopped this message because it reached the configured "
                    "retry limit."
                ),
            )
            if value.role == "host"
            else (
                "I stopped this message because it reached the configured retry limit."
            )
        )
        await self._store.settle(
            consumed_message_ids=(value.id,),
            source_conversation_id=str(self._thread_id),
            trace=SettlementTrace(
                run_id=str(self._run_id),
                through_checkpoint=str(value.id),
                conclusion_kind="stopped",
                outcome="attempts_exhausted",
            ),
            conclusion_text=conclusion_text,
            conclusion_message_id=uuid5(
                NAMESPACE_URL,
                f"jarvis-poison-v1:{value.id}:{self._maximum_attempts}",
            ),
        )
        self._record_consumed((value.id,))

    def _record_consumed(self, message_ids: tuple[UUID, ...]) -> None:
        known = set(self._consumed_message_ids)
        self._consumed_message_ids += tuple(
            message_id for message_id in message_ids if message_id not in known
        )

    def _record_consumed_owners(self, active: _ActiveClaim) -> tuple[UUID, ...]:
        host_ids = {value.id for value in active.host_inputs}
        known = set(self._consumed_owner_message_ids)
        group = tuple(
            message_id
            for message_id in active.message_ids
            if message_id not in host_ids and message_id not in known
        )
        if group:
            self._consumed_owner_message_ids += group
            self._consumed_owner_groups += (group,)
        return group

    def _require_active(
        self,
        claim: InputClaim,
        through_checkpoint: Checkpoint,
        *,
        promote_offered: bool = False,
    ) -> _ActiveClaim:
        active = self._active
        if active is None or active.claim.claim_id != claim.claim_id:
            raise CheckpointStateDefect("checkpoint claim is not active")
        if (
            promote_offered
            and active.offered_checkpoint is not None
            and through_checkpoint == active.offered_checkpoint
        ):
            self._promote_offered(active)
        if through_checkpoint != active.checkpoint:
            raise CheckpointStateDefect("checkpoint watermark is stale or unknown")
        return active

    @staticmethod
    def _promote_offered(active: _ActiveClaim) -> None:
        if active.offered_checkpoint is None or active.offered_as_of is None:
            raise CheckpointStateDefect("offered input metadata is incomplete")
        active.message_ids += active.offered_message_ids
        active.host_inputs += active.offered_host_inputs
        active.admitted_inputs += active.offered_inputs
        active.current_as_of = active.offered_as_of
        active.checkpoint = active.offered_checkpoint
        active.offered_message_ids = ()
        active.offered_host_inputs = ()
        active.offered_inputs = ()
        active.offered_as_of = None
        active.offered_checkpoint = None


def _host_input(value: StoredMessage) -> HostInput:
    kind = "owner_input" if value.role == "owner" else "host_input"
    attributes = (
        PromptAttribute(PromptAttributeName("source"), value.source),
        PromptAttribute(
            PromptAttributeName("source_conversation_id"),
            value.source_conversation_id,
        ),
    )
    return HostInput(
        input_id=InputId(str(value.id)),
        sections=PromptSections(
            (
                PromptSection(
                    PromptSectionKind(kind),
                    attributes,
                    PromptText(value.text),
                ),
            )
        ),
        source_timestamp=value.created_at,
    )


def _conclusion(conclusion: HostConclusion) -> tuple[str, str, str | None]:
    if isinstance(conclusion, ConversationConclusion):
        return (
            "conversation",
            "say" if conclusion.text is not None else "finish",
            conclusion.text,
        )
    if isinstance(conclusion, StoppedConclusion):
        messages = {
            "budget_exhausted": (
                "I stopped because this turn reached its configured limit."
            ),
            "cancelled": "Stopped.",
            "protocol_error": "I stopped because the model response stayed invalid.",
            "provider_error": "I stopped after repeated provider failures.",
            "quota_exhausted": (
                "I stopped because Codex capacity is currently exhausted."
            ),
            "stopped": "Stopped.",
        }
        return "stopped", conclusion.reason.value, messages[conclusion.reason.value]
    if isinstance(conclusion, SuspensionConclusion):
        return "suspension", conclusion.waiting_for.value, None
    raise CheckpointStateDefect("the conversational thread returned structured output")


def _reason_code(reason: str) -> str:
    value = _REASON_SEPARATOR.sub("_", reason.strip().casefold()).strip("_")
    return (value or "configuration_defect")[:64].rstrip("_")


def _control_conclusion_id(message_ids: tuple[UUID, ...], reason: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        "jarvis-control-v1:" + ",".join(map(str, message_ids)) + f":{reason}",
    )


__all__ = ["PostgresInputCheckpoint"]
