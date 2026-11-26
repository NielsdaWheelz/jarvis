"""Observe attributed skid jobs without opening their terminals."""

from __future__ import annotations

import asyncio
import hashlib
import json
from base64 import b64decode
from collections.abc import Awaitable, Callable, Coroutine
from time import monotonic
from typing import TYPE_CHECKING, Any
from uuid import UUID

from llm_agent_kernel import CancellationToken
from llm_tools.content import utf8_slice

from jarvis.agent_tools import (
    JOB_PAGE_BYTES,
    JOB_RESULT_SECONDS,
    AgentDelegateInput,
    AgentMachineId,
    DelegationState,
    JobOutcome,
    WireFailure,
    WireJobAck,
    WireJobPage,
    WireJobSubmission,
)

if TYPE_CHECKING:
    from llm_tools import FrozenToolPlan

    from jarvis.actions import ActionStore, StoredAction
    from jarvis.agent_control import AgentController


def delegation_evidence(state: DelegationState) -> dict[str, object]:
    """Project both a live receipt and a completed wake from one owned result."""
    value: dict[str, object] = state.registration_receipt.model_dump(mode="json")
    if state.terminal is not None:
        value["terminal"] = {"machine": state.machine, "handle": state.terminal.handle}
    outcome = state.outcome
    if outcome is None:
        return value
    value["state"] = outcome.state
    if outcome.reason is not None:
        value["reason"] = outcome.reason
    if outcome.answer is not None:
        answer = outcome.answer.encode()
        if len(answer) <= 8_192:
            value["answer"] = outcome.answer
        else:
            preview = utf8_slice(answer, 0, 8_192).decode()
            value["answer_preview"] = preview
            value["answer_shortened"] = True
            value["read_selection"] = {
                "kind": "worker_answer",
                "job_id": str(state.registration_receipt.job_id),
                "offset": 0,
                "max_bytes": 32_768,
                "expected_digest": None,
            }
    return value


async def _until_stopped[T](
    operation: Coroutine[Any, Any, T], cancellation: CancellationToken
) -> T | None:
    running = asyncio.create_task(operation)
    stopped = asyncio.create_task(cancellation.wait())
    try:
        done, _ = await asyncio.wait(
            {running, stopped}, return_when=asyncio.FIRST_COMPLETED
        )
        if running in done:
            return running.result()
        return None
    finally:
        for task in (running, stopped):
            task.cancel()
        await asyncio.gather(running, stopped, return_exceptions=True)


