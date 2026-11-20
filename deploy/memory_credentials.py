"""Root-side publication under the stopped deployment's maintenance ownership."""

import asyncio
import grp
import os
import pwd
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ETC = Path("/etc/jarvis")
MEMORY_USER = "jarvis-memory"
EMBEDDING = {
    b"JARVIS_EMBEDDING_OPENAI_API_KEY",
    b"JARVIS_EMBEDDING_MODEL",
    b"JARVIS_EMBEDDING_DIMENSION",
}
MEMORY = {b"JARVIS_MEMORY_CONFIG_PATH", b"JARVIS_MEMORY_HTTP_PORT"}


def publish(path, data, mode=0o600, owner=0, group=0):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
        try:
            out.write(data)
            out.flush()
            os.fchown(out.fileno(), owner, group)
            os.fchmod(out.fileno(), mode)
            os.fsync(out.fileno())
            os.replace(out.name, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(out.name).unlink(missing_ok=True)


def memory_identity():
    try:
        group = grp.getgrnam(MEMORY_USER)
    except KeyError:
        subprocess.run(["groupadd", "--system", MEMORY_USER], check=True)
        group = grp.getgrnam(MEMORY_USER)
    try:
        user = pwd.getpwnam(MEMORY_USER)
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "--system",
                "--gid",
                MEMORY_USER,
                "--home-dir",
                "/nonexistent",
                "--no-create-home",
                "--shell",
                "/usr/sbin/nologin",
                MEMORY_USER,
            ],
            check=True,
        )
        user = pwd.getpwnam(MEMORY_USER)
    members = set(group.gr_mem) | {
        entry.pw_name for entry in pwd.getpwall() if entry.pw_gid == group.gr_gid
    }
    if (
        user.pw_uid == 0
        or user.pw_gid != group.gr_gid
        or set(os.getgrouplist(user.pw_name, user.pw_gid)) != {group.gr_gid}
        or members - {MEMORY_USER, "jarvis"}
    ):
        raise RuntimeError("memory service identity or group has unexpected privileges")
    if "jarvis" not in members:
        subprocess.run(["usermod", "-aG", MEMORY_USER, "jarvis"], check=True)
    return group.gr_gid


