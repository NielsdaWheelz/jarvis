from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from urllib.parse import quote

import pytest
from llm_agent_kernel import (
    CancellationToken,
    Checkpoint,
    ClaimId,
    DispatchLineage,
    InputId,
    ToolDispatchDefect,
)
from llm_tools import (
    WEB_SEARCH_SPEC,
    Available,
    CapabilityProfile,
    HandlerSuccess,
    HostTable,
    InvocationPosition,
    PolicyEpoch,
    PositionState,
    ProfileId,
    ReplayPolicy,
    Reservation,
    RunLimits,
    Settlement,
    ToolBinding,
    ToolCatalog,
    ToolEffect,
    ToolGrant,
    ToolLimits,
    ToolPlan,
    WebSearchInput,
    WebSearchRequest,
    WebSearchResponse,
    bind_brave_web_search,
    web_family,
)
from llm_tools.testing import InMemoryBudgetState
from llm_tools.web.contracts import WebSearchSuccess
from provider_fixture import decision_key

from jarvis.read_dispatch import ReadToolDispatcher, RunReadRecorder
from jarvis.read_tools import GmailSearchInput


class _SlowSearch:
    async def search(
        self,
        request: WebSearchRequest,
        *,
        attempt_started: Callable[[], None] | None = None,
    ) -> WebSearchResponse:
        del request
        assert attempt_started is not None
        attempt_started()
        await asyncio.sleep(1)
        raise AssertionError("slow provider should be cancelled")


async def _must_not_execute(
    value: WebSearchInput, context: Any
) -> HandlerSuccess[WebSearchSuccess]:
    raise AssertionError((value, context))


def _plan() -> tuple[ToolBinding[Any, Any, Any], Any]:
    binding = ToolBinding(
        spec=WEB_SEARCH_SPEC,
        execute=Available(_must_not_execute),
        replay_policy=ReplayPolicy.BilledOnce,
        implementation_revision="llm-tools-web-search-v2",
        policy_epoch=PolicyEpoch("web-search-v2"),
        policy_inputs={
            "locale": "US/en",
            "max_results": 10,
            "operation_deadline_seconds": 12.0,
            "safe_search": "moderate",
        },
    )
    catalog = ToolCatalog.compose((web_family(search=binding),))
    limits = RunLimits(1, 2, 4_096, 32_768, 1, 30.0)
    profile = CapabilityProfile(
        ProfileId("dispatcher_test"),
        (ToolGrant(WEB_SEARCH_SPEC.id, None),),
        limits,
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    return binding, plan


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding_levels", (0, 1, 2))
async def test_web_secret_rejection_precedes_every_mutating_boundary(
    encoding_levels: int,
) -> None:
    secret = 'host"secret\\with'
    candidate = secret
    for _ in range(encoding_levels):
        candidate = quote(candidate, safe="")
    binding, plan = _plan()
    budgets = InMemoryBudgetState(plan.profile.run_limits)
    dispatcher = ReadToolDispatcher(recorder=RunReadRecorder(), host_secrets=(secret,))

    result = await dispatcher.dispatch(
        binding=binding,
        validated_input=WebSearchInput(
            query=f"lookup {candidate}",
            freshness_days=None,
        ),
        plan=plan,
        budgets=budgets,
        cancellation=CancellationToken(),
        lineage=DispatchLineage(
            ClaimId("claim"),
            Checkpoint("checkpoint"),
            (InputId("input"),),
            1,
            definition_fingerprint="a" * 64,
            model_decision_id=decision_key(str(ClaimId("claim")), 1),
        ),
    )

    assert result.result == {"type": "Failure", "error": {"type": "InvalidInput"}}
    assert dispatcher.recorder.position_count == 0
    assert budgets.actual_calls == 0
    assert budgets.actual_external_attempts == 0
    assert budgets.actual_input_bytes == 0
    assert budgets.actual_output_bytes == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate",
    (
        "access%5Ftoken%3Dabcdefghijklmnop",
        "api key=abcdefghijklmnop",
        "access token: abcdefghijklmnop",
        "refresh token=abcdefghijklmnop",
    ),
)
async def test_web_credential_label_is_rejected_before_mutation(
    candidate: str,
) -> None:
    binding, plan = _plan()
    budgets = InMemoryBudgetState(plan.profile.run_limits)
    dispatcher = ReadToolDispatcher(recorder=RunReadRecorder(), host_secrets=())

    result = await dispatcher.dispatch(
        binding=binding,
        validated_input=WebSearchInput(
            query=f"lookup {candidate}",
            freshness_days=None,
        ),
        plan=plan,
        budgets=budgets,
        cancellation=CancellationToken(),
        lineage=DispatchLineage(
            ClaimId("claim"),
            Checkpoint("checkpoint"),
            (InputId("input"),),
            1,
            definition_fingerprint="a" * 64,
            model_decision_id=decision_key(str(ClaimId("claim")), 1),
        ),
    )
    assert result.result == {"type": "Failure", "error": {"type": "InvalidInput"}}
    assert dispatcher.recorder.position_count == 0
    assert budgets.actual_calls == 0


