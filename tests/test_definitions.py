from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest
from llm_agent_kernel import (
    AgentDefinition,
    ConversationalOutput,
    FinishStep,
    SessionMode,
    StructuredOutput,
    provider_wire_schema,
    require_host_plan,
    validate_provider_step,
)
from llm_tools import FrozenToolPlan
from provider_runtime.agent_runtime import (
    TextContent,
    freeze_json_object,
    thaw_json_value,
)

from jarvis.definitions import (
    ROUTE_CONTEXT_TOKEN_FLOORS,
    SLICE1_KERNEL_LIMITS,
    NativeContextLimits,
    build_slice1_definitions,
    load_session_manifest,
    session_compatibility_revision,
    session_generation_limit,
    validate_native_context_bounds,
)


def test_slice1_definitions_are_closed_and_have_empty_host_plans() -> None:
    definitions = build_slice1_definitions(
        profile_key="jarvis-test",
        model="gpt-5.4",
        owner_timezone="America/Los_Angeles",
    )

    assert definitions.main.session_mode is SessionMode.continuing
    assert isinstance(definitions.main.output_contract, ConversationalOutput)
    for definition in (
        definitions.recaller,
        definitions.rememberer,
        definitions.dreamer,
        definitions.automatic_write_gate,
    ):
        assert definition.session_mode is SessionMode.isolated
        assert isinstance(definition.output_contract, StructuredOutput)
        assert definition.output_contract.schema["additionalProperties"] is False
        _assert_codex_closed_schema(definition.output_contract.wire_schema)
        _assert_codex_closed_schema(provider_wire_schema(definition.output_contract))
        assert definition.session_compatibility_revision
    for plan in definitions.plans.values():
        assert not plan.profile.ordered_grants
        assert plan.profile.run_limits.max_external_attempts == 0
        assert plan.is_tightening_of(plan.profile)
    assert definitions.plans["main"].plan_revision != (
        definitions.plans["scheduled_wake"].plan_revision
    )
    assert definitions.plans["main"].profile.profile_revision != (
        definitions.plans["scheduled_wake"].profile.profile_revision
    )
    assert definitions.plans["proactive"] is definitions.plans["scheduled_wake"]
    assert definitions.plans["scheduled_wake"].is_tightening_of(
        definitions.main.maximum_profile
    )
    require_host_plan(definitions.plans["main"], definitions.main.maximum_profile)
    require_host_plan(
        definitions.plans["scheduled_wake"], definitions.main.maximum_profile
    )
    with pytest.raises(TypeError):
        definitions.plans["extra"] = definitions.plans["main"]  # type: ignore[index]


def test_isolated_result_contracts_accept_decoded_json_arrays() -> None:
    definitions = build_slice1_definitions(
        profile_key="jarvis-test",
        model="gpt-5.4",
        owner_timezone="America/Los_Angeles",
    )
    memory_id = "00000000-0000-4000-8000-000000000001"
    summary_id = "00000000-0000-4000-8000-000000000002"
    owner_id = "00000000-0000-4000-8000-000000000003"
    cases: tuple[tuple[AgentDefinition, FrozenToolPlan, dict[str, object]], ...] = (
        (
            definitions.recaller,
            definitions.plans["recaller"],
            {
                "memories": [
                    {
                        "memory_id": memory_id,
                        "text": "synthetic recalled memory",
                        "created_at": "2026-09-03T12:00:00+00:00",
                        "source_memory_ids": [memory_id],
                    }
                ]
            },
        ),
        (definitions.rememberer, definitions.plans["rememberer"], {"memories": []}),
        (
            definitions.dreamer,
            definitions.plans["dreamer"],
            {
                "insertions": [
                    {
                        "text": "synthetic summary",
                        "source_memory_ids": [memory_id],
                    }
                ],
                "remove_summary_ids": [summary_id],
            },
        ),
        (
            definitions.automatic_write_gate,
            definitions.plans["automatic_write_gate"],
            {"decision": "allow", "supporting_owner_message_ids": [owner_id]},
        ),
    )
    for definition, plan, result in cases:
        step = validate_provider_step(
            freeze_json_object(
                {
                    "type": "finish",
                    "say": None,
                    "call_tool": None,
                    "finish": {"reason": None, "result": result},
                }
            ),
            definition.output_contract,
            plan,
        )
        assert isinstance(step, FinishStep)
        assert thaw_json_value(step.result) == result


