from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from llm_agent_kernel import (
    AdmissionDeferred,
    AdmissionGranted,
    AdmissionRejected,
    AdmissionRequest,
    AdmissionResult,
    AdmissionStateDefect,
    AdmissionToken,
    AdmissionUsage,
    RunId,
)
from llm_tools import (
    BudgetState,
    FrozenToolPlan,
    InvocationPosition,
    Reservation,
    RunLimits,
    Settlement,
)
from pydantic import BaseModel, ConfigDict, Field

from jarvis._atomic_json import read_private_json, replace_private_json
from jarvis.definitions import (
    MAIN_KERNEL_LIMITS,
    MAIN_TOOL_LIMITS,
    RECALLER_KERNEL_LIMITS,
    REMEMBERER_KERNEL_LIMITS,
    WRITE_GATE_KERNEL_LIMITS,
)


@dataclass(frozen=True, slots=True)
class RollingAdmissionLimits:
    window_seconds: int = 21_600
    max_turns: int = 24
    max_input_tokens: int = 800_000
    max_output_tokens: int = 160_000
    max_no_progress_attempts: int = 3
    root_input_token_overshoot: int = 32_768
    root_output_token_overshoot: int = 8_192
    serial_child_turns: int = 0
    serial_child_input_tokens: int = 0
    serial_child_output_tokens: int = 0

    def __post_init__(self) -> None:
        positive = (
            self.window_seconds,
            self.max_turns,
            self.max_input_tokens,
            self.max_output_tokens,
            self.max_no_progress_attempts,
            self.root_input_token_overshoot,
            self.root_output_token_overshoot,
        )
        non_negative = (
            self.serial_child_turns,
            self.serial_child_input_tokens,
            self.serial_child_output_tokens,
        )
        if any(type(value) is not int or value <= 0 for value in positive):
            raise ValueError("rolling admission limits must be positive integers")
        if any(type(value) is not int or value < 0 for value in non_negative):
            raise ValueError(
                "serial-child admission limits must be non-negative integers"
            )

    def json(self) -> dict[str, int]:
        return {
            "max_input_tokens": self.max_input_tokens,
            "max_no_progress_attempts": self.max_no_progress_attempts,
            "max_output_tokens": self.max_output_tokens,
            "max_turns": self.max_turns,
            "root_input_token_overshoot": self.root_input_token_overshoot,
            "root_output_token_overshoot": self.root_output_token_overshoot,
            "serial_child_input_tokens": self.serial_child_input_tokens,
            "serial_child_output_tokens": self.serial_child_output_tokens,
            "serial_child_turns": self.serial_child_turns,
            "window_seconds": self.window_seconds,
        }


