from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest
from llm_agent_kernel import StructuredOutput, provider_wire_schema
from pydantic import ValidationError

from jarvis.terminal import (
    JarvisTerminal,
    RenderedTerminal,
    TurnEvidence,
    render_terminal,
)


def _terminal(response: dict[str, object]) -> JarvisTerminal:
    return JarvisTerminal.model_validate({"response": response})


def test_terminal_contract_compiles_and_is_closed() -> None:
    contract = StructuredOutput("jarvis_terminal", JarvisTerminal)

    assert contract.schema["additionalProperties"] is False
    definitions = cast(
        "Mapping[str, Mapping[str, object]]",
        contract.schema["$defs"],
    )
    assert "_Response" not in definitions
    properties = cast(
        "Mapping[str, Mapping[str, object]]", contract.schema["properties"]
    )
    assert "oneOf" in properties["response"]
    assert {
        name: definitions[name]["description"]
        for name in ("Answered", "Partial", "NeedsInput", "Failed", "Silent")
    } == {
        "Answered": (
            "A complete answer from observed facts with no uncommitted later-work "
            "promise."
        ),
        "Partial": (
            "A useful incomplete answer naming one material limit and at most one "
            "question."
        ),
        "NeedsInput": "One concrete owner detail required to answer the request.",
        "Failed": "An honest explanation that the request could not be completed.",
        "Silent": (
            "No response, only when an ordinary owner input genuinely needs none."
        ),
    }
    assert provider_wire_schema(contract)["additionalProperties"] is False
    with pytest.raises(ValidationError):
        JarvisTerminal.model_validate(
            {"response": {"type": "answered", "text": "Done."}, "extra": True}
        )
    with pytest.raises(ValidationError):
        _terminal({"type": "answered", "text": "Done.", "extra": True})
    with pytest.raises(ValidationError):
        _terminal({"type": "working", "text": "I am checking."})


@pytest.mark.parametrize(
    ("response", "outcome", "conclusion_kind", "content"),
    [
        (
            {"type": "answered", "text": "The appointment is at 14:00."},
            "answered",
            "conversation",
            "The appointment is at 14:00.",
        ),
        (
            {
                "type": "partial",
                "text": "I found two appointments.",
                "limitation": "One calendar could not be read.",
                "question": "Should I check it again?",
            },
            "partial",
            "conversation",
            "Partial result — One calendar could not be read.\n\n"
            "I found two appointments.\n\nShould I check it again?",
        ),
        (
            {
                "type": "needs_input",
                "context": "There are two events named Review.",
                "question": "Which Review do you mean?",
            },
            "needs_input",
            "conversation",
            "There are two events named Review.\n\n"
            "I need one detail: Which Review do you mean?",
        ),
        (
            {
                "type": "needs_input",
                "context": "",
                "question": "Which day do you mean?",
            },
            "needs_input",
            "conversation",
            "I need one detail: Which day do you mean?",
        ),
        (
            {"type": "failed", "explanation": "Calendar access was denied."},
            "failed",
            "conversation",
            "I couldn\u2019t complete this: Calendar access was denied.",
        ),
        (
            {"type": "silent", "reason": "owner_needs_no_response"},
            "silent",
            "silent",
            None,
        ),
    ],
)
def test_renderer_is_exact(
    response: dict[str, object],
    outcome: str,
    conclusion_kind: str,
    content: str | None,
) -> None:
    rendered = render_terminal(_terminal(response), TurnEvidence())

    assert rendered.outcome == outcome
    assert rendered.conclusion_kind == conclusion_kind
    assert rendered.content == content


