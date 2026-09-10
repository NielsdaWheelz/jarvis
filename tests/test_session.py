from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from llm_agent_kernel import (
    SessionRefStateDefect,
    StaleSessionRef,
    StoredSessionRef,
    ThreadId,
)
from provider_runtime.agent_runtime import AgentSessionRef

from jarvis.session import AtomicSessionRefPort


def reference(native_id: str) -> AgentSessionRef:
    return AgentSessionRef(
        "agent-session-ref.v1",
        "codex",
        "sdk",
        native_id,
        "jarvis-test",
        "a" * 64,
        "b" * 64,
    )


async def test_session_reference_retains_matching_identity_and_rejects_stale_cas(
    tmp_path: Path,
) -> None:
    path = tmp_path / "session.json"
    port = AtomicSessionRefPort(path)
    thread = ThreadId("channel-1")
    fingerprint = "c" * 64

    first = await port.compare_and_set(thread, fingerprint, None, reference("one"))
    assert isinstance(first, StoredSessionRef)
    assert first.generation == 1
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert (await port.load(thread, fingerprint)).generation == 1  # type: ignore[union-attr]
    assert isinstance(
        await port.compare_and_set(thread, fingerprint, None, reference("stale")),
        StaleSessionRef,
    )

    second = await port.compare_and_set(thread, fingerprint, 1, reference("two"))
    assert isinstance(second, StoredSessionRef)
    assert second.generation == 2
    assert await AtomicSessionRefPort(path).load(thread, fingerprint) == second
    last_in_run = await port.compare_and_set(thread, fingerprint, 2, reference("three"))
    assert isinstance(last_in_run, StoredSessionRef)
    assert last_in_run.generation == 3
    assert await port.load(thread, fingerprint) == last_in_run
    assert isinstance(
        await port.compare_and_set(thread, fingerprint, None, reference("stale")),
        StaleSessionRef,
    )
    assert isinstance(
        await port.compare_and_set(thread, fingerprint, 2, reference("stale")),
        StaleSessionRef,
    )
    other = await port.compare_and_set(thread, "d" * 64, None, reference("four"))
    assert isinstance(other, StoredSessionRef)
    assert other.generation == 1
    assert await port.load(thread, fingerprint) is None


async def test_corrupt_session_reference_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")
    path.chmod(0o600)
    port = AtomicSessionRefPort(path)

    with pytest.raises(SessionRefStateDefect):
        await port.load(ThreadId("channel-1"), "c" * 64)