@pytest.mark.asyncio
async def test_recorder_preserves_uncertain_billed_once_state() -> None:
    recorder = RunReadRecorder()
    position = InvocationPosition("position")
    occupied = await recorder.occupy(
        position=position,
        tool_id=WEB_SEARCH_SPEC.id,
        tool_contract_revision=WEB_SEARCH_SPEC.tool_contract_revision,
        policy_revision="policy",
        plan_revision="plan",
        input_digest="digest",
        replay_policy=ReplayPolicy.BilledOnce,
    )
    assert occupied == PositionState(None, False, 0)
    budgets = InMemoryBudgetState(RunLimits(1, 1, 100, 100, 1, 30.0))
    assert await recorder.reserve(
        position=position,
        budgets=budgets,
        reservation=Reservation(1, 1, 1, 10),
    )
    started = await recorder.dispatch_started(
        position=position,
        replay_policy=ReplayPolicy.BilledOnce,
    )
    assert not started.uncertain
    await recorder.uncertain(position=position)

    replay = await recorder.occupy(
        position=position,
        tool_id=WEB_SEARCH_SPEC.id,
        tool_contract_revision=WEB_SEARCH_SPEC.tool_contract_revision,
        policy_revision="policy",
        plan_revision="plan",
        input_digest="digest",
        replay_policy=ReplayPolicy.BilledOnce,
    )
    assert replay.uncertain
    with pytest.raises(ValueError, match="uncertain"):
        await recorder.terminalize_and_settle(
            position=position,
            budgets=budgets,
            result={"type": "Failure", "error": {"type": "DeadlineExceeded"}},
            settlement=Settlement(1, 1),
        )