class Delegations:
    def __init__(
        self, skid: AgentController, actions: ActionStore, source_conversation_id: str
    ) -> None:
        self._skid = skid
        self._actions = actions
        self._scope = source_conversation_id
        self._changed = asyncio.Event()

    def notify_changed(self) -> None:
        self._changed.set()

    async def run(
        self,
        cancellation: CancellationToken,
        *,
        paused: Callable[[], Awaitable[bool]],
        plan: FrozenToolPlan,
        on_event: Callable[[], None],
    ) -> None:
        from jarvis.write_dispatch import require_current_action_binding

        tasks: dict[UUID, tuple[asyncio.Task[None], CancellationToken]] = {}
        try:
            while not cancellation.cancelled:
                self._changed.clear()
                for job_id, (task, _) in tuple(tasks.items()):
                    if task.done():
                        task.result()
                        del tasks[job_id]
                if await paused():
                    for _, token in tasks.values():
                        token.cancel()
                else:
                    for stored in await self._actions.active_delegations(
                        source_conversation_id=self._scope
                    ):
                        if stored.id in tasks:
                            continue
                        require_current_action_binding(stored, plan)
                        token = CancellationToken()
                        task = asyncio.create_task(
                            self._observe(stored, token, on_event),
                            name=f"jarvis-delegation-{stored.id}",
                        )
                        task.add_done_callback(lambda _: self._changed.set())
                        tasks[stored.id] = (task, token)
                await _until_stopped(self._changed.wait(), cancellation)
        finally:
            for _, token in tasks.values():
                token.cancel()
            for result in await asyncio.gather(
                *(task for task, _ in tasks.values()), return_exceptions=True
            ):
                if isinstance(result, BaseException):
                    raise result

    async def _observe(
        self,
        stored: StoredAction,
        cancellation: CancellationToken,
        on_event: Callable[[], None],
    ) -> None:
        from jarvis.actions import delegation_state
        from jarvis.agent_control import AgentOutcomeUnknown

        state = delegation_state(stored)
        machine_id = stored.agent_placement.machine_id
        if state.outcome is not None:
            await self._ack(stored.id, machine_id, cancellation)
            return
        request = AgentDelegateInput.model_validate(stored.payload)
        address = [str(stored.id), "--machine", machine_id]
        submit = state.submission == "unentered"
        delay = 1.0
        while not cancellation.cancelled:
            if submit:
                admitted = await self._actions.enter_delegation_submission(
                    stored.id,
                    source_conversation_id=self._scope,
                )
                if admitted is None or cancellation.cancelled:
                    return
                state = admitted
                try:
                    receipt = await _until_stopped(
                        self._skid.call(
                            ["job", "submit", *address, "--stdin"],
                            WireJobSubmission,
                            text=json.dumps(
                                request.model_dump(
                                    mode="json", exclude_none=True, exclude={"machine"}
                                ),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            write=True,
                        ),
                        cancellation,
                    )
                except AgentOutcomeUnknown:
                    receipt = WireFailure(code="unavailable", dispatch="unknown")
                if receipt is None:
                    return
                submit = False
                if (
                    isinstance(receipt, WireJobSubmission)
                    and receipt.job_id == stored.id
                ):
                    state = await self._actions.confirm_delegation_submission(
                        stored.id, terminal=receipt.job_terminal
                    )
                    delay = 1.0
                elif isinstance(receipt, WireFailure):
                    if receipt.code == "JobConflict" or (
                        receipt.dispatch == "not_sent"
                        and receipt.code not in {"unavailable", "machine_unknown"}
                    ):
                        await self._actions.finish_delegation(
                            stored.id,
                            JobOutcome(state="failed", reason=receipt.code),
                            terminal=None,
                            acknowledge=False,
                            source_conversation_id=self._scope,
                        )
                        on_event()
                        return
            started = monotonic()
            page = await _until_stopped(
                self._skid.call(
                    ["job", "result", *address],
                    WireJobPage,
                    deadline_seconds=JOB_RESULT_SECONDS,
                ),
                cancellation,
            )
            if page is None:
                return
            if isinstance(page, WireFailure):
                if page.code == "JobPending":
                    if state.submission != "confirmed":
                        state = await self._actions.confirm_delegation_submission(
                            stored.id, terminal=None
                        )
                    if monotonic() - started >= delay:
                        delay = 1.0
                        continue
                if page.code in {"JobNotFound", "JobAcknowledged"}:
                    if page.code == "JobNotFound" and state.submission != "confirmed":
                        submit = True
                    else:
                        await self._actions.finish_delegation(
                            stored.id,
                            JobOutcome(state="unknown", reason="result_lost"),
                            terminal=None,
                            acknowledge=False,
                            source_conversation_id=self._scope,
                        )
                        on_event()
                        return
            elif page.job_id == stored.id and state.terminal in (
                None,
                page.job_terminal,
            ):
                outcome = await self._collect(address, page, cancellation)
                if outcome is not None:
                    await self._actions.finish_delegation(
                        stored.id,
                        outcome,
                        terminal=page.job_terminal,
                        acknowledge=True,
                        source_conversation_id=self._scope,
                    )
                    on_event()
                    await self._ack(stored.id, machine_id, cancellation)
                    return
            await _until_stopped(asyncio.sleep(delay), cancellation)
            delay = min(delay * 2, 30.0)

    async def _collect(
        self,
        address: list[str],
        first: WireJobPage,
        cancellation: CancellationToken,
    ) -> JobOutcome | None:
        page = first
        content = bytearray()
        try:
            while True:
                if page.offset != len(content):
                    return None
                decoded = b64decode(page.page, validate=True)
                if len(decoded) != min(JOB_PAGE_BYTES, first.length - page.offset):
                    return None
                content.extend(decoded)
                if len(content) == first.length:
                    break
                next_page = await _until_stopped(
                    self._skid.call(
                        ["job", "result", *address, "--offset", str(len(content))],
                        WireJobPage,
                        deadline_seconds=JOB_RESULT_SECONDS,
                    ),
                    cancellation,
                )
                if not isinstance(next_page, WireJobPage) or next_page.model_dump(
                    exclude={"page", "offset"}
                ) != first.model_dump(exclude={"page", "offset"}):
                    return None
                page = next_page
            if hashlib.sha256(content).hexdigest() != first.sha256:
                return None
            answer = content.decode()
        except ValueError:
            return None
        if "\x00" in answer or (first.state == "answered" and not answer):
            return None
        return JobOutcome(state=first.state, reason=first.reason, answer=answer or None)

    async def _ack(
        self, job_id: UUID, machine_id: AgentMachineId, cancellation: CancellationToken
    ) -> None:
        delay = 1.0
        while not cancellation.cancelled:
            result = await _until_stopped(
                self._skid.call(
                    ["job", "ack", str(job_id), "--machine", machine_id],
                    WireJobAck,
                ),
                cancellation,
            )
            if isinstance(result, WireJobAck) or (
                isinstance(result, WireFailure) and result.code == "JobAcknowledged"
            ):
                await self._actions.acknowledge_delegation(job_id)
                return
            await _until_stopped(asyncio.sleep(delay), cancellation)
            delay = min(delay * 2, 30.0)
