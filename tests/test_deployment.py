from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def test_deployment_shell_programs_are_executable_and_parse() -> None:
    paths = [
        REPOSITORY / "deploy" / "activate-release",
        REPOSITORY / "deploy" / "install-release",
        REPOSITORY / "deploy" / "install-private-state",
        REPOSITORY / "deploy" / "provision-database",
        REPOSITORY / "deploy" / "verify-containment",
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
    assert "ProtectProc=ptraceable" in service
    assert "ProcSubset=pid" in service
    assert "ReadWritePaths=/var/lib/jarvis" in service
    assert "MemoryMax=3G" in service
    assert "LimitCORE=0" in service
    assert "Restart=on-failure" in service


def test_database_provisioning_splits_runtime_and_migration_authority() -> None:
    program = (REPOSITORY / "deploy" / "provision-database").read_text(encoding="utf-8")
    assert "jarvis_runtime" in program
    assert "jarvis_migrator" in program
    assert "jarvis_backup" not in program
    assert "database-runtime.env" in program
    assert "migration.env" in program
    assert 'sudo chmod 0600 "${files[@]}"' in program
    assert "REVOKE ALL ON DATABASE jarvis FROM PUBLIC" in program


def test_operator_application_commands_enter_the_immutable_release() -> None:
    activation = (REPOSITORY / "deploy" / "activate-release").read_text(
        encoding="utf-8"
    )
    assert "systemd-run" in activation
    assert "EnvironmentFile=/etc/jarvis/migration.env" in activation
    assert "EnvironmentFile=/etc/jarvis/jarvis.env" in activation
    assert "WorkingDirectory=$release" in activation


def test_private_environment_is_root_only_and_has_a_live_boundary_check() -> None:
    installer = (REPOSITORY / "deploy" / "install-private-state").read_text(
        encoding="utf-8"
    )
    verifier = (REPOSITORY / "deploy" / "verify-containment").read_text(
        encoding="utf-8"
    )
    assert 'install -m 0600 -o root -g root "$remote/jarvis.env"' in installer
    assert "root:root:600" in verifier
    assert 'if sudo -u jarvis test -r "$file"' in verifier
    assert "/proc/$pid/environ" in verifier
    assert "inspection_blocked" in verifier
