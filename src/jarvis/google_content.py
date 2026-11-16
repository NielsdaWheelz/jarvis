"""Disposable Google text projections and account-bound collection cursors."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, BinaryIO

from llm_tools import canonical_json_bytes
from llm_tools.content import fit_text_chunk, projection_digest
from llm_tools.schema import JsonObject
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from jarvis.read_tools import GOOGLE_CURSOR_BYTES, GOOGLE_OUTPUT_BYTES


class GoogleCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(ge=1, le=1)]
    tool: str
    account: str
    scope_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    page_size: Annotated[int, Field(ge=1, le=2_500)]
    provider_page_token: Annotated[str | None, Field(min_length=1)]
    item_offset: Annotated[int, Field(ge=0, le=2**53 - 1)]
    page_digest: Annotated[str | None, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def suffix_digest(self) -> GoogleCursor:
        if bool(self.item_offset) != (self.page_digest is not None):
            raise ValueError("page suffix requires its complete digest")
        return self

    @classmethod
    def decode(cls, value: str) -> GoogleCursor:
        if (
            len(value.encode()) > GOOGLE_CURSOR_BYTES
            or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
        ):
            raise ValueError("cursor is malformed")
        try:
            decoded = base64.b64decode(
                value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
            )
            parsed = cls.model_validate_json(decoded)
        except (ValueError, binascii.Error, ValidationError):
            raise ValueError("cursor is malformed") from None
        if parsed.encode() != value:
            raise ValueError("cursor is not canonical")
        return parsed

    def encode(self) -> str:
        result = (
            base64.urlsafe_b64encode(canonical_json_bytes(self.model_dump(mode="json")))
            .decode("ascii")
            .rstrip("=")
        )
        if len(result) > GOOGLE_CURSOR_BYTES:
            raise ValueError("cursor is too large")
        return result


@dataclass(frozen=True, slots=True)
class GoogleProjection:
    """One complete projected value, with bounded reads and automatic unlinking."""

    key: tuple[str, ...]
    source: JsonObject
    projection: str
    digest: str
    observed_at: datetime
    total_bytes: int
    file: BinaryIO

    @classmethod
    def create(
        cls,
        key: tuple[str, ...],
        source: JsonObject,
        projection: str,
        observed_at: datetime,
        value: object,
        *,
        text: bool = False,
    ) -> GoogleProjection:
        output = tempfile.TemporaryFile(mode="w+b")
        digest = hashlib.sha256()
        total = 0
        try:
            if text:
                if not isinstance(value, str):
                    raise ValueError("text projection is not text")
                fragments = (
                    value[start : start + 65_536]
                    for start in range(0, len(value), 65_536)
                )
            else:
                fragments = json.JSONEncoder(
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).iterencode(value)
            for fragment in fragments:
                encoded = fragment.encode("utf-8")
                output.write(encoded)
                total += len(encoded)
                if total > 2**53 - 1:
                    raise ValueError("projection exceeds byte-offset range")
                digest.update(encoded)
            output.flush()
            return cls(
                key,
                source,
                projection,
                projection_digest(source, projection, digest.hexdigest()),
                observed_at,
                total,
                output,
            )
        except BaseException:
            output.close()
            raise

    def chunk(
        self,
        offset: int,
        maximum: int,
        *,
        nested: bool = False,
        max_output_bytes: int = GOOGLE_OUTPUT_BYTES,
    ) -> JsonObject:
        self.file.seek(offset)
        window = self.file.read(maximum + 4)

        def build(text: str, end: int, next_offset: int | None) -> JsonObject:
            chunk: JsonObject = {
                "source": self.source,
                "projection": self.projection,
                "digest": self.digest,
                "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
                "offset": offset,
                "end_offset": end,
                "total_bytes": self.total_bytes,
                "text": text,
                "next_offset": next_offset,
            }
            return {"projection": "text", "chunk": chunk} if nested else chunk

        return fit_text_chunk(
            window,
            offset=offset,
            total_bytes=self.total_bytes,
            max_bytes=maximum,
            build=build,
            max_output_bytes=max_output_bytes,
        )
