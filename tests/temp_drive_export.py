"""Temporary controlled proof of the stopped read-only attachment exporter."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[1]
DSN = os.environ.get("JARVIS_EXPORT_DATABASE_URL", "")
EVIDENCE = Path(os.environ.get("JARVIS_EXPORT_TEST_EVIDENCE", Path.home()))


def main() -> None:
    loader = importlib.machinery.SourceFileLoader(
        "drive_export", str(ROOT / "deploy" / "drive-export")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    export = importlib.util.module_from_spec(spec)
    loader.exec_module(export)
    names = {state: uuid4() for state in ("ready", "pending", "failed")}
    source = uuid4()
    data = b"test pdf"
    digest = hashlib.sha256(data).hexdigest()
    with psycopg.connect(DSN) as conn:
        conn.execute(
            """INSERT INTO message (id,role,text,source,source_conversation_id)
               VALUES (%s,'owner','export fixture','web','120123')""",
            (source,),
        )
        for slot, id in enumerate(names.values()):
            obj = json.dumps({"kind": "web", "submission_id": str(id), "slot": slot})
            conn.execute(
                """INSERT INTO attachment
                      (id,source,source_key,r2_account,bucket,origin_message_id,
                       filename,media_type,advertised_size,size_bytes,sha256,state,created_at)
                    VALUES (%s,%s::jsonb,jarvis_attachment_source_key(%s::jsonb),
                       'fixture-r2','fixture-bucket',%s,'return.pdf',
                       'application/pdf',%s,%s,%s,'pending',now())""",
                (id, obj, obj, source, len(data), len(data), digest),
            )
        conn.execute(
            """UPDATE attachment SET state='ready',put_entered_at=now(),stored_at=now()
               WHERE id=%s""",
            (names["ready"],),
        )
        conn.execute(
            "UPDATE attachment SET state='failed',error='NotFound' WHERE id=%s",
            (names["failed"],),
        )

    ready = f"attachments/{names['ready']}/original"
    stale = f"attachments/{names['failed']}/original"
    orphan = f"attachments/{uuid4()}/original"

    class Bucket:
        def __init__(self):
            self.objects = {ready: data, stale: data, orphan: data}
            self.reads = []

        def get_paginator(self, method):
            assert method == "list_objects_v2"
            return self

        def paginate(self, *, Bucket):
            assert Bucket == "fixture-bucket"
            for key, body in self.objects.items():
                yield {
                    "Contents": [{"Key": key, "Size": len(body), "ETag": '"frozen"'}]
                }

        def get_object(self, *, Bucket, Key, IfMatch):
            assert (Bucket, IfMatch) == ("fixture-bucket", '"frozen"')
            self.reads.append(Key)
            body = self.objects[Key]
            return {"Body": io.BytesIO(body), "ContentLength": len(body)}

    with TemporaryDirectory(dir=EVIDENCE, prefix="drive-export-proof-") as directory:
        root = Path(directory)
        spool = root / "spool"
        spool.mkdir()
        pending = spool / f"{names['pending']}.{digest}"
        pending.write_bytes(data)
        (spool / "unlisted.partial").write_bytes(b"stale")
        token, grant = root / "r2.json", root / "google.json"
        token.touch(mode=0o600)
        grant.touch(mode=0o600)
        token.write_text('{"access_key_id":"fixture","secret_access_key":"fixture"}')
        grant.write_text('{"subject":"fixture_owner","status":"connected"}')
        args = argparse.Namespace(
            spool=spool,
            account="fixture-r2",
            bucket="fixture-bucket",
            credentials=token,
            google_state=grant,
            parent="fixture_folder",
            out=root / "export",
        )
        bucket = Bucket()
        with patch("boto3.client", return_value=bucket):
            export.run(args)
            path = args.out / "inventory.json"
            import_loader = importlib.machinery.SourceFileLoader(
                "drive_import", str(ROOT / "deploy" / "drive-import")
            )
            import_spec = importlib.util.spec_from_loader(
                import_loader.name, import_loader
            )
            assert import_spec is not None
            importer = importlib.util.module_from_spec(import_spec)
            import_loader.exec_module(importer)
            inventory = importer.read_inventory(
                path, hashlib.sha256(path.read_bytes()).hexdigest(), args.out / "blobs"
            )
            assert (inventory["subject"], inventory["parent"], inventory["rows"]) == (
                "fixture_owner",
                "fixture_folder",
                3,
            )
            assert (args.out / "blobs" / str(names["ready"])).read_bytes() == data
            assert (args.out / "blobs" / str(names["pending"])).read_bytes() == data
            assert bucket.reads == [ready], bucket.reads
            report = json.loads((args.out / "report.json").read_bytes())
            assert report["orphans"] == [orphan]
            assert report["retained_stale"] == [stale]
            assert report["spool_orphans"] == ["unlisted.partial"]
            assert {row["prior_state"] for row in inventory["entries"]} == set(names)
            assert pending.read_bytes() == data
            args.out = root / "damaged"
            bucket.objects[ready] = b"badbytes"
            pending.unlink()
            try:
                export.run(args)
            except export.Failure:
                pass
            else:
                raise AssertionError("unverified sources passed export")
            assert not (args.out / "inventory.json").exists()
            damaged = json.loads((args.out / "report.json").read_bytes())
            assert damaged["status"] == "held"
            assert len(damaged["blocked"]) == 2
            assert not any((args.out / "blobs").iterdir())
            assert any("bytes differ" in row["reason"] for row in damaged["blocked"])
            bucket.objects[ready] = data
            pending.write_bytes(data)
            with psycopg.connect(DSN) as conn:
                conn.execute(
                    "UPDATE attachment SET put_entered_at=now() WHERE id=%s",
                    (names["pending"],),
                )
            args.out = root / "entered"
            try:
                export.run(args)
            except export.Failure:
                pass
            else:
                raise AssertionError("entered legacy upload passed export")
            entered = json.loads((args.out / "report.json").read_bytes())
            assert entered["blocked"] == [
                {
                    "source_uuid": str(names["pending"]),
                    "state": "pending",
                    "reason": "pending row has unresolved predecessor storage evidence",
                }
            ]
            assert not (args.out / "inventory.json").exists()
            with psycopg.connect(DSN) as conn:
                deletion = uuid4()
                conn.execute(
                    """INSERT INTO action (id,tool_name,arguments,execution_contract,
                             status,origin_message_id,attempts)
                        VALUES (%s,'attachment.delete','{}','{}','executing',%s,1)""",
                    (deletion, source),
                )
                conn.execute(
                    """UPDATE attachment SET state='deleting',delete_action_id=%s
                       WHERE id=%s""",
                    (deletion, names["ready"]),
                )
            args.out = root / "deleting"
            reads_before = list(bucket.reads)
            try:
                export.run(args)
            except export.Failure:
                pass
            else:
                raise AssertionError("deletion in progress passed export")
            deleting = json.loads((args.out / "report.json").read_bytes())
            assert {row["state"] for row in deleting["blocked"]} == {
                "pending",
                "deleting",
            }
            assert bucket.reads == reads_before
            assert not (args.out / "inventory.json").exists()
    print("stopped export assertions passed")


if __name__ == "__main__":
    main()
