"""One stopped-maintenance declaration for corpus sharing and bearer ownership."""

from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from llm_tools import canonical_json_bytes
from pydantic import BaseModel, ConfigDict, Field, model_validator
from universal_memory import MemoryError
from universal_memory.types import Lane

from jarvis.config import ConfigurationError

type Machine = Literal["macbook", "arch", "devbox"]

MEMORY_IDENTITIES = frozenset(
    (machine, account)
    for machine in ("macbook", "arch", "devbox")
    for account in (
        "codex-personal",
        "codex-work",
        "codex-work2",
        "claude-personal",
        "claude-work",
    )
) | {("devbox", "jarvis")}


def memory_origin(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.path
        or parts.query
        or parts.fragment
        or parts.username is not None
        or parts.password is not None
        or value != f"{parts.scheme}://{parts.netloc}"
        or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        or len(value.encode()) > 4096
        or (
            parts.scheme == "http"
            and parts.hostname not in ("localhost", "127.0.0.1", "::1")
        )
    ):
        raise ValueError("memory origin must be canonical HTTPS or local HTTP")
    # Reading port validates its numeric range without inventing a default.
    _ = parts.port
    return value


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class Processors(_Closed):
    openai_embedding_project: str | None
    codex_account: str | None
    nexus_model_processors: tuple[str, ...] = Field(default=(), max_length=16)


class SharingAuthorization(_Closed):
    declaration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence: str = Field(min_length=1, max_length=4096)


class MemoryLane(Lane):
    controller: str | None = Field(default=None, min_length=1, max_length=256)
    sharing_authorization: SharingAuthorization | None = None
    admit: bool = False
    connect: bool = False
    client_bearer_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$", repr=False
    )


class NexusClient(_Closed):
    client: Literal["nexus-owner"]
    owner_user_id: UUID
    controller: str | None = Field(default=None, min_length=1, max_length=256)
    sharing_authorization: SharingAuthorization | None = None
    admit: bool = False
    connect: bool = False
    bearer_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$", repr=False
    )


type MemoryClient = MemoryLane | NexusClient