class _Child(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual_input_tokens: int | None = Field(default=None, ge=0)
    actual_output_tokens: int | None = Field(default=None, ge=0)
    actual_turns: int | None = Field(default=None, ge=0)
    reserved_input_tokens: int = Field(gt=0)
    reserved_output_tokens: int = Field(gt=0)
    reserved_turns: int = Field(gt=0)
    run_id: str = Field(min_length=1)
    state: str


class _Root(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual_input_tokens: int | None = Field(default=None, ge=0)
    actual_output_tokens: int | None = Field(default=None, ge=0)
    actual_turns: int | None = Field(default=None, ge=0)
    attempt_number: int | None = Field(default=None, gt=0)
    children: list[_Child]
    created_at: datetime
    expires_at: datetime
    owns_live_slot: bool
    reserved_input_tokens: int = Field(gt=0)
    reserved_output_tokens: int = Field(gt=0)
    reserved_turns: int = Field(gt=0)
    root_epoch_id: str = Field(min_length=1)
    root_reserved_input_tokens: int = Field(gt=0)
    root_reserved_output_tokens: int = Field(gt=0)
    root_reserved_turns: int = Field(gt=0)
    run_id: str = Field(min_length=1)
    state: str
    thread_id: str | None
    window_id: str = Field(min_length=1)


class _Journal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configuration: dict[str, int]
    reservations: list[_Root]
    schema_version: str


class RollingAdmissionPort:
    """Content-free rolling capacity with conservative crash accounting."""

    def __init__(
        self,
        path: Path,
        limits: RollingAdmissionLimits,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not path.is_absolute():
            raise ValueError("admission journal path must be absolute")
        self._path = path
        self._limits = limits
        self._clock = clock
        self._lock = asyncio.Lock()

    @classmethod
    def initialize(
        cls,
        path: Path,
        limits: RollingAdmissionLimits,
        *,
        replace: bool = False,
    ) -> None:
        if path.exists() and not replace:
            raise FileExistsError("admission journal already exists")
        replace_private_json(
            path,
            {
                "configuration": limits.json(),
                "reservations": [],
                "schema_version": "jarvis-admission.v1",
            },
        )

    async def preflight(
        self,
        *,
        maximum_turns: int,
        maximum_input_tokens: int,
        maximum_output_tokens: int,
    ) -> datetime | None:
        request = _required_root(
            maximum_turns,
            maximum_input_tokens,
            maximum_output_tokens,
            self._limits,
            include_serial_children=True,
        )
        async with self._lock:
            now = self._now()
            journal = self._read()
            changed = _prune(journal, now)
            if any(root.owns_live_slot for root in journal.reservations):
                raise AdmissionStateDefect(
                    "admission journal contains an active root slot"
                )
            reset_at = _capacity_reset(journal, now, self._limits, request)
            if changed:
                self._write(journal)
            return reset_at

    async def preflight_background(
        self,
        *,
        maximum_turns: int,
        maximum_input_tokens: int,
        maximum_output_tokens: int,
    ) -> datetime | None:
        request = _required_root(
            maximum_turns,
            maximum_input_tokens,
            maximum_output_tokens,
            self._limits,
            include_serial_children=False,
        )
        async with self._lock:
            now = self._now()
            journal = self._read()
            changed = _prune(journal, now)
            if any(root.owns_live_slot for root in journal.reservations):
                raise AdmissionStateDefect(
                    "admission journal contains an active root slot"
                )
            reset_at = _capacity_reset(journal, now, self._limits, request)
            if changed:
                self._write(journal)
            return reset_at

    async def reserve(self, request: AdmissionRequest) -> AdmissionResult:
        async with self._lock:
            now = self._now()
            journal = self._read()
            changed = _prune(journal, now)
            if request.parent is not None:
                result = _reserve_child(journal, request, self._limits)
                self._write(journal)
                return result
            if any(
                root.run_id == str(request.run_id)
                or any(child.run_id == str(request.run_id) for child in root.children)
                for root in journal.reservations
            ):
                raise AdmissionStateDefect(
                    "admission run id already exists in the window"
                )

            required = _required_root(
                request.maximum_turns,
                request.maximum_input_tokens,
                request.maximum_output_tokens,
                self._limits,
                include_serial_children=request.thread_id is not None,
            )
            if request.thread_id is not None and (
                request.attempt_number is None
                or request.attempt_number > self._limits.max_no_progress_attempts
            ):
                return AdmissionRejected("durable no-progress attempt ceiling exceeded")
            if any(root.owns_live_slot for root in journal.reservations):
                if request.thread_id is not None:
                    raise AdmissionStateDefect(
                        "capacity changed after successful foreground preflight"
                    )
                return AdmissionDeferred(now + timedelta(seconds=1))
            reset_at = _capacity_reset(journal, now, self._limits, required)
            if reset_at is not None:
                if changed:
                    self._write(journal)
                if request.thread_id is not None:
                    raise AdmissionStateDefect(
                        "capacity changed after successful foreground preflight"
                    )
                return AdmissionDeferred(reset_at)

            window_id = f"rolling:{now.isoformat()}"
            epoch = str(uuid4())
            root_turns = request.maximum_turns
            root_input = (
                request.maximum_input_tokens + self._limits.root_input_token_overshoot
            )
            root_output = (
                request.maximum_output_tokens + self._limits.root_output_token_overshoot
            )
            journal.reservations.append(
                _Root(
                    actual_input_tokens=None,
                    actual_output_tokens=None,
                    actual_turns=None,
                    attempt_number=request.attempt_number,
                    children=[],
                    created_at=now,
                    expires_at=now + timedelta(seconds=self._limits.window_seconds),
                    owns_live_slot=True,
                    reserved_input_tokens=required[1],
                    reserved_output_tokens=required[2],
                    reserved_turns=required[0],
                    root_epoch_id=epoch,
                    root_reserved_input_tokens=root_input,
                    root_reserved_output_tokens=root_output,
                    root_reserved_turns=root_turns,
                    run_id=str(request.run_id),
                    state="active",
                    thread_id=None
                    if request.thread_id is None
                    else str(request.thread_id),
                    window_id=window_id,
                )
            )
            self._write(journal)
            return AdmissionGranted(
                AdmissionToken(
                    request.run_id,
                    window_id,
                    epoch,
                    required[0],
                    required[1],
                    required[2],
                    True,
                )
            )

    async def settle(self, token: AdmissionToken, usage: AdmissionUsage) -> None:
        async with self._lock:
            journal = self._read()
            root = next(
                (
                    item
                    for item in journal.reservations
                    if item.root_epoch_id == token.root_epoch_id
                ),
                None,
            )
            if root is None or root.window_id != token.window_id:
                raise AdmissionStateDefect("admission settlement names an unknown root")
            if token.owns_live_slot:
                _settle_root(root, token, usage)
            else:
                _settle_child(root, token, usage)
            self._write(journal)

    async def recover_orphans(self) -> tuple[RunId, ...]:
        async with self._lock:
            journal = self._read()
            recovered: list[RunId] = []
            for root in journal.reservations:
                if root.state != "active":
                    continue
                root.state = "interrupted"
                root.owns_live_slot = False
                root.actual_turns = root.reserved_turns
                root.actual_input_tokens = root.reserved_input_tokens
                root.actual_output_tokens = root.reserved_output_tokens
                for child in root.children:
                    if child.state == "active":
                        child.state = "interrupted"
                recovered.append(RunId(root.run_id))
            if recovered:
                self._write(journal)
            return tuple(recovered)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise AdmissionStateDefect("admission clock must be timezone-aware")
        return value.astimezone(UTC)

    def _read(self) -> _Journal:
        try:
            value = read_private_json(self._path)
            if value is None:
                raise ValueError("admission journal is missing")
            journal = _Journal.model_validate(value)
            if journal.schema_version != "jarvis-admission.v1":
                raise ValueError("admission journal version is invalid")
            if journal.configuration != self._limits.json():
                raise ValueError("admission journal configuration changed")
            if journal.model_dump(mode="json") != dict(value):
                raise ValueError("admission journal is not canonical")
            _validate_journal(journal, self._limits)
            return journal
        except (OSError, TypeError, ValueError) as error:
            raise AdmissionStateDefect(
                "admission journal is missing or corrupt"
            ) from error

    def _write(self, journal: _Journal) -> None:
        replace_private_json(self._path, journal.model_dump(mode="json"))


class RootTrackingAdmissionPort:
    """Track the validated root and expose foreground roots to serial children."""

    def __init__(self, delegate: RollingAdmissionPort) -> None:
        self._delegate = delegate
        self._lock = asyncio.Lock()
        self._root: AdmissionToken | None = None
        self._child: AdmissionToken | None = None

    async def preflight(
        self,
        *,
        maximum_turns: int,
        maximum_input_tokens: int,
        maximum_output_tokens: int,
    ) -> datetime | None:
        return await self._delegate.preflight(
            maximum_turns=maximum_turns,
            maximum_input_tokens=maximum_input_tokens,
            maximum_output_tokens=maximum_output_tokens,
        )

    async def active_root(self) -> AdmissionToken:
        async with self._lock:
            if self._root is None or not self._root.owns_live_slot:
                raise AdmissionStateDefect("serial child has no active root admission")
            if self._child is not None:
                raise AdmissionStateDefect("another serial child admission is active")
            return self._root

    async def preflight_background(
        self,
        *,
        maximum_turns: int,
        maximum_input_tokens: int,
        maximum_output_tokens: int,
    ) -> datetime | None:
        return await self._delegate.preflight_background(
            maximum_turns=maximum_turns,
            maximum_input_tokens=maximum_input_tokens,
            maximum_output_tokens=maximum_output_tokens,
        )

    async def reserve(self, request: AdmissionRequest) -> AdmissionResult:
        async with self._lock:
            if request.parent is None:
                if self._root is not None:
                    raise AdmissionStateDefect(
                        "admission wrapper already has an active root"
                    )
            elif request.parent != self._root or self._child is not None:
                raise AdmissionStateDefect(
                    "serial child admission parent is not active"
                )
            result = await self._delegate.reserve(request)
            if isinstance(result, AdmissionGranted):
                if request.parent is None:
                    if not result.token.owns_live_slot:
                        raise AdmissionStateDefect(
                            "root admission returned a child token"
                        )
                    self._root = result.token
                else:
                    if result.token.owns_live_slot:
                        raise AdmissionStateDefect(
                            "child admission returned a root token"
                        )
                    self._child = result.token
            return result

    async def settle(self, token: AdmissionToken, usage: AdmissionUsage) -> None:
        async with self._lock:
            if token == self._child:
                await self._delegate.settle(token, usage)
                self._child = None
                return
            if token != self._root:
                raise AdmissionStateDefect("admission wrapper settlement is unknown")
            if self._child is not None:
                raise AdmissionStateDefect(
                    "root admission settled with an active child"
                )
            await self._delegate.settle(token, usage)
            self._root = None

    async def recover_orphans(self) -> tuple[RunId, ...]:
        async with self._lock:
            if self._root is not None or self._child is not None:
                raise AdmissionStateDefect(
                    "cannot recover admission while work is active"
                )
            return await self._delegate.recover_orphans()


def current_admission_limits(maximum_owner_inputs: int) -> RollingAdmissionLimits:
    if type(maximum_owner_inputs) is not int or maximum_owner_inputs <= 0:
        raise ValueError("maximum owner inputs must be a positive integer")
    root_input_overshoot = 32_768
    root_output_overshoot = 8_192
    maximum_gate_calls = MAIN_TOOL_LIMITS.max_calls
    serial_child_turns = (
        maximum_owner_inputs * RECALLER_KERNEL_LIMITS.max_provider_turns
        + maximum_gate_calls * WRITE_GATE_KERNEL_LIMITS.max_provider_turns
    )
    serial_child_input_tokens = maximum_owner_inputs * (
        RECALLER_KERNEL_LIMITS.max_provider_input_tokens + root_input_overshoot
    ) + maximum_gate_calls * (
        WRITE_GATE_KERNEL_LIMITS.max_provider_input_tokens + root_input_overshoot
    )
    serial_child_output_tokens = maximum_owner_inputs * (
        RECALLER_KERNEL_LIMITS.max_provider_output_tokens + root_output_overshoot
    ) + maximum_gate_calls * (
        WRITE_GATE_KERNEL_LIMITS.max_provider_output_tokens + root_output_overshoot
    )
    foreground_turns = MAIN_KERNEL_LIMITS.max_provider_turns + serial_child_turns
    foreground_input = (
        MAIN_KERNEL_LIMITS.max_provider_input_tokens
        + root_input_overshoot
        + serial_child_input_tokens
    )
    foreground_output = (
        MAIN_KERNEL_LIMITS.max_provider_output_tokens
        + root_output_overshoot
        + serial_child_output_tokens
    )
    # One envelope is held for the next worst-case foreground turn while one
    # envelope bounds already-settled usage in the rolling window. Without the
    # second envelope, a normal completed turn can make a conversational service
    # unable to reserve its next run until the entire window expires.
    rolling_foreground_envelopes = 2
    return RollingAdmissionLimits(
        max_turns=(
            rolling_foreground_envelopes * foreground_turns
            + REMEMBERER_KERNEL_LIMITS.max_provider_turns
        ),
        max_input_tokens=(
            rolling_foreground_envelopes * foreground_input
            + REMEMBERER_KERNEL_LIMITS.max_provider_input_tokens
            + root_input_overshoot
        ),
        max_output_tokens=(
            rolling_foreground_envelopes * foreground_output
            + REMEMBERER_KERNEL_LIMITS.max_provider_output_tokens
            + root_output_overshoot
        ),
        serial_child_turns=serial_child_turns,
        serial_child_input_tokens=serial_child_input_tokens,
        serial_child_output_tokens=serial_child_output_tokens,
    )


@dataclass(slots=True)
class _Spend:
    reservation: Reservation
    settlement: Settlement | None = None


class InProcessBudgetState:
    def __init__(
        self,
        limits: RunLimits,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits = limits
        self._monotonic = monotonic
        self._started_at = monotonic()
        self._spend: dict[InvocationPosition, _Spend] = {}

    @property
    def limits(self) -> RunLimits:
        return self._limits

    @property
    def remaining_elapsed_seconds(self) -> float:
        return self._limits.max_elapsed_seconds - (self._monotonic() - self._started_at)

    async def reserve(
        self, position: InvocationPosition, reservation: Reservation
    ) -> bool:
        existing = self._spend.get(position)
        if existing is not None:
            if existing.reservation != reservation:
                raise ValueError("position budget reservation changed")
            return True
        calls = sum(item.reservation.calls for item in self._spend.values())
        input_bytes = sum(item.reservation.input_bytes for item in self._spend.values())
        attempts = sum(
            item.reservation.max_attempts
            if item.settlement is None
            else item.settlement.actual_attempts
            for item in self._spend.values()
        )
        output_bytes = sum(
            item.reservation.max_output_bytes
            if item.settlement is None
            else item.settlement.actual_output_bytes
            for item in self._spend.values()
        )
        if (
            calls + reservation.calls > self._limits.max_calls
            or input_bytes + reservation.input_bytes > self._limits.max_input_bytes
            or attempts + reservation.max_attempts > self._limits.max_external_attempts
            or output_bytes + reservation.max_output_bytes
            > self._limits.max_output_bytes
            or sum(item.settlement is None for item in self._spend.values())
            >= self._limits.max_in_flight
        ):
            return False
        self._spend[position] = _Spend(reservation)
        return True

    async def settle(
        self, position: InvocationPosition, settlement: Settlement
    ) -> None:
        spend = self._spend.get(position)
        if spend is None:
            raise ValueError("position has no budget reservation")
        if spend.settlement is not None:
            if spend.settlement != settlement:
                raise ValueError("position budget settlement changed")
            return
        if (
            settlement.actual_attempts > spend.reservation.max_attempts
            or settlement.actual_output_bytes > spend.reservation.max_output_bytes
        ):
            raise ValueError("position budget settlement exceeds its reservation")
        spend.settlement = settlement


class ExactToolBudgetFactory:
    def create(self, plan: FrozenToolPlan) -> BudgetState:
        return InProcessBudgetState(plan.profile.run_limits)


def _required_root(
    turns: int,
    input_tokens: int,
    output_tokens: int,
    limits: RollingAdmissionLimits,
    *,
    include_serial_children: bool,
) -> tuple[int, int, int]:
    if any(
        type(value) is not int or value <= 0
        for value in (turns, input_tokens, output_tokens)
    ):
        raise ValueError("admission request maxima must be positive integers")
    return (
        turns + (limits.serial_child_turns if include_serial_children else 0),
        input_tokens
        + limits.root_input_token_overshoot
        + (limits.serial_child_input_tokens if include_serial_children else 0),
        output_tokens
        + limits.root_output_token_overshoot
        + (limits.serial_child_output_tokens if include_serial_children else 0),
    )


def _capacity_reset(
    journal: _Journal,
    now: datetime,
    limits: RollingAdmissionLimits,
    request: tuple[int, int, int],
) -> datetime | None:
    if (
        request[0] > limits.max_turns
        or request[1] > limits.max_input_tokens
        or request[2] > limits.max_output_tokens
    ):
        raise AdmissionStateDefect("one reservation exceeds rolling capacity")
    charged = [root for root in journal.reservations if root.expires_at > now]

    def fits(values: list[_Root]) -> bool:
        return (
            sum(_charge(root)[0] for root in values) + request[0] <= limits.max_turns
            and sum(_charge(root)[1] for root in values) + request[1]
            <= limits.max_input_tokens
            and sum(_charge(root)[2] for root in values) + request[2]
            <= limits.max_output_tokens
        )

    if fits(charged):
        return None
    for expiry in sorted({root.expires_at for root in charged}):
        charged = [root for root in charged if root.expires_at > expiry]
        if fits(charged):
            return expiry
    raise AdmissionStateDefect("rolling capacity cannot establish a reset instant")


def _charge(root: _Root) -> tuple[int, int, int]:
    if root.state in {"active", "interrupted"}:
        return (
            root.reserved_turns,
            root.reserved_input_tokens,
            root.reserved_output_tokens,
        )
    if root.state == "settled" and None not in (
        root.actual_turns,
        root.actual_input_tokens,
        root.actual_output_tokens,
    ):
        assert root.actual_turns is not None
        assert root.actual_input_tokens is not None
        assert root.actual_output_tokens is not None
        return root.actual_turns, root.actual_input_tokens, root.actual_output_tokens
    raise AdmissionStateDefect("admission reservation has invalid charge state")


def _prune(journal: _Journal, now: datetime) -> bool:
    retained = [
        root
        for root in journal.reservations
        if root.state == "active" or root.expires_at > now
    ]
    changed = len(retained) != len(journal.reservations)
    journal.reservations = retained
    return changed


def _reserve_child(
    journal: _Journal,
    request: AdmissionRequest,
    limits: RollingAdmissionLimits,
) -> AdmissionResult:
    assert request.parent is not None
    parent = request.parent
    root = next(
        (
            item
            for item in journal.reservations
            if item.root_epoch_id == parent.root_epoch_id
            and item.window_id == parent.window_id
        ),
        None,
    )
    if root is None or root.state != "active" or not root.owns_live_slot:
        raise AdmissionStateDefect("child admission has no active parent root")
    if root.thread_id is None:
        raise AdmissionStateDefect("background root has no serial-child allowance")
    if str(parent.run_id) != root.run_id or not parent.owns_live_slot:
        raise AdmissionStateDefect("child admission parent token is inconsistent")
    if any(
        candidate.run_id == str(request.run_id)
        or any(child.run_id == str(request.run_id) for child in candidate.children)
        for candidate in journal.reservations
        if candidate is not root
    ) or root.run_id == str(request.run_id):
        raise AdmissionStateDefect(
            "child admission run id already exists in the window"
        )
    existing = next(
        (child for child in root.children if child.run_id == str(request.run_id)), None
    )
    if existing is not None:
        if existing.state != "active":
            raise AdmissionStateDefect("child admission run id was already settled")
        return AdmissionGranted(
            AdmissionToken(
                request.run_id,
                root.window_id,
                root.root_epoch_id,
                existing.reserved_turns,
                existing.reserved_input_tokens,
                existing.reserved_output_tokens,
                False,
            )
        )
    child_input = request.maximum_input_tokens + limits.root_input_token_overshoot
    child_output = request.maximum_output_tokens + limits.root_output_token_overshoot
    used_turns = sum(child.reserved_turns for child in root.children)
    used_input = sum(child.reserved_input_tokens for child in root.children)
    used_output = sum(child.reserved_output_tokens for child in root.children)
    if (
        used_turns + request.maximum_turns > limits.serial_child_turns
        or used_input + child_input > limits.serial_child_input_tokens
        or used_output + child_output > limits.serial_child_output_tokens
    ):
        return AdmissionRejected("serial-child reservation exceeds its root allowance")
    root.children.append(
        _Child(
            reserved_input_tokens=child_input,
            reserved_output_tokens=child_output,
            reserved_turns=request.maximum_turns,
            run_id=str(request.run_id),
            state="active",
        )
    )
    return AdmissionGranted(
        AdmissionToken(
            request.run_id,
            root.window_id,
            root.root_epoch_id,
            request.maximum_turns,
            child_input,
            child_output,
            False,
        )
    )


def _settle_root(root: _Root, token: AdmissionToken, usage: AdmissionUsage) -> None:
    _validate_token(root, token)
    if any(child.state != "settled" for child in root.children):
        raise AdmissionStateDefect("root admission settled before its serial child")
    root_charge = _reported_charge(
        usage, root.root_reserved_input_tokens, root.root_reserved_output_tokens
    )
    child_charge = tuple(
        sum(_child_charge(child)[index] for child in root.children)
        for index in range(3)
    )
    total = tuple(root_charge[index] + child_charge[index] for index in range(3))
    if root.state == "settled":
        if _usage_tuple(root) != total:
            raise AdmissionStateDefect("root admission was settled differently")
        return
    if root.state != "active" or not root.owns_live_slot:
        raise AdmissionStateDefect("root admission is not active")
    if any(total[index] > _reserved_tuple(root)[index] for index in range(3)):
        raise AdmissionStateDefect("reported admission usage exceeded its reservation")
    root.actual_turns, root.actual_input_tokens, root.actual_output_tokens = total
    root.owns_live_slot = False
    root.state = "settled"


def _settle_child(root: _Root, token: AdmissionToken, usage: AdmissionUsage) -> None:
    child = next(
        (item for item in root.children if item.run_id == str(token.run_id)), None
    )
    if child is None:
        raise AdmissionStateDefect("child admission settlement is unknown")
    if (
        token.reserved_turns != child.reserved_turns
        or token.reserved_input_tokens != child.reserved_input_tokens
        or token.reserved_output_tokens != child.reserved_output_tokens
    ):
        raise AdmissionStateDefect("child admission token changed")
    charge = _reported_charge(
        usage, child.reserved_input_tokens, child.reserved_output_tokens
    )
    if child.state == "settled":
        if _child_charge(child) != charge:
            raise AdmissionStateDefect("child admission was settled differently")
        return
    if root.state != "active" or child.state != "active":
        raise AdmissionStateDefect("child admission is not active")
    if any(
        charge[index]
        > (
            child.reserved_turns,
            child.reserved_input_tokens,
            child.reserved_output_tokens,
        )[index]
        for index in range(3)
    ):
        raise AdmissionStateDefect("child admission usage exceeded its reservation")
    child.actual_turns, child.actual_input_tokens, child.actual_output_tokens = charge
    child.state = "settled"


def _reported_charge(
    usage: AdmissionUsage, reserved_input: int, reserved_output: int
) -> tuple[int, int, int]:
    return (
        usage.provider_turns,
        reserved_input
        if usage.usage.input_tokens is None
        else usage.usage.input_tokens,
        reserved_output
        if usage.usage.output_tokens is None
        else usage.usage.output_tokens,
    )


def _child_charge(child: _Child) -> tuple[int, int, int]:
    if child.state in {"active", "interrupted"}:
        return (
            child.reserved_turns,
            child.reserved_input_tokens,
            child.reserved_output_tokens,
        )
    if child.state == "settled" and None not in (
        child.actual_turns,
        child.actual_input_tokens,
        child.actual_output_tokens,
    ):
        assert child.actual_turns is not None
        assert child.actual_input_tokens is not None
        assert child.actual_output_tokens is not None
        return child.actual_turns, child.actual_input_tokens, child.actual_output_tokens
    raise AdmissionStateDefect("child admission has invalid charge state")


def _validate_token(root: _Root, token: AdmissionToken) -> None:
    if (
        str(token.run_id) != root.run_id
        or token.window_id != root.window_id
        or token.root_epoch_id != root.root_epoch_id
        or token.reserved_turns != root.reserved_turns
        or token.reserved_input_tokens != root.reserved_input_tokens
        or token.reserved_output_tokens != root.reserved_output_tokens
        or not token.owns_live_slot
    ):
        raise AdmissionStateDefect("root admission token changed")


def _reserved_tuple(root: _Root) -> tuple[int, int, int]:
    return root.reserved_turns, root.reserved_input_tokens, root.reserved_output_tokens


def _usage_tuple(root: _Root) -> tuple[int, int, int]:
    if None in (root.actual_turns, root.actual_input_tokens, root.actual_output_tokens):
        raise AdmissionStateDefect("settled root is missing usage")
    assert root.actual_turns is not None
    assert root.actual_input_tokens is not None
    assert root.actual_output_tokens is not None
    return root.actual_turns, root.actual_input_tokens, root.actual_output_tokens


def _validate_journal(journal: _Journal, limits: RollingAdmissionLimits) -> None:
    if any(
        root.created_at.tzinfo is None
        or root.created_at.utcoffset() is None
        or root.expires_at.tzinfo is None
        or root.expires_at.utcoffset() is None
        or root.expires_at <= root.created_at
        for root in journal.reservations
    ):
        raise ValueError("admission journal timestamps are invalid")
    if len({root.run_id for root in journal.reservations}) != len(journal.reservations):
        raise ValueError("admission journal contains duplicate root runs")
    if len({root.root_epoch_id for root in journal.reservations}) != len(
        journal.reservations
    ):
        raise ValueError("admission journal contains duplicate root epochs")
    if sum(root.owns_live_slot for root in journal.reservations) > 1:
        raise ValueError("admission journal contains multiple live root slots")
    run_ids: list[str] = []
    for root in journal.reservations:
        run_ids.append(root.run_id)
        if root.state not in {"active", "settled", "interrupted"}:
            raise ValueError("admission root state is invalid")
        if root.owns_live_slot != (root.state == "active"):
            raise ValueError("admission live-slot state is inconsistent")
        if root.expires_at - root.created_at != timedelta(
            seconds=limits.window_seconds
        ):
            raise ValueError("admission reservation window changed")
        if (root.thread_id is None) != (root.attempt_number is None):
            raise ValueError("admission thread and attempt state is inconsistent")
        child_turns = limits.serial_child_turns if root.thread_id is not None else 0
        child_input = (
            limits.serial_child_input_tokens if root.thread_id is not None else 0
        )
        child_output = (
            limits.serial_child_output_tokens if root.thread_id is not None else 0
        )
        if (
            root.reserved_turns != root.root_reserved_turns + child_turns
            or root.reserved_input_tokens
            != root.root_reserved_input_tokens + child_input
            or root.reserved_output_tokens
            != root.root_reserved_output_tokens + child_output
        ):
            raise ValueError("admission root and child allowances are inconsistent")
        if (
            root.reserved_turns > limits.max_turns
            or root.reserved_input_tokens > limits.max_input_tokens
            or root.reserved_output_tokens > limits.max_output_tokens
        ):
            raise ValueError("admission reservation exceeds configured capacity")
        actual = (
            root.actual_turns,
            root.actual_input_tokens,
            root.actual_output_tokens,
        )
        if root.state == "active" and any(value is not None for value in actual):
            raise ValueError("active admission root has actual usage")
        if root.state == "interrupted" and actual != _reserved_tuple(root):
            raise ValueError("interrupted admission root was refunded")
        if root.state == "settled" and (
            any(value is None for value in actual)
            or any(
                cast_value > reserved
                for cast_value, reserved in zip(
                    actual, _reserved_tuple(root), strict=True
                )
                if cast_value is not None
            )
        ):
            raise ValueError("settled admission root has invalid usage")
        if len({child.run_id for child in root.children}) != len(root.children):
            raise ValueError("admission journal contains duplicate child runs")
        for child in root.children:
            run_ids.append(child.run_id)
            if child.state not in {"active", "settled", "interrupted"}:
                raise ValueError("admission child state is invalid")
            child_actual = (
                child.actual_turns,
                child.actual_input_tokens,
                child.actual_output_tokens,
            )
            child_reserved = (
                child.reserved_turns,
                child.reserved_input_tokens,
                child.reserved_output_tokens,
            )
            if child.state in {"active", "interrupted"} and any(
                value is not None for value in child_actual
            ):
                raise ValueError("unsettled admission child has actual usage")
            if child.state == "settled" and (
                any(value is None for value in child_actual)
                or any(
                    cast_value > reserved
                    for cast_value, reserved in zip(
                        child_actual, child_reserved, strict=True
                    )
                    if cast_value is not None
                )
            ):
                raise ValueError("settled admission child has invalid usage")
        if root.state == "settled" and any(
            child.state != "settled" for child in root.children
        ):
            raise ValueError("settled admission root has unsettled children")
        if root.state == "interrupted" and any(
            child.state == "active" for child in root.children
        ):
            raise ValueError("interrupted admission root has an active child")
        if (
            sum(child.reserved_turns for child in root.children)
            > limits.serial_child_turns
            or sum(child.reserved_input_tokens for child in root.children)
            > limits.serial_child_input_tokens
            or sum(child.reserved_output_tokens for child in root.children)
            > limits.serial_child_output_tokens
        ):
            raise ValueError("admission children exceed their configured allowance")
        _charge(root)
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("admission journal contains duplicate run ids")


__all__ = [
    "ExactToolBudgetFactory",
    "InProcessBudgetState",
    "RollingAdmissionLimits",
    "RollingAdmissionPort",
    "RootTrackingAdmissionPort",
    "current_admission_limits",
]
