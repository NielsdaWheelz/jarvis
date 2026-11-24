"""Send the approved message and distinguish a sent copy from a surviving draft."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

from jarvis.gmail_drafts import (
    GmailOperation,
    content_digest,
    decode_mime,
    decode_raw,
    encode_for_write,
    metadata_marker,
    provider_id,
    provider_labels,
    read_revision,
)
from jarvis.write_tools import (
    GMAIL_WRITE_POLICY,
    GmailRevision,
    GmailSendContract,
    GmailSendDraftSuccess,
    GmailSnapshot,
    ReconciliationResult,
    WriteConnectorFailure,
    WriteResponse,
)

_THREAD_MESSAGE_LIMIT = 100


def confirmed_sent_message(
    message: dict[str, object],
    *,
    thread_id: str,
    previous_message_id: str | None = None,
) -> str:
    identifier = provider_id(message, "id")
    labels = provider_labels(message)
    if (
        identifier == previous_message_id
        or provider_id(message, "threadId") != thread_id
        or "SENT" not in labels
        or "DRAFT" in labels
    ):
        raise ValueError("Gmail did not identify a sent message in the expected thread")
    return identifier


async def gmail_send(
    mail: GmailOperation, contract: GmailSendContract
) -> WriteResponse[GmailSendDraftSuccess]:
    revision = contract.revision
    approved = contract.snapshot
    if await mail.account() != revision.account:
        raise WriteConnectorFailure("draft_changed", attempts=mail.attempts)
    draft = await read_revision(mail, revision)
    if draft.snapshot != approved:
        raise WriteConnectorFailure("draft_changed", attempts=mail.attempts)
    mime = await encode_for_write(
        mail, approved, revision.jarvis_effect_id, draft.parts
    )
    del draft
    payload = await mail.request(
        "POST",
        "drafts/send",
        account=revision.account,
        params={"fields": "id,threadId,labelIds"},
        metadata={"id": revision.draft_id, "message": {"threadId": revision.thread_id}},
        mime=mime,
        errors={
            400: "invalid_mail",
            404: "draft_not_found",
            409: "draft_changed",
            412: "draft_changed",
            429: "rate_limited",
        },
    )
    try:
        if payload is None:
            raise ValueError("Gmail did not return a send receipt")
        identifier = confirmed_sent_message(
            payload,
            thread_id=revision.thread_id,
            previous_message_id=revision.message_id,
        )
    except ValueError as exc:
        raise TimeoutError("Gmail draft send needs reconciliation") from exc
    return WriteResponse(
        GmailSendDraftSuccess(
            account=revision.account,
            sent_message_id=identifier,
            thread_id=revision.thread_id,
            jarvis_effect_id=revision.jarvis_effect_id,
            content_digest=revision.content_digest,
            sent_at=mail.now(),
        ),
        mail.attempts,
    )


@dataclass(frozen=True, slots=True)
class _ThreadObservation:
    selected_slice_complete: bool
    tail: bool
    expected_draft_present: bool
    sent_ids: set[str]
    conflict: bool


async def _observe_thread(
    mail: GmailOperation, revision: GmailRevision
) -> _ThreadObservation:
    payload = await mail.request(
        "GET",
        f"threads/{quote(revision.thread_id, safe='')}",
        account=revision.account,
        params={
            "format": "metadata",
            "metadataHeaders": "X-Jarvis-Effect-ID",
            "fields": "id,messages(id,threadId,labelIds,payload(headers))",
        },
        errors={404: "thread_not_found", 429: "rate_limited"},
    )
    if payload is None or provider_id(payload, "id") != revision.thread_id:
        raise ValueError("Gmail did not return the expected thread")
    response_messages = payload.get("messages")
    if not isinstance(response_messages, list) or not response_messages:
        raise ValueError("Gmail thread messages are absent")
    messages = cast(list[object], response_messages)
    complete = True
    conflict = False
    expected_draft_present = False
    seen_ids: set[str] = set()
    sent_ids: set[str] = set()
    for item in messages[:_THREAD_MESSAGE_LIMIT]:
        try:
            if not isinstance(item, dict):
                raise ValueError("Gmail thread message is malformed")
            message = cast(dict[str, object], item)
            identifier = provider_id(message, "id")
            if identifier in seen_ids:
                raise ValueError("Gmail thread message id is repeated")
            seen_ids.add(identifier)
            if provider_id(message, "threadId") != revision.thread_id:
                raise ValueError("Gmail message belongs to another thread")
            marker = metadata_marker(message)
        except ValueError:
            complete = False
            continue
        marked = marker == revision.jarvis_effect_id
        try:
            labels: frozenset[str] = (
                provider_labels(message) if "labelIds" in message else frozenset()
            )
        except ValueError:
            conflict = conflict or marked
            complete = False
            continue
        if not marked:
            if identifier == revision.message_id:
                complete = False
            continue
        if (
            "DRAFT" in labels
            and "SENT" not in labels
            and identifier == revision.message_id
        ):
            expected_draft_present = True
            continue
        if (
            "DRAFT" not in labels
            and "SENT" in labels
            and identifier != revision.message_id
        ):
            sent_ids.add(identifier)
        else:
            conflict = True
    return _ThreadObservation(
        complete,
        len(messages) > _THREAD_MESSAGE_LIMIT,
        expected_draft_present,
        sent_ids,
        conflict,
    )


def _sent_snapshot_matches(
    payload: dict[str, object],
    identifier: str,
    revision: GmailRevision,
    snapshot: GmailSnapshot,
) -> bool:
    if (
        confirmed_sent_message(
            payload,
            thread_id=revision.thread_id,
            previous_message_id=revision.message_id,
        )
        != identifier
    ):
        return False
    observed = decode_mime(decode_raw(payload.get("raw")), revision.account)
    return (
        observed.effect_id == revision.jarvis_effect_id
        and observed.snapshot == snapshot
    )


async def reconcile_gmail_send(
    mail: GmailOperation, revision: GmailRevision, snapshot: GmailSnapshot
) -> ReconciliationResult[GmailSendDraftSuccess]:
    try:
        account = await mail.account()
    except WriteConnectorFailure:
        # The fixed account URI can independently prove positive evidence.
        account = None
    if account is not None and account != revision.account:
        return ReconciliationResult("uncertain", "gmail-send-account-changed")

    intact_absences = 0
    conflict = False
    sent_ids: set[str] = set()
    for delay in GMAIL_WRITE_POLICY.recovery_delays:
        if delay:
            await mail.sleep(delay)
        intact = False
        try:
            await read_revision(mail, revision)
            intact = True
        except WriteConnectorFailure as exc:
            if exc.code == "draft_changed":
                conflict = True

        try:
            observation = await _observe_thread(mail, revision)
        except (ValueError, WriteConnectorFailure):
            continue
        sent_ids.update(observation.sent_ids)
        conflict = conflict or observation.conflict or len(sent_ids) > 1
        if conflict:
            continue
        if observation.sent_ids:
            identifier = next(iter(observation.sent_ids))
            try:
                payload = await mail.request(
                    "GET",
                    f"messages/{quote(identifier, safe='')}",
                    account=revision.account,
                    params={"format": "raw", "fields": "id,threadId,labelIds,raw"},
                    raw=True,
                    errors={404: "provider_unavailable", 429: "rate_limited"},
                )
                if payload is None:
                    continue
                matches = await asyncio.to_thread(
                    _sent_snapshot_matches, payload, identifier, revision, snapshot
                )
            except WriteConnectorFailure:
                continue
            except ValueError:
                matches = False
            if not matches:
                conflict = True
            elif observation.selected_slice_complete:
                return ReconciliationResult(
                    "succeeded",
                    "gmail-send-unique-matching-sent-message",
                    GmailSendDraftSuccess(
                        account=account,
                        sent_message_id=identifier,
                        thread_id=revision.thread_id,
                        jarvis_effect_id=revision.jarvis_effect_id,
                        content_digest=content_digest(snapshot),
                        sent_at=mail.now(),
                    ),
                )
        elif (
            intact
            and account is not None
            and observation.selected_slice_complete
            and not observation.tail
            and observation.expected_draft_present
            and not sent_ids
        ):
            intact_absences += 1
    if conflict:
        return ReconciliationResult("uncertain", "gmail-send-conflicting-evidence")
    if intact_absences == len(GMAIL_WRITE_POLICY.recovery_delays):
        return ReconciliationResult(
            "absent", "gmail-send-intact-draft-without-sent-match"
        )
    return ReconciliationResult("uncertain", "gmail-send-evidence-incomplete")
