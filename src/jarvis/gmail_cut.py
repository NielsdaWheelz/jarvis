"""Stopped audit of pre-revision send evidence. Never invokes a write binding."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, cast
from urllib.parse import quote
from uuid import UUID

from llm_tools import canonical_json_bytes
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import RowMapping, select

from jarvis._atomic_json import read_private_json, replace_private_json
from jarvis.actions import GMAIL_WRITE_NAMES, ActionStore
from jarvis.db import action
from jarvis.gmail_drafts import (
    GmailOperation,
    compose_snapshot,
    content_digest,
    metadata_marker,
    provider_id,
)
from jarvis.gmail_send import confirmed_sent_message, reconcile_gmail_send
from jarvis.write_connectors import GoogleWriteConnector
from jarvis.write_tools import (
    GmailContent,
    GmailRevision,
    GmailSnapshot,
    WriteConnectorFailure,
)

CUT_RECEIPT = "gmail-cut-v1.json"


class OwnerDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    outcome: Literal["sent", "absent"]
    evidence: str = Field(min_length=1, max_length=4_096)


async def historical_mail(actions: ActionStore) -> tuple[RowMapping, ...]:
    async with actions.engine.connect() as conn:
        rows = await conn.execute(
            select(
                action.c.id,
                action.c.tool_name,
                action.c.status,
                action.c.attempts,
                action.c.arguments,
                action.c.result,
            )
            .where(
                action.c.tool_name.in_(GMAIL_WRITE_NAMES),
                ~action.c.execution_contract.op("?")("mail"),
            )
            .order_by(action.c.created_at, action.c.id)
        )
        return tuple(rows.mappings())


def _digest(history: Sequence[RowMapping]) -> str:
    rows = [{**dict(row), "id": str(row["id"])} for row in history]
    return hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def verified_cut_ids(
    history: Sequence[RowMapping],
    path: Path,
) -> frozenset[UUID] | None:
    if any(
        row["status"] in {"queued", "awaiting_approval", "executing"} for row in history
    ):
        return None
    required = {
        str(row["id"])
        for row in history
        if row["tool_name"] == "gmail.send_draft"
        and row["status"] in {"succeeded", "uncertain"}
    }
    if not required:
        return frozenset()
    receipt = read_private_json(path)
    if receipt is None or receipt.get("inventory_sha256") != _digest(history):
        return None
    if receipt.get("status") != "clear" or not isinstance(receipt.get("actions"), dict):
        return None
    report = cast(dict[str, object], receipt["actions"])
    for identifier in required:
        item = report.get(identifier)
        if not isinstance(item, dict) or cast(dict[str, object], item).get(
            "outcome"
        ) not in ("sent", "absent"):
            return None
    return frozenset(map(UUID, required))


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("missing historical field")
    return cast(dict[str, object], value)


def _value(row: RowMapping) -> dict[str, object]:
    return _object(_object(row["result"])["value"])


def _prior_revision(
    before: Sequence[RowMapping],
    send: RowMapping,
    account: str,
) -> tuple[GmailRevision, GmailSnapshot]:
    arguments = _object(send["arguments"])
    old = _object(arguments.get("arguments", arguments))
    content = GmailContent.model_validate(old["content"])
    draft_id = provider_id(old, "draft_id")
    thread_id = provider_id(old, "thread_id")
    marker = provider_id(old, "jarvis_effect_id")
    for previous in reversed(before):
        if (
            previous["tool_name"] == "gmail.send_draft"
            or previous["status"] != "succeeded"
        ):
            continue
        try:
            observation = _value(previous)
        except (ValueError, KeyError):
            continue
        if (observation.get("draft_id"), observation.get("jarvis_effect_id")) != (
            draft_id,
            marker,
        ):
            continue
        if observation.get("thread_id") != thread_id:
            raise ValueError("historical draft thread changed")
        previous_args = _object(previous["arguments"])
        previous_content = _object(previous_args.get("arguments", previous_args))
        if (
            GmailContent.model_validate(
                previous_content.get("replacement", previous_content.get("content"))
            )
            != content
        ):
            raise ValueError("historical send and last draft envelope differ")
        parent = (
            None
            if content.reply_to is None
            else content.reply_to.parent_rfc822_message_id
        )
        snapshot = compose_snapshot(
            content, account, (), parent, () if parent is None else (parent,)
        )
        return GmailRevision(
            account=account,
            draft_id=draft_id,
            message_id=provider_id(observation, "message_id"),
            thread_id=thread_id,
            jarvis_effect_id=marker,
            content_digest=content_digest(snapshot),
        ), snapshot
    raise ValueError("historical draft message id is unavailable")


async def _observe_recorded_send(
    mail: GmailOperation,
    row: RowMapping,
    account: str,
) -> str | None:
    try:
        value = _value(row)
        if value.get("account") not in (None, account):
            return None
        identifier = provider_id(value, "sent_message_id")
        expected = provider_id(value, "thread_id")
        marker = provider_id(value, "jarvis_effect_id")
        arguments = _object(row["arguments"])
        captured = _object(arguments.get("arguments", arguments))
        if (
            captured.get("thread_id", expected) != expected
            or captured.get("jarvis_effect_id", marker) != marker
        ):
            return None
        message = await mail.request(
            "GET",
            f"messages/{quote(identifier, safe='')}",
            account=account,
            params={
                "format": "metadata",
                "metadataHeaders": "X-Jarvis-Effect-ID",
                "fields": "id,threadId,labelIds,payload(headers)",
            },
            errors={404: None},
        )
        if (
            message is not None
            and confirmed_sent_message(message, thread_id=expected) == identifier
            and metadata_marker(message) == marker
        ):
            return identifier
    except (ValueError, KeyError, WriteConnectorFailure):
        pass
    return None


async def audit_mail_cut(
    connector: GoogleWriteConnector,
    history: Sequence[RowMapping],
    receipt_path: Path,
    owner_evidence: Mapping[str, object] | None,
) -> dict[str, object]:
    dispositions = TypeAdapter(dict[UUID, OwnerDisposition]).validate_python(
        {} if owner_evidence is None else owner_evidence
    )
    results: dict[str, dict[str, object]] = {}
    account: str | None = None
    for index, row in enumerate(history):
        identifier = cast(UUID, row["id"])
        entered_send = (
            row["tool_name"] == "gmail.send_draft"
            and row["status"] == "executing"
            and row["attempts"] > 0
        )
        if not entered_send and row["status"] in {
            "queued",
            "awaiting_approval",
            "executing",
        }:
            results[str(identifier)] = {
                "outcome": "unfinished",
                "evidence": row["status"],
            }
            continue
        if not entered_send and (
            row["tool_name"] != "gmail.send_draft"
            or row["status"] not in {"succeeded", "uncertain"}
        ):
            continue
        result: dict[str, object] = {
            "outcome": "unknown",
            "evidence": "historical send lacks complete evidence",
        }
        mail = connector.gmail_operation()
        try:
            async with asyncio.timeout_at(mail.deadline):
                if account is None:
                    account = await mail.account()
                sent_id = None
                if row["status"] == "succeeded":
                    sent_id = await _observe_recorded_send(mail, row, account)
                if sent_id is not None:
                    result = {
                        "outcome": "sent",
                        "sent_message_id": sent_id,
                        "evidence": "recorded id is a marked Gmail sent message",
                    }
                else:
                    revision, snapshot = _prior_revision(history[:index], row, account)
                    proof = await reconcile_gmail_send(mail, revision, snapshot)
                    if proof.value is not None:
                        result = {
                            "outcome": "sent",
                            "evidence": proof.evidence,
                            "sent_message_id": proof.value.sent_message_id,
                        }
                    elif proof.outcome == "absent":
                        result = {"outcome": "absent", "evidence": proof.evidence}
                    else:
                        result["evidence"] = proof.evidence
        except (ValueError, KeyError, WriteConnectorFailure, TimeoutError):
            pass
        if entered_send:
            result = {
                "outcome": "unfinished",
                "evidence": "entered",
                "observation": result,
            }
        elif result["outcome"] == "unknown" and identifier in dispositions:
            result = {
                **dispositions.pop(identifier).model_dump(mode="json"),
                "owner": True,
            }
        results[str(identifier)] = result
    if dispositions:
        raise ValueError("owner dispositions must name disputed historical sends")
    clear = all(item["outcome"] in ("absent", "sent") for item in results.values())
    receipt: dict[str, object] = {
        "status": "clear" if clear else "blocked",
        "inventory_sha256": _digest(history),
        "actions": results,
    }
    if clear:
        replace_private_json(receipt_path, receipt)
    return receipt
