"""Qualify originals and publish native files for a single Gmail draft action."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import shutil
import stat
import sys
import tempfile
import time
import unicodedata
from collections.abc import Awaitable, Callable, Collection, Iterator
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, BinaryIO, Literal, Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import SchemaValidator, core_schema

from jarvis._secrets import SECRET_MARKER, contains_secret
from jarvis._thread_io import finish_entered, joined_thread
from jarvis.home_refs import DriveId
from jarvis.read_tools import ATTACHMENT_MAX_BYTES
from jarvis.workspace_mcp import WorkspaceError

if TYPE_CHECKING:
    from jarvis.workspace_write_models import DriveSourceFile

NATIVE_MAIL_ROOT = Path("/var/lib/jarvis-notes/.git/jarvis-mail")
MAIL_STAGE_ROOT = Path("/var/lib/jarvis/mail-stage")
MAIL_MAX_FILES = 10
MAIL_MAX_BYTES = 25_000_000
INTAKE_SECONDS = 60
_MANIFEST_BYTES = 4_096
_CHUNK_BYTES = 1024 * 1024
_SECRET_FOUND = 10
_BYTES_CHANGED = 11
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_MEDIA_TYPE = re.compile(
    r"(?:application|audio|font|haptics|image|model|text|video)/"
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}"
)


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def _basename(name: str) -> str:
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            for character in name
        )
        or len(name.encode("utf-8")) > 255
    ):
        raise ValueError("expected a basename of at most 255 utf-8 bytes")
    return name


def canonical_media_type(media_type: str | None) -> str:
    value = media_type.lower() if media_type else ""
    return value if _MEDIA_TYPE.fullmatch(value) else "application/octet-stream"


class MailFile(_Closed):
    filename: str
    media_type: str
    size_bytes: Annotated[int, Field(strict=True, ge=0)]
    sha256: Sha256

    @field_validator("filename")
    @classmethod
    def basename(cls, value: str) -> str:
        return _basename(value)

    @field_validator("media_type")
    @classmethod
    def canonical_type(cls, value: str) -> str:
        if canonical_media_type(value) != value:
            raise ValueError("expected a canonical media type")
        return value


class DriveMailFileRef(_Closed):
    kind: Literal["drive_file"]
    subject: DriveId
    id: DriveId
    export_type: (
        Annotated[str, Field(pattern=r"^[a-z0-9.+-]+/[a-z0-9.+-]+$", max_length=255)]
        | None
    ) = None


class NativeFileRef(_Closed):
    kind: Literal["native"]
    id: UUID
    manifest_sha256: Sha256


NewMailFile = Annotated[DriveMailFileRef | NativeFileRef, Field(discriminator="kind")]


class _NativeManifest(MailFile):
    id: UUID


class NativePublication(_Closed):
    ref: NativeFileRef
    file: MailFile


class FileUnavailable(_Closed):
    type: Literal["FileUnavailable"] = "FileUnavailable"
    slot: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=96)]


class MailLimit(_Closed):
    type: Literal["MailLimit"] = "MailLimit"
    measure: Literal["files", "decoded_bytes", "mime_bytes", "multipart_bytes"]
    actual: Annotated[int, Field(ge=0)]
    maximum: Annotated[int, Field(ge=0)]


class MailFileFailure(ValueError):
    def __init__(self, detail: FileUnavailable | MailLimit):
        super().__init__(detail.type)
        self.detail = detail

    @property
    def error(self) -> dict[str, object]:
        return self.detail.model_dump(mode="json")


@contextmanager
def _directory(path: Path | str, parent: int | None = None) -> Iterator[int]:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _regular(directory: int, leaf: str) -> Iterator[BinaryIO]:
    fd = os.open(
        leaf,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=directory,
    )
    with os.fdopen(fd, "rb") as stream:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise OSError("expected one regular file")
        yield stream


def _copy(
    source: BinaryIO, output: BinaryIO, maximum: int, deadline: float
) -> tuple[int, str]:
    size = 0
    digest = hashlib.sha256()
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError("mail file intake deadline")
        chunk = source.read(min(_CHUNK_BYTES, maximum + 1 - size))
        if not chunk:
            return size, digest.hexdigest()
        size += len(chunk)
        if size > maximum:
            return size, ""
        digest.update(chunk)
        output.write(chunk)


def _native_manifest(root: Path, ref: NativeFileRef) -> MailFile:
    with (
        _directory(root) as directory,
        _directory(str(ref.id), directory) as publication,
        _regular(publication, "manifest.json") as source,
    ):
        data = source.read(_MANIFEST_BYTES + 1)
    if (
        len(data) > _MANIFEST_BYTES
        or hashlib.sha256(data).hexdigest() != ref.manifest_sha256
    ):
        raise ValueError("native manifest digest mismatch")
    manifest = _NativeManifest.model_validate_json(data)
    if manifest.id != ref.id:
        raise ValueError("native manifest id mismatch")
    return MailFile.model_validate(manifest.model_dump(exclude={"id"}))


@contextmanager
def native_file(root: Path, ref: NativeFileRef) -> Iterator[tuple[MailFile, BinaryIO]]:
    descriptor = _native_manifest(root, ref)
    with (
        _directory(root) as directory,
        _directory(str(ref.id), directory) as entry,
        _regular(entry, "original") as original,
    ):
        yield descriptor, original


def publish_native(
    source: Path, name: str | None, *, root: Path = NATIVE_MAIL_ROOT
) -> NativePublication:
    source = Path(os.path.abspath(source))
    name = _basename(source.name if name is None else name)
    media_type, encoding = mimetypes.guess_type(name)
    identifier = uuid4()
    incoming = root / "incoming"
    transfer = source.is_relative_to(incoming)
    with ExitStack() as entries:
        directory = entries.enter_context(_directory(root))
        if transfer:
            if source.parent.parent != incoming:
                raise ValueError("expected an incoming request directory and file")
            incoming_fd = entries.enter_context(_directory("incoming", directory))
            source_fd = entries.enter_context(
                _directory(source.parent.name, incoming_fd)
            )
            if stat.S_IMODE(os.fstat(source_fd).st_mode) != 0o700:
                raise ValueError("incoming request directory must be private")
        else:
            source_fd = entries.enter_context(_directory(source.parent))
        stream = entries.enter_context(_regular(source_fd, source.name))
        temporary = Path(tempfile.mkdtemp(prefix=".prepare-", dir=root))
        try:
            group = os.fstat(directory).st_gid
            with _directory(temporary) as publication:
                os.fchown(publication, -1, group)
                with (temporary / "original").open("xb") as output:
                    size, digest = _copy(
                        stream,
                        output,
                        ATTACHMENT_MAX_BYTES,
                        time.monotonic() + INTAKE_SECONDS,
                    )
                    if size > ATTACHMENT_MAX_BYTES:
                        raise ValueError("file exceeds 100 mib")
                    os.fchown(output.fileno(), -1, group)
                    os.fchmod(output.fileno(), 0o640)
                    output.flush()
                    os.fsync(output.fileno())
                manifest = _NativeManifest(
                    id=identifier,
                    filename=name,
                    media_type=canonical_media_type(None if encoding else media_type),
                    size_bytes=size,
                    sha256=digest,
                )
                encoded = manifest.model_dump_json().encode()
                with (temporary / "manifest.json").open("xb") as output:
                    os.fchown(output.fileno(), -1, group)
                    os.fchmod(output.fileno(), 0o640)
                    output.write(encoded)
                    output.flush()
                    os.fsync(output.fileno())
                os.fchmod(publication, 0o750)
                os.fsync(publication)
            os.rename(
                temporary.name,
                str(identifier),
                src_dir_fd=directory,
                dst_dir_fd=directory,
            )
            os.fsync(directory)
            if transfer:
                os.unlink(source.name, dir_fd=source_fd)
                os.fsync(source_fd)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return NativePublication(
        ref=NativeFileRef(
            kind="native",
            id=identifier,
            manifest_sha256=hashlib.sha256(encoded).hexdigest(),
        ),
        file=MailFile.model_validate(manifest.model_dump(exclude={"id"})),
    )


@dataclass(frozen=True, slots=True)
class ObservedMailPart:
    """One complete, ordered part decoded from a verified Workspace draft."""

    file: MailFile
    data: bytes


@dataclass(frozen=True, slots=True)
class _SourceCopy:
    slot: int
    file: MailFile
    source: BinaryIO


class DriveMailReader(Protocol):
    async def drive_file(
        self,
        subject: str,
        id: str,
        export_type: str | None,
        *,
        destination: Path,
        maximum: int,
        invocation_id: str,
        before_send: Callable[[], Awaitable[None]],
    ) -> DriveSourceFile: ...


class MailFiles:
    def __init__(
        self,
        google: DriveMailReader | None,
        host_secrets: tuple[str, ...],
        *,
        native_root: Path = NATIVE_MAIL_ROOT,
        stage_root: Path = MAIL_STAGE_ROOT,
    ) -> None:
        self._google = google
        self._secrets = host_secrets
        self._native = native_root
        self._stage = stage_root

    async def stage(
        self,
        action_id: UUID,
        sources: tuple[NewMailFile | ObservedMailPart, ...],
        *,
        invocation_id: str,
        before_send: Callable[[], Awaitable[None]],
    ) -> tuple[MailFile, ...]:
        if len(sources) > MAIL_MAX_FILES:
            raise MailFileFailure(
                MailLimit(measure="files", actual=len(sources), maximum=MAIL_MAX_FILES)
            )
        deadline = time.monotonic() + INTAKE_SECONDS
        copies: list[_SourceCopy] = []
        slot, total = 1, 0
        try:
            async with asyncio.timeout(INTAKE_SECONDS):
                with ExitStack() as opened:
                    for slot, source in enumerate(sources, 1):
                        if isinstance(source, ObservedMailPart):
                            descriptor = source.file
                            body = opened.enter_context(io.BytesIO(source.data))
                        elif isinstance(source, DriveMailFileRef):
                            if self._google is None:
                                raise MailFileFailure(
                                    FileUnavailable(
                                        slot=slot, reason="drive_disconnected"
                                    )
                                )
                            temporary = opened.enter_context(
                                tempfile.TemporaryDirectory(prefix="jarvis-mail-drive-")
                            )
                            target = Path(temporary) / "download"
                            downloaded = await self._google.drive_file(
                                source.subject,
                                source.id,
                                source.export_type,
                                destination=target,
                                maximum=MAIL_MAX_BYTES - total,
                                invocation_id=invocation_id,
                                before_send=before_send,
                            )
                            descriptor = MailFile(
                                filename=downloaded.name,
                                media_type=canonical_media_type(downloaded.media_type),
                                size_bytes=downloaded.size,
                                sha256=downloaded.sha256,
                            )
                            body = opened.enter_context(target.open("rb"))
                        else:
                            descriptor, body = opened.enter_context(
                                native_file(self._native, source)
                            )
                        if contains_secret(descriptor.filename, self._secrets):
                            raise MailFileFailure(
                                FileUnavailable(slot=slot, reason="secret")
                            )
                        total += descriptor.size_bytes
                        if total > MAIL_MAX_BYTES:
                            raise MailFileFailure(
                                MailLimit(
                                    measure="decoded_bytes",
                                    actual=total,
                                    maximum=MAIL_MAX_BYTES,
                                )
                            )
                        copies.append(_SourceCopy(slot, descriptor, body))
                    if copies:
                        try:
                            await joined_thread(
                                self._stage_files, action_id, copies, deadline
                            )
                        except asyncio.CancelledError:
                            await self.discard(action_id)
                            raise
                        try:
                            await self._inspect(action_id, copies, deadline)
                        except BaseException:
                            await self.discard(action_id)
                            raise
        except MailFileFailure as exc:
            if isinstance(exc.detail, FileUnavailable):
                logging.getLogger(__name__).info(
                    "mail file unavailable: slot=%d reason=%s",
                    exc.detail.slot,
                    exc.detail.reason,
                )
            raise
        except WorkspaceError as exc:
            raise MailFileFailure(
                FileUnavailable(slot=slot, reason="drive_" + exc.kind)
            ) from exc
        except ValidationError as exc:
            raise MailFileFailure(
                FileUnavailable(slot=slot, reason="invalid_file")
            ) from exc
        except ValueError as exc:
            raise MailFileFailure(
                FileUnavailable(slot=slot, reason="digest_mismatch")
            ) from exc
        except (OSError, TimeoutError) as exc:
            raise MailFileFailure(
                FileUnavailable(slot=slot, reason="local_io")
            ) from exc
        return tuple(copy.file for copy in copies)

    def _stage_files(
        self, action_id: UUID, copies: list[_SourceCopy], deadline: float
    ) -> None:
        with _directory(self._stage) as root_fd:
            os.mkdir(str(action_id), mode=0o700, dir_fd=root_fd)
            try:
                with _directory(str(action_id), root_fd) as staged:
                    for copy in copies:
                        self._copy_slot(staged, copy, copy.source, deadline)
                    os.fsync(staged)
                os.fsync(root_fd)
                if time.monotonic() >= deadline:
                    raise MailFileFailure(
                        FileUnavailable(slot=copies[-1].slot, reason="local_io")
                    )
            except BaseException:
                self._discard(action_id)
                raise

    @staticmethod
    def _copy_slot(
        directory: int, copy: _SourceCopy, source: BinaryIO, deadline: float
    ) -> None:
        try:
            fd = os.open(
                str(copy.slot),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
                dir_fd=directory,
            )
            with os.fdopen(fd, "wb") as output:
                size, digest = _copy(source, output, copy.file.size_bytes, deadline)
                if (size, digest) != (copy.file.size_bytes, copy.file.sha256):
                    raise MailFileFailure(
                        FileUnavailable(slot=copy.slot, reason="digest_mismatch")
                    )
                output.flush()
                os.fsync(fd)
        except OSError as exc:
            raise MailFileFailure(
                FileUnavailable(slot=copy.slot, reason="local_io")
            ) from exc

    async def _inspect(
        self, action_id: UUID, copies: list[_SourceCopy], deadline: float
    ) -> None:
        # The Rust validator holds the GIL for the whole-file search.
        secrets = json.dumps(self._secrets).encode()
        with (
            _directory(self._stage) as root,
            _directory(str(action_id), root) as staged,
        ):
            for copy in copies:
                try:
                    async with asyncio.timeout(max(0.0, deadline - time.monotonic())):
                        with _regular(staged, str(copy.slot)) as stream:
                            worker = await asyncio.create_subprocess_exec(
                                sys.executable,
                                "-I",
                                "-m",
                                "jarvis.mail_files",
                                "_scan",
                                str(stream.fileno()),
                                str(copy.file.size_bytes),
                                copy.file.sha256,
                                env={},
                                stdin=asyncio.subprocess.PIPE,
                                stdout=asyncio.subprocess.DEVNULL,
                                stderr=asyncio.subprocess.DEVNULL,
                                pass_fds=(stream.fileno(),),
                            )
                            try:
                                await worker.communicate(secrets)
                            finally:
                                if worker.returncode is None:
                                    with suppress(ProcessLookupError):
                                        worker.kill()
                                    await finish_entered(
                                        asyncio.create_task(worker.wait())
                                    )
                    verdict = worker.returncode
                    if verdict == _SECRET_FOUND:
                        raise MailFileFailure(
                            FileUnavailable(slot=copy.slot, reason="secret")
                        )
                    if verdict == _BYTES_CHANGED:
                        raise MailFileFailure(
                            FileUnavailable(slot=copy.slot, reason="digest_mismatch")
                        )
                    if verdict != 0 or time.monotonic() >= deadline:
                        raise OSError("mail file scan failed")
                except OSError as exc:
                    raise MailFileFailure(
                        FileUnavailable(slot=copy.slot, reason="local_io")
                    ) from exc

    async def read(self, action_id: UUID, slot: int, expected: MailFile) -> bytes:
        if not 1 <= slot <= MAIL_MAX_FILES or expected.size_bytes > MAIL_MAX_BYTES:
            raise ValueError("invalid staged file contract")
        return await joined_thread(self._read, action_id, slot, expected)

    def _read(self, action_id: UUID, slot: int, expected: MailFile) -> bytes:
        try:
            with (
                _directory(self._stage) as directory,
                _directory(str(action_id), directory) as action,
                _regular(action, str(slot)) as stream,
            ):
                data = stream.read(expected.size_bytes + 1)
        except OSError as exc:
            raise MailFileFailure(
                FileUnavailable(slot=slot, reason="local_io")
            ) from exc
        if (
            len(data) != expected.size_bytes
            or hashlib.sha256(data).hexdigest() != expected.sha256
        ):
            raise MailFileFailure(FileUnavailable(slot=slot, reason="digest_mismatch"))
        return data

    def _discard(self, action_id: UUID) -> None:
        with _directory(self._stage) as directory:
            try:
                shutil.rmtree(str(action_id), dir_fd=directory)
            except FileNotFoundError:
                return
            os.fsync(directory)

    async def discard(self, action_id: UUID) -> None:
        await joined_thread(self._discard, action_id)

    async def sweep(self, needed: Collection[UUID]) -> None:
        def remove_orphans() -> None:
            with _directory(self._stage) as directory:
                for leaf in os.listdir(directory):
                    try:
                        identifier = UUID(leaf)
                    except ValueError:
                        continue
                    if leaf == str(identifier) and identifier not in needed:
                        self._discard(identifier)

        await joined_thread(remove_orphans)


def _scan(fd: int, size: int, digest: str) -> int:
    if not 0 <= size <= MAIL_MAX_BYTES:
        return _BYTES_CHANGED
    with os.fdopen(fd, "rb") as stream:
        stream.seek(0)
        data = stream.read(size + 1)
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        return _BYTES_CHANGED
    secrets = cast(list[str], json.load(sys.stdin))
    if any(secret and secret.encode() in data for secret in secrets):
        return _SECRET_FOUND
    matcher = SchemaValidator(
        core_schema.str_schema(
            pattern="(?i)" + SECRET_MARKER, regex_engine="rust-regex"
        )
    )
    return (
        _SECRET_FOUND
        if matcher.isinstance_python(data.decode("utf-8", "replace"))
        else 0
    )


def main() -> None:
    if len(sys.argv) == 5 and sys.argv[1] == "_scan":
        raise SystemExit(_scan(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]))
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("path", type=Path)
    prepare.add_argument("--name")
    args = parser.parse_args()
    try:
        result = publish_native(args.path, args.name)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"jarvis-mail-file: {exc}\n")
    print(result.model_dump_json())


if __name__ == "__main__":
    main()