@pytest.mark.parametrize(
    "response",
    [
        {"type": "answered", "text": ""},
        {"type": "answered", "text": "x" * 2_001},
        {
            "type": "partial",
            "text": "x" * 2_001,
            "limitation": "A limit applied.",
            "question": None,
        },
        {
            "type": "partial",
            "text": "Observed facts.",
            "limitation": "x" * 501,
            "question": None,
        },
        {
            "type": "partial",
            "text": "Observed facts.",
            "limitation": "A limit applied.",
            "question": "x" * 501,
        },
        {
            "type": "needs_input",
            "context": "x" * 1_001,
            "question": "Which one?",
        },
        {"type": "needs_input", "context": "Context.", "question": "x" * 501},
        {"type": "needs_input", "context": "Context.", "question": ""},
        {"type": "failed", "explanation": ""},
        {"type": "failed", "explanation": "x" * 2_001},
        {"type": "silent", "reason": "working"},
    ],
)
def test_terminal_content_bounds_are_strict(response: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _terminal(response)


def test_renderer_rejects_content_over_discord_limit() -> None:
    terminal = _terminal(
        {
            "type": "partial",
            "text": "x" * 2_000,
            "limitation": "A bounded read was incomplete.",
            "question": None,
        }
    )

    with pytest.raises(ValueError, match="Discord character bound"):
        render_terminal(terminal, TurnEvidence())


def test_rendered_terminal_cross_fields_are_strict() -> None:
    with pytest.raises(ValueError, match="silent terminal rendering"):
        RenderedTerminal("silent", "conversation", None)
    with pytest.raises(ValueError, match="visible terminal rendering"):
        RenderedTerminal("answered", "silent", "Done.")
    with pytest.raises(ValueError, match="visible terminal rendering"):
        RenderedTerminal("answered", "conversation", None)
    with pytest.raises(ValueError, match="Discord character bound"):
        RenderedTerminal("answered", "conversation", "x" * 2_001)


def test_incomplete_calendar_evidence_promotes_answered_to_partial() -> None:
    evidence = TurnEvidence()
    evidence.record_calendar_incompleteness(
        reasons=("calendar_failure", "event_limit"),
        calendars_discovered=35,
        calendars_completed=34,
        matched_events=None,
    )

    rendered = render_terminal(
        _terminal({"type": "answered", "text": "These are the next events."}),
        evidence,
    )

    assert rendered.outcome == "partial"
    assert rendered.conclusion_kind == "conversation"
    assert rendered.content == (
        "Partial result — Calendar coverage was incomplete: 34 of 35 calendar "
        "scans completed; one or more calendars could not be read; not every "
        "matching event fit in the response.\n\nThese are the next events."
    )


def test_incomplete_calendar_evidence_promotes_silent_to_visible_partial() -> None:
    evidence = TurnEvidence()
    evidence.record_calendar_incompleteness(
        reasons=("deadline",),
        calendars_discovered=35,
        calendars_completed=20,
        matched_events=None,
    )

    rendered = render_terminal(
        _terminal({"type": "silent", "reason": "owner_needs_no_response"}),
        evidence,
    )

    assert rendered.outcome == "partial"
    assert rendered.conclusion_kind == "conversation"
    assert rendered.content == (
        "Partial result — Calendar coverage was incomplete: 20 of 35 calendar "
        "scans completed; the calendar read reached its deadline.\n\n"
        "I couldn\u2019t produce a complete calendar answer."
    )


def test_multiple_incomplete_reads_have_deterministic_bounded_evidence() -> None:
    evidence = TurnEvidence()
    evidence.record_calendar_incompleteness(
        reasons=("event_page_limit", "output_byte_limit"),
        calendars_discovered=35,
        calendars_completed=35,
        matched_events=None,
    )
    evidence.record_calendar_incompleteness(
        reasons=("calendar_limit", "event_page_limit"),
        calendars_discovered=50,
        calendars_completed=50,
        matched_events=None,
    )

    rendered = render_terminal(
        _terminal({"type": "answered", "text": "Here is what I found."}), evidence
    )

    assert rendered.content == (
        "Partial result — Calendar coverage was incomplete across 2 reads: 85 of "
        "85 calendar scans completed; not every readable calendar fit within the "
        "calendar limit; the bounded event-read limit was reached; not every "
        "matching event fit in the response.\n\nHere is what I found."
    )
    assert rendered.content is not None
    assert len(rendered.content) <= 2_000


@pytest.mark.parametrize(
    ("reasons", "discovered", "completed", "matched"),
    [
        (("deadline", "deadline"), 1, 1, None),
        (("deadline", "calendar_failure"), 1, 0, None),
        (("unknown",), 1, 1, None),
        (("deadline",), -1, 0, None),
        (("deadline",), 51, 0, None),
        (("deadline",), 1, 2, None),
        (("deadline",), 1, 1, -1),
        (("deadline",), 1, 1, 0),
        (("event_limit",), 1, 1, None),
    ],
)
def test_turn_evidence_rejects_invalid_records(
    reasons: tuple[str, ...],
    discovered: int,
    completed: int,
    matched: int | None,
) -> None:
    evidence = TurnEvidence()

    with pytest.raises(ValueError):
        evidence.record_calendar_incompleteness(
            reasons=reasons,  # type: ignore[arg-type]
            calendars_discovered=discovered,
            calendars_completed=completed,
            matched_events=matched,
        )


def test_complete_calendar_observation_adds_no_incompleteness() -> None:
    evidence = TurnEvidence()
    evidence.record_calendar_incompleteness(
        reasons=(),
        calendars_discovered=35,
        calendars_completed=35,
        matched_events=80,
    )

    rendered = render_terminal(
        _terminal({"type": "answered", "text": "All 80 events were checked."}),
        evidence,
    )

    assert rendered.outcome == "answered"
    assert rendered.content == "All 80 events were checked."
