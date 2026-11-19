"""Persist a private notification with the fact that earned it."""

import logging
from typing import Literal
from uuid import UUID, uuid5

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import home_notice
from jarvis.discord import DeliveryFailed, DiscordCreateMessageClient
from jarvis.home_pages import HOME_ORIGIN
from jarvis.ownership import Database


async def enqueue_notice(
    connection: AsyncConnection,
    kind: Literal["approval", "question", "reply"],
    target: UUID,
) -> None:
    await connection.execute(
        insert(home_notice).values(
            id=uuid5(target, f"jarvis-home-notice:{kind}"),
            kind=kind,
            message_id=None if kind == "approval" else target,
            action_id=target if kind == "approval" else None,
        )
    )


async def deliver_pending(
    database: Database, sender: DiscordCreateMessageClient, limit: int
) -> bool:
    """Drain committed notices in order. An unacknowledged send stays pending."""
    while True:
        async with database.connect() as connection:
            notices = (
                (
                    await connection.execute(
                        select(home_notice)
                        .where(home_notice.c.discord_message_id.is_(None))
                        .order_by(home_notice.c.created_at, home_notice.c.id)
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        for notice in notices:
            kind = notice["kind"]
            if kind == "reply":
                label, path = "jarvis replied", f"/m/{notice['message_id']}"
            elif kind == "approval":
                label, path = (
                    "jarvis needs a decision",
                    f"/d/action/{notice['action_id']}",
                )
            else:
                label, path = (
                    "jarvis needs a decision",
                    f"/d/question/{notice['message_id']}",
                )
            result = await sender.create_message(
                persisted_message_id=notice["id"],
                content=f"{label}\n{HOME_ORIGIN}{path}",
            )
            if isinstance(result, DeliveryFailed):
                logging.getLogger(__name__).warning(
                    "notification pending: %s", result.kind
                )
                return False
            async with database.begin() as connection:
                await connection.execute(
                    update(home_notice)
                    .where(home_notice.c.id == notice["id"])
                    .values(discord_message_id=result.discord_message_id)
                )
        if len(notices) < limit:
            return True
