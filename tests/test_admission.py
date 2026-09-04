from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from llm_agent_kernel import (
    AdmissionGranted,
    AdmissionRequest,
    AdmissionStateDefect,
    AdmissionUsage,
    ProviderUsage,
    RunId,
    ThreadId,
)
from llm_tools import InvocationPosition, Reservation, RunLimits, Settlement

from jarvis.admission import (
    ExactToolBudgetFactory,
    RollingAdmissionLimits,
    RollingAdmissionPort,
)
from jarvis.definitions import build_slice1_definitions


def limits(**changes: int) -> RollingAdmissionLimits:
    values = {
        "window_seconds": 60,
        "max_turns": 8,
        "max_input_tokens": 500,
        "max_output_tokens": 200,
        "max_no_progress_attempts": 3,
        "root_input_token_overshoot": 10,
        "root_output_token_overshoot": 5,
        "serial_child_turns": 0,
        "serial_child_input_tokens": 0,
        "serial_child_output_tokens": 0,
    }
    values.update(changes)
    return RollingAdmissionLimits(**values)


async def test_missing_and_corrupt_admission_journal_fail_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "admission.json"
    port = RollingAdmissionPort(path, limits())
    with pytest.raises(AdmissionStateDefect):
        await port.preflight(
            maximum_turns=2, maximum_input_tokens=100, maximum_output_tokens=20
        )

    path.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(AdmissionStateDefect):
        await port.recover_orphans()


async def test_reservation_refunds_unused_capacity_on_clean_settlement(
    tmp_path: Path,
) -> None:
    path = tmp_path / "admission.json"
    selected = limits()
    RollingAdmissionPort.initialize(path, selected)
    now = datetime(2026, 9, 3, tzinfo=UTC)
    port = RollingAdmissionPort(path, selected, clock=lambda: now)

    assert (
        await port.preflight(
            maximum_turns=2, maximum_input_tokens=100, maximum_output_tokens=20
        )
        is None
    )
    result = await port.reserve(
        AdmissionRequest(RunId("run-1"), ThreadId("channel-1"), 1, 2, 100, 20)
    )
    assert isinstance(result, AdmissionGranted)
    assert result.token.reserved_input_tokens == 110
    assert result.token.reserved_output_tokens == 25
    await port.settle(
        result.token,
        AdmissionUsage(1, ProviderUsage(input_tokens=12, output_tokens=4), 1.0),
    )

    state = json.loads(path.read_text(encoding="utf-8"))
    reservation = state["reservations"][0]
    assert reservation["state"] == "settled"
    assert reservation["owns_live_slot"] is False
    assert reservation["actual_turns"] == 1
    assert reservation["actual_input_tokens"] == 12
    assert reservation["actual_output_tokens"] == 4


async def test_orphan_recovery_releases_slot_without_refund(tmp_path: Path) -> None:
    path = tmp_path / "admission.json"
    selected = limits()
    RollingAdmissionPort.initialize(path, selected)
    now = datetime(2026, 9, 3, tzinfo=UTC)
    port = RollingAdmissionPort(path, selected, clock=lambda: now)
    result = await port.reserve(
        AdmissionRequest(RunId("run-1"), ThreadId("channel-1"), 1, 2, 100, 20)
    )
    assert isinstance(result, AdmissionGranted)

    assert await port.recover_orphans() == (RunId("run-1"),)
    state = json.loads(path.read_text(encoding="utf-8"))["reservations"][0]
    assert state["state"] == "interrupted"
    assert state["owns_live_slot"] is False
    assert state["actual_turns"] == state["reserved_turns"]
    assert await port.recover_orphans() == ()

    delayed = RollingAdmissionPort(
        path, selected, clock=lambda: now + timedelta(seconds=61)
    )
    assert (
        await delayed.preflight(
            maximum_turns=2, maximum_input_tokens=100, maximum_output_tokens=20
        )
        is None
    )


async def test_child_reservation_shares_root_slot_and_charge(tmp_path: Path) -> None:
    path = tmp_path / "admission.json"
    selected = limits(
        serial_child_turns=1,
        serial_child_input_tokens=30,
        serial_child_output_tokens=10,
    )
    RollingAdmissionPort.initialize(path, selected)
    port = RollingAdmissionPort(
        path, selected, clock=lambda: datetime(2026, 9, 3, tzinfo=UTC)
    )
    root = await port.reserve(
        AdmissionRequest(RunId("root"), ThreadId("channel-1"), 1, 2, 100, 20)
    )
    assert isinstance(root, AdmissionGranted)
    child = await port.reserve(
        AdmissionRequest(RunId("child"), None, None, 1, 20, 5, root.token)
    )
    assert isinstance(child, AdmissionGranted)
    assert child.token.owns_live_slot is False
    assert child.token.root_epoch_id == root.token.root_epoch_id
    await port.settle(
        child.token,
        AdmissionUsage(1, ProviderUsage(input_tokens=8, output_tokens=2), 1.0),
    )
    await port.settle(
        root.token,
        AdmissionUsage(1, ProviderUsage(input_tokens=12, output_tokens=4), 1.0),
    )
    state = json.loads(path.read_text(encoding="utf-8"))["reservations"][0]
    assert state["actual_turns"] == 2
    assert state["actual_input_tokens"] == 20
    assert state["actual_output_tokens"] == 6


async def test_plan_factory_returns_fresh_exact_budget() -> None:
    definitions = build_slice1_definitions(
        profile_key="jarvis-test", model="gpt-5.4", owner_timezone="UTC"
    )
    plan = definitions.plans["main"]
    factory = ExactToolBudgetFactory()
    first = factory.create(plan)
    second = factory.create(plan)

    assert first is not second
    assert first.limits == plan.profile.run_limits
    assert await first.reserve(InvocationPosition("position"), Reservation(1, 1, 0, 64))
    await first.settle(InvocationPosition("position"), Settlement(0, 1))
    assert second.remaining_elapsed_seconds > 0


def test_budget_factory_accepts_only_run_limits() -> None:
    with pytest.raises((TypeError, ValueError)):
        RunLimits(1, 0, 1, 1, 1, 0)