class MemoryConfig(_Closed):
    recipients: tuple[str, ...]
    processors: Processors
    lanes: tuple[MemoryLane, ...]
    capture_bearer_sha256: dict[Machine, str] = Field(repr=False)
    origins: tuple[str, ...] = Field(min_length=1, max_length=16)
    nexus_client: NexusClient | None = None

    @property
    def declaration_sha256(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "recipients": sorted(self.recipients),
                    "processors": self.processors.model_dump(mode="json"),
                }
            )
        ).hexdigest()

    @property
    def admitted_lanes(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            (lane.machine, lane.account) for lane in self.lanes if lane.admit
        )

    @property
    def jarvis_admitted(self) -> bool:
        return ("devbox", "jarvis") in self.admitted_lanes

    @property
    def nexus_admitted_owner(self) -> UUID | None:
        client = self.nexus_client
        return client.owner_user_id if client is not None and client.admit else None

    @model_validator(mode="after")
    def valid_declaration(self) -> Self:
        identities = {(lane.machine, lane.account) for lane in self.lanes}
        if len(identities) != len(self.lanes):
            raise ValueError("duplicate memory lane")
        possible = {
            f"{machine}:{account}" for machine, account in MEMORY_IDENTITIES
        } | {"nexus-owner"}
        if len(set(self.recipients)) != len(self.recipients) or not set(
            self.recipients
        ).issubset(possible):
            raise ValueError("invalid corpus recipients")
        processors = self.processors
        if len(set(processors.nexus_model_processors)) != len(
            processors.nexus_model_processors
        ):
            raise ValueError("duplicate nexus processor")
        for value in (
            processors.openai_embedding_project,
            processors.codex_account,
            *processors.nexus_model_processors,
        ):
            if value is not None and (
                not value.strip() or value != value.strip() or len(value.encode()) > 256
            ):
                raise ValueError("invalid named processor")
        hashes = list(self.capture_bearer_sha256.values()) + [
            lane.client_bearer_sha256
            for lane in self.lanes
            if lane.client_bearer_sha256 is not None
        ]
        client = self.nexus_client
        if client is not None and client.bearer_sha256 is not None:
            hashes.append(client.bearer_sha256)
        if len(hashes) != len(set(hashes)) or any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None for value in hashes
        ):
            raise ValueError("invalid or multiply owned bearer hash")
        for lane in self.lanes:
            if lane.connect and (
                f"{lane.machine}:{lane.account}" not in self.recipients
                or lane.client_bearer_sha256 is None
            ):
                raise ValueError(
                    "connected lane needs recipient declaration and bearer"
                )
            if lane.admit:
                if (
                    lane.controller is None
                    or not lane.controller.strip()
                    or lane.sharing_authorization is None
                    or not lane.sharing_authorization.evidence.strip()
                    or lane.sharing_authorization.declaration_sha256
                    != self.declaration_sha256
                    or self.processors.openai_embedding_project is None
                    or self.processors.codex_account is None
                    or "devbox:jarvis" not in self.recipients
                ):
                    raise ValueError(
                        "admitted lane lacks current controller authorization"
                    )
                if (
                    lane.provider != "jarvis"
                    and lane.machine not in self.capture_bearer_sha256
                ):
                    raise ValueError(
                        "admitted native lane needs its host capture bearer"
                    )
        if client is not None:
            if client.connect and (
                client.client not in self.recipients
                or client.bearer_sha256 is None
                or "Nexus" not in processors.nexus_model_processors
            ):
                raise ValueError("connected nexus client lacks declared sharing")
            if client.admit and (
                client.controller is None
                or not client.controller.strip()
                or client.sharing_authorization is None
                or not client.sharing_authorization.evidence.strip()
                or client.sharing_authorization.declaration_sha256
                != self.declaration_sha256
                or processors.openai_embedding_project is None
                or processors.codex_account is None
                or "devbox:jarvis" not in self.recipients
            ):
                raise ValueError("admitted nexus notes lack controller authorization")
        for origin in self.origins:
            memory_origin(origin)
        return self

    @classmethod
    def load(cls, path: Path) -> Self:
        try:
            return cls.model_validate_json(path.read_bytes())
        except (OSError, ValueError):
            raise ConfigurationError("invalid memory declaration") from None

    def require_lane(
        self, machine: str, account: str, *, admit: bool = False, connect: bool = False
    ) -> MemoryLane:
        for lane in self.lanes:
            if (lane.machine, lane.account) == (machine, account):
                if (admit and not lane.admit) or (connect and not lane.connect):
                    break
                return lane
        raise MemoryError("forbidden")

    def _identity(self, bearer: str) -> tuple[Machine | None, MemoryClient | None]:
        if re.fullmatch(r"jmem_[0-9a-f]{64}", bearer) is None:
            raise MemoryError("unauthorized")
        digest = hashlib.sha256(bearer.encode()).hexdigest()
        for machine, expected in self.capture_bearer_sha256.items():
            if hmac.compare_digest(digest, expected):
                return machine, None
        for lane in self.lanes:
            if lane.client_bearer_sha256 is not None and hmac.compare_digest(
                digest, lane.client_bearer_sha256
            ):
                return lane.machine, lane
        client = self.nexus_client
        if (
            client is not None
            and client.bearer_sha256 is not None
            and hmac.compare_digest(digest, client.bearer_sha256)
        ):
            return None, client
        raise MemoryError("unauthorized")

    def authenticate_capture(self, bearer: str) -> Machine:
        machine, lane = self._identity(bearer)
        if lane is not None or machine is None:
            raise MemoryError("forbidden")
        return machine

    def authenticate_client(self, bearer: str) -> MemoryClient:
        _, lane = self._identity(bearer)
        if lane is None or not lane.connect:
            raise MemoryError("forbidden")
        return lane
