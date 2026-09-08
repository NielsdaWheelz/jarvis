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
    RootTrackingAdmissionPort,
    slice3_admission_limits,
    slice5_admission_limits,
    slice6_admission_limits,
)
from jarvis.definitions import (
    SLICE2_KERNEL_LIMITS,
    SLICE3_RECALL_KERNEL_LIMITS,
    SLICE3_REMEMBER_KERNEL_LIMITS,
    build_slice1_definitions,
)


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


async def test_tracking_wrapper_exposes_one_validated_root_to_one_serial_child(
    tmp_path: Path,
) -> None:
    path = tmp_path / "admission.json"
    selected = limits(
        serial_child_turns=1,
        serial_child_input_tokens=30,
        serial_child_output_tokens=10,
    )
    RollingAdmissionPort.initialize(path, selected)
    port = RootTrackingAdmissionPort(RollingAdmissionPort(path, selected))
    root = await port.reserve(
        AdmissionRequest(RunId("root"), ThreadId("channel-1"), 1, 2, 100, 20)
    )
    assert isinstance(root, AdmissionGranted)
    assert await port.active_root() == root.token
    child = await port.reserve(
        AdmissionRequest(RunId("child"), None, None, 1, 20, 5, root.token)
    )
    assert isinstance(child, AdmissionGranted)
    with pytest.raises(AdmissionStateDefect):
        await port.active_root()
    await port.settle(
        child.token,
        AdmissionUsage(1, ProviderUsage(input_tokens=8, output_tokens=2), 1.0),
    )
    await port.settle(
        root.token,
        AdmissionUsage(1, ProviderUsage(input_tokens=12, output_tokens=4), 1.0),
    )
    with pytest.raises(AdmissionStateDefect):
        await port.active_root()


def test_slice3_capacity_reserves_one_recaller_per_maximum_owner_input() -> None:
    selected = slice3_admission_limits(20)
    assert selected.serial_child_turns == 200
    assert selected.serial_child_input_tokens == 3_855_360
    assert selected.serial_child_output_tokens == 483_840


def test_slice5_capacity_reserves_recallers_and_write_gates() -> None:
    selected = slice5_admission_limits(20)
    assert selected.json() == {
        "max_input_tokens": 6_805_184,
        "max_no_progress_attempts": 3,
        "max_output_tokens": 1_027_296,
        "max_turns": 276,
        "root_input_token_overshoot": 32_768,
        "root_output_token_overshoot": 8_192,
        "serial_child_input_tokens": 5_979_648,
        "serial_child_output_tokens": 934_912,
        "serial_child_turns": 248,
        "window_seconds": 21_600,
    }


def test_slice6_capacity_reserves_recallers_and_every_write_gate() -> None:
    selected = slice6_admission_limits(20)
    assert selected.json() == {
        "max_input_tokens": 13_683_136,
        "max_no_progress_attempts": 3,
        "max_output_tokens": 2_086_784,
        "max_turns": 548,
        "root_input_token_overshoot": 32_768,
        "root_output_token_overshoot": 8_192,
        "serial_child_input_tokens": 6_112_416,
        "serial_child_output_tokens": 963_104,
        "serial_child_turns": 251,
        "window_seconds": 21_600,
    }


async def test_slice6_capacity_admits_after_a_normal_completed_turn(
    tmp_path: Path,
) -> None:
    path = tmp_path / "admission.json"
    selected = slice6_admission_limits(20)
    RollingAdmissionPort.initialize(path, selected)
    port = RollingAdmissionPort(
        path,
        selected,
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )

    first = await port.reserve(
        AdmissionRequest(
            RunId("bootstrap"),
            ThreadId("channel-1"),
            1,
            18,
            600_000,
            60_000,
        )
    )
    assert isinstance(first, AdmissionGranted)
    await port.settle(
        first.token,
        AdmissionUsage(
            15,
            ProviderUsage(input_tokens=158_906, output_tokens=1_689),
            90.0,
        ),
    )

    assert (
        await port.preflight(
            maximum_turns=18,
            maximum_input_tokens=600_000,
            maximum_output_tokens=60_000,
        )
        is None
    )


async def test_slice6_limit_migration_reserves_the_new_approval_write_gate(
    tmp_path: Path,
) -> None:
    previous = slice5_admission_limits(20)
    current = slice6_admission_limits(20)
    path = tmp_path / "admission.json"
    RollingAdmissionPort.initialize(path, previous)
    now = datetime(2026, 9, 7, tzinfo=UTC)
    port = RollingAdmissionPort(path, previous, clock=lambda: now)
    root = await port.reserve(
        AdmissionRequest(
            RunId("slice-five-root"),
            ThreadId("channel"),
            1,
            SLICE2_KERNEL_LIMITS.max_provider_turns,
            SLICE2_KERNEL_LIMITS.max_provider_input_tokens,
            SLICE2_KERNEL_LIMITS.max_provider_output_tokens,
        )
    )
    assert isinstance(root, AdmissionGranted)
    assert await port.recover_orphans() == (RunId("slice-five-root"),)

    assert RollingAdmissionPort.migrate_limits(path, previous=previous, current=current)
    state = json.loads(path.read_text(encoding="utf-8"))
    reservation = state["reservations"][0]
    assert state["configuration"] == current.json()
    assert reservation["reserved_turns"] == root.token.reserved_turns + 3
    assert reservation["reserved_input_tokens"] == (
        root.token.reserved_input_tokens + 132_768
    )
    assert reservation["reserved_output_tokens"] == (
        root.token.reserved_output_tokens + 28_192
    )
    assert reservation["actual_turns"] == reservation["reserved_turns"]
    assert reservation["actual_input_tokens"] == reservation["reserved_input_tokens"]
    assert reservation["actual_output_tokens"] == reservation["reserved_output_tokens"]
    assert not RollingAdmissionPort.migrate_limits(
        path, previous=previous, current=current
    )


