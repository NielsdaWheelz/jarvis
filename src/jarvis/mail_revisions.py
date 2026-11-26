"""Read a locally retained draft after its presentation has been authorized."""

from __future__ import annotations

from dataclasses import dataclass
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
from jarvis.workspace_write_models import (
    DraftSnapshot,
    DraftWriteReceipt,
    FrozenCompose,
    FrozenWorkspaceWrite,
    Mailbox,
)
from jarvis.write_tools import (
    WORKSPACE_IMPLEMENTATION,
    WORKSPACE_MAIL_SNAPSHOT_REVISIONS,
    GmailRevision,
    GmailSnapshot,
)


@dataclass(frozen=True, slots=True)
class VerifiedWorkspaceDraft:
    receipt: DraftWriteReceipt
    compose: FrozenCompose
    snapshot: DraftSnapshot | None

    @property
    def quote(self) -> str | None:
        if self.snapshot is None or not self.receipt.generated_quote:
            return None
        return self.snapshot.body_text[len(self.compose.content.body_text) :]


type VerifiedCompose = VerifiedDraft | VerifiedWorkspaceDraft
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
    revision = stored.execution_contract.implementation_revision
    if revision not in WORKSPACE_MAIL_SNAPSHOT_REVISIONS | {WORKSPACE_IMPLEMENTATION}:
        return verified_draft(stored)
    if stored.status != "succeeded" or stored.tool_name not in {
        "gmail.create_draft",
        "gmail.prepare_replacement",
    }:
        return None
    result = stored.result or {}
    try:
        frozen = FrozenWorkspaceWrite.model_validate(
            stored.execution_contract.as_json().get("workspace")
        )
        compose = frozen.effect
        if not isinstance(compose, FrozenCompose) or compose.tool != stored.tool_name:
            raise ValueError("wrong compose effect")
        receipt = DraftWriteReceipt.model_validate(result.get("value"))
        if receipt.verification != "verified":
            return None
        if (
            result.get("type") != "Success"
            or (receipt.action_id, frozen.action_id) != (stored.id, stored.id)
            or (receipt.account, receipt.grant_id, receipt.files)
            != (frozen.account, frozen.grant_id, compose.files)
        ):
            raise ValueError("receipt differs from frozen compose")
        snapshot = None
        if revision in WORKSPACE_MAIL_SNAPSHOT_REVISIONS:
            snapshot = DraftSnapshot.model_validate(result.get("draft_revision"))
            if not compose.matches_snapshot(snapshot, receipt):
                raise ValueError("snapshot differs from verified compose")
        return VerifiedWorkspaceDraft(receipt, compose, snapshot)
    except ValueError as exc:
        raise ActionPersistenceDefect("invalid verified create evidence") from exc


def integrity_failure() -> Record:
    return {
        "status": "integrity",
        "editable": False,
        **dict.fromkeys((*_FIELDS, "from", "observed_at", "quote", "omission")),
    }


def unavailable_revision() -> Record:
    return {
        **integrity_failure(),
        "status": "unavailable",
        "omission": "exact revision unavailable",
    }


def inspect_revision(stored: StoredAction, *, saved: bool) -> Record:
    observed_at: datetime | None = None
    omission = None
    quote = None
    if saved:
        verified = verified_compose(stored)
        if verified is None:
            raise ActionPersistenceDefect(
                "linked saved draft lacks its verified receipt"
            )
        if isinstance(verified, VerifiedDraft):
            observed_at, snapshot = verified.receipt.observed_at, verified.snapshot
        else:
            observed_at = verified.receipt.observed_at
            snapshot = verified.snapshot
            quote = verified.quote
            if snapshot is None:
                snapshot = DraftSnapshot(
                    **verified.compose.content.model_dump(include=_FIELDS),
                    sender=Mailbox(name=None, address=verified.receipt.account),
                    files=verified.receipt.files,
                )
                if verified.receipt.generated_quote:
                    omission = "gmail's appended quote was not retained"
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
        "status": "partial" if omission else "complete",
        "editable": False,
        "observed_at": observed_at,
        "quote": quote,
        "omission": omission,
        "from": sender,
        **snapshot.model_dump(mode="json", include=_FIELDS),
    }
