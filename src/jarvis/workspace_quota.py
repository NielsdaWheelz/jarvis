"""Project-wide Gmail admission, durably charged before every transmission."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from jarvis.db import gmail_usage
from jarvis.ownership import Database
from jarvis.workspace_mcp import GMAIL_TOOL_WEIGHTS, WorkspaceError

PACIFIC = ZoneInfo("America/Los_Angeles")
STANDARD_DAILY_UNITS = 5_000
UNKNOWN_PRIOR_USAGE = 4_000


class GmailQuota:
    def __init__(self, database: Database, project_id: str) -> None:
        self._database = database
        self._project_id = project_id

    async def debit(self, tool: str) -> None:
        weight = GMAIL_TOOL_WEIGHTS[tool]
        async with self._database.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:project, 0))"),
                {"project": f"jarvis-gmail-quota:{self._project_id}"},
            )
            day = await conn.scalar(
                text(
                    "SELECT (clock_timestamp() AT TIME ZONE "
                    "'America/Los_Angeles')::date"
                )
            )
            if not isinstance(day, date):
                raise RuntimeError("database did not supply Gmail quota day")

            row = (
                await conn.execute(
                    select(gmail_usage.c.pacific_day, gmail_usage.c.units).where(
                        gmail_usage.c.project_id == self._project_id
                    )
                )
            ).one_or_none()
            if row is not None and row.pacific_day > day:
                # A clock correction cannot reopen a previously charged day.
                day = row.pacific_day
            if row is None:
                # Fresh and restored databases do not know today's prior usage.
                used = UNKNOWN_PRIOR_USAGE
            else:
                used = row.units if row.pacific_day == day else 0
            total = used + weight
            allowed = total <= STANDARD_DAILY_UNITS
            if allowed or row is None:
                units = total if allowed else used
                await conn.execute(
                    insert(gmail_usage)
                    .values(project_id=self._project_id, pacific_day=day, units=units)
                    .on_conflict_do_update(
                        index_elements=[gmail_usage.c.project_id],
                        set_={"pacific_day": day, "units": units},
                    )
                )
        if not allowed:
            raise WorkspaceError(
                "rate_limited",
                retry_at=datetime.combine(day + timedelta(days=1), time(), PACIFIC),
            )