@pytest.mark.asyncio
async def test_recorder_terminal_replay_is_idempotent() -> None:
    recorder = RunReadRecorder()
    budgets = InMemoryBudgetState(RunLimits(1, 1, 100, 100, 1, 30.0))
    position = InvocationPosition("position")
    await recorder.occupy(
        position=position,
        tool_id=WEB_SEARCH_SPEC.id,
        tool_contract_revision=WEB_SEARCH_SPEC.tool_contract_revision,
        policy_revision="policy",
        plan_revision="plan",
        input_digest="digest",
        replay_policy=ReplayPolicy.BilledOnce,
    )
    await recorder.reserve(
        position=position,
        budgets=budgets,
        reservation=Reservation(1, 1, 1, 10),
    )
    await recorder.dispatch_started(
        position=position,
        replay_policy=ReplayPolicy.BilledOnce,
    )
    result = {"type": "Failure", "error": {"type": "InvalidInput"}}
    assert (
        await recorder.terminalize_and_settle(
            position=position,
            budgets=budgets,
            result=result,
            settlement=Settlement(0, 1),
        )
        == result
    )
    replay = await recorder.occupy(
        position=position,
        tool_id=WEB_SEARCH_SPEC.id,
        tool_contract_revision=WEB_SEARCH_SPEC.tool_contract_revision,
        policy_revision="policy",
        plan_revision="plan",
        input_digest="digest",
        replay_policy=ReplayPolicy.BilledOnce,
    )
    assert replay.terminal_result == result


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ("implementation", "replay", "schema", "effect"))
async def test_frozen_plan_rejects_binding_substitution_before_mutation(
    mutation: str,
) -> None:
    binding, plan = _plan()
    if mutation == "implementation":
        changed = replace(binding, implementation_revision="substituted")
    elif mutation == "replay":
        changed = replace(binding, replay_policy=ReplayPolicy.ReDispatchable)
    elif mutation == "schema":
        changed_spec = replace(
            binding.spec,
            input_type=GmailSearchInput,  # type: ignore[arg-type]
        )
        changed = replace(binding, spec=changed_spec)  # type: ignore[arg-type]
    else:
        changed_spec = replace(binding.spec, effect=ToolEffect.Write)
        changed = replace(binding, spec=changed_spec)
    budgets = InMemoryBudgetState(plan.profile.run_limits)
    dispatcher = ReadToolDispatcher(recorder=RunReadRecorder(), host_secrets=())
    with pytest.raises(ToolDispatchDefect):
        await dispatcher.dispatch(
            binding=changed,
            validated_input=WebSearchInput(query="synthetic", freshness_days=None),
            plan=plan,
            budgets=budgets,
            cancellation=CancellationToken(),
            lineage=DispatchLineage(
                ClaimId("claim"),
                Checkpoint("checkpoint"),
                (InputId("input"),),
                1,
                definition_fingerprint="a" * 64,
                model_decision_id=decision_key(str(ClaimId("claim")), 1),
            ),
        )
    assert dispatcher.recorder.position_count == 0
    assert budgets.actual_calls == 0
    assert budgets.actual_external_attempts == 0


@pytest.mark.asyncio
async def test_pinned_web_search_inner_deadline_completes_without_uncertainty() -> None:
    binding = bind_brave_web_search(
        _SlowSearch(),  # type: ignore[arg-type]
        operation_deadline_seconds=0.01,
    )
    catalog = ToolCatalog.compose((web_family(search=binding),))
    profile = CapabilityProfile(
        ProfileId("deadline_test"),
        (
            ToolGrant(
                WEB_SEARCH_SPEC.id,
                ToolLimits(4_096, 32_768, 1, 15.0),
            ),
        ),
        RunLimits(1, 1, 4_096, 32_768, 1, 15.0),
    ).freeze(catalog)
    plan = ToolPlan(profile.id, HostTable()).freeze(catalog, profile)
    budgets = InMemoryBudgetState(plan.profile.run_limits)
    dispatcher = ReadToolDispatcher(recorder=RunReadRecorder(), host_secrets=())

    completed = await dispatcher.dispatch(
        binding=binding,
        validated_input=WebSearchInput(query="synthetic timeout", freshness_days=None),
        plan=plan,
        budgets=budgets,
        cancellation=CancellationToken(),
        lineage=DispatchLineage(
            ClaimId("deadline-claim"),
            Checkpoint("deadline-checkpoint"),
            (InputId("deadline-input"),),
            1,
            definition_fingerprint="a" * 64,
            model_decision_id=decision_key(str(ClaimId("deadline-claim")), 1),
        ),
    )

    assert completed.result == {
        "type": "Failure",
        "error": {"type": "UpstreamUnavailable"},
    }
    assert dispatcher.recorder.position_count == 1
    assert dispatcher.recorder.terminal_count == 1
    assert dispatcher.recorder.uncertain_count == 0
    assert budgets.actual_calls == 1
    assert budgets.actual_external_attempts == 1
