# pyright: reportPrivateUsage=false
from __future__ import annotations

import io
import json
import subprocess
import tarfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from jarvis import backup
from jarvis.backup import (
    BackupConfigurationError,
    BackupEnvironment,
    BackupOperationError,
    BackupPaths,
)


def _environment(tmp_path: Path) -> dict[str, str]:
    password = tmp_path / "restic-password"
    password.write_text("synthetic-restic-password\n", encoding="utf-8")
    password.chmod(0o600)
    return {
        "PGHOST": "127.0.0.1",
        "PGPORT": "5432",
        "PGDATABASE": "jarvis",
        "PGUSER": "jarvis_backup",
        "PGPASSWORD": "synthetic-database-password",
        "RESTIC_REPOSITORY": (
            "s3:https://synthetic.r2.cloudflarestorage.com/jarvis-backups/production"
        ),
        "RESTIC_PASSWORD_FILE": str(password),
        "RESTIC_CACHE_DIR": str(tmp_path / "cache"),
        "AWS_ACCESS_KEY_ID": "synthetic-backup-key",
        "AWS_SECRET_ACCESS_KEY": "synthetic-backup-secret",
    }


def _paths(tmp_path: Path) -> dict[str, str]:
    release = tmp_path / "RELEASE.json"
    release.write_text('{"commit":"' + "a" * 40 + '"}\n', encoding="utf-8")
    release.chmod(0o644)
    return {
        "JARVIS_RELEASE_METADATA_PATH": str(release),
        "JARVIS_BACKUP_CONNECTOR_STATE_PATH": str(tmp_path / "google.json"),
        "JARVIS_BACKUP_RUNTIME_STATE_DIRECTORY": str(tmp_path / "runtime"),
        "JARVIS_BACKUP_STAGING_DIRECTORY": str(tmp_path / "staging"),
    }


