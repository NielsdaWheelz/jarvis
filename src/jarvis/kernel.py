from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Never

from llm_agent_kernel import (
    CODEX_NATIVE_OPTIONS,
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
    CodexUnixEndpoint,
    CredentialRef,
    PermissionPolicy,
    UnsafeConfirmation,
)

from jarvis.codex_config import canonical_absolute_path
from jarvis.definitions import load_session_manifest, verify_runtime_dependencies


async def resolve_role_providers(
    runtime: AgentRuntime, profile_key: str, *role_ids: str
) -> dict[str, ProviderConfiguration]:
    """Resolve the release roles against one authenticated personal catalog."""
    if profile_key != "personal":
        raise ValueError("codex model selection requires the personal subscription")
    auth = CredentialRef("local_account", profile_key)
    catalog = await runtime.model_catalog("codex", auth, transport="sdk")
    roles = load_session_manifest().roles
    providers: dict[str, ProviderConfiguration] = {}
    for role_id in role_ids:
        role = roles[role_id]
        rows = [row for row in catalog.models if row.key == role.model]
        if (
            len(rows) != 1
            or not rows[0].offered
            or rows[0].dispatch_model != role.model
        ):
            raise ValueError(
                f"personal codex catalog requires one offered {role.model} "
                f"row with identical dispatch for {role_id}"
            )
        row = rows[0]
        options = [option for option in row.reasoning if option.key == role.effort]
        if len(options) != 1 or options[0].native_wire_value != role.effort:
            raise ValueError(
                f"personal codex catalog requires exact {role.effort} effort "
                f"for {role_id} on {role.model}"
            )
        providers[role_id] = ProviderConfiguration(
            auth=auth,
            model_key=row.key,
            reasoning=role.effort,
            agent_definition_revision=catalog.definition_revision,
            row_fingerprint=row.row_fingerprint,
            native=replace(CODEX_NATIVE_OPTIONS, archive_internal=True),
        )
    return providers


def main_provider_configuration(
    base_provider: ProviderConfiguration, *, notes_repository: str
) -> ProviderConfiguration:
    """Derive main's native authority from its own authenticated selection."""
    repository = canonical_absolute_path(notes_repository)
    return replace(
        base_provider,
        cwd=repository,
        additional_dirs=(f"{repository}/.git",),
        policy=PermissionPolicy(
            filesystem="workspace_write",
            network="unrestricted",
            approval="deny",
            allowed_tools=("*",),
            unsafe_confirmation=UnsafeConfirmation(("network_unrestricted",)),
        ),
        native=replace(base_provider.native, builtin_tools=None),
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
            codex_endpoints={
                name: CodexUnixEndpoint(path) for name, path in codex_endpoints.items()
            },
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
    "main_provider_configuration",
    "resolve_role_providers",
]
