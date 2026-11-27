"""Stopped conversion of the 0028 work instructions and live obligations."""

from pathlib import Path
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis._atomic_json import read_private_json

# Load the exact literal SQL from the pinned migration without coupling
# that migration to later install or connector code.
_root = Path(__file__).resolve().parents[1]
_config = Config(str(_root / "alembic.ini"))
_config.set_main_option("script_location", str(_root / "migrations"))
_migration = ScriptDirectory.from_config(_config).get_revision("0029").module
CONVERTED_WORK_ROWS = _migration.CONVERTED_WORK_ROWS
INCOMPATIBLE_WORK = _migration.INCOMPATIBLE_WORK

WORK_COLUMNS = """id, title, state, content, due_date, wake_id, wake_at, repeat,
                  wake_until, wake_local_date, created_at, updated_at"""


def stopped_workspace_grant(state: Path) -> str | None:
    grant = read_private_json(state / "connectors" / "google-oauth-state.json")
    if (
        grant is None
        or grant.get("schema") != "jarvis.google-workspace-oauth.v2"
        or grant.get("status") != "connected"
    ):
        return None
    return str(UUID(str(grant["grant_id"])))


async def cut_inventory(
    connection: AsyncConnection, scope: str, grant: str | None
) -> dict[str, object]:
    return {
        "incompatible": [
            dict(row)
            for row in (
                await connection.execute(
                    text(INCOMPATIBLE_WORK), {"workspace_grant": grant}
                )
            ).mappings()
        ],
        "uncertain": [
            dict(row)
            for row in (
                await connection.execute(
                    text("""
            SELECT id::text, tool_name AS operation FROM action
            WHERE status = 'uncertain' ORDER BY id
        """)
                )
            ).mappings()
        ],
        "schedules": [
            str(row)
            for row in (
                await connection.execute(
                    text("""
            SELECT id FROM work WHERE workspace_check IS NOT NULL ORDER BY id
        """)
                )
            ).scalars()
        ],
        "undelivered_inputs": [
            str(row)
            for row in (
                await connection.execute(
                    text("""
            SELECT id FROM message WHERE source_conversation_id = :scope
              AND role IN ('owner','host') AND processed_at IS NULL ORDER BY id
        """),
                    {"scope": scope},
                )
            ).scalars()
        ],
        "source_ack": [
            dict(row)
            for row in (
                await connection.execute(
                    text("""
            SELECT progress->>'grant_id' AS grant_id, progress->'ack' AS ack
            FROM event_cursor
            WHERE progress->>'ack' IS NOT NULL
            ORDER BY account_id
        """)
                )
            ).mappings()
        ],
    }
