"""Closed references passed between the shell, conversation and native main."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from jarvis.action_requests import CanonicalUuid
from jarvis.home_pages import REV_PATTERN, SLUG_PATTERN


class _Ref(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ViewRef(_Ref):
    kind: Literal["view"]
    slug: Annotated[str, Field(pattern=SLUG_PATTERN, max_length=64)]
    rev: Annotated[str, Field(pattern=REV_PATTERN)]


class FileRef(_Ref):
    kind: Literal["file"]
    id: CanonicalUuid


type PageNumber = Annotated[int, Field(ge=1, le=2**53 - 1)]


class FilePageRef(FileRef):
    page: PageNumber


DRIVE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,255}$"
DRIVE_MIME_PATTERN = r"^[a-z0-9.+-]+/[a-z0-9.+-]+$"
type DriveId = Annotated[str, Field(pattern=DRIVE_ID_PATTERN)]


class NativeDriveFileRef(_Ref):
    kind: Literal["drive_file"]
    subject: DriveId
    id: DriveId
    # Native structured output emits every key, including null for a whole file.
    page: PageNumber | None


class DriveFileRef(NativeDriveFileRef):
    page: PageNumber | None = None


class TodoRef(_Ref):
    kind: Literal["todo"]
    id: CanonicalUuid


class ProposalRef(_Ref):
    kind: Literal["proposal"]
    message_id: CanonicalUuid
    action_id: CanonicalUuid


class SourceRef(_Ref):
    kind: Literal["source"]
    slot: Annotated[int, Field(ge=1, le=2**53 - 1)]


class DraftPresentationRef(_Ref):
    """Host-generated only. The message containing it supplies the address."""

    kind: Literal["draft"] = "draft"
    request_id: CanonicalUuid
    create_action_id: CanonicalUuid


type HomeRef = ViewRef | FilePageRef | FileRef | DriveFileRef | TodoRef | ProposalRef
HOME_REF_ADAPTER = TypeAdapter[HomeRef](HomeRef)
