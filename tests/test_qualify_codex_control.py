"""Qualification safety and real stored uncertainty; no provider or tmux."""

import asyncio
import json
import os
import sys
import tempfile
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from types import FrameType

    from _typeshed import TraceFunction

QUALIFIER = run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/qualify_codex_control.py")
)
SOCKET = "jarvis-codex-qualify-" + "a" * 32
NAME = "jarvis-qualify-" + "a" * 32 + "-personal"


def test_failure_evidence_keeps_fixed_stage_and_never_exception_content() -> None:
    assert QUALIFIER["_failure_evidence"](
        QUALIFIER["QualificationFailure"]("native_read")
    ) == {"status": "FAIL", "reason": "native_read"}
    try:
        raise RuntimeError("private-synthetic-sentinel")
    except RuntimeError as error:
        result = QUALIFIER["_failure_evidence"](error)
    assert result["reason"] == "journey_unconfirmed"
    assert result["exception_type"] == "RuntimeError"
    assert result["source"] == Path(__file__).name
    assert type(result["line"]) is int
    assert "private-synthetic-sentinel" not in json.dumps(result)


def test_isolated_runner_refuses_default_or_reused_nonspecific_socket_names() -> None:
    for name in ("", "default", "production", "jarvis-codex-qualify", "../socket"):
        with pytest.raises(ValueError, match="isolated"):
            QUALIFIER["isolated_runner_source"](Path("/usr/bin/tmux"), name)


def test_opt_in_requires_all_three_boundaries_before_preparation_or_imports(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "provider_runtime", None)
    for args in (
        [],
        ["--allow-provider-calls"],
        ["--allow-provider-calls", "--allow-isolated-tmux-mutation"],
    ):
        assert QUALIFIER["main"](args) == 2
        assert json.loads(capsys.readouterr().out) == {
            "status": "NOT_RUN",
            "reason": "explicit_opt_in_required",
        }


def test_preparation_rejects_wrong_runner_or_non_disposable_database() -> None:
    tmux = Path("/usr/bin/tmux")
    runner = QUALIFIER["isolated_runner_source"](tmux, SOCKET)
    database = "postgresql+psycopg://user:synthetic@127.0.0.1/jarvis_codex_qualify_test"
    QUALIFIER["validate_preparation"](
        runner=runner,
        tmux=tmux,
        socket_name=SOCKET,
        launcher_socket=Path("/run") / SOCKET / "launcher.sock",
        database_url=database,
    )
    for changed_runner, changed_database in (
        (b'#!/bin/sh\nexec /usr/bin/tmux "$@"\n', database),
        (runner, database.replace("jarvis_codex_qualify_test", "jarvis")),
        (runner, database.replace("127.0.0.1", "production.invalid")),
    ):
        with pytest.raises(ValueError):
            QUALIFIER["validate_preparation"](
                runner=changed_runner,
                tmux=tmux,
                socket_name=SOCKET,
                launcher_socket=Path("/run") / SOCKET / "launcher.sock",
                database_url=changed_database,
            )
    with pytest.raises(ValueError, match="launcher socket"):
        QUALIFIER["validate_preparation"](
            runner=runner,
            tmux=tmux,
            socket_name=SOCKET,
            launcher_socket=Path("/run/codex-shared/launcher.sock"),
            database_url=database,
        )


def test_gateway_configuration_rejects_nonfixture_routes_and_bad_identity() -> None:
    valid = {
        "url": "http://127.0.0.1:17341",
        "machine_handle": "mh-" + "b" * 32,
        "bearer": "A" * 43,
    }
    QUALIFIER["Gateway"](json.dumps(valid).encode())
    for change in (
        {"url": "http://127.0.0.1:7341"},
        {"url": "https://production.invalid:17341"},
        {"url": "http://localhost:17341"},
        {"url": "http://127.0.0.1:17341/path"},
        {"url": "http://user@127.0.0.1:17341"},
        {"machine_handle": "default"},
        {"bearer": "not a bearer"},
        {"unexpected": True},
    ):
        with pytest.raises(ValueError):
            QUALIFIER["Gateway"](json.dumps(valid | change).encode())


async def test_invalid_terminal_identity_fails_before_external_execution() -> None:
    with pytest.raises(ValueError, match="exact test identity"):
        await QUALIFIER["observe_terminal"]("/absent", "last", NAME)


