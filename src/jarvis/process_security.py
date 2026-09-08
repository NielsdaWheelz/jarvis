"""Small Linux process hardening owned by the Jarvis host."""

from __future__ import annotations

import ctypes
import sys
from typing import Any

_PR_SET_DUMPABLE = 4


class ProcessContainmentDefect(RuntimeError):
    """The host could not establish its process-inspection boundary."""


def _load_libc() -> Any:
    return ctypes.CDLL(None, use_errno=True)


def deny_same_identity_process_inspection() -> None:
    """Prevent an unprivileged same-UID child from inspecting Jarvis memory."""

    if sys.platform != "linux":
        return
    libc = _load_libc()
    prctl = libc.prctl
    prctl.argtypes = (
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    )
    prctl.restype = ctypes.c_int
    if prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise ProcessContainmentDefect(
            f"could not disable process inspection: errno={error_number}"
        )


__all__ = ["ProcessContainmentDefect", "deny_same_identity_process_inspection"]
