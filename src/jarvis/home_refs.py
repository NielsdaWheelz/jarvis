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
    page: Annotated[int, Field(ge=1)] | None = None


class TodoRef(_Ref):
    kind: Literal["todo"]
    id: CanonicalUuid


class DecisionRef(_Ref):
    kind: Literal["decision"]
    type: Literal["action", "question"]
    id: CanonicalUuid


type HomeRef = Annotated[
    ViewRef | FileRef | TodoRef | DecisionRef, Field(discriminator="kind")
]
HOME_REF_ADAPTER = TypeAdapter[HomeRef](HomeRef)
