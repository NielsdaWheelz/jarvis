from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import Annotated, Literal, cast
from uuid import UUID

from llm_agent_kernel import (
    AgentDefinition,
    AgentRole,
    ConversationalOutput,
    DefinitionId,
    KernelLimits,
    ProviderConfiguration,
    SessionMode,
    StructuredOutput,
    provider_wire_schema,
)
from llm_tools import (
    CapabilityProfile,
    FrozenToolPlan,
    HostTable,
    ProfileId,
    PromptAttribute,
    PromptAttributeName,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    RunLimits,
    ToolCatalog,
    ToolPlan,
    canonical_json_bytes,
)
from provider_runtime.agent_runtime import CredentialRef, ReasoningSpec
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, WithJsonSchema

SESSION_MANIFEST_NAME = "session-compatibility.json"
EXPECTED_GIT_PINS = {
    "llm-agent-kernel": "c9eefcb458ee5245010dd5e99b48f7116cd1139a",
    "llm-tools": "728f35c0b3a8be91b380ed4258d2b73ad68fc8fa",
    "provider-runtime": "a5d9c8e0c1c851daee0731554e0a4a326d3c2819",
}
EXPECTED_PACKAGE_VERSIONS = {
    "openai-codex": "0.144.4",
    "openai-codex-cli-bin": "0.144.4",
}
ROUTE_CONTEXT_TOKEN_FLOORS = MappingProxyType(
    {
        "gpt-5.6-terra": 1_050_000,
        "gpt-5.4": 1_050_000,
    }
)

# Slice 1 has no model-callable tools. llm-tools requires positive byte/call
# ceilings even for an empty catalog; zero external attempts makes the plan inert.
SLICE1_TOOL_LIMITS = RunLimits(
    max_calls=1,
    max_external_attempts=0,
    max_input_bytes=4_096,
    max_output_bytes=4_096,
    max_in_flight=1,
    max_elapsed_seconds=30.0,
)
SLICE1_KERNEL_LIMITS = KernelLimits(
    max_provider_turns=3,
    max_protocol_repairs=2,
    max_no_progress_attempts=3,
    max_cooperative_seconds=300.0,
    max_provider_input_tokens=100_000,
    max_provider_output_tokens=20_000,
    max_new_context_bytes=262_144,
)


def _canonical_uuid(value: str) -> str:
    try:
        canonical = str(UUID(value))
    except ValueError as exc:
        raise ValueError("value must be a canonical UUID") from exc
    if value != canonical:
        raise ValueError("value must be a canonical UUID")
    return value


CanonicalUuid = Annotated[
    str,
    AfterValidator(_canonical_uuid),
    WithJsonSchema({"type": "string", "format": "uuid"}),
]


class RecalledMemory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: CanonicalUuid
    text: str = Field(min_length=1, max_length=8_000)
    created_at: str = Field(min_length=1, max_length=64)
    source_memory_ids: list[CanonicalUuid] = Field(max_length=50)


class RecallResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memories: list[RecalledMemory] = Field(max_length=20)


class RememberResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memories: list[str] = Field(max_length=20)


class SummaryInsertion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=8_000)
    source_memory_ids: list[CanonicalUuid] = Field(min_length=1, max_length=100)


class DreamResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    insertions: list[SummaryInsertion] = Field(max_length=50)
    remove_summary_ids: list[CanonicalUuid] = Field(max_length=100)


class AutomaticWriteGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal["allow", "deny"]
    supporting_owner_message_ids: list[CanonicalUuid] = Field(max_length=100)


