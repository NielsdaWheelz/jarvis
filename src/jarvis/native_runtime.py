"""One main native turn; canonical requests and existing receipts survive sessions."""

from __future__ import annotations

import logging
from collections import Counter
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
    NativeRequestFit,
    NativeSubmissionConflict,
    NativeUncertain,
    NoNewInput,
    Preempt,
    ProviderSessionLease,
    input_batch,
    native_request_fit,
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
    ReplayPolicy,
    raw_input_digest,
)
from provider_runtime.agent_runtime import (
    AgentMessage,
    AgentNotSubmitted,
    AgentSubmissionRejected,
    NativeTerminalEvidence,
    OutputSchemaMismatch,
    decode_agent_output,
    thaw_json_value,
)
from sqlalchemy import case, func, or_, select, update
from universal_memory import MemoryError, render_ready_view

from jarvis.actions import ActionStore, retired_worker_predicate
from jarvis.admission import ExactToolBudgetFactory, JarvisOwner
from jarvis.db import (
    action,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    proven_native_delivery,
    read_position,
)
from jarvis.definitions import RoleDefinitions
from jarvis.home_reads import proposal_presented
from jarvis.input_framing import home_context, host_input
from jarvis.kernel import KernelRuntime
from jarvis.memory_service import MemoryService
from jarvis.messages import (
    MessageStore,
    StoredMessage,
    causal_component_ids,
    latest_control,
)
from jarvis.native_diagnostics import log_native_failure
from jarvis.native_journal import (
    NativeContentDefect,
    PostgresNativeJournal,
    ProductSettlement,
    StaleNativeProduct,
    commit_product,
    consume_fenced_losses,
    fail_native_product,
    native_loss_product,
    park_oversized_input,
    recover_sealed_turn,
)
from jarvis.ownership import (
    DeploymentOwnershipDefect,
    lock_conversation,
)
from jarvis.read_positions import PostgresReadRecorder
from jarvis.receipt_tools import original_read_position, receipt_scope
from jarvis.settings import Settings
from jarvis.terminal import JarvisTerminal, render_terminal
from jarvis.tool_results import completed_tool_result, memory_view_section
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


async def opening_memory_prefix(memory: MemoryService) -> tuple[int, PromptSections]:
    view = await memory.library.ready_view()
    return view.admitted_through, PromptSections(
        (memory_view_section(render_ready_view(view)),)
    )


