"""Closed Main message contracts and deterministic final rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from jarvis.action_requests import CanonicalUuid

type TerminalOutcome = Literal[
    "answered",
    "partial",
    "needs_input",
    "failed",
    "silent",
    "waiting",
]
type ConclusionKind = Literal["conversation", "silent"]

DISCORD_CONTENT_MAX_CHARACTERS = 2_000
PROGRESS_MAX_BYTES = 2_000


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


class Answered(_StrictModel):
    """A complete answer from observed facts with no uncommitted later-work promise."""

    type: Literal["answered"]
    text: Annotated[str, Field(min_length=1, max_length=2_000)]

    _valid_text = field_validator("text")(_terminal_text)


class Partial(_StrictModel):
    """A useful incomplete answer naming one material limit and at most one question."""

    type: Literal["partial"]
    text: Annotated[str, Field(min_length=1, max_length=2_000)]
    limitation: Annotated[str, Field(min_length=1, max_length=500)]
    question: Annotated[str | None, Field(min_length=1, max_length=500)]

    _valid_text = field_validator("text")(_terminal_text)
    _valid_limitation = field_validator("limitation")(_terminal_text)

    @field_validator("question")
    @classmethod
    def _valid_question(cls, value: str | None) -> str | None:
        return None if value is None else _terminal_text(value)


class NeedsInput(_StrictModel):
    """One concrete owner detail required to answer the request."""

    type: Literal["needs_input"]
    context: Annotated[str, Field(max_length=1_000)]
    question: Annotated[str, Field(min_length=1, max_length=500)]

    _valid_context = field_validator("context")(_terminal_text)
    _valid_question = field_validator("question")(_terminal_text)


class Failed(_StrictModel):
    """An honest explanation that the request could not be completed."""

    type: Literal["failed"]
    explanation: Annotated[str, Field(min_length=1, max_length=2_000)]

    _valid_explanation = field_validator("explanation")(_terminal_text)


class Silent(_StrictModel):
    """No public response is needed for these inputs."""

    type: Literal["silent"]
    reason: Literal["no_owner_notice_needed"]


class Waiting(_StrictModel):
    type: Literal["waiting"]
    text: Annotated[str, Field(min_length=1, max_length=2_000)]

    _valid_text = field_validator("text")(_terminal_text)


class Progress(_StrictModel):
    """Useful commentary; it grants no completion or action authority."""

    type: Literal["progress"]
    text: Annotated[str, Field(min_length=1, max_length=2_000)]

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


class _InputDispositions(_StrictModel):
    input_outcomes: list[InputOutcome]

    @model_validator(mode="after")
    def unique_inputs(self) -> Self:
        ids = [item.input_id for item in self.input_outcomes]
        if len(ids) != len(set(ids)):
            raise PydanticCustomError(
                "jarvis_input_dispositions_duplicate",
                "input dispositions must be unique",
            )
        return self


class JarvisTerminal(_InputDispositions):
    """One validated, terminal Main response."""

    response: Answered | Partial | NeedsInput | Failed | Silent | Waiting


class JarvisNativeMessage(_InputDispositions):
    """The native schema applies to both commentary and final responses."""

    response: Progress | Answered | Partial | NeedsInput | Failed | Silent | Waiting

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
        if len(self.content) > DISCORD_CONTENT_MAX_CHARACTERS:
            raise ValueError("rendered terminal exceeds the Discord character bound")


def render_terminal(terminal: JarvisTerminal) -> RenderedTerminal:
    """Render the validated response; main judges evidence relevance and notice."""

    response = terminal.response
    if response.type == "answered":
        return RenderedTerminal("answered", "conversation", response.text)
    if response.type == "waiting":
        return RenderedTerminal("waiting", "conversation", response.text)
    if response.type == "partial":
        content = f"partial result — {response.limitation}\n\n{response.text}"
        if response.question is not None:
            content += f"\n\n{response.question}"
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
            f"i couldn't complete this: {response.explanation}",
        )
    return RenderedTerminal("silent", "silent", None)


__all__ = [
    "PROGRESS_MAX_BYTES",
    "JarvisNativeMessage",
    "JarvisTerminal",
    "Progress",
    "RenderedTerminal",
    "render_terminal",
]
