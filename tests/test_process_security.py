from __future__ import annotations

import ctypes

import pytest

from jarvis.process_security import (
    ProcessContainmentDefect,
    deny_same_identity_process_inspection,
)


class _Prctl:
    argtypes: object = None
    restype: object = None

    def __init__(self, result: int) -> None:
        self.result = result
        self.calls: list[tuple[int, int, int, int, int]] = []

    def __call__(
        self, first: int, second: int, third: int, fourth: int, fifth: int
    ) -> int:
        self.calls.append((first, second, third, fourth, fifth))
        return self.result


class _Libc:
    def __init__(self, prctl: _Prctl) -> None:
        self.prctl = prctl


def test_non_linux_process_hardening_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jarvis.process_security.sys.platform", "darwin")
    monkeypatch.setattr(
        "jarvis.process_security._load_libc",
        lambda: pytest.fail("libc must not be loaded"),
    )

    deny_same_identity_process_inspection()


def test_linux_process_hardening_disables_dumpability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prctl = _Prctl(0)
    monkeypatch.setattr("jarvis.process_security.sys.platform", "linux")
    monkeypatch.setattr("jarvis.process_security._load_libc", lambda: _Libc(prctl))

    deny_same_identity_process_inspection()

    assert prctl.calls == [(4, 0, 0, 0, 0)]
    assert prctl.argtypes == (
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    )
    assert prctl.restype is ctypes.c_int


def test_linux_process_hardening_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jarvis.process_security.sys.platform", "linux")
    monkeypatch.setattr("jarvis.process_security._load_libc", lambda: _Libc(_Prctl(-1)))
    monkeypatch.setattr("jarvis.process_security.ctypes.get_errno", lambda: 1)

    with pytest.raises(ProcessContainmentDefect, match="errno=1"):
        deny_same_identity_process_inspection()
