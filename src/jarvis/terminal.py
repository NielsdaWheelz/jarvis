"""Closed Main message contracts and deterministic final rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from jarvis.action_requests import CanonicalUuid
from jarvis.home_refs import FilePageRef, FileRef, ViewRef

type TerminalOutcome = Literal[
    "answered",
    "partial",
    "needs_input",
    "failed",
    "silent",
    "waiting",
]
type ConclusionKind = Literal["conversation", "silent"]

CHAT_MAX_CHARACTERS = 2_000
_PARTIAL_PREFIX = "partial result — "
_FAILED_PREFIX = "i couldn't complete this: "
_PARAGRAPH = "\n\n"
_DETAIL_MAX = 500
_PARTIAL_BODY_MAX = (
    CHAT_MAX_CHARACTERS - len(_PARTIAL_PREFIX + _PARAGRAPH) - _DETAIL_MAX
)
PROGRESS_MAX_BYTES = 2_000
NATIVE_OUTPUT_NAME = "jarvis_home_message"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def _terminal_text(value: str) -> str:
    if "\x00" in value:
        raise PydanticCustomError("jarvis_text_nul", "terminal text contains nul")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PydanticCustomError(
            "jarvis_text_utf8_invalid", "terminal text must be valid UTF-8"
        ) from exc
    return value


class Presentation(_StrictModel):
    request_id: CanonicalUuid
    ref: ViewRef | FilePageRef | FileRef


class _Visible[KindT: str](_StrictModel):
    # Stock emits fields in schema order. Every response must choose its type first.
    type: KindT
    present: Presentation | None


class Answered(_Visible[Literal["answered"]]):
    """A complete answer from observed facts with no uncommitted later-work promise."""

    text: Annotated[str, Field(min_length=1, max_length=CHAT_MAX_CHARACTERS)]

    _valid_text = field_validator("text")(_terminal_text)


class _PartialFields(_Visible[Literal["partial"]]):
    text: Annotated[str, Field(min_length=1, max_length=CHAT_MAX_CHARACTERS)]
    limitation: Annotated[str, Field(min_length=1, max_length=_DETAIL_MAX)]

    _valid_text = field_validator("text")(_terminal_text)
    _valid_limitation = field_validator("limitation")(_terminal_text)

    @field_validator("question", check_fields=False)
    @classmethod
    def _valid_question(cls, value: str | None) -> str | None:
        return None if value is None else _terminal_text(value)


class Partial(_PartialFields):
    """A useful incomplete answer naming one material limit and at most one question."""

    question: Annotated[str | None, Field(min_length=1, max_length=_DETAIL_MAX)]


# A new opening reserves space for every field in its complete chat message.
# Frozen seals still use their own wire schema and the full semantic Partial.
class _PartialWithoutQuestion(_PartialFields):
    text: Annotated[str, Field(min_length=1, max_length=_PARTIAL_BODY_MAX)]
    question: None


class _PartialWithQuestion(_PartialFields):
    text: Annotated[
        str,
        Field(
            min_length=1, max_length=_PARTIAL_BODY_MAX - len(_PARAGRAPH) - _DETAIL_MAX
        ),
    ]
    question: Annotated[str, Field(min_length=1, max_length=_DETAIL_MAX)]


class NeedsInput(_Visible[Literal["needs_input"]]):
    """One concrete owner detail required to answer the request."""

    context: Annotated[str, Field(max_length=1_000)]
    question: Annotated[str, Field(min_length=1, max_length=_DETAIL_MAX)]

    _valid_context = field_validator("context")(_terminal_text)
    _valid_question = field_validator("question")(_terminal_text)


class Failed(_Visible[Literal["failed"]]):
    """An honest explanation that the request could not be completed."""

    explanation: Annotated[str, Field(min_length=1, max_length=CHAT_MAX_CHARACTERS)]

    _valid_explanation = field_validator("explanation")(_terminal_text)


class _GeneratedFailed(Failed):
    explanation: Annotated[
        str,
        Field(
            min_length=1,
            max_length=CHAT_MAX_CHARACTERS - len(_FAILED_PREFIX),
        ),
    ]


class Silent(_StrictModel):
    """No public response is needed for these inputs."""

    type: Literal["silent"]
    reason: Literal["no_owner_notice_needed"]


class Waiting(_Visible[Literal["waiting"]]):
    text: Annotated[str, Field(min_length=1, max_length=CHAT_MAX_CHARACTERS)]

    _valid_text = field_validator("text")(_terminal_text)


class Progress(_Visible[Literal["progress"]]):
    """Useful commentary; it grants no completion or action authority."""

    text: Annotated[str, Field(min_length=1, max_length=PROGRESS_MAX_BYTES)]

    @field_validator("text")
    @classmethod
    def bounded_text(cls, value: str) -> str:
        _terminal_text(value)
        if len(value.encode("utf-8")) > PROGRESS_MAX_BYTES:
            raise PydanticCustomError(
                "jarvis_progress_bytes_exceeded",
                "progress exceeds its UTF-8 byte bound",
            )
        return value


class InputOutcome(_StrictModel):
    input_id: CanonicalUuid
    disposition: Literal["complete", "continue", "waiting", "stop"]
    wait_reason: (
        Literal["approval", "external_reconciliation", "owner_input", "configuration"]
        | None
    )
    action_refs: list[CanonicalUuid]

    @model_validator(mode="after")
    def valid_blocker(self) -> InputOutcome:
        if len(self.action_refs) != len(set(self.action_refs)):
            raise PydanticCustomError(
                "jarvis_action_refs_duplicate", "action references must be unique"
            )
        if self.disposition != "waiting":
            if self.wait_reason is not None or self.action_refs:
                raise PydanticCustomError(
                    "jarvis_nonwaiting_has_blocker",
                    "nonwaiting disposition has no blocker",
                )
        elif self.wait_reason is None:
            raise PydanticCustomError(
                "jarvis_waiting_missing_blocker",
                "waiting disposition requires a blocker",
            )
        elif bool(self.action_refs) != (
            self.wait_reason in {"approval", "external_reconciliation"}
        ):
            raise PydanticCustomError(
                "jarvis_blocker_action_refs_mismatch",
                "action references disagree with the blocker",
            )
        return self


class _Message[ResponseT: _StrictModel](_StrictModel):
    response: ResponseT
    input_outcomes: list[InputOutcome]

    @model_validator(mode="after")
    def valid_outcomes(self, info: ValidationInfo) -> Self:
        ids = [item.input_id for item in self.input_outcomes]
        if len(ids) != len(set(ids)):
            raise PydanticCustomError(
                "jarvis_input_dispositions_duplicate",
                "input dispositions must be unique",
            )
        if (
            self.waits_for_owner
            and not self.has_question
            and info.context != "historical_seal"
        ):
            raise ValueError(
                "owner_input wait requires a needs_input or partial question"
            )
        return self

    @property
    def waits_for_owner(self) -> bool:
        return any(item.wait_reason == "owner_input" for item in self.input_outcomes)

    @property
    def has_question(self) -> bool:
        return isinstance(
            self.response, NeedsInput | Partial | _PartialWithQuestion
        ) and bool(self.response.question and self.response.question.strip())


class JarvisTerminal(
    _Message[Answered | Partial | NeedsInput | Failed | Silent | Waiting]
):
    """One validated, terminal Main response."""

    @classmethod
    def from_seal(cls, name: str, value: object) -> Self:
        if name == NATIVE_OUTPUT_NAME:
            return cls.model_validate(value)
        if name != "jarvis_native_message" or not isinstance(value, dict):
            raise ValueError("unrecognized native seal contract")
        document = cast(dict[str, JsonValue], value)
        response = document.get("response")
        if not isinstance(response, dict) or "present" in response:
            raise ValueError("invalid historical native response")
        if response.get("type") != "silent":
            document = {**document, "response": {**response, "present": None}}
        return cls.model_validate(document, context="historical_seal")


class JarvisNativeMessage(
    _Message[
        Progress
        | Answered
        | _PartialWithoutQuestion
        | _PartialWithQuestion
        | NeedsInput
        | _GeneratedFailed
        | Silent
        | Waiting
    ]
):
    """The native schema applies to both commentary and final responses."""

    @model_validator(mode="after")
    def progress_has_no_dispositions(self) -> Self:
        if isinstance(self.response, Progress) and self.input_outcomes:
            raise PydanticCustomError(
                "jarvis_progress_has_dispositions",
                "progress cannot settle or change input dispositions",
            )
        return self


@dataclass(frozen=True, slots=True)
class RenderedTerminal:
    """The terminal disposition and bounded content persisted by the host."""

    outcome: TerminalOutcome
    conclusion_kind: ConclusionKind
    content: str | None

    def __post_init__(self) -> None:
        if self.outcome == "silent":
            if self.conclusion_kind != "silent" or self.content is not None:
                raise ValueError("silent terminal rendering is inconsistent")
            return
        if self.conclusion_kind != "conversation" or not self.content:
            raise ValueError("visible terminal rendering is inconsistent")
        try:
            self.content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("rendered terminal must be valid UTF-8") from exc
        if len(self.content) > CHAT_MAX_CHARACTERS:
            raise ValueError("rendered terminal exceeds the chat character bound")


def render_terminal(terminal: JarvisTerminal) -> RenderedTerminal:
    """Render the validated response; main judges evidence relevance and notice."""

    response = terminal.response
    if response.type == "answered":
        return RenderedTerminal("answered", "conversation", response.text)
    if response.type == "waiting":
        return RenderedTerminal("waiting", "conversation", response.text)
    if response.type == "partial":
        content = f"{_PARTIAL_PREFIX}{response.limitation}{_PARAGRAPH}{response.text}"
        if response.question is not None:
            content += f"{_PARAGRAPH}{response.question}"
        return RenderedTerminal("partial", "conversation", content)
    if response.type == "needs_input":
        content = f"i need one detail: {response.question}"
        if response.context:
            content = f"{response.context}\n\n{content}"
        return RenderedTerminal("needs_input", "conversation", content)
    if response.type == "failed":
        return RenderedTerminal(
            "failed",
            "conversation",
            f"{_FAILED_PREFIX}{response.explanation}",
        )
    return RenderedTerminal("silent", "silent", None)


__all__ = [
    "NATIVE_OUTPUT_NAME",
    "PROGRESS_MAX_BYTES",
    "JarvisNativeMessage",
    "JarvisTerminal",
    "Presentation",
    "Progress",
    "RenderedTerminal",
    "Silent",
    "render_terminal",
]
