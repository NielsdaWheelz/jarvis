from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Never

from llm_agent_kernel import (
    AgentDefinition,
    CancellationToken,
    CodexProvider,
    ProviderConfiguration,
    SessionCoordinator,
    StaleSessionRef,
    StaleSessionReference,
    ThreadId,
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
from jarvis.session import AtomicSessionRefPort


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
    sessions: SessionCoordinator
    references: AtomicSessionRefPort

    async def close(self) -> None:
        try:
            await self.provider.shutdown()
        finally:
            await self.runtime.close()

    async def discard_recovered_session_reference(
        self,
        thread_id: ThreadId,
        definition: AgentDefinition,
    ) -> None:
        stored = await self.references.load(
            thread_id,
            definition.fingerprint,
        )
        if stored is None:
            return
        try:
            discarded = await self.references.discard(
                thread_id,
                definition.fingerprint,
                stored.generation,
            )
        except BaseException:
            await self.provider.discard_reference(definition.fingerprint, stored.ref)
            raise
        if isinstance(discarded, StaleSessionRef):
            await self.provider.discard_reference(definition.fingerprint, stored.ref)
            raise StaleSessionReference(
                "session reference changed during recovered-control discard"
            )
        await self.provider.discard_reference(definition.fingerprint, stored.ref)


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
    session_ref_path: Path,
) -> KernelRuntime:
    provider = CodexProvider(
        runtime,
        cwd_parent=shared_cwd_parent,
        share_cwd_with_group=True,
        cache_continuing=False,
    )
    references = AtomicSessionRefPort(session_ref_path)
    return KernelRuntime(
        runtime,
        provider,
        SessionCoordinator(provider, references),
        references,
    )


__all__ = [
    "EmptyToolDispatcher",
    "KernelRuntime",
    "build_agent_runtime",
    "build_kernel_runtime",
    "resolve_provider_configuration",
]
