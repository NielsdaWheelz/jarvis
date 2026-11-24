"""Strict host configuration."""

from __future__ import annotations

import json


class ConfigurationError(ValueError):
    """A required setting is missing or malformed."""


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    del value
    raise ValueError("non-JSON constant")


def decode_config_json(encoded: bytes) -> object:
    """Decode a UTF-8 JSON declaration with unique fields and finite numbers."""
    return json.loads(
        encoded.decode("utf-8"),
        object_pairs_hook=_object,
        parse_constant=_invalid_constant,
    )
