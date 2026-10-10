"""Jarvis memory bindings; shared declarations belong to universal_memory.tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from llm_tools import (
    Available,
    DeclaredToolFailure,
    ExecutionContext,
    HandlerSuccess,
    PolicyEpoch,
    ReplayPolicy,
    ToolBinding,
    ToolCatalog,
    ToolFamily,
)
from universal_memory.policy import (
    EMBEDDING_DIMENSIONS,
    FUSION_K,
    RESULT_BYTES,
    SEARCH_CANDIDATES,
    MemoryError,
)
from universal_memory.tools import (
    MEMORY_READ_SPECS,
    MEMORY_SAVE_NOTE_SPEC,
    MEMORY_SEARCH_SPEC,
    MemoryToolFailure,
    SaveNoteInput,
)
from universal_memory.types import (
    DateInput,
    DateResult,
    NoteReceipt,
    OpenInput,
    OpenPage,
    SearchInput,
    SearchResult,
    ViewInput,
    ViewPage,
    ZoomInput,
    ZoomResult,
)

if TYPE_CHECKING:
    from jarvis.memory_service import MemoryService


def memory_family(service: MemoryService) -> ToolFamily:
    # Composition runs after role/settings imports; declarations need no clients.
    from jarvis.memory_service import MemoryServiceError
    from jarvis.settings import EMBEDDING_MODEL

    async def read(
        value: SearchInput | OpenInput | ViewInput | ZoomInput | DateInput,
        context: ExecutionContext,
    ) -> HandlerSuccess[SearchResult | OpenPage | ViewPage | ZoomResult | DateResult]:
        if not context.scope.startswith("memory-through:"):
            raise RuntimeError("memory reads require a frozen host cutoff")
        cutoff = int(context.scope.removeprefix("memory-through:"))
        try:
            match value:
                case SearchInput():
                    result = await service.search(value, cutoff=cutoff)
                case OpenInput():
                    result = await service.library.open(value, cutoff=cutoff)
                case ViewInput():
                    result = await service.library.view(value.cursor, cutoff=cutoff)
                case ZoomInput():
                    result = await service.library.zoom(
                        value.start, value.count, cutoff=cutoff
                    )
                case DateInput():
                    result = await service.library.date(value.position, cutoff=cutoff)
        except MemoryError as exc:
            attempts = exc.actual_attempts if isinstance(exc, MemoryServiceError) else 0
            raise DeclaredToolFailure(
                MemoryToolFailure.model_validate({"code": exc.code}),
                actual_attempts=attempts,
            ) from None
        return HandlerSuccess(
            result, actual_attempts=1 if isinstance(value, SearchInput) else 0
        )

    async def save(
        value: SaveNoteInput, context: ExecutionContext
    ) -> HandlerSuccess[NoteReceipt]:
        if str(context.effect_id) != str(
            context.position
        ) or not context.position.startswith("native-invocation:"):
            raise RuntimeError("a main note save requires its original native position")
        try:
            receipt = await service.save_main_note(value.text, str(context.position))
        except MemoryError as exc:
            raise DeclaredToolFailure(
                MemoryToolFailure.model_validate({"code": exc.code}), actual_attempts=0
            ) from None
        return HandlerSuccess(receipt, actual_attempts=0)

    policy = {
        "authority": "historical-evidence-only",
        "cutoff": "immutable-run-scope",
        "stores": ("source_record", "memory_log", "memory_summary"),
        "max_output_bytes": RESULT_BYTES,
        "paging": "complete-source-content-and-lineage",
    }
    bindings: list[ToolBinding[Any, Any, Any]] = [
        ToolBinding(
            spec=spec,
            execute=Available(read),
            replay_policy=ReplayPolicy.BilledOnce
            if spec is MEMORY_SEARCH_SPEC
            else ReplayPolicy.ReDispatchable,
            implementation_revision=f"jarvis-{str(spec.id).replace('.', '-')}-v2",
            policy_epoch=PolicyEpoch("jarvis-universal-memory-v1"),
            policy_inputs={
                **policy,
                **(
                    {
                        "lexical": "english-and-simple-stemmed-keywords",
                        "semantic": "exact-cosine-vector-scan",
                        "fusion": {"method": "equal-weight-rrf", "k": FUSION_K},
                        "candidate_pool": SEARCH_CANDIDATES,
                        "embedding_failure": "typed-unavailable",
                        "owner_connection": "live-before-embedding",
                        "embedding_model": EMBEDDING_MODEL,
                        "embedding_dimensions": EMBEDDING_DIMENSIONS,
                        "external_attempts": 1,
                    }
                    if spec is MEMORY_SEARCH_SPEC
                    else {}
                ),
            },
        )
        for spec in MEMORY_READ_SPECS
    ]
    bindings.append(
        ToolBinding(
            spec=MEMORY_SAVE_NOTE_SPEC,
            execute=Available(save),
            replay_policy=ReplayPolicy.ReDispatchable,
            implementation_revision="jarvis-memory-save-note-v1",
            policy_epoch=PolicyEpoch("jarvis-universal-memory-v1"),
            policy_inputs={
                "authority": "admitted-jarvis-note-only",
                "identity": "native-invocation-position",
                "recovery": "exact-owned-transaction-note-receipt",
                "external_attempts": 0,
            },
        )
    )
    return ToolFamily(
        "memory", (*MEMORY_READ_SPECS, MEMORY_SAVE_NOTE_SPEC), tuple(bindings)
    )


def compose_memory_catalog(service: MemoryService) -> ToolCatalog:
    return ToolCatalog.compose((memory_family(service),))