@dataclass(frozen=True, slots=True)
class NativeContextLimits:
    max_system_bytes: int = 16_384
    max_developer_bytes: int = 16_384
    max_output_schema_bytes: int = 32_768
    one_turn_input_token_overshoot: int = 32_768
    one_turn_output_token_overshoot: int = 8_192

    def __post_init__(self) -> None:
        values = (
            self.max_system_bytes,
            self.max_developer_bytes,
            self.max_output_schema_bytes,
            self.one_turn_input_token_overshoot,
            self.one_turn_output_token_overshoot,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("provider-native context limits must be positive integers")


DEFAULT_NATIVE_CONTEXT_LIMITS = NativeContextLimits()


@dataclass(frozen=True, slots=True)
class Slice1Definitions:
    main: AgentDefinition
    recaller: AgentDefinition
    rememberer: AgentDefinition
    dreamer: AgentDefinition
    automatic_write_gate: AgentDefinition
    plans: Mapping[str, FrozenToolPlan]


def build_slice1_definitions(
    *,
    profile_key: str,
    model: str,
    owner_timezone: str,
    reasoning_effort: str = "high",
    native_limits: NativeContextLimits = DEFAULT_NATIVE_CONTEXT_LIMITS,
) -> Slice1Definitions:
    if not owner_timezone.strip():
        raise ValueError("owner timezone must not be empty")
    if model not in ROUTE_CONTEXT_TOKEN_FLOORS:
        raise ValueError("model is not a qualified Slice 1 route")
    provider = ProviderConfiguration(
        auth=CredentialRef("local_account", profile_key),
        model=model,
        reasoning=ReasoningSpec(reasoning_effort, summary="concise"),
    )
    catalog = ToolCatalog.compose(())
    manifest = load_session_manifest()

    def make(
        role_id: str,
        instructions: str,
        mode: SessionMode,
        output: ConversationalOutput | StructuredOutput,
    ) -> tuple[AgentDefinition, FrozenToolPlan]:
        profile = CapabilityProfile(
            ProfileId(f"slice1_{role_id}"), (), SLICE1_TOOL_LIMITS
        ).freeze(catalog)
        plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
        definition = AgentDefinition(
            definition_id=DefinitionId(f"jarvis-{role_id}"),
            role=AgentRole(role_id, _text_sections("role_instructions", instructions)),
            stable_context=PromptSections(
                (
                    PromptSection(
                        PromptSectionKind("owner_context"),
                        (
                            PromptAttribute(
                                PromptAttributeName("iana_timezone"), owner_timezone
                            ),
                        ),
                        None,
                    ),
                )
            ),
            session_mode=mode,
            output_contract=output,
            maximum_profile=profile,
            provider=provider,
            session_compatibility_revision=session_compatibility_revision(
                manifest, role_id
            ),
            limits=SLICE1_KERNEL_LIMITS,
        )
        validate_native_context_bounds(definition, native_limits)
        return definition, plan

    main, main_plan = make(
        "main",
        "You are Jarvis, one direct and calm personal assistant. Answer the current "
        "conversation using say. Use finish only when no owner-visible response is "
        "useful. "
        "Always use say for a host action-resolution or scheduled-wake input. "
        "Slice 1 grants no tools; never claim that an external action occurred.",
        SessionMode.continuing,
        ConversationalOutput(),
    )
    recaller, recaller_plan = make(
        "recaller",
        "Return only the closed recall result. Slice 1 has no memory tools, so return "
        "an empty memories list.",
        SessionMode.isolated,
        StructuredOutput("jarvis_recall", RecallResult),
    )
    rememberer, rememberer_plan = make(
        "rememberer",
        "Return only the closed remember result. Slice 1 does not persist memory, so "
        "return an empty memories list.",
        SessionMode.isolated,
        StructuredOutput("jarvis_remember", RememberResult),
    )
    dreamer, dreamer_plan = make(
        "dreamer",
        "Return only the closed dream result. Slice 1 has no memory state, so return "
        "empty insertions and removals.",
        SessionMode.isolated,
        StructuredOutput("jarvis_dream", DreamResult),
    )
    gate, gate_plan = make(
        "automatic_write_gate",
        "Return only the closed write-gate result. Slice 1 grants no writes; deny "
        "every proposal and return no supporting owner message IDs.",
        SessionMode.isolated,
        StructuredOutput("jarvis_automatic_write_gate", AutomaticWriteGateResult),
    )
    scheduled_profile = CapabilityProfile(
        ProfileId("slice1_scheduled_wake"), (), SLICE1_TOOL_LIMITS
    ).freeze(catalog)
    scheduled_plan = ToolPlan(scheduled_profile.id, HostTable()).freeze(
        catalog, scheduled_profile
    )
    if not scheduled_plan.is_tightening_of(main.maximum_profile):
        raise ValueError("scheduled-wake plan does not tighten the main envelope")
    return Slice1Definitions(
        main,
        recaller,
        rememberer,
        dreamer,
        gate,
        MappingProxyType(
            {
                "main": main_plan,
                "proactive": scheduled_plan,
                "scheduled_wake": scheduled_plan,
                "recaller": recaller_plan,
                "rememberer": rememberer_plan,
                "dreamer": dreamer_plan,
                "automatic_write_gate": gate_plan,
            }
        ),
    )


def load_session_manifest() -> dict[str, object]:
    raw = files("jarvis").joinpath(SESSION_MANIFEST_NAME).read_text(encoding="utf-8")
    value: object = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("session compatibility manifest has an invalid shape")
    manifest = cast("dict[str, object]", value)
    if set(manifest) != {
        "application_session_contract_revision",
        "dependencies",
        "role_contract_revisions",
        "schema_version",
    }:
        raise ValueError("session compatibility manifest has an invalid shape")
    if manifest["schema_version"] != "jarvis-session-compatibility.v1":
        raise ValueError("session compatibility manifest version is unsupported")
    if manifest["dependencies"] != {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS}:
        raise ValueError(
            "session compatibility manifest dependency pins do not match code"
        )
    return manifest


def session_compatibility_revision(manifest: dict[str, object], role_id: str) -> str:
    role_revisions_value = manifest.get("role_contract_revisions")
    if not isinstance(role_revisions_value, Mapping):
        raise ValueError("session compatibility role manifest is invalid")
    role_revisions = cast("Mapping[str, object]", role_revisions_value)
    if set(role_revisions) != {
        "automatic_write_gate",
        "dreamer",
        "main",
        "recaller",
        "rememberer",
    }:
        raise ValueError("session compatibility role manifest is invalid")
    role_revision = role_revisions.get(role_id)
    application_revision = manifest.get("application_session_contract_revision")
    if type(role_revision) is not str or not role_revision.strip():
        raise ValueError(f"session compatibility role is unknown: {role_id}")
    if type(application_revision) is not str or not application_revision.strip():
        raise ValueError("application session contract revision must not be empty")
    value = {
        "application_session_contract_revision": application_revision,
        "dependencies": manifest["dependencies"],
        "role_contract_revision": role_revision,
        "role_id": role_id,
    }
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_native_context_bounds(
    definition: AgentDefinition, limits: NativeContextLimits
) -> None:
    system_bytes = sum(len(part.text.encode()) for part in definition.provider.system)
    developer_bytes = sum(
        len(part.text.encode()) for part in definition.provider.developer
    )
    schema_bytes = len(
        canonical_json_bytes(provider_wire_schema(definition.output_contract))
    )
    if system_bytes > limits.max_system_bytes:
        raise ValueError("provider system material exceeds its explicit bound")
    if developer_bytes > limits.max_developer_bytes:
        raise ValueError("provider developer material exceeds its explicit bound")
    if schema_bytes > limits.max_output_schema_bytes:
        raise ValueError("provider output schema exceeds its explicit bound")


def session_generation_limit(
    model: str,
    *,
    kernel_limits: KernelLimits = SLICE1_KERNEL_LIMITS,
    native_limits: NativeContextLimits = DEFAULT_NATIVE_CONTEXT_LIMITS,
) -> int:
    """Conservatively rotate before worst-case retained history reaches context."""

    try:
        context_floor = ROUTE_CONTEXT_TOKEN_FLOORS[model]
    except KeyError as error:
        raise ValueError("model is not a qualified Slice 1 route") from error
    static_token_bound = (
        native_limits.max_system_bytes
        + native_limits.max_developer_bytes
        + native_limits.max_output_schema_bytes
    )
    retained_run_token_bound = (
        kernel_limits.max_provider_input_tokens
        + native_limits.one_turn_input_token_overshoot
        + kernel_limits.max_provider_output_tokens
        + native_limits.one_turn_output_token_overshoot
    )
    # Reserve one complete newly rendered invocation for provider-native wrappers,
    # reasoning, and opaque compaction state that the kernel counter cannot see.
    usable_context = context_floor - kernel_limits.max_new_context_bytes
    generations = (usable_context - static_token_bound) // retained_run_token_bound
    if generations <= 0:
        raise ValueError("route context cannot contain one bounded Slice 1 run")
    return generations


def verify_runtime_dependencies() -> None:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Jarvis requires Python 3.12")
    for name, expected in EXPECTED_GIT_PINS.items():
        distribution = importlib.metadata.distribution(name)
        direct_url = distribution.read_text("direct_url.json")
        if direct_url is None:
            raise RuntimeError(f"{name} has no immutable installation provenance")
        try:
            commit = json.loads(direct_url)["vcs_info"]["commit_id"]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"{name} has invalid installation provenance") from error
        if commit != expected:
            raise RuntimeError(f"{name} is not installed at its qualified revision")
    for name, expected in EXPECTED_PACKAGE_VERSIONS.items():
        if importlib.metadata.version(name) != expected:
            raise RuntimeError(f"{name} is not installed at its qualified version")


def _text_sections(kind: str, text: str) -> PromptSections:
    return PromptSections(
        (PromptSection(PromptSectionKind(kind), (), PromptText(text)),)
    )


__all__ = [
    "DEFAULT_NATIVE_CONTEXT_LIMITS",
    "EXPECTED_GIT_PINS",
    "EXPECTED_PACKAGE_VERSIONS",
    "ROUTE_CONTEXT_TOKEN_FLOORS",
    "SLICE1_KERNEL_LIMITS",
    "SLICE1_TOOL_LIMITS",
    "AutomaticWriteGateResult",
    "DreamResult",
    "NativeContextLimits",
    "RecallResult",
    "RememberResult",
    "Slice1Definitions",
    "build_slice1_definitions",
    "load_session_manifest",
    "session_compatibility_revision",
    "session_generation_limit",
    "validate_native_context_bounds",
    "verify_runtime_dependencies",
]
