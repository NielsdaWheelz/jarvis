"""Content-free native failure coordinates for the existing operator log."""

from __future__ import annotations

import json
import logging
import sys
from collections import deque
from typing import Literal, TypedDict, get_args
from uuid import UUID

from llm_agent_kernel import NativeDefect, NativeUncertain
from provider_runtime.agent_runtime import (
    AgentRuntimeDefect,
    AgentRuntimeError,
    OutputSchemaMismatch,
    ProtocolDefect,
)
from pydantic import ValidationError
from pydantic_core.core_schema import ErrorType

from jarvis.terminal import JarvisNativeMessage

_KINDS: dict[type[BaseException], str] = {
    kind: kind.__name__
    for kind in (
        NativeDefect,
        NativeUncertain,
        AgentRuntimeError,
        AgentRuntimeDefect,
        ProtocolDefect,
        OutputSchemaMismatch,
        ValidationError,
        ValueError,
        TypeError,
        RuntimeError,
        UnicodeEncodeError,
    )
}
_CODES = frozenset(get_args(ErrorType)) | {
    "jarvis_text_nul",
    "jarvis_text_utf8_invalid",
    "jarvis_progress_bytes_exceeded",
    "jarvis_action_refs_duplicate",
    "jarvis_nonwaiting_has_blocker",
    "jarvis_waiting_missing_blocker",
    "jarvis_blocker_action_refs_mismatch",
    "jarvis_input_dispositions_duplicate",
    "jarvis_progress_has_dispositions",
}
_SCHEMA = JarvisNativeMessage.model_json_schema()
_LOCATIONS = (
    frozenset(_SCHEMA["properties"])
    | frozenset(
        name
        for definition in _SCHEMA["$defs"].values()
        for name in definition.get("properties", {})
    )
    | frozenset(_SCHEMA["$defs"])
    | frozenset(
        definition["properties"]["type"]["const"]
        for definition in _SCHEMA["$defs"].values()
        if "const" in definition.get("properties", {}).get("type", {})
    )
)
_OWNED_PACKAGES = frozenset(
    {"jarvis", "llm_agent_kernel", "provider_runtime", "llm_tools", "universal_memory"}
)


class _Frame(TypedDict):
    module: str
    function: str
    line: int


class _Validation(TypedDict):
    code: str
    location: list[str | int]


class _Exception(TypedDict):
    kind: str
    frames: list[_Frame]
    validation: list[_Validation]
    validation_total: int


def log_native_failure(
    logger: logging.Logger,
    error: BaseException,
    *,
    attempt_id: str | None,
    boundary: Literal["run", "terminal", "command"],
) -> None:
    """Log only closed class, code and installed source coordinates; never payloads."""
    exceptions: list[_Exception] = []
    seen: set[int] = set()
    remaining_validation = 8
    truncated = False
    current: BaseException | None = error
    while current is not None and len(exceptions) < 4 and id(current) not in seen:
        seen.add(id(current))
        frames: deque[_Frame] = deque(maxlen=4)
        frame_count = 0
        traceback = current.__traceback__
        while traceback is not None:
            frame = traceback.tb_frame
            name = frame.f_globals.get("__name__")
            module = sys.modules.get(name) if isinstance(name, str) else None
            if (
                isinstance(name, str)
                and name.partition(".")[0] in _OWNED_PACKAGES
                and module is not None
                and vars(module) is frame.f_globals
                and module.__file__ == frame.f_code.co_filename
            ):
                frames.append(
                    {
                        "module": name,
                        "function": frame.f_code.co_name,
                        "line": traceback.tb_lineno,
                    }
                )
                frame_count += 1
            traceback = traceback.tb_next
        truncated |= frame_count > 4
        validation: list[_Validation] = []
        total = 0
        if isinstance(current, ValidationError):
            total = current.error_count()
            for item in current.errors(
                include_url=False, include_context=False, include_input=False
            )[:remaining_validation]:
                location: list[str | int] = []
                for segment in item["loc"][:8]:
                    if isinstance(segment, str) and segment in _LOCATIONS:
                        location.append(segment)
                    elif type(segment) is int and 0 <= segment <= 2**31 - 1:
                        location.append(segment)
                    else:
                        location.append("?")
                truncated |= len(item["loc"]) > 8
                validation.append(
                    {
                        "code": (
                            item["type"]
                            if item["type"] in _CODES
                            else "unknown_validation"
                        ),
                        "location": location,
                    }
                )
            remaining_validation -= len(validation)
            truncated |= total > len(validation)
        exceptions.append(
            {
                "kind": _KINDS.get(type(current), "other"),
                "frames": list(frames),
                "validation": validation,
                "validation_total": total,
            }
        )
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__suppress_context__:
            current = None
        else:
            current = current.__context__
    truncated |= current is not None
    failure: dict[str, object] = {
        "event": "native_failure",
        "attempt_id": None if attempt_id is None else str(UUID(attempt_id)),
        "boundary": boundary,
        "exceptions": exceptions,
        "truncated": truncated,
    }
    while True:
        encoded = json.dumps(failure, separators=(",", ":"))
        if len(encoded.encode("utf-8")) <= 8 * 1024:
            logger.warning("%s", encoded)
            return
        failure["truncated"] = True
        exceptions.pop()
