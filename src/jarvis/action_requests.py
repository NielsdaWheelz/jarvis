"""Write input identity; one schema and binding through publication and execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any
from uuid import UUID

from llm_tools import Available, PromptDocument, ToolBinding, ToolEffect, ToolFamily
from pydantic import BaseModel, ConfigDict, field_validator


class ActionRequest[InputT: BaseModel](BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    request_ref: str
    existing_action_ref: str | None
    arguments: InputT

    @field_validator("request_ref", "existing_action_ref")
    @classmethod
    def canonical_reference(cls, value: str | None) -> str | None:
        if value is not None and str(UUID(value)) != value:
            raise ValueError("action/request reference must be a canonical UUID")
        return value


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

        spec = replace(
            binding.spec,
            input_type=ActionRequest[binding.spec.input_type],
            documentation=PromptDocument(
                binding.spec.documentation.text
                + "\nrequest_ref names the canonical owner request authorizing "
                "this action. existing_action_ref is null for a new effect; echo "
                "a recorded action reference to recover its result or pending "
                "status. arguments holds the exact operation input."
            ),
            limits=replace(
                binding.spec.limits,
                max_input_bytes=binding.spec.limits.max_input_bytes + 256,
            ),
        )
        bindings.append(
            replace(
                binding,
                spec=spec,
                execute=Available(execute),
                policy_inputs={
                    **binding.policy_inputs,
                    "action_request_revision": "jarvis-action-request.v1",
                },
            )
        )
    return ToolFamily(
        family.namespace, tuple(binding.spec for binding in bindings), tuple(bindings)
    )


__all__ = ["ActionRequest", "bind_action_requests"]
