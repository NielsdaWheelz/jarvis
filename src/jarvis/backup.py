"""Encrypted off-host backup and clean-database restore entry points."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Self, TypedDict, cast
from urllib.parse import urlsplit

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

_APPLICATION_TABLES: Final[tuple[str, ...]] = (
    "action",
    "memory_log",
    "memory_summary",
    "message",
)
_OPTIONAL_STATE_FILES: Final[tuple[str, ...]] = ("session-ref.json",)
_REQUIRED_STATE_FILES: Final[tuple[str, ...]] = (
    "admission.json",
    "paused.json",
)
_BUNDLE_NAME: Final[str] = "jarvis-v1.tar"
_BUNDLE_PATH: Final[str] = f"/{_BUNDLE_NAME}"
_MAX_STATE_FILE_BYTES: Final[int] = 16 * 1024 * 1024
_MAX_DATABASE_DUMP_BYTES: Final[int] = 128 * 1024 * 1024 * 1024
_COPY_CHUNK_BYTES: Final[int] = 1024 * 1024
_SAFE_NAME = re.compile(r"[a-z][a-z0-9_]{0,62}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SNAPSHOT = re.compile(r"[0-9a-f]{64}")


class _FileIdentity(TypedDict):
    bytes: int
    sha256: str


class BackupConfigurationError(ValueError):
    """Backup configuration is missing or unsafe."""


class BackupOperationError(RuntimeError):
    """A backup or restore operation failed without exposing private output."""


def _required(source: Mapping[str, str], name: str) -> str:
    value = source.get(name)
    if value is None or not value or "\x00" in value or "\n" in value:
        raise BackupConfigurationError(f"missing or malformed setting: {name}")
    return value


def _absolute_path(source: Mapping[str, str], name: str) -> Path:
    path = Path(_required(source, name))
    if not path.is_absolute() or path != Path(os.path.normpath(path)):
        raise BackupConfigurationError(f"{name} must be a normalized absolute path")
    return path


def _safe_database_name(source: Mapping[str, str], name: str) -> str:
    value = _required(source, name)
    if _SAFE_NAME.fullmatch(value) is None:
        raise BackupConfigurationError(f"{name} must be a safe PostgreSQL name")
    return value


def _validate_repository(value: str) -> str:
    if not value.startswith("s3:https://"):
        raise BackupConfigurationError(
            "RESTIC_REPOSITORY must use the Cloudflare R2 HTTPS S3 endpoint"
        )
    parsed = urlsplit(value[3:])
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.hostname is None
        or not parsed.hostname.endswith(".r2.cloudflarestorage.com")
        or len(parsed.path.strip("/").split("/")) < 2
        or parsed.query
        or parsed.fragment
    ):
        raise BackupConfigurationError(
            "RESTIC_REPOSITORY must name an R2 bucket and Jarvis-only prefix"
        )
    return value


@dataclass(frozen=True, slots=True, repr=False)
class BackupEnvironment:
    """The least-authority environment shared by backup and restore."""

    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str
    restic_repository: str
    restic_password_file: Path
    restic_cache_directory: Path
    aws_access_key_id: str
    aws_secret_access_key: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        source = os.environ if environ is None else environ
        host = _required(source, "PGHOST")
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise BackupConfigurationError("PGHOST must be loopback")
        try:
            port = int(_required(source, "PGPORT"))
        except ValueError as exc:
            raise BackupConfigurationError("PGPORT must be 5432") from exc
        if port != 5432:
            raise BackupConfigurationError("PGPORT must be 5432")
        password_file = _absolute_path(source, "RESTIC_PASSWORD_FILE")
        cache = _absolute_path(source, "RESTIC_CACHE_DIR")
        return cls(
            pg_host=host,
            pg_port=port,
            pg_database=_safe_database_name(source, "PGDATABASE"),
            pg_user=_safe_database_name(source, "PGUSER"),
            pg_password=_required(source, "PGPASSWORD"),
            restic_repository=_validate_repository(
                _required(source, "RESTIC_REPOSITORY")
            ),
            restic_password_file=password_file,
            restic_cache_directory=cache,
            aws_access_key_id=_required(source, "AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=_required(source, "AWS_SECRET_ACCESS_KEY"),
        )

    def subprocess_environment(self) -> dict[str, str]:
        """Return the closed environment passed to pg/restic children."""

        return {
            "AWS_ACCESS_KEY_ID": self.aws_access_key_id,
            "AWS_DEFAULT_REGION": "auto",
            "AWS_SECRET_ACCESS_KEY": self.aws_secret_access_key,
            "HOME": "/var/lib/jarvis",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "PGDATABASE": self.pg_database,
            "PGHOST": self.pg_host,
            "PGPASSWORD": self.pg_password,
            "PGPORT": str(self.pg_port),
            "PGUSER": self.pg_user,
            "RESTIC_CACHE_DIR": str(self.restic_cache_directory),
            "RESTIC_PASSWORD_FILE": str(self.restic_password_file),
            "RESTIC_REPOSITORY": self.restic_repository,
            "TZ": "UTC",
        }

    def connection_info(self) -> str:
        return make_conninfo(
            host=self.pg_host,
            port=self.pg_port,
            dbname=self.pg_database,
            user=self.pg_user,
            password=self.pg_password,
            connect_timeout=10,
        )


@dataclass(frozen=True, slots=True)
class BackupPaths:
    release_commit: str
    connector_state: Path
    runtime_state: Path
    staging_parent: Path

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        source = os.environ if environ is None else environ
        commit = _release_commit(_absolute_path(source, "JARVIS_RELEASE_METADATA_PATH"))
        return cls(
            release_commit=commit,
            connector_state=_absolute_path(
                source, "JARVIS_BACKUP_CONNECTOR_STATE_PATH"
            ),
            runtime_state=_absolute_path(
                source, "JARVIS_BACKUP_RUNTIME_STATE_DIRECTORY"
            ),
            staging_parent=_absolute_path(source, "JARVIS_BACKUP_STAGING_DIRECTORY"),
        )


def _release_commit(path: Path) -> str:
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or metadata.st_size > 16 * 1024
        ):
            raise BackupConfigurationError("release metadata is unsafe")
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupConfigurationError("release metadata is unavailable") from exc
    if not isinstance(value, dict):
        raise BackupConfigurationError("release metadata is malformed")
    fields = cast(Mapping[str, object], value)
    commit = fields.get("commit")
    if not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None:
        raise BackupConfigurationError("release metadata has no full Git commit")
    return commit


def _private_directory(path: Path, *, create: bool = False) -> None:
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)
    try:
        value = path.lstat()
    except OSError as exc:
        raise BackupConfigurationError(
            "private backup directory is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(value.st_mode)
        or stat.S_IMODE(value.st_mode) & 0o077
        or value.st_uid != os.geteuid()
    ):
        raise BackupConfigurationError(
            "backup directories must be private and owned by the executing account"
        )


def _private_credential_file(path: Path) -> None:
    try:
        value = path.lstat()
    except OSError as exc:
        raise BackupConfigurationError("backup credential file is unavailable") from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid not in {0, os.geteuid()}
        or value.st_nlink != 1
        or stat.S_IMODE(value.st_mode) & 0o027
    ):
        raise BackupConfigurationError("backup credential file metadata is unsafe")


def _safe_json_file(path: Path, *, required: bool) -> bytes | None:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        if not required:
            return None
        raise BackupOperationError("required backup state is absent") from None
    except OSError as exc:
        raise BackupOperationError("backup state could not be opened") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) & 0o077
        ):
            raise BackupOperationError("backup state file metadata is unsafe")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(_MAX_STATE_FILE_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(data) > _MAX_STATE_FILE_BYTES:
        raise BackupOperationError("backup state file exceeds its bound")
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupOperationError("backup state file is not canonical JSON") from exc
    if not isinstance(value, dict):
        raise BackupOperationError("backup state file must contain one JSON object")
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_identity(path: Path, *, maximum_bytes: int) -> _FileIdentity:
    try:
        value = path.lstat()
        if (
            not stat.S_ISREG(value.st_mode)
            or value.st_uid != os.geteuid()
            or value.st_nlink != 1
            or value.st_size <= 0
            or value.st_size > maximum_bytes
        ):
            raise BackupOperationError("backup file metadata is unsafe")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(_COPY_CHUNK_BYTES):
                size += len(chunk)
                if size > maximum_bytes:
                    raise BackupOperationError("backup file exceeds its bound")
                digest.update(chunk)
    except OSError as exc:
        raise BackupOperationError("backup file could not be read") from exc
    if size != value.st_size:
        raise BackupOperationError("backup file changed while it was read")
    return {"bytes": size, "sha256": digest.hexdigest()}


def _database_identity(environment: BackupEnvironment) -> dict[str, str]:
    try:
        with psycopg.connect(environment.connection_info()) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            server_version = connection.execute(
                "SELECT current_setting('server_version')"
            ).fetchone()
            timezone = connection.execute(
                "SELECT current_setting('TimeZone')"
            ).fetchone()
            vector = connection.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
            tables = connection.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            ).fetchall()
    except psycopg.Error as exc:
        raise BackupOperationError("database identity could not be verified") from exc
    if server_version is None or timezone is None or vector is None:
        raise BackupOperationError("database identity is incomplete")
    if timezone[0] != "UTC" or not str(server_version[0]).startswith("16."):
        raise BackupOperationError("database deployment identity is incompatible")
    if tuple(row[0] for row in tables) != _APPLICATION_TABLES:
        raise BackupOperationError("database application-table roster is incompatible")
    return {
        "postgresql": str(server_version[0]),
        "pgvector": str(vector[0]),
        "timezone": str(timezone[0]),
    }


def _run_private(
    arguments: Sequence[str],
    *,
    environment: Mapping[str, str],
    stdin: io.BufferedReader | None = None,
    stdout: int | io.BufferedWriter = subprocess.DEVNULL,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            tuple(arguments),
            check=True,
            env=dict(environment),
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BackupOperationError("private backup subprocess failed") from exc


def _tar_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o600
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    archive.addfile(info, io.BytesIO(data))


def _tar_file(archive: tarfile.TarFile, name: str, path: Path) -> None:
    identity = _file_identity(path, maximum_bytes=_MAX_DATABASE_DUMP_BYTES)
    info = tarfile.TarInfo(name)
    info.size = identity["bytes"]
    info.mode = 0o600
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    with path.open("rb") as stream:
        archive.addfile(info, stream)


def create_backup(
    environment: BackupEnvironment,
    paths: BackupPaths,
) -> str:
    """Create one checked Restic snapshot and return its immutable ID."""

    _private_directory(paths.staging_parent, create=True)
    _private_directory(environment.restic_cache_directory, create=True)
    _private_credential_file(environment.restic_password_file)
    _private_directory(paths.connector_state.parent)
    _private_directory(paths.runtime_state)
    connector = _safe_json_file(paths.connector_state, required=True)
    assert connector is not None
    state: dict[str, bytes] = {}
    for name in _REQUIRED_STATE_FILES:
        value = _safe_json_file(paths.runtime_state / name, required=True)
        assert value is not None
        state[name] = value
    for name in _OPTIONAL_STATE_FILES:
        value = _safe_json_file(paths.runtime_state / name, required=False)
        if value is not None:
            state[name] = value

    process_environment = environment.subprocess_environment()
    identity = _database_identity(environment)
    with tempfile.TemporaryDirectory(
        prefix="snapshot-",
        dir=paths.staging_parent,
    ) as temporary:
        root = Path(temporary)
        dump = root / "database.dump"
        _run_private(
            (
                "/usr/bin/pg_dump",
                "--data-only",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(dump),
                *(
                    argument
                    for table in _APPLICATION_TABLES
                    for argument in ("--table", f"public.{table}")
                ),
            ),
            environment=process_environment,
        )
        files: dict[str, bytes] = {
            "connectors/google-oauth-state.json": connector,
            **{f"runtime/{name}": value for name, value in state.items()},
        }
        dump_identity = _file_identity(
            dump,
            maximum_bytes=_MAX_DATABASE_DUMP_BYTES,
        )
        manifest = {
            "schema_version": "jarvis-backup.v1",
            "created_at": datetime.now(UTC).isoformat(),
            "release_commit": paths.release_commit,
            "database": identity,
            "application_tables": list(_APPLICATION_TABLES),
            "files": {
                "database.dump": dump_identity,
                **{
                    name: {"bytes": len(value), "sha256": _sha256(value)}
                    for name, value in sorted(files.items())
                },
            },
        }
        bundle = root / _BUNDLE_NAME
        with tarfile.open(bundle, mode="w", format=tarfile.PAX_FORMAT) as archive:
            _tar_file(archive, "database.dump", dump)
            for name, value in sorted(files.items()):
                _tar_bytes(archive, name, value)
            _tar_bytes(
                archive,
                "manifest.json",
                json.dumps(
                    manifest,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n",
            )
        with bundle.open("rb") as stream:
            result = _run_private(
                (
                    "/usr/bin/restic",
                    "backup",
                    "--stdin",
                    "--stdin-filename",
                    _BUNDLE_NAME,
                    "--host",
                    "dev-server",
                    "--tag",
                    "jarvis-v1",
                    "--json",
                ),
                environment=process_environment,
                stdin=stream,
                stdout=subprocess.PIPE,
            )
    if len(result.stdout) > 1024 * 1024:
        raise BackupOperationError("restic result exceeded its bound")
    snapshot_id: str | None = None
    for raw_line in result.stdout.splitlines():
        try:
            record: object = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise BackupOperationError("restic returned malformed status") from exc
        if isinstance(record, dict):
            record_fields = cast(Mapping[str, object], record)
        else:
            continue
        if record_fields.get("message_type") == "summary":
            candidate = record_fields.get("snapshot_id")
            if isinstance(candidate, str) and _SNAPSHOT.fullmatch(candidate):
                snapshot_id = candidate
    if snapshot_id is None:
        raise BackupOperationError("restic did not return a snapshot identity")
    _run_private(
        ("/usr/bin/restic", "check"),
        environment=process_environment,
    )
    return snapshot_id


@dataclass(frozen=True, slots=True)
class _RestoredBundle:
    manifest: dict[str, object]
    files: dict[str, bytes]
    database_dump: Path


def _extract_and_verify_bundle(
    bundle: Path,
    release_commit: str,
    extraction_root: Path,
) -> _RestoredBundle:
    expected_names = {
        "database.dump",
        "manifest.json",
        "connectors/google-oauth-state.json",
        *(f"runtime/{name}" for name in _REQUIRED_STATE_FILES),
    }
    allowed_names = expected_names | {
        *(f"runtime/{name}" for name in _OPTIONAL_STATE_FILES),
    }
    files: dict[str, bytes] = {}
    try:
        with tarfile.open(bundle, mode="r:") as archive:
            members = archive.getmembers()
            names = {member.name for member in members}
            if not expected_names <= names or not names <= allowed_names:
                raise BackupOperationError(
                    "backup bundle has an unexpected file roster"
                )
            if len(names) != len(members):
                raise BackupOperationError("backup bundle has duplicate paths")
            for member in members:
                maximum = (
                    _MAX_DATABASE_DUMP_BYTES
                    if member.name == "database.dump"
                    else _MAX_STATE_FILE_BYTES
                )
                if not member.isfile() or member.size < 0 or member.size > maximum:
                    raise BackupOperationError("backup bundle member is unsafe")
                stream = archive.extractfile(member)
                if stream is None:
                    raise BackupOperationError("backup bundle member is unreadable")
                if member.name == "database.dump":
                    database_dump = extraction_root / "database.dump"
                    descriptor = os.open(
                        database_dump,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                        0o600,
                    )
                    try:
                        with os.fdopen(descriptor, "wb", closefd=False) as output:
                            remaining = member.size
                            while remaining:
                                chunk = stream.read(min(_COPY_CHUNK_BYTES, remaining))
                                if not chunk:
                                    raise BackupOperationError(
                                        "database dump ended before its declared size"
                                    )
                                output.write(chunk)
                                remaining -= len(chunk)
                            if stream.read(1):
                                raise BackupOperationError(
                                    "database dump exceeded its declared size"
                                )
                            output.flush()
                            os.fsync(output.fileno())
                    finally:
                        os.close(descriptor)
                else:
                    data = stream.read(member.size + 1)
                    if len(data) != member.size:
                        raise BackupOperationError(
                            "backup bundle member size is inconsistent"
                        )
                    files[member.name] = data
    except (OSError, tarfile.TarError) as exc:
        raise BackupOperationError("backup bundle is invalid") from exc
    database_dump = extraction_root / "database.dump"
    try:
        manifest_value: object = json.loads(files.pop("manifest.json"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupOperationError("backup manifest is invalid") from exc
    if not isinstance(manifest_value, dict):
        raise BackupOperationError("backup manifest must be an object")
    untyped_manifest = cast(Mapping[object, object], manifest_value)
    if not all(isinstance(key, str) for key in untyped_manifest):
        raise BackupOperationError("backup manifest must use string keys")
    manifest = dict(cast(Mapping[str, object], manifest_value))
    if (
        manifest.get("schema_version") != "jarvis-backup.v1"
        or manifest.get("release_commit") != release_commit
        or manifest.get("application_tables") != list(_APPLICATION_TABLES)
    ):
        raise BackupOperationError("backup manifest is incompatible")
    declared = manifest.get("files")
    restored_names = {"database.dump", *files}
    if not isinstance(declared, dict):
        raise BackupOperationError("backup file manifest is incomplete")
    untyped_declared = cast(Mapping[object, object], declared)
    if not all(isinstance(key, str) for key in untyped_declared):
        raise BackupOperationError("backup file manifest is incomplete")
    declared_files = cast(Mapping[str, object], declared)
    if set(declared_files) != restored_names:
        raise BackupOperationError("backup file manifest is incomplete")
    for name, data in files.items():
        entry = declared_files.get(name)
        if not isinstance(entry, dict) or entry != {
            "bytes": len(data),
            "sha256": _sha256(data),
        }:
            raise BackupOperationError("backup file digest is invalid")
    if declared_files.get("database.dump") != _file_identity(
        database_dump,
        maximum_bytes=_MAX_DATABASE_DUMP_BYTES,
    ):
        raise BackupOperationError("database dump digest is invalid")
    return _RestoredBundle(manifest, files, database_dump)


def _require_empty_migrated_database(environment: BackupEnvironment) -> None:
    try:
        with psycopg.connect(environment.connection_info()) as connection:
            rows = connection.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            ).fetchall()
            names = tuple(row[0] for row in rows)
            if names != _APPLICATION_TABLES:
                raise BackupOperationError(
                    "restore database must contain the exact migrated tables"
                )
            for table in _APPLICATION_TABLES:
                count = connection.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                ).fetchone()
                if count is None or count[0] != 0:
                    raise BackupOperationError("restore database is not empty")
    except psycopg.Error as exc:
        raise BackupOperationError("restore database could not be verified") from exc


def restore_backup(
    environment: BackupEnvironment,
    *,
    snapshot_id: str,
    release_commit: str,
    target_state_root: Path,
    staging_parent: Path,
) -> None:
    """Restore one exact snapshot into an empty migrated database and state root."""

    if _SNAPSHOT.fullmatch(snapshot_id) is None:
        raise BackupConfigurationError("snapshot ID must be 64 lowercase hex bytes")
    if _COMMIT.fullmatch(release_commit) is None:
        raise BackupConfigurationError("release commit must be a full Git commit")
    for path, name in (
        (target_state_root, "target state root"),
        (staging_parent, "restore staging directory"),
    ):
        if not path.is_absolute() or path != Path(os.path.normpath(path)):
            raise BackupConfigurationError(f"{name} must be a normalized absolute path")
    _private_directory(staging_parent, create=True)
    _private_directory(environment.restic_cache_directory, create=True)
    _private_credential_file(environment.restic_password_file)
    connectors_target = target_state_root / "connectors"
    runtime_target = target_state_root / "runtime"
    if connectors_target.exists() or runtime_target.exists():
        raise BackupOperationError("restore state target is not clean")
    process_environment = environment.subprocess_environment()
    with tempfile.TemporaryDirectory(
        prefix="restore-", dir=staging_parent
    ) as temporary:
        root = Path(temporary)
        bundle = root / _BUNDLE_NAME
        with bundle.open("wb") as output:
            _run_private(
                (
                    "/usr/bin/restic",
                    "dump",
                    snapshot_id,
                    _BUNDLE_PATH,
                ),
                environment=process_environment,
                stdout=output,
            )
        restored = _extract_and_verify_bundle(bundle, release_commit, root)
        _require_empty_migrated_database(environment)
        _run_private(
            (
                "/usr/bin/pg_restore",
                "--data-only",
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                environment.pg_database,
                str(restored.database_dump),
            ),
            environment=process_environment,
        )
        connectors_target.mkdir(mode=0o700, parents=True)
        runtime_target.mkdir(mode=0o700)
        targets = {
            "connectors/google-oauth-state.json": (
                connectors_target / "google-oauth-state.json"
            ),
            **{
                f"runtime/{name}": runtime_target / name
                for name in (*_REQUIRED_STATE_FILES, *_OPTIONAL_STATE_FILES)
            },
        }
        for name, target in targets.items():
            value = restored.files.get(name)
            if value is None:
                continue
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(value)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                os.close(descriptor)


def backup_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis-backup")
    parser.parse_args(argv)
    try:
        snapshot = create_backup(
            BackupEnvironment.from_env(),
            BackupPaths.from_env(),
        )
    except (BackupConfigurationError, BackupOperationError) as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Backup completed: snapshot={snapshot}.")
    return 0


def restore_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis-restore")
    parser.add_argument("snapshot_id")
    arguments = parser.parse_args(argv)
    source = os.environ
    try:
        restore_backup(
            BackupEnvironment.from_env(source),
            snapshot_id=arguments.snapshot_id,
            release_commit=_required(source, "JARVIS_RELEASE_COMMIT"),
            target_state_root=_absolute_path(source, "JARVIS_RESTORE_STATE_ROOT"),
            staging_parent=_absolute_path(source, "JARVIS_RESTORE_STAGING_DIRECTORY"),
        )
    except (BackupConfigurationError, BackupOperationError) as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        return 1
    print(f"Restore completed: snapshot={arguments.snapshot_id}.")
    return 0


__all__ = [
    "BackupConfigurationError",
    "BackupEnvironment",
    "BackupOperationError",
    "BackupPaths",
    "backup_main",
    "create_backup",
    "restore_backup",
    "restore_main",
]
