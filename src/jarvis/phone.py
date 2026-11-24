"""The owner-selected Firebase delivery address, independent of backups."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    field_validator,
    model_validator,
)

from jarvis._atomic_json import read_private_json, replace_private_json

PHONE_DIRECTORY = Path("/var/lib/jarvis/phone")


def canonical_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and str(identifier := UUID(value)) == value:
        return identifier
    raise ValueError("expected a canonical UUID")


type CanonicalUUID = Annotated[UUID, BeforeValidator(canonical_uuid)]


def validate_fid(value: str) -> str:
    if not 1 <= len(value.encode()) <= 4096:
        raise ValueError("invalid Firebase installation address")
    return value


class Enrollment(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    installation_id: CanonicalUUID
    fid: str
    replace: bool

    _validate_fid = field_validator("fid")(validate_fid)


class Phone(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )

    generation: CanonicalUUID
    installation_id: CanonicalUUID | None
    fid: str | None

    @model_validator(mode="after")
    def _check_occupant(self) -> Phone:
        if (self.installation_id is None) != (self.fid is None):
            raise ValueError("incomplete phone slot")
        if self.fid is not None:
            validate_fid(self.fid)
        return self

    @property
    def etag(self) -> str:
        return f'"{self.generation}"'

    def public(self) -> dict[str, str | None]:
        return {
            "installation_id": str(self.installation_id)
            if self.installation_id
            else None,
            "address_hash": sha256(self.fid.encode()).hexdigest() if self.fid else None,
        }


class StalePhone(ValueError):
    """The slot changed after the caller read it."""


class InactivePhone(ValueError):
    """An installation can only refresh its own active address."""


class PhoneSlot:
    def __init__(self, path: Path, on_changed: Callable[[], None]) -> None:
        self._path = path
        self._on_changed = on_changed
        self._lock = asyncio.Lock()

    def _read(self) -> Phone:
        try:
            value = read_private_json(self._path)
            if value is not None:
                return Phone.model_validate(value)
        except ValueError:
            raise OSError("phone slot is unreadable") from None
        return self._publish(None, None)

    def _publish(self, installation: UUID | None, fid: str | None) -> Phone:
        state = Phone(generation=uuid4(), installation_id=installation, fid=fid)
        try:
            replace_private_json(self._path, state.model_dump(mode="json"))
        except ValueError:
            raise OSError("phone slot is unavailable") from None
        return state

    async def read(self) -> Phone:
        async with self._lock:
            return self._read()

    async def change(self, expected: UUID, enrollment: Enrollment | None) -> Phone:
        async with self._lock:
            current = self._read()
            if current.generation != expected:
                raise StalePhone()
            if enrollment is None:
                state = self._publish(None, None)
            else:
                if (
                    not enrollment.replace
                    and current.installation_id != enrollment.installation_id
                ):
                    raise InactivePhone()
                state = self._publish(enrollment.installation_id, enrollment.fid)
            self._on_changed()
            return state

    async def unregister(self, attempted_generation: UUID) -> None:
        async with self._lock:
            if self._read().generation == attempted_generation:
                self._publish(None, None)
