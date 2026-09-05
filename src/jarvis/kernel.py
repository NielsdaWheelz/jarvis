from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Never

from llm_agent_kernel import (
    AgentDefinition,
    CancellationToken,
    CodexProvider,
    KernelLimits,
    SessionCoordinator,
    StaleSessionRef,
    StaleSessionReference,
    ThreadId,
    ToolDispatchDefect,
    ToolDispatchLineage,
)
from llm_tools import BudgetState, FrozenToolPlan, ToolBinding
from provider_runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig

from jarvis.definitions import (
    DEFAULT_NATIVE_CONTEXT_LIMITS,
    NativeContextLimits,
    session_generation_limit,
    verify_runtime_dependencies,
)
from jarvis.session import AtomicSessionRefPort


class EmptySlice1Dispatcher:
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
        raise ToolDispatchDefect("Slice 1 has no model-callable tools")


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
        stored = await self.references.load_for_discard(
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


def build_kernel_runtime(
    *,
    provider_state_root: Path,
    private_cwd_parent: Path,
    session_ref_path: Path,
    model: str,
    kernel_limits: KernelLimits,
    native_limits: NativeContextLimits = DEFAULT_NATIVE_CONTEXT_LIMITS,
    verify_dependencies: bool = True,
) -> KernelRuntime:
    if verify_dependencies:
        verify_runtime_dependencies()
    runtime = AgentRuntime(
        AgentRuntimeConfig(
            state_root_base=provider_state_root,
            max_turn_seconds=300.0,
        )
    )
    provider = CodexProvider(
        runtime,
        cwd_parent=private_cwd_parent,
        cache_continuing=False,
    )
    references = AtomicSessionRefPort(
        session_ref_path,
        max_generations=session_generation_limit(
            model,
            kernel_limits=kernel_limits,
            native_limits=native_limits,
        ),
    )
    return KernelRuntime(
        runtime,
        provider,
        SessionCoordinator(provider, references),
        references,
    )


__all__ = ["EmptySlice1Dispatcher", "KernelRuntime", "build_kernel_runtime"]
