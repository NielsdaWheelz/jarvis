"""Operator enrollment for one verified Google Workspace OAuth account."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import jwt as google_jwt
from google.auth.exceptions import GoogleAuthError

from jarvis._atomic_json import read_private_json
from jarvis.workspace_mcp import SCOPES, WorkspaceError, workspace_http_attempt

if TYPE_CHECKING:
    from jarvis.connectors import GoogleTokenManager

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
IDENTITY_SCOPES = frozenset(
    {"openid", "https://www.googleapis.com/auth/userinfo.email"}
)
ENROLLMENT_SCOPES = SCOPES | IDENTITY_SCOPES
_APPROVAL_COPY = (
    "this client must be marked for an ai-powered agent in google cloud. "
    "its permission can trash ordinary mail and change message labels. jarvis "
    "uses deletion only for verified draft revisions and label changes only "
    "to clear its enrolled pending label. the owner sends in gmail."
)


@dataclass(frozen=True, slots=True)
class WorkspaceEnrollment:
    grant_id: UUID
    project_id: str
    account: str
    subject: str
    pending_label_id: str | None
    scopes: frozenset[str]


@dataclass(frozen=True, slots=True)
class VerifiedTokens:
    account: str
    subject: str
    scopes: frozenset[str]
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_in: int


def granted_scopes(values: object) -> frozenset[str]:
    if not isinstance(values, str):
        raise ValueError("missing granted OAuth scope")
    scope_list = values.split()
    result = frozenset(
        "https://www.googleapis.com/auth/userinfo.email" if v == "email" else v
        for v in scope_list
    )
    if not IDENTITY_SCOPES <= result <= ENROLLMENT_SCOPES or len(result) != len(
        scope_list
    ):
        raise ValueError("unexpected or incomplete Google OAuth scopes")
    return result


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid Google credential response")
    return cast(dict[str, object], value)


def _text(source: Mapping[str, object], key: str, limit: int = 16384) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not 0 < len(value.encode()) <= limit:
        raise ValueError("invalid Google credential response")
    return value


def valid_pending_label(value: str | None) -> bool:
    return value is None or (
        bool(value) and len(value.encode()) <= 1024 and value.isprintable()
    )


async def _json(
    http: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    data: Mapping[str, str] | None = None,
) -> dict[str, object]:
    async with (
        workspace_http_attempt(15),
        http.stream(
            method,
            url,
            data=data,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            follow_redirects=False,
            timeout=15,
        ) as response,
    ):
        if response.status_code != 200:
            raise WorkspaceError(
                "temporary"
                if url == GOOGLE_JWKS or response.status_code >= 500
                else "grant_unavailable"
            )
        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=16384):
            if len(body) + len(chunk) > 131072:
                raise ValueError("Google credential response exceeds limit")
            body.extend(chunk)
        return _object(json.loads(body))


def _b64number(value: str) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,1400}", value):
        raise ValueError("malformed Google signing key")
    return int.from_bytes(
        base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)), "big"
    )


async def signed_identity(
    http: httpx.AsyncClient,
    token: Mapping[str, object],
    *,
    access: str,
    client_id: str,
    expected_email: str,
    nonce: str | None = None,
) -> tuple[str, str]:
    try:
        id_token = _text(token, "id_token")
        header = _object(
            google_jwt.decode_header(id_token)  # pyright: ignore[reportUnknownMemberType]
        )
        if header.get("alg") != "RS256":
            raise ValueError("unexpected Google signing algorithm")
        kid = _text(header, "kid", 256)
        keys = (await _json(http, "GET", GOOGLE_JWKS)).get("keys")
        if not isinstance(keys, list):
            raise ValueError("missing Google signing keys")
        matching = [
            k for k in map(_object, cast(list[object], keys)) if k.get("kid") == kid
        ]
        if len(matching) != 1:
            raise ValueError("unknown or ambiguous Google signing key")
        key = matching[0]
        if (key.get("kty"), key.get("alg"), key.get("use")) != ("RSA", "RS256", "sig"):
            raise ValueError("unexpected Google signing key")
        public = rsa.RSAPublicNumbers(
            _b64number(_text(key, "e", 16)), _b64number(_text(key, "n", 1400))
        ).public_key()
        pem = public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        claims = _object(
            google_jwt.decode(  # pyright: ignore[reportUnknownMemberType]
                id_token, certs={kid: pem}, audience=client_id
            )
        )
        account = _text(claims, "email", 320)
        subject = _text(claims, "sub", 255)
        if (
            claims.get("iss")
            not in {"https://accounts.google.com", "accounts.google.com"}
            or claims.get("azp", client_id) != client_id
            or claims.get("email_verified") is not True
            or account.casefold() != expected_email.casefold()
            or (nonce is not None and claims.get("nonce") != nonce)
        ):
            raise ValueError("Google identity does not match the approved enrollment")
        if "at_hash" in claims:
            digest = hashlib.sha256(access.encode()).digest()[:16]
            actual = base64.urlsafe_b64encode(digest).decode().rstrip("=")
            if claims["at_hash"] != actual:
                raise ValueError(
                    "Google access token does not match the identity token"
                )
        return account, subject
    except (GoogleAuthError, ValueError, KeyError, TypeError, OverflowError):
        raise WorkspaceError("grant_unavailable") from None
    except (httpx.RequestError, TimeoutError):
        raise WorkspaceError("temporary") from None


async def exchange_workspace_code(
    http: httpx.AsyncClient,
    *,
    client_id: str,
    client_secret: str,
    code: str,
    verifier: str,
    nonce: str,
    redirect_uri: str,
    expected_email: str,
) -> VerifiedTokens:
    """Redeem this loopback flow's code and independently verify its identity."""
    try:
        token = await _json(
            http,
            "POST",
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
            },
        )
        access = _text(token, "access_token")
        account, subject = await signed_identity(
            http,
            token,
            access=access,
            client_id=client_id,
            expected_email=expected_email,
            nonce=nonce,
        )
        expires = token.get("expires_in")
        if (
            type(expires) is not int
            or not 60 < expires <= 31_536_000
            or _text(token, "token_type").lower() != "bearer"
        ):
            raise ValueError("invalid Google token lifetime or type")
        return VerifiedTokens(
            account,
            subject,
            granted_scopes(token.get("scope")),
            access,
            _text(token, "refresh_token"),
            expires,
        )
    except (GoogleAuthError, ValueError, KeyError, TypeError, OverflowError):
        raise WorkspaceError("grant_unavailable") from None
    except (httpx.RequestError, TimeoutError):
        raise WorkspaceError("temporary") from None


