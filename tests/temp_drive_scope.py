"""Temporary signed-grant contract probe with controlled identity exchange."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from pydantic import SecretStr
from sqlalchemy import text

from jarvis.attachments import AttachmentStore
from jarvis.connectors import GoogleTokenManager
from jarvis.db import create_engine
from jarvis.home_http import create_home_app
from jarvis.owner_gmail_state import owner_drive_reader, owner_workspace_tokens
from jarvis.phone import PhoneSlot
from jarvis.settings import Settings
from jarvis.work import WorkStore
from jarvis.workspace_enrollment import (
    ENROLLMENT_SCOPES,
    IDENTITY_SCOPES,
    OWNER_DRAFT_SCOPES,
    VerifiedTokens,
)
from jarvis.workspace_mcp import DRIVE_SCOPE, WorkspaceError

DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"


async def check(dsn: str) -> None:
    issued = ENROLLMENT_SCOPES

    async def exchange(*args, **kwargs) -> VerifiedTokens:
        return VerifiedTokens(
            "owner@example.test",
            "12345",
            issued,
            (
                "human-drive-fixture"
                if DRIVE_READONLY in issued
                else "controlled-access"
            ),
            "controlled-refresh",
            3600,
        )

    async def refresh(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "oauth2.googleapis.com"
        result = {
            "access_token": "refreshed-access",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": " ".join(sorted(issued)),
        }
        return httpx.Response(200, json=result)

    with (
        TemporaryDirectory() as temp,
        patch("jarvis.connectors.exchange_workspace_code", exchange),
    ):
        path = Path(temp)
        async with httpx.AsyncClient(transport=httpx.MockTransport(refresh)) as client:

            def manager(name, product=None):
                instance = GoogleTokenManager(
                    state_path=path / name,
                    client=client,
                    client_id="shared-human-client" if product else "agent-client",
                    client_secret="synthetic",
                    active_key_version="v1",
                    single_secret="A" * 43,
                    project_id="synthetic-google",
                    human_product=product,
                    now=lambda: datetime(2026, 11, 26, tzinfo=UTC),
                )
                instance.__dict__["_installation"] = "synthetic-host"
                return instance

            async def connect(instance, **kwargs):
                return await instance.complete_enrollment(
                    code="fixture",
                    redirect_uri="http://127.0.0.1/",
                    verifier="fixture",
                    nonce="fixture",
                    expected_email="owner@example.test",
                    pending_label_id=kwargs.pop("pending_label_id", None),
                    **kwargs,
                )

            agent = manager("agent.json")
            baseline = await connect(agent, pending_label_id="Label_123")
            drive_loss, full_loss = [], []
            agent.on_drive_loss = drive_loss.append
            agent.on_grant_loss = full_loss.append

            declined = await connect(agent, incremental_drive=True)
            assert declined.grant_id == baseline.grant_id
            assert declined.pending_label_id == baseline.pending_label_id
            assert DRIVE_SCOPE not in declined.scopes

            issued = ENROLLMENT_SCOPES | {DRIVE_SCOPE}
            upgraded = await connect(agent, incremental_drive=True)
            assert upgraded.grant_id == baseline.grant_id
            assert upgraded.pending_label_id == "Label_123"
            assert DRIVE_SCOPE in upgraded.scopes

            gmail = manager("gmail.json", "gmail")
            issued = OWNER_DRAFT_SCOPES
            gmail_enrolled = await connect(gmail, expected_subject="12345")
            client_file = path / "client.json"
            client_file.write_text(
                json.dumps(
                    {
                        "installed": {
                            "project_id": "synthetic-google",
                            "client_id": "shared-human-client",
                            "client_secret": "synthetic",
                        }
                    }
                )
            )
            client_file.chmod(0o600)
            settings = Settings.model_construct(
                google_oauth_client_id=SecretStr("agent-client"),
                google_oauth_state_path=path / "agent.json",
                connector_encryption_key_version="v1",
                connector_encryption_secret=SecretStr("A" * 43),
            )
            reader = owner_workspace_tokens(settings, path, client, product="drive")
            issued = IDENTITY_SCOPES | {DRIVE_READONLY}
            human = await connect(reader, expected_subject="12345")
            assert human.scopes == issued
            assert gmail.enrollment() == gmail_enrolled
            assert human.grant_id != gmail_enrolled.grant_id

            try:
                await connect(reader, expected_subject="another-subject")
            except WorkspaceError as exc:
                assert exc.kind == "grant_unavailable"
            else:
                raise AssertionError("read-only grant crossed subjects")

            issued = ENROLLMENT_SCOPES
            original = await agent.credential(upgraded.grant_id, None)
            refreshed = await agent.credential(upgraded.grant_id, original.access_token)
            assert refreshed.scopes == ENROLLMENT_SCOPES
            assert refreshed.pending_label_id == "Label_123"
            assert agent.enrollment().grant_id == baseline.grant_id
            assert drive_loss == [baseline.grant_id] and not full_loss
            assert reader.enrollment() == human and gmail.enrollment() == gmail_enrolled

            provider_reads = 0

            async def drive_api(request: httpx.Request) -> httpx.Response:
                nonlocal provider_reads
                provider_reads += 1
                assert request.method == "GET"
                assert request.url.host == "www.googleapis.com"
                assert request.headers["Authorization"] == "Bearer human-drive-fixture"
                return httpx.Response(
                    200,
                    json={
                        "files": [
                            {
                                "id": "owner_only_preview",
                                "name": "owner only.pdf",
                                "mimeType": "application/pdf",
                            }
                        ]
                    },
                )

            async def forbidden(*args, **kwargs):
                raise AssertionError("browsing should not submit an assistant turn")

            engine = create_engine(dsn)
            try:
                async with engine.connect() as conn:
                    assert (
                        await conn.scalar(
                            text("""
                        SELECT control_kind FROM message WHERE source_conversation_id='120123'
                        AND control_kind IS NOT NULL ORDER BY control_sequence DESC LIMIT 1
                    """)
                        )
                        == "pause"
                    )
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(drive_api)
                ) as api:
                    home = create_home_app(
                        database=engine,
                        scope="120123",
                        owner_timezone="UTC",
                        work=WorkStore(engine, "120123", owner_timezone="UTC"),
                        attachments=AttachmentStore(
                            engine,
                            "120123",
                            spool_directory=path,
                            scratch_directory=path,
                        ),
                        submit=forbidden,
                        pages=path,
                        phone=PhoneSlot(path / "phone.json", lambda: None),
                        drive_reader=owner_drive_reader(
                            settings, path, agent, client, api
                        ),
                    )
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=home),
                        base_url="http://fixture.test",
                    ) as browser:
                        listing = await browser.get("/api/drive/files?folder=root")
                        assert listing.status_code == 200, listing.text
                        assert listing.json()["items"][0]["id"] == "owner_only_preview"
                        other = await browser.get("/api/drive/other/owner_only_preview")
                        assert other.status_code == 404 and provider_reads == 1
                        await reader.disconnect(human.grant_id)
                        absent = await browser.get("/api/drive/files?folder=root")
                        assert absent.status_code == 424 and provider_reads == 1
                        assert agent.enrollment().grant_id == baseline.grant_id
            finally:
                await engine.dispose()
    print(
        "agent decline, incremental consent and drive-only loss preserve gmail standing authority; human grants isolated"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dsn")
    asyncio.run(check(parser.parse_args().dsn))
