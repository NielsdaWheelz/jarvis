from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from llm_agent_kernel import (
    AdmissionDeferred,
    AdmissionGranted,
    AdmissionRequest,
    AdmissionUsage,
    ProviderUsage,
    RunId,
    ThreadId,
)

from jarvis.admission import RollingAdmissionPort, RootTrackingAdmissionPort
from jarvis.definitions import (
    SLICE3_RECALL_KERNEL_LIMITS,
    SLICE3_REMEMBER_KERNEL_LIMITS,
    SLICE4_DREAM_KERNEL_LIMITS,
    SLICE6_KERNEL_LIMITS,
)
from jarvis.memory import MemoryIdentity
from jarvis.messages import StoredMessage
from jarvis.settings import EMBEDDING_DIMENSION

NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)
RAW_ID = UUID("10000000-0000-4000-8000-000000000001")
OWNER_ID = UUID("20000000-0000-4000-8000-000000000001")
ROOT = Path(__file__).resolve().parents[1]
_QUALIFIER = run_path(str(ROOT / "scripts" / "qualify_memory_e2e.py"))
LiveResources = _QUALIFIER["LiveResources"]
MemoryState = _QUALIFIER["MemoryState"]
QualificationCheckFailed = cast(
    "type[Exception]", _QUALIFIER["QualificationCheckFailed"]
)
RawRow = _QUALIFIER["RawRow"]
SummaryRow = _QUALIFIER["SummaryRow"]
assert_sanitized_output = _QUALIFIER["assert_sanitized_output"]
backfill_dream_summary = _QUALIFIER["backfill_dream_summary"]
cognitive_usage = _QUALIFIER["cognitive_usage"]
cleanup_cycle_runtime = _QUALIFIER["cleanup_cycle_runtime"]
discard_main_reference = _QUALIFIER["_discard_main_reference"]
owner_inputs = _QUALIFIER["owner_inputs"]
qualification_admission_limits = _QUALIFIER["qualification_admission_limits"]
new_summaries = _QUALIFIER["new_summaries"]
selected_memories = _QUALIFIER["selected_memories"]
validate_first_phase = _QUALIFIER["validate_first_phase"]
validate_dream_phase = _QUALIFIER["validate_dream_phase"]
validate_second_phase = _QUALIFIER["validate_second_phase"]


def _resources() -> Any:
    return LiveResources(
        gmail_thread_id="thread-123",
        gmail_message_id="message-456",
        calendar_id="primary@example.test",
        calendar_event_id="event-789",
    )


def _owner(*, remembered: bool = True) -> StoredMessage:
    return StoredMessage(
        id=OWNER_ID,
        role="owner",
        text="Synthetic-safe qualification owner input.",
        source="qualification",
        source_conversation_id="qualification-channel",
        source_message_id="qualification-source",
        created_at=NOW,
        processed_at=NOW,
        processing_attempts=1,
        processing_parked_at=None,
        remembered_at=NOW if remembered else None,
        trace={
            "recaller": {
                "candidate_memory_ids": [],
                "selected_memory_ids": [
                    {"table_kind": "memory_log", "id": str(RAW_ID)}
                ],
                "run": {
                    "duration_ms": 12,
                    "input_tokens": 30,
                    "output_tokens": 4,
                    "provider_turns": 1,
                    "terminal_outcome": "completed",
                },
            },
            "rememberer": {
                "created_memory_ids": [str(RAW_ID)],
                "run": {
                    "duration_ms": 15,
                    "input_tokens": 40,
                    "output_tokens": 8,
                    "provider_turns": 1,
                    "terminal_outcome": "completed",
                },
            },
        },
    )


