"""Restore and verify one backup without starting any Jarvis writer."""

import asyncio
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
from memory_snapshot import (
    POSTGRES_BIN,
    RESTORE_ROLES,
    coverage,
    database_inventory,
    pg_environment,
    schema_inventory,
    table_inventory,
    witness_digest,
)
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
from universal_memory import MemoryStore

INPUT = Path("/input")
WORK = Path("/work")
DATA = WORK / "pgdata"
SOCKET = Path("/tmp/jarvis-memory-socket")
LOCK = Path("/opt/jarvis/uv.lock")
READER = "jarvis_backup"


def postgres_command(program, *args):
    subprocess.run(
        ["runuser", "-u", "postgres", "--", POSTGRES_BIN / program, *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def prepare_database(expected, password):
    with psycopg.connect(
        dbname="postgres", user="postgres", host=str(SOCKET), autocommit=True
    ) as admin:
        for role in RESTORE_ROLES:
            if role == READER:
                admin.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(password)
                    )
                )
            else:
                admin.execute(
                    sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role))
                )
        if (
            expected["name"],
            expected["owner"],
            expected["encoding"],
            expected["locale_provider"],
        ) != ("jarvis", "jarvis_migrator", "UTF8", "c"):
            raise RuntimeError("unsupported source database identity")
        admin.execute(
            sql.SQL("""
                CREATE DATABASE jarvis
                OWNER jarvis_migrator TEMPLATE template0 ENCODING 'UTF8'
                LOCALE_PROVIDER libc LC_COLLATE {} LC_CTYPE {}
            """).format(
                sql.Literal(expected["collate"]), sql.Literal(expected["ctype"])
            )
        )
        admin.execute("REVOKE ALL ON DATABASE jarvis FROM PUBLIC, jarvis_migrator")
        admin.execute("SET ROLE jarvis_migrator")
        for recipient, grantor, privilege, grantable in expected["acl"]:
            if (
                recipient not in (*RESTORE_ROLES, "PUBLIC")
                or grantor != "jarvis_migrator"
                or privilege not in {"CONNECT", "CREATE", "TEMPORARY"}
                or type(grantable) is not bool
            ):
                raise RuntimeError("unsupported source database ACL")
            admin.execute(
                sql.SQL("GRANT {} ON DATABASE jarvis TO {}{}").format(
                    sql.SQL(privilege),
                    sql.SQL("PUBLIC")
                    if recipient == "PUBLIC"
                    else sql.Identifier(recipient),
                    sql.SQL(" WITH GRANT OPTION" if grantable else ""),
                )
            )
    subprocess.run(
        [
            POSTGRES_BIN / "pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "--dbname=jarvis",
            INPUT / "database.dump",
        ],
        env=pg_environment(
            URL.create(
                "postgresql+psycopg",
                username="postgres",
                database="jarvis",
                query={"host": str(SOCKET)},
            )
        ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


async def verify(expected, password, report):
    engine = create_async_engine(
        URL.create(
            "postgresql+psycopg",
            username=READER,
            password=password,
            database="jarvis",
            query={"host": str(SOCKET)},
        ),
        connect_args={"options": "-c default_transaction_read_only=on"},
    )
    failures = report["failed"]
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
            for field, value in (await database_inventory(conn)).items():
                if value != expected[field]:
                    failures.append(field)
            for field, value in (await schema_inventory(conn)).items():
                if value != expected["schema"].get(field):
                    failures.append(f"schema {field}")
            observed = await table_inventory(conn)
            wanted = expected["tables"]
            failures.extend(
                f"table {table}"
                for table in sorted(observed.keys() | wanted.keys())
                if observed.get(table) != wanted.get(table)
            )
            scope = await coverage(conn)
            report["coverage"] = scope
            if scope != expected["coverage"]:
                failures.append("ready and admitted coverage")
            writable = await conn.scalar(
                text("""
                SELECT pg_has_role(current_user, 'jarvis_migrator', 'MEMBER')
                    OR has_database_privilege(current_database(), 'CREATE')
                    OR has_database_privilege(current_database(), 'TEMP')
                    OR has_schema_privilege('public', 'CREATE')
                    OR EXISTS(
                        SELECT FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE nspname = 'public' AND (
                            (c.relkind = 'r' AND (
                                has_table_privilege(c.oid,
                                    'INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER')
                                OR has_any_column_privilege(c.oid, 'INSERT, UPDATE')
                            ))
                            OR (c.relkind = 'S'
                                AND has_sequence_privilege(c.oid, 'USAGE, UPDATE'))
                        )
                    )
            """)
            )
            if writable:
                failures.append("reader write privilege")

        store = MemoryStore(engine)

        async def read(value):
            return await store.open(
                value, cutoff=expected["coverage"]["admitted_through"]
            )

        for name in ("event", "note"):
            witness = expected["witnesses"][name]
            if witness is None:
                failures.append(f"{name} witness absent")
                continue
            try:
                actual = await witness_digest(witness["selector"], read)
            except Exception as error:  # Both comparisons still get reported.
                failures.append(f"{name} witness read failed ({type(error).__name__})")
                continue
            if actual != {"count": witness["count"], "sha256": witness["sha256"]}:
                failures.append(f"{name} witness content")
            else:
                report["opened"][name] = actual["count"]
    finally:
        await engine.dispose()


def main():
    os.umask(0o077)
    report = {"coverage": None, "opened": {}, "failed": []}
    started = False
    phase = "input"
    try:
        manifest = json.loads((INPUT / "manifest.json").read_bytes())
        with LOCK.open("rb") as stream:
            lock_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
        if manifest["uv_lock_sha256"] != lock_sha256:
            raise RuntimeError("reader and manifest dependency locks differ")
        phase = "database initialization"
        DATA.mkdir()
        SOCKET.mkdir()
        shutil.chown(DATA, user="postgres")
        shutil.chown(SOCKET, user="postgres")
        postgres_command(
            "initdb",
            "-D",
            DATA,
            "--username=postgres",
            "--auth-local=trust",
            "--auth-host=reject",
            "--no-instructions",
        )
        (DATA / "pg_hba.conf").write_text(
            "local all postgres trust\nlocal jarvis jarvis_backup scram-sha-256\n",
            encoding="utf-8",
        )
        postgres_command(
            "pg_ctl",
            "-D",
            DATA,
            "-w",
            "-l",
            DATA / "server.log",
            "-o",
            f"-c listen_addresses='' -c unix_socket_directories={SOCKET} "
            "-c timezone=UTC",
            "start",
        )
        started = True
        phase = "strict database restore"
        password = secrets.token_hex(32)
        prepare_database(manifest["database"], password)
        phase = "inventory and read verification"
        asyncio.run(verify(manifest, password, report))
    except Exception as error:
        report["failed"].append(
            f"{phase}: {error}"
            if type(error) is RuntimeError
            else f"{phase}: {type(error).__name__}"
        )
    finally:
        if started:
            try:
                postgres_command("pg_ctl", "-D", DATA, "-w", "-m", "fast", "stop")
            except subprocess.CalledProcessError:
                report["failed"].append("isolated database shutdown")
    print(json.dumps(report, separators=(",", ":")), flush=True)
    return int(bool(report["failed"]))


if __name__ == "__main__":
    sys.exit(main())
