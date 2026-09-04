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

from jarvis.definitions import session_generation_limit
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


async def test_session_reference_cas_rotation_and_generation_bound(
    tmp_path: Path,
) -> None:
    path = tmp_path / "session.json"
    port = AtomicSessionRefPort(path, max_generations=2)
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
    assert await port.load(thread, fingerprint) is None
    assert await port.load_for_discard(thread, fingerprint) == second

    # A run admitted below the boundary may finish its remaining bounded turns.
    # The following acquisition still rotates rather than parking that live run.
    last_in_run = await port.compare_and_set(thread, fingerprint, 2, reference("three"))
    assert isinstance(last_in_run, StoredSessionRef)
    assert last_in_run.generation == 3
    rotated = await port.compare_and_set(thread, fingerprint, None, reference("three"))
    assert isinstance(rotated, StoredSessionRef)
    assert rotated.generation == 1
    other = await port.compare_and_set(thread, "d" * 64, None, reference("four"))
    assert isinstance(other, StoredSessionRef)
    assert other.generation == 1
    assert await port.load(thread, fingerprint) is None


async def test_corrupt_session_reference_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")
    path.chmod(0o600)
    port = AtomicSessionRefPort(path, max_generations=2)

    with pytest.raises(SessionRefStateDefect):
        await port.load(ThreadId("channel-1"), "c" * 64)


async def test_qualified_generation_boundary_rotates_before_fifth_run(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bounded-session.json"
    port = AtomicSessionRefPort(
        path,
        max_generations=session_generation_limit("gpt-5.4"),
    )
    thread = ThreadId("channel-1")
    fingerprint = "c" * 64
    expected: int | None = None
    for generation in range(1, 5):
        stored = await port.compare_and_set(
            thread,
            fingerprint,
            expected,
            reference(f"run-{generation}"),
        )
        assert isinstance(stored, StoredSessionRef)
        expected = stored.generation
        if generation < 4:
            assert await port.load(thread, fingerprint) == stored

    assert await port.load(thread, fingerprint) is None
    rotated = await port.compare_and_set(
        thread,
        fingerprint,
        None,
        reference("run-5-cold"),
    )
    assert isinstance(rotated, StoredSessionRef)
    assert rotated.generation == 1