async def fit_native_inputs(
    owner: JarvisOwner,
    store: MessageStore,
    definition: NativeDefinition,
    values: tuple[StoredMessage, ...],
    as_of: datetime,
    *,
    prefix: PromptSections,
    exclude_ids: tuple[UUID, ...],
    steer: bool = False,
) -> tuple[tuple[HostInput, ...], PromptSections, NativeRequestFit]:
    while True:
        omitted = await store.waiting_input_count(
            owner.scope_id,
            exclude_ids=(*exclude_ids, *(item.id for item in values)),
        )
        receipts = await native_receipt_context(
            owner, input_ids=tuple(InputId(str(item.id)) for item in values)
        )
        framed = _host_inputs(values, receipts, omitted)
        current = input_batch(
            framed, as_of, render_source_timestamps=True, render_batch_as_of=True
        )
        projected = PromptSections((*prefix.sections, current))
        fit = native_request_fit(
            definition,
            projected,
            operation="steer" if steer else "start",
        )
        if fit.fits or len(values) == 1:
            return framed, projected, fit
        values = values[:-1]


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
        # The kernel can prepare a steer before submit, but sends it only after
        # this opening request was accepted on the same native turn.
        self._pending: tuple[UUID, ...] = ()
        self._opening_only: set[UUID] = set()
        self.cancellation, self.maximum_batch_size = cancellation, maximum_batch_size

    async def poll(self, request: NativeRequest, through_checkpoint: Checkpoint | None):
        del through_checkpoint
        if self.cancellation.cancelled or await self.store.paused(self.owner.scope_id):
            return Preempt("owner_stop")
        async with self.owner.database.connect() as connection:
            attempt = (
                (
                    await connection.execute(
                        select(
                            native_attempt.c.owner_epoch, native_attempt.c.fenced_at
                        ).where(native_attempt.c.id == UUID(request.attempt_id))
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
            deliveries = {
                row.message_id: row.state
                for row in await connection.execute(
                    select(
                        native_input_delivery.c.message_id,
                        native_input_delivery.c.state,
                    ).where(
                        native_input_delivery.c.attempt_id == UUID(request.attempt_id)
                    )
                )
            }
        if self._pending:
            if any(
                deliveries.get(i) not in {"recorded", "rejected"} for i in self._pending
            ):
                return NoNewInput()
            self._pending = ()
        known = tuple(
            self._opening_only.union(deliveries, map(UUID, request.input_ids))
        )
        values = await self.store.pending_inputs(
            source_conversation_id=self.owner.scope_id,
            limit=self.maximum_batch_size,
            exclude_ids=known,
            steer=True,
        )
        if not values:
            return NoNewInput()
        as_of = datetime.now(UTC)
        inputs, _, size = await fit_native_inputs(
            self.owner,
            self.store,
            self.definition,
            values,
            as_of,
            prefix=PromptSections(()),
            exclude_ids=known,
            steer=True,
        )
        if not size.fits:
            self._opening_only.add(values[0].id)
            return NoNewInput()
        self._pending = tuple(UUID(item.input_id) for item in inputs)
        return AppendInputs(inputs, Checkpoint(str(inputs[-1].input_id)), as_of)

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
        dispatcher_factory: Callable[
            [NativeInputs, PostgresNativeJournal], WriteToolDispatcher
        ],
        actions: ActionStore,
    ) -> None:
        self.settings, self.store, self.owner = settings, store, owner
        self.kernel, self.definitions = kernel_runtime, definitions
        self.memory, self.actions = memory, actions
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

    async def recover_memory(self) -> None:
        await _recover_native_note_saves(self.owner, self.memory)
        await self.memory.publish()
        self.notify_delivery()

    async def run(self, cancellation: CancellationToken) -> NativeRunOutcome:
        self._dispatchers = [item for item in self._dispatchers if item.check_effects()]
        await recover_native_products(self.owner)
        await self.recover_memory()
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
            cutoff, source = await opening_memory_prefix(self.memory)
        except MemoryError as error:
            LOGGER.warning("memory preparation blocked: code=%s", error.code)
            return NativeRunOutcome("blocked")
        if cancellation.cancelled:
            return NativeRunOutcome("stopped")
        as_of = datetime.now(UTC)
        inputs, projected, size = await fit_native_inputs(
            self.owner,
            self.store,
            self.definitions.main,
            pending,
            as_of,
            prefix=source,
            exclude_ids=(),
        )
        if not size.fits:
            actual, limit, unit = size.actual_chars, size.max_chars, "characters"
            if actual <= limit:
                actual, limit, unit = size.wire_bytes, size.max_bytes, "wire bytes"
            reason = f"the opening needed {actual} {unit}, limit {limit}"
            parked = await park_oversized_input(self.owner, pending[0].id, reason)
            if parked:
                self.notify_delivery()
            return NativeRunOutcome("progressed" if parked else "blocked")
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
        protocol_fault = False
        try:
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
            except DeploymentOwnershipDefect:
                raise
            except (NativeUncertain, NativeSubmissionConflict):
                terminal = None
            except NativeDefect as error:
                log_native_failure(LOGGER, error, attempt_id=attempt_id, boundary="run")
                terminal = None
                protocol_fault = True
            if await self.store.paused(self.owner.scope_id):
                await recover_native_products(self.owner)
                return NativeRunOutcome("stopped")
            if cancellation.cancelled:
                return NativeRunOutcome("stopped")
            if (
                terminal is None
                or isinstance(terminal, AgentNotSubmitted | AgentSubmissionRejected)
                or not isinstance(terminal.evidence, NativeTerminalEvidence)
            ):
                result = await _settle_failed_opening(
                    self.owner, request, protocol_fault
                )
            else:
                try:
                    result = await _settle_native_product(self.owner, attempt_id)
                except Exception as error:
                    log_native_failure(
                        LOGGER, error, attempt_id=attempt_id, boundary="terminal"
                    )
                    raise
            progressed = result.status == "committed" or result.eligibility_changed
            return NativeRunOutcome("progressed" if progressed else "blocked")
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


async def _settle_failed_opening(
    owner: JarvisOwner, request: NativeRequest, protocol_fault: bool
) -> ProductSettlement:
    identifier = UUID(request.attempt_id)
    async with owner.database.connect() as connection:
        row = (
            await connection.execute(
                select(native_attempt.c.terminal_at, native_loss_product).where(
                    native_attempt.c.id == identifier,
                    native_attempt.c.conversation_id == owner.scope_id,
                )
            )
        ).one_or_none()
    if row is None and protocol_fault:
        return await fail_native_product(
            owner,
            request.attempt_id,
            request.input_ids,
            "native protocol requires repair",
        )
    if row is not None and row[0] is not None and not row[1]:
        return await _settle_native_product(owner, request.attempt_id, recovering=True)
    return await consume_fenced_losses(owner, attempt_id=identifier)


async def recover_native_products(owner: JarvisOwner) -> tuple[UUID, ...]:
    """Fence abandoned authority, drain original seals, then account for lost turns."""
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        fenced = (
            await connection.scalar(
                update(native_attempt)
                .where(
                    native_attempt.c.conversation_id == owner.scope_id,
                    native_attempt.c.fenced_at.is_(None),
                    native_attempt.c.product_outcome.is_(None),
                )
                .values(fenced_at=func.now())
                .returning(native_attempt.c.id)
            )
        ) is not None
    completed: list[UUID] = []
    counts: Counter[str] = Counter()
    try:
        while True:
            async with owner.database.connect() as connection:
                row = (
                    await connection.execute(
                        select(native_attempt.c.id, native_loss_product)
                        .where(
                            native_attempt.c.conversation_id == owner.scope_id,
                            native_attempt.c.terminal_at.is_not(None),
                            native_attempt.c.product_outcome.is_(None),
                        )
                        .order_by(native_attempt.c.attempt_seq)
                        .limit(1)
                    )
                ).one_or_none()
            if row is None:
                break
            identifier, lost = row
            try:
                if lost:
                    result = await consume_fenced_losses(owner, attempt_id=identifier)
                else:
                    result = await _settle_native_product(
                        owner, str(identifier), recovering=True
                    )
            except Exception as error:
                log_native_failure(
                    LOGGER, error, attempt_id=str(identifier), boundary="terminal"
                )
                error.add_note(f"recovering sealed native attempt {identifier}")
                raise
            if result.status is not None:
                counts[result.status] += 1
            completed.extend(result.completed)
        await consume_fenced_losses(owner)
    finally:
        if fenced or counts:
            LOGGER.info(
                "native recovery: fenced=%d committed=%d failed=%d stale=%d",
                int(fenced),
                counts["committed"],
                counts["failed"],
                counts["stale"],
            )
    return tuple(completed)


async def _mark_stale(
    owner: JarvisOwner, attempt_id: UUID, reason: str
) -> ProductSettlement:
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        updated = await connection.scalar(
            update(native_attempt)
            .where(
                native_attempt.c.id == attempt_id,
                native_attempt.c.terminal_at.is_not(None),
                native_attempt.c.product_outcome.is_(None),
            )
            .values(
                product_outcome={"status": "stale", "reason": reason},
                recovery_pending=False,
            )
            .returning(native_attempt.c.id)
        )
    return ProductSettlement("stale" if updated is not None else None)


async def _settle_native_product(
    owner: JarvisOwner,
    attempt_id: str,
    *,
    recovering: bool = False,
) -> ProductSettlement:
    turn = await recover_sealed_turn(owner.database, owner, attempt_id)
    if turn is None:
        raise NativeDefect("product settlement lacks a sealed native terminal")
    if turn.terminal.status != "succeeded":
        return await fail_native_product(
            owner,
            attempt_id,
            turn.input_ids,
            turn.terminal.failure,
        )
    if turn.output is None:
        raise NativeDefect("original output schema is absent")
    try:
        value = decode_agent_output(turn.output, turn.terminal)
        final = JarvisTerminal.from_seal(turn.output.name, thaw_json_value(value))
        rendered = render_terminal(final)
    except (TypeError, ValueError, OutputSchemaMismatch) as error:
        log_native_failure(LOGGER, error, attempt_id=attempt_id, boundary="terminal")
        return await fail_native_product(
            owner,
            attempt_id,
            turn.input_ids,
            "the final response did not meet its content contract",
        )
    try:
        return await commit_product(
            owner.database, owner, turn, final, rendered, recovering=recovering
        )
    except NativeContentDefect as error:
        log_native_failure(LOGGER, error, attempt_id=attempt_id, boundary="terminal")
        return await fail_native_product(
            owner, attempt_id, turn.input_ids, "native protocol requires repair"
        )
    except StaleNativeProduct:
        return await _mark_stale(owner, UUID(attempt_id), "request_authority_changed")


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
) -> PromptSections:
    """Frame operative facts and the inventory of recorded observations."""
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
                    select(
                        native_attempt.c.id,
                        native_attempt.c.product_outcome,
                        native_attempt.c.request["input_ids"].label("input_ids"),
                    )
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
                        native_input_delivery.c.attempt_id.in_(stop_attempts),
                        proven_native_delivery,
                    )
                )
            ).scalars()
        )
        for seal in seals:
            stop_input_ids.update(map(UUID, seal["input_ids"]))
            if seal["product_outcome"].get("response_id") is not None:
                stop_input_ids.add(UUID(seal["product_outcome"]["response_id"]))
        stop_context = (
            (
                await connection.execute(
                    select(message)
                    .where(
                        message.c.source_conversation_id == owner.scope_id,
                        message.c.id.not_in(component_ids),
                        or_(
                            message.c.id.in_(stop_input_ids),
                            message.c.control_targets.overlap(list(component_ids)),
                            message.c.id
                            == latest_control(owner.scope_id)
                            .with_only_columns(message.c.id)
                            .correlate(None)
                            .scalar_subquery(),
                        ),
                    )
                    .order_by(message.c.created_at, message.c.id)
                )
            )
            .mappings()
            .all()
        )
        records: list[dict[str, object]] = [
            {
                "kind": "canonical_request_context",
                "delivery": "context_only",
                "message_id": str(row["id"]),
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
                **home_context(row["home"]),
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
        retired = retired_worker_predicate(
            action.c.tool_name,
            action.c.execution_contract["implementation_revision"].as_string(),
        )
        action_ids: list[str] = []
        for row in await connection.execute(
            select(
                action.c.id,
                action.c.tool_name,
                action.c.origin_message_id,
                action.c.status,
                action.c.attempts,
                case(
                    (
                        action.c.status == "awaiting_approval",
                        proposal_presented(owner.scope_id),
                    ),
                ).label("presented"),
                case(
                    (
                        or_(
                            retired,
                            action.c.execution_contract["schema_version"]
                            .as_string()
                            .is_(None),
                        ),
                        None,
                    ),
                    else_=action.c.arguments,
                ).label("arguments"),
            )
            .where(action.c.origin_message_id.in_(component_ids))
            .order_by(action.c.created_at, action.c.id)
        ):
            action_ids.append(str(row.id))
            records.append(
                dict(
                    kind="accepted_action",
                    action_ref=str(row.id),
                    request_ref=str(row.origin_message_id),
                    tool_id=row.tool_name,
                    status=row.status,
                    attempts=row.attempts,
                    arguments=row.arguments,
                    **(
                        {"presented": row.presented}
                        if row.presented is not None
                        else {}
                    ),
                )
            )
        joined = native_invocation.join(
            native_attempt, native_attempt.c.id == native_invocation.c.attempt_id
        )
        scope = receipt_scope(owner.scope_id, component_ids)
        # An owner can decide a commitment from a separate request. Either fact
        # leads to the same immutable local receipt, including after replay.
        reply = native_invocation.c.reply_receipt
        decision = reply["result"]["value"]
        approvals = await connection.scalars(
            select(decision)
            .select_from(joined)
            .where(
                native_attempt.c.conversation_id == owner.scope_id,
                native_invocation.c.tool_id == "approval.respond",
                reply["type"].as_string() == "local_result",
                reply["result"]["type"].as_string() == "Success",
                or_(
                    decision["action_id"].as_string().in_(action_ids),
                    decision["owner_message_id"]
                    .as_string()
                    .in_(tuple(map(str, component_ids))),
                ),
            )
            .distinct()
            .order_by(decision)
        )
        records.extend(
            {"kind": "approval_decision", **approval} for approval in approvals
        )
        counts = await connection.execute(
            select(native_invocation.c.tool_id, func.count())
            .select_from(joined)
            .where(*scope)
            .group_by(native_invocation.c.tool_id)
            .order_by(native_invocation.c.tool_id)
        )
        records.append(
            {
                "kind": "receipt_inventory",
                "counts": dict(counts.tuples().all()),
                "lookup": (
                    "use receipt.read with a delivered request_ref to page and open "
                    "originals. inventory counts do not establish coverage."
                ),
            }
        )
        for row in await connection.execute(
            select(
                native_invocation.c.id,
                native_invocation.c.tool_id,
                native_invocation.c.proposal["arguments"].label("arguments"),
                read_position.c.state,
            )
            .select_from(joined.join(read_position, original_read_position()))
            .where(
                *scope,
                read_position.c.state.in_(("dispatched", "uncertain")),
                read_position.c.contract["replay_policy"].as_string()
                == ReplayPolicy.BilledOnce.value,
            )
            .order_by(native_attempt.c.attempt_seq, native_invocation.c.ordinal)
        ):
            records.append(
                dict(
                    kind="unresolved_paid_read",
                    invocation_id=str(row.id),
                    tool_id=row.tool_id,
                    state=row.state,
                    arguments=row.arguments,
                )
            )
    return PromptSections(
        (
            PromptSection(
                PromptSectionKind("recorded_tool_observations"), (), PromptJson(records)
            ),
        )
    )


__all__ = [
    "NativeInputs",
    "NativeRunOutcome",
    "NativeRunner",
    "fit_native_inputs",
    "native_receipt_context",
    "opening_memory_prefix",
    "recover_native_products",
]
