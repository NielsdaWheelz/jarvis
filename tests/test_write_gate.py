from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from llm_agent_kernel import (
    AdmissionGranted,
    AdmissionRequest,
    AdmissionUsage,
    BatchAsOfMode,
    CancellationToken,
    InputProjectionPolicy,
    OneShotCompleted,
    OneShotStopped,
    ProviderUsage,
    RunId,
    RunMetrics,
    ThreadId,
    ThreadStopKind,
    bootstrap_context,
)
from llm_tools import PromptSections, ToolId
from pydantic import ValidationError

from jarvis.admission import (
    RollingAdmissionLimits,
    RollingAdmissionPort,
    RootTrackingAdmissionPort,
)
from jarvis.definitions import AutomaticWriteGateResult, build_slice1_definitions
from jarvis.write_gate import (
    AutomaticWriteGate,
    EffectAudience,
    EffectTarget,
    GateOwnerInput,
    OmittedFreeform,
    WriteEffectDescriptor,
    owner_inputs_need_relative_time,
)

NOW = datetime(2026, 9, 6, 18, tzinfo=UTC)
OWNER_1 = UUID("00000000-0000-0000-0000-000000000001")
OWNER_2 = UUID("00000000-0000-0000-0000-000000000002")


def _inputs(*texts: str) -> tuple[GateOwnerInput, ...]:
    ids = (OWNER_1, OWNER_2)
    return tuple(
        GateOwnerInput(message_id=ids[index], text=text, created_at=NOW)
        for index, text in enumerate(texts)
    )


def _definition_and_plan() -> tuple[object, object]:
    definitions = build_slice1_definitions(
        profile_key="test", model="gpt-5.6-terra", owner_timezone="UTC"
    )
    definition = replace(
        definitions.automatic_write_gate,
        stable_context=PromptSections(()),
        input_projection_policy=InputProjectionPolicy(False, BatchAsOfMode.on_request),
    )
    return definition, definitions.plans["automatic_write_gate"]


async def _active_admission(
    tmp_path: Path,
) -> tuple[RootTrackingAdmissionPort, object]:
    limits = RollingAdmissionLimits(
        window_seconds=60,
        max_turns=20,
        max_input_tokens=500_000,
        max_output_tokens=100_000,
        root_input_token_overshoot=1,
        root_output_token_overshoot=1,
        serial_child_turns=10,
        serial_child_input_tokens=200_000,
        serial_child_output_tokens=20_000,
    )
    path = tmp_path / "admission.json"
    RollingAdmissionPort.initialize(path, limits)
    admission = RootTrackingAdmissionPort(RollingAdmissionPort(path, limits))
    root = await admission.reserve(
        AdmissionRequest(RunId("root"), ThreadId("thread"), 1, 3, 10_000, 1_000)
    )
    assert isinstance(root, AdmissionGranted)
    return admission, root.token


def _descriptor() -> WriteEffectDescriptor:
    return WriteEffectDescriptor(
        operation="create",
        targets=(EffectTarget(kind="calendar_id", value="owner"),),
        audience=(EffectAudience(kind="attendee", address="owner@example.test"),),
        starts_at="2026-09-07T18:00:00-07:00",
        ends_at="2026-09-07T18:30:00-07:00",
        notify_attendees=False,
        omitted_freeform=(OmittedFreeform.from_text("summary", "Private summary"),),
    )


def _metrics() -> RunMetrics:
    return RunMetrics(RunId("gate"), 1, ProviderUsage(100, 20), 0.5, False)


