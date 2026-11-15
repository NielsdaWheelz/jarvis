"""Canonical request framing shared by admission and publication bounds."""

from llm_agent_kernel import HostInput, InputId
from llm_tools import (
    PromptAttribute,
    PromptAttributeName,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
)

from jarvis.messages import StoredMessage


def host_input(value: StoredMessage) -> HostInput:
    return HostInput(
        InputId(str(value.id)),
        PromptSections(
            (
                PromptSection(
                    PromptSectionKind(
                        "owner_input" if value.role == "owner" else "host_input"
                    ),
                    tuple(
                        PromptAttribute(PromptAttributeName(name), text)
                        for name, text in (
                            ("input_id", str(value.id)),
                            ("role", value.role),
                            ("source", value.source),
                            ("source_timestamp", value.created_at.isoformat()),
                            (
                                "observed_at",
                                str(value.trace.get("observed_at", "unrecorded")),
                            ),
                            (
                                "parent_request_id",
                                str(value.parent_request_id)
                                if value.parent_request_id
                                else "none",
                            ),
                            ("request_state", value.request_state or "none"),
                            ("wait_reason", value.wait_reason or "none"),
                        )
                    ),
                    PromptText(value.text),
                ),
            )
        ),
        value.created_at,
    )
