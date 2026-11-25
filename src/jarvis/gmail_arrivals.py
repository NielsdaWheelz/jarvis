"""The five Google MCP calls admitted by the owner's Gmail arrival enrollment."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from jarvis.connectors import provider_array, provider_object
from jarvis.event_tools import EmailAdded, provider_id
from jarvis.events import Observation
from jarvis.read_tools import text_preview
from jarvis.workspace_mcp import (
    WorkspaceError,
    WorkspaceMcpClient,
    screen_workspace_content,
)


@dataclass(frozen=True, slots=True)
class GmailArrivalSource:
    client: WorkspaceMcpClient
    account: str
    grant_id: UUID
    label_id: str

    async def call(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        before_send: Callable[[], Awaitable[None]],
    ) -> dict[str, object]:
        return await self.client.call(
            "gmail",
            name,
            arguments,
            grant_id=self.grant_id,
            invocation_id=str(uuid4()),
            background=True,
            before_send=before_send,
        )


def items(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    return [provider_object(x, key) for x in provider_array(payload.get(key, []), key)]


def identity(payload: dict[str, object], key: str = "id") -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError("arrival identity absent")
    return provider_id(value)


def pending_label(payload: dict[str, object], label_id: str) -> tuple[str, int | None]:
    labels = items(payload, "labels")
    matches = [item for item in labels if item.get("labelId") == label_id]
    if len(matches) != 1:
        raise ValueError("enrolled label missing or ambiguous")
    label = matches[0]
    name, count = label.get("name"), label.get("messagesTotal")
    if (
        label.get("labelType") != "USER"
        or not isinstance(name, str)
        or not re.fullmatch(r"[\w ./-]{1,225}", name)
        or sum(item.get("name") == name for item in labels) != 1
        or ("messagesTotal" in label and (type(count) is not int or count < 0))
    ):
        # Do not reinterpret missing proto defaults as a confirmed zero. A name
        # outside the supported Gmail search grammar requires owner repair.
        raise ValueError("enrolled label cannot be counted or addressed safely")
    return name, count if isinstance(count, int) else None


def message_labels(message: dict[str, object]) -> set[str]:
    labels: set[str] = set()
    for value in provider_array(message.get("labelIds"), "message labels"):
        if not isinstance(value, str):
            raise ValueError("invalid message label")
        labels.add(provider_id(value))
    return labels


def eligible_labels(labels: set[str]) -> bool:
    return not labels.intersection({"DRAFT", "SPAM", "TRASH"}) and (
        "SENT" not in labels or "INBOX" in labels
    )


def observation(
    message: dict[str, object], account: str, thread: str, label: str, now: datetime
) -> Observation | None:
    message_id = identity(message)
    if "threadId" in message and message["threadId"] != thread:
        raise ValueError("message belongs to a different thread")
    if "labelIds" not in message:
        return None
    labels = message_labels(message)
    if label not in labels or not eligible_labels(labels):
        return None
    source_at = None
    raw = message.get("internalDate")
    if isinstance(raw, str) and raw.isascii() and raw.isdecimal():
        try:
            source_at = datetime.fromtimestamp(int(raw) / 1000, UTC)
        except (ValueError, OverflowError, OSError):
            pass
    date = message.get("date")
    if source_at is None and isinstance(date, str):
        try:
            parsed = datetime.fromisoformat(date)
            if parsed.utcoffset() is not None:
                source_at = parsed.astimezone(UTC)
        except (ValueError, OverflowError):
            pass
    sender, subject = message.get("sender"), message.get("subject")
    if (sender is not None and not isinstance(sender, str)) or (
        subject is not None and not isinstance(subject, str)
    ):
        raise ValueError("invalid gmail metadata")
    # Untrusted display text is optional. A withheld preview cannot hide
    # the independent fact that a verified labeled message arrived.
    try:
        screen_workspace_content(sender)
    except WorkspaceError:
        sender = None
    try:
        screen_workspace_content(subject)
    except WorkspaceError:
        subject = None
    event = EmailAdded(
        account=account,
        observed_at=now,
        message_id=message_id,
        thread_id=thread,
        metadata="available",
        source_at=source_at,
        sender=text_preview(sender) if isinstance(sender, str) else None,
        subject=text_preview(subject) if isinstance(subject, str) else None,
        inbox="INBOX" in labels,
    )
    return Observation("email_event", (account, message_id), event, source_at or now)
