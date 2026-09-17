from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from runpy import run_path
from typing import Any, cast

import pytest
from llm_agent_kernel import (
    ProviderUsage,
    RunId,
    RunMetrics,
    SessionMode,
    StructuredOutput,
    provider_wire_schema,
)
from llm_tools import ToolId, canonical_json_bytes
from provider_fixture import frozen_provider

from jarvis.definitions import (
    WRITE_GATE_KERNEL_LIMITS,
    AutomaticWriteGateResult,
    build_write_gate,
)
from jarvis.write_gate import WriteGateDecision

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_QUALIFIER = run_path(str(ROOT / "scripts" / "qualify_write_gate.py"))
TRIALS = _QUALIFIER["TRIALS"]
output_schema_digest = cast(
    "Callable[[object], str]", _QUALIFIER["output_schema_digest"]
)
qualification_admission_limits = _QUALIFIER["qualification_admission_limits"]
trial_evidence = _QUALIFIER["_trial_evidence"]
validate_trial_decision = _QUALIFIER["validate_trial_decision"]


def _decision(trial: Any) -> WriteGateDecision:
    expected = trial.expected_decision
    support = (trial.owner_message_id,) if expected == "allow" else ()
    return WriteGateDecision(
        expected,
        support,
        RunId(f"run-{trial.id}"),
        "completed",
        RunMetrics(RunId(f"run-{trial.id}"), 1, ProviderUsage(100, 20), 0.5, False),
    )


def test_trials_cover_exact_five_of_five_safety_and_direct_usability() -> None:
    observed = [
        (trial.id, trial.kind, trial.source, str(trial.tool_id)) for trial in TRIALS
    ]
    assert observed == [
        ("G01", "safety", "memory", "gmail.create_draft"),
        ("G02", "safety", "gmail", "schedule.wake"),
        ("G03", "safety", "calendar", "gmail.update_draft"),
        ("G04", "safety", "web", "calendar.create_event"),
        ("G05", "safety", "gmail", "calendar.delete_event"),
        ("G06", "usability", "owner", "gmail.create_draft"),
        ("G07", "usability", "owner", "calendar.create_event"),
        ("G08", "usability", "owner", "schedule.wake"),
    ]
    assert len({trial.owner_message_id for trial in TRIALS}) == len(TRIALS)
    assert all("synthetic" in trial.owner_text.casefold() for trial in TRIALS)
    assert all(
        trial.expected_decision == ("deny" if trial.kind == "safety" else "allow")
        for trial in TRIALS
    )


def test_trial_validation_requires_clean_exact_decision_and_support() -> None:
    for trial in TRIALS:
        valid = _decision(trial)
        validate_trial_decision(trial, valid)
        evidence = trial_evidence(trial, valid)
        assert evidence == {
            "decision": trial.expected_decision,
            "duration_ms": 500,
            "id": trial.id,
            "input_tokens": 100,
            "kind": trial.kind,
            "output_tokens": 20,
            "provider_turns": 1,
            "source": trial.source,
            "supporting_owner_message_count": (
                1 if trial.expected_decision == "allow" else 0
            ),
        }
        serialized = json.dumps(evidence)
        assert trial.owner_text not in serialized
        assert trial.descriptor.model_dump_json() not in serialized

        with pytest.raises(RuntimeError, match="wrong decision"):
            validate_trial_decision(
                trial,
                replace(
                    valid,
                    decision=("deny" if valid.decision == "allow" else "allow"),
                ),
            )
        with pytest.raises(RuntimeError, match="wrong decision"):
            validate_trial_decision(
                trial,
                replace(
                    valid,
                    supporting_owner_message_ids=(
                        ()
                        if valid.supporting_owner_message_ids
                        else (trial.owner_message_id,)
                    ),
                ),
            )
        with pytest.raises(RuntimeError, match="did not complete"):
            validate_trial_decision(
                trial, replace(valid, terminal_outcome="provider_error")
            )


def test_qualifier_uses_exact_production_gate_contract_and_empty_plan() -> None:
    definition, plan = build_write_gate(
        provider=frozen_provider("synthetic-profile", "gpt-5.6-terra", "high"),
    )

    assert definition.session_mode is SessionMode.isolated
    assert isinstance(definition.output_contract, StructuredOutput)
    assert definition.output_contract.name == "jarvis_automatic_write_gate"
    assert definition.output_contract.result_type is AutomaticWriteGateResult
    assert not definition.maximum_profile.ordered_grants
    assert not plan.profile.ordered_grants
    assert plan.is_tightening_of(definition.maximum_profile)
    assert (
        output_schema_digest(definition)
        == hashlib.sha256(
            canonical_json_bytes(provider_wire_schema(definition.output_contract))
        ).hexdigest()
    )


def test_qualifier_admission_reserves_one_bounded_child_per_paid_case() -> None:
    limits = qualification_admission_limits()

    assert limits.serial_child_turns == (
        len(TRIALS) * WRITE_GATE_KERNEL_LIMITS.max_provider_turns
    )
    assert limits.serial_child_input_tokens == len(TRIALS) * (
        WRITE_GATE_KERNEL_LIMITS.max_provider_input_tokens + 32_768
    )
    assert limits.serial_child_output_tokens == len(TRIALS) * (
        WRITE_GATE_KERNEL_LIMITS.max_provider_output_tokens + 8_192
    )
    assert limits.max_turns == 1 + limits.serial_child_turns
    assert limits.max_input_tokens == 1 + 32_768 + limits.serial_child_input_tokens
    assert limits.max_output_tokens == 1 + 8_192 + limits.serial_child_output_tokens


def test_all_effect_descriptors_are_bounded_and_contain_no_fixture_prose() -> None:
    for trial in TRIALS:
        assert len(trial.owner_text.encode("utf-8")) <= 8_000
        encoded = trial.descriptor.model_dump_json()
        assert trial.owner_text not in encoded
        for omitted in trial.descriptor.omitted_freeform:
            assert omitted.utf8_bytes >= 0
            assert len(omitted.sha256) == 64
            assert omitted.kind not in {"credential", "secret"}
        assert trial.tool_id in {
            ToolId("gmail.create_draft"),
            ToolId("gmail.update_draft"),
            ToolId("calendar.create_event"),
            ToolId("calendar.delete_event"),
            ToolId("schedule.wake"),
        }
