"""Exact, bounded source reads; provider locations never leave this module."""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx

from jarvis._thread_io import joined_thread
from jarvis.config import DiscordSettings
from jarvis.connectors import (
    GmailPart,
    GoogleReadConnector,
    OriginalTooLarge,
    decode_gmail_body,
)
from jarvis.read_tools import (
    ATTACHMENT_CONNECT_SECONDS,
    ATTACHMENT_MAX_BYTES,
    ATTACHMENT_OPERATION_SECONDS,
    ATTACHMENT_SOCKET_SECONDS,
    ConnectorFailure,
    ReadResponse,
    attachment_media_type,
)


@dataclass(frozen=True, slots=True)
class SourceOriginal:
    source: dict[str, object]
    filename: str | None
    media_type: str | None
    advertised_size: int | None


class AttachmentSources:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        google: GoogleReadConnector,
        discord: DiscordSettings,
    ) -> None:
        self._client = client
        self._google = google
        self._discord = discord

    async def resolve(self, source: dict[str, object]) -> ReadResponse[SourceOriginal]:
        attempts = 0

        def attempted() -> None:
            nonlocal attempts
            attempts += 1

        try:
            async with asyncio.timeout(ATTACHMENT_OPERATION_SECONDS):
                return await self._resolve(source, attempted)
        except (TimeoutError, httpx.HTTPError, OSError):
            raise ConnectorFailure("provider_unavailable", attempts=attempts) from None

    async def _resolve(
        self, source: dict[str, object], attempt_started: Callable[[], None]
    ) -> ReadResponse[SourceOriginal]:
        if source["kind"] == "gmail":
            response = await self._google.gmail_attachment_message(
                str(source["message_id"]), attempt_started=attempt_started
            )
            original = response.value
            if "account" in source and source["account"] != original.account:
                raise ConnectorFailure("source_changed", attempts=response.attempts)
            selected = next(
                (part for part in original.files if part.part_id == source["part_id"]),
                None,
            )
            if selected is None:
                raise ConnectorFailure("not_found", attempts=response.attempts)
            identity: dict[str, object] = {
                "kind": "gmail",
                "account": original.account,
                "message_id": original.message_id,
                "part_id": selected.part_id,
            }
            return ReadResponse(
                SourceOriginal(
                    identity,
                    selected.filename or None,
                    selected.media_type,
                    selected.advertised_size,
                ),
                response.attempts,
            )
        payload = await self._discord_message(source, attempt_started=attempt_started)
        selected = self._discord_part(payload, str(source["attachment_id"]))
        identity = {
            "kind": "discord",
            "guild_id": str(self._discord.guild_id),
            "channel_id": str(self._discord.channel_id),
            "message_id": str(source["message_id"]),
            "attachment_id": str(source["attachment_id"]),
        }
        if "guild_id" in source and identity != source:
            raise ConnectorFailure("source_changed", attempts=1)
        filename, media_type, size = (
            selected.get("filename"),
            selected.get("content_type"),
            selected.get("size"),
        )
        if (
            (filename is not None and not isinstance(filename, str))
            or (
                media_type is not None
                and (not isinstance(media_type, str) or len(media_type.encode()) > 255)
            )
            or (
                size is not None
                and (type(size) is not int or size < 0 or size > 2**63 - 1)
            )
        ):
            raise ConnectorFailure("provider_unavailable", attempts=1)
        try:
            attachment_media_type(media_type)
        except ValueError:
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return ReadResponse(
            SourceOriginal(
                identity,
                filename,
                media_type,
                size,
            ),
            1,
        )

    async def download(self, source: dict[str, object], destination: Path) -> int:
        attempts = 0
        starts = 0

        def attempted() -> None:
            nonlocal starts
            starts += 1

        try:
            async with asyncio.timeout(ATTACHMENT_OPERATION_SECONDS):
                if source["kind"] == "gmail":
                    response = await self._google.gmail_attachment_message(
                        str(source["message_id"]), attempt_started=attempted
                    )
                    attempts = response.attempts
                    original = response.value
                    part = next(
                        (
                            part
                            for part in original.files
                            if part.part_id == source["part_id"]
                        ),
                        None,
                    )
                    if original.account != source["account"] or part is None:
                        raise ConnectorFailure("source_changed", attempts=attempts)
                    self._check_advertised(part.advertised_size, attempts)
                    if part.external_id is not None:
                        try:
                            body = await self._google.gmail_attachment_body(
                                original.message_id,
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
                payload = await self._discord_message(source, attempt_started=attempted)
                attempts = 1
                selected = self._discord_part(payload, str(source["attachment_id"]))
                size = selected.get("size")
                self._check_advertised(size if type(size) is int else None, attempts)
                url = selected.get("url")
                if not isinstance(url, str) or not url.startswith("https://"):
                    raise ConnectorFailure("provider_unavailable", attempts=attempts)
                attempts += 1
                attempted()
                async with self._client.stream(
                    "GET",
                    url,
                    follow_redirects=False,
                    timeout=httpx.Timeout(
                        ATTACHMENT_SOCKET_SECONDS, connect=ATTACHMENT_CONNECT_SECONDS
                    ),
                ) as response:
                    if response.status_code == 404:
                        raise ConnectorFailure("not_found", attempts=attempts)
                    if response.status_code != 200:
                        raise ConnectorFailure(
                            "provider_unavailable", attempts=attempts
                        )
                    count = 0
                    with destination.open("wb") as output:
                        async for chunk in response.aiter_bytes(
                            chunk_size=1_024 * 1_024
                        ):
                            count += len(chunk)
                            if count > ATTACHMENT_MAX_BYTES:
                                raise ConnectorFailure("too_large", attempts=attempts)
                            await joined_thread(output.write, chunk)
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

    @staticmethod
    def _check_advertised(size: int | None, attempts: int) -> None:
        if size is not None and size > ATTACHMENT_MAX_BYTES:
            raise ConnectorFailure("too_large", attempts=attempts)

    async def _discord_message(
        self, source: dict[str, object], *, attempt_started: Callable[[], None]
    ) -> dict[str, object]:
        if source.get("guild_id", str(self._discord.guild_id)) != str(
            self._discord.guild_id
        ) or source.get("channel_id", str(self._discord.channel_id)) != str(
            self._discord.channel_id
        ):
            raise ConnectorFailure("source_changed", attempts=0)
        try:
            attempt_started()
            async with (
                asyncio.timeout(8.0),
                self._client.stream(
                    "GET",
                    f"https://discord.com/api/v10/channels/{self._discord.channel_id}/messages/{source['message_id']}",
                    headers={
                        "Authorization": "Bot "
                        + self._discord.bot_token.get_secret_value()
                    },
                    follow_redirects=False,
                    timeout=8.0,
                ) as response,
            ):
                if response.status_code == 404:
                    raise ConnectorFailure("not_found", attempts=1)
                if response.status_code != 200:
                    raise ConnectorFailure("provider_unavailable", attempts=1)
                with tempfile.TemporaryFile() as body:
                    size = 0
                    async for chunk in response.aiter_bytes(chunk_size=1_024 * 1_024):
                        size += len(chunk)
                        if size > 2 * 1_024 * 1_024:
                            raise ConnectorFailure(
                                "provider_response_too_large", attempts=1
                            )
                        await joined_thread(body.write, chunk)
                    body.seek(0)
                    payload: object = await joined_thread(json.load, body)
            if not isinstance(payload, dict):
                raise ValueError("message is not an object")
            payload = cast(dict[str, object], payload)
            author_raw = payload.get("author")
            author = (
                cast(dict[str, object], author_raw)
                if isinstance(author_raw, dict)
                else {}
            )
            if (
                payload.get("id") != source["message_id"]
                or payload.get("channel_id") != str(self._discord.channel_id)
                or author.get("id") != str(self._discord.owner_user_id)
                or author.get("bot") is True
                or payload.get("webhook_id") is not None
            ):
                raise ConnectorFailure("source_changed", attempts=1)
            return payload
        except (TimeoutError, httpx.HTTPError, ValueError, TypeError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None

    @staticmethod
    def _discord_part(
        payload: dict[str, object], attachment_id: str
    ) -> dict[str, object]:
        parts = payload.get("attachments")
        if not isinstance(parts, list):
            raise ConnectorFailure("provider_unavailable", attempts=1)
        selected = [
            cast(dict[str, object], part)
            for part in cast(list[object], parts)
            if isinstance(part, dict)
            and cast(dict[str, object], part).get("id") == attachment_id
        ]
        if len(selected) != 1:
            raise ConnectorFailure(
                "not_found" if not selected else "provider_unavailable", attempts=1
            )
        return selected[0]
