"""Canonical request framing shared by admission and archive publication."""

from typing import cast
from uuid import UUID

from llm_agent_kernel import HostInput, InputId
from llm_tools import (
    PromptAttribute,
    PromptAttributeName,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    canonical_json_bytes,
)
from pydantic import JsonValue

from jarvis.messages import StoredMessage


def render_attachment_manifest(trace: dict[str, object]) -> str | None:
    manifest = trace.get("attachment_manifest")
    if manifest is None:
        return None
    entries = cast(list[dict[str, object]], manifest)
    return canonical_json_bytes(
        cast(
            JsonValue,
            [dict(entry, id="attachment:" + str(entry["id"])) for entry in entries],
        )
    ).decode()


def home_context(
    home: dict[str, object] | None, *, archive: bool = False
) -> dict[str, object]:
    """Keep original archive bytes. Only current references frame a live input."""
    if home is None:
        return {}
    context = {
        key: home[key]
        for key in ("ref", "present", "proposal_title", "proposal_ids")
        if home.get(key) is not None
    }
    ref = context.get("ref")
    if (
        not archive
        and isinstance(ref, dict)
        and cast(dict[str, object], ref).get("kind") == "decision"
    ):
        del context["ref"]
    return context


def archive_message_text(
    text: str,
    trace: dict[str, object],
    input_id: UUID,
    home: dict[str, object] | None = None,
) -> str:
    """Preserve historical projection bytes and label new host-supplied metadata."""
    manifest = render_attachment_manifest(trace)
    if manifest is not None:
        caption = (
            f'<owner_input input_id="{input_id}">\n{text}\n</owner_input>\n'
            if text
            else ""
        )
        text = (
            caption
            + f'<attachment_manifest input_id="{input_id}" role="host">\n'
            + manifest
            + "\n</attachment_manifest>"
        )
    if context := home_context(home, archive=True):
        metadata = canonical_json_bytes(cast(JsonValue, context)).decode()
        text += (
            f'\n<home_context input_id="{input_id}" role="host">\n'
            f"{metadata}\n</home_context>"
        )
    return text


def host_input(value: StoredMessage) -> HostInput:
    attributes = tuple(
        PromptAttribute(PromptAttributeName(name), text)
        for name, text in (
            ("input_id", str(value.id)),
            ("role", value.role),
            ("source", value.source),
            ("source_timestamp", value.created_at.isoformat()),
            ("observed_at", str(value.trace.get("observed_at", "unrecorded"))),
            (
                "parent_request_id",
                str(value.parent_request_id) if value.parent_request_id else "none",
            ),
            ("request_state", value.request_state or "none"),
            ("wait_reason", value.wait_reason or "none"),
        )
    )
    sections: list[PromptSection] = []
    if value.text:
        sections.append(
            PromptSection(
                PromptSectionKind(
                    "owner_input" if value.role == "owner" else "host_input"
                ),
                attributes,
                PromptText(value.text),
            )
        )
    host_attributes = tuple(
        PromptAttribute(attribute.name, "host")
        if attribute.name == PromptAttributeName("role")
        else attribute
        for attribute in attributes
    )
    if value.native_retry_after is not None:
        retry = value.trace.get("native_retry")
        cause = "work on this input lost contact with the model."
        if value.trace.get("native_context_retry") is True:
            cause = (
                "work on this input hit the model's context limit. "
                "its original receipts are available through receipt.read."
            )
        elif (
            isinstance(retry, dict)
            and cast(dict[str, object], retry).get("reason")
            == "codex_quota_before_activity"
        ):
            cause = "codex ran out of usage before doing work on this input."
        sections.append(
            PromptSection(
                PromptSectionKind("native_retry"),
                host_attributes,
                PromptText(cause),
            )
        )
    manifest = render_attachment_manifest(value.trace)
    if manifest is not None:
        sections.append(
            PromptSection(
                PromptSectionKind("attachment_manifest"),
                host_attributes,
                PromptText(manifest),
            )
        )
    if context := home_context(value.home):
        sections.append(
            PromptSection(
                PromptSectionKind("home_context"),
                host_attributes,
                PromptText(canonical_json_bytes(cast(JsonValue, context)).decode()),
            )
        )
    return HostInput(
        InputId(str(value.id)),
        PromptSections(tuple(sections)),
        value.created_at,
    )
