"""Canonical main request and terminal contracts."""

from typing import Self

from pydantic import model_validator

from jarvis import terminal
from jarvis.home_refs import SourceRef

NATIVE_REQUEST_SCHEMA = "jarvis-native-request.v9"
NATIVE_OUTPUT_NAME = "jarvis_home_message_v6"


class JarvisNativeMessage(terminal.JarvisNativeMessage):
    sources: list[terminal.Source]

    @model_validator(mode="after")
    def progress_and_silence_have_no_sources(self) -> Self:
        if (
            isinstance(self.response, terminal.Progress | terminal.Silent)
            and self.sources
        ):
            raise ValueError("progress and silence have no citations")
        if isinstance(self.response, terminal.Progress) and isinstance(
            self.response.present and self.response.present.ref, SourceRef
        ):
            raise ValueError("a source is presented only by a final")
        return self


class JarvisTerminal(terminal.JarvisTerminal):
    sources: list[terminal.Source]

    @model_validator(mode="after")
    def silent_has_no_sources(self) -> Self:
        if isinstance(self.response, terminal.Silent) and self.sources:
            raise ValueError("silence has no citations")
        return self

    @classmethod
    def from_seal(cls, name: str, value: object) -> Self:
        if name != NATIVE_OUTPUT_NAME:
            raise ValueError("unrecognized native seal contract")
        return cls.model_validate(value)
