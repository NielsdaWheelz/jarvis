"""Keep the backup login on the local Jarvis database."""

import stat
import time
from pathlib import Path

from memory_credentials import publish

BEGIN = b"# begin jarvis backup connection scope\n"
END = b"# end jarvis backup connection scope\n"
BLOCK = (
    BEGIN
    + b"host  jarvis           jarvis_backup  127.0.0.1/32  scram-sha-256\n"
    + b"local all,replication  jarvis_backup                reject\n"
    + b"host  all,replication  jarvis_backup  all           reject\n"
    + END
    + b"\n"
)
PARSE_ERRORS = "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL"
LOAD_TIME = "SELECT pg_conf_load_time()"


def scope_backup_hba(role_psql):
    """Publish and reload the first-match block under stopped deployment ownership."""
    path = Path(role_psql("SHOW hba_file"))
    if not path.is_absolute():
        raise RuntimeError("PostgreSQL HBA path is not absolute")
    path = path.resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError("PostgreSQL HBA is not a regular file")
    existing = path.read_bytes()
    original = existing.removeprefix(BLOCK)
    if BEGIN.rstrip() in original or END.rstrip() in original:
        raise RuntimeError("unexpected Jarvis backup HBA block")
    if role_psql(PARSE_ERRORS) != "0":
        raise RuntimeError("existing PostgreSQL HBA is invalid")
    if (
        role_psql(
            "SELECT NOT EXISTS (SELECT FROM pg_stat_activity "
            "WHERE usename='jarvis_backup')"
        )
        != "t"
    ):
        raise RuntimeError("backup login already has an active PostgreSQL session")
    if existing == original:
        mode = stat.S_IMODE(info.st_mode)
        publish(path, BLOCK + original, mode, info.st_uid, info.st_gid)
        if role_psql(PARSE_ERRORS) != "0":
            publish(path, original, mode, info.st_uid, info.st_gid)
            raise RuntimeError("managed PostgreSQL HBA is invalid")

    # Each probe opens a fresh session and observes the postmaster's load time.
    previous = role_psql(LOAD_TIME)
    if role_psql("SELECT pg_reload_conf()") != "t":
        raise RuntimeError("PostgreSQL refused to reload its configuration")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if role_psql(LOAD_TIME) != previous:
            return
        time.sleep(0.1)
    raise RuntimeError("PostgreSQL configuration reload was not observed")
