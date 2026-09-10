"""Durable llm-tools Read positions, separate from recoverable Write actions."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast

from llm_agent_kernel import (
    InitialReadDispatchLineage,
    RunId,
    ToolDispatchLineage,
)
from llm_tools import (
    BudgetState,
    InvocationPosition,
    PositionState,
    RecoveryRequired,
    ReplayPolicy,
    Reservation,
    Settlement,
    ToolId,
    ToolResult,
    canonical_json_bytes,
)
from sqlalchemy import RowMapping, select, update
from sqlalchemy.dialects.postgresql import insert

from jarvis.db import model_decision, read_position
from jarvis.ownership import Database


class PostgresReadRecorder:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._reserved: dict[InvocationPosition, tuple[Reservation, bool]] = {}

    @property
    def durable(self) -> bool:
        return True

    async def recover_budget(
        self, *, lineage: ToolDispatchLineage, budgets: BudgetState
    ) -> None:
        """Rebuild original scope charges through the existing budget primitive."""
        async with self._database.connect() as connection:
            positions = [str(lineage.position)]
            if not isinstance(lineage, InitialReadDispatchLineage):
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
        contract = {
            "tool_id": str(tool_id),
            "tool_contract_revision": tool_contract_revision,
            "policy_revision": policy_revision,
            "plan_revision": plan_revision,
            "input_digest": input_digest,
            "replay_policy": replay_policy.value,
        }
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
                return existing[1]
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
