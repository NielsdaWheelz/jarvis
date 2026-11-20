"""Grant and verify backup-only PostgreSQL access under both stopped writer locks."""

import asyncio
import grp
import os
import pwd
import re
import secrets
import stat
import subprocess
import sys

from memory_backup_hba import scope_backup_hba
from memory_backup_storage import MANIFEST_LIMIT, producer_settings
from memory_credentials import ETC, publish, require_owner_pause
from memory_snapshot import (
    LO_GRANTS_SQL,
    POSTGRES_BIN,
    SEQUENCES,
    TABLE_KEYS,
    database_inventory,
    lo_write_permission,
)
from sqlalchemy.engine import make_url

from jarvis.db import create_engine, normalize_database_url
from jarvis.ownership import maintenance_ownership

ROLE = "jarvis_backup"
USER = "jarvis-backup"
DATABASE = "jarvis"


def role_psql(statement):
    return subprocess.run(
        [
            "runuser",
            "-u",
            "postgres",
            "--",
            POSTGRES_BIN / "psql",
            "-XqAtw",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            "/var/run/postgresql",
            "-p",
            "5432",
            "-d",
            DATABASE,
        ],
        input=statement,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def os_identity():
    try:
        group = grp.getgrnam(USER)
    except KeyError:
        subprocess.run(["groupadd", "--system", USER], check=True)
        group = grp.getgrnam(USER)
    try:
        user = pwd.getpwnam(USER)
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "--system",
                "--gid",
                USER,
                "--home-dir",
                "/nonexistent",
                "--no-create-home",
                "--shell",
                "/usr/sbin/nologin",
                USER,
            ],
            check=True,
        )
        user = pwd.getpwnam(USER)
    members = {
        entry.pw_name for entry in pwd.getpwall() if entry.pw_gid == group.gr_gid
    }
    if (
        user.pw_uid == 0
        or user.pw_shell != "/usr/sbin/nologin"
        or user.pw_dir != "/nonexistent"
        or user.pw_gid != group.gr_gid
        or set(os.getgrouplist(USER, user.pw_gid)) != {group.gr_gid}
        or members | set(group.gr_mem) != {USER}
        or subprocess.check_output(["passwd", "-S", USER], text=True).split()[1] != "L"
    ):
        raise RuntimeError("backup OS account is not locked and dedicated")
    return group.gr_gid


def grant_check():
    rels = ", ".join(f"'public.{name}'::regclass" for name in (*TABLE_KEYS, *SEQUENCES))
    return f"""
        SELECT rolcanlogin AND NOT (rolsuper OR rolcreatedb OR rolcreaterole
               OR rolreplication OR rolbypassrls)
           AND NOT EXISTS (
             SELECT FROM pg_auth_members WHERE member=r.oid OR roleid=r.oid
           )
           AND NOT EXISTS (
             SELECT FROM pg_shdepend s
             WHERE s.refclassid='pg_authid'::regclass AND s.refobjid=r.oid
             AND NOT (s.deptype='a' AND (
               (s.classid='pg_database'::regclass AND s.objid=d.oid)
               OR (s.dbid=d.oid AND s.classid='pg_namespace'::regclass
                   AND s.objid='public'::regnamespace)
               OR (s.dbid=d.oid AND s.classid='pg_class'::regclass
                   AND s.objsubid=0 AND s.objid IN ({rels}))
             ))
           )
           AND NOT EXISTS (
             SELECT FROM (
               SELECT 'CONNECT' AS expected, d.datacl AS acl
               UNION ALL SELECT 'USAGE', nspacl FROM pg_namespace WHERE nspname='public'
               UNION ALL SELECT 'SELECT', relacl FROM pg_class WHERE oid IN ({rels})
             ) objects
             WHERE EXISTS (
               SELECT FROM aclexplode(objects.acl)
               WHERE grantee=r.oid AND (is_grantable OR privilege_type<>expected)
             )
             OR NOT EXISTS (SELECT FROM aclexplode(objects.acl) WHERE grantee=r.oid)
           )
           AND NOT has_database_privilege(r.oid, d.oid, 'CREATE,TEMP')
           AND NOT has_schema_privilege(r.oid, 'public', 'CREATE')
           AND NOT ({lo_write_permission("r.oid")})
           AND NOT EXISTS (
             SELECT FROM pg_class WHERE oid IN ({rels}) AND (
               CASE WHEN relkind='S'
                    THEN has_sequence_privilege(r.oid, oid, 'USAGE,UPDATE')
                    ELSE has_any_column_privilege(
                        r.oid, oid, 'INSERT,UPDATE,REFERENCES'
                    ) OR has_table_privilege(r.oid, oid, 'DELETE,TRUNCATE,TRIGGER')
               END
             )
           )
        FROM pg_roles r CROSS JOIN pg_database d
        WHERE rolname='{ROLE}' AND d.datname=current_database()
    """


