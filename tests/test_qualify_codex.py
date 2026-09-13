"""Current Main over real PostgreSQL and a public provider fixture."""

from __future__ import annotations

import base64
import json
import os
import stat
from collections.abc import AsyncIterator
from pathlib import Path
from runpy import run_path
from typing import cast
from uuid import uuid4

import httpx
import pytest
from llm_agent_kernel import StructuredOutput, ThreadId
from provider_fixture import frozen_provider
from provider_runtime.agent_runtime import (
    AgentEvent,
    AgentRuntime,
    AgentSession,
    AgentSessionRef,
    AgentSessionRequest,
    AgentTerminal,
    TurnRequest,
    freeze_json_object,
)
from provider_runtime.agent_runtime.codex_control import CodexControl
from provider_runtime.types import Absent, CancelSignal
from pydantic import SecretStr
from test_codex_control import host_config

from jarvis.admission import RollingAdmissionLimits, RollingAdmissionPort
from jarvis.config import DiscordSettings
from jarvis.db import create_engine
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import build_kernel_runtime
from jarvis.messages import MessageStore
from jarvis.ownership import deployment_ownership
from jarvis.settings import Settings
from jarvis.terminal import JarvisTerminal

QUALIFIER = run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/qualify_codex.py")
)
DATABASE_URL = os.environ.get("JARVIS_TEST_DATABASE_URL")


class _Provider:
    """Only the external provider API is synthetic; Jarvis composition is real."""

    codex = CodexControl({}, lambda _: False)

    def __init__(self) -> None:
        self.turns = 0

    async def open_session(self, request: AgentSessionRequest) -> AgentSession:
        return AgentSession(
            AgentSessionRef(
                "agent-session-ref.v1",
                "codex",
                "sdk",
                "consumer-main",
                request.auth.profile_key,
                "1" * 64,
                "2" * 64,
            )
        )

    async def stream_turn(
        self,
        session: AgentSession,
        request: TurnRequest,
        *,
        approvals: object | None = None,
        cancel: CancelSignal | None = None,
    ) -> AsyncIterator[AgentEvent]:
        del request, approvals, cancel
        self.turns += 1
        yield AgentTerminal(
            status="succeeded",
            failure=None,
            final_text="untrusted projection",
            session_ref=session.ref,
            structured_output=freeze_json_object(
                {
                    "type": "finish",
                    "say": None,
                    "call_tool": None,
                    "finish": {
                        "reason": None,
                        "result": {
                            "response": {
                                "type": "answered",
                                "text": "consumer marker",
                            }
                        },
                    },
                }
            ),
            usage=Absent(),
        )

    async def close_session(self, session: AgentSession) -> None:
        del session

    async def close(self) -> None:
        pass


@pytest.mark.postgres
@pytest.mark.skipif(
    DATABASE_URL is None, reason="JARVIS_TEST_DATABASE_URL is not configured"
)
async def test_consumer_uses_current_structured_main_and_real_canonical_settlement(
    tmp_path: Path,
) -> None:
    assert DATABASE_URL is not None
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    cwd = tmp_path / "cwd"
    cwd.mkdir(mode=0o2750)
    # Temporary directories may inherit a group outside the test user's groups.
    os.chown(cwd, -1, os.getegid())
    cwd.chmod(0o2750)
    assert stat.S_IMODE(cwd.stat().st_mode) == 0o2750
    key = base64.urlsafe_b64encode(b"q" * 32).decode().rstrip("=")
    settings = Settings(
        database_url=SecretStr(DATABASE_URL),
        discord=DiscordSettings(
            bot_token=SecretStr("synthetic"),
            owner_user_id=1,
            guild_id=2,
            channel_id=uuid4().int % 900_000_000_000_000_000 + 1,
        ),
        owner_timezone="UTC",
        codex_profile_key="personal",
        codex_model="gpt-5.6-terra",
        agent_cli_path=tmp_path / "skid",
        agent_client_config_path=tmp_path / "agent-client.json",
        codex_host_config_path=tmp_path / "host.json",
        runtime_state_directory=state,
        google_oauth_state_path=state / "google.json",
        google_oauth_client_id=SecretStr("synthetic"),
        google_oauth_client_secret=SecretStr("synthetic"),
        verified_owner_only_calendar_ids=("primary",),
        connector_encryption_key_version="v2",
        connector_encryption_keys=SecretStr(json.dumps({"v2": key})),
        connector_encryption_secret=SecretStr(key),
        maps_api_key=SecretStr("synthetic"),
        brave_api_key=SecretStr("synthetic"),
        embedding_openai_api_key=SecretStr("synthetic"),
    )
    admission_limits = RollingAdmissionLimits()
    RollingAdmissionPort.initialize(settings.admission_journal_path, admission_limits)
    provider = _Provider()
    runtime = build_kernel_runtime(
        runtime=cast(AgentRuntime, provider),
        shared_cwd_parent=cwd,
        session_ref_path=settings.session_reference_path,
    )
    raw_engine = create_engine(DATABASE_URL)
    try:
        async with deployment_ownership(raw_engine) as engine:
            store = MessageStore(engine)
            history = PostgresCanonicalHistory(engine)
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _: pytest.fail("zero-tool consumer must not call connectors")
                ),
                trust_env=False,
            ) as client:
                definitions, plan = QUALIFIER["_definitions"](
                    engine=engine,
                    settings=settings,
                    host=host_config(tmp_path),
                    runtime=cast(AgentRuntime, provider),
                    provider=frozen_provider("personal"),
                    http_client=client,
                )
                assert isinstance(definitions.main.output_contract, StructuredOutput)
                assert definitions.main.output_contract.result_type is JarvisTerminal
                assert plan.profile.ordered_grants == ()
                metric, response = await QUALIFIER["_conversation_turn"](
                    engine=engine,
                    settings=settings,
                    runtime=runtime,
                    definitions=definitions,
                    plan=plan,
                    admission_limits=admission_limits,
                    store=store,
                    history=history,
                    source_message_id=f"consumer-{uuid4()}",
                    text="Answer briefly.",
                )
            assert response == "consumer marker"
            assert metric["status"] == "passed"
            assert provider.turns == 1
            conversation_id = str(settings.discord.channel_id)
            assert not await store.has_pending_work(
                source_conversation_id=conversation_id
            )
            delivered = await store.pending_delivery(
                source_conversation_id=conversation_id, limit=2
            )
            assert [value.text for value in delivered] == ["consumer marker"]
            completed = await history.completed_history(
                ThreadId(conversation_id), exclude_input_ids=(), limit=3
            )
            assert [(value.role, value.text) for value in completed] == [
                ("owner", "Answer briefly."),
                ("assistant", "consumer marker"),
            ]
    finally:
        await runtime.close()
        await raw_engine.dispose()