def _assert_codex_closed_schema(node: object) -> None:
    if isinstance(node, Mapping):
        value = cast("Mapping[str, object]", node)
        assert not isinstance(value.get("additionalProperties"), Mapping)
        if value.get("type") == "object" or "properties" in value:
            properties = value["properties"]
            assert isinstance(properties, Mapping)
            names = tuple(cast("Mapping[str, object]", properties))
            assert value["additionalProperties"] is False
            assert value["required"] == names or value["required"] == list(names)
        for child in value.values():
            _assert_codex_closed_schema(child)
    elif isinstance(node, tuple):
        for child in cast("tuple[object, ...]", node):
            _assert_codex_closed_schema(child)
    elif isinstance(node, list):
        for child in cast("list[object]", node):
            _assert_codex_closed_schema(child)


def test_manifest_revision_changes_with_role_contract() -> None:
    manifest = load_session_manifest()
    original = session_compatibility_revision(manifest, "main")
    changed = {**manifest}
    roles = dict(cast("dict[str, object]", changed["role_contract_revisions"]))
    roles["main"] = "jarvis-main-slice-1-v2"
    changed["role_contract_revisions"] = roles

    assert session_compatibility_revision(changed, "main") != original
    assert session_compatibility_revision(changed, "recaller") == (
        session_compatibility_revision(manifest, "recaller")
    )


def test_provider_native_material_has_independent_bounds() -> None:
    definitions = build_slice1_definitions(
        profile_key="jarvis-test",
        model="gpt-5.4",
        owner_timezone="UTC",
    )
    provider = replace(
        definitions.main.provider,
        system=(TextContent("x" * 17),),
    )
    definition = replace(definitions.main, provider=provider)

    with pytest.raises(ValueError, match="system material"):
        validate_native_context_bounds(
            definition,
            NativeContextLimits(
                max_system_bytes=16,
                max_developer_bytes=16,
                max_output_schema_bytes=32_768,
            ),
        )

    provider = replace(
        definitions.main.provider,
        developer=(TextContent("x" * 17),),
    )
    definition = replace(definitions.main, provider=provider)
    with pytest.raises(ValueError, match="developer material"):
        validate_native_context_bounds(
            definition,
            NativeContextLimits(
                max_system_bytes=16,
                max_developer_bytes=16,
                max_output_schema_bytes=32_768,
            ),
        )

    with pytest.raises(ValueError, match="output schema"):
        validate_native_context_bounds(
            definitions.main,
            NativeContextLimits(
                max_system_bytes=16,
                max_developer_bytes=16,
                max_output_schema_bytes=1,
            ),
        )


def test_route_context_floor_derives_conservative_session_generation_bound() -> None:
    assert ROUTE_CONTEXT_TOKEN_FLOORS == {
        "gpt-5.6-terra": 1_050_000,
        "gpt-5.4": 1_050_000,
    }
    assert session_generation_limit("gpt-5.6-terra") == 4
    assert session_generation_limit("gpt-5.4") == 4
    native = NativeContextLimits()
    retained_run_bound = (
        SLICE1_KERNEL_LIMITS.max_provider_input_tokens
        + native.one_turn_input_token_overshoot
        + SLICE1_KERNEL_LIMITS.max_provider_output_tokens
        + native.one_turn_output_token_overshoot
    )
    static_bound = (
        native.max_system_bytes
        + native.max_developer_bytes
        + native.max_output_schema_bytes
    )
    usable = 1_050_000 - SLICE1_KERNEL_LIMITS.max_new_context_bytes
    assert static_bound + 4 * retained_run_bound <= usable
    assert static_bound + 5 * retained_run_bound > usable
    assert 1_050_000 - usable == SLICE1_KERNEL_LIMITS.max_new_context_bytes

    with pytest.raises(ValueError, match="qualified Slice 1 route"):
        session_generation_limit("unqualified")
    with pytest.raises(ValueError, match="qualified Slice 1 route"):
        build_slice1_definitions(
            profile_key="jarvis-test",
            model="unqualified",
            owner_timezone="UTC",
        )
