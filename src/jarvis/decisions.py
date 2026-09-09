"""Original paid inference records; actions remain the sole effect owner."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol

from llm_agent_kernel import Checkpoint, InputId, ThreadId
from llm_agent_kernel.decisions import (
    DecisionScope,
    DurableIsolatedDecisions,
    IsolatedDecisionScope,
    ModelDecisionArmed,
    ModelDecisionCompleted,
    ModelDecisionDefect,
    ModelDecisionJournal,
    ModelDecisionRecord,
    ModelDecisionRequest,
    ModelDecisionScope,
)
from llm_tools import canonical_json_bytes
from provider_runtime.agent_runtime import (
    AgentFailure,
    AgentQuotaExhausted,
    AgentTerminal,
    freeze_json_value,
    ref_from_json,
    ref_to_json,
    thaw_json_value,
)
from provider_runtime.types import Absent, Present, TokenUsage
from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError
from sqlalchemy import RowMapping, delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import message, model_decision
from jarvis.ownership import Database


class _Document(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class _Request(_Document):
    schema_version: Literal["jarvis-model-decision.v1"]
    thread_id: str | None
    first_input_id: str | None
    operation_id: str | None
    ordinal: int
    definition_fingerprint: str
    plan_revision: str
    input_ids: tuple[str, ...]
    through_checkpoint: str | None
    as_of: datetime
    model_step_ordinal_before: int
    protocol_repairs: int
    canonical_content: tuple[str, ...]
    submitted_content: tuple[str, ...]

    @classmethod
    def from_request(cls, request: ModelDecisionRequest) -> _Request:
        scope = request.scope
        return cls(
            schema_version="jarvis-model-decision.v1",
            thread_id=str(scope.thread_id)
            if isinstance(scope, ModelDecisionScope)
            else None,
            first_input_id=str(scope.first_input_id)
            if isinstance(scope, ModelDecisionScope)
            else None,
            operation_id=scope.operation_id
            if isinstance(scope, IsolatedDecisionScope)
            else None,
            ordinal=request.ordinal,
            definition_fingerprint=request.definition_fingerprint,
            plan_revision=request.plan_revision,
            input_ids=tuple(map(str, request.input_ids)),
            through_checkpoint=None
            if request.through_checkpoint is None
            else str(request.through_checkpoint),
            as_of=request.as_of,
            model_step_ordinal_before=request.model_step_ordinal_before,
            protocol_repairs=request.protocol_repairs,
            canonical_content=request.canonical_content,
            submitted_content=request.submitted_content,
        )

    def to_request(self) -> ModelDecisionRequest:
        if self.operation_id is not None:
            if self.thread_id is not None or self.first_input_id is not None:
                raise ModelDecisionDefect("isolated decision has thread authority")
            scope: DecisionScope = IsolatedDecisionScope(self.operation_id)
        else:
            if self.thread_id is None or self.first_input_id is None:
                raise ModelDecisionDefect("thread decision has no original scope")
            scope = ModelDecisionScope(
                ThreadId(self.thread_id), InputId(self.first_input_id)
            )
        return ModelDecisionRequest(
            scope=scope,
            ordinal=self.ordinal,
            definition_fingerprint=self.definition_fingerprint,
            plan_revision=self.plan_revision,
            input_ids=tuple(map(InputId, self.input_ids)),
            through_checkpoint=None
            if self.through_checkpoint is None
            else Checkpoint(self.through_checkpoint),
            as_of=self.as_of,
            model_step_ordinal_before=self.model_step_ordinal_before,
            protocol_repairs=self.protocol_repairs,
            canonical_content=self.canonical_content,
            submitted_content=self.submitted_content,
        )


class _Usage(_Document):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int | None
    cache_read_input_tokens: int | None
    cache_write_input_tokens: int | None


class _Terminal(_Document):
    status: Literal["succeeded", "failed", "cancelled"]
    failure: (
        Literal[
            "quota_exhausted",
            "backend_failed",
            "turn_timeout",
            "output_limit_exceeded",
            "approval_unanswered",
            "output_schema_violation",
        ]
        | None
    )
    final_text: str
    session_ref: dict[str, JsonValue]
    structured_output: JsonValue
    usage: _Usage | None
    diagnostics: tuple[str, ...]

    @classmethod
    def from_terminal(cls, terminal: AgentTerminal) -> _Terminal:
        usage = terminal.usage.value if isinstance(terminal.usage, Present) else None
        return cls.model_validate(
            {
                "status": terminal.status,
                "failure": "quota_exhausted"
                if isinstance(terminal.failure, AgentQuotaExhausted)
                else terminal.failure.cause
                if isinstance(terminal.failure, AgentFailure)
                else None,
                "final_text": terminal.final_text,
                "session_ref": thaw_json_value(ref_to_json(terminal.session_ref)),
                "structured_output": thaw_json_value(terminal.structured_output),
                "usage": None
                if usage is None
                else {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                    "reasoning_tokens": usage.reasoning_tokens.value
                    if isinstance(usage.reasoning_tokens, Present)
                    else None,
                    "cache_read_input_tokens": usage.cache_read_input_tokens.value
                    if isinstance(usage.cache_read_input_tokens, Present)
                    else None,
                    "cache_write_input_tokens": usage.cache_write_input_tokens.value
                    if isinstance(usage.cache_write_input_tokens, Present)
                    else None,
                },
                "diagnostics": terminal.diagnostics,
            }
        )

    def to_terminal(self) -> AgentTerminal:
        usage = self.usage
        return AgentTerminal(
            status=self.status,
            failure=AgentQuotaExhausted()
            if self.failure == "quota_exhausted"
            else AgentFailure(self.failure)
            if self.failure is not None
            else None,
            final_text=self.final_text,
            session_ref=ref_from_json(self.session_ref),
            structured_output=freeze_json_value(self.structured_output),
            usage=Absent()
            if usage is None
            else Present(
                TokenUsage(
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.total_tokens,
                    Absent()
                    if usage.reasoning_tokens is None
                    else Present(usage.reasoning_tokens),
                    Absent()
                    if usage.cache_read_input_tokens is None
                    else Present(usage.cache_read_input_tokens),
                    Absent()
                    if usage.cache_write_input_tokens is None
                    else Present(usage.cache_write_input_tokens),
                )
            ),
            diagnostics=self.diagnostics,
        )


def _scope_key(scope: DecisionScope) -> str:
    value = (
        {"thread_id": str(scope.thread_id), "first_input_id": str(scope.first_input_id)}
        if isinstance(scope, ModelDecisionScope)
        else {"operation_id": scope.operation_id}
    )
    return canonical_json_bytes(value).decode()


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
        if row["terminal"] is None:
            return ModelDecisionArmed(request)
        return ModelDecisionCompleted(
            request,
            _Terminal.model_validate_json(
                canonical_json_bytes(row["terminal"])
            ).to_terminal(),
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise ModelDecisionDefect("stored paid decision is invalid") from error


class ModelEvidence(Protocol):
    def snapshot_model_evidence(self) -> dict[str, object]: ...
    def restore_model_evidence(self, value: object) -> None: ...


type ModelJournalFactory = Callable[[ModelEvidence | None], ModelDecisionJournal]


async def isolated_decisions(
    factory: ModelJournalFactory,
    evidence: ModelEvidence | None,
    operation_id: str,
    as_of: datetime,
) -> tuple[DurableIsolatedDecisions, datetime]:
    scope = IsolatedDecisionScope(operation_id)
    journal = factory(evidence)
    recorded = await journal.latest(scope)
    return DurableIsolatedDecisions(
        scope, journal
    ), as_of if recorded is None else recorded.request.as_of


class PostgresModelDecisionJournal:
    def __init__(
        self, engine: Database, *, evidence: ModelEvidence | None = None
    ) -> None:
        self._engine = engine
        self._evidence = evidence

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
        record = _record(row)
        if isinstance(record, ModelDecisionCompleted):
            if self._evidence is None:
                if row["host_evidence"] is not None:
                    raise ModelDecisionDefect(
                        "paid decision requires its original host evidence owner"
                    )
            else:
                self._evidence.restore_model_evidence(row["host_evidence"])
        return record

    async def arm(self, request: ModelDecisionRequest) -> None:
        document = _Request.from_request(request)
        try:
            async with self._engine.begin() as connection:
                previous = (
                    (
                        await connection.execute(
                            select(model_decision.c.ordinal, model_decision.c.terminal)
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
                    previous is not None and previous["terminal"] is None
                ):
                    raise ModelDecisionDefect(
                        "paid decision ordinal is not the next completed continuation"
                    )
                await connection.execute(
                    insert(model_decision).values(
                        decision_id=request.decision_id,
                        scope_key=_scope_key(request.scope),
                        thread_id=document.thread_id,
                        first_input_id=document.first_input_id,
                        ordinal=request.ordinal,
                        request_fingerprint=request.request_fingerprint,
                        request=document.model_dump(mode="json"),
                    )
                )
        except IntegrityError as error:
            raise ModelDecisionDefect(
                "paid decision identity is already armed or invalid"
            ) from error

    async def complete(
        self, request: ModelDecisionRequest, terminal: AgentTerminal
    ) -> ModelDecisionCompleted:
        async with self._engine.begin() as connection:
            changed = await connection.scalar(
                update(model_decision)
                .where(
                    model_decision.c.decision_id == request.decision_id,
                    model_decision.c.request_fingerprint == request.request_fingerprint,
                    model_decision.c.terminal.is_(None),
                )
                .values(
                    terminal=_Terminal.from_terminal(terminal).model_dump(mode="json"),
                    host_evidence=None
                    if self._evidence is None
                    else self._evidence.snapshot_model_evidence(),
                    completed_at=datetime.now(UTC),
                )
                .returning(model_decision.c.decision_id)
            )
            if changed is None:
                raise ModelDecisionDefect(
                    "paid decision completion is absent, changed, or already final"
                )
        return ModelDecisionCompleted(request, terminal)

    async def release_undispatched(self, request: ModelDecisionRequest) -> None:
        async with self._engine.begin() as connection:
            removed = await connection.scalar(
                delete(model_decision)
                .where(
                    model_decision.c.decision_id == request.decision_id,
                    model_decision.c.request_fingerprint == request.request_fingerprint,
                    model_decision.c.terminal.is_(None),
                )
                .returning(model_decision.c.decision_id)
            )
            if removed is None:
                raise ModelDecisionDefect(
                    "undispatched paid decision is absent, changed, or final"
                )


async def pending_thread_decision(
    connection: AsyncConnection, thread_id: str
) -> ModelDecisionRequest | None:
    latest = (
        select(model_decision)
        .where(model_decision.c.thread_id == thread_id)
        .distinct(model_decision.c.scope_key)
        .order_by(model_decision.c.scope_key, model_decision.c.ordinal.desc())
        .subquery()
    )
    row = (
        (
            await connection.execute(
                select(latest)
                .join(message, message.c.id == latest.c.first_input_id)
                .where(message.c.processed_at.is_(None))
                .order_by(message.c.created_at, message.c.id)
                .limit(1)
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _record(row).request
