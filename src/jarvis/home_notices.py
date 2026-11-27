"""Persist a private notification with the fact that earned it."""

from uuid import UUID, uuid5

from sqlalchemy import exists, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from jarvis.db import home_notice, message, workspace_block
from jarvis.fcm import FcmSender, NoticeKind, PushFailure
from jarvis.ownership import Database
from jarvis.phone import PhoneSlot


async def enqueue_notice(
    connection: AsyncConnection,
    message_id: UUID,
    *,
    kind: NoticeKind = "reply",
) -> None:
    await connection.execute(
        insert(home_notice).values(
            id=uuid5(message_id, "jarvis-home-notice:reply"),
            kind=kind,
            message_id=message_id,
        )
    )


async def deliver_pending(
    database: Database, sender: FcmSender, phone: PhoneSlot, limit: int
) -> PushFailure | None:
    """Drain committed notices in order. An unacknowledged send stays pending."""
    while True:
        async with database.connect() as connection:
            notices = (
                (
                    await connection.execute(
                        select(
                            home_notice.c.id,
                            home_notice.c.message_id,
                            home_notice.c.kind,
                        )
                        .join(message, message.c.id == home_notice.c.message_id)
                        .where(
                            home_notice.c.provider_id.is_(None),
                            or_(
                                message.c.source != "workspace_block",
                                exists().where(
                                    workspace_block.c.notice_anchor
                                    == home_notice.c.message_id,
                                    workspace_block.c.state == "needs_owner",
                                ),
                            ),
                        )
                        .order_by(home_notice.c.created_at, home_notice.c.id)
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        for notice in notices:
            try:
                state = await phone.read()
            except OSError:
                return PushFailure("slot")
            if state.fid is None:
                return None
            result = await sender.send(
                state.fid, notice["id"], notice["message_id"], notice["kind"]
            )
            if isinstance(result, PushFailure):
                if result.kind != "unregistered":
                    return result
                try:
                    await phone.unregister(state.generation)
                except OSError:
                    return PushFailure("slot")
                # Re-read the same pending notice against the current generation.
                break
            async with database.begin() as connection:
                await connection.execute(
                    update(home_notice)
                    .where(
                        home_notice.c.id == notice["id"],
                        home_notice.c.provider_id.is_(None),
                    )
                    .values(provider="fcm", provider_id=result)
                )
        else:
            if len(notices) < limit:
                return None