async def test_admission_fits_two_current_memory_cycles_and_one_dream(
    tmp_path: Path,
) -> None:
    limits = qualification_admission_limits()
    path = tmp_path / "admission.json"
    RollingAdmissionPort.initialize(path, limits)
    admission = RootTrackingAdmissionPort(RollingAdmissionPort(path, limits))
    roles = (
        SLICE6_KERNEL_LIMITS,
        SLICE3_REMEMBER_KERNEL_LIMITS,
        SLICE4_DREAM_KERNEL_LIMITS,
        SLICE6_KERNEL_LIMITS,
        SLICE3_REMEMBER_KERNEL_LIMITS,
    )
    for index, role in enumerate(roles):
        foreground = role is SLICE6_KERNEL_LIMITS
        root = await admission.reserve(
            AdmissionRequest(
                RunId(f"qualification-{index}"),
                ThreadId(f"owner-{index}") if foreground else None,
                1 if foreground else None,
                role.max_provider_turns,
                role.max_provider_input_tokens,
                role.max_provider_output_tokens,
            )
        )
        assert isinstance(root, AdmissionGranted)
        if foreground:
            recall = SLICE3_RECALL_KERNEL_LIMITS
            child = await admission.reserve(
                AdmissionRequest(
                    RunId(f"recaller-{index}"),
                    None,
                    None,
                    recall.max_provider_turns,
                    recall.max_provider_input_tokens,
                    recall.max_provider_output_tokens,
                    parent=root.token,
                )
            )
            assert isinstance(child, AdmissionGranted)
            await admission.settle(
                child.token,
                AdmissionUsage(recall.max_provider_turns, ProviderUsage(), 0.0),
            )
        await admission.settle(
            root.token,
            AdmissionUsage(role.max_provider_turns, ProviderUsage(), 0.0),
        )

    assert limits.max_turns == 86
    extra = await admission.reserve(
        AdmissionRequest(RunId("extra"), None, None, 1, 1, 1)
    )
    assert isinstance(extra, AdmissionDeferred)


def test_owner_inputs_use_documented_natural_language_refs() -> None:
    first, second, uris = owner_inputs(_resources())

    assert "<refs>" in first and "</refs>" in first
    assert (
        '<ref uri="gmail://primary/message/message-456">Related email in Gmail '
        "thread thread-123</ref>"
    ) in first
    assert (
        '<ref uri="gcal://primary%40example.test/event/event-789">Related calendar '
        "event</ref>"
    ) in first
    assert uris == (
        "gmail://primary/message/message-456",
        "gcal://primary%40example.test/event/event-789",
    )
    assert "thread-123" not in second
    assert "event-789" not in second
    assert "memory is evidence" in second


def test_first_phase_requires_linked_preference_vector_and_watermark() -> None:
    _, _, uris = owner_inputs(_resources())
    memory_text = (
        "The owner prefers exactly three short bullets headed Decision, Evidence, "
        f'and Next check. Gmail thread thread-123. <refs><ref uri="{uris[0]}">'
        "Email</ref>"
        f'<ref uri="{uris[1]}">Event</ref></refs>'
    )
    created, report = validate_first_phase(
        before=MemoryState((), 0, 0),
        after=MemoryState((RawRow(RAW_ID, memory_text, EMBEDDING_DIMENSION),), 0, 0),
        owner=_owner(),
        required_uris=uris,
        required_gmail_thread_id="thread-123",
    )

    assert created == frozenset((RAW_ID,))
    assert report == {
        "action_rows": 0,
        "created_raw_rows": 1,
        "duplicate_memory_text": False,
        "linked_preference_stored": True,
        "summary_rows": 0,
        "vectors_1536": True,
        "watermark_advanced": True,
    }


@pytest.mark.parametrize(
    ("rows", "remembered", "reason"),
    [
        (
            (RawRow(RAW_ID, "not the linked preference", EMBEDDING_DIMENSION),),
            True,
            "durable_linked_preference_missing",
        ),
        (
            (RawRow(RAW_ID, "linked preference", None),),
            True,
            "created_embedding_invalid",
        ),
        ((), True, "first_rememberer_created_not_one_memory"),
        (
            (RawRow(RAW_ID, "linked preference", EMBEDDING_DIMENSION),),
            False,
            "first_owner_watermark_missing",
        ),
    ],
)
def test_first_phase_fails_closed(
    rows: tuple[Any, ...], remembered: bool, reason: str
) -> None:
    with pytest.raises(QualificationCheckFailed, match=reason):
        validate_first_phase(
            before=MemoryState((), 0, 0),
            after=MemoryState(rows, 0, 0),
            owner=_owner(remembered=remembered),
            required_uris=("gmail://required", "gcal://required"),
            required_gmail_thread_id="required-thread",
        )


