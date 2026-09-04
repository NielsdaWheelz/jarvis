from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from jarvis.state import PausedState, PausedStateDefect


async def test_paused_state_is_private_durable_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "paused.json"
    PausedState.initialize(path)
    state = PausedState(path)

    assert await state.is_paused() is False
    assert await state.set_paused(True) is True
    assert await state.set_paused(True) is False
    assert await PausedState(path).is_paused() is True
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


async def test_missing_or_corrupt_pause_state_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "paused.json"
    state = PausedState(path)
    with pytest.raises(PausedStateDefect):
        await state.is_paused()

    path.write_text(json.dumps({"paused": False}), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(PausedStateDefect):
        await state.is_paused()


def test_paused_state_requires_an_absolute_path() -> None:
    with pytest.raises(ValueError):
        PausedState(Path("relative.json"))
