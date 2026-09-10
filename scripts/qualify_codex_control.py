#!/usr/bin/env python3
"""Explicitly opt-in shared-Codex qualification; never use default tmux."""

from __future__ import annotations

import argparse
import asyncio
import base64
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
    "phone_attachment",
    "contained_cognition_coexistence",
    "lost_submit_and_original_input_restart",
)
_PROMPT = (
    "This is a synthetic control qualification. Do not use tools, read files, "
    "write files, or access the network. Reply with one short acknowledgement."
)


class QualificationFailure(RuntimeError):
    """Only a host-owned stage label may enter evidence."""


def _private_file(path: Path, *, confidential: bool = False) -> bytes:
    with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
            or (confidential and metadata.st_mode & 0o007)
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


class Gateway:
    """Fixture-only Skid boundary; no direct cross-UID tmux authority."""

    def __init__(self, encoded: bytes) -> None:
        decoded: object = json.loads(encoded)
        if not isinstance(decoded, dict):
            raise ValueError("invalid fixture gateway configuration")
        fields = cast("dict[str, object]", decoded)
        if set(fields) != {"url", "machine_handle", "bearer"} or any(
            not isinstance(value, str) for value in fields.values()
        ):
            raise ValueError("invalid fixture gateway configuration")
        config = cast("dict[str, str]", fields)
        url = urlsplit(config["url"])
        if (
            url.scheme != "http"
            or url.hostname not in ("127.0.0.1", "::1")
            or url.port is None
            or not 1024 <= url.port <= 65535
            or url.port == 7341
            or url.path
            or url.query
            or url.fragment
            or url.username is not None
            or url.password is not None
            or not re.fullmatch(r"mh-[0-9a-f]{32}", config["machine_handle"])
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", config["bearer"])
        ):
            raise ValueError("invalid fixture gateway endpoint or identity")
        bearer = config["bearer"]
        if (
            base64.urlsafe_b64encode(base64.urlsafe_b64decode(bearer + "="))
            .decode()
            .rstrip("=")
            != bearer
        ):
            raise ValueError("noncanonical fixture bearer")
        self.url = config["url"]
        self.machine = config["machine_handle"]
        self.headers = {
            "Authorization": "Bearer " + bearer,
            "Skidbladnir-Machine": self.machine,
        }

    async def request(
        self,
        method: str,
        path: str,
        expected_status: int,
        body: dict[str, str] | None = None,
    ) -> bytes:
        import httpx

        async with (
            asyncio.timeout(5),
            httpx.AsyncClient(timeout=5, trust_env=False) as client,
        ):
            async with client.stream(
                method, self.url + path, headers=self.headers, json=body
            ) as response:
                if response.status_code != expected_status:
                    raise QualificationFailure("gateway_request")
                output = bytearray()
                async for chunk in response.aiter_bytes():
                    output.extend(chunk)
                    if len(output) > 65_536:
                        raise QualificationFailure("gateway_observation_bound")
                return bytes(output)

    async def sessions(self) -> list[dict[str, object]]:
        decoded: object = json.loads(await self.request("GET", "/v1/sessions", 200))
        if not isinstance(decoded, dict):
            raise QualificationFailure("gateway_inventory")
        value = cast("dict[str, object]", decoded)
        if value.get("machine") != {
            "handle": self.machine,
            "platform": "Linux",
        } or not isinstance(value.get("sessions"), list):
            raise QualificationFailure("gateway_inventory")
        rows: list[dict[str, object]] = []
        for item in cast("list[object]", value["sessions"]):
            if not isinstance(item, dict):
                raise QualificationFailure("gateway_session_identity")
            row = cast("dict[str, object]", item)
            if any(
                not isinstance(row.get(key), str) or not row[key]
                for key in ("tmuxId", "tmuxName", "identityToken")
            ):
                raise QualificationFailure("gateway_session_identity")
            rows.append(row)
        if len({row["tmuxId"] for row in rows}) != len(rows):
            raise QualificationFailure("gateway_session_identity")
        return rows


async def observe_terminal(gateway: Gateway, session_id: str, name: str) -> str | None:
    if not re.fullmatch(r"\$[0-9]+", session_id) or not re.fullmatch(
        r"jarvis-qualify-[0-9a-f]{32}-(?:personal|work|work2)", name
    ):
        raise ValueError("terminal observation requires an exact test identity")
    for row in await gateway.sessions():
        if row["tmuxId"] == session_id and row["tmuxName"] == name:
            return cast("str", row["identityToken"])
    return None


