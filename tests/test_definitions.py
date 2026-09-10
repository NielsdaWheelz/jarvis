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
from provider_fixture import frozen_provider
from provider_runtime.agent_runtime import (
    TextContent,
    freeze_json_object,
    thaw_json_value,
)

from jarvis.definitions import (
    QUALIFIED_CODEX_MODELS,
    NativeContextLimits,
    build_slice1_definitions,
    load_session_manifest,
    session_compatibility_revision,
    validate_native_context_bounds,
)


def test_slice1_definitions_are_closed_and_have_empty_host_plans() -> None:
    definitions = build_slice1_definitions(
        provider=frozen_provider("jarvis-test", "gpt-5.6-terra", "high"),
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
        provider=frozen_provider("jarvis-test", "gpt-5.6-terra", "high"),
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
    assert manifest["schema_version"] == "jarvis-session-compatibility.v3"
    assert (
        manifest["application_session_contract_revision"]
        == "jarvis-shared-codex-durable-inference-v1"
    )
    assert manifest["qualified_models"] == ["gpt-5.6-terra"]
    roles = cast("dict[str, object]", manifest["role_contract_revisions"])
    assert roles["main"] == "jarvis-main-codex-control-v1"
    assert roles["automatic_write_gate"] == "jarvis-write-gate-codex-control-v1"
    assert set(cast("dict[str, object]", manifest["dependencies"])) == {
        "llm-agent-kernel",
        "llm-tools",
        "provider-runtime",
    }

    original = session_compatibility_revision(manifest, "main")
    previous = {**manifest}
    previous_roles = dict(
        cast("dict[str, object]", previous["role_contract_revisions"])
    )
    previous_roles["main"] = "retired-main"
    previous["role_contract_revisions"] = previous_roles
    assert session_compatibility_revision(previous, "main") != original
    assert session_compatibility_revision(previous, "recaller") == (
        session_compatibility_revision(manifest, "recaller")
    )

    other_dependency = {**manifest}
    other_dependencies = dict(
        cast("dict[str, object]", other_dependency["dependencies"])
    )
    other_dependencies["llm-tools"] = "0" * 40
    other_dependency["dependencies"] = other_dependencies
    assert session_compatibility_revision(other_dependency, "main") != original

    application_changed = {**manifest}
    application_changed["application_session_contract_revision"] = "future"
    assert session_compatibility_revision(application_changed, "main") != original

    qualified_models_changed = {
        **manifest,
        "qualified_models": ["gpt-5.6-terra", "future"],
    }
    assert session_compatibility_revision(qualified_models_changed, "main") == original


def test_model_set_exclusion_and_selected_model_fingerprint() -> None:
    manifest = load_session_manifest()
    terra = build_slice1_definitions(
        provider=frozen_provider("jarvis-test", "gpt-5.6-terra", "high"),
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
        provider=replace(terra.provider, model_key="synthetic-future-model"),
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
        provider=frozen_provider("jarvis-test", "gpt-5.6-terra", "high"),
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


def test_only_qualified_models_are_admitted() -> None:
    assert QUALIFIED_CODEX_MODELS == ("gpt-5.6-terra",)
    with pytest.raises(ValueError, match="qualified Slice 1 route"):
        build_slice1_definitions(
            provider=frozen_provider("jarvis-test", "gpt-5.4", "high"),
            owner_timezone="UTC",
        )


def test_frozen_catalog_selection_is_shared_and_rotates_session_identity() -> None:
    from dataclasses import replace

    from llm_agent_kernel import ProviderConfiguration
    from provider_runtime.agent_runtime import CredentialRef

    provider = ProviderConfiguration(
        auth=CredentialRef("local_account", "jarvis-test"),
        model_key="gpt-5.6-terra",
        reasoning="high",
        agent_definition_revision="catalog-v1",
        row_fingerprint="a" * 64,
    )
    original = build_slice1_definitions(provider=provider, owner_timezone="UTC")
    assert original.main.provider is provider
    assert original.recaller.provider is provider
    rotated = build_slice1_definitions(
        provider=replace(provider, row_fingerprint="b" * 64), owner_timezone="UTC"
    )
    assert original.main.fingerprint != rotated.main.fingerprint
