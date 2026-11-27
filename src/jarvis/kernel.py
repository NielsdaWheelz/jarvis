from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
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
    AgentModelCatalog,
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
from provider_runtime.types import Present

from jarvis.codex_config import (
    CodexHostConfig,
    NativeRoute,
    canonical_absolute_path,
)
from jarvis.definitions import load_session_manifest, verify_runtime_dependencies

LOGGER = logging.getLogger(__name__)
type CodexRole = Literal["main", "compactor", "dreamer"]
INCLUDED_EXHAUSTED = frozenset({"included_exhausted", "credits_available"})
_OPENING_FAILED = "opening_failed"


@dataclass(frozen=True, slots=True)
class SelectedRoute:
    route: NativeRoute
    provider: ProviderConfiguration


@dataclass(frozen=True, slots=True)
class DeferredRoute:
    route: NativeRoute
    reason: str
    observed_at: datetime
    reset_at: datetime | None = None

    @classmethod
    def opening_failure(cls, route: NativeRoute) -> DeferredRoute:
        return cls(route, _OPENING_FAILED, datetime.now(UTC))


class RouteSelector:
    """Choose one route for a new opening from current admission evidence."""

    def __init__(
        self,
        runtime: AgentRuntime,
        host: CodexHostConfig,
        *,
        paid_ready: Callable[[], Awaitable[DeferredRoute | None]] | None = None,
    ) -> None:
        self._runtime = runtime
        self._primary = host.personal
        self._paid_ready = paid_ready
        self._primary_available: tuple[datetime, int, int] | None = None
        self._last_personal: CodexAllowance | DeferredRoute | None = None
        self._status: dict[tuple[CodexRole, NativeRoute | None], tuple[str, str]] = {}

    async def observe_personal(self) -> CodexAllowance | DeferredRoute:
        account = self._primary
        try:
            result = await self._runtime.codex.observe_codex_allowance(
                "personal",
                CodexSubject(
                    account.expected_user_id,
                    account.expected_account_id,
                    account.expected_plan_type,
                ),
                allow_existing_credits=account.allow_existing_credits,
            )
        except (AgentRuntimeDefect, AgentRuntimeError, OSError):
            result = DeferredRoute(
                "personal", "allowance_unverified", datetime.now(UTC)
            )
        else:
            if result.profile != "personal":
                result = DeferredRoute(
                    "personal", "identity_unverified", datetime.now(UTC)
                )
        self._last_personal = result
        if isinstance(result, DeferredRoute):
            self._primary_available = None
            return result
        if result.state == "available":
            try:
                socket = account.socket.stat()
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

    def describe_deferral(
        self, route: DeferredRoute, pinned: NativeRoute | None
    ) -> DeferredRoute:
        """Project the reason of this cohort without exposing admission evidence."""
        personal = self._last_personal
        if (
            route.reason != _OPENING_FAILED
            and pinned in {None, "personal"}
            and isinstance(personal, CodexAllowance)
            and personal.state in INCLUDED_EXHAUSTED | {"workspace_limit"}
        ):
            return replace(route, reason="quota", reset_at=personal.reset_at)
        return replace(
            route,
            reason="quota" if route.reason == "prepaid_depleted" else "unavailable",
            reset_at=None,
        )

    async def included_exhausted(self, route: NativeRoute) -> bool:
        if route != "personal":
            return False
        evidence = await self.observe_personal()
        return (
            isinstance(evidence, CodexAllowance)
            and evidence.state in INCLUDED_EXHAUSTED
        )

    def opening_failed(self, route: NativeRoute) -> None:
        if route == "personal":
            self._primary_available = None

    async def choose_route(
        self,
        role: CodexRole,
        *,
        pinned: NativeRoute | None = None,
    ) -> SelectedRoute | DeferredRoute:
        if pinned == "google_neon":
            if role != "main":
                raise ValueError("only main can open on google_neon")
            result = await self._select_paid()
        else:
            evidence = await self.observe_personal()
            if isinstance(evidence, DeferredRoute):
                result = evidence
            elif (
                role == "main"
                and pinned is None
                and evidence.state in INCLUDED_EXHAUSTED
            ):
                result = await self._select_paid()
            elif evidence.state in {"available", "available_with_credits"} or (
                evidence.state == "unavailable"
                and self._primary_grace(evidence.observed_at)
            ):
                try:
                    provider = (
                        await resolve_role_providers(self._runtime, "personal", role)
                    )[role]
                except (AgentRuntimeDefect, AgentRuntimeError, OSError, ValueError):
                    self._primary_available = None
                    result = DeferredRoute(
                        "personal", "catalog_unverified", evidence.observed_at
                    )
                else:
                    result = SelectedRoute("personal", provider)
            else:
                result = DeferredRoute(
                    "personal", evidence.state, evidence.observed_at, evidence.reset_at
                )

        reason = result.reason if isinstance(result, DeferredRoute) else "selected"
        status = (result.route, reason)
        if self._status.get((role, pinned)) != status:
            self._status[role, pinned] = status
            LOGGER.info(
                "route admission: role=%s pinned=%s route=%s state=%s "
                "observed_at=%s reset_at=%s",
                role,
                pinned,
                result.route,
                reason,
                result.observed_at.isoformat()
                if isinstance(result, DeferredRoute)
                else None,
                result.reset_at.isoformat()
                if isinstance(result, DeferredRoute) and result.reset_at is not None
                else None,
            )
        return result

    async def _select_paid(self) -> SelectedRoute | DeferredRoute:
        if self._paid_ready is None:
            return DeferredRoute("google_neon", "route_unavailable", datetime.now(UTC))
        try:
            blocked = await self._paid_ready()
        except (AgentRuntimeDefect, AgentRuntimeError, OSError, ValueError):
            return DeferredRoute(
                "google_neon", "capacity_unverified", datetime.now(UTC)
            )
        if blocked is not None:
            return blocked
        try:
            candidate = await resolve_neon_provider(self._runtime)
        except (AgentRuntimeDefect, AgentRuntimeError, OSError, ValueError):
            return DeferredRoute("google_neon", "catalog_unverified", datetime.now(UTC))
        return SelectedRoute("google_neon", candidate)

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