def test_first_phase_requires_private_gmail_thread_identity_in_memory() -> None:
    _, _, uris = owner_inputs(_resources())
    memory_text = (
        "The owner prefers exactly three short bullets headed Decision, Evidence, "
        f'and Next check. <refs><ref uri="{uris[0]}">Email</ref>'
        f'<ref uri="{uris[1]}">Event</ref></refs>'
    )

    with pytest.raises(
        QualificationCheckFailed, match="durable_linked_preference_missing"
    ):
        validate_first_phase(
            before=MemoryState((), 0, 0),
            after=MemoryState((RawRow(RAW_ID, memory_text, 1536),), 0, 0),
            owner=_owner(),
            required_uris=uris,
            required_gmail_thread_id="thread-123",
        )


def test_second_phase_requires_selected_created_row_and_exact_live_reopens() -> None:
    class Evidence:
        gmail_reopened = True
        calendar_reopened = True
        successful_reads = 2

    summary_id = UUID(int=3)
    report = validate_second_phase(
        after=MemoryState(
            (RawRow(RAW_ID, "Synthetic durable preference.", 1536),),
            1,
            0,
            (
                SummaryRow(
                    summary_id,
                    "Synthetic summary.",
                    (RAW_ID,),
                    1536,
                ),
            ),
        ),
        owner=_owner(),
        first_created=frozenset((RAW_ID,)),
        created_summaries=frozenset((summary_id,)),
        selected=(
            *selected_memories(_owner().trace),
            MemoryIdentity("memory_summary", summary_id),
        ),
        opened=(
            MemoryIdentity("memory_log", RAW_ID),
            MemoryIdentity("memory_summary", summary_id),
        ),
        answer_text=(
            "- **Decision:** Keep the current plan.\n"
            "- **Evidence:** Both live records were reopened.\n"
            "- **Next check:** Review the linked matter tomorrow."
        ),
        dispatcher=Evidence(),
    )

    assert report["fresh_recall_selected_created_raw"] is True
    assert report["fresh_recall_selected_created_summary"] is True
    assert report["fresh_recall_opened_summary_sources"] is True
    assert report["gmail_thread_reopened"] is True
    assert report["calendar_event_reopened"] is True
    assert report["successful_main_reads"] == 2
    assert report["action_rows"] == 0
    assert report["owner_visible_answer_useful"] is True
    assert report["response_preference_followed"] is True


def test_second_phase_rejects_duplicate_memory_text() -> None:
    class Evidence:
        gmail_reopened = True
        calendar_reopened = True
        successful_reads = 2

    duplicate = "Synthetic duplicate."

    summary_id = UUID(int=3)
    with pytest.raises(QualificationCheckFailed, match="duplicate_memory_text"):
        validate_second_phase(
            after=MemoryState(
                (
                    RawRow(RAW_ID, duplicate, 1536),
                    RawRow(UUID(int=2), duplicate, 1536),
                ),
                1,
                0,
                (SummaryRow(summary_id, "Summary.", (RAW_ID,), 1536),),
            ),
            owner=_owner(),
            first_created=frozenset((RAW_ID,)),
            created_summaries=frozenset((summary_id,)),
            selected=(
                MemoryIdentity("memory_log", RAW_ID),
                MemoryIdentity("memory_summary", summary_id),
            ),
            opened=(
                MemoryIdentity("memory_log", RAW_ID),
                MemoryIdentity("memory_summary", summary_id),
            ),
            answer_text=(
                "- Decision: Keep the current plan.\n"
                "- Evidence: Both records were reopened.\n"
                "- Next check: Review the matter tomorrow."
            ),
            dispatcher=Evidence(),
        )


