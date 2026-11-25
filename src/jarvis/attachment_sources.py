"""Resolve and revalidate observed Gmail file selectors before storing their bytes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from jarvis._thread_io import joined_thread
from jarvis.connectors import OriginalTooLarge
from jarvis.read_tools import (
    ATTACHMENT_OPERATION_SECONDS,
    ConnectorFailure,
    ReadResponse,
    display_descriptor,
)
from jarvis.workspace_mcp import HUMAN_WAIT_SECONDS, WorkspaceError, workspace_attempts
from jarvis.workspace_mime import MailPart
from jarvis.workspace_reads import WorkspaceReads


@dataclass(frozen=True, slots=True)
class SourceOriginal:
    source: dict[str, object]
    filename: str | None
    media_type: str | None
    advertised_size: int | None
    content: bytes = field(repr=False)


class AttachmentSources:
    def __init__(self, *, google: WorkspaceReads | None) -> None:
        self._google = google

    async def _part(self, source: dict[str, object]) -> ReadResponse[MailPart]:
        if self._google is None:
            raise ConnectorFailure("provider_unavailable", attempts=0)
        if source.get("kind") != "gmail" or not str(
            source.get("part_id", "")
        ).startswith("mime1."):
            raise ConnectorFailure("source_changed", attempts=0)
        # Leave room in the retain action for object observation and upload.
        with workspace_attempts(8, seconds=ATTACHMENT_OPERATION_SECONDS) as meter:
            try:
                async with asyncio.timeout(
                    ATTACHMENT_OPERATION_SECONDS + HUMAN_WAIT_SECONDS
                ):
                    part = await self._google.original(source)
                return ReadResponse(part, meter.attempts)
            except WorkspaceError as exc:
                code = {
                    "not_found": "not_found",
                    "source_changed": "source_changed",
                    "partial": "provider_response_too_large",
                }.get(exc.kind, "provider_unavailable")
                raise ConnectorFailure(code, attempts=meter.attempts) from exc
            except OriginalTooLarge:
                raise ConnectorFailure("too_large", attempts=meter.attempts) from None
            except (TimeoutError, ValueError, RecursionError, OSError):
                raise ConnectorFailure(
                    "provider_unavailable", attempts=meter.attempts
                ) from None

    async def resolve(self, source: dict[str, object]) -> ReadResponse[SourceOriginal]:
        if self._google is None or self._google.account is None:
            raise ConnectorFailure("provider_unavailable", attempts=0)
        qualified = {"account": self._google.account, **source}
        response = await self._part(qualified)
        part = response.value
        assert part.content is not None
        size = len(part.content)
        desc = display_descriptor(part.filename, part.media_type, size)
        return ReadResponse(
            SourceOriginal(
                qualified,
                str(desc["name"]) if desc["name"] is not None else None,
                part.media_type,
                size,
                part.content,
            ),
            response.attempts,
        )

    async def download(self, source: dict[str, object], destination: Path) -> int:
        response = await self._part(source)
        part = response.value
        assert part.content is not None
        await joined_thread(destination.write_bytes, part.content)
        return response.attempts