def postgres(statement):
    # The installed deployment uses the local postgres administrator over peer auth.
    return subprocess.run(
        [
            "sudo",
            "-n",
            "-u",
            "postgres",
            "psql",
            "-XqAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            "/var/run/postgresql",
            "-p",
            "5432",
            "-d",
            "jarvis",
        ],
        input=statement,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def memory_login():
    path = ETC / "database-memory.env"
    prefix = "JARVIS_DATABASE_URL=postgresql+psycopg://jarvis_memory:"
    suffix = "@127.0.0.1:5432/jarvis\n"
    role = postgres("""
        SELECT rolcanlogin AND NOT (rolsuper OR rolcreatedb OR rolcreaterole
               OR rolreplication OR rolbypassrls)
               AND NOT EXISTS(SELECT FROM pg_auth_members
                              WHERE member=r.oid OR roleid=r.oid)
               AND NOT EXISTS(SELECT FROM pg_shdepend
                              WHERE refclassid='pg_authid'::regclass
                                AND refobjid=r.oid AND deptype='o')
        FROM pg_roles r WHERE rolname='jarvis_memory';
    """)
    if role not in ("", "t"):
        raise RuntimeError("memory login has unexpected authority")
    if not path.exists():
        if role:
            raise RuntimeError("existing memory login has no private credential")
        publish(path, (prefix + secrets.token_hex(32) + suffix).encode())
    match = re.fullmatch(
        re.escape(prefix) + r"([0-9a-f]{64})" + re.escape(suffix), path.read_text()
    )
    if not match or path.stat().st_mode & 0o077 or path.stat().st_uid != 0:
        raise RuntimeError(
            "memory login credential file has incompatible contents or permissions"
        )
    password = match[1]
    if not role:
        # The credential file commits first. A retry uses the identical password.
        postgres(
            f"BEGIN; SET LOCAL log_statement=none; SET LOCAL log_duration=off; "
            f"SET LOCAL log_min_duration_statement=-1; "
            f"CREATE ROLE jarvis_memory LOGIN PASSWORD '{password}'; "
            "GRANT CONNECT ON DATABASE jarvis TO jarvis_memory; COMMIT;"
        )
    subprocess.run(
        [
            "psql",
            "-XqAtw",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            "jarvis_memory",
            "-d",
            "jarvis",
            "-c",
            "SELECT 1",
        ],
        env={**os.environ, "PGPASSWORD": password},
        check=True,
        capture_output=True,
    )


def split_environment(raw):
    assistant, embedding, memory = [], [], []
    seen = set()
    for line in raw.splitlines(keepends=True):
        if line.lstrip().startswith(b"#") or not line.strip():
            assistant.append(line)
            continue
        key, separator, value = line.partition(b"=")
        if not separator or not re.fullmatch(rb"[A-Z][A-Z0-9_]*", key) or key in seen:
            raise RuntimeError("invalid or repeated private environment assignment")
        seen.add(key)
        if key in EMBEDDING:
            embedding.append(line.rstrip(b"\r\n") + b"\n")
        else:
            assistant.append(line)
        if key in MEMORY:
            memory.append(line.rstrip(b"\r\n") + b"\n")
        if (
            key == b"JARVIS_MEMORY_CONFIG_PATH"
            and value.strip() != b"/etc/jarvis/memory.json"
        ):
            raise RuntimeError("memory declaration differs from installed path")
    if b"JARVIS_MEMORY_HTTP_PORT" not in seen:
        memory.append(b"JARVIS_MEMORY_HTTP_PORT=8768\n")
    if not ({b"JARVIS_MEMORY_CONFIG_PATH"} | EMBEDDING) <= seen:
        raise RuntimeError("incomplete memory or embedding settings")
    return b"".join(assistant), b"".join(embedding), b"".join(memory)


def publish_assistant(assistant, declaration):
    group = memory_identity()
    publish(ETC / "memory.json", declaration, 0o640, 0, group)
    os.chown(ETC, 0, group)
    ETC.chmod(0o710)
    publish(ETC / "jarvis.env", assistant)


async def install_staged(stage, bootstrap):
    from sqlalchemy import text

    from jarvis.db import APPLICATION_SCHEMA_REVISION, create_engine
    from jarvis.messages import MessageStore
    from jarvis.ownership import maintenance_ownership

    engine = create_engine(os.environ["JARVIS_MIGRATION_DATABASE_URL"])
    try:
        async with maintenance_ownership(engine) as db:
            async with db.begin() as conn:
                if (
                    bootstrap
                    and await conn.scalar(text("SELECT to_regclass('alembic_version')"))
                    is None
                ):
                    from alembic import command
                    from alembic.config import Config

                    os.environ["JARVIS_MEMORY_CONFIG_PATH"] = str(stage / "memory.json")

                    def migrate_empty(connection):
                        config = Config(
                            str(Path(__file__).resolve().parents[1] / "alembic.ini")
                        )
                        config.attributes["connection"] = connection
                        command.upgrade(config, "0015")

                    await conn.run_sync(migrate_empty)
                revision = await conn.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
                if bootstrap and (
                    revision != "0015"
                    or await conn.scalar(text("SELECT EXISTS (SELECT FROM message)"))
                ):
                    raise RuntimeError("bootstrap requires empty schema 0015")
            assistant, embedding, memory = split_environment(
                (stage / "jarvis.env").read_bytes()
            )
            if not bootstrap:
                old = {
                    key: os.environ[key].encode()
                    for key in ("JARVIS_OWNER_SCOPE", "JARVIS_OWNER_ARCHIVE_KEY")
                }
                entries = dict(
                    row.split(b"=", 1) for row in assistant.splitlines() if b"=" in row
                )
                if (
                    revision != APPLICATION_SCHEMA_REVISION
                    or any(entries.get(k.encode()) != v for k, v in old.items())
                    or await MessageStore(db).current_control(
                        os.environ["JARVIS_OWNER_SCOPE"]
                    )
                    != "pause"
                ):
                    raise RuntimeError(
                        "need the installed schema, original owner identities and pause"
                    )
            publish(ETC / "embedding.env", embedding)
            publish(ETC / "memory.env", memory)
            publish_assistant(assistant, (stage / "memory.json").read_bytes())
            account = pwd.getpwnam("jarvis")
            publish(
                Path("/var/lib/jarvis/connectors/google-oauth-state.json"),
                (stage / "google-oauth-state.json").read_bytes(),
                0o600,
                account.pw_uid,
                account.pw_gid,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["bootstrap-memory-login"]:
            memory_login()
            memory_identity()
        elif len(sys.argv) in (2, 3) and sys.argv[2:] in ([], ["--bootstrap"]):
            asyncio.run(install_staged(Path(sys.argv[1]), bool(sys.argv[2:])))
        else:
            raise RuntimeError("invalid private state operation")
    except Exception as error:
        # Database exceptions and environment contents are private.
        print(
            str(error) if type(error) is RuntimeError else type(error).__name__,
            file=sys.stderr,
        )
        sys.exit(1)
