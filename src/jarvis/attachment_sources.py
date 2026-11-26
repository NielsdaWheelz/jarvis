"""Materialize and revalidate the byte sources of an authorized Drive action."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, nullcontext
from dataclasses import replace
from pathlib import Path

from jarvis._thread_io import joined_thread
from jarvis.attachments import AttachmentStore, copy_verified
from jarvis.mail_files import (
    NATIVE_MAIL_ROOT,
    NativeFileRef,
    canonical_media_type,
    native_file,
)
from jarvis.read_tools import ATTACHMENT_MAX_BYTES
from jarvis.workspace_mcp import Fence, WorkspaceError
from jarvis.workspace_reads import WorkspaceReads
from jarvis.workspace_write_models import (
    DriveBinarySource,
    DriveSourceFile,
    GmailPartSource,
    NativePublicationSource,
    SubmissionSource,
)


class AttachmentSources:
    def __init__(
        self,
        submissions: AttachmentStore,
        google: WorkspaceReads | None,
        *,
        native_root: Path = NATIVE_MAIL_ROOT,
    ) -> None:
        self._submissions = submissions
        self._google = google
        self._native = native_root
        self._stage_lock = asyncio.Lock()

    @asynccontextmanager
    async def open(
        self,
        source: DriveBinarySource,
        *,
        invocation_id: str,
        before_send: Fence,
    ) -> AsyncIterator[DriveSourceFile]:
        async with (
            nullcontext() if isinstance(source, SubmissionSource) else self._stage_lock
        ):
            async with AsyncExitStack() as opened:
                try:
                    if isinstance(source, SubmissionSource):
                        row, stream = await self._submissions.open_pending(
                            source.submission_id
                        )
                        opened.enter_context(stream)
                        assert row.sha256 is not None and row.size_bytes is not None
                        # Filing owns custody through effect entry. The source is
                        # immutable and cannot be abandoned during transmission.
                        file = DriveSourceFile(
                            Path(stream.name),
                            row.filename or "upload",
                            canonical_media_type(row.media_type),
                            row.size_bytes,
                            row.sha256,
                        )
                    else:
                        scratch = await opened.enter_async_context(
                            self._submissions.transfer_scratch(ATTACHMENT_MAX_BYTES)
                        )
                        private = opened.enter_context(
                            tempfile.TemporaryDirectory(
                                prefix=".transfer-", dir=scratch
                            )
                        )
                        staged = opened.enter_context(
                            tempfile.NamedTemporaryFile(dir=private)
                        )
                        path = Path(staged.name)
                        if isinstance(source, NativePublicationSource):
                            reference = NativeFileRef(
                                kind="native",
                                id=source.native_file_id,
                                manifest_sha256=source.manifest_sha256,
                            )
                            with native_file(self._native, reference) as (
                                descriptor,
                                stream,
                            ):
                                await joined_thread(
                                    copy_verified,
                                    stream,
                                    staged.write,
                                    descriptor.size_bytes,
                                    descriptor.sha256,
                                )
                            file = DriveSourceFile(
                                path,
                                descriptor.filename,
                                descriptor.media_type,
                                descriptor.size_bytes,
                                descriptor.sha256,
                            )
                        else:
                            assert isinstance(source, GmailPartSource)
                            if self._google is None:
                                raise WorkspaceError("provider_unavailable")
                            observed = source.gmail_observation
                            part = await self._google.original(
                                {
                                    "kind": "gmail",
                                    "account": observed.account,
                                    "message_id": observed.message_id,
                                    "part_id": source.part_selector,
                                },
                                invocation_id=invocation_id,
                                before_send=before_send,
                            )
                            assert part.content is not None
                            if len(part.content) > ATTACHMENT_MAX_BYTES:
                                raise WorkspaceError("too_large")
                            await joined_thread(staged.write, part.content)
                            file = DriveSourceFile(
                                path,
                                part.filename or "attachment",
                                part.media_type,
                                len(part.content),
                                hashlib.sha256(part.content).hexdigest(),
                            )
                            del part
                        staged.flush()
                        os.fchmod(staged.fileno(), 0o400)
                except WorkspaceError as exc:
                    if exc.kind == "uncertain":
                        raise WorkspaceError(
                            "source_unavailable",
                            retry_at=exc.retry_at,
                            known_no_effect=True,
                        ) from exc
                    exc.known_no_effect = True
                    raise
                except (OSError, ValueError) as exc:
                    raise WorkspaceError(
                        "source_unavailable", known_no_effect=True
                    ) from exc
                if file.media_type.startswith("application/vnd.google-apps."):
                    file = replace(file, media_type="application/octet-stream")
                yield file
