from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("unusable", [False, True])
def test_release_installation_verifies_final_service_identity_before_success(
    tmp_path: Path, existing: bool, unusable: bool
) -> None:
    """Execute the remote shell; external sudo/uv outcomes are the host boundary."""
    log = tmp_path / "commands.jsonl"
    sudo = tmp_path / "sudo"
    sudo.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "user = 'root'\n"
        "if args[:1] == ['-u']:\n"
        "    user, args = args[1], args[2:]\n"
        "with open(os.environ['DEPLOY_TEST_LOG'], 'a') as log:\n"
        "    log.write(json.dumps([user, args]) + '\\n')\n"
        "if args[:2] == ['test', '-e']:\n"
        "    sys.exit(0 if os.environ['DEPLOY_TEST_EXISTING'] == '1' else 1)\n"
        "if args[:1] == ['cat']:\n"
        "    print('3.12.13')\n"
        "elif args[:2] == ['python3', '-'] and len(args) == 3:\n"
        "    print('a' * 40 + '|' + 'b' * 40 + '|' + 'c' * 64)\n"
        "if user == 'jarvis' and os.environ['DEPLOY_TEST_UNUSABLE'] == '1':\n"
        "    sys.exit(126)\n",
        encoding="utf-8",
    )
    sudo.chmod(0o755)
    program = (REPOSITORY / "deploy/install-release").read_text()
    remote = program.split("<<'REMOTE'\n", 1)[1].removesuffix("REMOTE\n")
    with tempfile.NamedTemporaryFile(
        prefix="jarvis-release.", suffix=".tar", dir="/tmp", delete=False
    ) as archive:
        result = subprocess.run(
            ["bash", "-s", "--", "a" * 40, "b" * 40, "c" * 64, "niels", archive.name],
            input=remote,
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
                "DEPLOY_TEST_LOG": str(log),
                "DEPLOY_TEST_EXISTING": str(int(existing)),
                "DEPLOY_TEST_UNUSABLE": str(int(unusable)),
            },
            timeout=15,
            check=False,
        )
        Path(archive.name).unlink(missing_ok=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    service_calls = [call for call in calls if call[0] == "jarvis"]
    assert (result.returncode != 0) is unusable
    assert service_calls and service_calls[0][1][0].endswith("/.venv/bin/python")
    publication = [
        call
        for call in calls
        if (call[1][:2] == ["python3", "-"] and len(call[1]) > 3)
        or (
            call[1][0] == "install"
            and call[1][-1] == "/etc/systemd/system/jarvis.service"
        )
    ]
    if unusable:
        assert not publication
        assert "installed:" not in result.stdout
        return
    assert service_calls[1][1][-1] == "--help"
    if existing:
        assert not publication
        assert "Release already installed:" in result.stdout
        return
    install = next(call for call in calls if "--no-bin" in call[1])
    assert install[0] == "niels" and install[1][-1] == "3.12.13"
    assert "/opt/jarvis/releases/" + "a" * 40 + "/.python" in install[1]
    sync = next(call for call in calls if "sync" in call[1])
    assert "--managed-python" in sync[1] and "--no-python-downloads" in sync[1]
    assert sync[1][sync[1].index("--link-mode") + 1] == "copy"
    root_owned = next(
        call for call in calls if call[1][:3] == ["chown", "-R", "root:root"]
    )
    assert (
        calls.index(root_owned)
        < calls.index(service_calls[0])
        < calls.index(publication[0])
    )


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
    assert "systemctl reset-failed jarvis.service" in activation
    assert "SubState" in activation
    assert "NRestarts" in activation
    assert "MainPID" in activation


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
