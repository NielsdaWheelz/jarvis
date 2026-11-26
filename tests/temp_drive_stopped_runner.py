"""Temporary proof through the actual stopped cut runner on synthetic databases."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from hashlib import sha256
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url

from jarvis._atomic_json import replace_private_json
from jarvis.db import create_engine


async def check(source_dsn, copy_dsn, source_container, copy_container):
    repo = Path(
        os.environ.get(
            "JARVIS_DRIVE_TEST_SOURCE_ROOT", Path(__file__).resolve().parents[1]
        )
    ).resolve()
    with TemporaryDirectory() as directory:
        base = Path(directory).resolve()
        proof, snapshot = base / "proof", base / "snapshot"
        proof.mkdir(mode=0o700)
        snapshot.mkdir(mode=0o700)
        root = base / "install"
        source_commit, target_commit = "a" * 40, "b" * 40
        source_dir = root / "releases" / source_commit
        target_dir = root / "releases" / target_commit
        source_dir.mkdir(parents=True)
        (target_dir / "deploy").mkdir(parents=True)
        for release, commit in [
            (source_dir, source_commit),
            (target_dir, target_commit),
        ]:
            (release / "RELEASE.json").write_text(json.dumps({"commit": commit}))
        (root / "current").symlink_to(source_dir)
        script = target_dir / "deploy" / "prepare-cutover"
        shutil.copyfile(repo / "deploy" / "prepare-cutover", script)
        shutil.copyfile(repo / "alembic.ini", target_dir / "alembic.ini")
        (target_dir / "migrations").symlink_to(repo / "migrations")
        sys.path.insert(0, str(repo / "deploy"))
        loader = SourceFileLoader("prepared_cut_probe", str(script))
        module = module_from_spec(spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        module.ROOT = root
        module.STATE = base / "state"
        module.DECLARATIONS = base / "declarations"
        module.OWNER_GMAIL_DIRECTORY = base / "human"
        module.DECLARATIONS.mkdir(mode=0o700)
        for name, data in (
            ("jarvis.env", "JARVIS_OWNER_SCOPE=120123\n"),
            ("memory.json", "{}"),
            ("codex-host.json", "{}"),
        ):
            (module.DECLARATIONS / name).write_text(data)
        (module.STATE / "runtime" / "uploads").mkdir(mode=0o700, parents=True)
        (module.STATE / "connectors").mkdir(mode=0o700)
        replace_private_json(
            module.STATE / "connectors" / "google-oauth-state.json",
            {"status": "connected", "subject": "isolated_subject"},
        )
        identifier, origin = uuid4(), uuid4()
        data = b"owner fixture bytes"
        digest = sha256(data).hexdigest()
        live_spool = module.STATE / "runtime" / "uploads" / f"{identifier}.{digest}"
        live_spool.write_bytes(data)
        shutil.copytree(module.STATE, snapshot / "private-state")
        shutil.copytree(module.DECLARATIONS, snapshot / "declarations")
        source = create_engine(source_dsn)
        restored = create_engine(copy_dsn)
        try:
            async with source.begin() as conn:
                await conn.execute(
                    text("""
                    INSERT INTO message
                      (id,role,text,source,source_conversation_id,created_at)
                    VALUES (:id,'owner','fixture','web','120123','2026-11-26T00:00:00Z')
                    """),
                    {"id": origin},
                )
                await conn.execute(
                    text("""
                    WITH source AS (SELECT jsonb_build_object(
                      'kind','web','submission_id',CAST(:id AS text),'slot',0) value)
                    INSERT INTO attachment
                      (id,source,source_key,r2_account,bucket,origin_message_id,
                       filename,media_type,advertised_size,size_bytes,sha256,state,created_at)
                    SELECT :id,value,jarvis_attachment_source_key(value),'fixture','fixture',
                      :origin,'return.txt','text/plain',:size,:size,:digest,
                      'pending','2026-11-26T00:00:00Z' FROM source
                    """),
                    {
                        "id": identifier,
                        "origin": origin,
                        "size": len(data),
                        "digest": digest,
                    },
                )
            url = make_url(source_dsn)
            with (snapshot / "database.dump").open("wb") as dump:
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        source_container,
                        "pg_dump",
                        "-Fc",
                        "-U",
                        "postgres",
                        "-d",
                        url.database,
                    ],
                    stdout=dump,
                    check=True,
                )
            with (snapshot / "database.dump").open("rb") as dump:
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        copy_container,
                        "pg_restore",
                        "--exit-on-error",
                        "-U",
                        "postgres",
                        "-d",
                        make_url(copy_dsn).database,
                    ],
                    stdin=dump,
                    check=True,
                )
            async with source.begin() as conn:
                source_facts = await module.inventory(conn, "120123")
            source_release = {"commit": source_commit, "schema": "0026"}
            target_release = {"commit": target_commit, "schema": "0027"}
            binding = {
                "id": "synthetic-drive-cut",
                "source": source_release,
                "target": target_release,
            }
            manifest = {
                "format": "jarvis-stopped-snapshot.v1",
                "change": binding["id"],
                "source": source_release,
                "target": target_release,
                "owner_scope": "120123",
                "database": [url.host, url.port, url.database],
                "copies": {
                    name: module.copy_digest(snapshot / name)
                    for name in ("private-state", "declarations")
                },
                "dump_sha256": module.file_digest(snapshot / "database.dump"),
                "original_facts": source_facts,
            }
            replace_private_json(snapshot / "SNAPSHOT.json", manifest)
            with patch.dict(os.environ, {"JARVIS_MIGRATION_DATABASE_URL": copy_dsn}):
                await module.inspect_restored("verify-restored-source", snapshot, proof)
                document = {
                    "subject": "wrong_subject",
                    "parent": "fixture_folder",
                    "entries": [
                        {
                            "source_uuid": str(identifier),
                            "prior_state": "pending",
                            "name": "return.txt",
                            "size": len(data),
                            "sha256": digest,
                        }
                    ],
                }
                path = proof / "drive-cut.json"
                replace_private_json(path, document)
                try:
                    await module.inspect_restored(
                        "migrate-restored-drive",
                        snapshot,
                        proof,
                        module.file_digest(path),
                    )
                except ValueError as exc:
                    assert "another google subject" in str(exc)
                else:
                    raise AssertionError("wrong subject allowed")
                document["subject"] = "isolated_subject"
                replace_private_json(path, document)
                try:
                    await module.inspect_restored(
                        "migrate-restored-drive", snapshot, proof, "0" * 64
                    )
                except RuntimeError as exc:
                    assert "approved digest" in str(exc)
                else:
                    raise AssertionError("old map hash allowed")
                await module.inspect_restored(
                    "migrate-restored-drive", snapshot, proof, module.file_digest(path)
                )
            async with restored.begin() as conn:
                target_facts = await module.inventory(conn, "120123")
                assert (
                    await conn.scalar(text("SELECT state FROM attachment")) == "staged"
                )
            qualification = proof / "qualification.json"
            replace_private_json(
                qualification,
                {
                    **module.rehearsal_binding(manifest),
                    "target_facts_sha256": module.json_digest(target_facts),
                    "drive_map_sha256": module.file_digest(path),
                    "compatibility": {
                        "outcome": "compatible",
                        "control": source_facts["control"],
                        "findings": [],
                    },
                },
            )
            with patch.dict(
                os.environ,
                {
                    "JARVIS_DATABASE_URL": source_dsn,
                    "JARVIS_MIGRATION_DATABASE_URL": source_dsn,
                },
            ):
                live_spool.write_bytes(b"corrupted live bytes")
                for operation in ("verify-rehearsal", "migrate"):
                    try:
                        await module.cut(
                            operation, snapshot, binding, {}, qualification
                        )
                    except ValueError as exc:
                        assert "spool bytes do not match" in str(exc)
                    else:
                        raise AssertionError("intact snapshot masked bad live spool")
                async with source.connect() as conn:
                    assert (
                        await conn.scalar(
                            text("SELECT version_num FROM alembic_version")
                        )
                        == "0026"
                    )
                live_spool.write_bytes(data)
                (snapshot.parent / "applying").mkdir()
                for operation in ("verify-rehearsal", "migrate"):
                    await module.cut(operation, snapshot, binding, {}, qualification)
                (root / "current").unlink()
                (root / "current").symlink_to(target_dir)
                await module.cut("verify-target", snapshot, binding, {}, qualification)
            print(
                "stopped runner refused wrong subject, changed map, bad live spool and applied verified cut"
            )
        finally:
            await source.dispose()
            await restored.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dsn")
    parser.add_argument("rehearsal_dsn")
    parser.add_argument("source_container")
    parser.add_argument("copy_container")
    args = parser.parse_args()
    asyncio.run(
        check(
            args.source_dsn,
            args.rehearsal_dsn,
            args.source_container,
            args.copy_container,
        )
    )
