"""Read a locally retained draft after its presentation has been authorized."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from jarvis.actions import ActionPersistenceDefect, StoredAction
from jarvis.gmail_drafts import (
    VerifiedDraft,
    content_digest,
    gmail_effect_id,
    verified_draft,
)
from jarvis.workspace_write_models import DraftSnapshot, DraftWriteReceipt
from jarvis.write_tools import (
    WORKSPACE_MAIL_IMPLEMENTATION,
    GmailRevision,
    GmailSnapshot,
)

type VerifiedCompose = VerifiedDraft | tuple[DraftWriteReceipt, DraftSnapshot]
type Record = dict[str, Any]
_FIELDS = {"to", "cc", "bcc", "subject", "body_text", "files"}


class _HistoricalSend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["send"]
    creation_id: UUID
    revision: GmailRevision
    snapshot: GmailSnapshot


def verified_compose(stored: StoredAction) -> VerifiedCompose | None:
    """Shared proof for final settlement and later inspection of the saved link."""
    if (
        stored.execution_contract.implementation_revision
        != WORKSPACE_MAIL_IMPLEMENTATION
    ):
        return verified_draft(stored)
    if stored.status != "succeeded" or stored.tool_name != "gmail.create_draft":
        return None
    result = stored.result or {}
    try:
        # recorded_action has checked this receipt against the frozen create,
        # including its action, account, manifest, body and any provider quote.
        receipt = DraftWriteReceipt.model_validate(result.get("value"))
        if receipt.verification != "verified":
            return None
        return receipt, DraftSnapshot.model_validate(result.get("draft_revision"))
    except ValueError as exc:
        raise ActionPersistenceDefect("invalid verified create evidence") from exc


def integrity_failure() -> Record:
    return {"status": "integrity", **dict.fromkeys((*_FIELDS, "from", "observed_at"))}


def inspect_revision(stored: StoredAction, *, saved: bool) -> Record:
    observed_at: datetime | None = None
    if saved:
        verified = verified_compose(stored)
        if verified is None:
            raise ActionPersistenceDefect(
                "linked saved draft lacks its verified receipt"
            )
        if isinstance(verified, VerifiedDraft):
            observed_at, snapshot = verified.receipt.observed_at, verified.snapshot
        else:
            receipt, snapshot = verified
            observed_at = receipt.observed_at
    else:
        mail = _HistoricalSend.model_validate(
            stored.execution_contract.as_json().get("mail")
        )
        snapshot = mail.snapshot
        if (
            snapshot.sender != mail.revision.account
            or gmail_effect_id(mail.creation_id) != mail.revision.jarvis_effect_id
            or content_digest(snapshot) != mail.revision.content_digest
        ):
            raise ActionPersistenceDefect(
                "send snapshot differs from its captured revision"
            )
    sender = (
        {"name": None, "address": snapshot.sender}
        if isinstance(snapshot, GmailSnapshot)
        else snapshot.sender.model_dump(mode="json")
    )
    return {
        "status": "complete",
        "observed_at": observed_at,
        "from": sender,
        **snapshot.model_dump(mode="json", include=_FIELDS),
    }
