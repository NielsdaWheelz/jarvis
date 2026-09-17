from __future__ import annotations

from datetime import UTC, datetime

from llm_agent_kernel import (
    Checkpoint,
    ClaimId,
    HostInput,
    InputClaim,
    InputId,
    ThreadId,
    bootstrap_context,
    run_context,
)
from llm_tools import (
    PromptSection,
    PromptSectionKind,
    PromptSections,
    PromptText,
    ToolCatalog,
)
from provider_fixture import frozen_provider

from jarvis.context import CanonicalMessage, JarvisContextSource
from jarvis.definitions import build_definitions


class History:
    def __init__(self, messages: tuple[CanonicalMessage, ...]) -> None:
        self.messages = messages
        self.excluded: tuple[InputId, ...] = ()

    async def completed_history(
        self,
        thread_id: ThreadId,
        *,
        exclude_input_ids: tuple[InputId, ...],
        limit: int,
    ) -> tuple[CanonicalMessage, ...]:
        assert thread_id == ThreadId("channel-1")
        assert limit == 100
        self.excluded = exclude_input_ids
        return self.messages


async def test_stateless_bootstrap_uses_plain_canonical_context_once(
    current_catalog: ToolCatalog,
) -> None:
    definitions = build_definitions(
        catalog=current_catalog,
        provider=frozen_provider("jarvis-test", "gpt-5.6-terra", "high"),
        owner_timezone="America/Los_Angeles",
    )
    current = HostInput(
        InputId("00000000-0000-0000-0000-000000000002"),
        PromptSections(
            (
                PromptSection(
                    PromptSectionKind("owner_message"),
                    (),
                    PromptText("current & exact"),
                ),
            )
        ),
        datetime(2026, 9, 3, 16, tzinfo=UTC),
    )
    claim = InputClaim(
        ClaimId("claim-1"),
        (current,),
        Checkpoint("00000000-0000-0000-0000-000000000002"),
        datetime(2026, 9, 3, 16, 1, tzinfo=UTC),
        definitions.plans["main"],
        1,
    )
    history = History(
        (
            CanonicalMessage(
                "00000000-0000-0000-0000-000000000001",
                "owner",
                "prior text",
                datetime(2026, 9, 3, 15, tzinfo=UTC),
            ),
        )
    )
    source = JarvisContextSource(ThreadId("channel-1"), history)
    canonical = await source.bootstrap(definitions.main, claim)
    projection = bootstrap_context(
        definitions.main,
        claim.inputs,
        claim.as_of,
        claim.plan,
        canonical,
    )

    assert history.excluded == (current.input_id,)
    assert projection.rendered.count("current &amp; exact") == 1
    assert projection.rendered.count("prior text") == 1
    assert projection.rendered.index("iana_timezone") < projection.rendered.index(
        "as_of"
    )
    assert "provider_runtime" not in repr(canonical)


async def test_healthy_continuation_does_not_repeat_history_or_timezone(
    current_catalog: ToolCatalog,
) -> None:
    definitions = build_definitions(
        catalog=current_catalog,
        provider=frozen_provider("jarvis-test", "gpt-5.6-terra", "high"),
        owner_timezone="UTC",
    )
    current = HostInput(
        InputId("input-1"),
        PromptSections(
            (
                PromptSection(
                    PromptSectionKind("owner_message"), (), PromptText("hello")
                ),
            )
        ),
        datetime(2026, 9, 3, tzinfo=UTC),
    )
    claim = InputClaim(
        ClaimId("claim-1"),
        (current,),
        Checkpoint("input-1"),
        datetime(2026, 9, 3, 0, 1, tzinfo=UTC),
        definitions.plans["main"],
        1,
    )
    source = JarvisContextSource(ThreadId("channel-1"), History(()))
    dynamic = await source.continuation(
        definitions.main, claim, claim.inputs, claim.through_checkpoint
    )
    projection = run_context(
        definitions.main,
        claim.inputs,
        claim.as_of,
        claim.plan,
        dynamic,
    )

    assert projection.rendered.count("hello") == 1
    assert "iana_timezone" not in projection.rendered
    assert "canonical_history" not in projection.rendered
