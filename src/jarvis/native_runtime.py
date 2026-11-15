"""One main native turn; canonical requests and existing receipts survive sessions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from llm_agent_kernel import (
    AppendInputs,
    CancellationToken,
    Checkpoint,
    HostInput,
    HostRef,
    InputId,
    NativeDefect,
    NativeDefinition,
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
from sqlalchemy.dialects.postgresql import array
from universal_memory import MemoryError, render_view

from jarvis.actions import ActionStore, recorded_action_context, recorded_action_result
from jarvis.admission import ExactToolBudgetFactory, JarvisOwner
from jarvis.db import (
    action,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    read_position,
)
from jarvis.definitions import RoleDefinitions
from jarvis.input_framing import host_input
from jarvis.kernel import KernelRuntime
from jarvis.memory_service import MemoryService
from jarvis.memory_workers import MemoryWorker
from jarvis.messages import MessageStore, StoredMessage, causal_component_ids
from jarvis.native_journal import (
    PostgresNativeJournal,
    commit_product,
    park_product,
    recover_sealed_turn,
)
from jarvis.ownership import (
    DeploymentOwnershipDefect,
    lock_conversation,
)
from jarvis.read_positions import PostgresReadRecorder
from jarvis.settings import Settings
from jarvis.terminal import JarvisTerminal
from jarvis.tool_results import completed_tool_result
from jarvis.write_dispatch import WriteToolDispatcher

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NativeRunOutcome:
    status: Literal["no_work", "progressed", "blocked", "stopped"]


def _host_inputs(
    values: tuple[StoredMessage, ...],
    receipts: PromptSections,
    omitted_waiting: int,
) -> tuple[HostInput, ...]:
    inputs = tuple(map(host_input, values))
    first, *rest = inputs
    context = PromptSection(
        PromptSectionKind("request_context"),
        (
            PromptAttribute(
                PromptAttributeName("omitted_waiting_inputs"), str(omitted_waiting)
            ),
        ),
        None,
    )
    return (
        HostInput(
            first.input_id,
            PromptSections((context, *receipts.sections, *first.sections.sections)),
            first.source_timestamp,
        ),
        *rest,
    )


async def _fit_inputs(
    owner: JarvisOwner,
    store: MessageStore,
    definition: NativeDefinition,
    values: tuple[StoredMessage, ...],
    as_of: datetime,
    *,
    prefix: PromptSections,
    exclude_ids: tuple[UUID, ...],
) -> tuple[HostInput, ...] | None:
    while values:
        omitted = await store.waiting_input_count(
            owner.scope_id,
            exclude_ids=(*exclude_ids, *(item.id for item in values)),
        )

        def fits(
            receipts: PromptSections,
            selected: tuple[StoredMessage, ...] = values,
            omitted_count: int = omitted,
        ) -> bool:
            framed = _host_inputs(selected, receipts, omitted_count)
            current = input_batch(
                framed,
                as_of,
                render_source_timestamps=True,
                render_batch_as_of=True,
            )
            return native_request_fits(
                definition,
                PromptSections((*prefix.sections, current)),
            )

        receipts = await native_receipt_context(
            owner,
            input_ids=tuple(InputId(str(item.id)) for item in values),
            fits=fits,
        )
        if receipts is not None:
            return _host_inputs(values, receipts, omitted)
        values = values[:-1]
    return None


class NativeInputs:
    def __init__(
        self,
        *,
        owner: JarvisOwner,
        store: MessageStore,
        plan: FrozenToolPlan,
        definition: NativeDefinition,
        memory_cutoff: int,
        cancellation: CancellationToken,
        maximum_batch_size: int,
    ) -> None:
        self.owner, self.store, self.plan = owner, store, plan
        self.definition = definition
        self.memory_cutoff = memory_cutoff
        self._pending: AppendInputs | None = None
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
        known = tuple(set(known).union(map(UUID, request.input_ids)))
        if self._pending is not None:
            if not all(UUID(item.input_id) in known for item in self._pending.inputs):
                return self._pending
            self._pending = None
        values = await self.store.pending_inputs(
            source_conversation_id=self.owner.scope_id,
            limit=self.maximum_batch_size,
            exclude_ids=known,
        )
        if not values:
            return NoNewInput()
        as_of = datetime.now(UTC)
        inputs = await _fit_inputs(
            self.owner,
            self.store,
            self.definition,
            values,
            as_of,
            prefix=PromptSections(()),
            exclude_ids=known,
        )
        if inputs is None:
            LOGGER.warning("native append blocked: code=request_too_large")
            return NoNewInput()
        self._pending = AppendInputs(
            inputs, Checkpoint(str(inputs[-1].input_id)), as_of
        )
        return self._pending

    async def require_live_request(
        self, lineage: NativeDispatchLineage, request_ref: UUID
    ) -> None:
        await self.owner.require_current(lineage.permit)
        if await self.store.paused(self.owner.scope_id):
            raise NativeDefect("new writes cannot enter while paused")
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
            or row["role"] not in {"owner", "host"}
            or row["control_kind"] is not None
            or row["source_conversation_id"] != self.owner.scope_id
            or row["request_state"] not in {"pending", "waiting"}
            or row["processing_parked_at"] is not None
            or str(request_ref) not in lineage.input_ids
        ):
            raise NativeDefect("write request_ref is outside delivered live inputs")


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
        dispatcher_factory: Callable[
            [NativeInputs, PostgresNativeJournal], WriteToolDispatcher
        ],
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
        )
        if not pending:
            return NativeRunOutcome("no_work")
        plan = self.definitions.plans["main"]
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
        inputs = await _fit_inputs(
            self.owner,
            self.store,
            self.definitions.main,
            pending,
            as_of,
            prefix=source,
            exclude_ids=(),
        )
        if inputs is None:
            LOGGER.warning("native context blocked: code=request_too_large")
            return NativeRunOutcome("blocked")
        current = input_batch(
            inputs,
            as_of,
            render_source_timestamps=True,
            render_batch_as_of=True,
        )
        projected = PromptSections((*source.sections, current))
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
            Checkpoint(str(inputs[-1].input_id)),
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
                definition=self.definitions.main,
                memory_cutoff=cutoff,
                cancellation=cancellation,
                maximum_batch_size=self.settings.maximum_batch_size,
            )
            dispatcher = self.dispatcher_factory(native_inputs, journal)
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
        completed = await commit_product(
            owner.database,
            owner,
            turn,
            final,
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
    await park_product(owner.database, owner, attempt_id, input_ids, reason)


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
    """Keep complete causal recovery facts; optional recent observations fit last."""
    selected_ids = tuple(map(UUID, input_ids))
    async with owner.database.connect() as connection:
        component_ids = await causal_component_ids(connection, selected_ids)
        requests = (
            (
                await connection.execute(
                    select(message)
                    .where(
                        message.c.id.in_(component_ids),
                        message.c.source_conversation_id == owner.scope_id,
                    )
                    .order_by(message.c.created_at, message.c.id)
                )
            )
            .mappings()
            .all()
        )
        stop_attempts = tuple(
            UUID(row["trace"]["native_attempt_id"])
            for row in requests
            if row["request_state"] == "stopped"
            and row["trace"].get("native_attempt_id") is not None
        )
        seals = (
            (
                await connection.execute(
                    select(native_attempt)
                    .where(
                        native_attempt.c.id.in_(stop_attempts),
                        native_attempt.c.conversation_id == owner.scope_id,
                    )
                    .order_by(native_attempt.c.attempt_seq)
                )
            )
            .mappings()
            .all()
        )
        stopped_ids = {
            str(row["id"]) for row in requests if row["request_state"] == "stopped"
        }
        seals = tuple(
            row
            for row in seals
            if row["product_outcome"] is not None
            and row["product_outcome"].get("status") == "committed"
            and any(
                item["disposition"] == "stop" and item["input_id"] in stopped_ids
                for item in row["product_outcome"].get("input_outcomes", ())
            )
        )
        stop_attempts = tuple(row["id"] for row in seals)
        stop_input_ids = set(
            (
                await connection.execute(
                    select(native_input_delivery.c.message_id).where(
                        native_input_delivery.c.attempt_id.in_(stop_attempts)
                    )
                )
            ).scalars()
        )
        for seal in seals:
            stop_input_ids.update(map(UUID, seal["request"]["input_ids"]))
            if seal["product_outcome"].get("response_id") is not None:
                stop_input_ids.add(UUID(seal["product_outcome"]["response_id"]))
        stop_context = (
            (
                await connection.execute(
                    select(message)
                    .where(
                        message.c.source_conversation_id == owner.scope_id,
                        or_(
                            message.c.id.in_(
                                tuple(stop_input_ids.difference(component_ids))
                            ),
                            message.c.control_targets.overlap(list(component_ids)),
                        ),
                    )
                    .order_by(message.c.created_at, message.c.id)
                )
            )
            .mappings()
            .all()
        )
        action_ids = tuple(
            (
                await connection.execute(
                    select(action.c.id)
                    .where(action.c.origin_message_id.in_(component_ids))
                    .order_by(action.c.created_at, action.c.id)
                )
            ).scalars()
        )
        recent = (
            select(native_invocation.c.id)
            .join(native_attempt, native_attempt.c.id == native_invocation.c.attempt_id)
            .where(native_attempt.c.conversation_id == owner.scope_id)
            .order_by(
                native_attempt.c.attempt_seq.desc(), native_invocation.c.ordinal.desc()
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
                                array(tuple(map(str, component_ids)))
                            ),
                            native_invocation.c.action_id.in_(action_ids),
                            native_invocation.c.id.in_(recent),
                        ),
                    )
                    .order_by(native_attempt.c.attempt_seq, native_invocation.c.ordinal)
                )
            )
            .mappings()
            .all()
        )
        records: list[dict[str, object]] = [
            {
                "kind": "canonical_request_context",
                "input_id": str(row["id"]),
                "role": row["role"],
                "source": row["source"],
                "source_timestamp": row["created_at"].isoformat(),
                "observed_at": row["trace"].get("observed_at"),
                "parent_request_id": str(row["parent_request_id"])
                if row["parent_request_id"]
                else None,
                "request_state": row["request_state"],
                "wait_reason": row["wait_reason"],
                "processing_parked_at": row["processing_parked_at"].isoformat()
                if row["processing_parked_at"]
                else None,
                "control_kind": row["control_kind"],
                "trace": row["trace"],
                "text": row["text"],
            }
            for row in (*requests, *stop_context)
            if row["id"] not in selected_ids
        ]
        records.extend(
            {
                "kind": "stop_settlement",
                "attempt_id": str(row["id"]),
                "product_outcome": row["product_outcome"],
            }
            for row in seals
        )
        for identifier in action_ids:
            records.append(await recorded_action_context(connection, identifier))
        observations: list[tuple[dict[str, object], bool]] = []
        component_text_ids = set(map(str, component_ids))
        for row in rows:
            position = row["read_position"] or "native-invocation:" + str(row["id"])
            read = (
                (
                    await connection.execute(
                        select(read_position).where(
                            read_position.c.position == position
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            result = None
            if row["reply_receipt"] is None:
                if read is not None:
                    result = read["result"]
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
                        "read_state": None if read is None else read["state"],
                        "read_contract": None if read is None else read["contract"],
                        "recorded_result": result,
                    },
                    bool(component_text_ids.intersection(row["proposal"]["input_ids"]))
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


__all__ = [
    "NativeInputs",
    "NativeRunOutcome",
    "NativeRunner",
    "native_receipt_context",
    "recover_native_products",
]