@pytest.mark.parametrize(
    ("input_method", "disconnect"),
    [
        (None, None),
        ("turn/start", None),
        ("turn/steer", None),
        (None, 1000),
        (None, 1011),
    ],
)
async def test_native_wire_witness_requires_creation_and_no_input(
    input_method: str | None,
    disconnect: int | None,
) -> None:
    from provider_runtime.agent_runtime.codex_app_server import (
        CodexAppServerClient,
        CodexAppServerConfig,
    )
    from websockets.asyncio.server import ServerConnection, unix_serve

    thread = str(uuid4())
    received: list[str] = []
    drop = asyncio.Event()
    dropped = asyncio.Event()

    async def native(connection: ServerConnection) -> None:
        async for frame in connection:
            request = json.loads(frame)
            method = request["method"]
            if method == "initialized":
                continue
            received.append(method)
            result = (
                {"userAgent": "synthetic native build"}
                if method == "initialize"
                else {"thread": {"id": thread}}
            )
            await connection.send(json.dumps({"id": request["id"], "result": result}))
            if method == "thread/start" and disconnect:
                await drop.wait()
                await connection.close(code=disconnect)
                dropped.set()
                return

    expected = (
        pytest.raises(QUALIFIER["QualificationFailure"], match="native_wire_forwarding")
        if disconnect
        else nullcontext()
    )
    with (
        expected,
        tempfile.TemporaryDirectory(prefix="codex-wire-proof-", dir="/tmp") as raw,
    ):
        root = Path(raw)
        endpoint = root / "native.sock"
        async with (
            await unix_serve(native, str(endpoint)),
            QUALIFIER["_observed_codex"]({"personal": endpoint}, root) as wire,
        ):
            with pytest.raises(QUALIFIER["QualificationFailure"]):
                await wire.verify_unprompted("personal", thread)
            async with CodexAppServerClient(
                CodexAppServerConfig(wire.endpoints["personal"])
            ) as client:
                await client.thread_start(cwd="/synthetic")
                if input_method is not None:
                    await client.request(
                        input_method, {"threadId": thread, "input": []}
                    )
                if disconnect:
                    drop.set()
                    await dropped.wait()
            assert ("personal", thread) in wire.created
            assert wire.inputs.get(("personal", thread), 0) == (
                0 if input_method is None else 1
            )
            if disconnect:
                await wire.verify_unprompted("personal", thread)
            with pytest.raises(QUALIFIER["QualificationFailure"]):
                await wire.verify_unprompted("work", thread)
            if input_method is None:
                await wire.verify_unprompted("personal", thread)
            else:
                with pytest.raises(QUALIFIER["QualificationFailure"]):
                    await wire.verify_unprompted("personal", thread)
    assert received == ["initialize", "thread/start"] + (
        [] if input_method is None else [input_method]
    )


