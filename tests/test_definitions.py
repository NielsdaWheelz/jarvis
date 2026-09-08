from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest
from llm_agent_kernel import (
    KERNEL_BASE_INSTRUCTION,
    KERNEL_BASE_INSTRUCTION_IDENTITY,
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
    QUALIFIED_CODEX_MODELS,
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
        model="gpt-5.6-terra",
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
        model="gpt-5.6-terra",
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
                        "table_kind": "memory_log",
                        "id": memory_id,
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


def test_manifest_publishes_exact_dependency_and_role_revisions() -> None:
    manifest = load_session_manifest()
    assert manifest["schema_version"] == "jarvis-session-compatibility.v2"
    assert manifest["application_session_contract_revision"] == "jarvis-slice-3-v1"
    assert manifest["qualified_models"] == ["gpt-5.6-terra"]
    assert (
        cast("dict[str, object]", manifest["role_contract_revisions"])["main"]
        == "jarvis-main-primary-calendar-v1"
    )
    assert (
        cast("dict[str, object]", manifest["role_contract_revisions"])["recaller"]
        == "jarvis-recaller-slice-4-v17"
    )
    assert session_compatibility_revision(manifest, "recaller") == (
        "30e958326a36706b566acab706dda0d820619d7a03b2f9d35cbb953f3f4f85db"
    )
    assert (
        cast("dict[str, object]", manifest["role_contract_revisions"])["dreamer"]
        == "jarvis-dreamer-slice-4-v6"
    )
    assert session_compatibility_revision(manifest, "dreamer") == (
        "6eab1699ee593b36f5f0baa77a180dffc8afb47f3838bf52067f16ee8d17053d"
    )
    previous_recaller = {**manifest}
    previous_recaller_roles = dict(
        cast("dict[str, object]", previous_recaller["role_contract_revisions"])
    )
    previous_recaller_roles["recaller"] = "jarvis-recaller-slice-4-v11"
    previous_recaller["role_contract_revisions"] = previous_recaller_roles
    assert session_compatibility_revision(previous_recaller, "recaller") == (
        "5f989b6f9045374e821155cb2be19daf27be50131effd633d0e4c57d8727ed93"
    )
    for role in ("main", "rememberer", "dreamer", "automatic_write_gate"):
        assert session_compatibility_revision(previous_recaller, role) == (
            session_compatibility_revision(manifest, role)
        )
    assert manifest["dependencies"] == {
        "llm-agent-kernel": "21084bec674023ea572950a18dde464506ea37ad",
        "llm-tools": "9e6d155f3b64f03495911435b7cae8b8d131f9a2",
        "openai-codex": "0.144.4",
        "openai-codex-cli-bin": "0.144.4",
        "provider-runtime": "4ddced3bb5487ce988858c4c6d45d2e5ee0acad9",
    }
    pre_containment_release = {**manifest}
    pre_containment_dependencies = dict(
        cast("dict[str, object]", pre_containment_release["dependencies"])
    )
    pre_containment_dependencies["llm-agent-kernel"] = (
        "09a1af093479aa92f3e783f4b4a7cc38e301a4a7"
    )
    pre_containment_dependencies["provider-runtime"] = (
        "2cfed97ee5b9b8eb11103b0575eb7f29de00a0bd"
    )
    pre_containment_release["dependencies"] = pre_containment_dependencies
    for role in (
        "main",
        "recaller",
        "rememberer",
        "dreamer",
        "automatic_write_gate",
    ):
        assert session_compatibility_revision(pre_containment_release, role) == (
            session_compatibility_revision(manifest, role)
        )

    initial_read_predecessor = {**pre_containment_release}
    initial_read_predecessor_dependencies = dict(pre_containment_dependencies)
    initial_read_predecessor_dependencies["llm-agent-kernel"] = (
        "7f3a9b145e68ba23c8aafad08500e9c452a9faef"
    )
    initial_read_predecessor["dependencies"] = initial_read_predecessor_dependencies
    for role in (
        "main",
        "recaller",
        "rememberer",
        "dreamer",
        "automatic_write_gate",
    ):
        assert session_compatibility_revision(initial_read_predecessor, role) == (
            session_compatibility_revision(manifest, role)
        )
    original = session_compatibility_revision(manifest, "main")
    assert (
        original == "0dc1db50855ec9f25ab82caf3c0302f64cd323250148e7e2c46f8f08031355e2"
    )

    previous = {**manifest}
    previous_roles = dict(
        cast("dict[str, object]", previous["role_contract_revisions"])
    )
    previous_roles["main"] = "jarvis-main-slice-2-v2"
    previous["role_contract_revisions"] = previous_roles
    assert session_compatibility_revision(previous, "main") == (
        "72adbeb8a9932a894b00e05e7f79aefd13dfd1d7a3d5b7c5a8331e199071d1ea"
    )

    historical = {**manifest}
    historical_dependencies = dict(
        cast("dict[str, object]", historical["dependencies"])
    )
    historical_dependencies["llm-agent-kernel"] = (
        "09f08df2970121ababe973b0e92d6901dd40da9e"
    )
    historical_dependencies["provider-runtime"] = (
        "f477dcdcad03c30019576203d4eb8a3581a6d32f"
    )
    historical["dependencies"] = historical_dependencies
    historical_revision = session_compatibility_revision(historical, "main")
    assert historical_revision != original

    predecessor = {**historical}
    predecessor_dependencies = dict(historical_dependencies)
    predecessor_dependencies["llm-agent-kernel"] = (
        "c9dac7a610636a668bbf932cc2f961c0904f9157"
    )
    predecessor_dependencies["provider-runtime"] = (
        "a5d9c8e0c1c851daee0731554e0a4a326d3c2819"
    )
    predecessor["dependencies"] = predecessor_dependencies
    assert session_compatibility_revision(predecessor, "main") == historical_revision

    partial = {**historical}
    partial_dependencies = dict(historical_dependencies)
    partial_dependencies["llm-agent-kernel"] = (
        "c9dac7a610636a668bbf932cc2f961c0904f9157"
    )
    partial["dependencies"] = partial_dependencies
    assert session_compatibility_revision(partial, "main") != historical_revision

    other_dependency = {**manifest}
    other_dependencies = dict(
        cast("dict[str, object]", other_dependency["dependencies"])
    )
    other_dependencies["llm-tools"] = "0" * 40
    other_dependency["dependencies"] = other_dependencies
    assert session_compatibility_revision(other_dependency, "main") != original

    changed = {**manifest}
    roles = dict(cast("dict[str, object]", changed["role_contract_revisions"]))
    roles["main"] = "jarvis-main-slice-1-v2"
    changed["role_contract_revisions"] = roles

    assert session_compatibility_revision(changed, "main") != original
    assert session_compatibility_revision(changed, "recaller") == (
        session_compatibility_revision(manifest, "recaller")
    )

    application_changed = {**manifest}
    application_changed["application_session_contract_revision"] = "jarvis-slice-2-v4"
    assert session_compatibility_revision(application_changed, "main") != original

    qualified_models_changed = {
        **manifest,
        "qualified_models": ["gpt-5.6-terra", "future"],
    }
    assert session_compatibility_revision(qualified_models_changed, "main") == original


def test_model_set_exclusion_and_selected_model_fingerprint() -> None:
    manifest = load_session_manifest()
    terra = build_slice1_definitions(
        profile_key="jarvis-test",
        model="gpt-5.6-terra",
        owner_timezone="UTC",
    ).main
    membership_changed = {
        **manifest,
        "qualified_models": ["gpt-5.6-terra", "synthetic-future-model"],
    }
    unchanged_revision = session_compatibility_revision(membership_changed, "main")
    unchanged_terra = replace(
        terra,
        session_compatibility_revision=unchanged_revision,
    )
    selected_model_changed = replace(
        terra,
        provider=replace(terra.provider, model="synthetic-future-model"),
    )

    assert unchanged_revision == terra.session_compatibility_revision
    assert unchanged_terra.fingerprint == terra.fingerprint
    assert selected_model_changed.fingerprint != terra.fingerprint


def test_provider_native_material_has_independent_bounds() -> None:
    assert KERNEL_BASE_INSTRUCTION_IDENTITY == (
        "llm-agent-kernel-contained-structured-agent-v1:sha256:"
        "1817c90f24bf9149f20f94b69f825d9be0b78df8bb46b1d24ed2691cf71b80e7"
    )
    kernel_system_bytes = len(KERNEL_BASE_INSTRUCTION.encode())
    definitions = build_slice1_definitions(
        profile_key="jarvis-test",
        model="gpt-5.6-terra",
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
                max_system_bytes=kernel_system_bytes + 16,
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
                max_system_bytes=16_384,
                max_developer_bytes=16,
                max_output_schema_bytes=32_768,
            ),
        )

    with pytest.raises(ValueError, match="output schema"):
        validate_native_context_bounds(
            definitions.main,
            NativeContextLimits(
                max_system_bytes=16_384,
                max_developer_bytes=16,
                max_output_schema_bytes=1,
            ),
        )


def test_route_context_floor_derives_conservative_session_generation_bound() -> None:
    assert QUALIFIED_CODEX_MODELS == ("gpt-5.6-terra",)
    assert ROUTE_CONTEXT_TOKEN_FLOORS == {"gpt-5.6-terra": 1_050_000}
    assert session_generation_limit("gpt-5.6-terra") == 3
    native = NativeContextLimits()
    retained_run_bound = (
        SLICE1_KERNEL_LIMITS.max_new_context_bytes
        + SLICE1_KERNEL_LIMITS.max_provider_output_tokens
        + native.one_turn_output_token_overshoot
    )
    static_bound = (
        native.max_system_bytes
        + native.max_developer_bytes
        + native.max_output_schema_bytes
    )
    assert static_bound + 3 * retained_run_bound <= 1_050_000
    assert static_bound + 4 * retained_run_bound > 1_050_000

    with pytest.raises(ValueError, match="qualified Slice 1 route"):
        session_generation_limit("unqualified")
    with pytest.raises(ValueError, match="qualified Slice 1 route"):
        build_slice1_definitions(
            profile_key="jarvis-test",
            model="gpt-5.4",
            owner_timezone="UTC",
        )
