"""Observe the enrolled Gmail pending label and acknowledge committed events."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from pydantic import ValidationError

from jarvis.event_tools import POLL_SECONDS
from jarvis.events import Cursor, EventStore, Failure, Observation
from jarvis.gmail_arrivals import (
    GmailArrivalSource,
    eligible_labels,
    identity,
    items,
    message_labels,
    observation,
    pending_label,
)
from jarvis.workspace_mcp import WorkspaceError, WorkspaceRequest, workspace_target_key

_UNREADABLE_ITEM = {
    "partial",
    "denied",
    "policy_block",
    "withheld",
    "not_found",
    "screened",
}


class _NotAdmitted(WorkspaceError):
    """The local poll lost authority before transmission or commit."""

    def __init__(self) -> None:
        super().__init__("not_admitted")


class EventPoller:
    def __init__(
        self,
        *,
        store: EventStore,
        source: GmailArrivalSource | None,
        admitted: Callable[[], Awaitable[bool]],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._source = source
        self._store.account = source.account if source is not None else None
        self._admitted = admitted
        self._now = now
        self._changed = asyncio.Event()
        self._stop: asyncio.Event | None = None
        self._episode: UUID | None = None
        self._partial: list[WorkspaceError] = []

    def notify_changed(self) -> None:
        self._changed.set()

    async def run(self, stop: asyncio.Event) -> None:
        self._stop = stop
        while not stop.is_set():
            self._changed.clear()
            wait_seconds = float(POLL_SECONDS)
            if self._source is not None and await self._admitted():
                cursor = await self._store.poll_cursor()
                if cursor is not None and cursor.next_poll_at is not None:
                    delay = (cursor.next_poll_at - self._now()).total_seconds()
                    if delay <= 0:
                        await self.poll(cursor)
                        continue
                    wait_seconds = min(wait_seconds, delay)
            changed = asyncio.create_task(self._changed.wait())
            stopped = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait(
                    (changed, stopped),
                    timeout=wait_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                changed.cancel()
                stopped.cancel()
                await asyncio.gather(changed, stopped, return_exceptions=True)

    async def _admit(self, cursor: Cursor) -> None:
        if (
            (self._stop is not None and self._stop.is_set())
            or not await self._admitted()
            or not await self._store.admission(cursor)
        ):
            raise _NotAdmitted

    async def _call(
        self,
        cursor: Cursor,
        tool: str,
        args: dict[str, object],
        *,
        before_send: Callable[[], Awaitable[None]] | None = None,
    ) -> dict[str, object]:
        assert self._source is not None and self._episode is not None
        await self._admit(cursor)
        key = workspace_target_key(self._source.grant_id, args)
        attended = await self._store.attended(cursor, self._episode, tool, key)
        try:
            result = await self._source.call(
                tool,
                args,
                before_send=before_send or (lambda: self._admit(cursor)),
                episode=self._episode,
                attended=attended,
            )
        except WorkspaceError as error:
            if (
                error.kind == "consent_required"
                and tool in {"get_thread", "get_message"}
                and await self._store.previously_denied(self._episode, tool, key)
            ):
                denied = WorkspaceError("denied", known_no_effect=True)
                denied.request = error.request
                raise denied from None
            raise
        if before_send is None:
            await self._admit(cursor)
        return result

    async def _commit(
        self,
        cursor: Cursor,
        progress: dict[str, object],
        observations: tuple[Observation, ...] = (),
        *,
        complete: bool = False,
        failure: Failure | None = None,
    ) -> Cursor:
        await self._admit(cursor)
        if not await self._store.commit_progress(
            cursor,
            progress,
            observations,
            complete=complete,
            failure=failure,
            partial=self._partial,
            episode=self._episode,
        ):
            raise _NotAdmitted
        return replace(cursor, progress=progress)

    async def _acknowledge(
        self, cursor: Cursor, label: str, *, recovering: bool
    ) -> Cursor | None:
        assert self._source is not None
        pending = cast(dict[str, object], cursor.progress["ack"])
        message_id = identity(pending, "message_id")
        args: dict[str, object] = {"messageId": message_id, "labelIds": [label]}

        def unknown_ack(*, label_present: bool = False) -> Failure:
            assert self._source is not None
            issue = WorkspaceError(
                "label_still_present" if label_present else "uncertain"
            )
            issue.request = WorkspaceRequest(
                "gmail",
                "unlabel_message",
                self._source.grant_id,
                workspace_target_key(self._source.grant_id, args),
                self._episode,
            )
            return Failure("AckUncertain", blocked=True, issue=issue)

        if recovering:
            try:
                fresh = await self._call(
                    cursor,
                    "get_message",
                    {
                        "messageId": message_id,
                        "messageFormat": "METADATA_ONLY",
                    },
                )
            except WorkspaceError as exc:
                if pending["phase"] == "entered" and exc.kind in _UNREADABLE_ITEM:
                    self._partial.append(exc)
                    await self._commit(
                        cursor,
                        cursor.progress,
                        failure=unknown_ack(),
                    )
                    return None
                if pending["phase"] == "ready" and exc.kind in _UNREADABLE_ITEM:
                    # No effect was entered. Preserve the Gmail tag; inspect other
                    # reachable messages on a subsequent scan.
                    return await self._commit(cursor, {**cursor.progress, "ack": None})
                raise
            if identity(fresh) != message_id:
                raise ValueError("returned a different message during ack recovery")
            # An omitted array is no positive tag evidence. For an entered
            # write it is also no positive evidence of tag removal.
            labels = message_labels(fresh) if "labelIds" in fresh else None
            if labels is not None and label not in labels:
                return await self._commit(cursor, {**cursor.progress, "ack": None})
            if pending["phase"] == "entered":
                await self._commit(
                    cursor,
                    cursor.progress,
                    failure=unknown_ack(
                        label_present=labels is not None and label in labels
                    ),
                )
                return None
            if labels is None or not eligible_labels(labels):
                return await self._commit(cursor, {**cursor.progress, "ack": None})

        async def enter() -> None:
            nonlocal cursor
            cursor = await self._commit(
                cursor,
                {
                    **cursor.progress,
                    "ack": {"message_id": message_id, "phase": "entered"},
                },
            )

        try:
            reply = await self._call(
                cursor,
                "unlabel_message",
                args,
                before_send=enter,
            )
        except _NotAdmitted:
            raise
        except WorkspaceError as exc:
            # A quota refusal before transmission leaves the ready marker.
            # After entry, even an ambiguous reply never dispatches again.
            progress = cursor.progress
            if exc.known_no_effect:
                progress = {
                    **progress,
                    "ack": {"message_id": message_id, "phase": "ready"},
                }
            failure = (
                unknown_ack()
                if exc.kind == "uncertain" and not exc.known_no_effect
                else _failure(exc)
            )
            await self._commit(cursor, progress, failure=failure)
            return None
        if reply != {}:
            await self._commit(
                cursor,
                cursor.progress,
                failure=Failure("InvalidResponse", blocked=True),
            )
            return
        return await self._commit(
            cursor, {**cursor.progress, "ack": None, "residual": None}
        )

    async def _drain(self, cursor: Cursor, name: str, count: int, label: str) -> None:
        token: str | None = None
        seen: set[str] = set()
        while True:
            args: dict[str, object] = {
                "query": f'label:"{name}" -in:spam -in:trash',
                "pageSize": 50,
                "view": "THREAD_VIEW_IDS_ONLY",
            }
            if token is not None:
                args["pageToken"] = token
            page = await self._call(cursor, "search_threads", args)
            changed = False
            for row in items(page, "threads"):
                thread = identity(row)
                try:
                    details = await self._call(
                        cursor,
                        "get_thread",
                        {
                            "threadId": thread,
                            "messageFormat": "METADATA_ONLY",
                        },
                    )
                except WorkspaceError as exc:
                    if exc.kind in _UNREADABLE_ITEM:
                        self._partial.append(exc)
                        continue
                    raise
                if identity(details) != thread:
                    raise ValueError("returned a different thread")
                for candidate in items(details, "messages"):
                    if "labelIds" not in candidate:
                        continue
                    labels = message_labels(candidate)
                    if label not in labels or not eligible_labels(labels):
                        continue
                    message_id = identity(candidate)
                    try:
                        fresh = await self._call(
                            cursor,
                            "get_message",
                            {
                                "messageId": message_id,
                                # The minimal view has subject/sender/date. Only
                                # these screened fields may reach the arrival event.
                                "messageFormat": "MINIMAL",
                            },
                        )
                    except WorkspaceError as exc:
                        if exc.kind in _UNREADABLE_ITEM:
                            self._partial.append(exc)
                            continue
                        raise
                    if identity(fresh) != message_id:
                        raise ValueError("returned a different message")
                    fact = observation(
                        fresh, cursor.account_id, thread, label, self._now()
                    )
                    if fact is None or await self._store.has_sent_echo(message_id):
                        continue
                    ready = await self._commit(
                        cursor,
                        {
                            **cursor.progress,
                            "residual": None,
                            "ack": {"message_id": message_id, "phase": "ready"},
                        },
                        (fact,),
                    )
                    cleared = await self._acknowledge(ready, label, recovering=False)
                    if cleared is None:
                        return
                    cursor = cleared
                    changed = True
            if changed:
                # Provider tokens refer to the old result set. Start at its head again.
                return
            if "nextPageToken" not in page:
                break
            raw_token = page["nextPageToken"]
            if (
                not isinstance(raw_token, str)
                or not 0 < len(raw_token.encode()) <= 8192
            ):
                raise ValueError("invalid gmail search continuation")
            token = raw_token
            if token in seen:
                await self._commit(
                    cursor, cursor.progress, failure=Failure("InvalidResponse")
                )
                return
            seen.add(token)
        await self._commit(
            cursor,
            {
                **cursor.progress,
                "residual": {
                    "total": count,
                    "recheck_at": (self._now() + timedelta(minutes=30)).isoformat(),
                },
            },
            complete=True,
        )

    async def poll(self, cursor: Cursor) -> None:
        """Drain the first processable page, then re-read the remaining membership."""
        self._episode = cursor.error.episode_id if cursor.error is not None else uuid4()
        self._partial.clear()
        try:
            source = self._source
            if (
                source is None
                or source.account != cursor.account_id
                or str(source.grant_id) != cursor.progress.get("grant_id")
                or source.label_id != cursor.progress.get("label_id")
            ):
                await self._commit(
                    cursor,
                    cursor.progress,
                    failure=Failure("AuthUnavailable", blocked=True),
                )
                return
            if cursor.progress.get("ack") is not None:
                await self._acknowledge(cursor, source.label_id, recovering=True)
                return
            response = await self._call(cursor, "list_labels", {})
            try:
                name, count = pending_label(response, source.label_id)
            except ValueError:
                await self._commit(
                    cursor,
                    cursor.progress,
                    failure=Failure("LabelUnavailable", blocked=True),
                )
                return
            if count is None:
                # On this wire a zero proto may omit the counter. Until the
                # authenticated shape is qualified, withhold the empty claim
                # and retry the count at the normal cadence.
                await self._commit(
                    cursor,
                    cursor.progress,
                    failure=Failure("LabelUnavailable", poll_again=True),
                )
                return
            if count == 0:
                await self._commit(
                    cursor, {**cursor.progress, "residual": None}, complete=True
                )
                return
            residual = cast(dict[str, object] | None, cursor.progress.get("residual"))
            if residual and residual["total"] == count:
                if self._now() < datetime.fromisoformat(str(residual["recheck_at"])):
                    if cursor.error is not None and cursor.error.code == "Partial":
                        await self._commit(
                            cursor,
                            cursor.progress,
                            failure=Failure("Partial", poll_again=True),
                        )
                    else:
                        await self._commit(cursor, cursor.progress, complete=True)
                    return
            if residual:
                cursor = await self._commit(
                    cursor, {**cursor.progress, "residual": None}
                )
            await self._drain(cursor, name, count, source.label_id)
        except _NotAdmitted:
            return
        except WorkspaceError as exc:
            await self._store.commit_progress(
                cursor, cursor.progress, failure=_failure(exc), episode=self._episode
            )
        except (ValueError, OverflowError, ValidationError):
            await self._store.commit_progress(
                cursor,
                cursor.progress,
                failure=Failure("InvalidResponse", blocked=True),
            )


def _failure(error: WorkspaceError) -> Failure:
    if error.kind == "rate_limited":
        return Failure("RateLimited", retry_at=error.retry_at, issue=error)
    if error.kind in {"grant_unavailable", "scope_missing"}:
        return Failure("AuthUnavailable", blocked=True, issue=error)
    if error.kind in {"consent_required", "consent_expired"}:
        return Failure("ConsentRequired", blocked=True, issue=error)
    if error.kind == "approval_busy":
        return Failure("ConsentRequired", retry_at=error.retry_at, issue=error)
    if error.kind in {"denied", "policy_block", "withheld", "screened"}:
        return Failure("Forbidden", blocked=True, issue=error)
    if error.kind in {"invalid_response", "unsupported"}:
        return Failure("InvalidResponse", blocked=True, issue=error)
    return Failure("TransportUnavailable", issue=error)
