"""Temporary real PostgreSQL acceptance for the native host contract."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, text

from jarvis.db import create_engine, message
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.terminal import JarvisTerminal, TurnEvidence, render_terminal


async def main() -> None:
    engine = create_engine(os.environ["JARVIS_PROOF_DATABASE_URL"])
    conversation = "proof-" + str(uuid4())
    try:
        async with deployment_ownership(engine) as database:
            store = MessageStore(database)
            first = await store.insert_waking(
                role="owner",
                text="research the first request",
                source="proof",
                source_conversation_id=conversation,
                source_message_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            async with database.connect() as connection:
                state = await connection.scalar(
                    select(message.c.request_state).where(
                        message.c.id == first.message.id
                    )
                )
                assert state == "pending", state
                table_names = set(
                    (
                        await connection.execute(
                            text(
                                (
                                    "SELECT tablename FROM pg_tables WHERE "
                                    "schemaname='public'"
                                )
                            )
                        )
                    ).scalars()
                )
                assert {
                    "native_attempt",
                    "native_invocation",
                    "native_input_delivery",
                } <= table_names
            terminal = JarvisTerminal.model_validate(
                {
                    "response": {
                        "type": "waiting",
                        "text": "the draft is waiting for approval.",
                    },
                    "input_outcomes": [
                        {
                            "input_id": str(first.message.id),
                            "disposition": "waiting",
                            "wait_reason": "approval",
                            "action_refs": [str(uuid4())],
                        }
                    ],
                }
            )
            rendered = render_terminal(terminal, TurnEvidence())
            assert rendered.content == "the draft is waiting for approval."
            print("request state, native schema and waiting final: GREEN")
    finally:
        await engine.dispose()


asyncio.run(main())
