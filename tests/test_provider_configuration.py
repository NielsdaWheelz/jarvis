"""Startup selects an exact authenticated model and reasoning row."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from provider_fixture import frozen_provider
from provider_runtime.agent_runtime import AgentRuntimeConfig, CredentialRef
from provider_runtime.agent_runtime.model_catalog import (
    AgentModelCatalog,
    AgentModelFacts,
    AgentReasoningFacts,
)
from provider_runtime.types import Absent, Present

from jarvis import kernel


def _catalog() -> AgentModelCatalog:
    provider = frozen_provider()
    return AgentModelCatalog(
        backend_contract_revision="provider-runtime.agent-model-catalog.v1",
        definition_revision="observed-catalog-revision",
        native_revision=Absent(),
        observed_at=datetime(2026, 9, 9, tzinfo=UTC),
        models=(
            AgentModelFacts(
                key=provider.model_key,
                dispatch_model="native-dispatch-name",
                label="Authenticated model",
                source_context_window=Absent(),
                source_max_output_tokens=Absent(),
                input_modalities=("text",),
                reasoning=(
                    AgentReasoningFacts("low", "Low", "low"),
                    AgentReasoningFacts("high", "High", "high"),
                ),
                source_default_reasoning=Present("low"),
                upgrade=Absent(),
                retirement=Absent(),
                row_fingerprint="b" * 64,
            ),
        ),
        diagnostics=(),
    )


class _CatalogRuntime:
    def __init__(self, catalog: AgentModelCatalog) -> None:
        self.catalog = catalog
        self.closed = False
        self.request: tuple[str, CredentialRef, str] | None = None

    async def __aenter__(self) -> _CatalogRuntime:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self.closed = True

    async def model_catalog(
        self, backend: str, auth: CredentialRef, *, transport: str
    ) -> AgentModelCatalog:
        self.request = backend, auth, transport
        return self.catalog


async def test_authenticated_catalog_keeps_app_high_reasoning_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _CatalogRuntime(_catalog())
    configs: list[AgentRuntimeConfig] = []

    def create_runtime(config: AgentRuntimeConfig) -> _CatalogRuntime:
        configs.append(config)
        return runtime

    monkeypatch.setattr(kernel, "AgentRuntime", create_runtime)
    selected = await kernel.resolve_provider_configuration(
        state_root=tmp_path,
        profile_key="owner-profile",
        model_key="gpt-5.6-terra",
    )
    assert selected.model_key == "gpt-5.6-terra"
    assert selected.reasoning == "high", (
        "native default replaced Jarvis's explicit policy"
    )
    assert selected.agent_definition_revision == "observed-catalog-revision"
    assert selected.row_fingerprint == "b" * 64
    assert selected.auth == CredentialRef("local_account", "owner-profile")
    assert runtime.request == ("codex", selected.auth, "sdk")
    assert configs[0].state_root_base == tmp_path
    assert runtime.closed


@pytest.mark.parametrize("failure", ("missing_model", "unsupported_reasoning"))
async def test_provider_configuration_refuses_unavailable_exact_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    catalog = _catalog()
    if failure == "missing_model":
        catalog = replace(catalog, models=())
    else:
        catalog = replace(
            catalog,
            models=(
                replace(catalog.models[0], reasoning=catalog.models[0].reasoning[:1]),
            ),
        )
    runtime = _CatalogRuntime(catalog)

    def create_runtime(_config: AgentRuntimeConfig) -> _CatalogRuntime:
        return runtime

    monkeypatch.setattr(kernel, "AgentRuntime", create_runtime)
    with pytest.raises(ValueError, match="authenticated"):
        await kernel.resolve_provider_configuration(
            state_root=tmp_path,
            profile_key="owner-profile",
            model_key="gpt-5.6-terra",
        )
    assert runtime.closed
