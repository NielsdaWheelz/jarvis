"""Current native messages and the read-only decoder for predecessor seals."""

from dataclasses import replace
from typing import Self

from llm_agent_kernel import CODEX_NATIVE_OPTIONS, CONTAINMENT_POLICY, NativeDefinition
from llm_tools import (
    CapabilityProfile,
    FrozenToolPlan,
    Native,
    ProfileId,
    ToolCatalog,
    ToolGrant,
    ToolId,
    ToolPlan,
)
from pydantic import model_validator

from jarvis import terminal
from jarvis.workspace_checks import WorkspaceResult

NATIVE_OUTPUT_NAME = "jarvis_home_message_v3"


def workspace_check_native(
    main: NativeDefinition, catalog: ToolCatalog
) -> tuple[NativeDefinition, FrozenToolPlan]:
    """Publish only named check reads inside the provider's contained session."""
    tools = (
        "calendar.get_event",
        "calendar.list_events",
        "gmail.get_message",
        "gmail.read_thread",
        "gmail.search",
        "receipt.read",
        "work.get",
    )
    profile = CapabilityProfile(
        ProfileId("workspace_check"),
        tuple(ToolGrant(ToolId(tool), None) for tool in tools),
        main.maximum_profile.run_limits,
    ).freeze(catalog)
    plan = ToolPlan(profile.id, Native()).freeze(catalog, profile)
    if not plan.is_tightening_of(main.maximum_profile):
        raise ValueError("standing-check plan exceeds main authority")
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
    workspace_result: WorkspaceResult | None

    @model_validator(mode="after")
    def progress_has_no_check_result(self) -> Self:
        if isinstance(self.response, terminal.Progress) and self.workspace_result:
            raise ValueError("progress cannot settle a workspace occurrence")
        return self


class JarvisTerminal(terminal.JarvisTerminal):
    workspace_result: WorkspaceResult | None

    @classmethod
    def from_seal(cls, name: str, value: object) -> Self:
        if name == terminal.NATIVE_OUTPUT_NAME:
            old = terminal.JarvisTerminal.from_seal(name, value)
            return cls(**old.model_dump(), workspace_result=None)
        if name != NATIVE_OUTPUT_NAME:
            raise ValueError("unrecognized native seal contract")
        return cls.model_validate(value)