async def test_native_wire_close_without_peer_close_reply_preserves_witness() -> None:
    from provider_runtime.agent_runtime.codex_app_server import (
        CodexAppServerClient,
        CodexAppServerConfig,
    )
    from websockets.frames import OP_CLOSE, OP_TEXT, Close, Frame
    from websockets.http11 import Request
    from websockets.server import ServerProtocol

    thread = str(uuid4())
    close_codes: list[int] = []

    async def native(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        protocol = ServerProtocol(max_size=4096)
        try:
            while data := await reader.read(4096):
                protocol.receive_data(data)
                for event in protocol.events_received():
                    if isinstance(event, Request):
                        protocol.send_response(protocol.accept(event))
                    elif isinstance(event, Frame):
                        if event.opcode == OP_CLOSE:
                            close_codes.append(Close.parse(event.data).code)
                            # Match the observed native teardown: close TCP without
                            # sending the protocol's queued WebSocket close reply.
                            return
                        assert event.opcode == OP_TEXT
                        request = json.loads(bytes(event.data))
                        if request["method"] == "initialized":
                            continue
                        result = (
                            {"userAgent": "synthetic native build"}
                            if request["method"] == "initialize"
                            else {"thread": {"id": thread}}
                        )
                        protocol.send_text(
                            json.dumps({"id": request["id"], "result": result}).encode()
                        )
                for output in protocol.data_to_send():
                    writer.write(output)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    with tempfile.TemporaryDirectory(prefix="codex-close-proof-", dir="/tmp") as raw:
        root = Path(raw)
        endpoint = root / "native.sock"
        async with (
            await asyncio.start_unix_server(native, str(endpoint)),
            QUALIFIER["_observed_codex"]({"personal": endpoint}, root) as wire,
        ):
            async with CodexAppServerClient(
                CodexAppServerConfig(wire.endpoints["personal"])
            ) as client:
                await client.thread_start(cwd="/synthetic")
            await wire.verify_unprompted("personal", thread)
            assert not wire.failed
            assert all(task.done() for task in wire.handlers)
    assert close_codes == [1000]


@pytest.mark.parametrize("queued_input", (False, True))
async def test_native_notification_after_clean_client_close_drains_requests(
    queued_input: bool,
) -> None:
    from websockets.asyncio.client import unix_connect
    from websockets.asyncio.connection import Connection
    from websockets.asyncio.server import ServerConnection, unix_serve
    from websockets.exceptions import ConnectionClosedOK

    thread = str(uuid4())
    paused: asyncio.Future[ServerConnection] = (
        asyncio.get_running_loop().create_future()
    )
    release = asyncio.Event()
    received: list[str] = []
    observed = asyncio.Event()

    def trace(
        frame: "FrameType", event: str, argument: object
    ) -> "TraceFunction | None":
        if frame.f_code is not Connection.send.__code__ or observed.is_set():
            return None
        connection = frame.f_locals.get("self")
        if (
            event == "exception"
            and isinstance(connection, Connection)
            and connection.local_address == str(wire.endpoints["personal"])
            and isinstance(
                cast("tuple[object, BaseException, object]", argument)[1],
                ConnectionClosedOK,
            )
        ):
            observed.set()
        return trace

    async def native(connection: ServerConnection) -> None:
        request = json.loads(await connection.recv())
        assert request["method"] == "thread/start"
        await connection.send(
            json.dumps({"id": request["id"], "result": {"thread": {"id": thread}}})
        )
        # External peer backpressure holds one upstream send while the independent
        # downstream WebSocket completes its normal close handshake.
        connection.transport.pause_reading()
        paused.set_result(connection)
        await release.wait()
        connection.transport.resume_reading()
        async for frame in connection:
            received.append(json.loads(frame)["method"])

    with tempfile.TemporaryDirectory(prefix="codex-reply-close-", dir="/tmp") as raw:
        root = Path(raw)
        endpoint = root / "native.sock"
        async with (
            asyncio.timeout(15),
            await unix_serve(
                native, str(endpoint), max_size=4 * 1024 * 1024, compression=None
            ),
            QUALIFIER["_observed_codex"]({"personal": endpoint}, root) as wire,
        ):
            async with unix_connect(
                str(wire.endpoints["personal"]), compression=None
            ) as client:
                await client.send(
                    json.dumps({"id": 1, "method": "thread/start", "params": {}})
                )
                await client.recv()
                peer = await paused
                await client.send(
                    json.dumps(
                        {
                            "id": 2,
                            "method": "fixture/backpressure",
                            "params": {"padding": "x" * (2 * 1024 * 1024)},
                        }
                    )
                )
                if queued_input:
                    await client.send(
                        json.dumps(
                            {
                                "id": 3,
                                "method": "turn/steer",
                                "params": {"threadId": thread, "input": []},
                            }
                        )
                    )
                await client.close()
            previous_trace = sys.gettrace()
            sys.settrace(trace)
            try:
                await peer.send(
                    json.dumps(
                        {
                            "method": "thread/status/changed",
                            "params": {"threadId": thread, "status": {"type": "idle"}},
                        }
                    )
                )
                await observed.wait()
            finally:
                sys.settrace(previous_trace)
                release.set()
            assert observed.is_set()
            await wire.settled()
            assert wire.inputs.get(("personal", thread), 0) == int(queued_input)
            if queued_input:
                with pytest.raises(
                    QUALIFIER["QualificationFailure"],
                    match="collision_native_input_witness",
                ):
                    await wire.verify_unprompted("personal", thread)
            else:
                await wire.verify_unprompted("personal", thread)
    assert received == ["fixture/backpressure"] + (
        ["turn/steer"] if queued_input else []
    )


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("JARVIS_TEST_DATABASE_URL"),
    reason="requires the disposable PostgreSQL action boundary",
)
async def test_uncertain_write_projects_real_stored_evidence_without_reentry() -> None:
    from llm_agent_kernel import CancellationToken, InitialReadDispatchLineage, RunId
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
    from websockets.asyncio.server import ServerConnection, unix_serve

    from jarvis.actions import ActionStore
    from jarvis.admission import ExactToolBudgetFactory
    from jarvis.codex_control import CodexController, CodexHostConfig
    from jarvis.codex_tools import (
        CodexListInput,
        CodexPromptInput,
        CodexSubmit,
        CodexThreadTarget,
        codex_family,
    )
    from jarvis.db import create_engine
    from jarvis.messages import MessageStore
    from jarvis.ownership import deployment_ownership
    from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder

    submissions = 0
    native_reads = 0

    async def native(connection: ServerConnection) -> None:
        nonlocal submissions, native_reads
        async for frame in connection:
            request = json.loads(frame)
            method = request["method"]
            if method == "initialized":
                continue
            if method == "initialize":
                result: dict[str, object] = {"userAgent": "codex/0.153.4"}
            elif method == "account/read":
                result = {"account": {"type": "chatgpt"}}
            elif method == "thread/list":
                native_reads += 1
                result = {"data": [], "nextCursor": None}
            else:
                assert method == "turn/start"
                submissions += 1
                await connection.close()
                return
            await connection.send(json.dumps({"id": request["id"], "result": result}))

    origin = uuid4()
    channel = f"qualifier-uncertainty-{origin}"
    target = CodexThreadTarget(profile="work", thread_handle=str(uuid4()))
    engine = create_engine(os.environ["JARVIS_TEST_DATABASE_URL"])
    try:
        with tempfile.TemporaryDirectory(prefix="qualifier-", dir="/tmp") as temporary:
            root = Path(temporary)
            host = CodexHostConfig.model_validate(
                {
                    "schema_version": 2,
                    "development_user": "synthetic",
                    "jarvis_user": "jarvis",
                    "client_group": "codex-clients",
                    "binary": "/synthetic/codex",
                    "tmux": "/synthetic/tmux",
                    "cognition_cwd_parent": str(root / "cognition"),
                    "launcher_socket": str(root / "unused-helper.sock"),
                    "profiles": {
                        profile: {
                            "account_home": f"/synthetic/{profile}",
                            "endpoint": f"unix://{root}/{profile}.sock",
                            "work_roots": [str(root)],
                        }
                        for profile in ("personal", "work", "work2")
                    },
                }
            )
            async with (
                await unix_serve(native, str(root / "work.sock")),
                deployment_ownership(engine) as database,
                AgentRuntime(
                    AgentRuntimeConfig(
                        state_root_base=root, codex_endpoints=host.endpoints
                    )
                ) as runtime,
            ):
                actions = ActionStore(database)
                controller = CodexController(
                    control=runtime.codex, host=host, actions=actions
                )
                catalog = ToolCatalog.compose((codex_family(controller),))
                profile = CapabilityProfile(
                    ProfileId("qualifier-proof"),
                    tuple(
                        ToolGrant(ToolId(tool), None)
                        for tool in ("codex.list", "codex.prompt")
                    ),
                    RunLimits(2, 2, 1048576, 2097152, 1, 60.0),
                ).freeze(catalog)
                plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
                await MessageStore(database).insert_waking(
                    role="owner",
                    text="Synthetic worker request.",
                    source="discord",
                    source_conversation_id=channel,
                    source_message_id=str(origin),
                    created_at=datetime.now(UTC),
                    message_id=origin,
                )
                budgets = ExactToolBudgetFactory().create(plan)
                result = await QUALIFIER["_write"](
                    actions=actions,
                    plan=plan,
                    budgets=budgets,
                    origin=origin,
                    ordinal=1,
                    tool=ToolId("codex.prompt"),
                    value=CodexPromptInput(
                        thread=target, input=CodexSubmit(text="Synthetic.")
                    ),
                    expect_uncertain=True,
                )
                assert result == {
                    "type": "Unknown",
                    "stage": "submit",
                    "prefix": {"type": "thread", "thread": target.model_dump()},
                }
                (stored,) = await actions.unreported_terminal(
                    source_conversation_id=channel
                )
                assert stored.status == "uncertain" and stored.attempts == 1
                assert stored.result is not None
                assert stored.result["type"] == "codex_uncertainty_v1"
                assert submissions == 1
                # Uncertainty ends this run. Its reservation is not refunded;
                # an attempted continuation must fail before any native read.
                blocked = await ReadToolDispatcher(
                    recorder=RunReadRecorder(), host_secrets=()
                ).dispatch(
                    binding=catalog.binding(ToolId("codex.list")),
                    validated_input=CodexListInput(profile="work"),
                    plan=plan,
                    budgets=budgets,
                    cancellation=CancellationToken(),
                    lineage=InitialReadDispatchLineage(
                        RunId(str(origin)), "after-uncertainty"
                    ),
                )
                assert blocked.result == {
                    "type": "Failure",
                    "error": {"type": "BudgetExceeded"},
                }
                assert native_reads == 0

                # A separate owner input gets its own run, not a replenished
                # budget or another attempt at the uncertain write.
                next_origin = uuid4()
                await MessageStore(database).insert_waking(
                    role="owner",
                    text="Synthetic independent inventory request.",
                    source="discord",
                    source_conversation_id=channel,
                    source_message_id=str(next_origin),
                    created_at=datetime.now(UTC),
                    message_id=next_origin,
                )
                independent = await ReadToolDispatcher(
                    recorder=RunReadRecorder(), host_secrets=()
                ).dispatch(
                    binding=catalog.binding(ToolId("codex.list")),
                    validated_input=CodexListInput(profile="work"),
                    plan=plan,
                    budgets=ExactToolBudgetFactory().create(plan),
                    cancellation=CancellationToken(),
                    lineage=InitialReadDispatchLineage(
                        RunId(str(next_origin)), "independent-read"
                    ),
                )
                assert independent.result["type"] == "Success"
                assert native_reads == 1 and submissions == 1
                assert await actions.get(stored.id) == stored
    finally:
        await engine.dispose()