async def test_slice5_limit_migration_conservatively_enlarges_interrupted_root(
    tmp_path: Path,
) -> None:
    previous = slice3_admission_limits(20)
    current = slice5_admission_limits(20)
    path = tmp_path / "admission.json"
    RollingAdmissionPort.initialize(path, previous)
    now = datetime(2026, 9, 6, tzinfo=UTC)
    port = RollingAdmissionPort(path, previous, clock=lambda: now)
    root = await port.reserve(
        AdmissionRequest(
            RunId("slice-four-root"),
            ThreadId("channel"),
            1,
            SLICE2_KERNEL_LIMITS.max_provider_turns,
            SLICE2_KERNEL_LIMITS.max_provider_input_tokens,
            SLICE2_KERNEL_LIMITS.max_provider_output_tokens,
        )
    )
    assert isinstance(root, AdmissionGranted)
    assert await port.recover_orphans() == (RunId("slice-four-root"),)

    assert RollingAdmissionPort.migrate_limits(path, previous=previous, current=current)
    state = json.loads(path.read_text(encoding="utf-8"))
    reservation = state["reservations"][0]
    assert state["configuration"] == current.json()
    assert reservation["reserved_turns"] == root.token.reserved_turns + 48
    assert reservation["reserved_input_tokens"] == (
        root.token.reserved_input_tokens + 2_124_288
    )
    assert reservation["reserved_output_tokens"] == (
        root.token.reserved_output_tokens + 451_072
    )
    assert reservation["actual_turns"] == reservation["reserved_turns"]
    assert reservation["actual_input_tokens"] == reservation["reserved_input_tokens"]
    assert reservation["actual_output_tokens"] == reservation["reserved_output_tokens"]
    assert not RollingAdmissionPort.migrate_limits(
        path, previous=previous, current=current
    )


async def test_slice3_capacity_fits_worst_foreground_then_background_rememberer(
    tmp_path: Path,
) -> None:
    maximum_owner_inputs = 20
    selected = slice3_admission_limits(maximum_owner_inputs)
    path = tmp_path / "admission.json"
    RollingAdmissionPort.initialize(path, selected)
    port = RollingAdmissionPort(
        path,
        selected,
        clock=lambda: datetime(2026, 9, 4, tzinfo=UTC),
    )
    main = SLICE2_KERNEL_LIMITS
    foreground = await port.reserve(
        AdmissionRequest(
            RunId("foreground"),
            ThreadId("channel"),
            1,
            main.max_provider_turns,
            main.max_provider_input_tokens,
            main.max_provider_output_tokens,
        )
    )
    assert isinstance(foreground, AdmissionGranted)
    recall = SLICE3_RECALL_KERNEL_LIMITS
    for index in range(maximum_owner_inputs):
        child = await port.reserve(
            AdmissionRequest(
                RunId(f"recaller-{index}"),
                None,
                None,
                recall.max_provider_turns,
                recall.max_provider_input_tokens,
                recall.max_provider_output_tokens,
                foreground.token,
            )
        )
        assert isinstance(child, AdmissionGranted)
        await port.settle(
            child.token,
            AdmissionUsage(
                recall.max_provider_turns,
                ProviderUsage(input_tokens=None, output_tokens=None),
                60.0,
            ),
        )
    await port.settle(
        foreground.token,
        AdmissionUsage(
            main.max_provider_turns,
            ProviderUsage(input_tokens=None, output_tokens=None),
            300.0,
        ),
    )

    remember = SLICE3_REMEMBER_KERNEL_LIMITS
    background = await port.reserve(
        AdmissionRequest(
            RunId("rememberer"),
            None,
            None,
            remember.max_provider_turns,
            remember.max_provider_input_tokens,
            remember.max_provider_output_tokens,
        )
    )
    assert isinstance(background, AdmissionGranted)
    assert background.token.reserved_turns == remember.max_provider_turns
    assert background.token.reserved_input_tokens == (
        remember.max_provider_input_tokens + selected.root_input_token_overshoot
    )
    assert background.token.reserved_output_tokens == (
        remember.max_provider_output_tokens + selected.root_output_token_overshoot
    )


async def test_plan_factory_returns_fresh_exact_budget() -> None:
    definitions = build_slice1_definitions(
        profile_key="jarvis-test", model="gpt-5.6-terra", owner_timezone="UTC"
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
