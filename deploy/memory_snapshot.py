"""One exported recovery cut and its reproducible database/read evidence."""

import hashlib
import json
import os
from datetime import UTC
from pathlib import Path

from sqlalchemy import text
from universal_memory.policy import canonical_json, encoded_size
from universal_memory.retrieval import open_records
from universal_memory.types import Missing, OpenInput

POSTGRES_BIN = Path("/usr/lib/postgresql/16/bin")
STOPPED_TABLE_KEYS = {
    "message": "id",
    "action": "id",
    "model_decision": "decision_id",
    "read_position": 'position COLLATE "C"',
    "native_attempt": 'conversation_id COLLATE "C", attempt_seq',
    "native_invocation": "id",
    "native_input_delivery": "attempt_id, message_id",
    "work": "id",
    "attachment": "id",
    "event_cursor": 'account_id COLLATE "C"',
    "home_notice": "id",
    "memory_log": "id",
    "memory_summary": "id",
    "source_record": "id",
    "memory_retired_source_record": "id",
    "source_conversation": "id",
    "memory_lane": 'machine COLLATE "C", account COLLATE "C"',
    "memory_leaf": "position",
    "memory_node": "level, node_index",
    "memory_state": "id",
}
TABLE_KEYS = {
    **STOPPED_TABLE_KEYS,
    "model_decision": 'decision_id COLLATE "C"',
    "alembic_version": 'version_num COLLATE "C"',
}
SEQUENCES = (
    "memory_leaf_position_seq",
    "memory_state_id_seq",
    "message_control_sequence",
)
# A new app schema can ship before its restore boundary is qualified.
SCHEMA_REVISION = "0022"
VECTOR_VERSION = "0.8.6"
WRITER_ROLES = ("jarvis_migrator", "jarvis_runtime", "jarvis_memory")
RESTORE_ROLES = (*WRITER_ROLES, "jarvis_backup")
LO_CONSTRUCTORS = (
    "pg_catalog.lo_create(oid)",
    "pg_catalog.lo_creat(integer)",
    "pg_catalog.lo_from_bytea(oid,bytea)",
)
LO_GRANTS_SQL = f"""
REVOKE EXECUTE ON FUNCTION {", ".join(LO_CONSTRUCTORS)} FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {", ".join(LO_CONSTRUCTORS)} TO {", ".join(WRITER_ROLES)};
"""


def lo_write_permission(role_expression):
    allowed = " OR ".join(
        f"has_function_privilege({role_expression}, '{function}', 'EXECUTE')"
        for function in LO_CONSTRUCTORS
    )
    return f"({allowed})"


