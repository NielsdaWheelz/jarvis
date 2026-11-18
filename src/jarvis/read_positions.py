"""Durable llm-tools Read positions, separate from recoverable Write actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from llm_agent_kernel import (
    DispatchCompleted,
    HostRef,
    InitialReadDispatchLineage,
    NativeDispatchLineage,
    RunId,
    ToolDispatchLineage,
)
from llm_tools import (
    BudgetState,
    FrozenToolPlan,
    InvocationPosition,
    ParsedJson,
    PositionState,
    RecoveryRequired,
    ReplayPolicy,
    Reservation,
    Settlement,
    ToolBinding,
    ToolEffect,
    ToolId,
    ToolResult,
    WebSearchInput,
    WebSearchSourceOperation,
    canonical_json_bytes,
    raw_input_digest,
    validate_tool_input,
)
from llm_tools.schema import JsonObject
from sqlalchemy import RowMapping, select, update
from sqlalchemy.dialects.postgresql import insert

from jarvis.attachment_tools import ATTACHMENT_READ_IDS
from jarvis.db import (
    message,
    model_decision,
    native_attempt,
    native_invocation,
    read_position,
)
from jarvis.event_tools import EVENT_READ_IDS
from jarvis.messages import causal_component_ids
from jarvis.ownership import Database, DeploymentOwnershipDefect, lock_conversation
from jarvis.tool_results import completed_tool_result
from jarvis.work_tools import WORK_READ_IDS

if TYPE_CHECKING:
    from jarvis.memory_service import MemoryService


# New callbacks observe current files/pages; exact native callbacks still replay.
FRESH_READ_IDS = (
    WORK_READ_IDS
    | EVENT_READ_IDS
    | ATTACHMENT_READ_IDS
    | {
        ToolId("gmail.search"),
        ToolId("gmail.list_thread_messages"),
        ToolId("gmail.list_attachments"),
        ToolId("gmail.read_message"),
        ToolId("calendar.list_calendars"),
        ToolId("calendar.read_calendar"),
        ToolId("calendar.list_events"),
        ToolId("calendar.get_event"),
        ToolId("web.read"),
    }
)


class PostgresReadRecorder:
    def __init__(
        self,
        database: Database,
        *,
        web_source_operation: Callable[[WebSearchInput], JsonObject | None]
        | None = None,
    ) -> None:
        self._database = database
        self._reserved: dict[InvocationPosition, tuple[Reservation, bool]] = {}
        self._web_source_operation = web_source_operation
        self._web_operations: dict[InvocationPosition, JsonObject | None] = {}

    @property
    def durable(self) -> bool:
        return True

    async def recover_committed_note_save(
        self,
        *,
        position: InvocationPosition,
        arguments: dict[str, Any],
        contract: dict[str, str],
        memory: MemoryService,
    ) -> ToolResult | None:
        """Settle an original committed local note; absence permits no execution."""
        if (
            not str(position).startswith("native-invocation:")
            or contract["tool_id"] != "memory.save_note"
            or contract["replay_policy"] != ReplayPolicy.ReDispatchable.value
        ):
            raise ValueError("note recovery requires its original local position")
        async with self._database.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(read_position).where(
                            read_position.c.position == str(position)
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        if row["contract"] != contract:
            raise ValueError("local note invocation contract changed")
        if row["state"] == "completed":
            return cast(ToolResult, row["result"])
        receipt = await memory.recover_main_note(arguments["text"], str(position))
        if receipt is None:
            return None
        if row["reservation"] is None:
            raise ValueError("a committed note has no original reservation")
        reservation = Reservation(**row["reservation"])
        result: ToolResult = {
            "type": "Success",
            "value": receipt.model_dump(mode="json"),
        }
        settlement = Settlement(0, len(canonical_json_bytes(result)))
        if (
            reservation.max_attempts != 0
            or settlement.actual_output_bytes > reservation.max_output_bytes
        ):
            raise ValueError("local note receipt exceeds its original reservation")
        async with self._database.begin() as connection:
            original = (
                (
                    await connection.execute(
                        select(read_position)
                        .where(read_position.c.position == str(position))
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if original["result"] is not None and (
                original["result"] != result
                or original["settlement"] != asdict(settlement)
            ):
                raise ValueError("local note position terminal result changed")
            await connection.execute(
                update(read_position)
                .where(read_position.c.position == str(position))
                .values(
                    state="completed",
                    result=result,
                    settlement=asdict(settlement),
                    updated_at=datetime.now(UTC),
                )
            )
        return result

    async def recover_note_save(
        self,
        *,
        lineage: NativeDispatchLineage,
        binding: ToolBinding[Any, Any, Any],
        plan: FrozenToolPlan,
        arguments: dict[str, Any],
        budgets: BudgetState,
        memory: MemoryService,
    ) -> DispatchCompleted | None:
        """Recover only the exact local note write after its transaction resolves."""
        if (
            binding.spec.id != ToolId("memory.save_note")
            or binding.spec.effect is not ToolEffect.Write
            or binding.replay_policy is not ReplayPolicy.ReDispatchable
        ):
            raise ValueError("note recovery is limited to the local note binding")
        position = lineage.position
        contract = {
            "tool_id": str(binding.spec.id),
            "tool_contract_revision": binding.spec.tool_contract_revision,
            "policy_revision": binding.policy_revision,
            "plan_revision": plan.plan_revision,
            "input_digest": raw_input_digest(ParsedJson(arguments)),
            "replay_policy": binding.replay_policy.value,
        }
        result = await self.recover_committed_note_save(
            position=position, arguments=arguments, contract=contract, memory=memory
        )
        if result is not None:
            await self.recover_budget(lineage=lineage, budgets=budgets)
            return completed_tool_result(result, HostRef(str(position)))
        # The owned connection has resolved any previous append. Only this local
        # zero-attempt write may return to prepared; paid reads retain barriers.
        async with self._database.begin() as connection:
            await connection.execute(
                update(read_position)
                .where(read_position.c.position == str(position))
                .values(state="prepared", updated_at=datetime.now(UTC))
            )
        return None

    async def recover_native_read(
        self,
        *,
        lineage: NativeDispatchLineage,
        binding: ToolBinding[Any, Any, Any],
        plan: FrozenToolPlan,
        arguments: dict[str, Any],
    ) -> DispatchCompleted | None:
        """Retain matching paid-read barriers across every live causal component."""
        contract = {
            "plan_revision": plan.plan_revision,
            "tool_contract_revision": binding.spec.tool_contract_revision,
            "implementation_revision": binding.implementation_revision,
            "policy_revision": binding.policy_revision,
            "effect": binding.spec.effect.value,
        }
        async with self._database.begin() as connection:
            await lock_conversation(connection, lineage.permit.scope_id)
            current = (
                (
                    await connection.execute(
                        select(native_invocation).where(
                            native_invocation.c.id == UUID(lineage.invocation_id)
                        )
                    )
                )
                .mappings()
                .one()
            )
            if (
                current["frozen_contract"] != contract
                or current["attempt_id"] != UUID(lineage.attempt_id)
                or current["tool_id"] != str(binding.spec.id)
                or tuple(current["proposal"]["input_ids"])
                != tuple(map(str, lineage.input_ids))
            ):
                raise ValueError(
                    "read dispatch contract changed after callback acceptance"
                )
            current_input = validate_tool_input(
                binding, current["proposal"]["arguments"]
            )
            if canonical_json_bytes(
                current_input.model_dump(mode="json")
            ) != canonical_json_bytes(arguments):
                raise ValueError("read arguments changed after callback acceptance")
            is_search = binding.spec.id == ToolId("web.search")
            operation: JsonObject | None = None
            if is_search:
                if self._web_source_operation is None:
                    raise ValueError("web search requires its bound source operation")
                try:
                    operation = self._web_source_operation(
                        cast(WebSearchInput, current_input)
                    )
                except ValueError:
                    return completed_tool_result(
                        {"type": "Failure", "error": {"type": "InvalidCursor"}}
                    )
                self._web_operations[lineage.position] = operation
                original = (
                    (
                        await connection.execute(
                            select(read_position)
                            .where(read_position.c.position == str(lineage.position))
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if original is not None:
                    expected = {
                        "tool_id": str(binding.spec.id),
                        "tool_contract_revision": binding.spec.tool_contract_revision,
                        "policy_revision": binding.policy_revision,
                        "plan_revision": plan.plan_revision,
                        "input_digest": raw_input_digest(ParsedJson(arguments)),
                        "replay_policy": binding.replay_policy.value,
                        "web_source_operation": operation,
                    }
                    if original["contract"] != expected:
                        raise ValueError("original web search contract changed")
                    if original["state"] == "completed":
                        return completed_tool_result(original["result"])
                    if operation is None and original["state"] in {
                        "dispatched",
                        "uncertain",
                    }:
                        # This exact stored contract proves no network was possible.
                        await connection.execute(
                            update(read_position)
                            .where(read_position.c.position == str(lineage.position))
                            .values(state="prepared", updated_at=datetime.now(UTC))
                        )
            if binding.spec.id in FRESH_READ_IDS:
                return None
            unfinished = set(
                (
                    await connection.execute(
                        select(message.c.id).where(
                            message.c.source_conversation_id == lineage.permit.scope_id,
                            message.c.id.in_(tuple(map(UUID, lineage.input_ids))),
                            message.c.role.in_(("owner", "host")),
                            message.c.control_kind.is_(None),
                            message.c.processing_parked_at.is_(None),
                            message.c.request_state.in_(("pending", "waiting")),
                        )
                    )
                ).scalars()
            )
            if not unfinished:
                return None
            component = set(await causal_component_ids(connection, tuple(unfinished)))
            rows = (
                (
                    await connection.execute(
                        select(native_invocation)
                        .join(
                            native_attempt,
                            native_attempt.c.id == native_invocation.c.attempt_id,
                        )
                        .where(
                            native_attempt.c.conversation_id == lineage.permit.scope_id,
                            native_invocation.c.id != UUID(lineage.invocation_id),
                            native_invocation.c.tool_id == str(binding.spec.id),
                            native_invocation.c.validation == "accepted",
                        )
                        .order_by(
                            native_attempt.c.attempt_seq, native_invocation.c.ordinal
                        )
                    )
                )
                .mappings()
                .all()
            )
            completed: DispatchCompleted | None = None
            for invocation in rows:
                if not component.intersection(
                    map(UUID, invocation["proposal"]["input_ids"])
                ):
                    continue
                prior_arguments = invocation["proposal"]["arguments"]
                if not is_search and invocation["frozen_contract"] == contract:
                    prior_input = validate_tool_input(binding, prior_arguments)
                    prior_arguments = prior_input.model_dump(mode="json")
                if not is_search and canonical_json_bytes(
                    prior_arguments
                ) != canonical_json_bytes(arguments):
                    continue
                position = invocation["read_position"] or "native-invocation:" + str(
                    invocation["id"]
                )
                row = (
                    (
                        await connection.execute(
                            select(read_position)
                            .where(read_position.c.position == position)
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None or row["state"] == "prepared":
                    continue
                if is_search:
                    if row["state"] == "completed":
                        continue
                    if "web_source_operation" not in row["contract"]:
                        return _paid_read_barrier(
                            position, "paid_read_contract_changed"
                        )
                    previous = row["contract"]["web_source_operation"]
                    if previous is not None:
                        previous = WebSearchSourceOperation.model_validate(
                            previous
                        ).model_dump(mode="json")
                        if previous == operation:
                            return _paid_read_barrier(
                                position, "paid_read_outcome_unknown"
                            )
                    continue
                if row["state"] in {"dispatched", "uncertain"} and (
                    row["contract"].get("replay_policy")
                    == ReplayPolicy.BilledOnce.value
                    or binding.replay_policy is ReplayPolicy.BilledOnce
                ):
                    return completed_tool_result(
                        {
                            "type": "Failure",
                            "error": {
                                "type": "HostRejected",
                                "code": "paid_read_outcome_unknown"
                                if invocation["frozen_contract"] == contract
                                else "paid_read_contract_changed",
                            },
                        },
                        HostRef(position),
                    )
                if (
                    row["state"] == "completed"
                    and invocation["frozen_contract"] == contract
                    and invocation["attempt_id"] != UUID(lineage.attempt_id)
                ):
                    completed = completed_tool_result(row["result"], HostRef(position))
            return completed

    async def recover_budget(
        self, *, lineage: ToolDispatchLineage, budgets: BudgetState
    ) -> None:
        """Rebuild original scope charges through the existing budget primitive."""
        async with self._database.connect() as connection:
            positions = [str(lineage.position)]
            if not isinstance(
                lineage, InitialReadDispatchLineage | NativeDispatchLineage
            ):
                scope_key = await connection.scalar(
                    select(model_decision.c.scope_key).where(
                        model_decision.c.decision_id == lineage.model_decision_id
                    )
                )
                if scope_key is None:
                    raise ValueError("read has no accepted original model decision")
                decisions = (
                    (
                        await connection.execute(
                            select(
                                model_decision.c.decision_id, model_decision.c.request
                            )
                            .where(model_decision.c.scope_key == scope_key)
                            .order_by(model_decision.c.ordinal)
                        )
                    )
                    .mappings()
                    .all()
                )
                positions = [
                    "model-decision:" + row["decision_id"] for row in decisions
                ]
                operation_id = decisions[0]["request"]["operation_id"]
                if operation_id is not None:
                    positions.insert(
                        0,
                        str(
                            InitialReadDispatchLineage(
                                RunId("budget-recovery"), operation_id
                            ).position
                        ),
                    )
            rows = (
                (
                    await connection.execute(
                        select(read_position).where(
                            read_position.c.position.in_(positions)
                        )
                    )
                )
                .mappings()
                .all()
            )
            if any(row["state"] in {"dispatched", "uncertain"} for row in rows):
                raise RecoveryRequired("original paid read outcome is uncertain")
            by_position = {row["position"]: row for row in rows}
            for identifier in positions:
                row = by_position.get(identifier)
                if row is None or row["reservation"] is None:
                    continue
                position = InvocationPosition(row["position"])
                reservation = Reservation(**row["reservation"])
                if not await budgets.reserve(position, reservation):
                    raise ValueError("original read charges exceed the frozen budget")
                if row["settlement"] is not None:
                    await budgets.settle(position, Settlement(**row["settlement"]))

    async def occupy(
        self,
        *,
        position: InvocationPosition,
        tool_id: ToolId,
        tool_contract_revision: str,
        policy_revision: str,
        plan_revision: str,
        input_digest: str,
        replay_policy: ReplayPolicy,
    ) -> PositionState:
        contract: dict[str, Any] = {
            "tool_id": str(tool_id),
            "tool_contract_revision": tool_contract_revision,
            "policy_revision": policy_revision,
            "plan_revision": plan_revision,
            "input_digest": input_digest,
            "replay_policy": replay_policy.value,
        }
        if tool_id == ToolId("web.search"):
            if position not in self._web_operations:
                raise ValueError(
                    "web source operation was not staged for this invocation"
                )
            contract["web_source_operation"] = self._web_operations[position]
        async with self._database.begin() as connection:
            await connection.execute(
                insert(read_position)
                .values(position=str(position), contract=contract, state="prepared")
                .on_conflict_do_nothing(index_elements=["position"])
            )
            row = (
                (
                    await connection.execute(
                        select(read_position)
                        .where(read_position.c.position == str(position))
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if row["contract"] != contract:
                raise ValueError("read position was occupied by a different invocation")
            return _state(row)

    async def reserve(
        self,
        *,
        position: InvocationPosition,
        budgets: BudgetState,
        reservation: Reservation,
    ) -> bool:
        async with self._database.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(read_position)
                        .where(read_position.c.position == str(position))
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if row["reservation"] is not None and row["reservation"] != asdict(
                reservation
            ):
                raise ValueError("read position reservation changed")
            existing = self._reserved.get(position)
            if existing is not None:
                if existing[0] != reservation:
                    raise ValueError("read position reservation changed")
                if not existing[1]:
                    return False
                return await budgets.reserve(position, reservation)
            accepted = await budgets.reserve(position, reservation)
            await connection.execute(
                update(read_position)
                .where(read_position.c.position == str(position))
                .values(
                    reservation=asdict(reservation) if accepted else None,
                    updated_at=datetime.now(UTC),
                )
            )
            self._reserved[position] = (reservation, accepted)
            return accepted

    async def dispatch_started(
        self, *, position: InvocationPosition, replay_policy: ReplayPolicy
    ) -> PositionState:
        async with self._database.begin() as connection:
            if str(position).startswith("native-invocation:"):
                invocation_id = UUID(str(position).removeprefix("native-invocation:"))
                attempt = (
                    (
                        await connection.execute(
                            select(native_attempt)
                            .join(
                                native_invocation,
                                native_invocation.c.attempt_id == native_attempt.c.id,
                            )
                            .where(native_invocation.c.id == invocation_id)
                        )
                    )
                    .mappings()
                    .one()
                )
                await lock_conversation(connection, attempt["conversation_id"])
                current = (
                    (
                        await connection.execute(
                            select(native_attempt)
                            .where(native_attempt.c.id == attempt["id"])
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .one()
                )
                if (
                    current["fenced_at"] is not None
                    or current["terminal"] is not None
                    or current["product_outcome"] is not None
                ):
                    raise DeploymentOwnershipDefect(
                        "native read authority is no longer live"
                    )
            row = (
                (
                    await connection.execute(
                        select(read_position)
                        .where(read_position.c.position == str(position))
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if row["contract"]["replay_policy"] != replay_policy.value:
                raise ValueError("read replay policy changed")
            if row["state"] != "prepared":
                return _state(row)
            reservation = self._reserved.get(position)
            if reservation is None or not reservation[1]:
                raise ValueError("read dispatch has no accepted current reservation")
            await connection.execute(
                update(read_position)
                .where(read_position.c.position == str(position))
                .values(state="dispatched", updated_at=datetime.now(UTC))
            )
            return PositionState(None, False)

    async def dispatch_abandoned(
        self,
        *,
        position: InvocationPosition,
        replay_policy: ReplayPolicy,
        actual_attempts: int,
        lease_recovered: bool,
    ) -> None:
        del position, replay_policy, actual_attempts, lease_recovered
        raise ValueError("durable reads do not automatically reconcile unknown charges")

    async def uncertain(self, *, position: InvocationPosition) -> None:
        async with self._database.begin() as connection:
            changed = await connection.scalar(
                update(read_position)
                .where(
                    read_position.c.position == str(position),
                    read_position.c.state.in_(("dispatched", "uncertain")),
                )
                .values(state="uncertain", updated_at=datetime.now(UTC))
                .returning(read_position.c.position)
            )
            if changed is None:
                raise ValueError("read uncertainty has no dispatched position")

    async def terminalize_and_settle(
        self,
        *,
        position: InvocationPosition,
        budgets: BudgetState,
        result: ToolResult,
        settlement: Settlement,
    ) -> ToolResult:
        canonical_json_bytes(result)
        reserved = self._reserved.get(position)
        if reserved is None or not reserved[1]:
            if settlement.actual_attempts != 0:
                raise ValueError("unreserved read cannot spend external attempts")
        elif (
            settlement.actual_attempts > reserved[0].max_attempts
            or settlement.actual_output_bytes > reserved[0].max_output_bytes
        ):
            raise ValueError("read settlement exceeds its reservation")
        async with self._database.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(read_position)
                        .where(read_position.c.position == str(position))
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            if row["state"] == "uncertain":
                raise ValueError("uncertain read cannot accept a fabricated terminal")
            if row["result"] is not None and (
                row["result"] != result or row["settlement"] != asdict(settlement)
            ):
                raise ValueError("read position terminal result changed")
            if reserved is not None and reserved[1]:
                await budgets.settle(position, settlement)
            await connection.execute(
                update(read_position)
                .where(read_position.c.position == str(position))
                .values(
                    state="completed",
                    result=result,
                    settlement=asdict(settlement),
                    updated_at=datetime.now(UTC),
                )
            )
        return result


def _state(row: RowMapping) -> PositionState:
    return PositionState(
        cast(ToolResult | None, row["result"]),
        row["state"] in {"dispatched", "uncertain"},
    )


def _paid_read_barrier(position: str, code: str) -> DispatchCompleted:
    return completed_tool_result(
        {"type": "Failure", "error": {"type": "HostRejected", "code": code}},
        HostRef(position),
    )
