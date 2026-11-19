"""Exact, bounded source reads; provider locations never leave this module."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from jarvis._thread_io import joined_thread
from jarvis.connectors import (
    GmailPart,
    GoogleReadConnector,
    OriginalTooLarge,
    decode_gmail_body,
)
from jarvis.read_tools import (
    ATTACHMENT_MAX_BYTES,
    ATTACHMENT_OPERATION_SECONDS,
    ConnectorFailure,
    ReadResponse,
)


@dataclass(frozen=True, slots=True)
class SourceOriginal:
    source: dict[str, object]
    filename: str | None
    media_type: str | None
    advertised_size: int | None


class AttachmentSources:
    def __init__(self, *, google: GoogleReadConnector) -> None:
        self._google = google

    async def _part(
        self, source: dict[str, object], attempt_started: Callable[[], None]
    ) -> tuple[str, GmailPart, int]:
        if source["kind"] != "gmail":
            raise ConnectorFailure("source_changed", attempts=0)
        response = await self._google.gmail_attachment_message(
            str(source["message_id"]), attempt_started=attempt_started
        )
        original = response.value
        if "account" in source and source["account"] != original.account:
            raise ConnectorFailure("source_changed", attempts=response.attempts)
        selected = next(
            (part for part in original.files if part.part_id == source["part_id"]), None
        )
        if selected is None:
            raise ConnectorFailure(
                "source_changed" if "account" in source else "not_found",
                attempts=response.attempts,
            )
        return original.account, selected, response.attempts

    async def resolve(self, source: dict[str, object]) -> ReadResponse[SourceOriginal]:
        attempts = 0

        def attempted() -> None:
            nonlocal attempts
            attempts += 1

        try:
            async with asyncio.timeout(ATTACHMENT_OPERATION_SECONDS):
                account, selected, attempts = await self._part(source, attempted)
                return ReadResponse(
                    SourceOriginal(
                        {
                            "kind": "gmail",
                            "account": account,
                            "message_id": source["message_id"],
                            "part_id": selected.part_id,
                        },
                        selected.filename or None,
                        selected.media_type,
                        selected.advertised_size,
                    ),
                    attempts,
                )
        except (TimeoutError, httpx.HTTPError, OSError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None

    async def download(self, source: dict[str, object], destination: Path) -> int:
        attempts = 0
        starts = 0

        def attempted() -> None:
            nonlocal starts
            starts += 1

        try:
            async with asyncio.timeout(ATTACHMENT_OPERATION_SECONDS):
                _, part, attempts = await self._part(source, attempted)
                if (
                    part.advertised_size is not None
                    and part.advertised_size > ATTACHMENT_MAX_BYTES
                ):
                    raise ConnectorFailure("too_large", attempts=attempts)
                if part.external_id is not None:
                    try:
                        body = await self._google.gmail_attachment_body(
                            str(source["message_id"]),
                            part.external_id,
                            attempt_started=attempted,
                        )
                    except ConnectorFailure as exc:
                        raise ConnectorFailure(
                            exc.code, attempts=attempts + exc.attempts
                        ) from None
                    attempts += body.attempts
                    content = body.value
                else:
                    content = await joined_thread(self._inline, part, attempts)
                await joined_thread(destination.write_bytes, content)
                return attempts
        except (TimeoutError, httpx.HTTPError, OSError):
            raise ConnectorFailure(
                "provider_unavailable", attempts=max(attempts, starts)
            ) from None

    @staticmethod
    def _inline(part: GmailPart, attempts: int) -> bytes:
        if part.data is None:
            raise ConnectorFailure("provider_unavailable", attempts=attempts)
        try:
            return decode_gmail_body(part.data)
        except OriginalTooLarge:
            raise ConnectorFailure("too_large", attempts=attempts) from None
        except ValueError:
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None