async def enroll_workspace(
    manager: GoogleTokenManager,
    client_file: Path,
    *,
    expected_email: str,
    pending_label_id: str | None,
    confirm: Callable[[str], bool],
    show_url: Callable[[str], None],
) -> WorkspaceEnrollment:
    """Run at the approved stopped installation on an operator-owned loopback;
    the caller displays the URL and scopes privately. Never print a returned code.
    """
    export = read_private_json(client_file)
    if (
        export is None
        or set(export) != {"installed"}
        or not valid_pending_label(pending_label_id)
        or not re.fullmatch(r"[^@\s]+@[^@\s]+", expected_email)
    ):
        raise WorkspaceError("grant_unavailable")
    client = _object(export["installed"])
    client_id = _text(client, "client_id")
    secret = _text(client, "client_secret")
    project = _text(client, "project_id")
    if not manager.matches_client(project, client_id, secret):
        raise WorkspaceError("grant_unavailable")
    if not confirm(f"connect {expected_email} to {project}? {_APPROVAL_COPY}"):
        raise WorkspaceError("cancelled")
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    answer: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def callback(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            async with asyncio.timeout(5):
                request = (await reader.readuntil(b"\r\n\r\n")).decode("ascii")
            method, target, _ = request.split("\r\n", 1)[0].split(" ", 2)
            url = urlsplit(target)
            args = parse_qs(url.query, max_num_fields=24)
            accepted = False
            if (
                method == "GET"
                and url.path == "/"
                and not url.netloc
                and not answer.done()
                and hmac.compare_digest(args.get("state", [""])[0], state)
                and len(args.get("state", [])) == 1
            ):
                if "error" in args:
                    answer.set_exception(WorkspaceError("denied"))
                elif len(args.get("code", [])) == 1 and args["code"][0]:
                    answer.set_result(args["code"][0])
                    accepted = True
            code = b"200 OK" if accepted else b"400 Bad Request"
            writer.write(
                b"HTTP/1.1 "
                + code
                + b"\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\n"
                b"Connection: close\r\n\r\nReturn to the operator terminal."
            )
            await writer.drain()
        except (
            TimeoutError,
            ConnectionError,
            UnicodeError,
            ValueError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            pass
        finally:
            writer.close()

    async with await asyncio.start_server(
        callback, "127.0.0.1", 0, limit=8192
    ) as server:
        port = server.sockets[0].getsockname()[1]
        redirect = f"http://127.0.0.1:{port}/"
        show_url(
            "https://accounts.google.com/o/oauth2/v2/auth?"
            + urlencode(
                {
                    "client_id": client_id,
                    "redirect_uri": redirect,
                    "scope": " ".join(sorted(ENROLLMENT_SCOPES)),
                    "response_type": "code",
                    "access_type": "offline",
                    "prompt": "consent",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "login_hint": expected_email,
                }
            )
        )
        try:
            async with asyncio.timeout(300):
                code = await answer
        except TimeoutError:
            raise WorkspaceError("consent_expired") from None
    return await manager.complete_enrollment(
        code=code,
        redirect_uri=redirect,
        verifier=verifier,
        nonce=nonce,
        expected_email=expected_email,
        pending_label_id=pending_label_id,
    )
