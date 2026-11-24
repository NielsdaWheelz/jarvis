"""Send private home notice identifiers using Firebase Cloud Messaging HTTP v1."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import partial
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

import httpx
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from requests import Session

type NoticeKind = Literal["reply", "question"]

PROJECT_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CREDENTIALS = Path("/var/lib/jarvis/connectors/fcm-sender.json")


@dataclass(frozen=True, slots=True)
class PushFailure:
    kind: Literal["configuration", "temporary", "rejected", "unregistered", "slot"]
    status: int | None = None
    retry_after: float = 0


class FcmSender:
    """Only serial delivery uses the credentials and the fixed Google endpoints."""

    def __init__(
        self, http: httpx.AsyncClient, project: str | None, account: Path = CREDENTIALS
    ) -> None:
        self._http = http
        self._project = project
        self._account = account
        self._credentials: Credentials | None = None

    def _access_token(self) -> str:
        if self._credentials is None:
            raw: object = json.loads(self._account.read_bytes())
            if not isinstance(raw, dict):
                raise ValueError("expected one service account")
            info = cast("dict[str, object]", raw)
            if (
                info.get("type") != "service_account"
                or info.get("project_id") != self._project
                or info.get("token_uri") != TOKEN_URL
                or info.get("universe_domain", "googleapis.com") != "googleapis.com"
            ):
                raise ValueError("unexpected FCM service account")
            self._credentials = Credentials.from_service_account_info(  # pyright: ignore[reportUnknownMemberType]
                info, scopes=[PROJECT_SCOPE]
            )
        if not self._credentials.valid:
            with Session() as session:
                session.trust_env = False
                self._credentials.refresh(  # pyright: ignore[reportUnknownMemberType]
                    partial(Request(session), timeout=10)
                )
        token = cast(object, self._credentials.token)  # pyright: ignore[reportUnknownMemberType]
        if not isinstance(token, str):
            raise ValueError("FCM service account did not return a token")
        return token

    async def send(
        self,
        fid: str,
        notice_id: UUID,
        message_id: UUID,
        kind: NoticeKind,
    ) -> str | PushFailure:
        if self._project is None:
            return PushFailure("configuration")
        try:
            token = await asyncio.to_thread(self._access_token)
        except (OSError, TypeError, ValueError, GoogleAuthError):
            self._credentials = None
            return PushFailure("configuration")

        try:
            response = await self._http.post(
                f"https://fcm.googleapis.com/v1/projects/{self._project}/messages:send",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "message": {
                        "fid": fid,
                        "data": {
                            "notice_id": str(notice_id),
                            "message_id": str(message_id),
                            "kind": kind,
                        },
                        "android": {
                            "priority": "HIGH" if kind == "question" else "NORMAL",
                            "ttl": "2419200s",
                            "restricted_package_name": "dev.niels.jarvis",
                        },
                    }
                },
                timeout=10,
            )
        except httpx.RequestError:
            return PushFailure("temporary")

        try:
            body: object = response.json()
        except ValueError:
            body = None
        payload = cast("dict[str, object]", body) if isinstance(body, dict) else {}
        status = response.status_code
        if status == 200:
            name = payload.get("name")
            prefix = f"projects/{self._project}/messages/"
            if (
                isinstance(name, str)
                and name.startswith(prefix)
                and name[len(prefix) :]
            ):
                return name
            return PushFailure("temporary", status)

        error = payload.get("error")
        if status == 404 and isinstance(error, dict):
            details = cast("dict[str, object]", error).get("details")
            if isinstance(details, list):
                for detail in cast("list[object]", details):
                    if not isinstance(detail, dict):
                        continue
                    entry = cast("dict[str, object]", detail)
                    if (
                        entry.get("@type")
                        == "type.googleapis.com/google.firebase.fcm.v1.FcmError"
                        and entry.get("errorCode") == "UNREGISTERED"
                    ):
                        return PushFailure("unregistered", status)

        if status == 429 or status == 408 or 500 <= status < 600:
            retry_after = 60.0 if status == 429 else 0.0
            if raw := response.headers.get("Retry-After"):
                try:
                    seconds: float = (
                        int(raw)
                        if raw.isascii() and raw.isdecimal()
                        else (
                            cast(datetime, parsedate_to_datetime(raw))
                            - datetime.now(UTC)
                        ).total_seconds()
                    )
                    retry_after = max(retry_after, seconds)
                except (ValueError, TypeError, OverflowError):
                    pass
            return PushFailure("temporary", status, retry_after)

        if status in (401, 403):
            self._credentials = None
        return PushFailure("rejected", status)
