"""Offline qualification safety contracts; no provider, database, or tmux."""

import json
import sys
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

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


@pytest.mark.parametrize("matches", [False, True])
async def test_cleanup_never_kills_an_unconfirmed_or_different_terminal(
    tmp_path: Path, matches: bool
) -> None:
    # External OS executable fixture: never tmux or an internal launcher mock.
    runner = tmp_path / "synthetic-terminal-boundary"
    calls = tmp_path / "calls.jsonl"
    runner.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"with open({str(calls)!r}, 'a') as out:\n"
        "    out.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1] == 'display-message':\n"
        f"    print({('$17\t' + NAME) if matches else ('$18\t' + NAME)!r})\n"
    )
    runner.chmod(0o700)
    terminal = SimpleNamespace(tmux_session_id="$17", tmux_name=NAME)
    assert await QUALIFIER["cleanup_terminals"](str(runner), (terminal,)) is matches
    recorded = [json.loads(line) for line in calls.read_text().splitlines()]
    assert recorded[0] == [
        "display-message",
        "-p",
        "-t",
        "$17",
        "#{session_id}\t#{session_name}",
    ]
    assert recorded[1:] == ([["kill-session", "-t", "$17"]] if matches else [])


async def test_invalid_terminal_identity_fails_before_external_execution() -> None:
    with pytest.raises(ValueError, match="exact test identity"):
        await QUALIFIER["observe_terminal"]("/absent", "last", NAME)
