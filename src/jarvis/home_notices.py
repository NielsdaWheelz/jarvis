"""Persist a private notification with the fact that earned it."""

from uuid import UUID, uuid5

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import home_notice
from jarvis.discord import DeliveryFailed, DiscordCreateMessageClient
from jarvis.home_pages import HOME_ORIGIN
from jarvis.ownership import Database


async def enqueue_notice(
    connection: AsyncConnection,
    message_id: UUID,
) -> None:
    await connection.execute(
        insert(home_notice).values(
            id=uuid5(message_id, "jarvis-home-notice:reply"),
            kind="reply",
            message_id=message_id,
        )
    )


async def deliver_pending(
    database: Database, sender: DiscordCreateMessageClient, limit: int
) -> DeliveryFailed | None:
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
            if notice["kind"] != "reply":
                raise RuntimeError("pending notice requires predecessor delivery")
            result = await sender.create_message(
                persisted_message_id=notice["id"],
                content=f"jarvis replied\n{HOME_ORIGIN}/m/{notice['message_id']}",
            )
            if isinstance(result, DeliveryFailed):
                return result
            async with database.begin() as connection:
                await connection.execute(
                    update(home_notice)
                    .where(home_notice.c.id == notice["id"])
                    .values(discord_message_id=result.discord_message_id)
                )
        if len(notices) < limit:
            return None
