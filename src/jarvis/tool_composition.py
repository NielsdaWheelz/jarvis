"""Production tool-catalog composition."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import cast
from uuid import UUID

import boto3  # pyright: ignore[reportMissingTypeStubs]
import httpx
from botocore.config import Config  # pyright: ignore[reportMissingTypeStubs]
from llm_tools import (
    BraveSearchProvider,
    SafeWebReader,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolFamily,
    Unavailable,
    WebSearchInput,
    WebSearchPolicy,
    bind_brave_web_search,
    bind_web_read,
    web_family,
    web_search_source_operation,
)
from llm_tools.schema import JsonObject
from sqlalchemy import text

from jarvis.action_requests import bind_action_requests
from jarvis.actions import ActionStore
from jarvis.admission import JarvisOwner
from jarvis.agent_control import AgentController
from jarvis.agent_tools import agent_family
from jarvis.approval_tools import approval_family
from jarvis.attachment_sources import AttachmentSources
from jarvis.attachment_tools import attachment_family
from jarvis.attachments import AttachmentStore, S3Client
from jarvis.connectors import GoogleTokenManager, MapsReadConnector
from jarvis.event_polling import EventPoller
from jarvis.event_tools import events_family
from jarvis.events import EventStore
from jarvis.gmail_arrivals import GmailArrivalSource
from jarvis.mail_files import MailFiles
from jarvis.memory_service import MemoryService
from jarvis.memory_tools import memory_family
from jarvis.ownership import Database
from jarvis.read_tools import (
    ATTACHMENT_CONNECT_SECONDS,
    ATTACHMENT_SOCKET_SECONDS,
    maps_family,
)
from jarvis.receipt_tools import receipt_family
from jarvis.settings import Settings
from jarvis.work import WorkStore
from jarvis.work_tools import work_family
from jarvis.workspace_consent import record_workspace_consent
from jarvis.workspace_mcp import WorkspaceApprovals, WorkspaceError, WorkspaceMcpClient
from jarvis.workspace_quota import GmailQuota
from jarvis.workspace_reads import (
    WorkspaceReadAccess,
    WorkspaceReads,
    workspace_read_families,
)
from jarvis.workspace_write_models import DraftEditorStamp
from jarvis.workspace_writes import WorkspaceWrites
from jarvis.write_tools import calendar_write_family, gmail_write_family


@dataclass(frozen=True, slots=True)
class ToolComposition:
    catalog: ToolCatalog
    workspace_writes: WorkspaceWrites
    event_poller: EventPoller
    attachments: AttachmentStore
    mail_files: MailFiles
    google_read: WorkspaceReads
    workspace_approvals: WorkspaceApprovals
    web_source_operation: Callable[[WebSearchInput], JsonObject | None]


def build_tool_composition(
    *,
    owner: JarvisOwner,
    settings: Settings,
    tokens: GoogleTokenManager,
    google_api_http: httpx.AsyncClient,
    workspace_access: Callable[[], WorkspaceReadAccess],
    maps_http: httpx.AsyncClient,
    brave_http: httpx.AsyncClient,
    memory: MemoryService,
    actions: ActionStore,
    agents: AgentController,
    work: WorkStore,
    events: EventStore,
    event_admitted: Callable[[], Awaitable[bool]],
    editor_stamp: DraftEditorStamp | None = None,
) -> ToolComposition:
    enrollment = tokens.enrollment()
    approvals = WorkspaceApprovals(
        audit=partial(record_workspace_consent, owner.database, owner.scope_id)
    )
    quota = (
        GmailQuota(owner.database, enrollment.project_id)
        if enrollment is not None
        else None
    )

    async def debit(grant_id: UUID, tool: str, background: bool) -> None:
        current = tokens.enrollment()
        if quota is None or current is None or current.grant_id != grant_id:
            raise WorkspaceError("grant_unavailable")
        await quota.debit(tool, background=background)

    workspace = WorkspaceMcpClient(
        google_api_http, credential=tokens.credential, debit=debit, approvals=approvals
    )
    tokens.on_grant_loss = workspace.invalidate
    google_read = WorkspaceReads(
        workspace,
        account=None if enrollment is None else enrollment.account,
        grant_id=None if enrollment is None else enrollment.grant_id,
        access=workspace_access,
    )
    attachments = build_attachment_store(
        settings=settings,
        database=actions.engine,
        google=google_read,
    )
    mail_files = MailFiles(
        attachments,
        settings.host_secrets,
        stage_root=settings.runtime_state_directory.parent / "mail-stage",
    )

    def draft_stamp(grant_id: UUID) -> DraftEditorStamp | None:
        current = tokens.enrollment()
        if (
            current is not None
            and editor_stamp is not None
            and current.grant_id == grant_id
            and current.subject == editor_stamp.google_sub
        ):
            return editor_stamp
        return None

    workspace_writes = WorkspaceWrites(workspace, mail_files, editor_stamp=draft_stamp)
    gmail_reads, calendar_reads = workspace_read_families(google_read)
    gmail_writes = gmail_write_family(workspace_writes)
    calendar_writes = calendar_write_family(workspace_writes)
    maps = MapsReadConnector(
        client=maps_http,
        api_key=settings.maps_api_key.get_secret_value(),
    )
    search_policy = WebSearchPolicy()
    brave = BraveSearchProvider(
        brave_http,
        api_key=settings.brave_api_key.get_secret_value(),
        policy=search_policy,
    )
    catalog = ToolCatalog.compose(
        (
            _bind_write_policy(agent_family(agents)),
            *(
                _bind_write_policy(
                    ToolFamily(
                        reads.namespace,
                        reads.declarations + writes.declarations,
                        reads.bindings + writes.bindings,
                    )
                )
                for reads, writes in (
                    (gmail_reads, gmail_writes),
                    (calendar_reads, calendar_writes),
                )
            ),
            maps_family(maps),
            web_family(
                search=bind_brave_web_search(
                    brave,
                    policy=search_policy,
                    operation_deadline_seconds=12.0,
                ),
                read=bind_web_read(SafeWebReader()),
            ),
            memory_family(memory),
            approval_family(),
            receipt_family(owner),
            _bind_write_policy(work_family(work)),
            _bind_write_policy(events_family(events)),
            _bind_write_policy(attachment_family(attachments)),
        )
    )
    if any(
        isinstance(catalog.binding(tool_id).execute, Unavailable)
        for tool_id in catalog.tool_ids
    ):
        raise RuntimeError("every application binding must be available")
    event_poller = EventPoller(
        store=events,
        source=(
            GmailArrivalSource(
                workspace,
                enrollment.account,
                enrollment.grant_id,
                enrollment.pending_label_id,
            )
            if enrollment is not None and enrollment.pending_label_id is not None
            else None
        ),
        admitted=event_admitted,
    )
    events.notify_changed = event_poller.notify_changed
    return ToolComposition(
        catalog,
        workspace_writes,
        event_poller,
        attachments,
        mail_files,
        google_read,
        approvals,
        partial(web_search_source_operation, policy=search_policy),
    )


def google_tokens(settings: Settings, http: httpx.AsyncClient) -> GoogleTokenManager:
    return GoogleTokenManager(
        state_path=settings.google_oauth_state_path,
        client=http,
        client_id=settings.google_oauth_client_id.get_secret_value(),
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        active_key_version=settings.connector_encryption_key_version,
        single_secret=settings.connector_encryption_secret.get_secret_value(),
        project_id=settings.workspace_project_id,
    )


def build_attachment_store(
    *,
    settings: Settings,
    database: Database,
    google: WorkspaceReads | None,
) -> AttachmentStore:
    async def require_owner() -> None:
        async with database.connect() as connection:
            await connection.execute(text("SELECT 1"))

    s3 = cast(
        S3Client,
        boto3.client(  # pyright: ignore[reportUnknownMemberType]
            "s3",
            endpoint_url=f"https://{settings.attachment_r2_account_id}.r2.cloudflarestorage.com",
            region_name="auto",
            aws_access_key_id=settings.attachment_r2_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.attachment_r2_secret_access_key.get_secret_value(),
            config=Config(
                retries={"total_max_attempts": 1},
                request_checksum_calculation="when_required",
                connect_timeout=ATTACHMENT_CONNECT_SECONDS,
                read_timeout=ATTACHMENT_SOCKET_SECONDS,
            ),
        ),
    )
    return AttachmentStore(
        database,
        settings.owner_scope,
        r2_account=settings.attachment_r2_account_id,
        bucket=settings.attachment_r2_bucket,
        cache_directory=settings.attachment_cache_directory,
        spool_directory=settings.runtime_state_directory / "uploads",
        s3_client=s3,
        sources=AttachmentSources(google=google),
        mutation_admitted=require_owner,
    )


def _bind_write_policy(family: ToolFamily) -> ToolFamily:
    bindings: list[ToolBinding[object, object, object]] = []
    for binding in family.bindings:
        if binding.spec.effect is not ToolEffect.Write:
            bindings.append(binding)
            continue
        inputs = {
            **binding.policy_inputs,
            "action_authority": "jarvis.action.v2",
        }
        bindings.append(
            ToolBinding(
                spec=binding.spec,
                execute=binding.execute,
                replay_policy=binding.replay_policy,
                implementation_revision=binding.implementation_revision,
                policy_epoch=binding.policy_epoch,
                policy_inputs=inputs,
            )
        )
    return bind_action_requests(
        ToolFamily(family.namespace, family.declarations, tuple(bindings))
    )


__all__ = [
    "ToolComposition",
    "build_attachment_store",
    "build_tool_composition",
    "google_tokens",
]
