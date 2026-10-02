"""Canonical deployment pause projection; message controls are the sole writer."""

from __future__ import annotations

from jarvis.messages import MessageStore


class PausedState:
    def __init__(self, store: MessageStore, conversation_id: str) -> None:
        self._store, self._conversation_id = store, conversation_id

    async def is_paused(self) -> bool:
        return await self._store.paused(self._conversation_id)


__all__ = ["PausedState"]
