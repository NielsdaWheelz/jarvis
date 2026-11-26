"""Current native message and scoped plan contracts."""

from dataclasses import replace
from typing import Self

from llm_agent_kernel import (
    CODEX_NATIVE_OPTIONS,
    CONTAINMENT_POLICY,
    NativeDefinition,
    ProviderConfiguration,
)
from llm_tools import (
    CapabilityProfile,
    FrozenToolPlan,
    Native,
    ProfileId,
    ToolCatalog,
    ToolEffect,
    ToolGrant,
    ToolId,
    ToolPlan,
)
from provider_runtime.agent_runtime import TextContent
from pydantic import model_validator

from jarvis import terminal
from jarvis.home_refs import SourceRef
from jarvis.workspace_checks import WorkspaceResult

NATIVE_REQUEST_SCHEMA = "jarvis-native-request.v8"
NATIVE_OUTPUT_NAME = "jarvis_home_message_v5"
WORKSPACE_CHECK_PROFILE = ProfileId("workspace_check")
FOREGROUND_RECOVERY_PROFILE = ProfileId("foreground_recovery")


def workspace_check_native(
    main: NativeDefinition, main_plan: FrozenToolPlan, catalog: ToolCatalog
) -> tuple[NativeDefinition, FrozenToolPlan]:
    """Publish only named check reads inside the provider's contained session."""
    return _read_only_native(
        main,
        main_plan,
        catalog,
        WORKSPACE_CHECK_PROFILE,
        (
            "calendar.get_event",
            "calendar.list_events",
            "gmail.get_message",
            "gmail.read_thread",
            "gmail.search",
            "receipt.read",
            "work.get",
        ),
    )


def foreground_recovery_native(
    main: NativeDefinition, main_plan: FrozenToolPlan, catalog: ToolCatalog
) -> tuple[NativeDefinition, FrozenToolPlan]:
    instructions = TextContent(
        "recover only the delivered input's independently useful result. "
        "use original receipts for prior effects. distinguish the missing answer "
        "from an unknown "
        "effect. report only observed coverage and keep any request whose outcome "
        "remains unfinished open. do not propose a new action or publish progress."
    )
    main = replace(
        main,
        provider=replace(
            main.provider,
            developer=(*main.provider.developer, instructions),
        ),
    )
    return _read_only_native(
        main,
        main_plan,
        catalog,
        FOREGROUND_RECOVERY_PROFILE,
        (
            "calendar.get_event",
            "gmail.get_message",
            "receipt.read",
            "web.read",
            "web.search",
        ),
    )


def _read_only_native(
    main: NativeDefinition,
    main_plan: FrozenToolPlan,
    catalog: ToolCatalog,
    profile_id: ProfileId,
    tools: tuple[str, ...],
) -> tuple[NativeDefinition, FrozenToolPlan]:
    tool_ids = tuple(map(ToolId, tools))
    if any(catalog.spec(tool_id).effect is not ToolEffect.Read for tool_id in tool_ids):
        raise ValueError("read-only plan includes a non-read tool")
    profile = CapabilityProfile(
        profile_id,
        tuple(
            ToolGrant(tool_id, main_plan.grant(tool_id).limits) for tool_id in tool_ids
        ),
        main_plan.profile.run_limits,
    ).freeze(catalog)
    plan = ToolPlan(profile.id, Native()).freeze(catalog, profile)
    if not plan.is_tightening_of(main_plan.profile):
        raise ValueError("read-only plan exceeds main authority")
    if not isinstance(main.provider, ProviderConfiguration):
        raise ValueError("read-only plan requires the stock main template")
    provider = replace(
        main.provider,
        cwd=None,
        additional_dirs=(),
        policy=CONTAINMENT_POLICY,
        native=replace(
            CODEX_NATIVE_OPTIONS, archive_internal=main.provider.native.archive_internal
        ),
    )
    return replace(main, provider=provider, maximum_profile=profile), plan


class JarvisNativeMessage(terminal.JarvisNativeMessage):
    sources: list[terminal.Source]
    workspace_result: WorkspaceResult | None

    @model_validator(mode="after")
    def progress_has_no_check_result(self) -> Self:
        if (
            isinstance(self.response, terminal.Progress | terminal.Silent)
            and self.sources
        ):
            raise ValueError("progress and silence have no citations")
        if isinstance(self.response, terminal.Progress) and isinstance(
            self.response.present and self.response.present.ref, SourceRef
        ):
            raise ValueError("a source is presented only by a final")
        if isinstance(self.response, terminal.Progress) and self.workspace_result:
            raise ValueError("progress cannot settle a workspace occurrence")
        return self


class JarvisTerminal(terminal.JarvisTerminal):
    sources: list[terminal.Source]

    @model_validator(mode="after")
    def silent_has_no_sources(self) -> Self:
        if isinstance(self.response, terminal.Silent) and self.sources:
            raise ValueError("silence has no citations")
        return self

    workspace_result: WorkspaceResult | None

    @classmethod
    def from_seal(cls, name: str, value: object) -> Self:
        if name != NATIVE_OUTPUT_NAME:
            raise ValueError("unrecognized native seal contract")
        return cls.model_validate(value)