async def table_inventory(conn, *, stopped_keys=None, projections=None):
    await conn.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    await conn.execute(text("SET LOCAL DateStyle TO 'ISO, YMD'"))
    await conn.execute(text("SET LOCAL IntervalStyle TO postgres"))
    await conn.execute(text("SET LOCAL extra_float_digits TO 3"))
    await conn.execute(text("SET LOCAL bytea_output TO hex"))
    keys_by_table = TABLE_KEYS
    if stopped_keys is not None:
        keys_by_table = stopped_keys
        tables = (
            await conn.execute(
                text("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema='public' AND table_type='BASE TABLE'
                        AND table_name<>'alembic_version'
                """)
            )
        ).scalars()
        if set(tables) != keys_by_table.keys():
            raise RuntimeError("stopped database table roster differs")
    projections = projections or {}
    return {
        table: await row_inventory(
            conn, projections.get(table, f"public.{table}"), keys
        )
        for table, keys in keys_by_table.items()
    }


async def row_inventory(conn, rows, order_by):
    # Only fixed-size hashes cross the connection. Original JSON survives.
    query = f"""SELECT sha256(convert_to(row_to_json(original)::text, 'UTF8'))
                FROM {rows} original ORDER BY {order_by}"""
    digest, count = hashlib.sha256(), 0
    async for row in (await conn.stream(text(query))).scalars():
        digest.update(row)
        count += 1
    return [count, digest.hexdigest()]


def pg_environment(url):
    host = url.host or url.query.get("host")
    if not host or not url.database or set(url.query) - {"host", "sslmode"}:
        raise RuntimeError("unsupported PostgreSQL endpoint")
    environment = {
        "PATH": os.defpath,
        "LC_ALL": "C",
        "PGHOST": host,
        "PGPORT": str(url.port or 5432),
        "PGDATABASE": url.database,
        "PGUSER": url.username or "",
        "PGSSLMODE": url.query.get("sslmode", "prefer"),
    }
    if url.password is not None:
        environment["PGPASSWORD"] = url.password
    elif passfile := os.environ.get("PGPASSFILE"):
        environment["PGPASSFILE"] = passfile
    return environment


async def database_inventory(conn):
    rows = await conn.execute(
        text("""
            SELECT nspname, relname, relkind
            FROM pg_class JOIN pg_namespace ON pg_namespace.oid = relnamespace
            WHERE relkind IN ('r', 'p', 'S', 'f', 'm', 'v')
            AND nspname NOT IN ('information_schema', 'pg_catalog')
            AND nspname !~ '^pg_(toast|temp)'
        """)
    )
    if set(rows.tuples()) != {
        *(("public", name, "r") for name in TABLE_KEYS),
        *(("public", name, "S") for name in SEQUENCES),
    } or await conn.scalar(text("SELECT EXISTS(SELECT FROM pg_largeobject_metadata)")):
        raise RuntimeError("unexpected database object roster")
    revision = await conn.scalar(text("SELECT version_num FROM public.alembic_version"))
    version = int(await conn.scalar(text("SHOW server_version_num"))) // 10_000
    vector = await conn.scalar(
        text("""
        SELECT extversion FROM pg_extension JOIN pg_namespace n ON n.oid = extnamespace
        WHERE extname = 'vector' AND nspname = 'public'
    """)
    )
    if (revision, version, vector) != (SCHEMA_REVISION, 16, VECTOR_VERSION):
        raise RuntimeError(
            "unsupported PostgreSQL, vector extension, or Alembic revision"
        )

    db = dict(
        (
            await conn.execute(
                text("""
                    SELECT datname AS name, pg_get_userbyid(datdba) AS owner,
                    pg_encoding_to_char(encoding) AS encoding, datcollate AS collate,
                    datctype AS ctype, datlocprovider AS locale_provider
                    FROM pg_database WHERE datname = current_database()
                """)
            )
        )
        .mappings()
        .one()
    )
    if (db["name"], db["owner"], db["encoding"], db["locale_provider"]) != (
        "jarvis",
        "jarvis_migrator",
        "UTF8",
        "c",
    ):
        raise RuntimeError("unsupported database identity or locale")
    db["acl"] = sorted(
        list(row)
        for row in await conn.execute(
            text("""
                SELECT CASE WHEN grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee)
                END AS role, pg_get_userbyid(grantor) AS grantor, privilege_type,
                is_grantable
                FROM pg_database CROSS JOIN LATERAL
                    aclexplode(coalesce(datacl, acldefault('d', datdba)))
                WHERE datname = current_database()
            """)
        )
    )
    if any(
        role not in (*RESTORE_ROLES, "PUBLIC")
        or grantor != db["owner"]
        or privilege not in {"CONNECT", "CREATE", "TEMPORARY"}
        for role, grantor, privilege, _ in db["acl"]
    ):
        raise RuntimeError("unexpected database-level grant")
    return {
        "postgres_major": version,
        "vector_version": vector,
        "schema_revision": revision,
        "database": db,
    }


async def schema_inventory(conn):
    # Pretty PostgreSQL expressions normalize redundant grouping introduced by
    # parse/dump/restore (for example, BETWEEN inside an AND).
    constructors = ", ".join(
        f"'{signature}'::regprocedure" for signature in LO_CONSTRUCTORS
    )
    queries = {
        "schemas": """
            SELECT nspname, pg_get_userbyid(nspowner)
            FROM pg_namespace
            WHERE nspname NOT IN ('information_schema', 'pg_catalog')
            AND nspname !~ '^pg_(toast|temp)'
        """,
        "extensions": """
            SELECT extname, nspname, extversion, pg_get_userbyid(extowner)
            FROM pg_extension JOIN pg_namespace ON pg_namespace.oid = extnamespace
        """,
        "relations": """
            SELECT relname, relkind, pg_get_userbyid(relowner), relpersistence,
                relrowsecurity, relforcerowsecurity, relreplident, reloptions
            FROM pg_class WHERE relnamespace = 'public'::regnamespace
        """,
        "columns": """
            SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
                a.attnotnull, a.attidentity, a.attgenerated, l.collname,
                pg_get_expr(d.adbin, d.adrelid, true)
            FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
            LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
            LEFT JOIN pg_collation l ON l.oid = a.attcollation
            WHERE c.relnamespace = 'public'::regnamespace
                AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY c.relname COLLATE "C", a.attnum
        """,
        "constraints": """
            SELECT c.relname, p.conname, p.convalidated,
                pg_get_constraintdef(p.oid, true)
            FROM pg_constraint p JOIN pg_class c ON c.oid = p.conrelid
            WHERE c.relnamespace = 'public'::regnamespace
        """,
        "indexes": """
            SELECT c.relname, i.indisvalid, i.indisclustered,
                pg_get_indexdef(c.oid, 0, true)
            FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
            WHERE c.relnamespace = 'public'::regnamespace
        """,
        "triggers": """
            SELECT c.relname, t.tgname, t.tgenabled, pg_get_triggerdef(t.oid, true)
            FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
            WHERE c.relnamespace = 'public'::regnamespace AND NOT t.tgisinternal
        """,
        "functions": """
            SELECT p.proname, pg_get_userbyid(p.proowner), pg_get_functiondef(p.oid)
            FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace
                AND p.prokind <> 'a'
                AND NOT EXISTS(SELECT FROM pg_depend d
                    WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
                    AND d.refclassid = 'pg_extension'::regclass AND d.deptype = 'e')
        """,
        "sequences": """
            SELECT c.relname, format_type(s.seqtypid, NULL), s.seqstart, s.seqincrement,
                s.seqmax, s.seqmin, s.seqcache, s.seqcycle, t.relname, a.attname
            FROM pg_sequence s JOIN pg_class c ON c.oid = s.seqrelid
            LEFT JOIN pg_depend d ON d.classid = 'pg_class'::regclass
                AND d.objid = c.oid AND d.refclassid = 'pg_class'::regclass
                AND d.deptype IN ('a', 'i')
            LEFT JOIN pg_class t ON t.oid = d.refobjid
            LEFT JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
            WHERE c.relnamespace = 'public'::regnamespace
        """,
        "grants": f"""
            WITH acls(kind, name, item, acl) AS (
                SELECT 'schema', nspname, '',
                    coalesce(nspacl, acldefault('n', nspowner))
                FROM pg_namespace WHERE nspname = 'public'
                UNION ALL
                SELECT 'relation', relname, '',
                    coalesce(relacl, acldefault(
                        (CASE WHEN relkind = 'S' THEN 's' ELSE 'r' END)::"char",
                        relowner))
                FROM pg_class WHERE relnamespace = 'public'::regnamespace
                    AND relkind IN ('r', 'S')
                UNION ALL
                SELECT 'column', relname, attname, attacl
                FROM pg_class JOIN pg_attribute ON attrelid = pg_class.oid
                WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'
                    AND attnum > 0 AND NOT attisdropped AND attacl IS NOT NULL
                UNION ALL
                SELECT 'routine', nspname || '.' || proname,
                    pg_get_function_identity_arguments(pg_proc.oid),
                    coalesce(proacl, acldefault('f', proowner))
                FROM pg_proc JOIN pg_namespace ON pg_namespace.oid = pronamespace
                WHERE nspname = 'public' OR pg_proc.oid IN ({constructors})
            )
            SELECT kind, name, item, pg_get_userbyid(grantor),
                CASE WHEN grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,
                privilege_type, is_grantable
            FROM acls CROSS JOIN LATERAL aclexplode(acl)
        """,
    }
    await conn.execute(text("SET LOCAL search_path = pg_catalog, public"))
    facts = {}
    for name, query in queries.items():
        rows = [list(row) for row in await conn.execute(text(query))]
        # Columns preserve ordinal order. JSON retains the full int64 bounds.
        if name != "columns":
            rows.sort(key=lambda row: json.dumps(row, ensure_ascii=False))
        wire = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        facts[name] = hashlib.sha256(wire.encode()).hexdigest()
    return facts


async def witness_digest(selector, read, *, retired=False):
    value = OpenInput.model_validate_json(canonical_json(selector))
    digest, count = hashlib.sha256(), 0
    while True:
        page = await read(value)
        if not page.records:
            raise RuntimeError("empty witness page")
        for record in page.records:
            if isinstance(record, Missing):
                if not retired or record.error != "retired":
                    raise RuntimeError("incorrect missing witness disposition")
            elif retired:
                raise RuntimeError("retired original returned live content")
            digest.update(
                canonical_json(record.model_dump(mode="json")).encode() + b"\n"
            )
            count += 1
        if page.cursor is None:
            return {"count": count, "sha256": digest.hexdigest()}
        value = value.model_copy(update={"cursor": page.cursor})


async def collect_witnesses(conn, cutoff):
    event = (
        await conn.execute(
            text("""
                SELECT r.conversation_id::text, r.native_event_id, count(*) AS parts
                FROM public.source_record r
                JOIN public.memory_leaf l ON l.source_record_id = r.id
                WHERE l.position < :cutoff
                GROUP BY r.conversation_id, r.native_event_id
                HAVING count(*) = min(r.part_count)
                    AND min(r.part_count) = max(r.part_count)
                ORDER BY max(l.position) DESC LIMIT 1
            """),
            {"cutoff": cutoff},
        )
    ).one_or_none()
    note = await conn.scalar(
        text("""
            SELECT n.id::text FROM public.memory_log n
            JOIN public.memory_leaf l ON l.note_id = n.id
            WHERE l.position < :cutoff AND n.agent_submission IS NOT NULL
            ORDER BY l.position DESC LIMIT 1
        """),
        {"cutoff": cutoff},
    )

    async def read(value):
        return await open_records(conn, value, cutoff, encoded_size)

    witnesses = {"event": None, "note": None, "retired": None}
    retired = await conn.scalar(
        text("""
        SELECT id::text FROM public.memory_retired_source_record ORDER BY id LIMIT 1
    """)
    )
    if retired is not None:
        selector = {"identities": [{"store": "source_record", "id": retired}]}
        witnesses["retired"] = {
            "selector": selector,
            **await witness_digest(selector, read, retired=True),
        }
    if event is not None:
        selector = {"event": {"conversation_id": event[0], "native_event_id": event[1]}}
        observed = await witness_digest(selector, read)
        if observed["count"] != event[2]:
            raise RuntimeError("event witness did not return every declared part")
        witnesses["event"] = {"selector": selector, **observed}
    if note is not None:
        selector = {"identities": [{"store": "memory_log", "id": note}]}
        witnesses["note"] = {
            "selector": selector,
            **await witness_digest(selector, read),
        }
    return witnesses


async def coverage(conn):
    through, admitted = (
        await conn.execute(
            text("SELECT view_through, leaf_count FROM public.memory_state")
        )
    ).one()
    return {"through": through, "admitted_through": admitted}


async def snapshot(conn):
    """Export one cut. The caller holds conn's transaction through the full dump."""
    await conn.execute(
        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    )
    if await conn.scalar(text(f"SELECT {lo_write_permission('current_user')}")):
        raise RuntimeError("backup login can create large objects")
    snapshot_id, cut = (
        await conn.execute(text("SELECT pg_export_snapshot(), transaction_timestamp()"))
    ).one()
    facts = await database_inventory(conn)
    scope = await coverage(conn)
    return snapshot_id, {
        "cut_utc": cut.astimezone(UTC).isoformat(),
        **facts,
        "schema": await schema_inventory(conn),
        "tables": await table_inventory(conn),
        "coverage": scope,
        "witnesses": await collect_witnesses(conn, scope["admitted_through"]),
    }
