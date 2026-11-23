"""Write input identity; one schema and binding through publication and execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Annotated, Any

from llm_tools import (
    Available,
    PromptDocument,
    ToolBinding,
    ToolEffect,
    ToolFamily,
    ToolSpec,
)
from pydantic import BaseModel, ConfigDict, Field

CanonicalUuid = Annotated[
    str,
    Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]


class ActionRequest[InputT: BaseModel](BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    request_ref: CanonicalUuid
    existing_action_ref: CanonicalUuid | None
    arguments: InputT


def action_request_spec(spec: ToolSpec[Any, Any, Any]) -> ToolSpec[Any, Any, Any]:
    """The write declaration captured on every action by the main tool plan."""
    return replace(
        spec,
        input_type=ActionRequest[spec.input_type],
        documentation=PromptDocument(
            spec.documentation.text
            + "\nrequest_ref names a delivered live owner or host request. "
            "existing_action_ref is null for a new invocation, even when its "
            "arguments equal earlier work. use an explicit recorded action "
            "reference to recover its original result or pending status within "
            "the same causal component. arguments is the exact operation input."
        ),
        limits=replace(
            spec.limits,
            max_input_bytes=spec.limits.max_input_bytes + 256,
        ),
    )


def bind_action_requests(family: ToolFamily) -> ToolFamily:
    bindings: list[ToolBinding[Any, Any, Any]] = []
    for binding in family.bindings:
        if binding.spec.effect is not ToolEffect.Write:
            bindings.append(binding)
            continue
        if not isinstance(binding.execute, Available):
            raise ValueError("Write must have an available handler")
        handler = binding.execute.handler

        async def execute(
            value: ActionRequest[Any],
            context: Any,
            *,
            original: Callable[..., Awaitable[Any]] = handler,
        ) -> Any:
            return await original(value.arguments, context)

        spec = action_request_spec(binding.spec)
        bindings.append(
            replace(
                binding,
                spec=spec,
                execute=Available(execute),
                policy_inputs={
                    **binding.policy_inputs,
                    "action_request_revision": "jarvis-action-request.v2",
                },
            )
        )
    return ToolFamily(
        family.namespace, tuple(binding.spec for binding in bindings), tuple(bindings)
    )


__all__ = [
    "ActionRequest",
    "CanonicalUuid",
    "action_request_spec",
    "bind_action_requests",
]