@pytest.mark.parametrize(
    ("opened", "answer", "reason"),
    [
        (
            (MemoryIdentity("memory_summary", UUID(int=3)),),
            "- Decision: Keep the plan.\n"
            "- Evidence: Both records agree.\n"
            "- Next check: Review tomorrow.",
            "summary_raw_sources_not_opened",
        ),
        (
            (
                MemoryIdentity("memory_log", RAW_ID),
                MemoryIdentity("memory_summary", UUID(int=3)),
            ),
            "The linked matter is current.",
            "owner_answer_preference_not_followed",
        ),
        (
            (
                MemoryIdentity("memory_log", RAW_ID),
                MemoryIdentity("memory_summary", UUID(int=3)),
            ),
            "- Decision:\n"
            "- Evidence: Both records agree.\n"
            "- Next check: Review tomorrow.",
            "owner_answer_not_useful",
        ),
    ],
)
def test_second_phase_requires_opened_raw_basis_and_useful_preference_answer(
    opened: tuple[MemoryIdentity, ...],
    answer: str,
    reason: str,
) -> None:
    class Evidence:
        gmail_reopened = True
        calendar_reopened = True
        successful_reads = 2

    summary_id = UUID(int=3)
    with pytest.raises(QualificationCheckFailed, match=reason):
        validate_second_phase(
            after=MemoryState(
                (RawRow(RAW_ID, "Synthetic durable preference.", 1536),),
                1,
                0,
                (SummaryRow(summary_id, "Summary.", (RAW_ID,), 1536),),
            ),
            owner=_owner(),
            first_created=frozenset((RAW_ID,)),
            created_summaries=frozenset((summary_id,)),
            selected=(
                MemoryIdentity("memory_log", RAW_ID),
                MemoryIdentity("memory_summary", summary_id),
            ),
            opened=opened,
            answer_text=answer,
            dispatcher=Evidence(),
        )


def test_dream_phase_requires_one_embedded_summary_with_exact_raw_lineage() -> None:
    _, _, uris = owner_inputs(_resources())
    raw = (RawRow(RAW_ID, "Synthetic raw memory.", EMBEDDING_DIMENSION),)
    summary_id = UUID(int=3)
    created, report = validate_dream_phase(
        before=MemoryState(raw, 0, 0),
        after=MemoryState(
            raw,
            1,
            0,
            (
                SummaryRow(
                    summary_id,
                    f"Synthetic linked summary {uris[0]} and {uris[1]}.",
                    (RAW_ID,),
                    EMBEDDING_DIMENSION,
                ),
            ),
        ),
        first_created=frozenset((RAW_ID,)),
        required_uris=uris,
    )

    assert created == frozenset((summary_id,))
    assert report["flattened_raw_lineage"] is True
    assert report["raw_memory_unchanged"] is True


def test_trace_projection_keeps_only_usage_and_selected_identities() -> None:
    owner = _owner()

    assert selected_memories(owner.trace) == (MemoryIdentity("memory_log", RAW_ID),)
    assert cognitive_usage(owner.trace, "recaller") == {
        "duration_ms": 12,
        "input_tokens": 30,
        "output_tokens": 4,
        "provider_turns": 1,
    }
    assert cognitive_usage(owner.trace, "rememberer") == {
        "duration_ms": 15,
        "input_tokens": 40,
        "output_tokens": 8,
        "provider_turns": 1,
    }


def test_report_sanitizer_rejects_resource_or_secret_values() -> None:
    assert_sanitized_output({"status": "passed", "count": 1}, ("private-id",))

    with pytest.raises(QualificationCheckFailed, match="report_contains_private_value"):
        assert_sanitized_output(
            {"status": "passed", "accidental": "private-id"}, ("private-id",)
        )


def test_all_script_owned_http_clients_disable_environment_proxies() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "qualify_memory_e2e.py"
    ).read_text(encoding="utf-8")

    assert source.count("httpx.AsyncClient(") == 5
    assert source.count("trust_env=False") == 5


def test_e2e_embeds_the_summary_through_the_shipped_bounded_backfill() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "qualify_memory_e2e.py"
    ).read_text(encoding="utf-8")

    assert "await rememberer.run_one(CancellationToken())" in source
    assert ".update_embedding(" not in source


