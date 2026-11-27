"""One main native turn; canonical requests and existing receipts survive sessions."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import takewhile
from typing import TYPE_CHECKING, Literal, Protocol, cast
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
    AgentRuntimeError,
    AgentSubmissionRejected,
    AgentTerminal,
    AgentToolUse,
    NativeTerminalEvidence,
    OutputSchemaMismatch,
)
from sqlalchemy import case, func, or_, select, true, update
from sqlalchemy import text as sql_text
from universal_memory import MemoryError, render_ready_view

from jarvis.actions import ActionStore, retired_worker_predicate
from jarvis.admission import ExactToolBudgetFactory, JarvisOwner
from jarvis.codex_config import NATIVE_ROUTES, NativeRoute
from jarvis.db import (
    action,
    active_native_attempt,
    message,
    native_attempt,
    native_input_delivery,
    native_invocation,
    proven_native_delivery,
    read_position,
)
from jarvis.definitions import RoleDefinitions, with_main_provider
from jarvis.home_reads import proposal_presented
from jarvis.input_framing import home_context, host_input
from jarvis.kernel import DeferredRoute, KernelRuntime, RouteSelector, SelectedRoute
from jarvis.memory_service import MemoryService
from jarvis.messages import (
    MessageStore,
    StoredMessage,
    causal_component_ids,
    is_recovery_input,
    latest_control,
)
from jarvis.native_diagnostics import log_native_failure
from jarvis.native_journal import (
    NEON_REFILL_INTERVAL,
    NativeContentDefect,
    NeonOpeningUnavailable,
    PostgresNativeJournal,
    ProductSettlement,
    StaleCatchupInventory,
    StaleNativeProduct,
    commit_product,
    consume_fenced_losses,
    defer_first_sample_refusal,
    fail_native_product,
    native_loss_product,
    never_submitted,
    park_unadmitted_input,
    recover_sealed_turn,
    yield_workspace_input,
)
from jarvis.native_protocol import (
    FOREGROUND_RECOVERY_PROFILE,
    WORKSPACE_CHECK_PROFILE,
)
from jarvis.ownership import (
    DeploymentOwnershipDefect,
    lock_conversation,
)
from jarvis.read_positions import PostgresReadRecorder
from jarvis.receipt_tools import original_read_position, receipt_scope
from jarvis.recovery_catchup import (
    RECOVERY_CATCHUP_SOURCE,
    CatchupStale,
    catchup_mail_ids,
)
from jarvis.settings import Settings
from jarvis.stock_observations import StockObservationWriter
from jarvis.terminal import render_terminal
from jarvis.tool_results import completed_tool_result, memory_view_section
from jarvis.workspace_host import WorkspaceHost, is_workspace_wake

if TYPE_CHECKING:
    from provider_runtime.agent_runtime.neon_control import NeonControl
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

    from jarvis.presence import Presence
    from jarvis.write_dispatch import WriteToolDispatcher

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NativeRunOutcome:
    status: Literal["no_work", "progressed", "blocked", "stopped"]
    retry_at: datetime | None = None
    deferral: DeferredRoute | None = None


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


def _workspace_input(item: StoredMessage) -> bool:
    return (
        is_workspace_wake(item.source, item.text)
        or (item.home or {}).get("workspace_refresh") is not None
    )


def _opening_profile(item: StoredMessage) -> str:
    if is_recovery_input(item):
        return FOREGROUND_RECOVERY_PROFILE
    if _workspace_input(item):
        return WORKSPACE_CHECK_PROFILE
    return "main"


def _ordinary_prefix(values: tuple[StoredMessage, ...]) -> tuple[StoredMessage, ...]:
    return tuple(takewhile(lambda item: _opening_profile(item) == "main", values))


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
    connection: AsyncConnection | None = None,
) -> tuple[tuple[HostInput, ...], PromptSections, NativeRequestFit]:
    while True:
        omitted = await store.waiting_input_count(
            owner.scope_id,
            exclude_ids=(*exclude_ids, *(item.id for item in values)),
            connection=connection,
        )
        receipts = await native_receipt_context(
            owner,
            input_ids=tuple(InputId(str(item.id)) for item in values),
            connection=connection,
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
        accept_steers: bool,
        workspace: WorkspaceHost | None,
    ) -> None:
        self.owner, self.store, self.plan = owner, store, plan
        self.workspace = workspace
        self.owner_preempted = False
        self.definition = definition
        self.memory_cutoff = memory_cutoff
        # The kernel can prepare a steer before submit, but sends it only after
        # this opening request was accepted on the same native turn.
        self._pending: tuple[UUID, ...] = ()
        self._opening_only: set[UUID] = set()
        self.cancellation, self.maximum_batch_size = cancellation, maximum_batch_size
        self.accept_steers = accept_steers

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
            if not self.accept_steers and self.plan.profile.id == "main":
                return NoNewInput()
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
        # The checked session has immutable provider permissions. Leave an
        # interrupting owner request pending for a fresh ordinary session.
        if self.plan.profile.id != "main":
            if (
                values
                and values[0].role == "owner"
                and values[0].request_state == "pending"
            ):
                if self.plan.profile.id == FOREGROUND_RECOVERY_PROFILE:
                    self.owner_preempted = True
                    return Preempt("recovery_owner_steer")
                if await yield_workspace_input(self.owner, request, values[0].id):
                    self.owner_preempted = True
                    return Preempt("workspace_owner_steer")
            return NoNewInput()
        values = _ordinary_prefix(values)
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


class WorkspaceMatchSender(Protocol):
    def __call__(
        self,
        occurrence_id: UUID,
        todo_id: UUID,
        *,
        still_current: Callable[[], Awaitable[bool]],
    ) -> Awaitable[object]: ...


class RecoverAction(Protocol):
    async def __call__(
        self, action_id: UUID, *, allow_queued_execution: bool
    ) -> None: ...


class NativeRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        store: MessageStore,
        opening_reads: AsyncEngine,
        owner: JarvisOwner,
        kernel_runtime: KernelRuntime,
        route_selector: RouteSelector,
        definitions: RoleDefinitions,
        memory: MemoryService,
        dispatcher_factory: Callable[
            [NativeInputs, PostgresNativeJournal], WriteToolDispatcher
        ],
        actions: ActionStore,
        presence: Presence,
        workspace: WorkspaceHost | None = None,
        recover_action: RecoverAction | None = None,
        neon_control: NeonControl | None = None,
        notify_workspace_match: WorkspaceMatchSender | None = None,
    ) -> None:
        self.settings, self.store, self.owner = settings, store, owner
        self.opening_reads = opening_reads
        self.kernel, self.definitions = kernel_runtime, definitions
        self.route_selector = route_selector
        self.memory, self.actions = memory, actions
        self.presence = presence
        self.recover_action, self.neon_control = recover_action, neon_control
        self.workspace, self.notify_workspace_match = workspace, notify_workspace_match
        self.dispatcher_factory = dispatcher_factory
        self._session: ProviderSessionLease | None = None
        self._journal: PostgresNativeJournal | None = None
        self._dispatchers: list[WriteToolDispatcher] = []
        self.notify_delivery: Callable[[], None] = lambda: None
        self.notify_work: Callable[[], None] = lambda: None

    async def record(self, attempt_id: str, message: AgentMessage) -> None:
        if self._journal is None:
            raise NativeDefect("public message has no active native journal")
        if self._journal.plan.profile.id == FOREGROUND_RECOVERY_PROFILE:
            return
        await self._journal.record(attempt_id, message)
        await self.memory.publish()

    async def recover_memory(self) -> None:
        await _recover_native_note_saves(self.owner, self.memory)
        await self.memory.publish()
        await self.memory.recover_stock_observations()
        self.notify_delivery()

    async def run(self, cancellation: CancellationToken) -> NativeRunOutcome:
        self._dispatchers = [item for item in self._dispatchers if item.check_effects()]
        route_selector = (
            None
            if cancellation.cancelled or await self.store.paused(self.owner.scope_id)
            else self.route_selector
        )
        await recover_native_products(
            self.owner,
            route_selector=route_selector,
            workspace=self.workspace,
            recover_action=self.recover_action,
        )
        await self.recover_memory()
        if cancellation.cancelled or await self.store.paused(self.owner.scope_id):
            return NativeRunOutcome("stopped")
        excluded: list[NativeRoute | None] = []
        excluded_inputs: list[UUID] = []
        retry_at: datetime | None = None
        first_deferral = None
        all_deferred = True
        while True:
            pending = await self.store.pending_inputs(
                source_conversation_id=self.owner.scope_id,
                limit=self.settings.maximum_batch_size,
                exclude_ids=tuple(excluded_inputs),
                exclude_retry_routes=tuple(excluded),
            )
            if not pending:
                return NativeRunOutcome(
                    "blocked" if excluded or excluded_inputs else "no_work",
                    retry_at,
                    first_deferral if all_deferred else None,
                )
            await self.owner.require_current(
                self.owner.permit("jarvis-codex-admission")
            )
            if cancellation.cancelled or await self.store.paused(self.owner.scope_id):
                return NativeRunOutcome("stopped")
            first = pending[0]
            if first.role == "host" and first.source == RECOVERY_CATCHUP_SOURCE:
                grant = None if self.workspace is None else self.workspace.enrollment()
                if grant is None:
                    all_deferred = False
                    excluded_inputs.append(first.id)
                    continue
                try:
                    async with self.owner.database.connect() as connection:
                        await catchup_mail_ids(
                            connection,
                            self.owner.scope_id,
                            first.id,
                            grant.account,
                            grant.grant_id,
                        )
                except CatchupStale:
                    if await park_unadmitted_input(
                        self.owner, first.id, "catch-up inventory no longer matches"
                    ):
                        self.notify_delivery()
                        return NativeRunOutcome("progressed")
                    all_deferred = False
                    excluded_inputs.append(first.id)
                    continue
            pinned = _retry_pin(first)
            selected = await self.route_selector.choose_route("main", pinned=pinned)
            if cancellation.cancelled or await self.store.paused(self.owner.scope_id):
                return NativeRunOutcome("stopped")
            if isinstance(selected, DeferredRoute):
                outcome = selected
            else:
                cohort = tuple(item for item in pending if _retry_pin(item) == pinned)
                outcome = await self._run_selected(
                    cohort, selected, pinned, cancellation
                )
            if isinstance(outcome, NativeRunOutcome):
                if outcome.status != "blocked" or retry_at is None:
                    return outcome
                return NativeRunOutcome(
                    "blocked", min(retry_at, outcome.retry_at or retry_at)
                )
            if first_deferral is None:
                first_deferral = self.route_selector.describe_deferral(outcome, pinned)
            deadline = outcome.reset_at
            if deadline is not None and deadline > datetime.now(UTC):
                retry_at = deadline if retry_at is None else min(retry_at, deadline)
            excluded.append(pinned)

    async def _run_selected(
        self,
        pending: tuple[StoredMessage, ...],
        selected: SelectedRoute,
        pinned: NativeRoute | None,
        cancellation: CancellationToken,
    ) -> NativeRunOutcome | DeferredRoute:
        profile = _opening_profile(pending[0])
        match profile:
            case "foreground_recovery":
                template = self.definitions.foreground_recovery
            case "workspace_check":
                template = self.definitions.workspace_check
            case "main":
                template = self.definitions.main
            case _:
                raise NativeDefect("unknown opening profile")
        pending = _ordinary_prefix(pending) if profile == "main" else pending[:1]
        plan = self.definitions.plans[profile]
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
        attempt_id = str(uuid4())
        permit = self.owner.permit("jarvis-native:" + attempt_id)
        definition = with_main_provider(template, selected.provider)
        try:
            async with self.opening_reads.begin() as connection:
                await connection.execute(
                    sql_text(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                    )
                )
                inputs, projected, fit = await fit_native_inputs(
                    self.owner,
                    self.store,
                    definition,
                    pending,
                    as_of,
                    prefix=source,
                    exclude_ids=(),
                    connection=connection,
                )
                if fit.fits:
                    await self.owner.require_current(permit)
                    if cancellation.cancelled or await self.store.paused(
                        self.owner.scope_id
                    ):
                        return NativeRunOutcome("stopped")
                    try:
                        self._session = await self.kernel.provider.acquire_native(
                            definition, plan, permit, None
                        )
                    except (AgentRuntimeError, OSError) as error:
                        self.route_selector.opening_failed(selected.route)
                        LOGGER.warning(
                            "native opening blocked: route=%s type=%s",
                            selected.route,
                            type(error).__name__,
                        )
                        return DeferredRoute.opening_failure(selected.route)
            if fit.overflow is not None:
                actual, limit, unit = fit.overflow
                reason = f"the opening needed {actual} {unit}, limit {limit}"
                parked = await park_unadmitted_input(self.owner, pending[0].id, reason)
                if parked:
                    self.notify_delivery()
                return NativeRunOutcome("progressed" if parked else "blocked")
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
            return await self._run_opened(
                selected,
                definition,
                request,
                cutoff,
                pinned,
                cancellation,
            )
        finally:
            session, self._session = self._session, None
            if session is not None:
                await self.kernel.provider.discard(session)

    async def _run_opened(
        self,
        selected: SelectedRoute,
        definition: NativeDefinition,
        request: NativeRequest,
        cutoff: int,
        pinned: NativeRoute | None,
        cancellation: CancellationToken,
    ) -> NativeRunOutcome | DeferredRoute:
        session = self._session
        if session is None:
            raise NativeDefect("supervision requires an acquired native session")
        attempt_id = request.attempt_id
        plan = request.plan
        profile = plan.profile.id
        protocol_fault = False
        terminal = None
        native_inputs = None
        observations = None
        try:
            try:
                ref = session.session.ref
                if (ref.profile_key, ref.backend, ref.transport) != (
                    selected.route,
                    definition.provider.backend,
                    definition.provider.transport,
                ):
                    raise NativeDefect("acquired session changed the selected route")
                journal = PostgresNativeJournal(
                    self.owner.database,
                    definition=definition,
                    plan=plan,
                    owner=self.owner,
                    memory=self.memory,
                    neon_control=self.neon_control,
                    on_armed=self.presence.arm,
                    workspace_grant=(
                        self.workspace.enrollment()
                        if profile == FOREGROUND_RECOVERY_PROFILE
                        and self.workspace is not None
                        else None
                    ),
                )
                self._journal = journal
                native_inputs = NativeInputs(
                    owner=self.owner,
                    store=self.store,
                    plan=plan,
                    definition=definition,
                    memory_cutoff=cutoff,
                    cancellation=cancellation,
                    maximum_batch_size=self.settings.maximum_batch_size,
                    accept_steers=pinned is None and profile == "main",
                    workspace=self.workspace,
                )
                dispatcher = self.dispatcher_factory(native_inputs, journal)
                dispatcher.on_effect_settled = self.notify_work
                self._dispatchers.append(dispatcher)
                if self.memory.jarvis_admitted:
                    observations = StockObservationWriter(
                        self.memory, str(self.owner.token), UUID(attempt_id)
                    )

                def stock_tool(event: AgentToolUse) -> None:
                    self.presence.stock(event)
                    if observations is not None:
                        observations.offer(event)

                terminal = await run_native(
                    definition=definition,
                    request=request,
                    provider=self.kernel.provider,
                    session=session,
                    owner=self.owner,
                    journal=journal,
                    inputs=native_inputs,
                    dispatch=dispatcher,
                    budgets=ExactToolBudgetFactory(),
                    messages=self,
                    cancellation=cancellation,
                    on_stock_tool=stock_tool,
                )
            except DeploymentOwnershipDefect:
                raise
            except (NativeUncertain, NativeSubmissionConflict):
                terminal = None
            except NeonOpeningUnavailable:
                self.route_selector.opening_failed(selected.route)
                LOGGER.warning("paid native control unavailable before submission")
                return DeferredRoute.opening_failure(selected.route)
            except StaleCatchupInventory:
                parked = await park_unadmitted_input(
                    self.owner,
                    UUID(request.input_ids[0]),
                    "catch-up inventory no longer matches",
                )
                return NativeRunOutcome("progressed" if parked else "blocked")
            except NativeDefect as error:
                log_native_failure(LOGGER, error, attempt_id=attempt_id, boundary="run")
                terminal = None
                protocol_fault = True
            if await self.store.paused(self.owner.scope_id):
                await recover_native_products(
                    self.owner,
                    workspace=self.workspace,
                    recover_action=self.recover_action,
                )
                return NativeRunOutcome("stopped")
            if cancellation.cancelled:
                return NativeRunOutcome("stopped")
            journal = self._journal
            refusal = None if journal is None else await journal.close_neon(attempt_id)
            if cancellation.cancelled:
                return NativeRunOutcome("stopped")
            if journal is not None and refusal is not None:
                session, self._session = self._session, None
                if session is not None:
                    await self.kernel.provider.discard(session)
                await journal.fence(attempt_id, "neon_first_sample_refused")
                deferred = await defer_first_sample_refusal(
                    self.owner, attempt_id, refusal
                )
                if deferred is not None:
                    # Recheck admission on the next pass. Personal may have reset.
                    return NativeRunOutcome("progressed")
            if (
                terminal is None
                or isinstance(terminal, AgentNotSubmitted | AgentSubmissionRejected)
                or not isinstance(terminal.evidence, NativeTerminalEvidence)
            ):
                result = await _settle_failed_opening(
                    self.owner,
                    request,
                    protocol_fault,
                    route_selector=self.route_selector,
                    workspace=self.workspace,
                    recover_action=self.recover_action,
                )
            else:
                try:
                    result = await _settle_native_product(
                        self.owner,
                        attempt_id,
                        workspace=self.workspace,
                        recover_action=self.recover_action,
                    )
                except Exception as error:
                    log_native_failure(
                        LOGGER, error, attempt_id=attempt_id, boundary="terminal"
                    )
                    raise
            match = result.workspace_match
            if (
                match is not None
                and self.workspace is not None
                and self.notify_workspace_match is not None
            ):
                workspace = self.workspace

                async def still_current() -> bool:
                    return await workspace.match_current(
                        match.occurrence_id, match.work_id
                    )

                try:
                    await self.notify_workspace_match(
                        match.occurrence_id, match.work_id, still_current=still_current
                    )
                except DeploymentOwnershipDefect:
                    raise
                except Exception:
                    LOGGER.warning(
                        "workspace match delivery failed: occurrence=%s",
                        match.occurrence_id,
                    )
            progressed = (
                result.status == "committed"
                or result.eligibility_changed
                or (native_inputs is not None and native_inputs.owner_preempted)
            )
            return NativeRunOutcome("progressed" if progressed else "blocked")
        finally:
            journal, self._journal = self._journal, None
            session, self._session = self._session, None
            drain_deadline = (
                asyncio.get_running_loop().time()
                + definition.control.interrupt_grace_seconds
            )
            try:
                try:
                    if journal is not None:
                        await journal.close_neon(attempt_id)
                finally:
                    if session is not None:
                        await self.kernel.provider.discard(session)
                await self.memory.publish()
                self.notify_delivery()
            finally:
                if observations is not None:
                    complete = isinstance(
                        terminal, AgentNotSubmitted | AgentSubmissionRejected
                    ) or (
                        isinstance(terminal, AgentTerminal)
                        and isinstance(terminal.evidence, NativeTerminalEvidence)
                        and terminal.status == "succeeded"
                        and not cancellation.cancelled
                    )
                    await observations.close(drain_deadline, incomplete=not complete)

    async def close(self) -> None:
        for dispatcher in self._dispatchers:
            await dispatcher.close()
        if self._session is not None:
            await self.kernel.provider.discard(self._session)
            self._session = None


def _retry_pin(value: StoredMessage) -> NativeRoute | None:
    if value.native_retry_after is None:
        return None
    stored = value.trace.get("native_retry")
    if not isinstance(stored, dict):
        raise NativeDefect("a due retry has no prepared route evidence")
    retry = cast(dict[str, object], stored)
    route = retry.get("route")
    if not isinstance(retry.get("attempt_id"), str) or route not in NATIVE_ROUTES:
        raise NativeDefect("a due retry has no original route")
    match retry.get("selection"):
        case "fresh":
            return None
        case "pinned":
            return route
        case _:
            raise NativeDefect("a due retry has an unknown selection")


async def _confirm_unsubmitted_quota(
    owner: JarvisOwner, route_selector: RouteSelector, *, attempt_id: UUID | None = None
) -> frozenset[UUID]:
    query = select(
        native_attempt.c.id, native_attempt.c.request["route"].as_string()
    ).where(
        native_attempt.c.conversation_id == owner.scope_id,
        native_attempt.c.fenced_at.is_not(None),
        native_attempt.c.recovery_pending,
        native_attempt.c.terminal_at.is_(None),
        never_submitted,
    )
    if attempt_id is not None:
        query = query.where(native_attempt.c.id == attempt_id)
    async with owner.database.connect() as connection:
        rows = (await connection.execute(query)).all()
    confirmed: set[UUID] = set()
    for identifier, route in rows:
        if route not in NATIVE_ROUTES:
            raise NativeDefect("unsubmitted attempt lacks its prepared route")
        if await route_selector.included_exhausted(route):
            confirmed.add(identifier)
    return frozenset(confirmed)


async def _settle_failed_opening(
    owner: JarvisOwner,
    request: NativeRequest,
    protocol_fault: bool,
    *,
    route_selector: RouteSelector,
    workspace: WorkspaceHost | None,
    recover_action: RecoverAction | None,
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
        return await _settle_native_product(
            owner,
            request.attempt_id,
            recovering=True,
            workspace=workspace,
            recover_action=recover_action,
        )
    confirmed = await _confirm_unsubmitted_quota(
        owner, route_selector, attempt_id=identifier
    )
    if row is not None:
        await _recover_entered_actions(owner, recover_action, attempt_id=identifier)
    return await consume_fenced_losses(
        owner,
        attempt_id=identifier,
        confirmed_unsubmitted_quota=confirmed,
    )


async def recover_native_products(
    owner: JarvisOwner,
    *,
    route_selector: RouteSelector | None = None,
    workspace: WorkspaceHost | None = None,
    recover_action: RecoverAction | None = None,
    settle_losses: bool = True,
) -> tuple[UUID, ...]:
    """Fence abandoned authority, drain original seals, then account for lost turns."""
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        fenced = (
            await connection.scalar(
                update(native_attempt)
                .where(
                    native_attempt.c.conversation_id == owner.scope_id,
                    active_native_attempt,
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
                        select(
                            native_attempt.c.id,
                            native_loss_product.label("lost"),
                            native_attempt.c.local_outcome["neon_refusal"]["reason"]
                            .as_string()
                            .label("neon_refused"),
                        )
                        .where(
                            native_attempt.c.conversation_id == owner.scope_id,
                            native_attempt.c.terminal_at.is_not(None),
                            native_attempt.c.product_outcome.is_(None),
                            true()
                            if settle_losses
                            else native_attempt.c.terminal["status"].as_string()
                            == "succeeded",
                        )
                        .order_by(native_attempt.c.attempt_seq)
                        .limit(1)
                    )
                ).one_or_none()
            if row is None:
                break
            identifier = row.id
            try:
                if row.neon_refused:
                    result = await _mark_stale(
                        owner, identifier, "neon_" + row.neon_refused
                    )
                elif row.lost:
                    await _recover_entered_actions(
                        owner, recover_action, attempt_id=identifier
                    )
                    result = await consume_fenced_losses(owner, attempt_id=identifier)
                else:
                    result = await _settle_native_product(
                        owner,
                        str(identifier),
                        recovering=True,
                        workspace=workspace,
                        recover_action=recover_action,
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
        if settle_losses:
            await _recover_entered_actions(owner, recover_action)
            confirmed = (
                None
                if route_selector is None
                else await _confirm_unsubmitted_quota(owner, route_selector)
            )
            await consume_fenced_losses(owner, confirmed_unsubmitted_quota=confirmed)
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


async def _recover_entered_actions(
    owner: JarvisOwner,
    recover_action: RecoverAction | None,
    *,
    attempt_id: UUID | None = None,
) -> None:
    if recover_action is None:
        return
    query = (
        select(action.c.id)
        .join(native_invocation, native_invocation.c.action_id == action.c.id)
        .join(native_attempt, native_attempt.c.id == native_invocation.c.attempt_id)
        .where(
            native_attempt.c.conversation_id == owner.scope_id,
            native_attempt.c.fenced_at.is_not(None),
            native_attempt.c.product_outcome.is_(None),
            action.c.status == "executing",
        )
        .distinct()
    )
    if attempt_id is not None:
        query = query.where(native_attempt.c.id == attempt_id)
    async with owner.database.connect() as connection:
        originals = (await connection.scalars(query)).all()
    for identifier in originals:
        await recover_action(identifier, allow_queued_execution=False)


async def neon_paid_ready(
    owner: JarvisOwner, control: NeonControl
) -> DeferredRoute | None:
    """Coalesce refill probes on the original refusal row."""
    now = datetime.now(UTC)
    if not await control.available():
        return DeferredRoute("google_neon", "route_unavailable", now)
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        if await connection.scalar(latest_control(owner.scope_id)) == "pause":
            return DeferredRoute("google_neon", "owner_paused", now)
        row = (
            await connection.execute(
                select(native_attempt.c.id, native_attempt.c.local_outcome)
                .where(
                    native_attempt.c.conversation_id == owner.scope_id,
                    native_attempt.c.local_outcome.has_key("neon_capacity"),
                )
                .order_by(native_attempt.c.attempt_seq.desc())
                .limit(1)
                .with_for_update()
            )
        ).one_or_none()
        if row is None:
            return None
        local = row.local_outcome
        evidence = local["neon_capacity"]
        if evidence["status"] == "ready":
            return None
        check_after = datetime.fromisoformat(evidence["check_after"])
        if check_after > now:
            return DeferredRoute("google_neon", evidence["status"], now, check_after)
        if not evidence["requires_billing_probe"]:
            return None
        next_check = now + NEON_REFILL_INTERVAL
        await connection.execute(
            update(native_attempt)
            .where(native_attempt.c.id == row.id)
            .values(
                local_outcome={
                    **local,
                    "neon_capacity": {
                        **evidence,
                        "check_after": next_check.isoformat(),
                    },
                }
            )
        )
    probe = await control.probe()
    check_after = now + max(
        NEON_REFILL_INTERVAL, timedelta(seconds=probe.retry_after or 0)
    )
    async with owner.database.begin() as connection:
        await lock_conversation(connection, owner.scope_id)
        await connection.execute(
            update(native_attempt)
            .where(
                native_attempt.c.id == row.id,
                native_attempt.c.local_outcome["neon_capacity"][
                    "check_after"
                ].as_string()
                == next_check.isoformat(),
            )
            .values(
                local_outcome=native_attempt.c.local_outcome.op("||")(
                    {
                        "neon_capacity": {
                            "status": probe.status,
                            "requires_billing_probe": True,
                            "check_after": check_after.isoformat(),
                        }
                    }
                )
            )
        )
    return (
        None
        if probe.status == "ready"
        else DeferredRoute("google_neon", probe.status, now, check_after)
    )


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
    workspace: WorkspaceHost | None = None,
    recover_action: RecoverAction | None = None,
) -> ProductSettlement:
    async with owner.database.connect() as connection:
        turn = await recover_sealed_turn(connection, owner.scope_id, attempt_id)
    if turn is None:
        raise NativeDefect("product settlement lacks a sealed native terminal")
    if turn.terminal.status != "succeeded":
        await _recover_entered_actions(
            owner, recover_action, attempt_id=UUID(attempt_id)
        )
        return await fail_native_product(
            owner,
            attempt_id,
            turn.input_ids,
            turn.terminal.failure,
            initial_delivery_proven=turn.initial_delivery_proven,
        )
    try:
        final = turn.decode_final()
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
            owner.database,
            owner,
            turn,
            final,
            rendered,
            recovering=recovering,
            workspace=workspace,
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
    connection: AsyncConnection | None = None,
) -> PromptSections:
    """Frame operative facts and the inventory of recorded observations."""
    selected_ids = tuple(map(UUID, input_ids))
    async with (
        owner.database.connect()
        if connection is None
        else nullcontext(connection) as connection
    ):
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