async def cleanup_terminals(
    gateway: Gateway, terminals: Sequence[tuple[CodexTerminal, str | None]]
) -> bool:
    complete = True
    for terminal, token in terminals:
        try:
            if token is None or token != await observe_terminal(
                gateway, terminal.tmux_session_id, terminal.tmux_name
            ):
                complete = False
                continue
            await gateway.request(
                "DELETE",
                f"/v1/sessions/{terminal.tmux_session_id}",
                204,
                {"tmuxName": terminal.tmux_name, "identityToken": token},
            )
        except Exception:
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

    from jarvis.actions import (
        ActionPositionRecorder,
        ExecutionContract,
        codex_uncertainty_result,
    )
    from jarvis.codex_tools import CodexActionEvidence, CodexUnknown

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
        evidence = CodexActionEvidence.model_validate(
            codex_uncertainty_result(terminal)["control"]
        )
        return CodexUnknown(stage=evidence.stage, prefix=evidence.prefix).model_dump(
            mode="json"
        )
    output = result.get("value")
    if result.get("type") != "Success" or not isinstance(output, dict):
        raise QualificationFailure("write_result")
    return cast("dict[str, object]", output)


async def _journey(
    host: CodexHostConfig, args: argparse.Namespace, database_url: str, gateway: Gateway
) -> dict[str, object]:
    from llm_agent_kernel import (
        CancellationToken,
        InitialReadDispatchLineage,
        RunId,
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
    from jarvis.ownership import deployment_ownership
    from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder

    if await gateway.sessions():
        raise QualificationFailure("isolated_socket_not_empty")
    engine = create_engine(database_url)
    terminals: list[tuple[CodexTerminal, str | None]] = []
    observations: dict[str, dict[str, str]] = {}
    clean = False
    try:
        with tempfile.TemporaryDirectory(prefix="jarvis-control-qualify-") as state:
            config = AgentRuntimeConfig(
                state_root_base=Path(state), codex_endpoints=host.endpoints
            )
            async with (
                deployment_ownership(engine) as database,
                AgentRuntime(config) as runtime,
            ):
                actions = ActionStore(database)
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
                dispatcher = ReadToolDispatcher(
                    recorder=RunReadRecorder(), host_secrets=(database_url,)
                )
                origin = uuid4()
                await MessageStore(database).insert_waking(
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
                        lineage=InitialReadDispatchLineage(
                            RunId(str(origin)),
                            f"codex-control-qualification:{origin}:{ordinal}",
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
                    terminals.append((started.terminal, None))
                    token = await observe_terminal(
                        gateway,
                        started.terminal.tmux_session_id,
                        started.terminal.tmux_name,
                    )
                    terminals[-1] = (started.terminal, token)
                    if started.turn.thread.profile != key or token is None:
                        raise QualificationFailure("terminal_identity")
                    # The real Skid boundary must reject another opaque token
                    # without mutating this exact newly-created terminal.
                    mismatched = token[:-1] + ("0" if token[-1] != "0" else "1")
                    rejected = json.loads(
                        await gateway.request(
                            "DELETE",
                            f"/v1/sessions/{started.terminal.tmux_session_id}",
                            409,
                            {
                                "tmuxName": started.terminal.tmux_name,
                                "identityToken": mismatched,
                            },
                        )
                    )
                    if rejected != {
                        "code": "SessionIdentityMismatch",
                        "message": "The session changed. Refresh and try again.",
                    } or token != await observe_terminal(
                        gateway,
                        started.terminal.tmux_session_id,
                        started.terminal.tmux_name,
                    ):
                        raise QualificationFailure("gateway_mismatched_identity")
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
                        "skid_inventory": "PASS",
                        "skid_mismatched_identity_refused": "PASS",
                    }
                clean = await cleanup_terminals(gateway, terminals)
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
            clean = await cleanup_terminals(gateway, terminals)
        await engine.dispose()
    if not clean:
        raise QualificationFailure("owned_terminal_cleanup_unconfirmed")
    return {
        "status": "NOT_RUN",
        "automated_journey": "PASS",
        "profiles": observations,
        "remaining": {name: "NOT_RUN" for name in _UNQUALIFIED},
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
    parser.add_argument("--gateway-config", type=Path)
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
            (args.profile_config, args.socket_name, args.cwd, args.gateway_config)
        ):
            raise ValueError("prepared Linux deployment is required")
        database_url = os.environ["JARVIS_CODEX_QUALIFICATION_DATABASE_URL"]
        from jarvis.codex_control import CodexHostConfig

        host = CodexHostConfig.load(args.profile_config)
        if args.gateway_config.parent.name != args.socket_name:
            raise ValueError("gateway configuration must identify isolated preparation")
        gateway = Gateway(_private_file(args.gateway_config, confidential=True))
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
        result = asyncio.run(_journey(host, args, database_url, gateway))
    except Exception:
        # No exception text, endpoint, database URL, account data, prompt, or
        # native answer enters ordinary evidence, even on an unexpected defect.
        print(json.dumps({"status": "FAIL", "reason": "journey_unconfirmed"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 2  # Full acceptance is NOT_RUN until the separately owned boundaries run.


if __name__ == "__main__":
    raise SystemExit(main())
