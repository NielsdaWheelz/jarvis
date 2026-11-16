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


def archive_message_text(text: str, trace: dict[str, object], input_id: UUID) -> str:
    """Old text remains byte-identical; uploads add labelled host references."""
    manifest = render_attachment_manifest(trace)
    if manifest is None:
        return text
    caption = (
        f'<owner_input input_id="{input_id}">\n{text}\n</owner_input>\n' if text else ""
    )
    return (
        caption
        + f'<attachment_manifest input_id="{input_id}" role="host">\n'
        + manifest
        + "\n</attachment_manifest>"
    )


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
    manifest = render_attachment_manifest(value.trace)
    if manifest is not None:
        sections.append(
            PromptSection(
                PromptSectionKind("attachment_manifest"),
                tuple(
                    PromptAttribute(
                        attribute.name,
                        "host"
                        if attribute.name == PromptAttributeName("role")
                        else attribute.value,
                    )
                    for attribute in attributes
                ),
                PromptText(manifest),
            )
        )
    return HostInput(
        InputId(str(value.id)),
        PromptSections(tuple(sections)),
        value.created_at,
    )
