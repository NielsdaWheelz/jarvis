from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from llm_tools import Available, ExecutionContext, ToolEffect, ToolId, Unavailable
from pydantic import ValidationError

from jarvis.write_tools import (
    AUTOMATIC_WRITE_TOOL_IDS,
    GMAIL_CREATE_DRAFT_SPEC,
    GMAIL_SEND_DRAFT_SPEC,
    WRITE_ACTION_MAX_ATTEMPTS,
    WRITE_TOOL_IDS,
    GmailContent,
    GmailCreateDraftInput,
    GmailDraftSuccess,
    Mailbox,
    WriteAttemptBudget,
    WriteResponse,
    calendar_write_family,
    gmail_write_family,
)

ACTION_ID = UUID("12345678-1234-4234-8234-123456789abc")
NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


class _Provider:
    called: UUID | None = None

    async def gmail_create_draft(
        self,
        value: GmailCreateDraftInput,
        effect_id: UUID,
        attempts: WriteAttemptBudget,
    ) -> WriteResponse[GmailDraftSuccess]:
        assert attempts == WriteAttemptBudget(0, 4)
        self.called = effect_id
        return WriteResponse(
            GmailDraftSuccess(
                draft_id="draft",
                message_id="message",
                thread_id="thread",
                jarvis_effect_id="a" * 64,
                content_digest="b" * 64,
                observed_at=NOW,
            ),
            1,
        )

    async def gmail_update_draft(
        self, value: object, effect_id: UUID, attempts: WriteAttemptBudget
    ) -> object:
        raise AssertionError((value, effect_id, attempts))

    async def calendar_create_event(
        self, value: object, effect_id: UUID, attempts: WriteAttemptBudget
    ) -> object:
        raise AssertionError((value, effect_id, attempts))

    async def calendar_update_event(
        self, value: object, effect_id: UUID, attempts: WriteAttemptBudget
    ) -> object:
        raise AssertionError((value, effect_id, attempts))

    async def calendar_delete_event(
        self, value: object, effect_id: UUID, attempts: WriteAttemptBudget
    ) -> object:
        raise AssertionError((value, effect_id, attempts))


def _content() -> GmailContent:
    return GmailContent(
        to=(Mailbox(name="Owner", address="owner@example.invalid"),),
        cc=(),
        bcc=(),
        subject="Synthetic",
        body_text="Synthetic body",
        reply_to=None,
    )


def _assert_closed(value: object) -> None:
    if isinstance(value, dict):
        item = cast("dict[object, object]", value)
        if item.get("type") == "object":
            assert item.get("additionalProperties") is False
        for child in item.values():
            _assert_closed(child)
    elif isinstance(value, list):
        for child in cast("list[object]", value):
            _assert_closed(child)


def test_write_manifest_is_exact_closed_and_redispatchable() -> None:
    provider = cast("Any", _Provider())
    families = (gmail_write_family(provider), calendar_write_family(provider))
    bindings = tuple(binding for family in families for binding in family.bindings)

    assert frozenset(binding.spec.id for binding in bindings) == WRITE_TOOL_IDS
    assert GMAIL_SEND_DRAFT_SPEC.id not in AUTOMATIC_WRITE_TOOL_IDS
    assert WRITE_ACTION_MAX_ATTEMPTS == 2
    for binding in bindings:
        assert binding.spec.effect is ToolEffect.Write
        assert binding.implementation_revision == (
            f"jarvis-{str(binding.spec.id).replace('.', '-')}-v1"
        )
        assert binding.policy_inputs["action_max_attempts"] == 2
        _assert_closed(binding.spec.input_schema.semantic)
        _assert_closed(binding.spec.success_schema.semantic)
        assert binding.spec.declared_error_schema is not None
        _assert_closed(binding.spec.declared_error_schema.semantic)

    declared = GMAIL_CREATE_DRAFT_SPEC.declared_error_schema
    assert declared is not None
    errors = cast(
        "list[dict[str, Any]]",
        declared.semantic["anyOf"],
    )
    assert {branch["properties"]["type"]["const"] for branch in errors} == {
        "InvalidRecipient",
        "ThreadNotFound",
        "ThreadMismatch",
        "Conflict",
        "RateLimited",
        "ProviderUnavailable",
    }
    send = next(
        binding for binding in bindings if binding.spec.id == GMAIL_SEND_DRAFT_SPEC.id
    )
    assert isinstance(send.execute, Unavailable)
    assert "Slice 6" in send.execute.private_reason


def test_mailbox_normalizes_only_domain_and_rejects_header_injection() -> None:
    assert Mailbox(name=None, address="Owner@Example.INVALID").address == (
        "Owner@example.invalid"
    )
    with pytest.raises(ValidationError):
        Mailbox(name=None, address="Name <owner@example.invalid>")
    with pytest.raises(ValidationError):
        Mailbox(name="Injected\nBcc", address="owner@example.invalid")


@pytest.mark.asyncio
async def test_binding_requires_action_id_as_position_and_effect_id() -> None:
    provider = _Provider()
    binding = gmail_write_family(cast("Any", provider)).bindings[0]
    assert binding.spec.id == ToolId("gmail.create_draft")
    assert isinstance(binding.execute, Available)

    def grant(tool_id: ToolId) -> SimpleNamespace:
        return SimpleNamespace(id=tool_id, limits=binding.spec.limits)

    context = cast(
        "ExecutionContext",
        SimpleNamespace(
            effect_id=str(ACTION_ID),
            position=str(ACTION_ID),
            grant=SimpleNamespace(id=binding.spec.id, limits=binding.spec.limits),
            plan=SimpleNamespace(grant=grant),
        ),
    )

    result = await binding.execute.handler(
        GmailCreateDraftInput(content=_content()), context
    )

    assert result.actual_attempts == 1
    assert provider.called == ACTION_ID
    bad_context = cast(
        "ExecutionContext",
        SimpleNamespace(
            effect_id=str(ACTION_ID),
            position="different",
            grant=SimpleNamespace(limits=binding.spec.limits),
        ),
    )
    with pytest.raises(RuntimeError, match="position and effect"):
        await binding.execute.handler(
            GmailCreateDraftInput(content=_content()), bad_context
        )
