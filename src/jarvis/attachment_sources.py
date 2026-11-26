"""Materialize and revalidate the byte sources of an authorized Drive action."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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

    @asynccontextmanager
    async def open(
        self,
        source: DriveBinarySource,
        *,
        invocation_id: str,
        before_send: Fence,
    ) -> AsyncIterator[DriveSourceFile]:
        with tempfile.NamedTemporaryFile(prefix="jarvis-drive-source-") as staged:
            path = Path(staged.name)
            try:
                if isinstance(source, SubmissionSource):
                    row, stream = await self._submissions.open_pending(
                        source.submission_id
                    )
                    with stream:
                        assert row.sha256 is not None and row.size_bytes is not None
                        await joined_thread(
                            copy_verified,
                            stream,
                            staged.write,
                            row.size_bytes,
                            row.sha256,
                        )
                    file = DriveSourceFile(
                        path,
                        row.filename or "upload",
                        canonical_media_type(row.media_type),
                        row.size_bytes,
                        row.sha256,
                    )
                elif isinstance(source, NativePublicationSource):
                    reference = NativeFileRef(
                        kind="native",
                        id=source.native_file_id,
                        manifest_sha256=source.manifest_sha256,
                    )
                    with native_file(self._native, reference) as (descriptor, stream):
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
                    await joined_thread(staged.write, part.content)
                    file = DriveSourceFile(
                        path,
                        part.filename or "attachment",
                        part.media_type,
                        len(part.content),
                        hashlib.sha256(part.content).hexdigest(),
                    )
                staged.flush()
                os.fchmod(staged.fileno(), 0o400)
            except (OSError, ValueError):
                raise WorkspaceError("source_unavailable") from None
            if file.media_type.startswith("application/vnd.google-apps."):
                file = replace(file, media_type="application/octet-stream")
            yield file
