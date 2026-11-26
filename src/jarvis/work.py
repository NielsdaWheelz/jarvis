"""Current work records, atomic local receipts, and scheduled input publication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from llm_agent_kernel import input_batch
from llm_tools import (
    DeclaredToolFailure,
    PromptSections,
    ToolId,
    ToolResult,
    canonical_json_bytes,
    render_prompt,
)
from pydantic import BaseModel, TypeAdapter
from sqlalchemy import RowMapping, case, delete, func, insert, select, update

from jarvis.actions import (
    ActionPersistenceDefect,
    action_replay_result,
    complete_local_action,
    require_locked_action,
)
from jarvis.db import message, work
from jarvis.input_framing import host_input
from jarvis.messages import append_waking_input
from jarvis.ownership import Database, lock_conversation
from jarvis.work_schedule import (
    IntervalRule,
    Occurrence,
    RepeatRule,
    ScheduleError,
    Wake,
    due_window,
    first_occurrence,
    resolve_occurrence,
)
from jarvis.work_tools import (
    ACTIVE_WORK_STATES,
    WORK_MUTATION_IDS,
    WORK_STATES,
    NotFound,
    WorkCreateInput,
    WorkDeleteInput,
    WorkGetSuccess,
    WorkListSuccess,
    WorkMutationSuccess,
    WorkRecord,
    WorkState,
    WorkSummary,
    WorkUpdateInput,
    validate_work_result,
)
from jarvis.workspace_checks import (
    WorkspaceCheck,
    WorkspaceSelectors,
    observed_calendar_ids,
)

_REPEAT = TypeAdapter[RepeatRule](RepeatRule)
_STATE_RANK = {state: rank for rank, state in enumerate(WORK_STATES)}
_STATE_ORDER = case(_STATE_RANK, value=work.c.state)
_DATE_ORDER = work.c.due_date.asc().nulls_last()
_TIE_BREAK = (work.c.updated_at.desc(), work.c.id)


def _record(row: RowMapping | dict[str, object]) -> WorkRecord:
    return WorkRecord.model_validate(
        {
            key: str(value) if isinstance(value := row[key], UUID) else value
            for key in WorkRecord.model_fields
        }
    )


class WorkStore:
    def __init__(
        self,
        database: Database,
        conversation_id: str,
        *,
        owner_timezone: str = "UTC",
        workspace_grant_id: Callable[[], UUID | None] | None = None,
    ) -> None:
        self._database = database
        self._owner_zone = ZoneInfo(owner_timezone)
        self._workspace_grant_id = workspace_grant_id
        self._conversation_id = conversation_id
        self.notify_changed: Callable[[], None] = lambda: None

    async def get(self, work_id: UUID) -> WorkGetSuccess:
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            as_of = datetime.now(UTC)
            row = (
                (await connection.execute(select(work).where(work.c.id == work_id)))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DeclaredToolFailure(NotFound(), actual_attempts=0)
            result = WorkGetSuccess(record=_record(row), as_of=as_of)
            validate_work_result(
                ToolId("work.get"),
                {"type": "Success", "value": result.model_dump(mode="json")},
            )
            return result

    async def list(
        self, states: list[WorkState], limit: int, offset: int
    ) -> WorkListSuccess:
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            as_of = datetime.now(UTC)
            total = await connection.scalar(
                select(func.count()).select_from(work).where(work.c.state.in_(states))
            )
            rows = (
                (
                    await connection.execute(
                        select(work)
                        .where(work.c.state.in_(states))
                        .order_by(_STATE_ORDER, _DATE_ORDER, *_TIE_BREAK)
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .mappings()
                .all()
            )
            result = WorkListSuccess(
                items=[
                    WorkSummary.model_validate(
                        {
                            key: str(value)
                            if isinstance(value := row[key], UUID)
                            else value
                            for key in WorkSummary.model_fields
                        }
                    )
                    for row in rows
                ],
                total=total or 0,
                as_of=as_of,
            )
            validate_work_result(
                ToolId("work.list"),
                {"type": "Success", "value": result.model_dump(mode="json")},
            )
            return result

    async def web_list(self) -> dict[str, object]:
        """Read the complete active list under the writer lock."""
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            as_of = datetime.now(UTC)
            today = as_of.astimezone(self._owner_zone).date()
            active = work.c.state.in_(ACTIVE_WORK_STATES)
            due_order = (_DATE_ORDER, _STATE_ORDER, *_TIE_BREAK)
            next_id = await connection.scalar(
                select(work.c.id)
                .where(active, work.c.due_date > today)
                .order_by(*due_order)
                .limit(1)
            )
            section = case(
                (work.c.due_date <= today, "due"),
                (work.c.id == next_id, "next_deadline"),
                else_=work.c.state,
            )
            rows = await connection.execute(
                select(
                    work.c.id,
                    work.c.title,
                    work.c.state,
                    work.c.due_date,
                    section.label("section"),
                )
                .where(active)
                .order_by(
                    case(
                        {"due": -2, "next_deadline": -1, **_STATE_RANK}, value=section
                    ),
                    *due_order,
                )
            )
            items = [dict(row) for row in rows.mappings()]
        return {
            "as_of": as_of,
            "timezone": self._owner_zone.key,
            "today": today,
            "offset": 0,
            "total": len(items),
            "backlog_remaining": sum(item["section"] == "backlog" for item in items),
            "items": items,
        }

    async def recover_mutation(self, action_id: UUID) -> ToolResult | None:
        """Wait out entered SQL before using absence as local replay proof."""
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            stored = await require_locked_action(connection, action_id)
            scope = await connection.scalar(
                select(message.c.source_conversation_id).where(
                    message.c.id == stored.origin_message_id
                )
            )
            if (
                stored.tool_name not in WORK_MUTATION_IDS
                or scope != self._conversation_id
            ):
                raise ActionPersistenceDefect(
                    "work recovery requires a matching work mutation"
                )
            return action_replay_result(stored)

    async def mutate(
        self, action_id: UUID, tool_id: ToolId, arguments: BaseModel
    ) -> ToolResult:
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            stored = await require_locked_action(connection, action_id)
            replay = action_replay_result(stored)
            if replay is not None:
                return replay
            if not isinstance(
                arguments, WorkCreateInput | WorkUpdateInput | WorkDeleteInput
            ):
                raise ActionPersistenceDefect("work mutation has foreign input")
            origin = (
                await connection.execute(
                    select(
                        message.c.source_conversation_id,
                        message.c.role,
                        message.c.source,
                        message.c.control_kind,
                        message.c.home,
                    ).where(message.c.id == stored.origin_message_id)
                )
            ).one()
            if (
                tool_id not in WORK_MUTATION_IDS
                or stored.tool_name != tool_id
                or stored.payload != arguments.model_dump(mode="json")
                or stored.status != "executing"
                or stored.attempts < 1
                or origin.source_conversation_id != self._conversation_id
            ):
                raise ActionPersistenceDefect(
                    "work mutation differs from its entered action"
                )
            now = datetime.now(UTC)
            identifier = (
                action_id
                if isinstance(arguments, WorkCreateInput)
                else UUID(str(arguments.id))
            )
            row = (
                (
                    await connection.execute(
                        select(work).where(work.c.id == identifier).with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            error: dict[str, object] | None = None
            values: dict[str, object] = {}
            assigning: Wake | None = None
            has_wake = False
            setting_check = False
            selectors: WorkspaceSelectors | None = None
            editing_condition = False
            old_check = (
                WorkspaceCheck.model_validate(row["workspace_check"])
                if row is not None and row["workspace_check"] is not None
                else None
            )
            owner_authorized = (
                origin.role == "owner"
                and origin.source != "initialize_state"
                and origin.control_kind is None
                and "workspace_refresh" not in (origin.home or {})
            )
            if isinstance(arguments, WorkCreateInput):
                if row is not None:
                    raise ActionPersistenceDefect(
                        "creating work already exists without a receipt"
                    )
                values = arguments.model_dump(
                    mode="python", exclude={"wake", "workspace_check"}
                )
                values["workspace_check"] = None
                selectors = arguments.workspace_check
                setting_check = selectors is not None
                values.update(id=identifier, created_at=now, updated_at=now)
                assigning, has_wake = arguments.wake, True
            elif row is None:
                error = {"type": "NotFound"}
            elif isinstance(arguments, WorkUpdateInput):
                values = dict(row)
                for change in arguments.changes:
                    if change.field == "wake":
                        assigning, has_wake = change.value, True
                    elif change.field == "workspace_check":
                        setting_check, selectors = True, change.value
                    else:
                        if change.field == "content":
                            editing_condition = True
                        values[change.field] = change.value
                values["updated_at"] = now
            elif old_check is not None and not owner_authorized:
                error = {"type": "InvalidWorkspaceCheck", "code": "owner_required"}
            if error is None and values:
                if has_wake:
                    values.update(
                        wake_id=None, wake_at=None, repeat=None, wake_local_date=None
                    )
                    if assigning is not None:
                        if values["state"] in {"done", "cancelled"}:
                            error = {"type": "InvalidSchedule", "code": "inactive"}
                        elif assigning.at.astimezone(
                            UTC
                        ) <= stored.created_at.astimezone(UTC):
                            error = {
                                "type": "InvalidSchedule",
                                "code": "not_future_at_admission",
                            }
                        else:
                            try:
                                occurrence = (
                                    Occurrence(assigning.at, None)
                                    if assigning.repeat is None
                                    else first_occurrence(
                                        assigning.repeat, assigning.at
                                    )
                                )
                                if assigning.repeat is not None:
                                    due_window(
                                        assigning.repeat,
                                        occurrence.at,
                                        occurrence.local_date,
                                        occurrence.at,
                                    )
                                values.update(
                                    wake_id=action_id,
                                    wake_at=occurrence.at,
                                    repeat=None
                                    if assigning.repeat is None
                                    else assigning.repeat.model_dump(mode="json"),
                                    wake_local_date=occurrence.local_date,
                                )
                            except ScheduleError as exc:
                                error = {"type": "InvalidSchedule", "code": exc.code}
                if values["state"] in {"done", "cancelled"}:
                    values.update(
                        wake_id=None, wake_at=None, repeat=None, wake_local_date=None
                    )
                if (
                    old_check is not None
                    and not setting_check
                    and (
                        values["state"] in {"done", "cancelled"}
                        or (has_wake and assigning is None)
                    )
                ):
                    setting_check = True
                changing_check = setting_check or (
                    old_check is not None and (editing_condition or has_wake)
                )
                if error is None and changing_check:
                    if not owner_authorized:
                        error = {
                            "type": "InvalidWorkspaceCheck",
                            "code": "owner_required",
                        }
                    elif setting_check and selectors is None:
                        values["workspace_check"] = None
                    elif values.get("repeat") is None:
                        error = {
                            "type": "InvalidWorkspaceCheck",
                            "code": "recurring_wake_required",
                        }
                    elif not str(values["content"]).strip():
                        error = {
                            "type": "InvalidWorkspaceCheck",
                            "code": "condition_required",
                        }
                    else:
                        grant = (
                            self._workspace_grant_id()
                            if self._workspace_grant_id
                            else None
                        )
                        selected = selectors or old_check
                        contract = stored.current_execution_contract
                        admitted = contract.workspace_grant_id
                        if (
                            grant is None
                            or grant != admitted
                            or (
                                not setting_check
                                and old_check is not None
                                and old_check.grant_id != str(grant)
                            )
                        ):
                            error = {
                                "type": "InvalidWorkspaceCheck",
                                "code": "grant_unavailable",
                            }
                        elif selected is not None and selected.expired(
                            now, self._owner_zone
                        ):
                            error = {"type": "InvalidWorkspaceCheck", "code": "expired"}
                        elif (
                            selectors is not None
                            and selectors.calendar is not None
                            and not await observed_calendar_ids(
                                connection,
                                selectors.calendar,
                                attempt_id=contract.claim_id,
                                grant_id=grant,
                                input_ids=contract.input_message_ids,
                                before_ordinal=contract.model_step_ordinal,
                                admitted_at=stored.created_at,
                            )
                        ):
                            error = {
                                "type": "InvalidWorkspaceCheck",
                                "code": "calendar_not_observed",
                            }
                        elif selectors is not None:
                            values["workspace_check"] = {
                                **selectors.model_dump(mode="json"),
                                "grant_id": str(grant),
                            }
                    if values.get("wake_id") is not None:
                        values["wake_id"] = action_id
                if values["state"] in {"done", "cancelled"}:
                    values["workspace_check"] = None
                if values["state"] == "next_up":
                    count = await connection.scalar(
                        select(func.count())
                        .select_from(work)
                        .where(work.c.state == "next_up", work.c.id != identifier)
                    )
                    if (count or 0) >= 3:
                        error = {"type": "NextUpFull"}
            operation = (
                "created"
                if isinstance(arguments, WorkCreateInput)
                else "updated"
                if isinstance(arguments, WorkUpdateInput)
                else "deleted"
            )
            if error is not None:
                result: ToolResult = {"type": "Failure", "error": error}
            else:
                receipt = WorkMutationSuccess.model_validate(
                    {
                        "id": str(identifier),
                        "operation": operation,
                        "wake_id": str(values["wake_id"])
                        if values.get("wake_id") is not None
                        else None,
                        "wake_at": values.get("wake_at"),
                        "repeat": values.get("repeat"),
                        "recorded_at": now,
                    }
                )
                result = {"type": "Success", "value": receipt.model_dump(mode="json")}
            validate_work_result(tool_id, result)
            if error is None and values:
                _record(values)
            if error is None:
                if operation == "created":
                    await connection.execute(insert(work).values(**values))
                elif operation == "updated":
                    await connection.execute(
                        update(work).where(work.c.id == identifier).values(**values)
                    )
                else:
                    await connection.execute(
                        delete(work).where(work.c.id == identifier)
                    )
            await complete_local_action(connection, stored, result, now)
        if result["type"] == "Success":
            self.notify_changed()
        return result

    async def next_due_at(self) -> datetime | None:
        async with self._database.begin() as connection:
            return await connection.scalar(select(func.min(work.c.wake_at)))

    async def recompute_calendar_wakes(self) -> None:
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            rows = (
                (
                    await connection.execute(
                        select(work)
                        .where(work.c.wake_local_date.is_not(None))
                        .order_by(work.c.id)
                        .with_for_update()
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                rule = _REPEAT.validate_python(row["repeat"])
                if isinstance(rule, IntervalRule):
                    raise ValueError("interval work has a civil cursor")
                resolved = resolve_occurrence(rule, row["wake_local_date"])
                await connection.execute(
                    update(work).where(work.c.id == row["id"]).values(wake_at=resolved)
                )

    async def publish_due(self, as_of: datetime) -> UUID | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("work publication clock must be timezone-aware")
        as_of = as_of.astimezone(UTC)
        async with self._database.begin() as connection:
            await lock_conversation(connection, self._conversation_id)
            control = await connection.scalar(
                select(message.c.control_kind)
                .where(
                    message.c.source_conversation_id == self._conversation_id,
                    message.c.control_kind.is_not(None),
                )
                .order_by(message.c.control_sequence.desc())
                .limit(1)
            )
            if control == "pause":
                return None
            row = (
                (
                    await connection.execute(
                        select(work)
                        .where(work.c.wake_at <= as_of)
                        .order_by(work.c.wake_at, work.c.id)
                        .limit(1)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            record = _record(row)
            if record.workspace_check is not None and record.workspace_check.expired(
                as_of, self._owner_zone
            ):
                await connection.execute(
                    update(work)
                    .where(work.c.id == row["id"])
                    .values(
                        wake_id=None,
                        wake_at=None,
                        repeat=None,
                        wake_local_date=None,
                        workspace_check=None,
                    )
                )
                return None
            if record.state in {"done", "cancelled"} or row["wake_id"] is None:
                raise ValueError("inactive work has a persisted schedule")
            rule = (
                None
                if row["repeat"] is None
                else _REPEAT.validate_python(row["repeat"])
            )
            window = due_window(rule, row["wake_at"], row["wake_local_date"], as_of)
            if window is None:
                raise ValueError("due work has no due occurrence")
            identity = (
                "date:" + window.scheduled_local_date.isoformat()
                if window.scheduled_local_date is not None
                else "instant:"
                + window.scheduled_for.astimezone(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            body = {
                "record": record.model_dump(mode="json"),
                "scheduled_for": window.scheduled_for.isoformat(),
                "scheduled_local_date": None
                if window.scheduled_local_date is None
                else window.scheduled_local_date.isoformat(),
                "skipped_count": window.skipped_count,
                "next_wake_at": None
                if window.next_wake_at is None
                else window.next_wake_at.isoformat(),
            }
            appended = await append_waking_input(
                connection,
                role="host",
                text=canonical_json_bytes(body).decode(),
                source="work_wake",
                source_conversation_id=self._conversation_id,
                source_message_id=str(row["wake_id"]) + ":" + identity,
                created_at=window.scheduled_for,
                parent_request_id=None,
            )
            frame = PromptSections(
                (
                    input_batch(
                        (host_input(appended.message),),
                        as_of,
                        render_source_timestamps=True,
                        render_batch_as_of=True,
                    ),
                )
            )
            if len(render_prompt(frame).encode("utf-8")) > 65536:
                raise ValueError("work wake exceeds its complete input frame bound")
            await connection.execute(
                update(work)
                .where(work.c.id == row["id"])
                .values(
                    wake_id=row["wake_id"] if window.next_wake_at is not None else None,
                    wake_at=window.next_wake_at,
                    repeat=row["repeat"] if window.next_wake_at is not None else None,
                    wake_local_date=window.next_local_date,
                )
            )
            return appended.message.id if appended.inserted else None