def install_login():
    active = ETC / "database-backup.pass"
    stage = active.with_suffix(".staged")
    prefix = f"127.0.0.1:5432:{DATABASE}:{ROLE}:"
    exists = role_psql(f"SELECT 1 FROM pg_roles WHERE rolname='{ROLE}'") == "1"
    if exists and role_psql(grant_check()) != "t":
        raise RuntimeError("existing backup login does not have the required grants")
    credential = active if active.exists() else stage
    if not credential.exists():
        if exists:
            raise RuntimeError("existing backup login has no staged credential")
        publish(stage, (prefix + secrets.token_hex(32) + "\n").encode())
    if (
        not stat.S_ISREG(credential.lstat().st_mode)
        or stat.S_IMODE(credential.stat().st_mode) != 0o600
        or credential.stat().st_uid != 0
    ):
        raise RuntimeError("backup credential is not root-private")
    match = re.fullmatch(re.escape(prefix) + "([0-9a-f]{64})\n", credential.read_text())
    if not match:
        raise RuntimeError("invalid backup credential format")
    if not exists:
        tables = ", ".join(f"public.{name}" for name in TABLE_KEYS)
        sequences = ", ".join(f"public.{name}" for name in SEQUENCES)
        role_psql(f"""
            BEGIN;
            SET LOCAL log_statement=none;
            SET LOCAL log_duration=off;
            SET LOCAL log_min_duration_statement=-1;
            SET LOCAL log_min_error_statement=panic;
            SET LOCAL password_encryption='scram-sha-256';
            CREATE ROLE {ROLE} LOGIN PASSWORD '{match[1]}';
            GRANT CONNECT ON DATABASE {DATABASE} TO {ROLE};
            GRANT USAGE ON SCHEMA public TO {ROLE};
            GRANT SELECT ON TABLE {tables} TO {ROLE};
            GRANT SELECT ON SEQUENCE {sequences} TO {ROLE};
            {LO_GRANTS_SQL}
            DO $verify$ BEGIN
                IF ({grant_check()}) IS DISTINCT FROM true THEN
                    RAISE EXCEPTION 'unexpected backup grants';
                END IF;
            END $verify$;
            COMMIT;
        """)
    subprocess.run(
        [
            POSTGRES_BIN / "psql",
            "-XqAtw",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            ROLE,
            "-d",
            DATABASE,
            "-c",
            "SELECT version_num FROM alembic_version",
        ],
        env={**os.environ, "PGPASSFILE": str(credential)},
        capture_output=True,
        check=True,
    )
    denied = subprocess.run(
        [
            POSTGRES_BIN / "psql",
            "-XqAtw",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            ROLE,
            "-d",
            "postgres",
            "-c",
            "SELECT 1",
        ],
        env={**os.environ, "LC_ALL": "C", "PGPASSFILE": str(credential)},
        capture_output=True,
        check=False,
    )
    if denied.returncode == 0 or b"pg_hba.conf rejects connection" not in denied.stderr:
        raise RuntimeError("backup login lacks alternate database rejection")
    if credential == stage:
        publish(active, stage.read_bytes())
        stage.unlink()


async def install(raw):
    conn = make_url(normalize_database_url(os.environ["JARVIS_MIGRATION_DATABASE_URL"]))
    if (conn.host, conn.port or 5432, conn.database) != ("127.0.0.1", 5432, DATABASE):
        raise RuntimeError("backup provisioning requires the installed local database")
    producer_settings(raw)
    engine = create_engine(str(conn.render_as_string(hide_password=False)))
    try:
        async with maintenance_ownership(engine) as owner:
            await require_owner_pause(owner)
            async with owner.connect() as connection:
                await database_inventory(connection)
            group = os_identity()
            scope_backup_hba(role_psql)
            install_login()
            os.chown("/opt/jarvis/.deploy.lock", 0, group)
            os.chmod("/opt/jarvis/.deploy.lock", 0o640)
            publish(ETC / "backup.json", raw)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(install(sys.stdin.buffer.read(MANIFEST_LIMIT + 1)))
    except Exception as error:
        print(
            str(error) if type(error) is RuntimeError else type(error).__name__,
            file=sys.stderr,
        )
        sys.exit(1)
