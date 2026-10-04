"""Temporary production-helper composition with controlled loaded-unit facts.

Run .venv/bin/python tests/native_acceptance/prune_host_probe.py. All files and
deletions are confined to fresh temporary roots; no host or provider calls.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

helper = Path("deploy/release-functions").read_text()
checks: dict[str, bool] = {}
for label, host, candidate, allowed in (
    ("active-unretained-host-refuses-before-deletion", "c", "", False),
    ("active-selected-host-allows-prune", "a", "", True),
    ("active-candidate-host-allows-prune", "b", "b", True),
    ("fully-stopped-host-allows-prune", "", "", True),
):
    root = Path(tempfile.mkdtemp(prefix="jarvis-prune-host-")).resolve()
    releases = root / "releases"
    for suffix in ("a", "b", "c"):
        directory = releases / (suffix * 40)
        directory.mkdir(parents=True)
        (directory / "RELEASE.json").write_text("{}")
    (root / "current").symlink_to("releases/" + "a" * 40)
    executable = str(releases / (host * 40) / ".venv/bin/python")
    property_value = json.dumps(
        {
            "type": "a(sasbttttuii)",
            "data": [
                [
                    executable,
                    [
                        executable,
                        str(releases / (host * 40) / "deploy/codex-host"),
                        "start",
                    ],
                ]
            ],
        }
    )
    script = """set -euo pipefail
readlink() {
  "$PROOF_PYTHON" -c 'from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve(strict=True))' "$2"
}
systemctl() {
  case "$*" in
    *jarvis-codex-contained.service*)
      case "$*" in
        *ActiveState*) printf '%s\\n' "$HOST_STATE" ;;
        *MainPID*) printf '%s\\n' "$HOST_PID" ;;
        *ControlPID*) printf '0\\n' ;;
        *) return 1 ;;
      esac ;;
    *jarvis.service*) printf '0\\n' ;;
    *) return 1 ;;
  esac
}
busctl() { printf '%s\\n' "$HOST_EXEC"; }
"""
    script += helper.replace("/opt/jarvis", str(root))
    script += '\nprune_releases "$CANDIDATE"\n'
    result = subprocess.run(
        ["bash", "-s"],
        input=script,
        text=True,
        capture_output=True,
        env={
            "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
            "PROOF_PYTHON": str(Path(".venv/bin/python").resolve()),
            "HOST_STATE": "active" if host else "inactive",
            "HOST_PID": "1234" if host else "0",
            "HOST_EXEC": property_value,
            "CANDIDATE": candidate * 40,
        },
    )
    retained = {item.name for item in releases.iterdir()}
    expected = (
        {"a" * 40, *(set() if not candidate else {candidate * 40})}
        if allowed
        else {suffix * 40 for suffix in ("a", "b", "c")}
    )
    checks[label] = (result.returncode == 0) == allowed and retained == expected
    if not checks[label]:
        print("RED", label, result.returncode, result.stderr, retained)

capture_root = Path(tempfile.mkdtemp(prefix="jarvis-contained-install-capture-"))
captured = capture_root / "ssh.json"
mapping = capture_root / "host.json"
mapping.write_text("{}")
ssh = capture_root / "ssh"
ssh.write_text(
    "#!" + sys.executable + "\n"
    "import json, os, sys\n"
    "from pathlib import Path\n"
    "if 'mktemp' in sys.argv:\n"
    " print('/tmp/jarvis-contained-host.proof')\n"
    "else:\n"
    " Path(os.environ['PROOF_CAPTURE']).write_text("
    "json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read()}))\n"
)
ssh.chmod(0o755)
scp = capture_root / "scp"
scp.write_text("#!/bin/sh\nexit 0\n")
scp.chmod(0o755)
result = subprocess.run(
    ["bash", "deploy/install-contained-host", "a" * 40],
    text=True,
    capture_output=True,
    env={
        **os.environ,
        "PATH": str(capture_root) + ":/usr/bin:/bin",
        "JARVIS_SOURCE_CODEX_HOST_CONFIG": str(mapping),
        "PROOF_CAPTURE": str(captured),
    },
)
command = json.loads(captured.read_text())["argv"]
checks["contained-host-install-shares-release-lock"] = result.returncode == 0 and (
    command[1:6] == ["sudo", "flock", "/opt/jarvis/.deploy.lock", "bash", "-s"]
)
artifact = Path(tempfile.mkdtemp(prefix="jarvis-prune-host-receipt-")) / "receipt.json"
artifact.write_text(
    json.dumps(
        {
            "kind": "production-shell-helper-controlled-loaded-unit",
            "provider_calls": 0,
            "host_calls": 0,
            "helper_sha256": sha256(helper.encode()).hexdigest(),
            "checks": checks,
        },
        indent=2,
    )
)
print(artifact, json.dumps(checks))
assert all(checks.values()), checks
