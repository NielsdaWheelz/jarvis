"""Bounded Gmail observations with durable progress owned by EventStore."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import cast
from urllib.parse import quote

import httpx
from llm_tools import canonical_json_bytes
from pydantic import ValidationError

from jarvis.connectors import (
    GoogleCredentialDefect,
    GoogleProfile,
    GoogleReadConnector,
    GoogleReadFailure,
    GoogleTokenManager,
    google_profile,
    provider_array,
    provider_object,
    provider_string,
    provider_text,
)
from jarvis.event_tools import (
    POLL_SECONDS,
    EmailAdded,
    Preview,
    provider_id,
    text_preview,
)
from jarvis.events import Cursor, EventStore, Failure, Observation
from jarvis.read_tools import GMAIL_API_BASE_URL, ConnectorFailure

_LOGGER = logging.getLogger(__name__)
_PAGE_SIZE = 20
_QUANTUM_SECONDS = 30.0

_HISTORY_FIELDS = (
    "history(id,messagesAdded(message(id,threadId))),nextPageToken,historyId"
)


class _NotAdmitted(Exception):
    pass


class _ReadFailed(Exception):
    def __init__(self, failure: Failure, *, status: int | None = None) -> None:
        self.failure = failure
        self.status = status
        super().__init__(failure.code)


def _optional_id(value: dict[str, object], key: str) -> str | None:
    return None if value.get(key) is None else provider_id(provider_string(value, key))


def _preview(value: object) -> Preview | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("source preview is malformed")
    return text_preview(value, 240)


def _page_token(payload: dict[str, object], name: str = "nextPageToken") -> str | None:
    if payload.get(name) is None:
        return None
    return provider_text(provider_string(payload, name), 8_192)


def _prefix(candidates: list[tuple[str, str, str | None]], count: int) -> str | None:
    if not count:
        return None
    return hashlib.sha256(
        canonical_json_bytes(
            [[history, message] for history, message, _ in candidates[:count]]
        )
    ).hexdigest()


class EventPoller:
    def __init__(
        self,
        *,
        store: EventStore,
        client: httpx.AsyncClient,
        tokens: GoogleTokenManager,
        admitted: Callable[[], Awaitable[bool]],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._reads = GoogleReadConnector(client=client, tokens=tokens, now=now)
        self._admitted = admitted
        self._now = now
        self._changed = asyncio.Event()
        self._deadline = 0.0
        self._verification_at: datetime | None = None
        self._verification_failures = 0
        self._verification_blocked = False
        self._stop: asyncio.Event | None = None

    def notify_changed(self) -> None:
        self._changed.set()

    async def run(self, stop: asyncio.Event) -> None:
        self._stop = stop
        while not stop.is_set():
            self._changed.clear()
            wait_seconds = float(POLL_SECONDS)
            if await self._admitted():
                if self._store.account is None:
                    if not self._verification_blocked and (
                        self._verification_at is None
                        or self._verification_at <= self._now()
                    ):
                        await self._verify()
                    if self._store.account is None and not self._verification_blocked:
                        due_at = self._verification_at
                        if due_at is not None:
                            wait_seconds = min(
                                float(POLL_SECONDS),
                                max(0.0, (due_at - self._now()).total_seconds()),
                            )
                if self._store.account is not None:
                    cursor = await self._store.poll_cursor()
                    if cursor is not None and cursor.next_poll_at is not None:
                        delay = (cursor.next_poll_at - self._now()).total_seconds()
                        if delay <= 0:
                            await self.poll(cursor)
                            await asyncio.sleep(0)
                            continue
                        wait_seconds = min(float(POLL_SECONDS), delay)
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

    async def _verify(self) -> None:
        self._deadline = time.monotonic() + _QUANTUM_SECONDS
        try:
            profile = await self._profile(None)
            await self._store.initialize(profile.account, profile.history_id)
            self._verification_failures = 0
        except _NotAdmitted:
            return
        except _ReadFailed as exc:
            self._verification_failures = min(5, self._verification_failures + 1)
            delay = (60, 120, 240, 480, 900)[self._verification_failures - 1]
            self._verification_at = max(
                self._now() + timedelta(seconds=delay),
                exc.failure.retry_at or self._now(),
            )
            self._verification_blocked = exc.failure.blocked
            _LOGGER.warning(
                "event source account unavailable code=%s retry_count=%d blocked=%s",
                exc.failure.code,
                self._verification_failures,
                self._verification_blocked,
            )

    async def _before(self, cursor: Cursor | None) -> None:
        # Provider cancellation must join admission SQL, never cancel its owner.
        task = asyncio.create_task(self._check_admission(cursor))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def _check_admission(self, cursor: Cursor | None) -> None:
        if time.monotonic() >= self._deadline:
            raise _ReadFailed(Failure("TransportUnavailable"))
        if self._stop is not None and self._stop.is_set():
            raise _NotAdmitted
        if not await self._admitted() or (
            cursor is not None and not await self._store.admission(cursor)
        ):
            raise _NotAdmitted

    async def _read(
        self, cursor: Cursor | None, url: str, params: dict[str, str | int | list[str]]
    ) -> dict[str, object]:
        for attempt in range(2):
            await self._before(cursor)
            try:
                async with asyncio.timeout(
                    max(0.001, self._deadline - time.monotonic())
                ):
                    payload = await self._fetch(cursor, url, params)
                return payload
            except GoogleReadFailure as exc:
                if exc.status == 401 and attempt == 0:
                    continue
                retry_at = None
                if exc.retry_after:
                    try:
                        if exc.retry_after.isdecimal():
                            retry_at = self._now() + timedelta(
                                seconds=int(exc.retry_after)
                            )
                        else:
                            parsed = parsedate_to_datetime(exc.retry_after)
                            if parsed.tzinfo is not None:
                                retry_at = parsed.astimezone(UTC)
                    except (ValueError, TypeError, OverflowError):
                        pass
                if exc.status == 401:
                    failure = Failure("AuthUnavailable", blocked=True)
                elif exc.status == 403 and exc.code == "rate_limited":
                    failure = Failure("RateLimited", retry_at=retry_at)
                elif exc.status == 403 and exc.grant_unavailable:
                    failure = Failure("AuthUnavailable", blocked=True)
                elif exc.status == 403:
                    failure = Failure("Forbidden", blocked=True)
                elif 200 <= exc.status < 300 or exc.status == 400:
                    failure = Failure("InvalidResponse", blocked=True)
                elif exc.status == 429:
                    failure = Failure("RateLimited", retry_at=retry_at)
                else:
                    failure = Failure("TransportUnavailable", retry_at=retry_at)
                raise _ReadFailed(failure, status=exc.status) from None
            except GoogleCredentialDefect:
                raise _ReadFailed(Failure("AuthUnavailable", blocked=True)) from None
            except ConnectorFailure as exc:
                raise _ReadFailed(
                    Failure("ResponseTooLarge", blocked=True)
                    if exc.code == "provider_response_too_large"
                    else Failure("RateLimited")
                    if exc.code == "rate_limited"
                    else Failure("TransportUnavailable")
                ) from None
            except TimeoutError:
                raise _ReadFailed(Failure("TransportUnavailable")) from None
        raise AssertionError("request retry exhausted")

    async def _fetch(
        self,
        cursor: Cursor | None,
        url: str,
        params: dict[str, str | int | list[str]],
    ) -> dict[str, object]:
        request = asyncio.create_task(
            self._reads.get_json(
                url,
                params=params,
                not_found="not_found",
                before_request=lambda: self._before(cursor),
            )
        )
        stopped = (
            asyncio.create_task(self._stop.wait()) if self._stop is not None else None
        )
        try:
            if stopped is not None:
                await asyncio.wait(
                    (request, stopped), return_when=asyncio.FIRST_COMPLETED
                )
                if stopped.done():
                    raise _NotAdmitted
            payload, _ = await request
            return payload
        finally:
            if stopped is not None:
                stopped.cancel()
            request.cancel()
            await asyncio.gather(
                request,
                *(() if stopped is None else (stopped,)),
                return_exceptions=True,
            )

    async def _commit(
        self,
        cursor: Cursor,
        progress: dict[str, object],
        observations: Sequence[Observation] = (),
        *,
        complete: bool = False,
        failure: Failure | None = None,
        gap: bool = False,
    ) -> bool:
        if (
            self._stop is not None and self._stop.is_set()
        ) or not await self._admitted():
            return False
        return await self._store.commit_progress(
            cursor,
            progress,
            observations,
            complete=complete,
            failure=failure,
            gap=gap,
        )

    async def _profile(self, cursor: Cursor | None) -> GoogleProfile:
        payload = await self._read(
            cursor,
            f"{GMAIL_API_BASE_URL}/users/me/profile",
            {"fields": "emailAddress,historyId"},
        )
        try:
            return google_profile(payload)
        except ValueError:
            raise _ReadFailed(Failure("InvalidResponse", blocked=True)) from None

    async def poll(self, cursor: Cursor) -> None:
        """One bounded page/prefix; all provider calls precede owned publication."""
        self._deadline = time.monotonic() + _QUANTUM_SECONDS
        try:
            await self._gmail(cursor)
        except _NotAdmitted:
            return
        except _ReadFailed as exc:
            await self._commit(cursor, cursor.progress, failure=exc.failure)
        except (ValueError, TypeError, ValidationError, OverflowError):
            await self._commit(
                cursor,
                cursor.progress,
                failure=Failure("InvalidResponse", blocked=True),
            )

    async def _gmail(self, cursor: Cursor) -> None:
        progress = dict(cursor.progress)
        if progress["history_id"] is None:
            profile = await self._profile(cursor)
            if profile.account != cursor.account_id:
                raise _ReadFailed(Failure("AuthUnavailable", blocked=True))
            progress["history_id"] = profile.history_id
            await self._commit(cursor, progress, complete=True)
            return
        params: dict[str, str | int | list[str]] = {
            "startHistoryId": str(progress["history_id"]),
            "historyTypes": "messageAdded",
            "maxResults": _PAGE_SIZE,
            "fields": _HISTORY_FIELDS,
        }
        if progress["page_token"] is not None:
            params["pageToken"] = str(progress["page_token"])
        try:
            payload = await self._read(
                cursor, f"{GMAIL_API_BASE_URL}/users/me/history", params
            )
        except _ReadFailed as exc:
            if exc.status != 404:
                raise
            await self._commit(
                cursor,
                {
                    "history_id": None,
                    "page_token": None,
                    "consumed": 0,
                    "prefix_sha256": None,
                },
                gap=True,
            )
            return
        high_water = provider_text(provider_string(payload, "historyId"), 8192)
        if not high_water.isascii() or not high_water.isdecimal():
            raise ValueError("invalid Gmail high water")
        candidates: dict[tuple[str, str], str | None] = {}
        for raw in provider_array(payload.get("history", []), "Gmail history"):
            history = provider_object(raw, "Gmail history record")
            history_id = provider_text(provider_string(history, "id"), 8192)
            if not history_id.isascii() or not history_id.isdecimal():
                raise ValueError("invalid history order")
            for raw_added in provider_array(
                history.get("messagesAdded", []), "Gmail additions"
            ):
                item = provider_object(
                    provider_object(raw_added, "Gmail addition").get("message"),
                    "Gmail message",
                )
                message_id = provider_id(provider_string(item, "id"))
                candidates[(history_id, message_id)] = _optional_id(item, "threadId")
        ordered = [
            (history, message, thread)
            for (history, message), thread in sorted(
                candidates.items(), key=lambda entry: (int(entry[0][0]), entry[0][1])
            )
        ]
        consumed = cast("int", progress["consumed"])
        if (
            consumed > len(ordered)
            or _prefix(ordered, consumed) != progress["prefix_sha256"]
        ):
            consumed = 0
        observations: list[Observation] = []
        failure = None
        for _, message_id, thread_id in ordered[consumed : consumed + _PAGE_SIZE]:
            identity = (cursor.account_id, message_id)
            try:
                if not await self._store.is_email_published(
                    identity
                ) and not await self._store.has_sent_echo(message_id):
                    observation = await self._mail_metadata(
                        cursor, message_id, thread_id, identity
                    )
                    if observation is not None:
                        observations.append(observation)
            except _ReadFailed as exc:
                failure = exc.failure
                break
            except (ValueError, TypeError, ValidationError, OverflowError):
                failure = Failure("InvalidResponse", blocked=True)
                break
            consumed += 1
        progress["consumed"] = consumed
        progress["prefix_sha256"] = _prefix(ordered, consumed)
        complete = False
        if failure is None and consumed == len(ordered):
            progress["page_token"] = _page_token(payload)
            progress["consumed"] = 0
            progress["prefix_sha256"] = None
            if progress["page_token"] is None:
                progress["history_id"] = high_water
                complete = True
        await self._commit(
            cursor, progress, observations, complete=complete, failure=failure
        )

    async def _mail_metadata(
        self,
        cursor: Cursor,
        message_id: str,
        thread_id: str | None,
        identity: tuple[object, ...],
    ) -> Observation | None:
        try:
            payload = await self._read(
                cursor,
                f"{GMAIL_API_BASE_URL}/users/me/messages/{quote(message_id, safe='')}",
                {
                    "format": "metadata",
                    "metadataHeaders": ["From", "Subject"],
                    "fields": "id,threadId,labelIds,internalDate,payload(headers)",
                },
            )
        except _ReadFailed as exc:
            if exc.status != 404:
                raise
            now = self._now()
            return Observation(
                "email_event",
                identity,
                EmailAdded(
                    account=cursor.account_id,
                    observed_at=now,
                    message_id=message_id,
                    thread_id=thread_id,
                    metadata="missing",
                    source_at=None,
                    sender=None,
                    subject=None,
                    inbox=None,
                ),
                now,
            )
        now = self._now()
        if provider_id(provider_string(payload, "id")) != message_id:
            raise ValueError("metadata message identity changed")
        labels = set(provider_array(payload.get("labelIds", []), "Gmail labels"))
        if any(not isinstance(label, str) for label in labels):
            raise ValueError("invalid Gmail label")
        if labels.intersection({"DRAFT", "SPAM", "TRASH"}) or (
            "SENT" in labels and "INBOX" not in labels
        ):
            return None
        metadata = provider_object(payload.get("payload", {}), "Gmail metadata")
        headers: dict[str, str] = {}
        for raw in provider_array(metadata.get("headers", []), "Gmail headers"):
            header = provider_object(raw, "Gmail header")
            name = provider_string(header, "name").lower()
            if name in {"from", "subject"}:
                value = header.get("value")
                if not isinstance(value, str):
                    raise ValueError("invalid Gmail header text")
                headers[name] = value
        source_at = None
        if payload.get("internalDate") is not None:
            raw_date = provider_string(payload, "internalDate")
            if not raw_date.isdecimal():
                raise ValueError("invalid Gmail internal date")
            source_at = datetime.fromtimestamp(int(raw_date) / 1000, UTC)
        event = EmailAdded(
            account=cursor.account_id,
            observed_at=now,
            message_id=message_id,
            thread_id=_optional_id(payload, "threadId") or thread_id,
            metadata="available",
            source_at=source_at,
            sender=_preview(headers.get("from")),
            subject=_preview(headers.get("subject")),
            inbox="INBOX" in labels,
        )
        return Observation("email_event", identity, event, source_at or now)
