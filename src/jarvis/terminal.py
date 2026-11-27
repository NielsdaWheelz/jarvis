"""Closed Main message contracts and deterministic final rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from jarvis.action_requests import CanonicalUuid
from jarvis.home_refs import (
    FilePageRef,
    FileRef,
    NativeDriveFileRef,
    SourceRef,
    ViewRef,
)

type TerminalOutcome = Literal[
    "answered",
    "partial",
    "needs_input",
    "failed",
    "silent",
    "waiting",
]
type ConclusionKind = Literal["conversation", "silent"]

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


class Source(_StrictModel):
    request_id: CanonicalUuid
    kind: Literal["mail", "event"]
    item: str
    reads: list[CanonicalUuid]
    passage: str | None


class Presentation(_StrictModel):
    request_id: CanonicalUuid
    ref: ViewRef | FilePageRef | FileRef | NativeDriveFileRef | SourceRef


class TodoResult(_StrictModel):
    todo_id: CanonicalUuid
    request_id: CanonicalUuid
    draft_ref: CanonicalUuid | None
    file_ref: NativeDriveFileRef | None


class _Visible[KindT: str](_StrictModel):
    # Stock chooses a branch as it emits fields. Keep its discriminator first.
    # Canonical hashing ignores property order; rotate main on a wire reordering.
    type: KindT
    present: Presentation | None
    artifact_links: list[ViewRef]


class Answered(_Visible[Literal["answered"]]):
    """A complete answer from observed facts with no uncommitted later-work promise."""

    text: Annotated[str, Field(min_length=1)]
    todo_result: TodoResult | None
    send_request: CanonicalUuid | None

    _valid_text = field_validator("text")(_terminal_text)


class Partial(_Visible[Literal["partial"]]):
    """A useful incomplete answer naming one material limit and at most one question."""

    text: Annotated[str, Field(min_length=1)]
    limitation: Annotated[str, Field(min_length=1)]
    question: Annotated[str, Field(min_length=1)] | None
    todo_result: TodoResult | None
    send_request: CanonicalUuid | None

    _valid_text = field_validator("text")(_terminal_text)
    _valid_limitation = field_validator("limitation")(_terminal_text)

    @field_validator("question")
    @classmethod
    def _valid_question(cls, value: str | None) -> str | None:
        return None if value is None else _terminal_text(value)


class NeedsInput(_Visible[Literal["needs_input"]]):
    """One concrete owner detail required to answer the request."""

    context: str
    question: Annotated[str, Field(min_length=1)]

    _valid_context = field_validator("context")(_terminal_text)
    _valid_question = field_validator("question")(_terminal_text)


class Failed(_Visible[Literal["failed"]]):
    """An honest explanation that the request could not be completed."""

    explanation: Annotated[str, Field(min_length=1)]

    _valid_explanation = field_validator("explanation")(_terminal_text)


class Silent(_StrictModel):
    """No public response is needed for these inputs."""

    type: Literal["silent"]
    reason: Literal["no_owner_notice_needed"]


class Waiting(_Visible[Literal["waiting"]]):
    text: Annotated[str, Field(min_length=1)]

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
        Literal["external_reconciliation", "owner_input", "configuration"] | None
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
        elif bool(self.action_refs) != (self.wait_reason == "external_reconciliation"):
            raise PydanticCustomError(
                "jarvis_blocker_action_refs_mismatch",
                "action references disagree with the blocker",
            )
        return self


class _Message[ResponseT: _StrictModel](_StrictModel):
    response: ResponseT
    input_outcomes: list[InputOutcome]

    @model_validator(mode="after")
    def valid_outcomes(self) -> Self:
        ids = [item.input_id for item in self.input_outcomes]
        if len(ids) != len(set(ids)):
            raise PydanticCustomError(
                "jarvis_input_dispositions_duplicate",
                "input dispositions must be unique",
            )
        if self.waits_for_owner and not self.has_question:
            raise ValueError(
                "owner_input wait requires a needs_input or partial question"
            )
        return self

    @property
    def waits_for_owner(self) -> bool:
        return any(item.wait_reason == "owner_input" for item in self.input_outcomes)

    @property
    def has_question(self) -> bool:
        return isinstance(self.response, NeedsInput | Partial) and bool(
            self.response.question and self.response.question.strip()
        )


class JarvisTerminal(
    _Message[Answered | Partial | NeedsInput | Failed | Silent | Waiting]
):
    """One validated, terminal Main response."""


class JarvisNativeMessage(
    _Message[Progress | Answered | Partial | NeedsInput | Failed | Silent | Waiting]
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
    """The terminal disposition and content persisted by the host."""

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
    "Presentation",
    "Progress",
    "RenderedTerminal",
    "Silent",
    "render_terminal",
]
