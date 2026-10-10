"""One main native turn; canonical requests and existing receipts survive sessions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4, uuid5

from llm_agent_kernel import (
    AppendInputs,
    CancellationToken,
    Checkpoint,
    HostInput,
    HostRef,
    InputId,
    NativeDefect,
    NativeDispatchLineage,
    NativeRequest,
    NativeUncertain,
    NoNewInput,
    Preempt,
    ProviderSessionLease,
    input_batch,
    native_request_fits,
    run_native,
)
from llm_tools import (
    FrozenToolPlan,
    InvocationPosition,
    ParsedJson,
    PromptAttribute,
    PromptAttributeName,
    PromptJson,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    ReplayPolicy,
    raw_input_digest,
)
from provider_runtime.agent_runtime import (
    AgentMessage,
    AgentNotSubmitted,
    NativeTerminalEvidence,
    OutputSchemaMismatch,
    decode_agent_output,
    thaw_json_value,
)
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import array, insert
from universal_memory import MemoryError, render_view

from jarvis.actions import (
    ActionStore,
    finish_schedule_conclusion,
    recorded_action_result,
)
from jarvis.admission import ExactToolBudgetFactory, JarvisOwner
from jarvis.agent_tools import AgentListResult
from jarvis.approval import render_approval
from jarvis.db import (
    action,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    read_position,
)
from jarvis.definitions import RoleDefinitions
from jarvis.kernel import KernelRuntime
from jarvis.memory_service import MemoryService
from jarvis.memory_workers import MemoryWorker
from jarvis.messages import MessageStore, StoredMessage, render_host_fallback
from jarvis.native_journal import (
    PostgresNativeJournal,
    commit_product,
    recover_sealed_turn,
)
from jarvis.ownership import (
    DeploymentOwnershipDefect,
    lock_conversation,
    memory_is_admitted,
)
from jarvis.read_positions import PostgresReadRecorder
from jarvis.read_tools import CalendarListEventsSuccess
from jarvis.settings import Settings
from jarvis.terminal import JarvisTerminal, TurnEvidence
from jarvis.tool_results import completed_tool_result
from jarvis.write_dispatch import WriteToolDispatcher, require_current_action_binding

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NativeRunOutcome:
    status: Literal["no_work", "progressed", "blocked", "stopped"]


def _host_input(value: StoredMessage) -> HostInput:
    return HostInput(
        InputId(str(value.id)),
        PromptSections(
            (
                PromptSection(
                    PromptSectionKind(
                        "owner_input" if value.role == "owner" else "host_input"
                    ),
                    tuple(
                        PromptAttribute(PromptAttributeName(name), text)
                        for name, text in (
                            ("input_id", str(value.id)),
                            ("source", value.source),
                            ("source_timestamp", value.created_at.isoformat()),
                            ("request_state", value.request_state or "host_event"),
                            ("wait_reason", value.wait_reason or "none"),
                        )
                    ),
                    PromptText(value.text),
                ),
            )
        ),
        value.created_at,
    )


class NativeInputs:
    def __init__(
        self,
        *,
        owner: JarvisOwner,
        store: MessageStore,
        plan: FrozenToolPlan,
        memory_cutoff: int,
        cancellation: CancellationToken,
        maximum_batch_size: int,
    ) -> None:
        self.owner, self.store, self.plan = owner, store, plan
        self.memory_cutoff = memory_cutoff
        self.cancellation, self.maximum_batch_size = cancellation, maximum_batch_size

    async def poll(self, request: NativeRequest, through_checkpoint: Checkpoint | None):
        del through_checkpoint
        if self.cancellation.cancelled or await self.store.paused(self.owner.scope_id):
            return Preempt("owner_stop")
        async with self.owner.database.connect() as connection:
            attempt = (
                (
                    await connection.execute(
                        select(native_attempt).where(
                            native_attempt.c.id == UUID(request.attempt_id)
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if attempt is not None and (
                attempt["owner_epoch"] != str(self.owner.token)
                or attempt["fenced_at"] is not None
            ):
                return Preempt("owner_fenced")
            known = tuple(
                (
                    await connection.execute(
                        select(native_input_delivery.c.message_id).where(
                            native_input_delivery.c.attempt_id
                            == UUID(request.attempt_id)
                        )
                    )
                ).scalars()
            )
        scheduled = self.plan.profile.id == "scheduled_wake"
        values = await self.store.pending_inputs(
            source_conversation_id=self.owner.scope_id,
            limit=self.maximum_batch_size,
            exclude_ids=known or tuple(map(UUID, request.input_ids)),
            scheduled=scheduled,
        )
        if not values:
            return NoNewInput()
        inputs = tuple(map(_host_input, values))
        return AppendInputs(
            inputs,
            Checkpoint(str(values[-1].id)),
            datetime.now(UTC),
        )

    async def automatic_write_gate_inputs(
        self, lineage: NativeDispatchLineage, request_ref: UUID
    ):
        await self.owner.require_current(lineage.permit)
        async with self.owner.database.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(message).where(message.c.id == request_ref)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if (
            row is None
            or row["role"] != "owner"
            or row["source_conversation_id"] != self.owner.scope_id
            or row["request_state"] not in {"pending", "waiting"}
            or str(request_ref) not in lineage.input_ids
        ):
            raise NativeDefect(
                "Write request_ref is outside delivered live owner intent"
            )
        value = await self.store.message_by_id(request_ref)
        assert value is not None
        return (_host_input(value),), datetime.now(UTC)


class NativeRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        store: MessageStore,
        owner: JarvisOwner,
        kernel_runtime: KernelRuntime,
        definitions: RoleDefinitions,
        memory: MemoryService,
        memory_worker: MemoryWorker,
        dispatcher_factory: Callable[[NativeInputs], WriteToolDispatcher],
        actions: ActionStore,
    ) -> None:
        self.settings, self.store, self.owner = settings, store, owner
        self.kernel, self.definitions = kernel_runtime, definitions
        self.memory, self.memory_worker, self.actions = memory, memory_worker, actions
        self.dispatcher_factory = dispatcher_factory
        self._session: ProviderSessionLease | None = None
        self._journal: PostgresNativeJournal | None = None
        self._dispatchers: list[WriteToolDispatcher] = []
        self.notify_delivery: Callable[[], None] = lambda: None
        self.notify_work: Callable[[], None] = lambda: None

    async def record(self, attempt_id: str, message: AgentMessage) -> None:
        if self._journal is None:
            raise NativeDefect("public message has no active native journal")
        await self._journal.record(attempt_id, message)
        await self.memory.publish()
        self.notify_delivery()

    async def recover(self) -> None:
        await recover_native_products(self.owner)
        await _recover_native_note_saves(self.owner, self.memory)
        await self.memory.publish()
        self.notify_delivery()

    async def run(self, cancellation: CancellationToken) -> NativeRunOutcome:
        self._dispatchers = [item for item in self._dispatchers if item.check_effects()]
        await self.recover()
        if cancellation.cancelled or await self.store.paused(self.owner.scope_id):
            return NativeRunOutcome("stopped")
        pending = await self.store.pending_inputs(
            source_conversation_id=self.owner.scope_id,
            limit=self.settings.maximum_batch_size,
            scheduled=False,
        )
        scheduled = not pending
        if scheduled:
            pending = await self.store.pending_inputs(
                source_conversation_id=self.owner.scope_id, limit=1, scheduled=True
            )
        if not pending:
            return NativeRunOutcome("no_work")
        if not scheduled:
            async with self.owner.database.connect() as connection:
                waiting = tuple(
                    (
                        await connection.execute(
                            select(message.c.id)
                            .where(
                                message.c.source_conversation_id == self.owner.scope_id,
                                message.c.role == "owner",
                                message.c.request_state == "waiting",
                                message.c.control_kind.is_(None),
                            )
                            .order_by(message.c.created_at, message.c.id)
                            .limit(self.settings.maximum_batch_size - len(pending))
                        )
                    ).scalars()
                )
            extra = [
                await self.store.message_by_id(identifier) for identifier in waiting
            ]
            pending = tuple(
                sorted(
                    (*pending, *(item for item in extra if item is not None)),
                    key=lambda item: (item.created_at, item.id),
                )
            )
        plan = self.definitions.plans["scheduled_wake" if scheduled else "main"]
        try:
            pending_publication = await self.memory.pending_publication()
            await self.memory.project_pending(pending_publication)
            cutoff = await self.memory.library.cutoff()
            await self.memory_worker.ensure_ready(cutoff, cancellation)
            nodes = await self.memory.library.main_view(cutoff)
        except MemoryError as error:
            LOGGER.warning("memory preparation blocked: code=%s", error.code)
            return NativeRunOutcome("blocked")
        if cancellation.cancelled:
            return NativeRunOutcome("stopped")
        source = PromptSections(
            (
                PromptSection(
                    PromptSectionKind("historical_memory_view"),
                    (),
                    PromptText(render_view(nodes, cutoff)),
                ),
            )
        )
        as_of = datetime.now(UTC)
        while pending:
            inputs = tuple(map(_host_input, pending))
            current = input_batch(
                inputs,
                as_of,
                render_source_timestamps=True,
                render_batch_as_of=True,
            )

            def fits(
                receipts: PromptSections, current: PromptSection = current
            ) -> bool:
                return native_request_fits(
                    self.definitions.main,
                    PromptSections((*source.sections, *receipts.sections, current)),
                )

            receipts = await native_receipt_context(
                self.owner,
                input_ids=tuple(item.input_id for item in inputs),
                fits=fits,
            )
            if receipts is not None:
                break
            pending = pending[:-1]
        else:
            LOGGER.warning("native context blocked: code=request_too_large")
            return NativeRunOutcome("blocked")
        projected = PromptSections((*source.sections, *receipts.sections, current))
        attempt_id = str(uuid4())
        permit = self.owner.permit("jarvis-native:" + attempt_id)
        request = NativeRequest(
            attempt_id,
            permit,
            "thread",
            tuple(item.input_id for item in inputs),
            projected,
            projected,
            plan,
            "restart_reasoning",
            None,
            Checkpoint(str(pending[-1].id)),
        )
        try:
            self._session = await self.kernel.provider.acquire_native(
                self.definitions.main, plan, permit, None
            )
            journal = PostgresNativeJournal(
                self.owner.database,
                definition=self.definitions.main,
                plan=plan,
                owner=self.owner,
                memory=self.memory,
            )
            self._journal = journal
            native_inputs = NativeInputs(
                owner=self.owner,
                store=self.store,
                plan=plan,
                memory_cutoff=cutoff,
                cancellation=cancellation,
                maximum_batch_size=self.settings.maximum_batch_size,
            )
            dispatcher = self.dispatcher_factory(native_inputs)
            dispatcher.on_effect_settled = self.notify_work
            self._dispatchers.append(dispatcher)
            terminal = await run_native(
                definition=self.definitions.main,
                request=request,
                provider=self.kernel.provider,
                session=self._session,
                owner=self.owner,
                journal=journal,
                inputs=native_inputs,
                dispatch=dispatcher,
                budgets=ExactToolBudgetFactory(),
                messages=self,
                cancellation=cancellation,
            )
            if isinstance(terminal, AgentNotSubmitted):
                await _fail_native_product(
                    self.owner,
                    request.attempt_id,
                    request.input_ids,
                    "the native turn was not submitted",
                )
                return NativeRunOutcome("blocked")
            if cancellation.cancelled or await self.store.paused(self.owner.scope_id):
                if isinstance(terminal.evidence, NativeTerminalEvidence):
                    await _mark_stale(self.owner, UUID(attempt_id), "owner_stopped")
                return NativeRunOutcome("stopped")
            if isinstance(terminal.evidence, NativeTerminalEvidence):
                await _settle_native_product(self.owner, request.attempt_id)
            else:
                await _fail_native_product(
                    self.owner,
                    request.attempt_id,
                    request.input_ids,
                    "the native provider did not complete this turn",
                )
            return NativeRunOutcome("progressed")
        except DeploymentOwnershipDefect:
            raise
        except NativeUncertain:
            # run_native fences old callbacks; restart reasoning in a fresh thread.
            return NativeRunOutcome("progressed")
        except NativeDefect as error:
            if cancellation.cancelled or await self.store.paused(self.owner.scope_id):
                return NativeRunOutcome("stopped")
            await _fail_native_product(
                self.owner,
                request.attempt_id,
                request.input_ids,
                "native protocol requires repair",
            )
            LOGGER.warning(
                "native turn blocked: attempt=%s exception=%s",
                attempt_id,
                type(error).__name__,
            )
            return NativeRunOutcome("blocked")
        finally:
            self._journal = None
            session, self._session = self._session, None
            if session is not None:
                await self.kernel.provider.discard(session)
            await self.memory.publish()
            self.notify_delivery()

    async def refresh_stopped_approvals(self) -> None:
        async with self.owner.database.connect() as connection:
            ids = tuple(
                (
                    await connection.execute(
                        select(action.c.id)
                        .join(message, message.c.id == action.c.origin_message_id)
                        .where(
                            message.c.source_conversation_id == self.owner.scope_id,
                            message.c.request_state == "pending",
                            action.c.status == "cancelled",
                            action.c.attempts == 0,
                            action.c.approval_message_id.is_not(None),
                            action.c.result["reason_code"].as_string()
                            == "owner_stopped",
                            ~action.c.id.in_(
                                select(action.c.supersedes_action_id).where(
                                    action.c.supersedes_action_id.is_not(None)
                                )
                            ),
                        )
                    )
                ).scalars()
            )
        for identifier in ids:
            stored = await self.actions.get(identifier)
            assert stored is not None
            binding = require_current_action_binding(
                stored, self.definitions.plans["main"]
            )
            value = binding.spec.input_type.model_validate(stored.arguments)
            successor_id = uuid5(stored.id, "resumed-approval")
            presentation = render_approval(
                successor_id, stored.tool_name, value.arguments
            )
            await self.actions.insert_awaiting_approval(
                tool_name=stored.tool_name,
                arguments=stored.arguments,
                execution_contract=stored.execution_contract,
                origin_message_id=stored.origin_message_id,
                approval_text=presentation.content,
                source_conversation_id=self.owner.scope_id,
                action_id=successor_id,
                supersedes_action_id=stored.id,
            )
        self.notify_delivery()

    async def close(self) -> None:
        for dispatcher in self._dispatchers:
            await dispatcher.close()
        if self._session is not None:
            await self.kernel.provider.discard(self._session)
            self._session = None


async def recover_native_products(owner: JarvisOwner) -> tuple[UUID, ...]:
    """Fence old callback owners, then drain sealed terminals locally."""
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        rows = (
            (
                await connection.execute(
                    select(native_attempt)
                    .where(
                        native_attempt.c.conversation_id == owner.scope_id,
                        native_attempt.c.product_outcome.is_(None),
                    )
                    .order_by(native_attempt.c.attempt_seq)
                    .with_for_update()
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == row["id"])
                .values(fenced_at=func.coalesce(native_attempt.c.fenced_at, func.now()))
            )
    completed: list[UUID] = []
    for row in rows:
        if row["terminal"] is None:
            continue
        try:
            completed.extend(
                await _settle_native_product(owner, str(row["id"]), recovering=True)
            )
        except NativeDefect:
            await _mark_stale(owner, row["id"], "request_authority_changed")

    return tuple(completed)


async def _mark_stale(owner: JarvisOwner, attempt_id: UUID, reason: str) -> None:
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        await connection.execute(
            update(native_attempt)
            .where(
                native_attempt.c.id == attempt_id,
                native_attempt.c.terminal.is_not(None),
                native_attempt.c.product_outcome.is_(None),
            )
            .values(product_outcome={"status": "stale", "reason": reason})
        )


async def _settle_native_product(
    owner: JarvisOwner,
    attempt_id: str,
    *,
    recovering: bool = False,
) -> tuple[UUID, ...]:
    turn = await recover_sealed_turn(owner.database, owner, attempt_id)
    if turn is None:
        raise NativeDefect("product settlement lacks a sealed native terminal")
    try:
        if turn.terminal.status != "succeeded":
            await _fail_native_product(
                owner,
                turn.attempt_id,
                turn.input_ids,
                "the native provider did not complete this turn",
            )
            return ()
        if turn.output is None:
            raise ValueError("original output schema is absent")
        value = decode_agent_output(turn.output, turn.terminal)
        final = JarvisTerminal.model_validate(thaw_json_value(value))
        evidence = await _turn_evidence(owner, UUID(turn.attempt_id))
        completed = await commit_product(
            owner.database,
            owner,
            turn,
            final,
            evidence,
            recovering=recovering,
        )
    except (TypeError, ValueError, OutputSchemaMismatch):
        await _fail_native_product(
            owner,
            turn.attempt_id,
            turn.input_ids,
            "the final response did not meet its content contract",
        )
        return ()
    return completed


async def _fail_native_product(
    owner: JarvisOwner,
    attempt_id: str,
    input_ids: tuple[InputId, ...],
    reason: str,
) -> None:
    await owner.require_current(owner.permit("jarvis-product:" + attempt_id))
    timestamp = datetime.now(UTC)
    conclusion_id = uuid5(UUID(attempt_id), "product-failure")
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        ids = tuple(
            (
                await connection.execute(
                    select(native_input_delivery.c.message_id).where(
                        native_input_delivery.c.attempt_id == UUID(attempt_id)
                    )
                )
            ).scalars()
        ) or tuple(map(UUID, input_ids))
        rows = (
            (
                await connection.execute(
                    select(message)
                    .where(message.c.id.in_(ids))
                    .order_by(message.c.id)
                    .with_for_update()
                )
            )
            .mappings()
            .all()
        )
        attempt = (
            (
                await connection.execute(
                    select(native_attempt)
                    .where(native_attempt.c.id == UUID(attempt_id))
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if attempt is not None and attempt["product_outcome"] is not None:
            return
        if attempt is not None:
            if attempt["conversation_id"] != owner.scope_id:
                raise NativeDefect("product failure is outside this conversation")
        controlled = (
            None
            if attempt is None
            else await connection.scalar(
                select(message.c.id)
                .where(
                    message.c.source_conversation_id == owner.scope_id,
                    message.c.control_sequence > attempt["request"]["control_sequence"],
                    message.c.control_targets.overlap(list(ids)),
                )
                .limit(1)
            )
        )
        if controlled is not None or any(
            item["request_state"] == "stopped" for item in rows
        ):
            if attempt is not None and attempt["terminal"] is not None:
                await connection.execute(
                    update(native_attempt)
                    .where(native_attempt.c.id == attempt["id"])
                    .values(
                        product_outcome={
                            "status": "stale",
                            "reason": "owner_stopped",
                        }
                    )
                )
            return
        content = (
            f"i couldn't finish this turn: {reason}. "
            "unfinished requests and recorded actions are retained."
        )
        hosts = tuple(item for item in rows if item["role"] == "host")
        if hosts:
            content = render_host_fallback(
                source=hosts[0]["source"],
                text=hosts[0]["text"],
                maximum_characters=2000,
                suffix=content,
            )
        await connection.execute(
            insert(message)
            .values(
                id=conclusion_id,
                role="assistant",
                text=content,
                source="native_failure",
                memory_admitted=memory_is_admitted(connection),
                source_conversation_id=owner.scope_id,
                processed_at=timestamp,
                trace={"native_attempt_id": attempt_id},
            )
            .on_conflict_do_nothing(index_elements=(message.c.id,))
        )
        for item in rows:
            if item["role"] == "owner" and item["request_state"] in {
                "pending",
                "waiting",
            }:
                await connection.execute(
                    update(message)
                    .where(message.c.id == item["id"])
                    .values(
                        request_state="waiting",
                        wait_reason="configuration",
                        processed_at=None,
                    )
                )
            elif item["role"] == "host" and item["processed_at"] is None:
                await connection.execute(
                    update(message)
                    .where(message.c.id == item["id"])
                    .values(
                        processed_at=timestamp,
                        trace={
                            **item["trace"],
                            "conclusion_message_id": str(conclusion_id),
                        },
                    )
                )
                if item["source"] == "schedule_wake":
                    await finish_schedule_conclusion(
                        connection,
                        action_id=UUID(item["source_message_id"]),
                        conclusion_message_id=conclusion_id,
                        recorded_at=timestamp,
                    )
        if attempt is not None:
            changes = {"fenced_at": attempt["fenced_at"] or timestamp}
            if attempt["terminal"] is not None:
                changes["product_outcome"] = {
                    "status": "failed",
                    "response_id": str(conclusion_id),
                    "reason": reason,
                }
            await connection.execute(
                update(native_attempt)
                .where(native_attempt.c.id == attempt["id"])
                .values(**changes)
            )


async def _recover_native_note_saves(owner: JarvisOwner, memory: MemoryService) -> None:
    """Link existing local note receipts after the old callback owner is fenced."""
    async with owner.database.connect() as connection:
        rows = (
            (
                await connection.execute(
                    select(native_invocation)
                    .join(
                        native_attempt,
                        native_attempt.c.id == native_invocation.c.attempt_id,
                    )
                    .where(
                        native_attempt.c.conversation_id == owner.scope_id,
                        native_attempt.c.fenced_at.is_not(None),
                        native_invocation.c.tool_id == "memory.save_note",
                        native_invocation.c.validation == "accepted",
                        native_invocation.c.reply_receipt.is_(None),
                    )
                    .order_by(native_attempt.c.attempt_seq, native_invocation.c.ordinal)
                )
            )
            .mappings()
            .all()
        )
    recorder = PostgresReadRecorder(owner.database)
    for row in rows:
        if row["frozen_contract"]["effect"] != "Write":
            raise NativeDefect(
                "local note recovery requires the original Write contract"
            )
        position = InvocationPosition("native-invocation:" + str(row["id"]))
        arguments = row["proposal"]["arguments"]
        contract = {
            "tool_id": "memory.save_note",
            "tool_contract_revision": row["frozen_contract"]["tool_contract_revision"],
            "policy_revision": row["frozen_contract"]["policy_revision"],
            "plan_revision": row["frozen_contract"]["plan_revision"],
            "input_digest": raw_input_digest(ParsedJson(arguments)),
            "replay_policy": ReplayPolicy.ReDispatchable.value,
        }
        result = await recorder.recover_committed_note_save(
            position=position, arguments=arguments, contract=contract, memory=memory
        )
        if result is None:
            continue
        receipt = completed_tool_result(result, HostRef(str(position)))
        async with owner.database.begin() as connection:
            await lock_conversation(connection, owner.scope_id)
            current = (
                (
                    await connection.execute(
                        select(native_invocation)
                        .where(native_invocation.c.id == row["id"])
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if current["reply_receipt"] is not None:
                if current["read_position"] != str(position):
                    raise NativeDefect("local note receipt lost its original position")
                continue
            await connection.execute(
                update(native_invocation)
                .where(native_invocation.c.id == row["id"])
                .values(
                    read_position=str(position),
                    reply_receipt={
                        "type": "tool_result_ref",
                        "result_ref": str(position),
                        "host_ref": str(position),
                        "wire_text": receipt.model_text,
                        "success": result["type"] == "Success",
                    },
                    reply_recorded_at=datetime.now(UTC),
                )
            )


async def native_receipt_context(
    owner: JarvisOwner,
    *,
    input_ids: tuple[InputId, ...],
    fits: Callable[[PromptSections], bool],
) -> PromptSections | None:
    """Keep every operative fact, then fit a whole-record recent tail around it."""
    selected_ids = tuple(map(UUID, input_ids))
    async with owner.database.connect() as connection:
        resolutions = (
            (
                await connection.execute(
                    select(message.c.source_message_id).where(
                        message.c.id.in_(selected_ids),
                        message.c.source == "action",
                    )
                )
            )
            .scalars()
            .all()
        )
        accepted_actions = (
            (
                await connection.execute(
                    select(action)
                    .join(message, message.c.id == action.c.origin_message_id)
                    .where(
                        message.c.source_conversation_id == owner.scope_id,
                        or_(
                            action.c.origin_message_id.in_(selected_ids),
                            action.c.id.in_(tuple(map(UUID, resolutions))),
                        ),
                    )
                    .order_by(action.c.created_at, action.c.id)
                )
            )
            .mappings()
            .all()
        )
        action_ids = tuple(row["id"] for row in accepted_actions)
        recent = (
            select(native_invocation.c.id)
            .join(native_attempt, native_attempt.c.id == native_invocation.c.attempt_id)
            .where(native_attempt.c.conversation_id == owner.scope_id)
            .order_by(
                native_attempt.c.attempt_seq.desc(),
                native_invocation.c.ordinal.desc(),
            )
            .limit(100)
            .correlate(None)
        )
        rows = (
            (
                await connection.execute(
                    select(native_invocation, native_attempt.c.attempt_seq)
                    .join(
                        native_attempt,
                        native_attempt.c.id == native_invocation.c.attempt_id,
                    )
                    .where(
                        native_attempt.c.conversation_id == owner.scope_id,
                        or_(
                            native_invocation.c.proposal["input_ids"].op("?|")(
                                array(tuple(map(str, input_ids)))
                            ),
                            native_invocation.c.action_id.in_(action_ids),
                            native_invocation.c.id.in_(recent),
                        ),
                    )
                    .order_by(
                        native_attempt.c.attempt_seq,
                        native_invocation.c.ordinal,
                    )
                )
            )
            .mappings()
            .all()
        )
        records: list[dict[str, object]] = []
        for row in accepted_actions:
            records.append(
                {
                    "kind": "accepted_action",
                    "action_ref": str(row["id"]),
                    "request_ref": str(row["origin_message_id"]),
                    "tool_id": row["tool_name"],
                    "arguments": row["arguments"],
                    "execution_contract": row["execution_contract"],
                    "status": row["status"],
                    "attempts": row["attempts"],
                    "recorded_result": await recorded_action_result(
                        connection, row["id"]
                    ),
                    "supersedes_action_ref": (
                        str(row["supersedes_action_id"])
                        if row["supersedes_action_id"] is not None
                        else None
                    ),
                }
            )
        observations: list[tuple[dict[str, object], bool]] = []
        for row in rows:
            result = None
            # The original wire already contains the entire public result.
            # Keep it once; canonical recorder storage stays unchanged.
            if row["reply_receipt"] is None:
                if row["read_position"] is not None:
                    result = await connection.scalar(
                        select(read_position.c.result).where(
                            read_position.c.position == row["read_position"]
                        )
                    )
                elif row["action_id"] is not None:
                    result = await recorded_action_result(connection, row["action_id"])
            observations.append(
                (
                    {
                        "kind": "native_invocation",
                        "invocation_id": str(row["id"]),
                        "tool_id": row["tool_id"],
                        "proposal": row["proposal"],
                        "reply": row["reply_receipt"],
                        "recorded_result": result,
                    },
                    bool(set(row["proposal"]["input_ids"]).intersection(input_ids))
                    or row["action_id"] in action_ids,
                )
            )
    required = tuple(record for record, operative in observations if operative)

    def frame(values: tuple[dict[str, object], ...]) -> PromptSections:
        return PromptSections(
            (
                PromptSection(
                    PromptSectionKind("recorded_tool_observations"),
                    (),
                    PromptJson([*records, *values]),
                ),
            )
        )

    context = frame(required)
    if not fits(context):
        return None
    selected = {record["invocation_id"] for record in required}
    for record, operative in reversed(observations):
        if operative:
            continue
        selected.add(record["invocation_id"])
        candidate = frame(
            tuple(item for item, _ in observations if item["invocation_id"] in selected)
        )
        if not fits(candidate):
            break
        context = candidate
    return context


async def _turn_evidence(owner: JarvisOwner, attempt_id: UUID) -> TurnEvidence:
    evidence = TurnEvidence()
    async with owner.database.connect() as connection:
        rows = (
            await connection.execute(
                select(native_invocation.c.tool_id, read_position.c.result)
                .join(
                    read_position,
                    read_position.c.position == native_invocation.c.read_position,
                )
                .where(native_invocation.c.attempt_id == attempt_id)
                .order_by(native_invocation.c.ordinal)
            )
        ).all()
    for row in rows:
        if row.result is None or row.result.get("type") != "Success":
            continue
        if row.tool_id == "calendar.list_events":
            coverage = CalendarListEventsSuccess.model_validate(
                row.result["value"]
            ).coverage
            evidence.record_calendar_incompleteness(
                reasons=coverage.reasons,
                calendars_discovered=coverage.calendars_discovered,
                calendars_completed=coverage.calendars_completed,
                matched_events=coverage.matched_events,
            )
        elif row.tool_id == "agent.list":
            inventory = AgentListResult.model_validate(row.result["value"])
            if inventory.partial:
                evidence.record_agent_inventory_incompleteness(
                    unavailable_machines=sum(not peer.ok for peer in inventory.peers)
                )
    return evidence


__all__ = [
    "NativeInputs",
    "NativeRunOutcome",
    "NativeRunner",
    "native_receipt_context",
    "recover_native_products",
]
