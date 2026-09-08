from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def test_deployment_shell_programs_are_executable_and_parse() -> None:
    paths = [
        REPOSITORY / "deploy" / "activate-release",
        REPOSITORY / "deploy" / "install-backup-secrets",
        REPOSITORY / "deploy" / "install-release",
        REPOSITORY / "deploy" / "install-private-state",
        REPOSITORY / "deploy" / "initialize-backup",
        REPOSITORY / "deploy" / "provision-database",
    ]
    for path in paths:
        assert os.access(path, os.X_OK)
    subprocess.run(["bash", "-n", *paths], check=True)


def test_service_uses_immutable_release_and_least_privilege_credentials() -> None:
    service = (REPOSITORY / "deploy" / "jarvis.service").read_text(encoding="utf-8")
    assert "User=jarvis" in service
    assert "WorkingDirectory=/opt/jarvis/current" in service
    assert "ExecStart=/opt/jarvis/current/.venv/bin/jarvis serve" in service
    assert "EnvironmentFile=/etc/jarvis/database-runtime.env" in service
    assert "EnvironmentFile=/etc/jarvis/migration.env" not in service
    assert "NoNewPrivileges=true" in service
    assert "ProtectSystem=strict" in service
    assert "ReadWritePaths=/var/lib/jarvis" in service
    assert "MemoryMax=3G" in service
    assert "Restart=on-failure" in service


def test_backup_unit_is_daily_private_and_read_only_at_database_boundary() -> None:
    service = (REPOSITORY / "deploy" / "jarvis-backup.service").read_text(
        encoding="utf-8"
    )
    timer = (REPOSITORY / "deploy" / "jarvis-backup.timer").read_text(encoding="utf-8")
    assert "User=jarvis" in service
    assert "EnvironmentFile=/etc/jarvis/backup-database.env" in service
    assert "EnvironmentFile=/etc/jarvis/restore-database.env" not in service
    assert "ExecStart=/opt/jarvis/current/.venv/bin/jarvis-backup" in service
    assert "ProtectSystem=strict" in service
    assert "OnCalendar=*-*-* 04:15:00 UTC" in timer
    assert "Persistent=true" in timer


def test_database_provisioning_splits_runtime_backup_and_restore_authority() -> None:
    program = (REPOSITORY / "deploy" / "provision-database").read_text(encoding="utf-8")
    assert "jarvis_runtime" in program
    assert "jarvis_migrator" in program
    assert "jarvis_backup" in program
    assert "database-runtime.env" in program
    assert "migration.env" in program
    assert "backup-database.env" in program
    assert "restore-database.env" in program
    assert "PGUSER=jarvis_backup" in program
    assert "PGUSER=jarvis_migrator" in program
    assert "REVOKE ALL ON DATABASE jarvis FROM PUBLIC" in program
