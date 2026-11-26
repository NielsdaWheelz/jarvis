"""ADR 0120 temporary proof through real HTTP, filesystem and PostgreSQL."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import sys
from datetime import UTC, datetime
from inspect import signature
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
from llm_tools import ParsedJson, ReplayPolicy, ToolEffect, raw_input_digest
from sqlalchemy import insert, select, update


async def run() -> None:
    from jarvis.actions import ExecutionContract
    from jarvis.attachments import AttachmentStore
    from jarvis.db import action, attachment, create_engine
    from jarvis.home_pages import HOME_ORIGIN
    from jarvis.messages import MessageStore
    from jarvis.ownership import deployment_ownership
    from jarvis.phone import PhoneSlot

    engine = create_engine(os.environ["JARVIS_DRIVE_CUSTODY_TEST_DSN"])
    try:
        async with deployment_ownership(engine) as database:
            with TemporaryDirectory(prefix="jarvis-drive-custody-") as state:
                scope, root = "120123", Path(state)
                spool = root / "spool"
                scratch = root / "scratch"
                scratch.mkdir()
                store = MessageStore(database)
                assert await store.current_control(scope) == "pause"
                from jarvis.home_http import create_home_app

                predecessor = "r2_account" in signature(store.submit).parameters
                if predecessor:
                    from jarvis.attachment_sources import AttachmentSources

                    attachments = AttachmentStore(
                        database,
                        scope,
                        spool_directory=spool,
                        cache_directory=root / "scratch",
                        r2_account="fixture",
                        bucket="fixture",
                        s3_client=object(),
                        sources=AttachmentSources(google=None),
                        mutation_admitted=None,
                    )
                    submit_config = {"r2_account": "fixture", "bucket": "fixture"}
                else:
                    attachments = AttachmentStore(
                        database,
                        scope,
                        spool_directory=spool,
                        scratch_directory=scratch,
                    )
                    submit_config = {"spool": spool}

                async def submit(submission_id, text, ref, uploads):
                    result = await store.submit(
                        submission_id,
                        text,
                        ref,
                        uploads,
                        scope=scope,
                        **submit_config,
                    )
                    return result.message.id, result.inserted

                app = create_home_app(
                    database=database,
                    scope=scope,
                    owner_timezone="UTC",
                    work=None,
                    attachments=attachments,
                    submit=submit,
                    pages=root,
                    **({"spool": spool} if predecessor else {}),
                    phone=PhoneSlot(root / "phone", lambda: None),
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=HOME_ORIGIN,
                    headers={
                        "Origin": HOME_ORIGIN,
                        "X-Jarvis-Viewer-Contract": "drive-files",
                    },
                ) as client:

                    async def send(identifier, payload):
                        return await client.put(
                            f"/api/messages/{identifier}",
                            files=[
                                ("message", (None, json.dumps({"text": ""}))),
                                ("file", ("return.pdf", payload, "application/pdf")),
                            ],
                        )

                    submission, data = uuid4(), b"%PDF-1.4\nsynthetic return"
                    original = await send(submission, data)
                    assert original.status_code == 201, original.text
                    retry = await client.get(f"/api/submissions/{submission}")
                    assert retry.json() == original.json(), retry.text
                    pending = await store.pending_inputs(
                        source_conversation_id=scope, limit=64
                    )
                    origin = UUID(original.json()["id"])
                    assert origin in {value.id for value in pending}, (
                        "durably received upload was blocked on remote storage"
                    )
                    async with database.connect() as connection:
                        rows = await connection.execute(
                            select(attachment).where(
                                attachment.c.origin_message_id == origin
                            )
                        )
                        source = rows.mappings().one()
                    assert source["state"] == "staged"
                    stale = await client.put(
                        f"/api/messages/{uuid4()}",
                        headers={"X-Jarvis-Viewer-Contract": "retired"},
                        json={"text": "stale client"},
                    )
                    assert stale.status_code == 426
                    download = await client.get(
                        f"/api/drive/origin/{source['id']}/content"
                    )
                    assert download.content == data
                    native = (await attachments.open(source["id"])).value
                    assert native["type"] == "Success", native
                    path = Path(native["value"]["local_path"])
                    assert path.read_bytes() == data
                    assert path.stat().st_mode & 0o020 == 0
                    await attachments.reset_scratch()
                    assert not path.exists()
                    with patch("jarvis.attachments.SPOOL_MAX_BYTES", len(data)):
                        assert (await send(submission, data)).json() == original.json()
                        assert (await send(submission, data + b"x")).status_code == 409
                        assert (await send(uuid4(), data)).status_code == 413
                        plain = await client.put(
                            f"/api/messages/{uuid4()}", json={"text": "hello"}
                        )
                        assert plain.status_code == 201, plain.text
                    with patch("jarvis.home_uploads.BODY_LIMIT", len(data)):
                        assert (await send(uuid4(), data)).status_code == 413
                    assert len(list(spool.iterdir())) == 1
                    from jarvis.attachment_sources import AttachmentSources
                    from jarvis.workspace_mcp import WorkspaceError
                    from jarvis.workspace_write_models import SubmissionSource

                    async def unused_fence():
                        raise AssertionError("spool source should use no provider")

                    marked = AttachmentSources(attachments, None)
                    submission_source = SubmissionSource(submission_id=source["id"])
                    (actual_file,) = spool.iterdir()
                    alternate = actual_file.with_name(".source-fault")
                    actual_file.rename(alternate)
                    try:
                        async with marked.open(
                            submission_source,
                            invocation_id="missing-source",
                            before_send=unused_fence,
                        ):
                            raise AssertionError("missing source was yielded")
                    except WorkspaceError as exc:
                        assert exc.known_no_effect, (
                            "pre-effect read was treated as unknown"
                        )
                    finally:
                        alternate.rename(actual_file)
                    with patch(
                        "jarvis.attachment_sources.tempfile.NamedTemporaryFile",
                        side_effect=OSError("synthetic temp disk full"),
                    ):
                        async with marked.open(
                            submission_source,
                            invocation_id="no-second-copy",
                            before_send=unused_fence,
                        ) as upload:
                            assert upload.path == actual_file
                            assert upload.path.read_bytes() == data
                    assert list(spool.iterdir()) == [actual_file]

                    from jarvis.attachments import CustodyConflict

                    # In-flight transport competes for the same native scratch.
                    with patch("jarvis.attachments.SCRATCH_MAX_BYTES", 4):
                        async with attachments.transfer_scratch(2) as transfer_dir:
                            assert transfer_dir == scratch
                            try:
                                await attachments.materialize(
                                    io.BytesIO(b"abc"),
                                    3,
                                    hashlib.sha256(b"abc").hexdigest(),
                                )
                            except CustodyConflict as exc:
                                assert str(exc) == "ScratchFull"
                            else:
                                raise AssertionError(
                                    "transfer scratch was not accounted"
                                )
                        path = await attachments.materialize(
                            io.BytesIO(b"abc"), 3, hashlib.sha256(b"abc").hexdigest()
                        )
                        assert path.read_bytes() == b"abc"
                        await attachments.reset_scratch()

                    # Replay the saved id after an executor restart.
                    async def create_action(
                        tool, attachment_id, *, status="executing", attempts=1
                    ):
                        id = uuid4()
                        args = {
                            "request_ref": str(origin),
                            "existing_action_ref": None,
                            "arguments": {"id": str(attachment_id)},
                        }
                        contract = ExecutionContract(
                            schema_version="jarvis.action.v2",
                            tool_contract_revision="fixture",
                            implementation_revision="fixture",
                            policy_revision="fixture",
                            plan_revision="fixture",
                            tool_effect=ToolEffect.Write,
                            replay_policy=ReplayPolicy.ReDispatchable,
                            input_digest=raw_input_digest(ParsedJson(args)),
                            max_attempts=2,
                            claim_id="fixture",
                            through_checkpoint=str(origin),
                            input_message_ids=(str(origin),),
                            model_step_ordinal=1,
                        )
                        async with database.begin() as connection:
                            await connection.execute(
                                insert(action).values(
                                    id=id,
                                    status=status,
                                    tool_name=tool,
                                    attempts=attempts,
                                    origin_message_id=origin,
                                    execution_contract=contract.as_json(),
                                    arguments=args,
                                )
                            )
                        return id

                    local_id = source["id"]
                    first = await create_action("drive.create", local_id)
                    async with database.begin() as connection:
                        await attachments.bind(connection, local_id, first)
                    await attachments.acknowledge(
                        local_id, first, "google-owner", "known-id"
                    )
                    assert (await attachments.inspect(local_id)).state == "created"
                    denied = await create_action("submission.abandon", local_id)
                    assert (await attachments.abandon(denied, local_id)).value[
                        "error"
                    ] == {"type": "FilingInProgress", "id": str(local_id)}
                    restarted = AttachmentStore(
                        database,
                        scope,
                        spool_directory=spool,
                        scratch_directory=scratch,
                    )
                    await restarted.acknowledge(
                        local_id, first, "google-owner", "known-id"
                    )
                    await restarted.verify(local_id, first)
                    await restarted.verify(local_id, first)
                    reopened = await restarted.inspect(local_id)
                    assert (reopened.state, reopened.drive_file_id) == (
                        "filed",
                        "known-id",
                    )
                    assert not list(spool.iterdir())
                    assert (await restarted.open(local_id)).value["error"][
                        "drive_file_id"
                    ] == "known-id"

                    # Lost acknowledgement forbids rebinding and survives abandonment.
                    second_message = await send(uuid4(), data)
                    assert second_message.status_code == 201
                    async with database.connect() as connection:
                        second_id = await connection.scalar(
                            select(attachment.c.id).where(
                                attachment.c.origin_message_id
                                == UUID(second_message.json()["id"])
                            )
                        )
                    second = await create_action("drive.create", second_id)
                    async with database.begin() as connection:
                        await restarted.bind(connection, second_id, second)
                    await restarted.mark_uncertain(second_id, second)
                    try:
                        async with database.begin() as connection:
                            await restarted.bind(connection, second_id, first)
                    except CustodyConflict:
                        pass
                    else:
                        raise AssertionError("lost create was rebound")
                    async with database.begin() as connection:
                        await connection.execute(
                            update(action)
                            .where(action.c.id == second)
                            .values(
                                status="uncertain",
                                completed_at=datetime.now(UTC),
                                result={"type": "known-unknown-fixture"},
                            )
                        )
                    abandon_id = await create_action("submission.abandon", second_id)
                    abandoned = (await restarted.abandon(abandon_id, second_id)).value
                    assert abandoned["value"]["drive_effect_unknown"]
                    assert (
                        await restarted.abandon(abandon_id, second_id)
                    ).value == abandoned
                    gone = await restarted.inspect(second_id)
                    assert (gone.state, gone.disposition) == (
                        "unavailable",
                        "abandoned_uncertain",
                    )
                    assert not list(spool.iterdir())

    finally:
        await engine.dispose()


async def run_mail() -> None:
    from jarvis.mail_files import (
        MAIL_MAX_BYTES,
        DriveMailFileRef,
        MailFileFailure,
        MailFiles,
    )
    from jarvis.workspace_mcp import WorkspaceError
    from jarvis.workspace_write_models import DriveSourceFile

    class Drive:
        data = b"a" * MAIL_MAX_BYTES
        calls = 0

        async def drive_file(
            self,
            subject,
            id,
            export_type,
            *,
            destination,
            maximum,
            invocation_id,
            before_send,
        ):
            assert (subject, id, export_type) == ("owner-subject", "doc", None)
            assert (
                destination.parent.parent == Path(directory) and destination.name == "1"
            )
            await before_send()
            self.calls += 1
            if len(self.data) > maximum:
                raise WorkspaceError("response_too_large")
            destination.write_bytes(self.data)
            return DriveSourceFile(
                destination,
                "tax.pdf",
                "application/pdf",
                len(self.data),
                hashlib.sha256(self.data).hexdigest(),
            )

    async def fence():
        pass

    with TemporaryDirectory(prefix="jarvis-drive-mail-") as directory:
        drive = Drive()
        files = MailFiles(drive, (), stage_root=Path(directory))
        ref = DriveMailFileRef(kind="drive_file", subject="owner-subject", id="doc")
        action_id = uuid4()
        (staged,) = await files.stage(
            action_id,
            (ref,),
            invocation_id="mail-compose",
            before_send=fence,
        )
        assert staged.size_bytes == MAIL_MAX_BYTES
        drive.data = b"b" * MAIL_MAX_BYTES
        assert await files.read(action_id, 1, staged) == b"a" * MAIL_MAX_BYTES
        assert drive.calls == 1, "sending approved attachment re-opened live Drive"
        await files.discard(action_id)
        drive.data = b"c" * (MAIL_MAX_BYTES + 1)
        try:
            await files.stage(
                uuid4(), (ref,), invocation_id="over-capacity", before_send=fence
            )
        except MailFileFailure as exc:
            assert exc.detail.reason == "drive_response_too_large"
        else:
            raise AssertionError("over-capacity Drive source was staged")
        assert not list(Path(directory).iterdir()), "denial left an action stage"

        from jarvis.mail_files import native_file, publish_native
        from jarvis.read_tools import ATTACHMENT_MAX_BYTES

        root = Path(directory)
        path = root / "report.bin"
        with path.open("wb") as f:
            f.seek(ATTACHMENT_MAX_BYTES - 1)
            f.write(b"z")
        publication = publish_native(path, None, root=root)
        assert publication.file.size_bytes == ATTACHMENT_MAX_BYTES
        with native_file(root, publication.ref) as (manifest, original):
            assert (
                manifest.sha256 == hashlib.file_digest(original, "sha256").hexdigest()
            )
        with path.open("ab") as f:
            f.write(b"!")
        try:
            publish_native(path, None, root=root)
        except ValueError as exc:
            assert str(exc) == "file exceeds 100 mib"
        else:
            raise AssertionError("over-capacity native publication was accepted")
        assert not list(root.glob(".prepare-*"))


if __name__ == "__main__":
    if "--mail-only" not in sys.argv:
        asyncio.run(run())
    asyncio.run(run_mail())
    print("custody assertions passed")
