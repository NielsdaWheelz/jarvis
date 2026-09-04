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

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                value, stream, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if _descriptor_is_open(descriptor):
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def _descriptor_is_open(descriptor: int) -> bool:
    try:
        os.fstat(descriptor)
    except OSError:
        return False
    return True
