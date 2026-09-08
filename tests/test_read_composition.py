from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
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
    ToolId,
    WebReadInput,
    WebSearchInput,
    publish_host_table,
    render_prompt,
    web_family,
)
from pydantic import SecretStr

from jarvis.admission import ExactToolBudgetFactory
from jarvis.config import DiscordSettings
from jarvis.definitions import (
    SLICE2_KERNEL_LIMITS,
    SLICE2_PLAN_TOOL_LIMITS,
    SLICE2_READ_IDS,
    SLICE2_TOOL_LIMITS,
    SLICE2_WEB_READ_LIMITS,
    SLICE2_WEB_SEARCH_LIMITS,
    build_slice2_definitions,
    session_generation_limit,
)
from jarvis.read_composition import build_read_catalog
from jarvis.read_dispatch import ReadToolDispatcher
from jarvis.read_tools import compose_read_catalog
from jarvis.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    key = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    return Settings(
        database_url=SecretStr("postgresql://synthetic"),
        discord=DiscordSettings(
            bot_token=SecretStr("synthetic-discord-token"),
            owner_user_id=1,
            guild_id=2,
            channel_id=3,
        ),
        owner_timezone="UTC",
        codex_profile_key="synthetic-profile",
        codex_model="gpt-5.6-terra",
        codex_state_root=tmp_path / "codex",
        runtime_state_directory=tmp_path / "runtime",
        google_oauth_state_path=tmp_path / "google.json",
        google_oauth_client_id=SecretStr("synthetic-google-client"),
        google_oauth_client_secret=SecretStr("synthetic-google-secret"),
        verified_owner_only_calendar_ids=("primary",),
        connector_encryption_key_version="v2",
        connector_encryption_keys=SecretStr(json.dumps({"v2": key})),
        connector_encryption_secret=SecretStr("synthetic-encryption-secret"),
        maps_api_key=SecretStr("synthetic-maps-key"),
        brave_api_key=SecretStr("synthetic-brave-key"),
        embedding_openai_api_key=SecretStr("synthetic-embedding-key"),
    )


