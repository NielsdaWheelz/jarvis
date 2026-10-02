"""Jarvis model replies retain the original result and stable host reference."""

from llm_agent_kernel import DispatchCompleted, HostRef
from llm_tools import ToolResult, canonical_json_bytes


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
