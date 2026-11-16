"""Civil recurrence arithmetic; stored nominal dates survive clock transitions."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_INSTANT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])\Z"
)


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class _CalendarRule(_Closed):
    at: Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]
    zone: str

    @field_validator("zone")
    @classmethod
    def bounded_zone(cls, value: str) -> str:
        if not value.strip() or "\0" in value or len(value.encode("utf-8")) > 128:
            raise ValueError("zone must be nonblank UTF-8 text within 128 bytes")
        return value


class DailyRule(_CalendarRule):
    type: Literal["daily"]


class WeeklyRule(_CalendarRule):
    type: Literal["weekly"]
    weekdays: Annotated[
        list[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]],
        Field(min_length=1, max_length=7),
    ]

    @field_validator("weekdays")
    @classmethod
    def ordered_days(cls, value: list[str]) -> list[str]:
        if value != [day for day in _WEEKDAYS if day in value]:
            raise ValueError("weekdays must be unique and in monday-to-sunday order")
        return value


class MonthlyRule(_CalendarRule):
    type: Literal["monthly"]
    day: Annotated[int, Field(strict=True, ge=1, le=31)]


class IntervalRule(_Closed):
    type: Literal["interval"]
    seconds: Annotated[int, Field(strict=True, ge=60)]


type CalendarRule = DailyRule | WeeklyRule | MonthlyRule
type RepeatRule = Annotated[
    DailyRule | WeeklyRule | MonthlyRule | IntervalRule, Field(discriminator="type")
]


class Wake(_Closed):
    at: AwareDatetime
    repeat: RepeatRule | None

    @field_validator("at", mode="before")
    @classmethod
    def exact_instant(cls, value: object) -> object:
        if not isinstance(value, datetime) and (
            not isinstance(value, str) or _INSTANT.fullmatch(value) is None
        ):
            raise ValueError("at must be RFC3339 with at most six fractional digits")
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("z", "+00:00"))
        return value

    @field_validator("at")
    @classmethod
    def utc_instant(cls, value: datetime) -> datetime:
        return _utc(value)


@dataclass(frozen=True, slots=True)
class Occurrence:
    at: datetime
    local_date: date | None


@dataclass(frozen=True, slots=True)
class DueWindow:
    scheduled_for: datetime
    scheduled_local_date: date | None
    next_wake_at: datetime | None
    next_local_date: date | None
    skipped_count: int


class ScheduleError(ValueError):
    def __init__(self, code: Literal["invalid_zone", "out_of_range"]) -> None:
        self.code = code
        super().__init__(code)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("an aware instant is required")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError):
        raise ScheduleError("out_of_range") from None


def _zone(rule: CalendarRule) -> ZoneInfo:
    try:
        return ZoneInfo(rule.zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ScheduleError("invalid_zone") from None


def resolve_occurrence(rule: CalendarRule, local_date: date) -> datetime:
    """Resolve the nominal date under installed zone rules, never move its cursor."""
    return resolve_civil(local_date, time.fromisoformat(rule.at), _zone(rule))


def resolve_civil(local_date: date, at: time, zone: ZoneInfo) -> datetime:
    """Choose the earlier fold and shift gaps forward by the offset change."""
    local = datetime.combine(local_date, at)
    try:
        candidates = [
            local.replace(tzinfo=zone, fold=fold).astimezone(UTC) for fold in (0, 1)
        ]
        returned = [item.astimezone(zone).replace(tzinfo=None) for item in candidates]
        valid = [
            instant
            for instant, roundtrip in zip(candidates, returned, strict=True)
            if roundtrip == local
        ]
        if valid:
            return min(valid)
        # A gap's forward roundtrip advances by its actual offset change.
        return min(
            instant
            for instant, roundtrip in zip(candidates, returned, strict=True)
            if roundtrip > local
        )
    except (OverflowError, ValueError):
        raise ScheduleError("out_of_range") from None


def _index(rule: CalendarRule, day: date) -> int:
    """Index the last nominal occurrence on or before this date."""
    if isinstance(rule, DailyRule):
        return day.toordinal() - 1
    if isinstance(rule, WeeklyRule):
        weeks, weekday = divmod(day.toordinal() - 1, 7)
        return (
            weeks * len(rule.weekdays)
            + sum(_WEEKDAYS.index(item) <= weekday for item in rule.weekdays)
            - 1
        )
    index = (day.year - 1) * 12 + day.month - 1
    nominal_day = min(rule.day, calendar.monthrange(day.year, day.month)[1])
    return index - (nominal_day > day.day)


def _date(rule: CalendarRule, index: int) -> date:
    try:
        if index < 0:
            raise ValueError("negative recurrence index")
        if isinstance(rule, DailyRule):
            return date.fromordinal(index + 1)
        if isinstance(rule, WeeklyRule):
            week, day = divmod(index, len(rule.weekdays))
            return date.fromordinal(week * 7 + _WEEKDAYS.index(rule.weekdays[day]) + 1)
        year, month = divmod(index, 12)
        year += 1
        month += 1
        return date(year, month, min(rule.day, calendar.monthrange(year, month)[1]))
    except (OverflowError, ValueError):
        raise ScheduleError("out_of_range") from None


def first_occurrence(rule: RepeatRule, at: datetime) -> Occurrence:
    at = _utc(at)
    if isinstance(rule, IntervalRule):
        return Occurrence(at, None)
    try:
        local_date = at.astimezone(_zone(rule)).date()
    except (OverflowError, ValueError) as exc:
        if isinstance(exc, ScheduleError):
            raise
        raise ScheduleError("out_of_range") from None
    index = _index(rule, local_date)
    if index < 0 or _date(rule, index) < local_date:
        index += 1
    nominal = _date(rule, index)
    instant = resolve_occurrence(rule, nominal)
    if instant < at:
        nominal = _date(rule, index + 1)
        instant = resolve_occurrence(rule, nominal)
    return Occurrence(instant, nominal)


def due_window(
    rule: RepeatRule | None,
    wake_at: datetime,
    wake_local_date: date | None,
    as_of: datetime,
) -> DueWindow | None:
    wake_at, as_of = _utc(wake_at), _utc(as_of)
    if wake_at > as_of:
        return None
    if rule is None:
        return DueWindow(wake_at, None, None, None, 0)
    if isinstance(rule, IntervalRule):
        elapsed = as_of - wake_at
        elapsed_us = (elapsed.days * 86_400 + elapsed.seconds) * 1_000_000
        elapsed_us += elapsed.microseconds
        skipped = elapsed_us // (rule.seconds * 1_000_000)
        try:
            latest = wake_at + timedelta(seconds=skipped * rule.seconds)
            following = wake_at + timedelta(seconds=(skipped + 1) * rule.seconds)
        except OverflowError:
            raise ScheduleError("out_of_range") from None
        return DueWindow(latest, None, following, None, skipped)
    if wake_local_date is None:
        raise ValueError("a calendar recurrence requires its nominal date")
    try:
        local_date = as_of.astimezone(_zone(rule)).date()
    except (OverflowError, ValueError) as exc:
        if isinstance(exc, ScheduleError):
            raise
        raise ScheduleError("out_of_range") from None
    start = _index(rule, wake_local_date)
    index = max(start, _index(rule, local_date))
    nominal = _date(rule, index)
    latest = resolve_occurrence(rule, nominal)
    # Rank arithmetic skips the elapsed span; only clock-boundary neighbors remain.
    while latest > as_of and index > start:
        index -= 1
        nominal = _date(rule, index)
        latest = resolve_occurrence(rule, nominal)
    next_nominal = _date(rule, index + 1)
    following = resolve_occurrence(rule, next_nominal)
    while following <= as_of:
        index += 1
        nominal, latest = next_nominal, following
        next_nominal = _date(rule, index + 1)
        following = resolve_occurrence(rule, next_nominal)
    return DueWindow(latest, nominal, following, next_nominal, index - start)
