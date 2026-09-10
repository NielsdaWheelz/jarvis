"""Offline qualification safety contracts; no provider, database, or tmux."""

import json
import sys
from pathlib import Path
from runpy import run_path

import pytest

QUALIFIER = run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/qualify_codex_control.py")
)
SOCKET = "jarvis-codex-qualify-" + "a" * 32
NAME = "jarvis-qualify-" + "a" * 32 + "-personal"


def test_isolated_runner_refuses_default_or_reused_nonspecific_socket_names() -> None:
    for name in ("", "default", "production", "jarvis-codex-qualify", "../socket"):
        with pytest.raises(ValueError, match="isolated"):
            QUALIFIER["isolated_runner_source"](Path("/usr/bin/tmux"), name)


def test_opt_in_requires_all_three_boundaries_before_preparation_or_imports(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "provider_runtime", None)
    for args in (
        [],
        ["--allow-provider-calls"],
        ["--allow-provider-calls", "--allow-isolated-tmux-mutation"],
    ):
        assert QUALIFIER["main"](args) == 2
        assert json.loads(capsys.readouterr().out) == {
            "status": "NOT_RUN",
            "reason": "explicit_opt_in_required",
        }


def test_preparation_rejects_wrong_runner_or_non_disposable_database() -> None:
    tmux = Path("/usr/bin/tmux")
    runner = QUALIFIER["isolated_runner_source"](tmux, SOCKET)
    database = "postgresql+psycopg://user:synthetic@127.0.0.1/jarvis_codex_qualify_test"
    QUALIFIER["validate_preparation"](
        runner=runner,
        tmux=tmux,
        socket_name=SOCKET,
        launcher_socket=Path("/run") / SOCKET / "launcher.sock",
        database_url=database,
    )
    for changed_runner, changed_database in (
        (b'#!/bin/sh\nexec /usr/bin/tmux "$@"\n', database),
        (runner, database.replace("jarvis_codex_qualify_test", "jarvis")),
        (runner, database.replace("127.0.0.1", "production.invalid")),
    ):
        with pytest.raises(ValueError):
            QUALIFIER["validate_preparation"](
                runner=changed_runner,
                tmux=tmux,
                socket_name=SOCKET,
                launcher_socket=Path("/run") / SOCKET / "launcher.sock",
                database_url=changed_database,
            )
    with pytest.raises(ValueError, match="launcher socket"):
        QUALIFIER["validate_preparation"](
            runner=runner,
            tmux=tmux,
            socket_name=SOCKET,
            launcher_socket=Path("/run/codex-shared/launcher.sock"),
            database_url=database,
        )


def test_gateway_configuration_rejects_nonfixture_routes_and_bad_identity() -> None:
    valid = {
        "url": "http://127.0.0.1:17341",
        "machine_handle": "mh-" + "b" * 32,
        "bearer": "A" * 43,
    }
    QUALIFIER["Gateway"](json.dumps(valid).encode())
    for change in (
        {"url": "http://127.0.0.1:7341"},
        {"url": "https://production.invalid:17341"},
        {"url": "http://localhost:17341"},
        {"url": "http://127.0.0.1:17341/path"},
        {"url": "http://user@127.0.0.1:17341"},
        {"machine_handle": "default"},
        {"bearer": "not a bearer"},
        {"unexpected": True},
    ):
        with pytest.raises(ValueError):
            QUALIFIER["Gateway"](json.dumps(valid | change).encode())


async def test_invalid_terminal_identity_fails_before_external_execution() -> None:
    with pytest.raises(ValueError, match="exact test identity"):
        await QUALIFIER["observe_terminal"]("/absent", "last", NAME)