async def resolve_role_providers(
    runtime: AgentRuntime, profile_key: Literal["personal"], *role_ids: str
) -> dict[str, ProviderConfiguration]:
    """Resolve the personal release roles against the authenticated catalog."""
    auth = CredentialRef("local_account", profile_key)
    catalog = await runtime.model_catalog("codex", auth, transport="sdk")
    roles = load_session_manifest().roles
    return {
        role_id: _catalog_provider(
            catalog, auth, roles[role_id].model, roles[role_id].effort
        )
        for role_id in role_ids
    }


async def resolve_neon_provider(runtime: AgentRuntime) -> ProviderConfiguration:
    """Resolve and qualify the one paid model and its child efforts."""
    auth = CredentialRef("host_managed", "google_neon")
    catalog = await runtime.model_catalog("codex", auth, transport="sdk")
    contract = load_session_manifest().google_neon
    if catalog.native_revision != Present(contract.catalog_revision):
        raise ValueError("neon catalog revision differs from the release pin")
    provider = _catalog_provider(catalog, auth, contract.model, contract.effort)
    (row,) = catalog.models
    if {(option.key, option.native_wire_value) for option in row.reasoning} != {
        (effort, effort) for effort in contract.child_efforts
    } or len(row.reasoning) != len(contract.child_efforts):
        raise ValueError("neon catalog child efforts differ from the release pin")
    return provider


def _catalog_provider(
    catalog: AgentModelCatalog, auth: CredentialRef, model: str, effort: str
) -> ProviderConfiguration:
    rows = [row for row in catalog.models if row.key == model]
    if len(rows) != 1 or not rows[0].offered or rows[0].dispatch_model != model:
        raise ValueError(f"codex catalog requires exact offered model {model}")
    row = rows[0]
    options = [option for option in row.reasoning if option.key == effort]
    if len(options) != 1 or options[0].native_wire_value != effort:
        raise ValueError(f"codex catalog requires exact {effort} effort on {model}")
    return ProviderConfiguration(
        auth=auth,
        model_key=row.key,
        reasoning=effort,
        agent_definition_revision=catalog.definition_revision,
        row_fingerprint=row.row_fingerprint,
        native=replace(CODEX_NATIVE_OPTIONS, archive_internal=True),
    )


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
    neon_origin: str | None = None,
) -> AgentRuntime:
    verify_runtime_dependencies()
    return AgentRuntime(
        AgentRuntimeConfig(
            state_root_base=provider_state_root,
            codex_endpoints={
                name: CodexUnixEndpoint(path) for name, path in codex_endpoints.items()
            },
            max_turn_seconds=300.0,
            codex_neon_origin=neon_origin,
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
    "resolve_neon_provider",
    "resolve_role_providers",
]
