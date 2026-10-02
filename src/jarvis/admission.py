"""Current deployment authority and exact frozen tool-budget construction."""

from __future__ import annotations

from uuid import UUID, uuid4

from llm_agent_kernel import NativeDefect, OwnerPermit, OwnerToken
from llm_tools import BudgetState, FrozenToolPlan, RunBudgetState
from sqlalchemy import select, text

from jarvis.db import native_attempt, native_invocation
from jarvis.ownership import Database, DeploymentOwnershipDefect


class JarvisOwner:
    def __init__(self, database: Database, scope_id: str) -> None:
        self.database = database
        self.scope_id = scope_id
        self.token = OwnerToken(str(uuid4()))

    def permit(
        self, operation_id: str, parent_invocation_id: str | None = None
    ) -> OwnerPermit:
        return OwnerPermit(
            self.scope_id, self.token, operation_id, parent_invocation_id
        )

    async def require_current(self, permit: OwnerPermit) -> None:
        if permit.scope_id != self.scope_id or permit.owner_token != self.token:
            raise DeploymentOwnershipDefect(
                "owner permit is stale or outside this deployment"
            )
        async with self.database.connect() as connection:
            await connection.execute(text("SELECT 1"))
            if permit.parent_invocation_id is not None:
                current = await connection.scalar(
                    select(native_invocation.c.id)
                    .join(
                        native_attempt,
                        native_attempt.c.id == native_invocation.c.attempt_id,
                    )
                    .where(
                        native_invocation.c.id == UUID(permit.parent_invocation_id),
                        native_attempt.c.owner_epoch == str(self.token),
                        native_attempt.c.fenced_at.is_(None),
                        native_attempt.c.product_outcome.is_(None),
                    )
                )
                if current is None:
                    raise NativeDefect("parent native invocation is no longer current")
            elif permit.operation_id.startswith("jarvis-native:"):
                attempt = (
                    (
                        await connection.execute(
                            select(native_attempt).where(
                                native_attempt.c.id
                                == UUID(
                                    permit.operation_id.removeprefix("jarvis-native:")
                                )
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if attempt is not None and (
                    attempt["owner_epoch"] != str(self.token)
                    or attempt["fenced_at"] is not None
                    or attempt["product_outcome"] is not None
                ):
                    raise NativeDefect("native attempt authority is no longer current")


class ExactToolBudgetFactory:
    def create(self, plan: FrozenToolPlan) -> BudgetState:
        return RunBudgetState(plan.profile.run_limits)
