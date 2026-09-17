from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import httpx
import pytest
from composition_fixture import (
    MemoryEmbedderFixture,
    MemoryRepositoryFixture,
    build_test_catalog,
    composition_settings,
    with_read_bindings,
)
from llm_agent_kernel import (
    CancellationToken,
    Checkpoint,
    ClaimId,
    DispatchLineage,
    InputId,
    require_host_plan,
)
from llm_tools import (
    WEB_READ_SPEC,
    WEB_SEARCH_SPEC,
    Available,
    HostTable,
    ToolCatalog,
    ToolId,
    WebReadInput,
    WebSearchInput,
    publish_host_table,
    render_prompt,
    web_family,
)
from provider_fixture import decision_key, frozen_provider
from pydantic import SecretStr

from jarvis.admission import ExactToolBudgetFactory
from jarvis.definitions import (
    EXTERNAL_READ_IDS,
    SCHEDULED_WAKE_TOOL_LIMITS,
    WEB_READ_LIMITS,
    WEB_SEARCH_LIMITS,
    RoleDefinitions,
    build_definitions,
    load_session_manifest,
    session_compatibility_revision,
)
from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder


def test_production_catalog_has_exact_available_pinned_web_bindings(
    tmp_path: Path,
    current_catalog: ToolCatalog,
    current_definitions: RoleDefinitions,
) -> None:
    catalog = current_catalog
    definitions = current_definitions
    search = catalog.binding(ToolId("web.search"))
    read = catalog.binding(ToolId("web.read"))
    assert catalog.spec(ToolId("web.search")) is WEB_SEARCH_SPEC
    assert catalog.spec(ToolId("web.read")) is WEB_READ_SPEC
    assert isinstance(search.execute, Available)
    assert isinstance(read.execute, Available)
    assert search.implementation_revision == "llm-tools-web-search-v2"
    assert str(search.policy_epoch) == "web-search-v2"
    assert read.implementation_revision == "llm-tools-web-read-v2"
    assert search.policy_inputs == {
        "locale": "US/en",
        "max_results": 10,
        "operation_deadline_seconds": 12.0,
        "safe_search": "moderate",
    }
    assert read.policy_inputs == {
        "accepted_media": (
            "application/json",
            "application/xhtml+xml",
            "text/html",
            "text/plain",
        ),
        "mode": "direct",
    }

    bare_key = next(
        value
        for value in composition_settings(tmp_path).host_secrets
        if value.startswith("a2tr")
    )
    assert bare_key not in repr(composition_settings(tmp_path))

    declared = tuple(catalog.spec(tool_id).limits for tool_id in EXTERNAL_READ_IDS)
    assert sum(limit.max_input_bytes for limit in declared) == 73_768
    assert sum(limit.max_output_bytes for limit in declared) == 1_638_400
    assert sum(limit.max_attempts for limit in declared) == 223
    assert sum(limit.deadline_seconds for limit in declared) == 205.0
    assert definitions.main.session_compatibility_revision == (
        session_compatibility_revision(load_session_manifest(), "main")
    )
    plan = definitions.plans["scheduled_wake"]
    assert plan.profile.run_limits == SCHEDULED_WAKE_TOOL_LIMITS
    profile_revision = (
        "f179a4fbd84e8f4b2fd08dd705974d99b5d3677dc0876b84e4c0a7a3f2db69ed"
    )
    plan_revision = "51fd77b3dba108933959a00430f7149a7cd6c34264639d25e6e2448e54b8f263"
    assert tuple(grant.id for grant in plan.profile.ordered_grants) == (
        EXTERNAL_READ_IDS
    )
    assert plan.grant(ToolId("web.read")).limits == WEB_READ_LIMITS
    assert plan.grant(ToolId("web.search")).limits == (WEB_SEARCH_LIMITS)
    assert isinstance(plan.exposure, HostTable)
    assert plan.profile.profile_revision == profile_revision
    assert plan.plan_revision == plan_revision
    rendered = render_prompt(publish_host_table(plan))
    assert rendered.startswith('<section kind="host_table">\n')
    assert rendered.endswith("\n</section>")
    published = json.loads(
        html.unescape(
            rendered.removeprefix('<section kind="host_table">\n').removesuffix(
                "\n</section>"
            )
        )
    )
    assert published["count"] == 10
    assert published["profile_revision"] == profile_revision
    assert published["plan_revision"] == plan_revision
    published_tools = {tool["id"]: tool for tool in published["tools"]}
    calendar_contracts = {
        "calendar.list_calendars": (
            "08cc652b133c80a30ee2e9c3be2c64d2321f00533805a4a56213ce95fd911817"
        ),
        "calendar.list_events": (
            "908bb99fd8da9ea022051eddf48fb0e061712738620e6ef8842bc015dd7b7086"
        ),
        "calendar.get_event": (
            "15dfc456377fe4eaff7de42292c9cddc5a97b1190baa7e7196cb4f1e287f0087"
        ),
    }
    for tool_name, contract_revision in calendar_contracts.items():
        tool_id = ToolId(tool_name)
        binding = plan.catalog_view.binding(tool_id)
        if tool_name != "calendar.list_calendars":
            assert binding.policy_inputs["observed_end"] == (
                "missing-or-false-parses-end;"
                "true-becomes-unspecified-and-discards-compatibility-end"
            )
        assert published_tools[tool_name]["tool_contract_revision"] == (
            contract_revision
        )
        expected_implementation = (
            "jarvis-calendar-list_events-v6"
            if tool_name == "calendar.list_events"
            else "jarvis-calendar-list_calendars-v1"
            if tool_name == "calendar.list_calendars"
            else "jarvis-calendar-get_event-v2"
        )
        assert published_tools[tool_name]["implementation_revision"] == (
            expected_implementation
        )
        assert published_tools[tool_name]["policy_revision"] == (
            binding.policy_revision
        )
    assert (
        plan.catalog_view.binding(ToolId("web.read")).implementation_revision
        == "llm-tools-web-read-v2"
    )
    require_host_plan(plan, definitions.main.maximum_profile)
    with pytest.raises(ValueError, match="qualified"):
        build_definitions(
            catalog=catalog,
            provider=frozen_provider("synthetic-profile", "gpt-5.4", "high"),
            owner_timezone="UTC",
        )


