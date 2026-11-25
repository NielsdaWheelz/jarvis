"""Complete, bounded Workspace read projections."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO

from llm_tools.content import fit_text_chunk, projection_digest
from llm_tools.schema import JsonObject

from jarvis.read_tools import GOOGLE_OUTPUT_BYTES


@dataclass(frozen=True, slots=True)
class GoogleProjection:
    """One complete projected value, with bounded reads and automatic unlinking."""

    source: JsonObject
    projection: str
    digest: str
    observed_at: datetime
    total_bytes: int
    file: BinaryIO

    @classmethod
    def create(
        cls,
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
            return chunk

        return fit_text_chunk(
            window,
            offset=offset,
            total_bytes=self.total_bytes,
            max_bytes=maximum,
            build=build,
            max_output_bytes=max_output_bytes,
        )
