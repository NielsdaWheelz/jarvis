"""Startup freezes the exact catalog row from the shared host runtime."""

from __future__ import annotations

from pathlib import Path

import pytest
from provider_runtime.agent_runtime import CredentialRef
from provider_runtime.agent_runtime.codex_control import CodexListRequest
from test_codex_control import THREAD, protocol_peer

from jarvis.kernel import build_agent_runtime, resolve_provider_configuration


async def test_authenticated_selection_keeps_shared_runtime_and_high_default(
    tmp_path: Path,
) -> None:
    async with protocol_peer() as (root, external):
        async with build_agent_runtime(
            provider_state_root=tmp_path,
            codex_endpoints={"personal": root / "work.sock"},
            verify_dependencies=False,
        ) as runtime:
            selected = await resolve_provider_configuration(
                runtime=runtime,
                profile_key="personal",
                model_key="gpt-5.6-terra",
            )
            observed = await runtime.model_catalog("codex", selected.auth)
            assert selected.model_key == "gpt-5.6-terra"
            assert selected.reasoning == "high", (
                "native default replaced Jarvis's explicit policy"
            )
            assert selected.auth == CredentialRef("local_account", "personal")
            assert selected.agent_definition_revision == observed.definition_revision
            assert selected.row_fingerprint == observed.models[0].row_fingerprint
            workers = await runtime.codex.list(CodexListRequest("personal"))
            assert workers.threads[0].target.thread_handle == THREAD
            assert external.methods.count("model/list") == 2
            assert "thread/start" not in external.methods


@pytest.mark.parametrize("failure", ("missing_model", "unsupported_reasoning"))
async def test_provider_configuration_refuses_unavailable_exact_selection(
    tmp_path: Path, failure: str
) -> None:
    async with protocol_peer() as (root, external):
        if failure == "missing_model":
            external.models[0]["id"] = "unqualified-model"
        else:
            external.models[0]["supportedReasoningEfforts"] = [
                {"reasoningEffort": "low", "description": "Low"}
            ]
        async with build_agent_runtime(
            provider_state_root=tmp_path,
            codex_endpoints={"personal": root / "work.sock"},
            verify_dependencies=False,
        ) as runtime:
            with pytest.raises(ValueError, match="authenticated"):
                await resolve_provider_configuration(
                    runtime=runtime,
                    profile_key="personal",
                    model_key="gpt-5.6-terra",
                )
            assert external.methods.count("model/list") == 1
            assert "thread/start" not in external.methods
