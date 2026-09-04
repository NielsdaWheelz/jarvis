#!/usr/bin/env python3
"""Run the paid Slice 1 Codex consumer qualification with sanitized output."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from llm_agent_kernel import (
    AgentDefinition,
    AgentRole,
    CancellationToken,
    DefinitionId,
    DispatchCompleted,
    HostInput,
    InputId,
    OneShotCompleted,
    ProviderUsage,
    RunId,
    SessionMode,
    StructuredOutput,
    ThreadCompleted,
    ThreadId,
    ToolDispatchDefect,
    ToolDispatchLineage,
    run_one_shot,
)
from llm_tools import (
    Available,
    BudgetState,
    CapabilityProfile,
    FrozenToolPlan,
    HostTable,
    NoDeclaredError,
    PolicyEpoch,
    ProfileId,
    PromptDocument,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    ReplayPolicy,
    RunLimits,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolFamily,
    ToolGrant,
    ToolId,
    ToolLimits,
    ToolPlan,
    ToolSpec,
)
from provider_runtime.agent_runtime import thaw_json_value
from pydantic import BaseModel, ConfigDict, SecretStr

from jarvis.admission import (
    ExactToolBudgetFactory,
    RollingAdmissionLimits,
    RollingAdmissionPort,
)
from jarvis.config import DiscordSettings
from jarvis.db import create_engine
from jarvis.definitions import (
    DEFAULT_NATIVE_CONTEXT_LIMITS,
    EXPECTED_GIT_PINS,
    EXPECTED_PACKAGE_VERSIONS,
    SLICE1_KERNEL_LIMITS,
    DreamResult,
    Slice1Definitions,
    build_slice1_definitions,
    session_generation_limit,
    validate_native_context_bounds,
    verify_runtime_dependencies,
)
from jarvis.history import PostgresCanonicalHistory
from jarvis.kernel import EmptySlice1Dispatcher, KernelRuntime, build_kernel_runtime
from jarvis.messages import MessageStore
from jarvis.service import Slice1ThreadRunner
from jarvis.session import AtomicSessionRefPort
from jarvis.settings import Settings

_SUPPORTED_ROUTES = frozenset({"gpt-5.6-terra", "gpt-5.4"})


def _implementation() -> dict[str, str]:
    lock = Path(__file__).resolve().parents[1] / "uv.lock"
    return {
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "os": platform.system().lower(),
        "architecture": platform.machine().lower(),
    }


@dataclass(frozen=True, slots=True)
class Arguments:
    model: str
    profile: str
    state_root: Path
    runtime_state_directory: Path
    database_url: str
    owner_timezone: str
    reasoning_effort: str


class ProbeToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str


class ProbeToolSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    echoed: str


class ProbeToolRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    acknowledged: bool


async def _must_not_execute(value: object, context: object) -> object:
    del value, context
    raise AssertionError("probe binding executed outside its dispatcher")


class ProbeToolDispatcher:
    def __init__(self, binding: ToolBinding[Any, Any, Any]) -> None:
        self._binding = binding
        self.validated_call_seen = False

    async def dispatch(
        self,
        *,
        binding: ToolBinding[Any, Any, Any],
        validated_input: object,
        plan: FrozenToolPlan,
        budgets: BudgetState,
        cancellation: CancellationToken,
        lineage: ToolDispatchLineage,
    ) -> DispatchCompleted:
        del plan, budgets, cancellation, lineage
        if binding is not self._binding or validated_input != ProbeToolInput(
            text="wire-qualified"
        ):
            raise ToolDispatchDefect("probe did not receive the validated logical call")
        self.validated_call_seen = True
        return DispatchCompleted(
            {"type": "Success", "value": {"echoed": "wire-qualified"}}
        )


def _sections(kind: str, text: str) -> PromptSections:
    return PromptSections(
        (PromptSection(PromptSectionKind(kind), (), PromptText(text)),)
    )


def _runtime(arguments: Arguments, settings: Settings) -> KernelRuntime:
    return build_kernel_runtime(
        provider_state_root=arguments.state_root,
        private_cwd_parent=settings.provider_cwd_parent,
        session_ref_path=settings.session_reference_path,
        model=arguments.model,
    )


def _metric(
    *,
    provider_turns: int,
    usage: ProviderUsage,
    duration_seconds: float,
) -> dict[str, object]:
    return {
        "status": "passed",
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "reported": usage.input_tokens is not None
            and usage.output_tokens is not None,
            "provider_turns": provider_turns,
        },
        "timing_ms": round(duration_seconds * 1_000),
    }


async def _conversation_turn(
    *,
    arguments: Arguments,
    settings: Settings,
    definitions: Slice1Definitions,
    admission_limits: RollingAdmissionLimits,
    store: MessageStore,
    history: PostgresCanonicalHistory,
    source_message_id: str,
    text: str,
) -> tuple[dict[str, object], str]:
    before = {
        message.id
        for message in await store.pending_delivery(
            source_conversation_id=str(settings.discord.channel_id),
            limit=100,
        )
    }
    await store.insert_waking(
        role="owner",
        text=text,
        source="qualification",
        source_conversation_id=str(settings.discord.channel_id),
        source_message_id=source_message_id,
        created_at=datetime.now(UTC),
    )
    runtime = _runtime(arguments, settings)
    try:
        outcome = await Slice1ThreadRunner(
            settings=settings,
            store=store,
            admission=RollingAdmissionPort(
                settings.admission_journal_path,
                admission_limits,
            ),
            kernel_runtime=runtime,
            definitions=definitions,
            history=history,
        ).run(CancellationToken())
    finally:
        await runtime.close()
    if not isinstance(outcome, ThreadCompleted):
        raise RuntimeError("conversation qualification did not complete")
    created = tuple(
        message
        for message in await store.pending_delivery(
            source_conversation_id=str(settings.discord.channel_id),
            limit=100,
        )
        if message.id not in before
    )
    if len(created) != 1:
        raise RuntimeError("conversation qualification did not persist one response")
    return (
        _metric(
            provider_turns=outcome.metrics.provider_turns,
            usage=outcome.metrics.usage,
            duration_seconds=outcome.metrics.duration_seconds,
        ),
        created[0].text,
    )


async def _conversation_probe(
    *,
    arguments: Arguments,
    settings: Settings,
    definitions: Slice1Definitions,
    admission_limits: RollingAdmissionLimits,
    store: MessageStore,
    history: PostgresCanonicalHistory,
) -> tuple[dict[str, object], dict[str, bool]]:
    marker = f"amber-cascade-{uuid4().hex[:8]}"
    source_prefix = uuid4().hex
    references = AtomicSessionRefPort(
        settings.session_reference_path,
        max_generations=session_generation_limit(arguments.model),
    )
    first_metric, _first_response = await _conversation_turn(
        arguments=arguments,
        settings=settings,
        definitions=definitions,
        admission_limits=admission_limits,
        store=store,
        history=history,
        source_message_id=f"{source_prefix}-1",
        text=f"Remember the synthetic marker {marker}. Reply briefly to confirm.",
    )
    first_ref = await references.load(
        ThreadId(str(settings.discord.channel_id)),
        definitions.main.fingerprint,
    )
    if first_ref is None:
        raise RuntimeError("first conversation turn did not store a session reference")

    second_metric, second_response = await _conversation_turn(
        arguments=arguments,
        settings=settings,
        definitions=definitions,
        admission_limits=admission_limits,
        store=store,
        history=history,
        source_message_id=f"{source_prefix}-2",
        text="Reply with the synthetic marker from my preceding message.",
    )
    second_ref = await references.load(
        ThreadId(str(settings.discord.channel_id)),
        definitions.main.fingerprint,
    )
    if second_ref is None:
        raise RuntimeError("second conversation turn did not store a session reference")
    continued = (
        first_ref.ref.native_session_id == second_ref.ref.native_session_id
        and second_ref.generation > first_ref.generation
    )

    third_metric, third_response = await _conversation_turn(
        arguments=arguments,
        settings=settings,
        definitions=definitions,
        admission_limits=admission_limits,
        store=store,
        history=history,
        source_message_id=f"{source_prefix}-3",
        text="Reply with the same synthetic marker again.",
    )
    third_ref = await references.load(
        ThreadId(str(settings.discord.channel_id)),
        definitions.main.fingerprint,
    )
    if third_ref is None:
        raise RuntimeError("third conversation turn lost its compatible reference")

    fourth_metric, fourth_response = await _conversation_turn(
        arguments=arguments,
        settings=settings,
        definitions=definitions,
        admission_limits=admission_limits,
        store=store,
        history=history,
        source_message_id=f"{source_prefix}-4",
        text="Reply with the same synthetic marker once more.",
    )
    fourth_boundary = await references.load_for_discard(
        ThreadId(str(settings.discord.channel_id)),
        definitions.main.fingerprint,
    )
    if fourth_boundary is None:
        raise RuntimeError("fourth turn did not retain its bounded reference")

    fifth_metric, fifth_response = await _conversation_turn(
        arguments=arguments,
        settings=settings,
        definitions=definitions,
        admission_limits=admission_limits,
        store=store,
        history=history,
        source_message_id=f"{source_prefix}-5",
        text=(
            "After automatic session rotation, reply with the synthetic marker "
            "from the first message."
        ),
    )
    fifth_ref = await references.load(
        ThreadId(str(settings.discord.channel_id)),
        definitions.main.fingerprint,
    )
    if fifth_ref is None:
        raise RuntimeError("automatic rotation did not store a fresh reference")

    settings.session_reference_path.unlink()
    sixth_metric, sixth_response = await _conversation_turn(
        arguments=arguments,
        settings=settings,
        definitions=definitions,
        admission_limits=admission_limits,
        store=store,
        history=history,
        source_message_id=f"{source_prefix}-6",
        text=(
            "After deliberate local session loss, reply with the synthetic marker "
            "from the first message."
        ),
    )
    sixth_ref = await references.load(
        ThreadId(str(settings.discord.channel_id)),
        definitions.main.fingerprint,
    )
    if sixth_ref is None:
        raise RuntimeError("deliberate-loss turn did not store a fresh reference")

    continuity = {
        "compatible_restart": continued,
        "compatible_restart_recalled_context": marker in second_response.casefold(),
        "retained_through_generation_three": (
            third_ref.ref.native_session_id == second_ref.ref.native_session_id
            and third_ref.generation == 3
            and marker in third_response.casefold()
        ),
        "generation_four_boundary_reached": (
            fourth_boundary.ref.native_session_id == third_ref.ref.native_session_id
            and fourth_boundary.generation == 4
            and marker in fourth_response.casefold()
        ),
        "automatic_session_rotated": (
            fifth_ref.ref.native_session_id != third_ref.ref.native_session_id
            and fifth_ref.generation == 1
        ),
        "automatic_rotation_reconstructed": marker in fifth_response.casefold(),
        "deliberate_loss_session_rotated": (
            sixth_ref.ref.native_session_id != fifth_ref.ref.native_session_id
            and sixth_ref.generation == 1
        ),
        "deliberate_loss_reconstructed": marker in sixth_response.casefold(),
    }
    if not all(continuity.values()):
        raise RuntimeError("conversation session continuity qualification failed")
    return {
        "status": "passed",
        "turns": [
            first_metric,
            second_metric,
            third_metric,
            fourth_metric,
            fifth_metric,
            sixth_metric,
        ],
    }, continuity


async def _structured_probe(
    *,
    arguments: Arguments,
    settings: Settings,
    definitions: Slice1Definitions,
    admission: RollingAdmissionPort,
) -> dict[str, object]:
    runtime = _runtime(arguments, settings)
    try:
        outcome = await run_one_shot(
            run_id=RunId(str(uuid4())),
            definition=definitions.dreamer,
            inputs=(
                HostInput(
                    InputId(str(uuid4())),
                    _sections(
                        "qualification_input",
                        "Return the required empty insertions and "
                        "remove_summary_ids result.",
                    ),
                    datetime.now(UTC),
                ),
            ),
            as_of=datetime.now(UTC),
            plan=definitions.plans["dreamer"],
            source_sections=PromptSections(()),
            admission=admission,
            provider=runtime.provider,
            dispatcher=EmptySlice1Dispatcher(),
            budget_factory=ExactToolBudgetFactory(),
        )
    finally:
        await runtime.close()
    if not isinstance(outcome, OneShotCompleted):
        raise RuntimeError("structured qualification did not complete")
    result = DreamResult.model_validate(thaw_json_value(outcome.result))
    if result.insertions or result.remove_summary_ids:
        raise RuntimeError("structured qualification returned an unexpected result")
    return _metric(
        provider_turns=outcome.metrics.provider_turns,
        usage=outcome.metrics.usage,
        duration_seconds=outcome.metrics.duration_seconds,
    )


def _tool_probe_definition(
    definitions: Slice1Definitions,
) -> tuple[AgentDefinition, FrozenToolPlan, ToolBinding[Any, Any, Any]]:
    spec: ToolSpec[ProbeToolInput, ProbeToolSuccess, NoDeclaredError] = ToolSpec(
        id=ToolId("qualification.echo"),
        summary="Validate one provider tool-argument envelope",
        documentation=PromptDocument("Echo one bounded qualification string."),
        input_type=ProbeToolInput,
        success_type=ProbeToolSuccess,
        error_type=NoDeclaredError,
        effect=ToolEffect.Pure,
        limits=ToolLimits(4_096, 4_096, 1, 30.0),
    )
    binding: ToolBinding[
        ProbeToolInput,
        ProbeToolSuccess,
        NoDeclaredError,
    ] = ToolBinding(
        spec=spec,
        execute=Available(_must_not_execute),
        replay_policy=ReplayPolicy.ReDispatchable,
        implementation_revision="jarvis-qualification-echo-v1",
        policy_epoch=PolicyEpoch("slice-1-qualification-v1"),
        policy_inputs={},
    )
    catalog = ToolCatalog.compose((ToolFamily("qualification", (spec,), (binding,)),))
    maximum = CapabilityProfile(
        ProfileId("slice1_qualification_echo"),
        (ToolGrant(spec.id, None),),
        RunLimits(1, 1, 4_096, 4_096, 1, 30.0),
    ).freeze(catalog)
    plan = ToolPlan(maximum.id, HostTable()).freeze(catalog, maximum)
    definition = AgentDefinition(
        definition_id=DefinitionId("jarvis-qualification-echo"),
        role=AgentRole(
            "qualification_echo",
            _sections(
                "role_instructions",
                "Call qualification.echo exactly once with text wire-qualified. "
                "After the host observation, finish with acknowledged true.",
            ),
        ),
        stable_context=PromptSections(()),
        session_mode=SessionMode.isolated,
        output_contract=StructuredOutput(
            "jarvis_qualification_echo_result",
            ProbeToolRunResult,
        ),
        maximum_profile=maximum,
        provider=definitions.main.provider,
        session_compatibility_revision=(
            f"{definitions.main.session_compatibility_revision}:qualification-echo-v1"
        ),
        limits=SLICE1_KERNEL_LIMITS,
    )
    validate_native_context_bounds(definition, DEFAULT_NATIVE_CONTEXT_LIMITS)
    return definition, plan, cast("ToolBinding[Any, Any, Any]", binding)


async def _tool_argument_probe(
    *,
    arguments: Arguments,
    settings: Settings,
    definitions: Slice1Definitions,
    admission: RollingAdmissionPort,
) -> dict[str, object]:
    definition, plan, binding = _tool_probe_definition(definitions)
    dispatcher = ProbeToolDispatcher(binding)
    runtime = _runtime(arguments, settings)
    try:
        outcome = await run_one_shot(
            run_id=RunId(str(uuid4())),
            definition=definition,
            inputs=(
                HostInput(
                    InputId(str(uuid4())),
                    _sections(
                        "qualification_input",
                        "Perform the exact qualification call, then return the "
                        "required result.",
                    ),
                    datetime.now(UTC),
                ),
            ),
            as_of=datetime.now(UTC),
            plan=plan,
            source_sections=PromptSections(()),
            admission=admission,
            provider=runtime.provider,
            dispatcher=dispatcher,
            budget_factory=ExactToolBudgetFactory(),
        )
    finally:
        await runtime.close()
    if not isinstance(outcome, OneShotCompleted) or not dispatcher.validated_call_seen:
        raise RuntimeError("tool-argument qualification did not complete")
    result = ProbeToolRunResult.model_validate(thaw_json_value(outcome.result))
    if result.acknowledged is not True:
        raise RuntimeError("tool-argument qualification returned an unexpected result")
    return _metric(
        provider_turns=outcome.metrics.provider_turns,
        usage=outcome.metrics.usage,
        duration_seconds=outcome.metrics.duration_seconds,
    )


async def _run(arguments: Arguments) -> dict[str, object]:
    verify_runtime_dependencies()
    _validate_directories(arguments)
    arguments.runtime_state_directory.mkdir(mode=0o700)
    provider_cwd = arguments.runtime_state_directory / "provider-cwd"
    provider_cwd.mkdir(mode=0o700)
    conversation_id = uuid4().int % 900_000_000_000_000_000 + 1
    settings = Settings(
        database_url=SecretStr(arguments.database_url),
        discord=DiscordSettings(
            bot_token=SecretStr("qualification-placeholder"),
            owner_user_id=1,
            guild_id=2,
            channel_id=conversation_id,
        ),
        owner_timezone=arguments.owner_timezone,
        codex_profile_key=arguments.profile,
        codex_model=arguments.model,
        codex_state_root=arguments.state_root,
        runtime_state_directory=arguments.runtime_state_directory,
    )
    admission_limits = RollingAdmissionLimits()
    RollingAdmissionPort.initialize(settings.admission_journal_path, admission_limits)
    definitions = build_slice1_definitions(
        profile_key=arguments.profile,
        model=arguments.model,
        owner_timezone=arguments.owner_timezone,
        reasoning_effort=arguments.reasoning_effort,
    )
    engine = create_engine(arguments.database_url)
    store = MessageStore(engine)
    history = PostgresCanonicalHistory(engine)
    try:
        conversation, continuity = await _conversation_probe(
            arguments=arguments,
            settings=settings,
            definitions=definitions,
            admission_limits=admission_limits,
            store=store,
            history=history,
        )
        admission = RollingAdmissionPort(
            settings.admission_journal_path,
            admission_limits,
        )
        structured = await _structured_probe(
            arguments=arguments,
            settings=settings,
            definitions=definitions,
            admission=admission,
        )
        tool_arguments = await _tool_argument_probe(
            arguments=arguments,
            settings=settings,
            definitions=definitions,
            admission=admission,
        )
    finally:
        await engine.dispose()
    return {
        "route": arguments.model,
        "revisions": {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS},
        "implementation": {
            **_implementation(),
            "main_definition_fingerprint": definitions.main.fingerprint,
            "session_compatibility_revision": (
                definitions.main.session_compatibility_revision
            ),
            "reasoning_effort": arguments.reasoning_effort,
        },
        "status": "passed",
        "session_continuity": continuity,
        "probes": {
            "conversation": conversation,
            "structured": structured,
            "tool_arguments": tool_arguments,
        },
    }


def _validate_directories(arguments: Arguments) -> None:
    if (
        not arguments.state_root.is_absolute()
        or not arguments.state_root.is_dir()
        or stat.S_IMODE(arguments.state_root.stat().st_mode) & 0o077
    ):
        raise ValueError(
            "Codex state root must be an existing private absolute directory"
        )
    runtime = arguments.runtime_state_directory
    if not runtime.is_absolute() or runtime.exists() or not runtime.parent.is_dir():
        raise ValueError(
            "runtime state must be an unused absolute path with an existing parent"
        )
    if stat.S_IMODE(runtime.parent.stat().st_mode) & 0o077:
        raise ValueError("runtime-state parent must be private")


def _required(values: Mapping[str, object], name: str) -> str:
    value = values.get(name)
    if type(value) is not str or not value:
        raise ValueError(f"missing qualification setting: {name}")
    return value


def _parse_arguments() -> Arguments:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.environ.get("JARVIS_CODEX_MODEL"))
    parser.add_argument("--profile", default=os.environ.get("JARVIS_CODEX_PROFILE_KEY"))
    parser.add_argument(
        "--state-root", default=os.environ.get("JARVIS_CODEX_STATE_ROOT")
    )
    parser.add_argument(
        "--runtime-state-directory",
        default=os.environ.get("JARVIS_LIVE_RUNTIME_STATE_DIRECTORY"),
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("JARVIS_LIVE_DATABASE_URL"),
    )
    parser.add_argument(
        "--owner-timezone",
        default=os.environ.get("JARVIS_OWNER_TIMEZONE"),
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.environ.get("JARVIS_CODEX_REASONING_EFFORT", "high"),
    )
    parser.add_argument(
        "--confirm-paid",
        action="store_true",
        default=os.environ.get("JARVIS_CODEX_LIVE") == "1",
    )
    values = cast("dict[str, object]", vars(parser.parse_args()))
    if values["confirm_paid"] is not True:
        raise ValueError(
            "paid qualification requires --confirm-paid or JARVIS_CODEX_LIVE=1"
        )
    model = _required(values, "model")
    if model not in _SUPPORTED_ROUTES:
        raise ValueError("model must be one of the two qualified routes")
    return Arguments(
        model=model,
        profile=_required(values, "profile"),
        state_root=Path(_required(values, "state_root")),
        runtime_state_directory=Path(_required(values, "runtime_state_directory")),
        database_url=_required(values, "database_url"),
        owner_timezone=_required(values, "owner_timezone"),
        reasoning_effort=_required(values, "reasoning_effort"),
    )


def main() -> int:
    route = os.environ.get("JARVIS_CODEX_MODEL", "unconfigured")
    try:
        arguments = _parse_arguments()
        route = arguments.model
        result = asyncio.run(_run(arguments))
    except BaseException:
        result = {
            "route": route if route in _SUPPORTED_ROUTES else "unconfigured",
            "revisions": {**EXPECTED_GIT_PINS, **EXPECTED_PACKAGE_VERSIONS},
            "implementation": _implementation(),
            "status": "failed",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
