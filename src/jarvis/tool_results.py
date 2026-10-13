"""Jarvis model replies retain the original result and stable host reference."""

from typing import cast

from llm_agent_kernel import DispatchCompleted, HostRef, tool_observation_section
from llm_tools import (
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    ToolId,
    ToolResult,
    canonical_json_bytes,
    render_prompt,
)
from mcp.types import CallToolResult, TextContent
from pydantic import JsonValue


class NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


def memory_view_size(value: str) -> int:
    """Count the exact shared memory text frame, including XML escaping."""
    return len(
        render_prompt(
            PromptSections(
                (
                    PromptSection(
                        PromptSectionKind("historical_memory_view"),
                        (),
                        PromptText(value),
                    ),
                )
            )
        ).encode()
    )


def memory_result_size(value: object) -> int:
    """Measure the shared read result with actual host observation framing."""
    if not isinstance(value, dict):
        raise TypeError("a memory result must be an object")
    result: ToolResult = {"type": "Success", "value": cast(JsonValue, value)}
    model_text = canonical_json_bytes(result).decode()
    observation = render_prompt(
        tool_observation_section(ToolId("memory.search"), model_text, 10)
    )
    native_reply = completed_tool_result(
        result,
        HostRef("native-invocation:00000000-0000-0000-0000-000000000000"),
    ).model_text
    mcp_result = CallToolResult(
        content=[TextContent(type="text", text=canonical_json_bytes(value).decode())],
    )
    return max(
        len(model_text.encode()),
        len(observation.encode()),
        len(native_reply.encode()),
        len(
            canonical_json_bytes(
                mcp_result.model_dump(mode="json", exclude_none=True, by_alias=True)
            )
        ),
    )


def completed_tool_result(
    result: ToolResult, host_ref: HostRef | None = None
) -> DispatchCompleted:
    model_value = (
        result
        if host_ref is None
        else {"type": "tool_result", "host_ref": str(host_ref), "result": result}
    )
    return DispatchCompleted(
        result, canonical_json_bytes(model_value).decode(), host_ref
    )