def _add_bytes(archive: tarfile.TarFile, name: str, value: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(value)
    info.mode = 0o600
    archive.addfile(info, io.BytesIO(value))


def _bundle(
    path: Path,
    *,
    commit: str,
    overrides: Mapping[str, bytes] | None = None,
) -> None:
    files = {
        "database.dump": b"synthetic-database-dump",
        "connectors/google-oauth-state.json": b'{"encrypted":true}\n',
        "runtime/admission.json": b'{"reservations":[]}\n',
        "runtime/paused.json": b'{"paused":false}\n',
        **({} if overrides is None else overrides),
    }
    manifest = {
        "schema_version": "jarvis-backup.v1",
        "created_at": "2026-09-07T00:00:00+00:00",
        "release_commit": commit,
        "database": {
            "postgresql": "16.15",
            "pgvector": "0.8.6",
            "timezone": "UTC",
        },
        "application_tables": [
            "action",
            "memory_log",
            "memory_summary",
            "message",
        ],
        "files": {
            name: {"bytes": len(value), "sha256": backup._sha256(value)}
            for name, value in sorted(files.items())
        },
    }
    with tarfile.open(path, "w") as archive:
        for name, value in files.items():
            _add_bytes(archive, name, value)
        _add_bytes(
            archive,
            "manifest.json",
            json.dumps(manifest, sort_keys=True).encode("utf-8"),
        )


def test_backup_environment_is_closed_and_loopback_only(tmp_path: Path) -> None:
    environment = BackupEnvironment.from_env(_environment(tmp_path))

    child = environment.subprocess_environment()
    assert set(child) == {
        "AWS_ACCESS_KEY_ID",
        "AWS_DEFAULT_REGION",
        "AWS_SECRET_ACCESS_KEY",
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "PGDATABASE",
        "PGHOST",
        "PGPASSWORD",
        "PGPORT",
        "PGUSER",
        "RESTIC_CACHE_DIR",
        "RESTIC_PASSWORD_FILE",
        "RESTIC_REPOSITORY",
        "TZ",
    }
    assert child["HOME"] == "/var/lib/jarvis"
    assert child["TZ"] == "UTC"

    unsafe = _environment(tmp_path)
    unsafe["PGHOST"] = "database.example.com"
    with pytest.raises(BackupConfigurationError, match="loopback"):
        BackupEnvironment.from_env(unsafe)


@pytest.mark.parametrize(
    "repository",
    [
        "s3:https://example.com/bucket/jarvis",
        "s3:http://synthetic.r2.cloudflarestorage.com/bucket/jarvis",
        "s3:https://synthetic.r2.cloudflarestorage.com/bucket",
        "s3:https://user:secret@synthetic.r2.cloudflarestorage.com/bucket/jarvis",
    ],
)
def test_backup_environment_rejects_non_r2_or_unscoped_repository(
    tmp_path: Path,
    repository: str,
) -> None:
    environment = _environment(tmp_path)
    environment["RESTIC_REPOSITORY"] = repository
    with pytest.raises(BackupConfigurationError, match="R2"):
        BackupEnvironment.from_env(environment)


def test_backup_paths_require_exact_release_and_absolute_paths(tmp_path: Path) -> None:
    paths = BackupPaths.from_env(_paths(tmp_path))
    assert paths.release_commit == "a" * 40

    invalid = _paths(tmp_path)
    metadata = Path(invalid["JARVIS_RELEASE_METADATA_PATH"])
    metadata.write_text('{"commit":"main"}\n', encoding="utf-8")
    with pytest.raises(BackupConfigurationError, match="full Git commit"):
        BackupPaths.from_env(invalid)


def test_bundle_verification_streams_database_and_checks_every_digest(
    tmp_path: Path,
) -> None:
    commit = "b" * 40
    bundle = tmp_path / "jarvis-v1.tar"
    extraction = tmp_path / "extract"
    extraction.mkdir()
    _bundle(bundle, commit=commit)

    restored = backup._extract_and_verify_bundle(bundle, commit, extraction)

    assert restored.database_dump.read_bytes() == b"synthetic-database-dump"
    assert "database.dump" not in restored.files
    assert restored.files["runtime/paused.json"] == b'{"paused":false}\n'


def test_bundle_verification_rejects_unexpected_paths(tmp_path: Path) -> None:
    commit = "c" * 40
    bundle = tmp_path / "jarvis-v1.tar"
    extraction = tmp_path / "extract"
    extraction.mkdir()
    _bundle(bundle, commit=commit, overrides={"../escape": b"forbidden"})

    with pytest.raises(BackupOperationError, match="unexpected file roster"):
        backup._extract_and_verify_bundle(bundle, commit, extraction)
    assert not (tmp_path / "escape").exists()


def test_bundle_verification_rejects_tampering(tmp_path: Path) -> None:
    commit = "d" * 40
    bundle = tmp_path / "jarvis-v1.tar"
    extraction = tmp_path / "extract"
    extraction.mkdir()
    _bundle(bundle, commit=commit)

    with tarfile.open(bundle, "a") as archive:
        _add_bytes(archive, "runtime/paused.json", b'{"paused":true}\n')

    with pytest.raises(BackupOperationError, match="duplicate paths"):
        backup._extract_and_verify_bundle(bundle, commit, extraction)


def test_private_json_rejects_symlinks_and_permissive_files(tmp_path: Path) -> None:
    value = tmp_path / "value.json"
    value.write_text("{}\n", encoding="utf-8")
    value.chmod(0o644)
    with pytest.raises(BackupOperationError, match="metadata is unsafe"):
        backup._safe_json_file(value, required=True)

    value.chmod(0o600)
    alias = tmp_path / "alias.json"
    alias.symlink_to(value)
    with pytest.raises(BackupOperationError):
        backup._safe_json_file(alias, required=True)


def test_create_backup_builds_checked_snapshot_without_database_buffering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = BackupEnvironment.from_env(_environment(tmp_path))
    path_environment = _paths(tmp_path)
    connector = Path(path_environment["JARVIS_BACKUP_CONNECTOR_STATE_PATH"])
    runtime = Path(path_environment["JARVIS_BACKUP_RUNTIME_STATE_DIRECTORY"])
    connector.parent.chmod(0o700)
    runtime.mkdir(mode=0o700)
    connector.write_text('{"encrypted":true}\n', encoding="utf-8")
    (runtime / "admission.json").write_text('{"reservations":[]}\n', encoding="utf-8")
    (runtime / "paused.json").write_text('{"paused":false}\n', encoding="utf-8")
    for path in (connector, runtime / "admission.json", runtime / "paused.json"):
        path.chmod(0o600)
    paths = BackupPaths.from_env(path_environment)
    observed_bundle = False

    def run(
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str],
        stdin: io.BufferedReader | None = None,
        stdout: int | io.BufferedWriter = subprocess.DEVNULL,
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal observed_bundle
        assert environment["AWS_DEFAULT_REGION"] == "auto"
        if arguments[0] == "/usr/bin/pg_dump":
            destination = Path(arguments[arguments.index("--file") + 1])
            destination.write_bytes(b"streamed-custom-dump")
            return subprocess.CompletedProcess(arguments, 0, b"", b"")
        if tuple(arguments[:2]) == ("/usr/bin/restic", "backup"):
            assert stdin is not None
            with tarfile.open(fileobj=io.BytesIO(stdin.read()), mode="r:") as archive:
                assert archive.getnames() == [
                    "database.dump",
                    "connectors/google-oauth-state.json",
                    "runtime/admission.json",
                    "runtime/paused.json",
                    "manifest.json",
                ]
                dumped = archive.extractfile("database.dump")
                assert dumped is not None
                assert dumped.read() == b"streamed-custom-dump"
            observed_bundle = True
            result = b'{"message_type":"summary","snapshot_id":"' + b"e" * 64 + b'"}\n'
            return subprocess.CompletedProcess(arguments, 0, result, b"")
        assert tuple(arguments) == ("/usr/bin/restic", "check")
        return subprocess.CompletedProcess(arguments, 0, b"", b"")

    def database_identity(_environment: BackupEnvironment) -> dict[str, str]:
        return {
            "postgresql": "16.15",
            "pgvector": "0.8.6",
            "timezone": "UTC",
        }

    monkeypatch.setattr(backup, "_run_private", run)
    monkeypatch.setattr(backup, "_database_identity", database_identity)

    assert backup.create_backup(environment, paths) == "e" * 64
    assert observed_bundle


def test_restore_verifies_bundle_and_writes_only_clean_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = BackupEnvironment.from_env(_environment(tmp_path))
    commit = "f" * 40
    source_bundle = tmp_path / "source.tar"
    _bundle(source_bundle, commit=commit)
    target = tmp_path / "target"
    staging = tmp_path / "restore-staging"
    restored_dump = False

    def run(
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str],
        stdin: io.BufferedReader | None = None,
        stdout: int | io.BufferedWriter = subprocess.DEVNULL,
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal restored_dump
        del environment, stdin
        if tuple(arguments[:2]) == ("/usr/bin/restic", "dump"):
            destination = cast(io.BufferedWriter, stdout)
            destination.write(source_bundle.read_bytes())
            return subprocess.CompletedProcess(arguments, 0, b"", b"")
        assert arguments[0] == "/usr/bin/pg_restore"
        assert Path(arguments[-1]).read_bytes() == b"synthetic-database-dump"
        restored_dump = True
        return subprocess.CompletedProcess(arguments, 0, b"", b"")

    def require_empty(_environment: BackupEnvironment) -> None:
        return None

    monkeypatch.setattr(backup, "_run_private", run)
    monkeypatch.setattr(backup, "_require_empty_migrated_database", require_empty)

    backup.restore_backup(
        environment,
        snapshot_id="1" * 64,
        release_commit=commit,
        target_state_root=target,
        staging_parent=staging,
    )

    assert restored_dump
    assert (target / "connectors" / "google-oauth-state.json").read_bytes() == (
        b'{"encrypted":true}\n'
    )
    assert (target / "runtime" / "paused.json").read_bytes() == b'{"paused":false}\n'


def test_restore_rejects_a_symlinked_state_root(
    tmp_path: Path,
) -> None:
    environment = BackupEnvironment.from_env(_environment(tmp_path))
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)

    with pytest.raises(BackupConfigurationError, match="private"):
        backup.restore_backup(
            environment,
            snapshot_id="1" * 64,
            release_commit="f" * 40,
            target_state_root=alias,
            staging_parent=tmp_path / "staging",
        )
