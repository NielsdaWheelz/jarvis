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


class FilePageRef(FileRef):
    page: Annotated[int, Field(ge=1, le=2**53 - 1)]


DRIVE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,255}$"
type DriveId = Annotated[str, Field(pattern=DRIVE_ID_PATTERN)]


class DriveFileRef(_Ref):
    kind: Literal["drive_file"]
    subject: DriveId
    id: DriveId
    page: Annotated[int, Field(ge=1, le=2**53 - 1)] | None = None


class TodoRef(_Ref):
    kind: Literal["todo"]
    id: CanonicalUuid


class ProposalRef(_Ref):
    kind: Literal["proposal"]
    message_id: CanonicalUuid
    action_id: CanonicalUuid


type HomeRef = ViewRef | FilePageRef | FileRef | DriveFileRef | TodoRef | ProposalRef
HOME_REF_ADAPTER = TypeAdapter[HomeRef](HomeRef)
