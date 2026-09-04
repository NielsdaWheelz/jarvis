from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import Literal, Protocol

from llm_agent_kernel import (
    AgentDefinition,
    Checkpoint,
    ContextSourceDefect,
    HostInput,
    InputClaim,
    InputId,
    ThreadId,
)
from llm_tools import (
    PromptAttribute,
    PromptAttributeName,
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    render_prompt,
)


@dataclass(frozen=True, slots=True)
class CanonicalMessage:
    message_id: str
    role: Literal["owner", "assistant", "host"]
    text: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.message_id:
            raise ValueError("canonical message id must not be empty")
        if self.role not in ("owner", "assistant", "host"):
            raise ValueError("canonical message role is invalid")
        if not self.text:
            raise ValueError("canonical message text must not be empty")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("canonical message timestamp must be timezone-aware")


class CanonicalHistoryPort(Protocol):
    async def completed_history(
        self,
        thread_id: ThreadId,
        *,
        exclude_input_ids: tuple[InputId, ...],
        limit: int,
    ) -> tuple[CanonicalMessage, ...]: ...


class JarvisContextSource:
    def __init__(
        self,
        thread_id: ThreadId,
        history: CanonicalHistoryPort,
        *,
        history_limit: int = 100,
        history_max_bytes: int = 65_536,
    ) -> None:
        if type(history_limit) is not int or history_limit <= 0:
            raise ValueError("history limit must be a positive integer")
        if type(history_max_bytes) is not int or history_max_bytes <= 0:
            raise ValueError("history byte limit must be a positive integer")
        self._thread_id = thread_id
        self._history = history
        self._history_limit = history_limit
        self._history_max_bytes = history_max_bytes

    async def bootstrap(
        self, definition: AgentDefinition, claim: InputClaim
    ) -> PromptSections:
        del definition
        excluded = tuple(item.input_id for item in claim.inputs)
        messages = await self._history.completed_history(
            self._thread_id,
            exclude_input_ids=excluded,
            limit=self._history_limit,
        )
        if type(messages) is not tuple:
            raise ContextSourceDefect("canonical history returned invalid values")
        if len(messages) > self._history_limit:
            raise ContextSourceDefect("canonical history exceeded its row bound")
        if {message.message_id for message in messages}.intersection(
            map(str, excluded)
        ):
            raise ContextSourceDefect("canonical history included current input")
        if any(
            left.created_at > right.created_at for left, right in pairwise(messages)
        ):
            raise ContextSourceDefect("canonical history is not chronological")

        selected: list[PromptSection] = []
        used = 0
        for message in reversed(messages):
            section = _message_section(message)
            size = len(render_prompt(section).encode())
            if size > self._history_max_bytes and not selected:
                raise ContextSourceDefect(
                    "newest canonical history row exceeds its byte bound"
                )
            if used + size > self._history_max_bytes:
                break
            selected.append(section)
            used += size
        selected.reverse()
        if not selected:
            return PromptSections(())
        return PromptSections(
            (
                PromptSection(
                    PromptSectionKind("canonical_history"),
                    (),
                    PromptSections(tuple(selected)),
                ),
            )
        )

    async def continuation(
        self,
        definition: AgentDefinition,
        claim: InputClaim,
        inputs: tuple[HostInput, ...],
        through_checkpoint: Checkpoint,
    ) -> PromptSections:
        del definition, claim, inputs, through_checkpoint
        return PromptSections(())


def _message_section(message: CanonicalMessage) -> PromptSection:
    return PromptSection(
        PromptSectionKind("canonical_message"),
        (
            PromptAttribute(PromptAttributeName("message_id"), message.message_id),
            PromptAttribute(PromptAttributeName("role"), message.role),
            PromptAttribute(
                PromptAttributeName("source_timestamp"), message.created_at.isoformat()
            ),
        ),
        PromptText(message.text),
    )


__all__ = ["CanonicalHistoryPort", "CanonicalMessage", "JarvisContextSource"]
