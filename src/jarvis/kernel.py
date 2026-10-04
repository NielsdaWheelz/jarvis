from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Never

from llm_agent_kernel import (
    CancellationToken,
    CodexProvider,
    ProviderConfiguration,
    ToolDispatchDefect,
    ToolDispatchLineage,
)
from llm_tools import BudgetState, FrozenToolPlan, ToolBinding
from provider_runtime.agent_runtime import (
    AgentRuntime,
    AgentRuntimeConfig,
    CredentialRef,
)

from jarvis.definitions import (
    QUALIFIED_CODEX_MODELS,
    verify_runtime_dependencies,
)


async def resolve_provider_configuration(
    *,
    runtime: AgentRuntime,
    profile_key: str,
    model_key: str,
    reasoning: str = "high",
) -> ProviderConfiguration:
    """Freeze one qualified selection from the owner's authenticated native catalog."""
    if model_key not in QUALIFIED_CODEX_MODELS:
        raise ValueError("model is not a qualified Jarvis route")
    auth = CredentialRef("local_account", profile_key)
    catalog = await runtime.model_catalog("codex", auth, transport="sdk")
    matches = tuple(row for row in catalog.models if row.key == model_key)
    if len(matches) != 1:
        raise ValueError("model is absent or ambiguous in the authenticated catalog")
    row = matches[0]
    if sum(option.key == reasoning for option in row.reasoning) != 1:
        raise ValueError("reasoning is unsupported in the authenticated model catalog")
    return ProviderConfiguration(
        auth=auth,
        model_key=row.key,
        reasoning=reasoning,
        agent_definition_revision=catalog.definition_revision,
        row_fingerprint=row.row_fingerprint,
    )


class EmptyToolDispatcher:
    async def dispatch(
        self,
        *,
        binding: ToolBinding[Any, Any, Any],
        validated_input: object,
        plan: FrozenToolPlan,
        budgets: BudgetState,
        cancellation: CancellationToken,
        lineage: ToolDispatchLineage,
    ) -> Never:
        del binding, validated_input, plan, budgets, cancellation, lineage
        raise ToolDispatchDefect("an empty tool plan cannot dispatch a tool")


@dataclass(slots=True)
class KernelRuntime:
    runtime: AgentRuntime
    provider: CodexProvider

    async def close(self) -> None:
        try:
            await self.provider.shutdown()
        finally:
            await self.runtime.close()


def build_agent_runtime(
    *,
    provider_state_root: Path,
    codex_endpoints: Mapping[str, Path],
) -> AgentRuntime:
    verify_runtime_dependencies()
    return AgentRuntime(
        AgentRuntimeConfig(
            state_root_base=provider_state_root,
            codex_endpoints=codex_endpoints,
            max_turn_seconds=300.0,
        )
    )


def build_kernel_runtime(
    *,
    runtime: AgentRuntime,
    shared_cwd_parent: Path,
) -> KernelRuntime:
    provider = CodexProvider(
        runtime,
        cwd_parent=shared_cwd_parent,
        share_cwd_with_group=True,
    )
    return KernelRuntime(runtime, provider)


__all__ = [
    "EmptyToolDispatcher",
    "KernelRuntime",
    "build_agent_runtime",
    "build_kernel_runtime",
    "resolve_provider_configuration",
]
