"""Temporary synthetic predecessor-to-Drive custody proof."""

from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text

from jarvis.db import create_engine
from jarvis.drive_cut import load_stopped_drive_map


def upgrade(connection: Connection, cut: object) -> None:
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    config.attributes["drive_cut"] = cut
    command.upgrade(config, "head")


async def check(dsn: str) -> None:
    engine = create_engine(dsn)
    rows: dict[str, UUID] = {}
    digest = sha256(b"fixture").hexdigest()
    try:
        async with engine.begin() as conn:
            assert (
                await conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "0026"
            )
            origin = uuid4()
            await conn.execute(
                text("""INSERT INTO message
                    (id,role,text,source,source_conversation_id)
                    VALUES (:id,'owner','import fixture','web','120123')"""),
                {"id": origin},
            )
            for slot, state in enumerate(("ready", "pending", "failed", "deleted")):
                file = rows[state] = uuid4()
                await conn.execute(
                    text("""
                    WITH source AS (
                      SELECT jsonb_build_object('kind','web',
                        'submission_id',CAST(:id AS text),'slot',:slot) value)
                    INSERT INTO attachment
                      (id,source,source_key,r2_account,bucket,origin_message_id,
                       filename,media_type,advertised_size,size_bytes,sha256,state,created_at)
                    SELECT :id,value,jarvis_attachment_source_key(value),'fixture-r2',
                      'fixture-bucket',:origin,'return.pdf','application/pdf',7,7,
                      :digest,'pending',now() FROM source
                    """),
                    {"id": file, "origin": origin, "slot": slot, "digest": digest},
                )
                if state in ("ready", "deleted"):
                    await conn.execute(
                        text("""UPDATE attachment SET state='ready',put_entered_at=now(),
                        stored_at=now() WHERE id=:id"""),
                        {"id": file},
                    )
                if state == "deleted":
                    delete_id = uuid4()
                    await conn.execute(
                        text("""
                        INSERT INTO action (id,tool_name,arguments,execution_contract,
                            status,origin_message_id,completed_at)
                        VALUES (:id,'attachment.delete','{}','{}','succeeded',:origin,now())
                        """),
                        {"id": delete_id, "origin": origin},
                    )
                    await conn.execute(
                        text("""
                        UPDATE attachment SET state='deleting',delete_action_id=:action
                          WHERE id=:id
                        """),
                        {"id": file, "action": delete_id},
                    )
                    await conn.execute(
                        text(
                            "UPDATE attachment SET state='deleted',deleted_at=now() WHERE id=:id"
                        ),
                        {"id": file},
                    )
                if state == "failed":
                    await conn.execute(
                        text(
                            "UPDATE attachment SET state='failed',error='NotFound' WHERE id=:id"
                        ),
                        {"id": file},
                    )
        cut = {
            "subject": "1234567890",
            "parent": "synthetic_import_folder",
            "entries": [
                {
                    "source_uuid": str(rows["ready"]),
                    "prior_state": "ready",
                    "name": "return.pdf",
                    "size": 7,
                    "sha256": digest,
                    "drive_id": "synthetic_google_file",
                    "verified_at": "2026-11-26T00:00:00Z",
                },
                {
                    "source_uuid": str(rows["pending"]),
                    "prior_state": "pending",
                    "name": "return.pdf",
                    "size": 7,
                    "sha256": digest,
                },
                {
                    "source_uuid": str(rows["failed"]),
                    "prior_state": "failed",
                    "name": "return.pdf",
                    "size": 7,
                    "sha256": digest,
                    "reason": "NotFound",
                },
                {
                    "source_uuid": str(rows["deleted"]),
                    "prior_state": "deleted",
                    "name": "return.pdf",
                    "size": 7,
                    "sha256": digest,
                    "reason": "Deleted",
                },
            ],
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path, grant = root / "drive-cut.json", root / "google.json"
            path.write_text(json.dumps(cut))
            path.chmod(0o600)
            grant.write_text('{"subject":"wrong","status":"connected"}')
            grant.chmod(0o600)
            try:
                load_stopped_drive_map(path, spool=root, google_state=grant)
            except ValueError as exc:
                assert "another google subject" in str(exc)
            else:
                raise AssertionError("stopped map crossed an account")
            grant.write_text(
                json.dumps({"subject": cut["subject"], "status": "connected"})
            )
            pending = root / f"{rows['pending']}.{digest}"
            for data in (None, b"wrong!!"):
                if data is not None:
                    pending.write_bytes(data)
                try:
                    load_stopped_drive_map(path, spool=root, google_state=grant)
                except ValueError as exc:
                    assert "spool bytes do not match" in str(exc)
                else:
                    raise AssertionError("unverified spool would enter the cut")
            pending.write_bytes(b"fixture")
            cut = load_stopped_drive_map(
                path, spool=root, google_state=grant
            ).model_dump(mode="json")
        broken = deepcopy(cut)
        broken["entries"][0]["sha256"] = sha256(b"wrong!!").hexdigest()
        try:
            async with engine.begin() as conn:
                await conn.run_sync(upgrade, broken)
        except RuntimeError as exc:
            assert "attachment" in str(exc) and "match" in str(exc), str(exc)
        else:
            raise AssertionError("a wrong byte manifest must stop the cut")
        try:
            async with engine.begin() as conn:
                action = uuid4()
                await conn.execute(
                    text("""
                        INSERT INTO action (id,tool_name,arguments,execution_contract,
                            status,origin_message_id)
                        VALUES (:id,'attachment.delete','{}','{}','queued',:origin)
                    """),
                    {"id": action, "origin": origin},
                )
                await conn.run_sync(upgrade, cut)
        except RuntimeError as exc:
            assert "attachment.delete is queued" in str(exc)
        else:
            raise AssertionError("migration allowed a retired action to remain queued")
        async with engine.begin() as conn:
            assert (
                await conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "0026"
            )
            await conn.run_sync(upgrade, cut)
            updated = {
                row.id: row
                for row in (await conn.execute(text("SELECT * FROM attachment")))
            }
            assert updated[rows["ready"]].state == "filed"
            assert updated[rows["ready"]].drive_file_id == "synthetic_google_file"
            assert updated[rows["ready"]].sha256 == digest
            assert updated[rows["ready"]].stored_at is not None
            assert updated[rows["pending"]].state == "staged"
            assert updated[rows["failed"]].state == "unavailable"
            assert updated[rows["failed"]].error == "NotFound"
            assert updated[rows["deleted"]].state == "unavailable"
            assert updated[rows["deleted"]].disposition == "historical_deleted"
            assert updated[rows["deleted"]].deleted_at is not None
            assert "r2_account" not in updated[rows["ready"]]._mapping
        print(
            "cut held for wrong subject, lost spool, changed bytes and retired action; mapped four exact states"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dsn")
    asyncio.run(check(parser.parse_args().dsn))
