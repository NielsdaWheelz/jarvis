"""Verified, one-time mapping of stopped attachment custody into Drive."""

from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from jarvis._atomic_json import read_private_json

DRIVE_CUSTODY_SCHEMA = "0026"
DriveIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,255}$")]
ByteDigest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DriveCutEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_uuid: UUID
    prior_state: Literal["ready", "pending", "failed", "deleted"]
    name: str | None
    size: int | None = Field(ge=0, le=100 * 1024 * 1024)
    sha256: ByteDigest | None
    drive_id: DriveIdentifier | None = None
    verified_at: AwareDatetime | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def check_evidence(self) -> "DriveCutEntry":
        has_bytes = self.size is not None
        if has_bytes != (self.sha256 is not None):
            raise ValueError("attachment size and digest must be recorded together")
        if self.prior_state == "ready":
            if not has_bytes or self.drive_id is None or self.verified_at is None:
                raise ValueError(
                    "ready attachment requires verified Drive bytes and id"
                )
        elif self.drive_id is not None or self.verified_at is not None:
            raise ValueError("only ready attachments can have imported files")
        if self.prior_state == "pending" and not has_bytes:
            raise ValueError("pending attachment requires verified spool bytes")
        if self.prior_state in ("failed", "deleted"):
            if not self.reason:
                raise ValueError(
                    "terminal attachment requires a historical disposition"
                )
        elif self.reason is not None:
            raise ValueError("active attachment cannot have a terminal disposition")
        return self


class RetiredDriveAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    disposition: Literal["verified_under_original_contract", "owner_accepted_unknown"]


class DriveCutManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: DriveIdentifier
    parent: DriveIdentifier
    entries: list[DriveCutEntry]
    retired_actions: tuple[RetiredDriveAction, ...] = ()

    @model_validator(mode="after")
    def check_identities(self) -> "DriveCutManifest":
        sources = {entry.source_uuid for entry in self.entries}
        files = [entry.drive_id for entry in self.entries if entry.drive_id is not None]
        if len(sources) != len(self.entries) or len(set(files)) != len(files):
            raise ValueError("attachment migration duplicates a source or destination")
        if len({item.id for item in self.retired_actions}) != len(self.retired_actions):
            raise ValueError("duplicate retired attachment action disposition")
        if self.parent in files:
            raise ValueError("attachment destination cannot be the import folder")
        return self


def load_stopped_drive_map(
    inventory: Path, *, spool: Path, google_state: Path
) -> DriveCutManifest:
    """Bind the conserved bytes and selected subject before applying any DDL."""
    from hashlib import file_digest

    document = read_private_json(inventory)
    grant = read_private_json(google_state)
    manifest = DriveCutManifest.model_validate(document)
    if (
        grant is None
        or grant.get("status") != "connected"
        or grant.get("subject") != manifest.subject
    ):
        raise ValueError("attachment map belongs to another google subject")
    for item in manifest.entries:
        if item.prior_state != "pending":
            continue
        source = spool / f"{item.source_uuid}.{item.sha256}"
        try:
            with source.open("rb") as stream:
                matches = (
                    source.stat().st_size == item.size
                    and file_digest(stream, "sha256").hexdigest() == item.sha256
                )
        except OSError:
            matches = False
        if not matches:
            raise ValueError(f"attachment {item.source_uuid} spool bytes do not match")
    return manifest
