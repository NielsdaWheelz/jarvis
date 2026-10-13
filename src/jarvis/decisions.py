"""Original paid inference records; actions remain the sole effect owner."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from llm_agent_kernel import InputId
from llm_agent_kernel.decisions import (
    DecisionScope,
    IsolatedDecisionScope,
    ModelDecisionArmed,
    ModelDecisionCompleted,
    ModelDecisionDefect,
    ModelDecisionJournal,
    ModelDecisionNotSubmitted,
    ModelDecisionRecord,
    ModelDecisionRequest,
)
from llm_tools import canonical_json_bytes
from provider_runtime.agent_runtime import (
    AgentNotSubmitted,
    AgentRuntimeDefect,
    AgentTerminal,
    attempt_from_json,
    attempt_to_json,
    submission_from_json,
    submission_to_json,
    terminal_from_json,
    terminal_to_json,
)
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import RowMapping, insert, select, update
from sqlalchemy.exc import IntegrityError

from jarvis.db import model_decision
from jarvis.ownership import Database


class _Document(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class _Request(_Document):
    schema_version: Literal["jarvis-model-decision.v2"]
    operation_id: str
    ordinal: int
    definition_fingerprint: str
    plan_revision: str
    input_ids: tuple[str, ...]
    as_of: datetime
    model_step_ordinal_before: int
    protocol_repairs: int
    canonical_content: tuple[str, ...]
    submitted_content: tuple[str, ...]
    provider_attempt: dict[str, str]

    @classmethod
    def from_request(cls, request: ModelDecisionRequest) -> _Request:
        return cls(
            schema_version="jarvis-model-decision.v2",
            operation_id=request.scope.operation_id,
            ordinal=request.ordinal,
            definition_fingerprint=request.definition_fingerprint,
            plan_revision=request.plan_revision,
            input_ids=tuple(map(str, request.input_ids)),
            as_of=request.as_of,
            model_step_ordinal_before=request.model_step_ordinal_before,
            protocol_repairs=request.protocol_repairs,
            canonical_content=request.canonical_content,
            submitted_content=request.submitted_content,
            provider_attempt=attempt_to_json(request.provider_attempt),
        )

    def to_request(self) -> ModelDecisionRequest:
        return ModelDecisionRequest(
            scope=IsolatedDecisionScope(self.operation_id),
            ordinal=self.ordinal,
            definition_fingerprint=self.definition_fingerprint,
            plan_revision=self.plan_revision,
            input_ids=tuple(map(InputId, self.input_ids)),
            through_checkpoint=None,
            as_of=self.as_of,
            model_step_ordinal_before=self.model_step_ordinal_before,
            protocol_repairs=self.protocol_repairs,
            canonical_content=self.canonical_content,
            submitted_content=self.submitted_content,
            provider_attempt=attempt_from_json(self.provider_attempt),
        )


def _scope_key(scope: DecisionScope) -> str:
    return canonical_json_bytes({"operation_id": scope.operation_id}).decode()


def _record(row: RowMapping) -> ModelDecisionRecord:
    try:
        request = _Request.model_validate_json(
            canonical_json_bytes(row["request"])
        ).to_request()
        if (
            request.decision_id != row["decision_id"]
            or request.request_fingerprint != row["request_fingerprint"]
            or _scope_key(request.scope) != row["scope_key"]
        ):
            raise ModelDecisionDefect("stored paid decision identity disagrees")
        if row["submission"] is not None:
            evidence = submission_from_json(row["submission"])
            if row["terminal"] is not None or not isinstance(
                evidence, AgentNotSubmitted
            ):
                raise ModelDecisionDefect(
                    "stored non-submission conflicts with native truth"
                )
            return ModelDecisionNotSubmitted(request, evidence)
        if row["terminal"] is None:
            return ModelDecisionArmed(request)
        return ModelDecisionCompleted(
            request,
            terminal_from_json(row["terminal"]),
        )
    except (AgentRuntimeDefect, ValidationError, TypeError, ValueError) as error:
        raise ModelDecisionDefect("stored paid decision is invalid") from error


type ModelJournalFactory = Callable[[], ModelDecisionJournal]


class PostgresModelDecisionJournal:
    def __init__(self, engine: Database) -> None:
        self._engine = engine

    async def latest(self, scope: DecisionScope) -> ModelDecisionRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(model_decision)
                        .where(model_decision.c.scope_key == _scope_key(scope))
                        .order_by(model_decision.c.ordinal.desc())
                        .limit(1)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        if row["host_evidence"] is not None:
            raise ModelDecisionDefect(
                "retired memory cognition cannot replay through the gate"
            )
        return _record(row)

    async def arm(self, request: ModelDecisionRequest) -> None:
        document = _Request.from_request(request)
        try:
            async with self._engine.begin() as connection:
                previous = (
                    (
                        await connection.execute(
                            select(
                                model_decision.c.ordinal,
                                model_decision.c.terminal,
                                model_decision.c.submission,
                            )
                            .where(
                                model_decision.c.scope_key == _scope_key(request.scope)
                            )
                            .order_by(model_decision.c.ordinal.desc())
                            .limit(1)
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                expected_ordinal = 1 if previous is None else previous["ordinal"] + 1
                if request.ordinal != expected_ordinal or (
                    previous is not None
                    and previous["terminal"] is None
                    and previous["submission"] is None
                ):
                    raise ModelDecisionDefect(
                        "paid decision ordinal is not the next completed continuation"
                    )
                await connection.execute(
                    insert(model_decision).values(
                        decision_id=request.decision_id,
                        scope_key=_scope_key(request.scope),
                        ordinal=request.ordinal,
                        request_fingerprint=request.request_fingerprint,
                        request=document.model_dump(mode="json"),
                        host_evidence=None,
                    )
                )
        except IntegrityError as error:
            raise ModelDecisionDefect(
                "paid decision identity is already armed or invalid"
            ) from error

    async def complete(
        self, request: ModelDecisionRequest, terminal: AgentTerminal
    ) -> ModelDecisionCompleted:
        completed = ModelDecisionCompleted(request, terminal)
        async with self._engine.begin() as connection:
            changed = await connection.scalar(
                update(model_decision)
                .where(
                    model_decision.c.decision_id == request.decision_id,
                    model_decision.c.request_fingerprint == request.request_fingerprint,
                    model_decision.c.terminal.is_(None),
                    model_decision.c.submission.is_(None),
                )
                .values(
                    terminal=terminal_to_json(terminal),
                    completed_at=datetime.now(UTC),
                )
                .returning(model_decision.c.decision_id)
            )
            if changed is None:
                raise ModelDecisionDefect(
                    "paid decision completion is absent, changed, or already final"
                )
        return completed

    async def not_submitted(
        self, request: ModelDecisionRequest, evidence: AgentNotSubmitted
    ) -> None:
        ModelDecisionNotSubmitted(request, evidence)
        async with self._engine.begin() as connection:
            changed = await connection.scalar(
                update(model_decision)
                .where(
                    model_decision.c.decision_id == request.decision_id,
                    model_decision.c.request_fingerprint == request.request_fingerprint,
                    model_decision.c.terminal.is_(None),
                    model_decision.c.submission.is_(None),
                )
                .values(submission=submission_to_json(evidence))
                .returning(model_decision.c.decision_id)
            )
            if changed is None:
                raise ModelDecisionDefect(
                    "non-submission proof is absent, changed, or final"
                )