async def test_gate_uses_only_restricted_projection_and_active_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    definition, plan = _definition_and_plan()
    admission, root = await _active_admission(tmp_path)
    observed: dict[str, object] = {}

    async def completed(**kwargs: object) -> OneShotCompleted:
        observed.update(kwargs)
        return OneShotCompleted(
            _metrics(),
            AutomaticWriteGateResult(
                decision="allow",
                supporting_owner_message_ids=[str(OWNER_1)],
            ).model_dump(mode="json"),
        )

    monkeypatch.setattr("jarvis.write_gate.run_one_shot", completed)
    gate = AutomaticWriteGate(
        definition=cast(Any, definition),
        plan=cast(Any, plan),
        admission=admission,
        provider=cast(Any, object()),
    )
    decision = await gate.evaluate(
        _inputs("Create the event for the owner."),
        tool_id=ToolId("calendar.create_event"),
        descriptor=_descriptor(),
        owner_timezone="America/Los_Angeles",
        as_of=NOW,
        cancellation=CancellationToken(),
    )

    assert decision.allowed
    assert decision.supporting_owner_message_ids == (OWNER_1,)
    assert observed["parent_admission"] == root
    assert observed["input_projection"] is None
    projection = bootstrap_context(
        cast(Any, observed["definition"]),
        cast(Any, observed["inputs"]),
        cast(Any, observed["as_of"]),
        cast(Any, observed["plan"]),
        cast(Any, observed["source_sections"]),
        input_projection=None,
    ).rendered
    assert "Private summary" not in projection
    assert "owner_timezone" not in projection
    assert "source_timestamp" not in projection
    assert 'as_of="' not in projection
    assert '"utf8_bytes":15' in projection
    assert '"canonical_tool_id":"calendar.create_event"' in projection

    await admission.settle(cast(Any, root), AdmissionUsage(0, ProviderUsage(), 0))


async def test_relative_time_alone_requests_time_projection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    definition, plan = _definition_and_plan()
    admission, root = await _active_admission(tmp_path)
    observed: dict[str, object] = {}

    async def denied(**kwargs: object) -> OneShotCompleted:
        observed.update(kwargs)
        return OneShotCompleted(
            _metrics(),
            {"decision": "deny", "supporting_owner_message_ids": []},
        )

    monkeypatch.setattr("jarvis.write_gate.run_one_shot", denied)
    gate = AutomaticWriteGate(
        definition=cast(Any, definition),
        plan=cast(Any, plan),
        admission=admission,
        provider=cast(Any, object()),
    )
    decision = await gate.evaluate(
        _inputs("Create it tomorrow morning."),
        tool_id=ToolId("calendar.create_event"),
        descriptor=_descriptor(),
        owner_timezone="America/Los_Angeles",
        as_of=NOW,
        cancellation=CancellationToken(),
    )

    assert not decision.allowed
    assert cast(Any, observed["input_projection"]).render_batch_as_of
    projection = bootstrap_context(
        cast(Any, observed["definition"]),
        cast(Any, observed["inputs"]),
        cast(Any, observed["as_of"]),
        cast(Any, observed["plan"]),
        cast(Any, observed["source_sections"]),
        input_projection=cast(Any, observed["input_projection"]),
    ).rendered
    assert 'owner_timezone":"America/Los_Angeles"' in projection
    assert 'as_of="2026-09-06T18:00:00+00:00"' in projection
    assert "source_timestamp" not in projection

    await admission.settle(cast(Any, root), AdmissionUsage(0, ProviderUsage(), 0))


