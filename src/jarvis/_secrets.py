"""One marker expression for request arguments and outgoing file inspection."""

from __future__ import annotations

import re
from typing import cast
from urllib.parse import unquote, unquote_plus

SECRET_MARKER = (
    r"(?:"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b(?:api[\s_-]*key|access[\s_-]*token|refresh[\s_-]*token|password|secret)"
    r"\s*[=:]\s*\S+"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"
    r"|\b(?:sk|gh[opusr]|xox[baprs])[-_][A-Za-z0-9_-]{16,}"
    r"|\bAIza[A-Za-z0-9_-]{20,}"
    r"|\bjmem_[A-Za-z0-9_-]{16,}"
    r"|\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"
    r")"
)
_SECRET_PATTERN = re.compile(SECRET_MARKER, re.IGNORECASE)


def contains_secret(value: object, host_secrets: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        pending = [value]
        seen: set[str] = set()
        while pending:
            candidate = pending.pop()
            if candidate in seen:
                continue
            seen.add(candidate)
            if any(secret and secret in candidate for secret in host_secrets):
                return True
            if _SECRET_PATTERN.search(candidate) is not None:
                return True
            pending.extend((unquote(candidate), unquote_plus(candidate)))
        return False
    if isinstance(value, dict):
        return any(
            contains_secret(item, host_secrets)
            for item in cast("dict[object, object]", value).values()
        )
    if isinstance(value, list):
        return any(
            contains_secret(item, host_secrets) for item in cast("list[object]", value)
        )
    return False
