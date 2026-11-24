"""One stopped rewrite of the pre-conversation-capture corpus at its frozen cut."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection
from universal_memory.archive import insert_events
from universal_memory.policy import BATCH_EVENTS, split_text
from universal_memory.schema import source_conversation
from universal_memory.types import Event, normalize_event

from jarvis.tool_results import memory_result_size

if TYPE_CHECKING:
    from jarvis.historical_capture_manifest import HistoricalCaptureManifest


def require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def rewrite_history(
    conn: AsyncConnection, plan: HistoricalCaptureManifest
) -> dict[str, int]:
    """The caller owns both maintenance locks, source inventory and transaction."""
    state = (
        await conn.execute(
            text("""
        SELECT leaf_count, dream_through FROM memory_state WHERE id = 1 FOR UPDATE
    """)
        )
    ).one()
    require(
        not plan.hold and plan.leaf_count == state.leaf_count,
        "unresolved or stale historical cut",
    )
    shape = (
        await conn.execute(
            text("""
        SELECT count(*), coalesce(min(position),0), coalesce(max(position)+1,0)
        FROM memory_leaf
    """)
        )
    ).one()
    require(
        tuple(shape) == (state.leaf_count, 0, state.leaf_count),
        "noncontiguous input leaves",
    )
    await conn.execute(
        text("""
        CREATE TEMP TABLE cut_retired(
            id uuid PRIMARY KEY, conversation_id uuid NOT NULL, native_event_id text
                NOT NULL,
            native_digest text NOT NULL, part integer NOT NULL, part_count integer
                NOT NULL,
            UNIQUE(conversation_id,native_event_id,part)
        ) ON COMMIT DROP
    """)
    )
    await conn.execute(
        text("""
        INSERT INTO cut_retired
        SELECT p.id::uuid, r.conversation_id, r.native_event_id, r.native_digest,
               p.ordinal-1, jsonb_array_length(r.part_ids)
        FROM jsonb_to_recordset(cast(:carriers AS jsonb)) AS r(
            conversation_id uuid,native_event_id text,native_digest text,part_ids jsonb)
        CROSS JOIN LATERAL jsonb_array_elements_text(r.part_ids) WITH ORDINALITY AS
            p(id,ordinal)
    """),
        {"carriers": json.dumps([r.model_dump(mode="json") for r in plan.retire])},
    )
    require(
        not await conn.scalar(
            text("""
        SELECT EXISTS(
            SELECT FROM cut_retired t LEFT JOIN source_record r ON r.id=t.id
            LEFT JOIN source_conversation c ON c.id=r.conversation_id
            WHERE r.id IS NULL OR c.provider NOT IN ('codex','claude','nexus')
               OR (r.conversation_id,r.native_event_id,r.native_digest,r.part,
                   r.part_count)
                   IS DISTINCT FROM (t.conversation_id,t.native_event_id,
                       t.native_digest,t.part,t.part_count)
               OR NOT (r.kind IN ('tool_call','tool_result','memory_reference')
                       OR (r.kind='text' AND r.role='owner' AND c.provider IN
                           ('codex','claude')))
        ) OR EXISTS(
            SELECT FROM source_record r JOIN source_conversation c ON
                c.id=r.conversation_id
            LEFT JOIN cut_retired t ON t.id=r.id
            WHERE c.provider IN ('codex','claude','nexus')
              AND r.kind IN ('tool_call','tool_result','memory_reference') AND t.id
                  IS NULL
        ) OR EXISTS(
            SELECT FROM cut_retired t JOIN source_record r ON r.id=t.id
            GROUP BY t.conversation_id,t.native_event_id
            HAVING count(*)<>max(r.part_count) OR count(DISTINCT r.kind)<>1
                OR count(DISTINCT r.role)<>1
        ) OR EXISTS(
            SELECT FROM cut_retired t LEFT JOIN memory_leaf l ON l.source_record_id=t.id
            GROUP BY t.id HAVING count(l.position)<>1
        )
    """)
        ),
        "retirement manifest differs from complete stopped originals",
    )
    carriers = {
        (r.conversation_id, r.native_event_id): r
        for r in (
            await conn.execute(
                text("""
            SELECT t.conversation_id,t.native_event_id,t.native_digest,l.position,r.kind
            FROM cut_retired t JOIN source_record r ON r.id=t.id
            JOIN memory_leaf l ON l.source_record_id=r.id WHERE t.part=0
        """)
            )
        ).all()
    }
    require(len(carriers) == len(plan.retire), "duplicate or empty historical carrier")
    corrections = {key for key, row in carriers.items() if row.kind == "text"}
    deliveries: dict[tuple[UUID, str], tuple[Event, int, int]] = {}
    for ordinal, item in enumerate([*plan.recovered, *plan.gaps]):
        old_key = (item.conversation_id, item.carrier_native_event_id)
        old = carriers.get(old_key)
        require(
            old is not None and old.native_digest == item.carrier_native_digest,
            "replacement lacks its original carrier",
        )
        assert old is not None
        event = item.event
        require(
            normalize_event(event.model_dump(mode="python")) == event,
            "unnormalized replacement",
        )
        if ordinal < len(plan.recovered):
            delivery = event.attributes.get("delivery")
            require(
                event.kind == "text"
                and isinstance(delivery, dict)
                and delivery.get("carrier_event_id") == old.native_event_id,
                "recovered speech lacks exact carrier provenance",
            )
            if old.kind == "text":
                require(
                    event.role == "peer"
                    and isinstance(delivery, dict)
                    and delivery.get("kind") == "report",
                    "legacy text lacks a proved peer report",
                )
                corrections.discard(old_key)
        else:
            require(
                old.kind != "text"
                and event.kind == "gap"
                and event.role == "unknown"
                and event.text == ""
                and event.attributes.get("reason") in ("unsupported", "unreadable"),
                "invalid source gap",
            )
        key = (item.conversation_id, event.native_event_id)
        require(
            key not in carriers and key not in deliveries,
            "conflicting recovered address",
        )
        deliveries[key] = (event, old.position, ordinal)
    require(not corrections, "retired conversation text lacks its recovered report")
    await conn.execute(
        text("""
        CREATE TEMP TABLE cut_insert(
            conversation_id uuid NOT NULL,native_event_id text NOT NULL,
            anchor bigint NOT NULL,ordinal integer NOT NULL,PRIMARY
                KEY(conversation_id,native_event_id)
        ) ON COMMIT DROP
    """)
    )
    if deliveries:
        await conn.execute(
            text("""
            INSERT INTO cut_insert
            SELECT * FROM jsonb_to_recordset(cast(:items AS jsonb)) AS e(
                conversation_id uuid,native_event_id text,anchor bigint,ordinal integer)
        """),
            {
                "items": json.dumps(
                    [
                        {
                            "conversation_id": str(k[0]),
                            "native_event_id": k[1],
                            "anchor": v[1],
                            "ordinal": v[2],
                        }
                        for k, v in deliveries.items()
                    ]
                )
            },
        )
    # Some v4 deliveries might already be admitted when the cut freezes.
    existing: dict[tuple[UUID, str], list[RowMapping]] = defaultdict(list)
    for r in (
        await conn.execute(
            text("""
        SELECT r.*, l.position FROM cut_insert i JOIN source_record r
            USING(conversation_id,native_event_id)
        LEFT JOIN memory_leaf l ON l.source_record_id=r.id ORDER BY
            r.conversation_id,r.native_event_id,r.part
    """)
        )
    ).mappings():
        existing[(r["conversation_id"], r["native_event_id"])].append(r)
    for key, rows in existing.items():
        event = deliveries[key][0]
        parts = split_text(event.text)
        require(len(parts) == len(rows), "existing delivery incomplete")
        for part, (body, row) in enumerate(zip(parts, rows, strict=True)):
            require(
                row["part"] == part
                and row["part_count"] == len(parts)
                and row["text"] == body
                and row["position"] is not None
                and all(
                    row[field] == getattr(event, field)
                    for field in (
                        "native_digest",
                        "kind",
                        "role",
                        "attributes",
                        "occurred_at",
                        "turn_id",
                        "native_parent_id",
                    )
                ),
                "existing delivery differs from source proof",
            )
    # Bind every original survivor, including embedding and provenance. Sequence is
    # checked separately against the rebuilt transcript where a delivery moves.
    await conn.execute(
        text("""
        CREATE TEMP TABLE cut_survivor ON COMMIT DROP AS
        SELECT r.id, r.conversation_id, r.sequence,
            sha256(convert_to((to_jsonb(r)-'sequence')::text,'UTF8')) AS digest
        FROM source_record r LEFT JOIN cut_retired t ON t.id=r.id WHERE t.id IS NULL
    """)
    )
    await conn.execute(text("CREATE UNIQUE INDEX cut_survivor_id ON cut_survivor(id)"))
    # An identical earlier delivery remains at its first observed position. A
    # later identical delivery belongs at the old carrier, including seed progress.
    await conn.execute(
        text("""
        UPDATE cut_insert i SET anchor=least(i.anchor,l.position)
        FROM source_record r JOIN memory_leaf l ON l.source_record_id=r.id
        WHERE (r.conversation_id,r.native_event_id)=(i.conversation_id,
            i.native_event_id) AND r.part=0
    """)
    )
    pending: dict[UUID, list[Event]] = defaultdict(list)
    for key, (event, _, _) in deliveries.items():
        if key not in existing:
            pending[key[0]].append(event)
    position = state.leaf_count
    for conversation_id, events in pending.items():
        conversation = (
            (
                await conn.execute(
                    select(source_conversation).where(
                        source_conversation.c.id == conversation_id
                    )
                )
            )
            .mappings()
            .one()
        )
        for offset in range(0, len(events), BATCH_EVENTS):
            batch = events[offset : offset + BATCH_EVENTS]
            await insert_events(conn, conversation, position, batch, memory_result_size)
            position += sum(len(split_text(e.text)) for e in batch)
    # Put every recovered event at its first carrier, once, with all parts together.
    await conn.execute(
        text("""
        CREATE TEMP TABLE cut_layout ON COMMIT DROP AS
        WITH ordered AS (
            SELECT l.source_record_id,l.note_id,l.position AS anchor,0 AS ordinal,0
                AS part
            FROM memory_leaf l LEFT JOIN cut_retired t ON t.id=l.source_record_id
            LEFT JOIN source_record r ON r.id=l.source_record_id
            LEFT JOIN cut_insert i ON (i.conversation_id,
                i.native_event_id)=(r.conversation_id,r.native_event_id)
            WHERE t.id IS NULL AND i.anchor IS NULL
            UNION ALL
            SELECT l.source_record_id,l.note_id,i.anchor,i.ordinal,r.part
            FROM memory_leaf l JOIN source_record r ON r.id=l.source_record_id
            JOIN cut_insert i USING(conversation_id,native_event_id)
        )
        SELECT row_number() OVER (ORDER BY anchor,ordinal,part)-1 AS position,
               anchor,source_record_id,note_id FROM ordered
    """)
    )
    retired = (
        await conn.execute(text("SELECT count(*) FROM cut_retired"))
    ).scalar_one()
    count, dream = (
        await conn.execute(
            text("""
        SELECT count(*),count(*) FILTER (WHERE anchor<:dream) FROM cut_layout
    """),
            {"dream": state.dream_through},
        )
    ).one()
    require(count == position - retired, "reconstructed layout incomplete")
    # Excerpt neighbors use source sequence. Only conversations with inserted or
    # moved speech need renumbering. Use a disjoint temporary range because the
    # unique sequence constraint is immediate and updated rows can cross.
    await conn.execute(
        text("""
        CREATE TEMP TABLE cut_sequence ON COMMIT DROP AS
        WITH ordered AS (
            SELECT r.id,r.sequence,row_number() OVER (
                PARTITION BY r.conversation_id ORDER BY l.position)-1 AS wanted
            FROM cut_layout l JOIN source_record r ON r.id=l.source_record_id
            WHERE r.conversation_id IN (SELECT conversation_id FROM cut_insert)
        )
        SELECT id,wanted,wanted+greatest(max(sequence) OVER (),max(wanted) OVER
            ())+1 AS temporary
        FROM ordered
    """)
    )
    # The selected migrator owns these immutable-store triggers. Their DDL,
    # changes to original bytes and the new public address generation commit together.
    for statement in (
        "ALTER TABLE memory_leaf DISABLE TRIGGER memory_leaf_universal_guard",
        "DELETE FROM memory_leaf",
        "ALTER TABLE memory_leaf ENABLE TRIGGER memory_leaf_universal_guard",
        "ALTER TABLE source_record DISABLE TRIGGER source_record_universal_guard",
        "DELETE FROM source_record r USING cut_retired t WHERE r.id=t.id",
        "UPDATE source_record r SET sequence=s.temporary FROM cut_sequence s "
        "WHERE r.id=s.id AND r.sequence<>s.wanted",
        "UPDATE source_record r SET sequence=s.wanted FROM cut_sequence s "
        "WHERE r.id=s.id AND r.sequence=s.temporary",
        "ALTER TABLE source_record ENABLE TRIGGER source_record_universal_guard",
        "INSERT INTO memory_leaf(position,source_record_id,note_id) "
        "SELECT position,source_record_id,note_id FROM cut_layout",
        "DELETE FROM memory_node",
    ):
        await conn.execute(text(statement))
    await conn.execute(
        text("""
        UPDATE memory_state SET leaf_count=:count,dream_through=:dream,view_through=0,
            compaction_error=NULL,main_parts='[]',compact_parts='[]',
                main_shrinking=false,compact_shrinking=false
        WHERE id=1
    """),
        {"count": count, "dream": dream},
    )
    require(
        not await conn.scalar(
            text("""
        SELECT EXISTS(
            SELECT FROM cut_survivor s LEFT JOIN source_record r ON r.id=s.id
            LEFT JOIN cut_sequence q ON q.id=s.id
            WHERE r.id IS NULL OR r.sequence<>coalesce(q.wanted,s.sequence)
               OR sha256(convert_to((to_jsonb(r)-'sequence')::text,'UTF8'))<>s.digest
        ) OR EXISTS(
            SELECT FROM source_record r LEFT JOIN memory_leaf l ON
                l.source_record_id=r.id
            GROUP BY r.id HAVING count(l.position)<>1
        ) OR EXISTS(
            SELECT FROM (SELECT r.sequence,lag(r.sequence) OVER (
                PARTITION BY r.conversation_id ORDER BY l.position) AS previous
                FROM source_record r JOIN memory_leaf l ON l.source_record_id=r.id
                WHERE r.conversation_id IN (SELECT conversation_id FROM cut_insert))
                    ordered
            WHERE previous>=sequence
        )
    """)
        ),
        "historical cut changed an original or broke transcript order",
    )
    return {
        "retired_parts": retired,
        "added_parts": position - state.leaf_count,
        "deduplicated_events": len(existing),
        "old_leaf_count": state.leaf_count,
        "new_leaf_count": count,
        "old_dream_through": state.dream_through,
        "new_dream_through": dream,
    }
