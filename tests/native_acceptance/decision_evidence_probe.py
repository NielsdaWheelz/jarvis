"""Temporary real-store original attempt and native-terminal recovery proof."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

from llm_agent_kernel.decisions import (
    IsolatedDecisionScope,
    ModelDecisionArmed,
    ModelDecisionCompleted,
    ModelDecisionNotSubmitted,
    ModelDecisionRequest,
    model_decision_id,
)
from provider_runtime.agent_runtime import (
    AgentAttempt,
    AgentNotSubmitted,
    AgentSessionRef,
    AgentTerminal,
    AgentTurnRef,
    NativeTerminalEvidence,
    RawAgentOutput,
    freeze_json_value,
)
from sqlalchemy import select

from jarvis.db import create_engine, model_decision
from jarvis.decisions import PostgresModelDecisionJournal
from jarvis.ownership import deployment_ownership


async def main():
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    try:
        async with deployment_ownership(engine) as database:
            scope = IsolatedDecisionScope("decision-proof:" + str(uuid4()))

            def request(ordinal):
                return ModelDecisionRequest(
                    scope,
                    ordinal,
                    "a" * 64,
                    "plan-one",
                    (),
                    None,
                    datetime.now(UTC),
                    0,
                    0,
                    ("canonical",),
                    ("submitted",),
                    AgentAttempt(model_decision_id(scope, ordinal), "b" * 64),
                )

            original = request(1)
            journal = PostgresModelDecisionJournal(database)
            await journal.arm(original)
            reopened = PostgresModelDecisionJournal(database)
            assert await reopened.latest(scope) == ModelDecisionArmed(original)
            proof = AgentNotSubmitted(
                original.provider_attempt, "revoked before submission"
            )
            await reopened.not_submitted(original, proof)
            assert await journal.latest(scope) == ModelDecisionNotSubmitted(
                original, proof
            )
            following = request(2)
            await journal.arm(following)
            ref = AgentSessionRef(
                "agent-session-ref.v1",
                "codex",
                "sdk",
                "proof",
                "proof",
                "a" * 64,
                "b" * 64,
            )
            terminal = AgentTerminal(
                "succeeded",
                None,
                "{invalid product output}",
                ref,
                NativeTerminalEvidence(
                    following.provider_attempt,
                    AgentTurnRef(ref, "native-turn"),
                    "codex-turn-completed.v1",
                ),
                RawAgentOutput(freeze_json_value({"invalid": True})),
            )
            await journal.complete(following, terminal)
            assert await reopened.latest(scope) == ModelDecisionCompleted(
                following, terminal
            )
            async with database.connect() as connection:
                first = (
                    (
                        await connection.execute(
                            select(model_decision).where(
                                model_decision.c.decision_id == original.decision_id
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                assert first["submission"] is not None and first["terminal"] is None
            print(
                "original prepared request, preserved non-submission, "
                "strict native terminal roundtrip: GREEN"
            )
    finally:
        await engine.dispose()


asyncio.run(main())
