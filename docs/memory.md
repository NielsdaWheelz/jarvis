# Memory specification

This document expands [SPEC section 6](../SPEC.md#6-memory).

## Mental model

```text
central message history
          │
          ▼
      rememberer ─────────► memory_log
                                │
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
        full-text index     embeddings          dreamer
                                                    │
                                                    ▼
                                             memory_summary
```

`memory_log` is the durable substrate. A row is a model-made recollection, not
proof of current external reality. Everything used to organize or retrieve those
rows is replaceable.

## Schema

```text
memory_log
  id
  text
  created_at
  embedding

memory_summary
  id
  text
  source_memory_ids
  created_at
  embedding
```

No semantic column may be added in v1. In particular, memory has no category,
importance, confidence, salience, validity, conflict, person, project, or
procedure field.

The physical migration adds no search columns. It creates English-stemmed and
simple-token GIN expression indexes over `text`, preserving the exact canonical
column schema while keeping both lexical representations rebuildable.

Recommended physical types:

- `id`: application-generated UUID.
- `text`: non-empty UTF-8 text.
- `created_at`: database-generated `timestamptz` in UTC.
- `embedding`: nullable `vector(1536)`, pinned with the deployment's
  `text-embedding-3-small` model.
- `source_memory_ids`: non-empty UUID array validated by host code against
  `memory_log` before insertion.

Exact vector scans are sufficient initially. Add an approximate vector index
only after measured corpus size or latency requires one. Full-text search SHOULD
index both an English-stemmed representation and a simple token representation
so names and rare identifiers survive stemming.

## Raw-memory immutability

The application database role can select and insert raw memories and update only
the derived embedding column. It cannot delete, truncate, or edit raw identity,
text, or creation time.

The first migration SHOULD enforce this with grants plus a simple trigger:

```sql
CREATE FUNCTION memory_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'memory_log is append-only';
  END IF;

  IF NEW.id IS DISTINCT FROM OLD.id
     OR NEW.text IS DISTINCT FROM OLD.text
     OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'memory_log identity, text, and time are immutable';
  END IF;

  RETURN NEW;
END $$;

CREATE TRIGGER memory_log_no_mutate
  BEFORE UPDATE OR DELETE ON memory_log
  FOR EACH ROW EXECUTE FUNCTION memory_log_append_only();
```

`DELETE` and `TRUNCATE` are not granted to the application role. The application
role receives column-level update permission only for `embedding`.

V1 has no trigger bypass, redaction function, external erasure journal, or
destructive consolidation. Adding administrative erasure requires a new design
covering every durable and third-party copy, not a special case in this trigger.

## Raw-memory format

A useful raw memory:

- Stands alone when retrieved later.
- Names its subject when pronouns would be ambiguous.
- Includes a date in prose when time matters.
- Preserves uncertainty rather than turning possibilities into decisions.
- Contains enough context to prevent the owner repeating an explanation.
- Refers to live external resources instead of copying their entire contents.

Example:

```xml
On 1 September 2026, Nikhil decided that Jarvis v1 should preserve raw
natural-language memories and rebuild every summary and index from them.

<refs>
  <ref uri="discord://jarvis/general/message-123">Decision discussion</ref>
</refs>
```

References are ordinary text with a recognizable convention. V1 has no XML
schema or relationship table. A well-formed reference may be opened through an
existing tool; malformed references do not invalidate the memory.

A later correction is another self-contained natural-language memory explaining
what changed. No special `corrects` edge or deterministic relation resolver
exists in v1. Search and dreaming are responsible for bringing related and
contradictory recollections together.

## Rememberer

### Invocation

The rememberer runs once after a settled input group containing one or more
owner messages that:

- Produced a validated `say`.
- Finished silently through `finish`.
- Created an action awaiting approval and a host-rendered approval message.

It opens a fresh isolated Codex session and receives every consumed owner
message in the group, the persisted conclusion, source timestamps, material
tool/action observations, and the identities of memories recalled for that work
so it may reopen them. Host action-resolution or scheduled-wake rows may appear
as context but are never watermark targets. Its root invocation receives the
owner timezone and one host-generated `as_of` value once.

### Reasoning

The rememberer is a bounded Codex role. It may search and open memory several
times. Its final structured result is a list of zero or more memory strings.

It asks:

> What from this interaction would make Jarvis meaningfully more helpful in a
> future situation?

Good candidates include preferences, decisions, unresolved intentions,
persistent circumstances, relationships, and reusable lessons.

Poor candidates include greetings, full resource copies, transient live state,
unsupported inference, secrets, standing authority, and redundant paraphrases.

### Commit

Host code validates the final strings and performs one transaction:

1. Append every accepted raw memory.
2. Set `remembered_at` on every consumed owner message in the settled group.

A successful rememberer that returns no memories still sets every watermark. A
failed or cancelled run leaves all target values null. A bounded sweep retries
completed owner rows where `processed_at IS NOT NULL` and
`remembered_at IS NULL`. Normally it groups rows by their shared settled run and
conclusion trace and processes the group once. If legacy or damaged trace cannot
establish the group, it processes owner rows individually; search and model
judgment limit duplicate memories without claiming exact semantic deduplication.
The explicit processing watermark prevents an interrupted turn from being
mistaken for a completed turn whose rememberer merely chose to write nothing.
Rows with `role = host`, including action resolutions and scheduled wakes, are
excluded as targets.

This is a canonical application transaction, not a tool effect. It creates no
`action` row and stores the memory text in no other Jarvis table.

Before insertion, host code rejects unmistakable secret material such as private
key blocks and known API-token prefixes. The candidate is dropped whole and the
diagnostic contains no secret text. Broader heuristics are added only after
measured need.

Embeddings may be populated after the raw transaction. Until then, lexical search
still finds the memory.

## Recaller

The recaller runs in a fresh isolated Codex session before every owner-authored
human input. It receives the owner timezone and the foreground turn's one
host-generated `as_of` value. It has two primitives:

```text
memory.search(query, lexical_limit, semantic_limit)
memory.open(identities)
```

Search covers both tables and returns the union of full-text and vector results.
The host deduplicates identical `(table_kind, id)` results but does not suppress a
raw memory merely because a selected summary cites it.

Every semantic search sends its bounded query to the configured OpenAI embedding
processor and incurs a metered embedding call. Lexical-only search sends nothing
to that processor. An embedding failure removes only the semantic lane for that
call; PostgreSQL lexical retrieval still runs.

Candidates include their ID, table kind, text, creation time, retrieval ranks,
and summary source IDs where applicable. The recaller may reformulate queries,
search repeatedly, and open raw sources before returning a compact bundle.

The recaller SHOULD open a summary's raw sources when exact detail matters, when
sources may disagree, when the user asks where something came from, or when an
outward action may rely on the memory.

An empty bundle is a correct result.

## Dreamer

The dreamer runs in a fresh isolated Codex session periodically or manually when
no owner work is waiting. Its root invocation receives one job `as_of` value. It
may search and open raw memories and current summaries across several Codex
turns.

Its final structured output is a batch of:

- Summary insertions with flattened raw lineage.
- Summary IDs to remove or replace.

Host code validates all referenced raw IDs and applies the batch transactionally.
Summary persistence creates no action rows.

A summary:

- Has at least one raw source ID.
- Resolves directly to raw IDs even if built using other summaries.
- Introduces no material claim unsupported by its sources.
- Preserves meaningful disagreement or uncertainty.

The dreamer cannot update raw memory, execute external actions, alter prompts or
permissions, edit code, or deploy itself.

## Embeddings

The deployment pins `text-embedding-3-small` with exactly 1,536 dimensions.
These are deployment configuration, not row metadata.

Ordinary ingestion may leave embeddings null during an outage. Queries exclude
null vectors and retain lexical results.

A model change is an offline rebuild:

1. Stop Jarvis.
2. Clear every raw and summary vector in one transaction.
3. Apply a migration if the vector dimension changes.
4. Update deployment configuration.
5. Re-embed the entire corpus.
6. Run recall evaluation.
7. Restart Jarvis.

Because all old vectors are cleared before new vectors are written and service
remains stopped, the system never searches a mixed vector space.

## Recall evaluation

`eval/recall.jsonl` is a version-controlled, synthetic or redacted set of at
least fifteen owner-authored or explicitly owner-approved cases. Model-invented
cases are never described as owner-authored:

```json
{"id":"R07","query":"...","must_recall_ids":["..."],"lane":"semantic"}
```

The set includes:

- At least five semantic cases whose queries share no important keyword with the
  expected memories.
- At least three lexical cases involving a name or rare term.
- At least three empty cases where returning no memory is correct.
- At least one contradiction case.
- At least one summary-lineage case.

Cases originate from real Slice 3 usage but contain no private raw data in the
repository. They run through one documented command.

## Rebuild contract

The required rebuild test:

1. Record the recall evaluation result.
2. Delete every `memory_summary` row.
3. Clear every embedding and rebuildable search artifact.
4. Rebuild raw full-text search and embeddings.
5. Run the dreamer to regenerate summaries.
6. Embed and index summaries.
7. Run recall evaluation again.

The post-rebuild result must be no worse than the pre-rebuild result. Generated
summary text need not be byte-identical.

## Current-state rule

Memory does not replace live integration state. Questions about current mail,
calendar events, places, or public-Web information use the corresponding tool.
Current Jarvis conversation comes from canonical `message` rows; Discord has no
model-callable read tool in v1. Recalled memory supplies history and relevance.

Memory quality is judged by whether it reduces repeated explanation while
keeping irrelevant recollections out of the main context. Schema richness is not
a success metric.
