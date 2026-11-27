"""Bounded host-owned Google connector clients for Slice 2 reads."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import math
import plistlib
import re
import secrets
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import cached_property
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from llm_tools import ExecutionContext
from pydantic import ValidationError

from jarvis._atomic_json import read_private_json, replace_private_json
from jarvis._thread_io import joined_thread
from jarvis.read_tools import (
    ATTACHMENT_MAX_BYTES,
    PLACE_DETAILS_FIELD_MASK,
    PLACES_API_BASE_URL,
    PLACES_SEARCH_FIELD_MASK,
    ROUTES_API_URL,
    ROUTES_FIELD_MASK,
    ConnectorFailure,
    Coordinates,
    MapsDirectionsInput,
    MapsDirectionsSuccess,
    MapsGetPlaceInput,
    MapsGetPlaceSuccess,
    MapsSearchPlacesInput,
    MapsSearchPlacesSuccess,
    Place,
    ReadResponse,
    Route,
)
from jarvis.workspace_enrollment import (
    DRIVE_SCOPE,
    GOOGLE_TOKEN_ENDPOINT,
    HumanWorkspaceProduct,
    WorkspaceEnrollment,
    exchange_workspace_code,
    granted_scopes,
    signed_identity,
    valid_pending_label,
)
from jarvis.workspace_mcp import (
    ARRIVAL_SCOPES,
    WorkspaceCredential,
    WorkspaceError,
    workspace_http_attempt,
    workspace_retry_at,
)

GOOGLE_TOKEN_URL = GOOGLE_TOKEN_ENDPOINT
GOOGLE_STATE_SCHEMA = "jarvis.google-workspace-oauth.v2"
GOOGLE_STATE_PROVIDER = "google"
GOOGLE_AAD_NAMESPACE = "jarvis.connector.google"
MAX_PROVIDER_BODY_BYTES = 2 * 1_024 * 1_024
_KEY_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_TOKEN_ENVELOPE_PREFIX = "aesgcm.v1."
_MAX_GOOGLE_TOKEN_BYTES = 16 * 1_024
_MAX_TOKEN_CIPHERTEXT_BYTES = 12 + _MAX_GOOGLE_TOKEN_BYTES + 16
_MAX_TOKEN_ENVELOPE_CHARS = (
    len(_TOKEN_ENVELOPE_PREFIX) + (4 * _MAX_TOKEN_CIPHERTEXT_BYTES + 2) // 3
)
_TokenField = Literal["access_token", "refresh_token"]


class GoogleCredentialDefect(RuntimeError):
    """The host-owned Google credential state is invalid or unusable."""


class _GoogleRefreshRejected(GoogleCredentialDefect):
    """Google denied the configured refresh grant."""


class GoogleReadFailure(ConnectorFailure):
    def __init__(
        self,
        code: str,
        *,
        attempts: int,
        status: int,
        retry_after: str | None = None,
        grant_unavailable: bool = False,
        malformed_body: bool = False,
    ) -> None:
        super().__init__(code, attempts=attempts)
        self.status = status
        self.retry_after = retry_after
        self.grant_unavailable = grant_unavailable
        self.malformed_body = malformed_body


class _MalformedProviderBody(ConnectorFailure):
    def __init__(self, *, attempts: int) -> None:
        super().__init__("provider_unavailable", attempts=attempts)


class _ProviderResponseTooLarge(ConnectorFailure):
    def __init__(self, *, attempts: int, status: int) -> None:
        super().__init__("provider_response_too_large", attempts=attempts)
        self.status = status


class _ProviderTooLarge(ValueError):
    pass


class OriginalTooLarge(_ProviderTooLarge):
    """The selected decoded original exceeds its admitted byte bound."""


def _b64decode(value: str) -> bytes:
    if not value or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise GoogleCredentialDefect("connector encryption material is invalid")
    try:
        return base64.b64decode(
            (value + "=" * (-len(value) % 4)).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise GoogleCredentialDefect(
            "connector encryption material is invalid"
        ) from None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _token_bytes(value: str) -> bytes:
    encoded = value.encode()
    if not value or len(encoded) > _MAX_GOOGLE_TOKEN_BYTES:
        raise ValueError("Google token value is malformed")
    return encoded


def provider_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} is malformed")
    return cast("dict[str, object]", value)


def provider_array(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} is malformed")
    return cast("list[object]", value)


def _handoff_key(single_secret: str) -> bytes:
    decoded = _b64decode(single_secret)
    return decoded if len(decoded) == 32 else hashlib.sha256(decoded).digest()


class GoogleTokenManager:
    """Decrypt, refresh, and atomically persist the reused Google OAuth grant."""

    def __init__(
        self,
        *,
        state_path: Path,
        client: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        active_key_version: str,
        single_secret: str,
        project_id: str | None = None,
        human_product: HumanWorkspaceProduct | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not state_path.is_absolute():
            raise GoogleCredentialDefect("Google state path must be absolute")
        if project_id is not None and (
            not client_id
            or not client_secret
            or not single_secret
            or _KEY_VERSION.fullmatch(active_key_version) is None
        ):
            raise GoogleCredentialDefect(
                "Google credential configuration is incomplete"
            )
        self.human_product: HumanWorkspaceProduct | None = human_product
        self._schema = (
            f"jarvis.owner-{human_product}-oauth.v1"
            if human_product
            else GOOGLE_STATE_SCHEMA
        )
        self._aad = (
            f"jarvis.owner.{human_product}" if human_product else GOOGLE_AAD_NAMESPACE
        )
        self._state_path = state_path
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._active_key_version = active_key_version
        self._project_id = project_id
        self.on_grant_loss: Callable[[UUID], None] | None = None
        self._handoff_key = (
            _handoff_key(single_secret) if project_id is not None else b""
        )
        self._now = now
        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._force_refresh = False
        self._refresh_lock = asyncio.Lock()

    def matches_client(self, project: str, client_id: str, client_secret: str) -> bool:
        return (project, client_id, client_secret) == (
            self._project_id,
            self._client_id,
            self._client_secret,
        )

    @cached_property
    def _installation(self) -> str | None:
        # The stopped recovery copy contains /etc/jarvis and /var/lib/jarvis,
        # not the installation's machine id. A detached copy cannot own the label.
        try:
            if sys.platform == "darwin":
                hardware = subprocess.check_output(
                    ("/usr/sbin/ioreg", "-ard1", "-c", "IOPlatformExpertDevice"),
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                )
                machine = UUID(plistlib.loads(hardware)[0]["IOPlatformUUID"]).hex
            else:
                machine = Path("/etc/machine-id").read_text().strip()
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            plistlib.InvalidFileException,
        ):
            return None
        if not re.fullmatch(r"[a-f0-9]{32}", machine) or machine == "0" * 32:
            return None
        binding = f"{machine}:{self._state_path.resolve()}"
        return hashlib.sha256(binding.encode()).hexdigest()

    def enrollment(self) -> WorkspaceEnrollment | None:
        if self._project_id is None:
            return None
        try:
            state = read_private_json(self._state_path)
            if (
                not state
                or state.get("schema") != self._schema
                or state.get("status") == "disconnected"
                or not state.get("installation")
                or state.get("installation") != self._installation
            ):
                return None
            return self._identity(self._validate_state(state))
        except (UnicodeError, ValueError) as exc:
            raise GoogleCredentialDefect("workspace enrollment is malformed") from exc

    def _identity(self, state: Mapping[str, object]) -> WorkspaceEnrollment:
        subject = provider_string(state, "subject")
        account = provider_string(state, "account")
        grant = UUID(provider_string(state, "grant_id"))
        label = state.get("pending_label_id")
        if (
            not self._project_id
            or state.get("project_id") != self._project_id
            or state.get("client_id") != self._client_id
            or grant.version != 4
            or not 1 <= len(subject.encode()) <= 255
            or len(account.encode()) > 320
            or not re.fullmatch(r"[^@\s]+@[^@\s]+", account)
            or (label is not None and not isinstance(label, str))
            or (self.human_product is not None and label is not None)
            or not valid_pending_label(label)
        ):
            raise GoogleCredentialDefect("workspace enrollment identity is invalid")
        values = state.get("granted_scopes")
        if not isinstance(values, list) or not all(
            isinstance(v, str) and " " not in v for v in cast(list[object], values)
        ):
            raise GoogleCredentialDefect("workspace enrollment scopes are invalid")
        scopes = granted_scopes(
            " ".join(cast(list[str], values)), human_product=self.human_product
        )
        return WorkspaceEnrollment(
            grant, self._project_id, account, subject, label, scopes
        )

    def _forget(self, grant_id: UUID) -> None:
        self._access_token = None
        self._expires_at = None
        self._force_refresh = False
        if self.on_grant_loss is not None:
            self.on_grant_loss(grant_id)

    def _disconnect(self, grant_id: UUID) -> None:
        self._forget(grant_id)
        replace_private_json(
            self._state_path,
            {
                "schema": self._schema,
                "provider": GOOGLE_STATE_PROVIDER,
                "status": "disconnected",
                "grant_id": str(grant_id),
            },
        )

    async def disconnect(self, grant_id: UUID) -> None:
        async with self._refresh_lock:
            current = self.enrollment()
            if current and current.grant_id == grant_id:
                self._disconnect(grant_id)

    async def complete_enrollment(
        self,
        *,
        code: str,
        redirect_uri: str,
        verifier: str,
        nonce: str,
        expected_email: str,
        pending_label_id: str | None,
        incremental_drive: bool = False,
        expected_subject: str | None = None,
    ) -> WorkspaceEnrollment:
        installation = self._installation
        if (
            not self._project_id
            or not installation
            or (self.human_product is not None) != (expected_subject is not None)
            or (self.human_product is not None and pending_label_id is not None)
            or not valid_pending_label(pending_label_id)
        ):
            raise WorkspaceError("grant_unavailable")
        async with self._refresh_lock:
            tokens = await exchange_workspace_code(
                self._client,
                client_id=self._client_id,
                client_secret=self._client_secret,
                code=code,
                verifier=verifier,
                nonce=nonce,
                redirect_uri=redirect_uri,
                expected_email=expected_email,
                human_product=self.human_product,
            )
            if expected_subject is not None and tokens.subject != expected_subject:
                raise WorkspaceError("grant_unavailable")
            previous = self.enrollment()
            account = tokens.account
            if incremental_drive:
                if (
                    previous is None
                    or self.human_product is not None
                    or tokens.subject != previous.subject
                    or tokens.account.casefold() != previous.account.casefold()
                    or tokens.scopes - {DRIVE_SCOPE} != previous.scopes - {DRIVE_SCOPE}
                    or pending_label_id not in (None, previous.pending_label_id)
                ):
                    raise WorkspaceError("grant_unavailable")
                account = previous.account
                pending_label_id = previous.pending_label_id
                grant_id = previous.grant_id
            else:
                if DRIVE_SCOPE in tokens.scopes:
                    raise WorkspaceError("grant_unavailable")
                grant_id = uuid4()
            if pending_label_id is not None and not ARRIVAL_SCOPES <= tokens.scopes:
                raise WorkspaceError("scope_missing")
            now = self._now().astimezone(UTC)
            state: dict[str, object] = {
                "schema": self._schema,
                "provider": GOOGLE_STATE_PROVIDER,
                "status": "connected",
                "installation": installation,
                "project_id": self._project_id,
                "client_id": self._client_id,
                "grant_id": str(grant_id),
                "account": account,
                "subject": tokens.subject,
                "pending_label_id": pending_label_id,
                "granted_scopes": sorted(tokens.scopes),
                "access_token_enc": self._encrypt(
                    tokens.access_token, field="access_token"
                ),
                "refresh_token_enc": self._encrypt(
                    tokens.refresh_token, field="refresh_token"
                ),
                "access_token_expires_at": (
                    now + timedelta(seconds=tokens.expires_in)
                ).isoformat(),
                "token_obtained_at": now.isoformat(),
                "encryption": {
                    "aad_namespace": (f"{self._aad}:{self._active_key_version}"),
                    "algorithm": "AES-256-GCM",
                    "key_version": self._active_key_version,
                },
            }
            enrolled = self._identity(state)
            replace_private_json(self._state_path, state)
            if previous is not None and previous.grant_id != enrolled.grant_id:
                self._forget(previous.grant_id)
            else:
                self._access_token = None
                self._expires_at = None
                self._force_refresh = False
            return enrolled

    async def credential(
        self, grant_id: UUID, rejected_token: str | None
    ) -> WorkspaceCredential:
        async with self._refresh_lock:
            current = self.enrollment()
            if current is None or current.grant_id != grant_id:
                raise WorkspaceError("grant_unavailable")
            if rejected_token is not None:
                self._invalidate_access_token(rejected_token)
            try:
                token = await self._current_access_token(current)
            except _GoogleRefreshRejected:
                self._disconnect(grant_id)
                raise WorkspaceError("grant_unavailable") from None
            except GoogleReadFailure as exc:
                if exc.status == 429:
                    raise WorkspaceError(
                        "rate_limited", retry_at=workspace_retry_at(exc.retry_after)
                    ) from None
                raise WorkspaceError("temporary") from None
            except ConnectorFailure:
                raise WorkspaceError("temporary") from None
            current = self.enrollment()
            if current is None or current.grant_id != grant_id:
                raise WorkspaceError("grant_unavailable")
            return WorkspaceCredential(token, current.scopes, current.pending_label_id)

    async def _current_access_token(self, current: WorkspaceEnrollment) -> str:
        now = self._now()
        if now.tzinfo is None:
            raise RuntimeError("Google credential clock must be aware")
        if (
            self._access_token is not None
            and self._expires_at is not None
            and self._expires_at > now + timedelta(seconds=60)
            and not self._force_refresh
        ):
            return self._access_token
        state = self._load_state()
        encryption = cast("dict[str, object]", state["encryption"])
        key_version = cast("str", encryption["key_version"])
        try:
            expires_at = parse_google_instant(
                provider_string(state, "access_token_expires_at")
            )
            access_token = self._decrypt(
                provider_string(state, "access_token_enc"),
                field="access_token",
                key_version=key_version,
            )
        except ValueError as exc:
            raise GoogleCredentialDefect(
                "Google credential state is malformed"
            ) from exc
        if expires_at > now + timedelta(seconds=60) and not self._force_refresh:
            self._access_token = access_token
            self._expires_at = expires_at
            return access_token
        try:
            refresh_token = self._decrypt(
                provider_string(state, "refresh_token_enc"),
                field="refresh_token",
                key_version=key_version,
            )
        except ValueError as exc:
            raise GoogleCredentialDefect(
                "Google credential state is malformed"
            ) from exc
        try:
            async with (
                workspace_http_attempt(4.0),
                self._client.stream(
                    "POST",
                    GOOGLE_TOKEN_URL,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                    headers={"Accept": "application/json"},
                    follow_redirects=False,
                    timeout=httpx.Timeout(5.0, connect=2.0),
                ) as response,
            ):
                if response.status_code == 429:
                    raise GoogleReadFailure(
                        "rate_limited",
                        attempts=1,
                        status=429,
                        retry_after=response.headers.get("Retry-After"),
                    )
                if response.status_code >= 500:
                    raise GoogleReadFailure(
                        "provider_unavailable",
                        attempts=1,
                        status=response.status_code,
                        retry_after=response.headers.get("Retry-After"),
                    )
                if response.status_code != 200:
                    error_payload = await _json_body(response, attempts=1)
                    if error_payload.get("error") in {
                        "invalid_client",
                        "invalid_grant",
                    }:
                        raise _GoogleRefreshRejected("Google OAuth grant is unusable")
                    raise ConnectorFailure("provider_unavailable", attempts=1)
                payload = await _json_body(response, attempts=1)
        except (TimeoutError, httpx.HTTPError, OSError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        try:
            token = provider_string(payload, "access_token")
            _token_bytes(token)
            expires_in = payload.get("expires_in")
            if (
                type(expires_in) is not int
                or expires_in <= 60
                or expires_in > 31_536_000
            ):
                raise ValueError("Google OAuth expiry is malformed")
            token_type = payload.get("token_type")
            if not isinstance(token_type, str) or token_type.lower() != "bearer":
                raise ValueError("Google OAuth token type is malformed")
            if "id_token" in payload:
                try:
                    _, subject = await signed_identity(
                        self._client,
                        payload,
                        access=token,
                        client_id=self._client_id,
                        expected_email=current.account,
                    )
                except WorkspaceError as exc:
                    if exc.kind == "grant_unavailable":
                        raise _GoogleRefreshRejected(
                            "Google OAuth identity changed"
                        ) from None
                    raise
                if subject != current.subject:
                    raise _GoogleRefreshRejected("Google OAuth subject changed")
            refreshed_scopes = current.scopes
            returned_scope = payload.get("scope")
            if returned_scope is not None:
                if not isinstance(returned_scope, str):
                    raise ValueError("Google OAuth scope is malformed")
                try:
                    refreshed_scopes = granted_scopes(
                        returned_scope, human_product=self.human_product
                    )
                except ValueError:
                    raise _GoogleRefreshRejected("Google OAuth scope changed") from None
                if (
                    refreshed_scopes != current.scopes
                    and refreshed_scopes != current.scopes - {DRIVE_SCOPE}
                ):
                    raise _GoogleRefreshRejected("Google OAuth scope changed")
        except GoogleCredentialDefect:
            raise
        except ValueError:
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        refreshed_at = now.astimezone(UTC)
        refreshed_expiry = refreshed_at + timedelta(seconds=expires_in)
        updated = dict(state)
        updated["access_token_enc"] = self._encrypt(token, field="access_token")
        updated["access_token_expires_at"] = refreshed_expiry.isoformat()
        updated["token_obtained_at"] = refreshed_at.isoformat()
        updated["granted_scopes"] = sorted(refreshed_scopes)
        returned_refresh = payload.get("refresh_token")
        if returned_refresh is not None:
            if not isinstance(returned_refresh, str) or not returned_refresh:
                raise ConnectorFailure("provider_unavailable", attempts=1)
            try:
                _token_bytes(returned_refresh)
            except ValueError:
                raise ConnectorFailure("provider_unavailable", attempts=1) from None
            refresh_token = returned_refresh
        updated["refresh_token_enc"] = self._encrypt(
            refresh_token, field="refresh_token"
        )
        updated["encryption"] = {
            "aad_namespace": f"{self._aad}:{self._active_key_version}",
            "algorithm": "AES-256-GCM",
            "key_version": self._active_key_version,
        }
        replace_private_json(self._state_path, updated)
        self._access_token = token
        self._expires_at = refreshed_expiry
        self._force_refresh = False
        return token

    def _invalidate_access_token(self, rejected_token: str) -> None:
        if self._access_token == rejected_token:
            self._access_token = None
            self._expires_at = None
            self._force_refresh = True

    def _load_state(self) -> Mapping[str, object]:
        try:
            state = read_private_json(self._state_path)
        except ValueError as exc:
            raise GoogleCredentialDefect("Google credential state is unsafe") from exc
        if state is None:
            raise GoogleCredentialDefect("Google credential state is absent")
        return self._validate_state(state)

    def _validate_state(self, state: Mapping[str, object]) -> Mapping[str, object]:
        encryption = state.get("encryption")
        encryption_value = (
            cast("dict[str, object]", encryption)
            if isinstance(encryption, dict)
            else {}
        )
        key_version = encryption_value.get("key_version")
        if (
            state.get("schema") != self._schema
            or state.get("provider") != GOOGLE_STATE_PROVIDER
            or state.get("status") != "connected"
            or not isinstance(key_version, str)
            or encryption_value.get("algorithm") != "AES-256-GCM"
            or encryption_value.get("aad_namespace") != f"{self._aad}:{key_version}"
        ):
            raise GoogleCredentialDefect("Google credential state contract is invalid")
        self._identity(state)
        return state

    def _decrypt(self, envelope: str, *, field: _TokenField, key_version: str) -> str:
        if len(envelope) > _MAX_TOKEN_ENVELOPE_CHARS or not envelope.startswith(
            _TOKEN_ENVELOPE_PREFIX
        ):
            raise GoogleCredentialDefect("Google token envelope is malformed")
        encoded = envelope.removeprefix(_TOKEN_ENVELOPE_PREFIX)
        combined = _b64decode(encoded)
        if (
            len(combined) < 28
            or len(combined) > _MAX_TOKEN_CIPHERTEXT_BYTES
            or _b64encode(combined) != encoded
        ):
            raise GoogleCredentialDefect("Google token envelope is malformed")
        nonce = combined[:12]
        ciphertext = combined[12:]
        try:
            plaintext = AESGCM(self._handoff_key).decrypt(
                nonce,
                ciphertext,
                f"{self._aad}:{key_version}:{field}".encode(),
            )
            value = plaintext.decode()
        except (InvalidTag, UnicodeDecodeError):
            raise GoogleCredentialDefect("Google token decryption failed") from None
        if not value or len(plaintext) > _MAX_GOOGLE_TOKEN_BYTES:
            raise GoogleCredentialDefect("Google token value is malformed")
        return value

    def _encrypt(self, value: str, *, field: _TokenField) -> str:
        version = self._active_key_version
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._handoff_key).encrypt(
            nonce,
            _token_bytes(value),
            f"{self._aad}:{version}:{field}".encode(),
        )
        return f"{_TOKEN_ENVELOPE_PREFIX}{_b64encode(nonce + ciphertext)}"


def gmail_headers(part: Mapping[str, object]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for raw in provider_array(part.get("headers", []), "Gmail headers"):
        header = provider_object(raw, "Gmail header")
        name, value = header.get("name"), header.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("Gmail header is malformed")
        result.append({"name": name, "value": value})
    return result


class MapsReadConnector:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not api_key:
            raise ValueError("Maps key must not be empty")
        self._client = client
        self._api_key = api_key
        self._now = now

    async def search_places(
        self, value: MapsSearchPlacesInput, *, context: ExecutionContext | None = None
    ) -> ReadResponse[MapsSearchPlacesSuccess]:
        if not value.query.strip():
            raise ConnectorFailure("invalid_query", attempts=0)
        body: dict[str, object] = {
            "textQuery": value.query,
            "pageSize": value.max_results,
        }
        if value.location_bias is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": value.location_bias.latitude,
                        "longitude": value.location_bias.longitude,
                    },
                    "radius": value.location_bias.radius_m,
                }
            }
        payload = await self._request(
            "POST",
            f"{PLACES_API_BASE_URL}/places:searchText",
            field_mask=PLACES_SEARCH_FIELD_MASK,
            json_body=body,
            invalid_request="invalid_query",
        )
        try:
            raw_places = provider_array(payload.get("places", []), "Places results")
            if len(raw_places) > value.max_results:
                raise _ProviderTooLarge
            result = MapsSearchPlacesSuccess(
                places=tuple(_place(item) for item in raw_places),
                observed_at=self._observed_at(),
            )
        except _ProviderTooLarge:
            raise ConnectorFailure("provider_response_too_large", attempts=1) from None
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return ReadResponse(result, 1)

    async def get_place(
        self, value: MapsGetPlaceInput, *, context: ExecutionContext | None = None
    ) -> ReadResponse[MapsGetPlaceSuccess]:
        payload = await self._request(
            "GET",
            f"{PLACES_API_BASE_URL}/places/{quote(value.place_id, safe='')}",
            field_mask=PLACE_DETAILS_FIELD_MASK,
            not_found="place_not_found",
            invalid_request="place_not_found",
        )
        try:
            place = _place(payload)
            if place.place_id != value.place_id:
                raise ValueError("Places returned a different stable identity")
            result = MapsGetPlaceSuccess(place=place, observed_at=self._observed_at())
        except _ProviderTooLarge:
            raise ConnectorFailure("provider_response_too_large", attempts=1) from None
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return ReadResponse(result, 1)

    async def directions(
        self, value: MapsDirectionsInput, *, context: ExecutionContext | None = None
    ) -> ReadResponse[MapsDirectionsSuccess]:
        now = self._observed_at()
        departure: datetime | None = None
        if value.departure_at is not None:
            try:
                departure = value.departure_at.astimezone(UTC)
            except (OverflowError, ValueError):
                raise ConnectorFailure("invalid_departure_time", attempts=0) from None
            if departure < now and value.travel_mode != "transit":
                raise ConnectorFailure("invalid_departure_time", attempts=0)
            if value.travel_mode == "transit" and not (
                now - timedelta(days=7) <= departure <= now + timedelta(days=100)
            ):
                raise ConnectorFailure("invalid_departure_time", attempts=0)
        body: dict[str, object] = {
            "origin": _waypoint(value.origin),
            "destination": _waypoint(value.destination),
            "travelMode": {
                "driving": "DRIVE",
                "walking": "WALK",
                "bicycling": "BICYCLE",
                "transit": "TRANSIT",
            }[value.travel_mode],
            "computeAlternativeRoutes": False,
        }
        if departure is not None:
            body["departureTime"] = _rfc3339(departure)
        payload = await self._request(
            "POST",
            ROUTES_API_URL,
            field_mask=ROUTES_FIELD_MASK,
            json_body=body,
            invalid_request="invalid_location",
        )
        try:
            raw_routes = provider_array(payload.get("routes", []), "Routes results")
            if not raw_routes:
                raise ConnectorFailure("no_route", attempts=1)
            if len(raw_routes) != 1:
                raise _ProviderTooLarge
            raw = provider_object(raw_routes[0], "route")
            warnings = provider_array(raw.get("warnings", []), "route warnings")
            if len(warnings) > 10:
                raise _ProviderTooLarge
            route = Route(
                distance_meters=_bounded_integer(raw.get("distanceMeters", 0)),
                duration_seconds=_duration(provider_string(raw, "duration")),
                description=_exact_optional(raw, "description", 1_000),
                warnings=tuple(_exact_string(item, 1_000) for item in warnings),
            )
            result = MapsDirectionsSuccess(routes=(route,), observed_at=now)
        except ConnectorFailure:
            raise
        except _ProviderTooLarge:
            raise ConnectorFailure("provider_response_too_large", attempts=1) from None
        except (TypeError, ValueError, ValidationError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return ReadResponse(result, 1)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        field_mask: str,
        json_body: Mapping[str, object] | None = None,
        not_found: str | None = None,
        invalid_request: str | None = None,
    ) -> dict[str, object]:
        try:
            headers = {
                "Accept": "application/json",
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": field_mask,
            }
            request_options: dict[str, Any] = {
                "headers": headers,
                "follow_redirects": False,
                "timeout": httpx.Timeout(12.0, connect=5.0),
            }
            if json_body is not None:
                headers["Content-Type"] = "application/json"
                request_options["json"] = json_body
            async with (
                asyncio.timeout(12.0),
                self._client.stream(
                    method,
                    url,
                    **request_options,
                ) as response,
            ):
                if response.status_code == 404 and not_found is not None:
                    raise ConnectorFailure(not_found, attempts=1)
                if response.status_code == 429:
                    raise ConnectorFailure("rate_limited", attempts=1)
                if response.status_code == 400:
                    raise ConnectorFailure(
                        invalid_request or "provider_unavailable", attempts=1
                    )
                if response.status_code < 200 or response.status_code >= 300:
                    raise ConnectorFailure("provider_unavailable", attempts=1)
                payload = await _json_body(response, attempts=1)
        except (TimeoutError, httpx.HTTPError, OSError):
            raise ConnectorFailure("provider_unavailable", attempts=1) from None
        return payload

    def _observed_at(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise RuntimeError("connector clock must be aware")
        return value.astimezone(UTC)


async def _json_body(
    response: httpx.Response,
    *,
    attempts: int,
    maximum: int | None = MAX_PROVIDER_BODY_BYTES,
) -> dict[str, object]:
    chunk_bytes = 1_024 * 1_024
    if maximum is not None:
        chunk_bytes = min(chunk_bytes, maximum + 1)
    try:
        with tempfile.TemporaryFile() as body:
            count = 0
            async for chunk in response.aiter_bytes(chunk_size=chunk_bytes):
                count += len(chunk)
                if maximum is not None and count > maximum:
                    raise _ProviderResponseTooLarge(
                        attempts=attempts, status=response.status_code
                    )
                await joined_thread(body.write, chunk)
            body.seek(0)
            value: object = await joined_thread(
                json.load,
                body,
                parse_constant=_reject_constant,
                object_pairs_hook=_strict_object,
            )
    except OSError:
        raise ConnectorFailure("provider_unavailable", attempts=attempts) from None
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ):
        raise _MalformedProviderBody(attempts=attempts) from None
    if not isinstance(value, dict):
        raise _MalformedProviderBody(attempts=attempts)
    return cast("dict[str, object]", value)


def _reject_constant(value: str) -> None:
    del value
    raise ValueError("non-finite JSON number")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate provider JSON key")
        value[key] = item
    return value


def provider_string(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"provider field {key} is missing")
    return result


def provider_text(value: str, maximum: int) -> str:
    if len(value.encode()) > maximum:
        raise _ProviderTooLarge
    return value


def _exact_string(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError("provider string is malformed")
    return provider_text(value, maximum)


def _exact_optional(value: Mapping[str, object], key: str, maximum: int) -> str | None:
    result = value.get(key)
    if result is None:
        return None
    return _exact_string(result, maximum)


_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


_FRACTION = re.compile(r"\.(\d+)(?=Z|[+-]\d\d:\d\d|$)")


def _timestamp_text(value: str) -> str:
    if len(value.encode()) > 64:
        raise _ProviderTooLarge
    match = _FRACTION.search(value)
    if match is None or len(match.group(1)) <= 6:
        return value
    fraction = match.group(1)
    if any(character != "0" for character in fraction[6:]):
        raise _ProviderTooLarge
    return value[: match.start(1)] + fraction[:6] + value[match.end(1) :]


def parse_google_instant(value: str) -> datetime:
    text = _timestamp_text(value)
    if _RFC3339.fullmatch(text) is None:
        raise ValueError("provider timestamp is malformed")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    try:
        return parsed.astimezone(UTC)
    except OverflowError:
        raise _ProviderTooLarge from None


def decode_gmail_body(
    data: str, *, maximum: int | None = ATTACHMENT_MAX_BYTES
) -> bytes:
    if maximum is not None and len(data) > (maximum + 2) // 3 * 4:
        raise OriginalTooLarge
    try:
        decoded = base64.b64decode(
            (data + "=" * (-len(data) % 4)).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ValueError("Gmail MIME data is malformed") from exc
    if maximum is not None and len(decoded) > maximum:
        raise OriginalTooLarge
    return decoded


def _place(value: object) -> Place:
    place = provider_object(value, "Place")
    display = provider_object(place.get("displayName"), "Place display name")
    location_value = place.get("location")
    location: Coordinates | None = None
    if location_value is not None:
        coordinates = provider_object(location_value, "Place location")
        latitude = coordinates.get("latitude", 0)
        longitude = coordinates.get("longitude", 0)
        if (
            isinstance(latitude, bool)
            or not isinstance(latitude, int | float)
            or not math.isfinite(latitude)
            or isinstance(longitude, bool)
            or not isinstance(longitude, int | float)
            or not math.isfinite(longitude)
        ):
            raise ValueError("Place coordinates are malformed")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise _ProviderTooLarge
        location = Coordinates(
            latitude=latitude,
            longitude=longitude,
        )
    types = provider_array(place.get("types", []), "Place types")
    if len(types) > 32:
        raise _ProviderTooLarge
    links = provider_object(place.get("googleMapsLinks", {}), "Place link")
    uri = links.get("placeUri", place.get("googleMapsUri"))
    if uri is not None and not isinstance(uri, str):
        raise ValueError("Place link is malformed")
    return Place(
        place_id=provider_text(provider_string(place, "id"), 1_024),
        display_name=provider_text(provider_string(display, "text"), 512),
        formatted_address=_exact_optional(place, "formattedAddress", 1_024),
        location=location,
        types=tuple(_exact_string(item, 128) for item in types),
        maps_uri=provider_text(uri, 4_096) if uri is not None else None,
    )


def _waypoint(value: object) -> dict[str, object]:
    if getattr(value, "type", None) == "address":
        return {"address": cast("Any", value).address}
    if getattr(value, "type", None) == "place":
        return {"placeId": cast("Any", value).place_id}
    coordinates = cast("Any", value).coordinates
    return {
        "location": {
            "latLng": {
                "latitude": coordinates.latitude,
                "longitude": coordinates.longitude,
            }
        }
    }


_DURATION = re.compile(r"^(\d+)(?:\.(\d{1,9}))?s$")


def _duration(value: str) -> int:
    match = _DURATION.fullmatch(value)
    if match is None:
        raise ValueError("route duration is malformed")
    try:
        seconds = Decimal(value[:-1])
    except InvalidOperation as exc:
        raise ValueError("route duration is malformed") from exc
    rounded = math.ceil(seconds)
    if rounded > 2_147_483_647:
        raise _ProviderTooLarge
    return rounded


def _bounded_integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("provider integer is malformed")
    if value > 2_147_483_647:
        raise _ProviderTooLarge
    return value


__all__ = [
    "GOOGLE_AAD_NAMESPACE",
    "GOOGLE_STATE_SCHEMA",
    "GOOGLE_TOKEN_URL",
    "MAX_PROVIDER_BODY_BYTES",
    "GoogleCredentialDefect",
    "GoogleTokenManager",
    "MapsReadConnector",
]