def test_definition_rejects_unavailable_web_bindings(
    current_catalog: ToolCatalog,
) -> None:
    catalog = with_read_bindings(current_catalog, ToolCatalog.compose((web_family(),)))
    with pytest.raises(ValueError, match="must be available"):
        build_definitions(
            catalog=catalog,
            provider=frozen_provider(),
            owner_timezone="UTC",
        )


async def test_production_web_binding_rejects_encoded_host_secret_before_io(
    tmp_path: Path,
) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        trust_env=False,
        follow_redirects=False,
    )
    settings = composition_settings(tmp_path).model_copy(
        update={"embedding_openai_api_key": SecretStr("alpha beta gamma")}
    )
    try:
        provider = frozen_provider(
            settings.codex_profile_key, settings.codex_model, "high"
        )
        catalog = build_test_catalog(
            settings,
            client,
            provider,
            memory_repository=cast(Any, MemoryRepositoryFixture()),
            memory_embedder=cast(Any, MemoryEmbedderFixture()),
        )
        definitions = build_definitions(
            catalog=catalog,
            provider=provider,
            owner_timezone=settings.owner_timezone,
        )
        plan = definitions.plans["scheduled_wake"]
        require_host_plan(plan, definitions.main.maximum_profile)
        budgets = ExactToolBudgetFactory().create(plan)
        dispatcher = ReadToolDispatcher(
            recorder=RunReadRecorder(), host_secrets=settings.host_secrets
        )
        bare_key = next(
            value for value in settings.host_secrets if value.startswith("a2tr")
        )
        encoded = quote(quote(bare_key, safe=""), safe="")

        result = await dispatcher.dispatch(
            binding=catalog.binding(ToolId("web.search")),
            validated_input=WebSearchInput(
                query=f"lookup {encoded}",
                freshness_days=None,
            ),
            plan=plan,
            budgets=budgets,
            cancellation=CancellationToken(),
            lineage=DispatchLineage(
                ClaimId("claim"),
                Checkpoint("checkpoint"),
                (InputId("input"),),
                1,
                definition_fingerprint="a" * 64,
                model_decision_id=decision_key(str(ClaimId("claim")), 1),
            ),
        )
        plus_result = await dispatcher.dispatch(
            binding=catalog.binding(ToolId("web.read")),
            validated_input=WebReadInput(
                url="https://public.example/?value=alpha+beta+gamma"
            ),
            plan=plan,
            budgets=budgets,
            cancellation=CancellationToken(),
            lineage=DispatchLineage(
                ClaimId("claim"),
                Checkpoint("checkpoint"),
                (InputId("input"),),
                2,
                definition_fingerprint="a" * 64,
                model_decision_id=decision_key(str(ClaimId("claim")), 2),
            ),
        )
        label_result = await dispatcher.dispatch(
            binding=catalog.binding(ToolId("web.read")),
            validated_input=WebReadInput(
                url="https://public.example/?api+key=abcdefghijklmnop"
            ),
            plan=plan,
            budgets=budgets,
            cancellation=CancellationToken(),
            lineage=DispatchLineage(
                ClaimId("claim"),
                Checkpoint("checkpoint"),
                (InputId("input"),),
                3,
                definition_fingerprint="a" * 64,
                model_decision_id=decision_key(str(ClaimId("claim")), 3),
            ),
        )
    finally:
        await client.aclose()

    assert result.result == {
        "type": "Failure",
        "error": {"type": "InvalidInput"},
    }
    assert plus_result.result == result.result
    assert label_result.result == result.result
    assert dispatcher.recorder.position_count == 0
    assert calls == 0