async def test_empty_completed_dream_fails_before_embedding_backfill() -> None:
    state = MemoryState(
        (RawRow(RAW_ID, "Synthetic raw memory.", EMBEDDING_DIMENSION),),
        0,
        0,
    )
    assert new_summaries(state, state) == ()

    class Rememberer:
        calls = 0

        async def run_one(self, cancellation: object) -> bool:
            self.calls += 1
            return True

    rememberer = Rememberer()
    with pytest.raises(
        QualificationCheckFailed, match="dreamer_created_not_one_summary"
    ):
        await backfill_dream_summary(state, state, rememberer)
    assert rememberer.calls == 0


@pytest.mark.parametrize(("present", "discard_calls"), [(True, 1), (False, 0)])
async def test_final_cleanup_proves_reference_absent_with_or_without_one(
    present: bool, discard_calls: int
) -> None:
    class References:
        def __init__(self) -> None:
            self.current = object() if present else None

        async def load(self, thread_id: object, fingerprint: object) -> object | None:
            del thread_id, fingerprint
            return self.current

    references = References()

    class Runner:
        calls = 0

        async def discard_recovered_session_reference(self) -> None:
            self.calls += 1
            references.current = None

    runner = Runner()
    await discard_main_reference(
        settings=SimpleNamespace(discord=SimpleNamespace(channel_id=3)),
        definitions=SimpleNamespace(main=SimpleNamespace(fingerprint="fingerprint")),
        runtime=SimpleNamespace(references=references),
        runner=runner,
        require_present=False,
    )

    assert references.current is None
    assert runner.calls == discard_calls


async def test_failure_path_discards_saved_reference_before_runtime_close() -> None:
    class References:
        current: object | None = object()

        async def load(self, *args: object) -> object | None:
            del args
            return self.current

    references = References()
    order: list[str] = []

    class Runner:
        async def discard_recovered_session_reference(self) -> None:
            order.append("discard")
            references.current = None

    class Runtime:
        def __init__(self) -> None:
            self.references = references

        async def close(self) -> None:
            order.append("close")

    await cleanup_cycle_runtime(
        settings=SimpleNamespace(discord=SimpleNamespace(channel_id=3)),
        definitions=SimpleNamespace(main=SimpleNamespace(fingerprint="fingerprint")),
        runtime=Runtime(),
        runner=Runner(),
        primary_error=QualificationCheckFailed("primary_failure"),
    )

    assert references.current is None
    assert order == ["discard", "close"]


async def test_cleanup_failure_does_not_mask_primary_failure() -> None:
    class References:
        async def load(self, *args: object) -> object:
            del args
            raise RuntimeError("private reference cleanup detail")

    class Runtime:
        references = References()
        closed = False

        async def close(self) -> None:
            self.closed = True
            raise RuntimeError("private runtime cleanup detail")

    runtime = Runtime()
    await cleanup_cycle_runtime(
        settings=SimpleNamespace(discord=SimpleNamespace(channel_id=3)),
        definitions=SimpleNamespace(main=SimpleNamespace(fingerprint="fingerprint")),
        runtime=runtime,
        runner=SimpleNamespace(),
        primary_error=QualificationCheckFailed("primary_failure"),
    )

    assert runtime.closed is True


async def test_cleanup_failure_without_primary_is_content_free() -> None:
    class Runtime:
        references = SimpleNamespace()

        async def close(self) -> None:
            raise RuntimeError("private runtime cleanup detail")

    with pytest.raises(
        QualificationCheckFailed, match="cycle_runtime_cleanup_failed"
    ) as failure:
        await cleanup_cycle_runtime(
            settings=SimpleNamespace(discord=SimpleNamespace(channel_id=3)),
            definitions=SimpleNamespace(
                main=SimpleNamespace(fingerprint="fingerprint")
            ),
            runtime=Runtime(),
            runner=None,
            primary_error=None,
        )

    assert "private" not in str(failure.value)
