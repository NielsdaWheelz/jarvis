from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import httpx
from composition_fixture import (
    ActionsFixture,
    MemoryEmbedderFixture,
    MemoryRepositoryFixture,
    composition_settings,
)
from llm_agent_kernel import SessionMode, StructuredOutput, require_host_plan
from llm_tools import Available, PromptText, ToolId, canonical_json_bytes
from provider_fixture import frozen_provider

from jarvis.agent_control import AgentController
from jarvis.agent_tools import AGENT_READ_IDS
from jarvis.definitions import (
    EXTERNAL_READ_IDS,
    MAIN_KERNEL_LIMITS,
    MAIN_MAXIMUM_TOOL_LIMITS,
    MAIN_TOOL_LIMITS,
    MAIN_WRITE_IDS,
    MEMORY_READ_IDS,
    build_definitions,
    build_write_gate,
    load_session_manifest,
    session_compatibility_revision,
)
from jarvis.terminal import JarvisTerminal
from jarvis.tool_composition import build_tool_composition


async def test_catalog_and_plans_select_every_qualified_binding(
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
    gate, _ = build_write_gate(
        provider=frozen_provider("synthetic-profile", "gpt-5.6-terra", "high"),
    )
    try:
        catalog, rotated = (
            build_tool_composition(
                settings=composition_settings(tmp_path),
                google_oauth_http=clients[0],
                google_api_http=clients[1],
                maps_http=clients[2],
                brave_http=clients[3],
                memory_repository=cast("Any", MemoryRepositoryFixture()),
                memory_embedder=cast("Any", MemoryEmbedderFixture()),
                actions=cast("Any", ActionsFixture()),
                agents=AgentController(
                    executable=tmp_path / "skid",
                    client_config=tmp_path / "agent-client.json",
                    actions=cast("Any", ActionsFixture()),
                ),
                automatic_write_gate_definition_fingerprint=gate_fingerprint,
            ).catalog
            for gate_fingerprint in (gate.fingerprint, "b" * 64)
        )
    finally:
        for client in clients:
            await client.aclose()

    assert all(
        isinstance(catalog.binding(tool_id).execute, Available)
        for tool_id in catalog.tool_ids
    )
    assert set(catalog.tool_ids) == {
        ToolId("gmail.search"),
        ToolId("gmail.read_thread"),
        ToolId("gmail.create_draft"),
        ToolId("gmail.update_draft"),
        ToolId("gmail.send_draft"),
        ToolId("calendar.list_events"),
        ToolId("calendar.list_calendars"),
        ToolId("calendar.get_event"),
        ToolId("calendar.create_event"),
        ToolId("calendar.update_event"),
        ToolId("calendar.delete_event"),
        ToolId("maps.search_places"),
        ToolId("maps.get_place"),
        ToolId("maps.directions"),
        ToolId("web.search"),
        ToolId("web.read"),
        ToolId("memory.search"),
        ToolId("memory.open"),
        ToolId("schedule.wake"),
        ToolId("agent.list"),
        ToolId("agent.info"),
        ToolId("agent.read"),
        ToolId("agent.start"),
        ToolId("agent.send"),
        ToolId("agent.keys"),
        ToolId("agent.interrupt"),
        ToolId("agent.stop"),
        ToolId("agent.kill"),
    }
    assert catalog.binding(ToolId("schedule.wake")).implementation_revision == (
        "jarvis-schedule-wake-v1"
    )
    assert catalog.binding(ToolId("calendar.create_event")).implementation_revision == (
        "jarvis-calendar-create_event-v1"
    )
    assert catalog.binding(ToolId("gmail.create_draft")).implementation_revision == (
        "jarvis-gmail-create_draft-v1"
    )
    assert catalog.binding(ToolId("gmail.update_draft")).policy_inputs == {
        "action_max_attempts": 2,
        "authority": "automatic-write-gated",
        "conflict_check": "exact-normalized-content-digest",
        "effect_header": "preserve-X-Jarvis-Effect-ID",
        "reconciliation_max_thread_messages": 100,
        "reconciliation_thread_read": (
            "threads.get(format=minimal)-then-messages.get(format=raw)"
        ),
        "send": False,
        "automatic_write_gate_definition_fingerprint": gate.fingerprint,
    }
    calendar = catalog.binding(ToolId("calendar.create_event"))
    assert calendar.policy_inputs["verified_owner_calendar_ids_digest"] == (
        hashlib.sha256(canonical_json_bytes(["owner@example.invalid"])).hexdigest()
    )
    assert "owner@example.invalid" not in json.dumps(dict(calendar.policy_inputs))
    assert (
        rotated.binding(ToolId("gmail.create_draft")).policy_revision
        != catalog.binding(ToolId("gmail.create_draft")).policy_revision
    )
    assert (
        rotated.binding(ToolId("gmail.search")).policy_revision
        == catalog.binding(ToolId("gmail.search")).policy_revision
    )

    send = catalog.binding(ToolId("gmail.send_draft"))
    assert send.implementation_revision == "jarvis-gmail-send_draft-v1"
    assert send.policy_inputs == {
        "action_max_attempts": 2,
        "authority": "approval-required",
        "automatic_write_gate_definition_fingerprint": gate.fingerprint,
        "effect_header": "preserve-X-Jarvis-Effect-ID",
        "mailbox_search": False,
        "pre_send_check": "exact-normalized-snapshot",
        "reconciliation_backoff_seconds": (0, 2, 8),
        "reconciliation_list_pages": 0,
        "reconciliation_max_elapsed_seconds": 30,
        "reconciliation_max_observations": 3,
        "reconciliation_positive_proof": (
            "one-exact-match-after-bounded-candidates-processed-"
            "with-no-conflicting-evidence"
        ),
        "reconciliation_max_provider_reads_per_observation": 102,
        "reconciliation_max_response_bytes": 16 * 1024 * 1024,
        "reconciliation_max_response_bytes_per_read": 2 * 1024 * 1024,
        "reconciliation_max_thread_messages": 100,
        "reconciliation_thread_minimal_gets_per_observation": 1,
        "reconciliation_thread_raw_message_gets_per_observation": 100,
    }
    definitions = build_definitions(
        catalog=catalog,
        provider=frozen_provider("synthetic-profile", "gpt-5.6-terra", "high"),
        owner_timezone="UTC",
    )
    assert definitions.main.limits == MAIN_KERNEL_LIMITS
    assert definitions.main.maximum_profile.run_limits == MAIN_MAXIMUM_TOOL_LIMITS
    assert definitions.plans["main"].profile.run_limits == MAIN_TOOL_LIMITS

    assert set(definitions.main.maximum_profile.grants) == set(
        (*EXTERNAL_READ_IDS, *MAIN_WRITE_IDS, *AGENT_READ_IDS)
    )
    assert set(definitions.plans["main"].profile.grants) == set(catalog.tool_ids) - {
        *MEMORY_READ_IDS
    }
    assert set(definitions.plans["scheduled_wake"].profile.grants) == set(
        EXTERNAL_READ_IDS
    )
    assert not definitions.automatic_write_gate.maximum_profile.grants
    assert not definitions.plans["automatic_write_gate"].profile.grants
    assert definitions.main.session_mode is SessionMode.continuing
    assert isinstance(definitions.main.output_contract, StructuredOutput)
    assert definitions.main.output_contract.name == "jarvis_terminal"
    assert definitions.main.output_contract.result_type is JarvisTerminal
    main_body = definitions.main.role.instructions.sections[0].body
    assert isinstance(main_body, PromptText)
    main_instructions = main_body.text
    assert "write all prose responses in lowercase" in main_instructions
    assert "never use horizontal rules or emojis" in main_instructions
    assert "critique the owner's ideas assertively" in main_instructions
    assert "do not search the public web unless the owner explicitly requests" in (
        main_instructions
    )
    owner_context = definitions.main.stable_context.sections
    assert len(owner_context) == 1
    assert owner_context[0].kind == "owner_context"
    owner_body = owner_context[0].body
    assert isinstance(owner_body, PromptText)
    assert "neuroscientist by training" in owner_body.text
    assert "maintain an accurate view of active commitments" in owner_body.text
    assert "proactively surface what deserves attention" in owner_body.text
    for role in (
        definitions.recaller,
        definitions.rememberer,
        definitions.dreamer,
        definitions.automatic_write_gate,
    ):
        rendered = "\n".join(
            section.body.text if isinstance(section.body, PromptText) else ""
            for sections in (role.role.instructions, role.stable_context)
            for section in sections.sections
        )
        assert "neuroscientist by training" not in rendered
        assert "write all prose responses in lowercase" not in rendered
    assert definitions.main.maximum_profile.run_limits.max_external_attempts == 250
    assert definitions.plans["main"].profile.run_limits.max_external_attempts == 249
    assert (
        definitions.plans["scheduled_wake"].profile.run_limits.max_external_attempts
        == 222
    )
    for role in ("recaller", "rememberer", "dreamer", "automatic_write_gate"):
        assert getattr(definitions, role).session_mode is SessionMode.isolated
    for name in definitions.plans:
        role = "main" if name == "scheduled_wake" else name
        require_host_plan(
            definitions.plans[name], getattr(definitions, role).maximum_profile
        )
    manifest = load_session_manifest()
    for role in ("main", "recaller", "rememberer", "dreamer", "automatic_write_gate"):
        assert getattr(definitions, role).session_compatibility_revision == (
            session_compatibility_revision(manifest, role)
        )
