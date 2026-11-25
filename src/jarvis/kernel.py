from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Never

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
    AgentRuntimeDefect,
    AgentRuntimeError,
    CodexAllowance,
    CodexSubject,
    CodexUnixEndpoint,
    CredentialRef,
    PermissionPolicy,
    UnsafeConfirmation,
)

from jarvis.codex_config import CodexHostConfig, CodexProfile, canonical_absolute_path
from jarvis.definitions import load_session_manifest, verify_runtime_dependencies

LOGGER = logging.getLogger(__name__)
type CodexRole = Literal["main", "compactor", "dreamer"]


@dataclass(frozen=True, slots=True)
class SelectedCodex:
    profile: CodexProfile
    provider: ProviderConfiguration


@dataclass(frozen=True, slots=True)
class CodexBlocked:
    profile: CodexProfile
    reason: str
    observed_at: datetime
    reset_at: datetime | None = None


class CodexStandby:
    """Admit new Jarvis runs from the contained account order."""

    def __init__(self, runtime: AgentRuntime, host: CodexHostConfig) -> None:
        self._runtime = runtime
        self._host = host
        self._primary = host.accounts[0]
        self._subjects: dict[CodexProfile, CodexSubject] = {
            account.key: CodexSubject(
                account.expected_user_id,
                account.expected_account_id,
                account.expected_plan_type,
            )
            for account in host.accounts
        }
        self._primary_available: tuple[datetime, int, int] | None = None
        self._status: dict[tuple[CodexRole, CodexProfile | None], tuple[str, str]] = {}

    async def observe(self, profile: CodexProfile) -> CodexAllowance | CodexBlocked:
        try:
            result = await self._runtime.codex.observe_codex_allowance(
                profile, self._subjects[profile]
            )
        except (AgentRuntimeDefect, AgentRuntimeError, OSError):
            if profile == self._primary.key:
                self._primary_available = None
            return CodexBlocked(profile, "allowance_unverified", datetime.now(UTC))
        if result.profile != profile:
            self._primary_available = None
            return CodexBlocked(profile, "identity_unverified", datetime.now(UTC))
        if profile == self._primary.key:
            if result.state == "available":
                try:
                    socket = self._primary.socket.stat()
                except OSError:
                    self._primary_available = None
                else:
                    self._primary_available = (
                        result.observed_at,
                        socket.st_dev,
                        socket.st_ino,
                    )
            elif result.state != "unavailable":
                self._primary_available = None
        return result

    def opening_failed(self, profile: CodexProfile) -> None:
        if profile == self._primary.key:
            self._primary_available = None

    async def choose_codex(
        self, role: CodexRole, *, pinned_profile: CodexProfile | None = None
    ) -> SelectedCodex | CodexBlocked:
        profiles = (
            (pinned_profile,) if pinned_profile is not None else tuple(self._subjects)
        )
        failure = CodexBlocked(
            self._primary.key, "allowance_unverified", datetime.now(UTC)
        )
        for profile in profiles:
            evidence = await self.observe(profile)
            if isinstance(evidence, CodexBlocked):
                failure = evidence
                break
            reason = evidence.state
            failure = CodexBlocked(
                profile, reason, evidence.observed_at, evidence.reset_at
            )
            if reason == "included_exhausted":
                continue
            if reason != "available" and not (
                profile == self._primary.key
                and reason == "unavailable"
                and self._primary_grace(evidence.observed_at)
            ):
                break
            try:
                selected = (await resolve_role_providers(self._runtime, profile, role))[
                    role
                ]
            except (AgentRuntimeDefect, AgentRuntimeError, OSError, ValueError):
                if profile == self._primary.key:
                    self._primary_available = None
                failure = CodexBlocked(
                    profile, "catalog_unverified", evidence.observed_at
                )
                break
            if role == "main":
                selected = main_provider_configuration(
                    selected, notes_repository=self._host.notes_repository
                )
            self._log_selection(
                role, pinned_profile, profile, "selected", evidence.observed_at
            )
            return SelectedCodex(profile, selected)
        self._log_selection(
            role,
            pinned_profile,
            failure.profile,
            failure.reason,
            failure.observed_at,
            failure.reset_at,
        )
        return failure

    def _primary_grace(self, observed_at: datetime) -> bool:
        if self._primary_available is None:
            return False
        previous, device, inode = self._primary_available
        try:
            socket = self._primary.socket.stat()
        except OSError:
            self._primary_available = None
            return False
        if (socket.st_dev, socket.st_ino) != (device, inode):
            self._primary_available = None
            return False
        return timedelta(0) <= observed_at - previous < timedelta(seconds=60)

    def _log_selection(
        self,
        role: CodexRole,
        pinned_profile: CodexProfile | None,
        profile: str,
        reason: str,
        observed_at: datetime,
        reset_at: datetime | None = None,
    ) -> None:
        status = (profile, reason)
        if self._status.get((role, pinned_profile)) != status:
            self._status[role, pinned_profile] = status
            LOGGER.info(
                "codex admission: role=%s retry_account=%s account=%s state=%s "
                "observed_at=%s reset_at=%s",
                role,
                pinned_profile,
                profile,
                reason,
                observed_at.isoformat(),
                None if reset_at is None else reset_at.isoformat(),
            )


async def resolve_role_providers(
    runtime: AgentRuntime, profile_key: str, *role_ids: str
) -> dict[str, ProviderConfiguration]:
    """Resolve the release roles against one authenticated endpoint catalog."""
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
                f"codex catalog requires one offered {role.model} "
                f"row with identical dispatch for {role_id}"
            )
        row = rows[0]
        options = [option for option in row.reasoning if option.key == role.effort]
        if len(options) != 1 or options[0].native_wire_value != role.effort:
            raise ValueError(
                f"codex catalog requires exact {role.effort} effort "
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
