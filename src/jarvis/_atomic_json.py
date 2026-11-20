from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast


def read_private_json(path: Path) -> Mapping[str, object] | None:
    if not path.exists():
        return None
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("private runtime state must be a mode-0600 regular file")
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("private runtime state is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError("private runtime state must be a JSON object")
    return cast("dict[str, object]", value)


def replace_private_json(path: Path, value: Mapping[str, object]) -> None:
    parent = path.parent
    if not path.is_absolute() or not parent.is_dir():
        raise ValueError("runtime-state path must be absolute with an existing parent")
    if stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise ValueError(
            "runtime-state directory must not be accessible by group or other"
        )

    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    replace_bytes(path, (encoded + "\n").encode(), 0o600)


def replace_bytes(path: Path, payload: bytes, mode: int) -> None:
    """Publish complete bytes durably in an existing directory."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
