#!/usr/bin/env python3
"""Explicitly opt-in shared-Codex qualification; never use default tmux."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import stat
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from llm_tools import BudgetState, FrozenToolPlan, ToolId
    from pydantic import BaseModel

    from jarvis.actions import ActionStore
    from jarvis.codex_control import CodexHostConfig
    from jarvis.codex_tools import CodexTerminal

PROFILES = ("personal", "work", "work2")
_UNQUALIFIED = (
    "tui_attachment_and_manual_input",
    "pending_approval_replay_and_single_response",
    "skid_inventory_and_phone_attachment",
    "contained_cognition_coexistence",
    "lost_submit_and_original_input_restart",
)
_PROMPT = (
    "This is a synthetic control qualification. Do not use tools, read files, "
    "write files, or access the network. Reply with one short acknowledgement."
)


class QualificationFailure(RuntimeError):
    """Only a host-owned stage label may enter evidence."""


def _private_file(path: Path) -> bytes:
    with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
        ):
            raise ValueError("qualification preparation must be root-owned")
        content = stream.read(65537)
    if len(content) > 65536:
        raise ValueError("qualification preparation exceeds bound")
    return content


def isolated_runner_source(tmux: Path, socket_name: str) -> bytes:
    """The closed runner the prepared test deployment must install."""
    if not re.fullmatch(r"jarvis-codex-qualify-[0-9a-f]{32}", socket_name):
        raise ValueError("qualification requires a unique isolated socket name")
    if (
        not tmux.is_absolute()
        or os.path.normpath(str(tmux)) != str(tmux)
        or any(ord(character) < 32 for character in str(tmux))
    ):
        raise ValueError("qualification requires an absolute tmux binary")
    return (
        f'#!/bin/sh\nexec {shlex.quote(str(tmux))} -L {shlex.quote(socket_name)} "$@"\n'
    ).encode()


def validate_preparation(
    *,
    runner: bytes,
    tmux: Path,
    socket_name: str,
    launcher_socket: Path,
    database_url: str,
) -> None:
    if runner != isolated_runner_source(tmux, socket_name):
        raise ValueError("prepared launcher must use the exact isolated runner")
    if (
        launcher_socket.parent.name != socket_name
        or launcher_socket.name != "launcher.sock"
    ):
        raise ValueError("launcher socket must identify the isolated preparation")
    database = urlsplit(database_url)
    if (
        database.scheme != "postgresql+psycopg"
        or database.hostname not in ("127.0.0.1", "localhost", "::1")
        or not re.fullmatch(r"/jarvis_codex_qualify_[a-z0-9_]+", database.path)
    ):
        raise ValueError("qualification requires an explicitly disposable database")


async def _tmux(runner: str, *arguments: str) -> tuple[int, bytes]:
    # Every caller uses the previously verified -L wrapper. No default server,
    # terminal capture, send-keys, shell command, or provider process is launched here.
    child = await asyncio.create_subprocess_exec(
        runner,
        *arguments,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TERM": "xterm"},
    )
    try:
        async with asyncio.timeout(5):
            assert child.stdout is not None
            output = await child.stdout.read(65537)
            if len(output) > 65536:
                raise QualificationFailure("terminal_output_bound")
            return await child.wait(), output
    except BaseException:
        if child.returncode is None:
            child.kill()  # Only this invocation's tmux client, never its server.
        await child.wait()
        raise


async def observe_terminal(runner: str, session_id: str, name: str) -> bool:
    if not re.fullmatch(r"\$[0-9]+", session_id) or not re.fullmatch(
        r"jarvis-qualify-[0-9a-f]{32}-(?:personal|work|work2)", name
    ):
        raise ValueError("terminal observation requires an exact test identity")
    status, output = await _tmux(
        runner,
        "display-message",
        "-p",
        "-t",
        session_id,
        "#{session_id}\t#{session_name}",
    )
    return status == 0 and output == f"{session_id}\t{name}\n".encode()


async def cleanup_terminals(runner: str, terminals: Sequence[CodexTerminal]) -> bool:
    complete = True
    for terminal in terminals:
        try:
            if not await observe_terminal(
                runner, terminal.tmux_session_id, terminal.tmux_name
            ):
                complete = False
                continue
            status, _ = await _tmux(
                runner, "kill-session", "-t", terminal.tmux_session_id
            )
            complete = complete and status == 0
        except (OSError, TimeoutError, QualificationFailure):
            complete = False
    return complete


class _NoTelemetry:
    def event(self, name: str, attributes: dict[str, object]) -> None:
        del name, attributes


async def _write(
    *,
    actions: ActionStore,
    plan: FrozenToolPlan,
    budgets: BudgetState,
    origin: UUID,
    ordinal: int,
    tool: ToolId,
    value: BaseModel,
    expect_uncertain: bool = False,
) -> dict[str, object]:
    from llm_agent_kernel import CancellationToken
    from llm_tools import (
        EffectId,
        ExecutionContext,
        InvocationPosition,
        ParsedJson,
        Principal,
        RecoveryRequired,
        ReplayPolicy,
        Scope,
        ToolEffect,
        ToolExecutor,
        raw_input_digest,
    )

    from jarvis.actions import ActionPositionRecorder, ExecutionContract

    binding, grant = plan.catalog_view.binding(tool), plan.grant(tool)
    if (
        binding.spec.effect is not ToolEffect.Write
        or binding.replay_policy is not ReplayPolicy.BilledOnce
    ):
        raise QualificationFailure("write_contract")
    arguments = cast("dict[str, object]", value.model_dump(mode="json"))
    stored = await actions.insert_automatic(
        tool_name=tool,
        arguments=arguments,
        execution_contract=ExecutionContract(
            tool_contract_revision=binding.spec.tool_contract_revision,
            implementation_revision=binding.implementation_revision,
            policy_revision=binding.policy_revision,
            plan_revision=plan.plan_revision,
            tool_effect=binding.spec.effect,
            replay_policy=binding.replay_policy,
            input_digest=raw_input_digest(ParsedJson(arguments)),
            max_attempts=1,
            claim_id=str(origin),
            through_checkpoint=str(origin),
            model_step_ordinal=ordinal,
            input_message_ids=(str(origin),),
            write_gate_supporting_owner_message_ids=(str(origin),),
        ),
        origin_message_id=origin,
    )

    def context() -> ExecutionContext:
        return ExecutionContext(
            plan=plan,
            grant=grant,
            catalog_view=plan.catalog_view,
            position=InvocationPosition(str(stored.id)),
            recorder=ActionPositionRecorder(
                store=actions,
                action_id=stored.id,
                implementation_revision=binding.implementation_revision,
                max_external_attempts=grant.limits.max_attempts,
            ),
            effect_id=EffectId(str(stored.id)),
            budgets=budgets,
            principal=Principal("jarvis-owner"),
            scope=Scope("codex-control-qualification"),
            cancellation=CancellationToken(),
            telemetry=_NoTelemetry(),
        )

    async def execute() -> dict[str, object]:
        try:
            return await ToolExecutor.execute(binding, ParsedJson(arguments), context())
        except RecoveryRequired:
            observed = await actions.get(stored.id)
            if not expect_uncertain or observed is None or observed.result is None:
                raise QualificationFailure("unconfirmed_write") from None
            return observed.result

    result = await execute()
    # A fresh recorder must replay this same occupied position, never re-enter
    # a handler. This is not original-owner-input restart qualification.
    replayed = await execute()
    terminal = await actions.get(stored.id)
    expected_status = "uncertain" if expect_uncertain else "succeeded"
    if (
        replayed != result
        or terminal is None
        or terminal.attempts != 1
        or terminal.status != expected_status
        or terminal.result != result
    ):
        raise QualificationFailure("action_settlement_and_replay")
    if expect_uncertain:
        error = result.get("error")
        if not isinstance(error, dict):
            raise QualificationFailure("unknown_launch")
        error = cast("dict[str, object]", error)
        if error.get("type") != "Unknown":
            raise QualificationFailure("unknown_launch")
        return error
    output = result.get("value")
    if result.get("type") != "Success" or not isinstance(output, dict):
        raise QualificationFailure("write_result")
    return cast("dict[str, object]", output)


async def _journey(
    host: CodexHostConfig, args: argparse.Namespace, database_url: str
) -> dict[str, object]:
    from llm_agent_kernel import (
        CancellationToken,
        Checkpoint,
        ClaimId,
        DispatchLineage,
        InputId,
    )
    from llm_tools import (
        CapabilityProfile,
        HostTable,
        ProfileId,
        RunLimits,
        ToolCatalog,
        ToolGrant,
        ToolId,
        ToolPlan,
    )
    from provider_runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig

    from jarvis.actions import ActionStore
    from jarvis.admission import ExactToolBudgetFactory
    from jarvis.codex_control import CodexController
    from jarvis.codex_tools import (
        CodexAccepted,
        CodexInterruptInput,
        CodexListInput,
        CodexPromptInput,
        CodexReadInput,
        CodexStarted,
        CodexStartInput,
        CodexSubmit,
        CodexThreadTarget,
        CodexUnknown,
        codex_family,
    )
    from jarvis.db import create_engine
    from jarvis.messages import MessageStore
    from jarvis.read_dispatch import ReadToolDispatcher

    status, output = await _tmux(host.tmux, "list-sessions", "-F", "#{session_id}")
    if status not in (0, 1) or output:
        raise QualificationFailure("isolated_socket_not_empty")
    engine = create_engine(database_url)
    terminals: list[CodexTerminal] = []
    observations: dict[str, dict[str, str]] = {}
    clean = False
    try:
        with tempfile.TemporaryDirectory(prefix="jarvis-control-qualify-") as state:
            config = AgentRuntimeConfig(
                state_root_base=Path(state), codex_endpoints=host.endpoints
            )
            async with AgentRuntime(config) as runtime:
                actions = ActionStore(engine)
                controller = CodexController(
                    control=runtime.codex, host=host, actions=actions
                )
                catalog = ToolCatalog.compose((codex_family(controller),))
                profile = CapabilityProfile(
                    ProfileId("codex-qualification"),
                    tuple(ToolGrant(tool, None) for tool in catalog.tool_ids),
                    RunLimits(30, 100, 1048576, 2097152, 1, 600.0),
                ).freeze(catalog)
                plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
                budgets = ExactToolBudgetFactory().create(plan)
                dispatcher = ReadToolDispatcher(host_secrets=(database_url,))
                origin = uuid4()
                await MessageStore(engine).insert_waking(
                    role="owner",
                    text=_PROMPT,
                    source="discord",
                    source_conversation_id="codex-control-qualification",
                    source_message_id=str(origin),
                    created_at=datetime.now(UTC),
                    message_id=origin,
                )
                ordinal = 0

                async def read(tool: str, value: BaseModel) -> dict[str, object]:
                    nonlocal ordinal
                    ordinal += 1
                    result = await dispatcher.dispatch(
                        binding=catalog.binding(ToolId(tool)),
                        validated_input=value,
                        plan=plan,
                        budgets=budgets,
                        cancellation=CancellationToken(),
                        lineage=DispatchLineage(
                            ClaimId(str(origin)),
                            Checkpoint(str(origin)),
                            (InputId(str(origin)),),
                            ordinal,
                        ),
                    )
                    if result.result.get("type") != "Success":
                        raise QualificationFailure("native_read")
                    return cast("dict[str, object]", result.result["value"])

                async def write(tool: str, value: BaseModel) -> dict[str, object]:
                    nonlocal ordinal
                    ordinal += 1
                    return await _write(
                        actions=actions,
                        plan=plan,
                        budgets=budgets,
                        origin=origin,
                        ordinal=ordinal,
                        tool=ToolId(tool),
                        value=value,
                    )

                targets: list[CodexThreadTarget] = []
                for key in PROFILES:
                    await read("codex.list", CodexListInput(profile=key))
                    started = CodexStarted.model_validate(
                        await write(
                            "codex.start",
                            CodexStartInput(
                                profile=key,
                                cwd=args.cwd,
                                name=f"jarvis-qualify-{args.socket_name[-32:]}-{key}",
                                prompt=_PROMPT,
                            ),
                        )
                    )
                    terminals.append(started.terminal)
                    ordinal += 1
                    collision = CodexUnknown.model_validate(
                        await _write(
                            actions=actions,
                            plan=plan,
                            budgets=budgets,
                            origin=origin,
                            ordinal=ordinal,
                            tool=ToolId("codex.start"),
                            expect_uncertain=True,
                            value=CodexStartInput(
                                profile=key,
                                cwd=args.cwd,
                                name=started.terminal.tmux_name,
                                prompt=_PROMPT,
                            ),
                        )
                    )
                    if (
                        collision.stage != "terminal"
                        or collision.prefix.type != "thread"
                    ):
                        raise QualificationFailure("collision_prefix")
                    unprompted = await read(
                        "codex.read", CodexReadInput(thread=collision.prefix.thread)
                    )
                    if unprompted.get("turn") is not None:
                        raise QualificationFailure("collision_dispatched_prompt")
                    if started.turn.thread.profile != key or not await observe_terminal(
                        host.tmux,
                        started.terminal.tmux_session_id,
                        started.terminal.tmux_name,
                    ):
                        raise QualificationFailure("terminal_identity")
                    # Existence is exact tmux evidence, never TUI-ready evidence.
                    target = started.turn.thread
                    native = await read("codex.read", CodexReadInput(thread=target))
                    if (
                        cast("dict[str, object]", native["thread"])["thread"]
                        != target.model_dump()
                    ):
                        raise QualificationFailure("native_thread_identity")
                    accepted = CodexAccepted.model_validate(
                        await write(
                            "codex.prompt",
                            CodexPromptInput(
                                thread=target, input=CodexSubmit(text=_PROMPT)
                            ),
                        )
                    )
                    if accepted.turn.thread != target:
                        raise QualificationFailure("native_submit_identity")
                    await write(
                        "codex.interrupt", CodexInterruptInput(turn=accepted.turn)
                    )
                    targets.append(target)
                    observations[key] = {
                        "list_read_start_submit_interrupt": "PASS",
                        "same_action_replay_without_reentry": "PASS",
                        "post_create_unknown_without_prompt": "PASS",
                        "exact_terminal_observed": "PASS",
                    }
                clean = await cleanup_terminals(host.tmux, terminals)
                terminals.clear()  # Cleanup never repeats a failed kill request.
            # Reconnect after every owned client/TUI exits; no replacement server.
            async with AgentRuntime(config) as reopened:
                for target in targets:
                    from provider_runtime.agent_runtime import (
                        CodexThreadTarget as NativeThreadTarget,
                    )

                    await reopened.codex.read(
                        NativeThreadTarget(target.profile, target.thread_handle)
                    )
                    observations[target.profile][
                        "native_history_survives_client_exit"
                    ] = "PASS"
    finally:
        if terminals:
            clean = await cleanup_terminals(host.tmux, terminals)
        await engine.dispose()
    if not clean:
        raise QualificationFailure("owned_terminal_cleanup_unconfirmed")
    return {
        "status": "NOT_RUN",
        "automated_journey": "PASS",
        "profiles": observations,
        "remaining": {name: "NOT_RUN" for name in _UNQUALIFIED},
        "codex_version": host.version,
        "cleanup": "owned_terminals_only",
        "native_history": "retained",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in (
        "provider-calls",
        "isolated-tmux-mutation",
        "disposable-database-writes",
    ):
        parser.add_argument(f"--allow-{flag}", action="store_true")
    parser.add_argument("--profile-config", type=Path)
    parser.add_argument("--tmux-binary", type=Path, default=Path("/usr/bin/tmux"))
    parser.add_argument("--socket-name")
    parser.add_argument("--cwd")
    args = parser.parse_args(argv)
    if not all(
        (
            args.allow_provider_calls,
            args.allow_isolated_tmux_mutation,
            args.allow_disposable_database_writes,
        )
    ):
        print(json.dumps({"status": "NOT_RUN", "reason": "explicit_opt_in_required"}))
        return 2
    try:
        if sys.platform != "linux" or not all(
            (args.profile_config, args.socket_name, args.cwd)
        ):
            raise ValueError("prepared Linux deployment is required")
        database_url = os.environ["JARVIS_CODEX_QUALIFICATION_DATABASE_URL"]
        from jarvis.codex_control import CodexHostConfig

        host = CodexHostConfig.load(args.profile_config)
        validate_preparation(
            runner=_private_file(Path(host.tmux)),
            tmux=args.tmux_binary,
            socket_name=args.socket_name,
            launcher_socket=Path(host.launcher_socket),
            database_url=database_url,
        )
        launcher = Path(host.launcher_socket)
        if (
            launcher.resolve(strict=True) != launcher
            or not launcher.is_socket()
            or not os.access(host.tmux, os.X_OK)
        ):
            raise ValueError("isolated helper is unavailable")
        if args.profile_config == Path("/etc/codex-shared/profiles.json"):
            raise ValueError("production mapping cannot qualify isolated tmux")
    except (ValueError, OSError, KeyError, ImportError):
        print(
            json.dumps({"status": "NOT_RUN", "reason": "isolated_preparation_required"})
        )
        return 2
    try:
        result = asyncio.run(_journey(host, args, database_url))
    except Exception:
        # No exception text, endpoint, database URL, account data, prompt, or
        # native answer enters ordinary evidence, even on an unexpected defect.
        print(json.dumps({"status": "FAIL", "reason": "journey_unconfirmed"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 2  # Full acceptance is NOT_RUN until the separately owned boundaries run.


if __name__ == "__main__":
    raise SystemExit(main())