@pytest.mark.parametrize(
    ("result", "outcome"),
    [
        ({"decision": "allow", "supporting_owner_message_ids": []}, "invalid_support"),
        (
            {
                "decision": "allow",
                "supporting_owner_message_ids": [str(OWNER_2), str(OWNER_1)],
            },
            "invalid_support",
        ),
        (
            {
                "decision": "allow",
                "supporting_owner_message_ids": [str(OWNER_1), str(OWNER_1)],
            },
            "invalid_support",
        ),
        (
            {
                "decision": "deny",
                "supporting_owner_message_ids": [str(OWNER_1)],
            },
            "invalid_support",
        ),
        ({"decision": "maybe", "supporting_owner_message_ids": []}, "invalid_result"),
    ],
)
async def test_gate_rejects_invalid_or_noncurrent_support(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    result: dict[str, object],
    outcome: str,
) -> None:
    definition, plan = _definition_and_plan()
    admission, root = await _active_admission(tmp_path)

    async def completed(**kwargs: object) -> OneShotCompleted:
        del kwargs
        return OneShotCompleted(_metrics(), result)

    monkeypatch.setattr("jarvis.write_gate.run_one_shot", completed)
    gate = AutomaticWriteGate(
        definition=cast(Any, definition),
        plan=cast(Any, plan),
        admission=admission,
        provider=cast(Any, object()),
    )
    decision = await gate.evaluate(
        _inputs("First", "Second"),
        tool_id=ToolId("gmail.create_draft"),
        descriptor=_descriptor(),
        owner_timezone=None,
        as_of=NOW,
        cancellation=CancellationToken(),
    )

    assert not decision.allowed
    assert decision.supporting_owner_message_ids == ()
    assert decision.terminal_outcome == outcome
    await admission.settle(cast(Any, root), AdmissionUsage(0, ProviderUsage(), 0))


async def test_gate_stops_and_empty_owner_input_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    definition, plan = _definition_and_plan()
    admission, root = await _active_admission(tmp_path)
    calls = 0

    async def stopped(**kwargs: object) -> OneShotStopped:
        nonlocal calls
        del kwargs
        calls += 1
        return OneShotStopped(_metrics(), ThreadStopKind.provider_error)

    monkeypatch.setattr("jarvis.write_gate.run_one_shot", stopped)
    gate = AutomaticWriteGate(
        definition=cast(Any, definition),
        plan=cast(Any, plan),
        admission=admission,
        provider=cast(Any, object()),
    )
    empty = await gate.evaluate(
        (),
        tool_id=ToolId("gmail.create_draft"),
        descriptor=_descriptor(),
        owner_timezone=None,
        as_of=NOW,
        cancellation=CancellationToken(),
    )
    stopped_decision = await gate.evaluate(
        _inputs("Draft the message."),
        tool_id=ToolId("gmail.create_draft"),
        descriptor=_descriptor(),
        owner_timezone=None,
        as_of=NOW,
        cancellation=CancellationToken(),
    )

    assert empty.terminal_outcome == "no_owner_input"
    assert empty.run_id is None
    assert stopped_decision.terminal_outcome == "provider_error"
    assert calls == 1
    await admission.settle(cast(Any, root), AdmissionUsage(0, ProviderUsage(), 0))


def test_gate_definition_and_descriptor_boundaries() -> None:
    definition, plan = _definition_and_plan()
    with pytest.raises(ValueError, match="input projection policy"):
        AutomaticWriteGate(
            definition=replace(
                cast(Any, definition),
                input_projection_policy=InputProjectionPolicy(),
            ),
            plan=cast(Any, plan),
            admission=cast(Any, object()),
            provider=cast(Any, object()),
        )
    with pytest.raises(ValidationError, match="target kinds must be unique"):
        WriteEffectDescriptor(
            operation="update",
            targets=(
                EffectTarget(kind="draft_id", value="one"),
                EffectTarget(kind="draft_id", value="two"),
            ),
        )
    omitted = OmittedFreeform.from_text("body_text", "synthetic secret")
    assert omitted.utf8_bytes == 16
    assert omitted.sha256 == (
        "2ef421e10e1688c4df43290c46ae2ac0db71b202a48e20d33d223bf2b6ea4442"
    )


def test_relative_time_classifier_is_deterministic() -> None:
    assert owner_inputs_need_relative_time(_inputs("Remind me next Tuesday."))
    assert owner_inputs_need_relative_time(_inputs("Create it in 2 hours."))
    assert owner_inputs_need_relative_time(_inputs("Remind me in half an hour."))
    assert owner_inputs_need_relative_time(_inputs("Remind me in half hour."))
    assert owner_inputs_need_relative_time(_inputs("Remind me an hour from now."))
    assert not owner_inputs_need_relative_time(_inputs("Draft the final report."))
