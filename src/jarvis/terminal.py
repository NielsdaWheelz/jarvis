"""Closed Main terminal contract and deterministic host rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

type CalendarCoverageReason = Literal[
    "calendar_limit",
    "calendar_failure",
    "event_page_limit",
    "event_limit",
    "output_byte_limit",
    "deadline",
]
type TerminalOutcome = Literal[
    "answered",
    "partial",
    "needs_input",
    "failed",
    "silent",
]
type ConclusionKind = Literal["conversation", "silent"]

DISCORD_CONTENT_MAX_CHARACTERS = 2_000
_CALENDAR_COVERAGE_REASONS: tuple[CalendarCoverageReason, ...] = (
    "calendar_failure",
    "calendar_limit",
    "deadline",
    "event_limit",
    "event_page_limit",
    "output_byte_limit",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def _utf8(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("terminal text must be valid UTF-8") from exc
    return value


class Answered(_StrictModel):
    """A complete answer from observed facts with no uncommitted later-work promise."""

    type: Literal["answered"]
    text: Annotated[str, Field(min_length=1, max_length=2_000)]

    _valid_text = field_validator("text")(_utf8)


class Partial(_StrictModel):
    """A useful incomplete answer naming one material limit and at most one question."""

    type: Literal["partial"]
    text: Annotated[str, Field(min_length=1, max_length=2_000)]
    limitation: Annotated[str, Field(min_length=1, max_length=500)]
    question: Annotated[str | None, Field(min_length=1, max_length=500)]

    _valid_text = field_validator("text")(_utf8)
    _valid_limitation = field_validator("limitation")(_utf8)

    @field_validator("question")
    @classmethod
    def _valid_question(cls, value: str | None) -> str | None:
        return None if value is None else _utf8(value)


class NeedsInput(_StrictModel):
    """One concrete owner detail required to answer the request."""

    type: Literal["needs_input"]
    context: Annotated[str, Field(max_length=1_000)]
    question: Annotated[str, Field(min_length=1, max_length=500)]

    _valid_context = field_validator("context")(_utf8)
    _valid_question = field_validator("question")(_utf8)


class Failed(_StrictModel):
    """An honest explanation that the request could not be completed."""

    type: Literal["failed"]
    explanation: Annotated[str, Field(min_length=1, max_length=2_000)]

    _valid_explanation = field_validator("explanation")(_utf8)


class Silent(_StrictModel):
    """No response, only when an ordinary owner input genuinely needs none."""

    type: Literal["silent"]
    reason: Literal["owner_needs_no_response"]


class JarvisTerminal(_StrictModel):
    """One validated, terminal Main response."""

    response: Annotated[
        Answered | Partial | NeedsInput | Failed | Silent,
        Field(discriminator="type"),
    ]


@dataclass(frozen=True, slots=True)
class _CalendarIncompleteness:
    reasons: tuple[CalendarCoverageReason, ...]
    calendars_discovered: int
    calendars_completed: int
    matched_events: int | None


@dataclass(slots=True)
class TurnEvidence:
    """Run-local Calendar and fleet incompleteness, without payloads or prose."""

    calendar_incompleteness: tuple[_CalendarIncompleteness, ...] = field(
        default=(), init=False
    )
    # unavailable machines, one count per incomplete fleet read
    agent_inventory_incompleteness: tuple[int, ...] = field(default=(), init=False)

    def record_calendar_incompleteness(
        self,
        *,
        reasons: tuple[CalendarCoverageReason, ...],
        calendars_discovered: int,
        calendars_completed: int,
        matched_events: int | None,
    ) -> None:
        if not 0 <= calendars_discovered <= 50:
            raise ValueError("calendars_discovered is outside its bound")
        if not 0 <= calendars_completed <= calendars_discovered:
            raise ValueError("calendars_completed is outside its bound")
        if matched_events is not None and matched_events < 0:
            raise ValueError("matched_events must be non-negative")
        if reasons != tuple(sorted(set(reasons))):
            raise ValueError("Calendar coverage reasons must be sorted and unique")
        if any(reason not in _CALENDAR_COVERAGE_REASONS for reason in reasons):
            raise ValueError("unknown Calendar coverage reason")
        if not reasons:
            if calendars_completed != calendars_discovered or matched_events is None:
                raise ValueError("complete Calendar coverage counts are inconsistent")
            return
        incomplete_pages = {"calendar_failure", "event_page_limit", "deadline"}
        if incomplete_pages.intersection(reasons):
            if matched_events is not None:
                raise ValueError(
                    "incomplete Calendar pages cannot report a match count"
                )
        elif matched_events is None:
            raise ValueError("exhausted Calendar pages require a match count")
        self.calendar_incompleteness += (
            _CalendarIncompleteness(
                reasons=reasons,
                calendars_discovered=calendars_discovered,
                calendars_completed=calendars_completed,
                matched_events=matched_events,
            ),
        )

    def record_agent_inventory_incompleteness(
        self, *, unavailable_machines: int
    ) -> None:
        if type(unavailable_machines) is not int or unavailable_machines <= 0:
            raise ValueError("incomplete fleet inventory requires unavailable machines")
        self.agent_inventory_incompleteness += (unavailable_machines,)


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


def render_terminal(
    terminal: JarvisTerminal,
    evidence: TurnEvidence,
) -> RenderedTerminal:
    """Apply read completeness policy and render one final host response."""

    response = terminal.response
    calendar = evidence.calendar_incompleteness
    fleet = evidence.agent_inventory_incompleteness
    if (calendar or fleet) and response.type in ("answered", "silent"):
        parts: list[str] = []
        if calendar:
            parts.append(_calendar_limitation(evidence))
        if fleet:
            parts.append(_fleet_limitation(evidence))
        limitation = " ".join(parts)
        if len(limitation) > 500:
            raise ValueError("read coverage limitation exceeds its content bound")
        text = (
            response.text
            if response.type == "answered"
            else "I couldn\u2019t produce a complete answer."
        )
        content = f"Partial result — {limitation}\n\n{text}"
        return RenderedTerminal("partial", "conversation", content)

    if response.type == "answered":
        return RenderedTerminal("answered", "conversation", response.text)
    if response.type == "partial":
        content = f"Partial result — {response.limitation}\n\n{response.text}"
        if response.question is not None:
            content += f"\n\n{response.question}"
        return RenderedTerminal("partial", "conversation", content)
    if response.type == "needs_input":
        content = f"I need one detail: {response.question}"
        if response.context:
            content = f"{response.context}\n\n{content}"
        return RenderedTerminal("needs_input", "conversation", content)
    if response.type == "failed":
        return RenderedTerminal(
            "failed",
            "conversation",
            f"I couldn\u2019t complete this: {response.explanation}",
        )
    return RenderedTerminal("silent", "silent", None)


def _calendar_limitation(evidence: TurnEvidence) -> str:
    records = evidence.calendar_incompleteness
    discovered = sum(record.calendars_discovered for record in records)
    completed = sum(record.calendars_completed for record in records)
    reasons = {reason for record in records for reason in record.reasons}
    if len(records) == 1:
        lead = (
            "Calendar coverage was incomplete: "
            f"{completed} of {discovered} calendar scans completed"
        )
    else:
        lead = (
            f"Calendar coverage was incomplete across {len(records)} reads: "
            f"{completed} of {discovered} calendar scans completed"
        )

    details: list[str] = []
    if "calendar_limit" in reasons:
        details.append("not every readable calendar fit within the calendar limit")
    if "calendar_failure" in reasons:
        details.append("one or more calendars could not be read")
    if "event_page_limit" in reasons:
        details.append("the bounded event-read limit was reached")
    if "event_limit" in reasons or "output_byte_limit" in reasons:
        details.append("not every matching event fit in the response")
    if "deadline" in reasons:
        details.append("the calendar read reached its deadline")
    return "; ".join((lead, *details)) + "."


def _fleet_limitation(evidence: TurnEvidence) -> str:
    records = evidence.agent_inventory_incompleteness
    lead = (
        "Fleet inventory was incomplete"
        if len(records) == 1
        else f"Fleet inventory was incomplete in {len(records)} reads"
    )
    return f"{lead}: machine scans unavailable {sum(records)}; the rest is unknown."


__all__ = [
    "CalendarCoverageReason",
    "JarvisTerminal",
    "RenderedTerminal",
    "TurnEvidence",
    "render_terminal",
]