async def test_production_catalog_has_exact_available_pinned_web_bindings(
    tmp_path: Path,
) -> None:
    clients = tuple(
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, request=request)
            ),
            trust_env=False,
            follow_redirects=False,
        )
        for _ in range(4)
    )
    try:
        catalog = build_read_catalog(
            settings=_settings(tmp_path),
            google_oauth_http=clients[0],
            google_api_http=clients[1],
            maps_http=clients[2],
            brave_http=clients[3],
        )
    finally:
        for client in clients:
            await client.aclose()

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
        value for value in _settings(tmp_path).host_secrets if value.startswith("a2tr")
    )
    assert bare_key not in repr(_settings(tmp_path))

    definitions = build_slice2_definitions(
        catalog=catalog,
        profile_key="synthetic-profile",
        model="gpt-5.6-terra",
        owner_timezone="UTC",
    )
    assert definitions.main.maximum_profile.run_limits == SLICE2_TOOL_LIMITS
    declared = tuple(catalog.spec(tool_id).limits for tool_id in SLICE2_READ_IDS)
    assert sum(limit.max_input_bytes for limit in declared) == 69_672
    assert sum(limit.max_output_bytes for limit in declared) == 1_114_112
    assert sum(limit.max_attempts for limit in declared) == 21
    assert sum(limit.deadline_seconds for limit in declared) == 150.0
    assert definitions.main.limits == SLICE2_KERNEL_LIMITS
    assert definitions.main.maximum_profile.profile_revision == (
        "4bd28b0c871150edf9bc09954c0df67b3f07a8d088ef4b56ef7dd20560239b86"
    )
    assert definitions.main.session_compatibility_revision == (
        "0dc1db50855ec9f25ab82caf3c0302f64cd323250148e7e2c46f8f08031355e2"
    )
    assert definitions.main.fingerprint == (
        "dfe6bf3618b09ec3c02e97bbf62c36ca830ef6a778569e09b1c767f28bcf9cd3"
    )
    assert definitions.plans["main"].profile.run_limits == SLICE2_PLAN_TOOL_LIMITS
    assert definitions.plans["scheduled_wake"].profile.run_limits == (
        SLICE2_PLAN_TOOL_LIMITS
    )
    exact_revisions = {
        "main": (
            "c25b7e21bfa49db7f87bd17b92e3aeb2601ccb426d34c4310e58675427d7764e",
            "565037c9dcc0cb87a987b8179fd9f07374a3fc7a821c07548478b3c02bc7c2ca",
        ),
        "scheduled_wake": (
            "c0832f6891e0fe4e7b38b93607f7baec66f848cb02a622a638cc4f4f0c0e2881",
            "df2be4627286a9f7326b4e4a5d278e7b4014d6e4adeaea7cddb441044cbf366d",
        ),
    }
    for name, (profile_revision, plan_revision) in exact_revisions.items():
        plan = definitions.plans[name]
        assert tuple(grant.id for grant in plan.profile.ordered_grants) == (
            SLICE2_READ_IDS
        )
        assert plan.grant(ToolId("web.read")).limits == SLICE2_WEB_READ_LIMITS
        assert plan.grant(ToolId("web.search")).limits == (SLICE2_WEB_SEARCH_LIMITS)
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
        assert published["count"] == 9
        assert published["profile_revision"] == profile_revision
        assert published["plan_revision"] == plan_revision
        published_tools = {tool["id"]: tool for tool in published["tools"]}
        calendar_contracts = {
            "calendar.list_events": (
                "eaa9c46273debf37d8d8ac051817dbcb9e3477ee8d3646277ee5e84f676e12ad"
            ),
            "calendar.get_event": (
                "15dfc456377fe4eaff7de42292c9cddc5a97b1190baa7e7196cb4f1e287f0087"
            ),
        }
        for tool_name, contract_revision in calendar_contracts.items():
            tool_id = ToolId(tool_name)
            binding = plan.catalog_view.binding(tool_id)
            assert binding.policy_inputs["observed_end"] == (
                "missing-or-false-parses-end;"
                "true-becomes-unspecified-and-discards-compatibility-end"
            )
            assert published_tools[tool_name]["tool_contract_revision"] == (
                contract_revision
            )
            expected_implementation = (
                "jarvis-calendar-list_events-v3"
                if tool_name == "calendar.list_events"
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
    assert (
        session_generation_limit("gpt-5.6-terra", kernel_limits=SLICE2_KERNEL_LIMITS)
        == 2
    )
    with pytest.raises(ValueError, match="qualified Slice 2 route"):
        build_slice2_definitions(
            catalog=catalog,
            profile_key="synthetic-profile",
            model="gpt-5.4",
            owner_timezone="UTC",
        )
    native_static = 16_384 + 16_384 + 32_768
    retained = 444_000 + 40_000 + 8_192
    assert native_static + 2 * retained == 1_049_920


def test_slice2_definition_rejects_unavailable_web_bindings() -> None:
    class NeverProvider:
        async def gmail_search(self, value: object) -> object:
            raise AssertionError(value)

        async def gmail_read_thread(self, value: object) -> object:
            raise AssertionError(value)

        async def calendar_list_events(self, value: object) -> object:
            raise AssertionError(value)

        async def calendar_get_event(self, value: object) -> object:
            raise AssertionError(value)

        async def search_places(self, value: object) -> object:
            raise AssertionError(value)

        async def get_place(self, value: object) -> object:
            raise AssertionError(value)

        async def directions(self, value: object) -> object:
            raise AssertionError(value)

    catalog = compose_read_catalog(
        google=NeverProvider(),  # type: ignore[arg-type]
        maps=NeverProvider(),  # type: ignore[arg-type]
        web=web_family(),
    )
    with pytest.raises(ValueError, match="must all be available"):
        build_slice2_definitions(
            catalog=catalog,
            profile_key="synthetic-profile",
            model="gpt-5.6-terra",
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

    clients = tuple(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            trust_env=False,
            follow_redirects=False,
        )
        for _ in range(4)
    )
    settings = _settings(tmp_path).model_copy(
        update={"embedding_openai_api_key": SecretStr("alpha beta gamma")}
    )
    try:
        catalog = build_read_catalog(
            settings=settings,
            google_oauth_http=clients[0],
            google_api_http=clients[1],
            maps_http=clients[2],
            brave_http=clients[3],
        )
        definitions = build_slice2_definitions(
            catalog=catalog,
            profile_key=settings.codex_profile_key,
            model=settings.codex_model,
            owner_timezone=settings.owner_timezone,
        )
        plan = definitions.plans["main"]
        require_host_plan(plan, definitions.main.maximum_profile)
        budgets = ExactToolBudgetFactory().create(plan)
        dispatcher = ReadToolDispatcher(host_secrets=settings.host_secrets)
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
            ),
        )
    finally:
        for client in clients:
            await client.aclose()

    assert result.result == {
        "type": "Failure",
        "error": {"type": "InvalidInput"},
    }
    assert plus_result.result == result.result
    assert label_result.result == result.result
    assert dispatcher.recorder.position_count == 0
    assert calls == 0
