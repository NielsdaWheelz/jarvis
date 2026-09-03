# ADR 0018: Map the serial kernel and bounded recovery into four tables

- Status: Accepted; dispatch lineage, admission reservations, attempt ceilings,
  and schedule-recorder semantics amended by
  [ADR 0019](0019-ground-writes-and-close-recovery-seams.md)
- Date: 2026-09-02
- Amends: [ADR 0010](0010-minimal-durable-state.md),
  [ADR 0012](0012-resumable-session-and-context.md),
  [ADR 0013](0013-unversioned-v1-tools.md), and
  [ADR 0017](0017-extract-agent-kernel.md)

## Context

An adversarial review of the first `llm-agent-kernel` specification found that
the core whole-step and checkpoint ideas were sound while its boundaries were
not:

- It described a provider surface different from the pinned public API.
- Provider containment policy was omitted from the advertised authority and
  fingerprint.
- Multi-call/parallel execution had no durable partial-outcome model.
- Input was read only once, so a human could not steer a live loop.
- Cleanup rearmed every unconsumed input, allowing poison input or cancellation
  to obtain unlimited fresh provider budgets.
- `llm-tools` vocabulary and public seams were misstated.
- “No kernel schema” was incorrectly presented as “no durable-state
  requirement.”

The owner accepted the corrected kernel design. Jarvis now needs the smallest
honest mapping without reversing the four-table product decision.

## Decision

Adopt kernel commit `049bc9221860d6fc5310f21ad560a9ec39371add` and its
actual `AgentRuntime`, serial `call_tool`, polling, settlement, admission, and
effect contracts.

Keep exactly four application tables and add only:

- `message.processing_attempts`: durable provider-work entries for one logical
  waking input; it bounds crash recovery.
- `action.execution_contract`: closed immutable host JSON containing exact
  tool/policy/plan revisions, `ToolEffect`, `ReplayPolicy`, and canonical input
  digest for the occupied position.
- `action.attempts`: count of actual effectful binding executor entries, bounded
  for life by the execution contract after ADR 0019.

The action row conforms to the durable `llm-tools` recorder/effect boundary:
`action.id` is both `InvocationPosition` and `EffectId`; immutable arguments and
execution contract identify the input; status/result carry occupied/completed/
uncertain evidence. Slice 0 MUST prove this mapping against the upgraded public
recorder API. If it cannot, work stops for a new schema ADR rather than bypassing
the executor.

V1 tool names remain unversioned. The execution contract does not select among
implementations; it proves that current code is compatible with an already
occupied durable position. Incompatible pending work is resolved or cancelled
before deployment.

Jarvis stores bounded per-message run summaries in `message.trace` and all-role
rolling admission counters in a content-free atomically replaced private
journal. The journal bounds provider turns, available normalized tokens,
no-progress attempts, and concurrency at one. Missing/corrupt state fails closed
until explicit operator reset.

ADR 0019 later made admission a conservative pre-I/O reservation, copied full
kernel dispatch lineage into the execution contract, and used shared settlement
trace across every consumed row without changing the table roster.

The kernel has no run class. Jarvis selects the batch and frozen plan, prioritizes
owner work, appends compatible input through polling, and leaves incompatible
work unclaimed. Stop/pause preempts. Ordinary follow-up racing settlement does
not suppress a valid paid answer.

## Consequences

Benefits:

- The four-table architecture survives with truthful crash and write semantics.
- Poison input, cancellation, or quota exhaustion cannot renew budgets forever.
- One serial call removes partial execution state.
- A lost provider session cannot erase the original write or its resolution
  evidence.

Costs:

- Three columns and one content-free runtime journal are now mandatory.
- The action contract stores revision/digest evidence previously considered
  speculative; the recorder boundary proved it irreducible.
- Journal corruption pauses cognitive work until operator action.
- Serial calls and no progress prose may feel slower.
- An ordinary raced follow-up is handled after the already-valid answer.

## Rejected alternatives

- Keep the earlier zero-column promise: makes poison recovery and occupied write
  replay unverifiable.
- Add intent key, client ref, lease, or general tool-version tables: still not
  required by the corrected boundary.
- Put rolling admission only in process memory: a restart renews its ceiling.
- Store the complete provider/tool transcript: unnecessary private data and
  non-canonical coupling.
- Bypass `llm-tools` for model-callable application writes: violates the single
  execution owner.
