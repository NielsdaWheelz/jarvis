"""Temporary synthetic predecessor-to-Drive custody proof."""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from hashlib import sha256
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text

from jarvis.db import create_engine


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
                == "0025"
            )
            origin = uuid4()
            await conn.execute(
                text("""INSERT INTO message
                    (id,role,text,source,source_conversation_id)
                    VALUES (:id,'owner','import fixture','web','120123')"""),
                {"id": origin},
            )
            for slot, state in enumerate(("ready", "pending", "failed")):
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
                if state == "ready":
                    await conn.execute(
                        text("""UPDATE attachment SET state='ready',put_entered_at=now(),
                        stored_at=now() WHERE id=:id"""),
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
            ],
        }
        broken = deepcopy(cut)
        broken["entries"][0]["sha256"] = sha256(b"wrong!!").hexdigest()
        try:
            async with engine.begin() as conn:
                await conn.run_sync(upgrade, broken)
        except RuntimeError as exc:
            assert "attachment" in str(exc) and "match" in str(exc), str(exc)
        else:
            raise AssertionError("a wrong byte manifest must stop the cut")
        async with engine.begin() as conn:
            assert (
                await conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "0025"
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
            assert "r2_account" not in updated[rows["ready"]]._mapping
        print(
            "cut rejected mismatched bytes and atomically mapped three historical states"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dsn")
    asyncio.run(check(parser.parse_args().dsn))
