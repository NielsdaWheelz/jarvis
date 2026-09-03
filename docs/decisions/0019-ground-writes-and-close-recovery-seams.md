# ADR 0019: Ground writes and close the remaining recovery seams

- Status: Accepted; claim/attempt ordering amended by
  [ADR 0020](0020-pin-the-implemented-kernel-boundary.md)
- Date: 2026-09-02
- Amends: [ADR 0010](0010-minimal-durable-state.md),
  [ADR 0012](0012-resumable-session-and-context.md),
  [ADR 0015](0015-explicit-v1-proactivity.md), and
  [ADR 0018](0018-serial-kernel-and-bounded-recovery.md)

## Context

The corrected serial kernel made each run internally bounded, but the Jarvis
mapping still left six boundary facts underspecified:

1. A main model could read injected connector/memory/Web text and then propose a
   technically valid automatic write. The frozen plan bounded tool shape, not
   whether current owner speech actually requested that effect.
2. A write proposed after mid-loop input recorded only one origin message, so
   restart recovery could not identify the complete input prefix that preceded
   the effect.
3. Admission usage settled on normal exits but did not define the crash interval
   between durable admission and cleanup, or what the owner sees when capacity
   is temporarily unavailable.
4. `action.attempts` recorded repeats but had no finite lifetime ceiling.
5. A scheduled wake needed to remain `queued` after its tool call completed, so
   product status alone could not satisfy the durable recorder's replay
   semantics.
6. A turn may consume multiple owner messages, while `remembered_at` was
   described as if there were always one originating row.

These can be closed without another table, workflow framework, domain object, or
general provenance system.

## Decision

### Ground every proposed write

Add one internal `AutomaticWriteGate` definition. It is an isolated
`llm-agent-kernel` one-shot with a closed allow/deny result and an empty tool
plan. It runs only after strict validation of a proposed `Write` and before an
action or approval message exists.

The gate sees current owner-authored input IDs/text, the canonical tool ID, and
an allowlisted host-normalized descriptor of operation, target, audience, and
timing. Free-form payloads are replaced by length/digest. It sees no recalled
memory, connector/Web/tool result, model rationale/history, credentials, or
host-authored waking text. Allow requires direct entailment, matching scope, and
a non-empty subset of current owner IDs. Every ambiguity or failure denies.

This gate is additional Jarvis policy. It cannot widen the frozen plan, classify
approval, or override deterministic host constraints. Approval-bearing writes
pass it too, preventing untrusted content from generating nuisance or deceptive
approval requests. Its revision and supporting IDs are stored in the existing
execution contract.

The gate is a pragmatic prompt-injection reduction, not a formal proof. The
owner's own adversarially quoted text can still cause a false allow or false
deny. V1 accepts that residual and the extra model call on writes instead of
building typed information-flow provenance for every context token.

### Bind effects to the full admitted prefix

Adopt kernel dispatch lineage: claim ID, through-checkpoint, ordered admitted
input IDs, and model-step ordinal. Copy it into every action execution contract;
keep `origin_message_id` only as a convenient first-input pointer. Startup uses
the immutable contract to reconcile and close exactly the input rows that could
have influenced an effect.

Settlement puts the same run/checkpoint/conclusion identity in bounded
`message.trace` on every consumed waking row. Trace helps diagnosis and
rememberer grouping; effect correctness uses the immutable action contract.

### Reserve admission conservatively

Before provider I/O, durably reserve finite maximum turn/token capacity and one
root concurrency slot. A foreground reservation includes allowance for its
strictly serial recaller and possible write-gate child calls. The parent cannot
perform provider or tool I/O while a child runs. Background roles reserve their
own root work.

Clean exits settle actual usage and refund unused capacity. A crash leaves the
full turn/token reservation charged. Startup under the exclusive deployment
lock marks orphaned reservations interrupted and releases only their live slot;
capacity remains charged until rolling-window expiry. Missing or corrupt state
fails closed.

Admission preflight denial does not claim or increment input. After a successful
preflight under the execution mutex, checkpoint claim atomically increments
`processing_attempts`; the later durable reservation must have capacity, and an
inconsistent result raises `AdmissionStateDefect` so the kernel parks the claim.
Foreground
input remains pending and is reconsidered at reset/startup. Delays of at least
60 seconds receive one deterministic host-rendered assistant notice; background
memory work defers silently.

### Bound effect entries for life

Every action execution contract stores a finite per-tool `max_attempts >= 1`.
Executor entry atomically requires capacity and increments `attempts`.
Reconciliation proof that the effect is absent and safe to repeat remains
necessary but is no longer sufficient once the ceiling is exhausted. Proved
absence then becomes failed; unresolved evidence becomes uncertain. Slice 0
selects the exact finite values and procedures from live provider behavior.

### Separate schedule creation from wake completion

A schedule-create action remains product-status `queued`, but its closed
`result.creation_receipt` records completion of the original tool effect. The
action-backed `llm-tools` recorder always replays that immutable receipt for the
occupied position. The timer changes status and writes only a separate
`wake_outcome`. A queued row without a valid creation receipt never fires.

Cancellation is a separate gated action with its own identity, ceiling, and
receipt. It atomically succeeds itself and cancels only a queued original,
recording cancellation in the original wake outcome.

### Remember settled groups

The rememberer runs once for all owner messages consumed by one settlement.
Appending raw memories and setting every target `remembered_at` is one
transaction. The normal sweep groups by shared settlement trace; if grouping
metadata is absent, it processes rows individually and relies on search/model
judgment rather than adding a semantic-deduplication table.

## Consequences

Benefits:

- Retrieved untrusted text cannot by itself justify a Jarvis write or approval.
- Mid-loop steering has durable effect lineage and exact recovery scope.
- A process crash cannot erase rolling usage while permanently stranding the
  concurrency slot.
- No action can be evidence-authorized into an unbounded replay loop.
- Schedule creation and later wake execution coexist in one action row without
  lying to the durable recorder.
- Multi-message turns form memory once without another grouping table.

Costs:

- Every proposed write adds one isolated model call and may be falsely denied.
- Worst-case admission reservation may defer useful work that would have used
  less capacity, especially after a crash.
- `execution_contract`, `result`, and bounded `trace` carry more structure even
  though the relational schema remains unchanged.
- The schedule recorder adapter is deliberately product-specific and must be
  qualified against the public `llm-tools` API in Slice 0.

## Rejected alternatives

- Trust the main model after an untrusted read: schema and capability validation
  do not establish owner intent.
- Preselect all write authority before the run: mid-loop owner input can
  legitimately add a request, and a static selection cannot safely capture it.
- Give the gate recall or connector context: recreates the authority-laundering
  channel the gate exists to remove.
- Add token-level provenance and taint tracking: large infrastructure whose
  semantics would still be heuristic for model reasoning.
- Keep only `origin_message_id`: loses the admitted prefix after polling.
- Refund an orphaned reservation on startup: process death does not prove no
  provider usage occurred.
- Let attempts grow while reconciliation remains optimistic: reintroduces
  unbounded work at the effect layer.
- Mark schedule creation `succeeded` and add a fifth wake table: duplicates the
  same durable object to make one status column look uniform.
- Add a remembered-group table: shared settlement trace plus per-row fallback is
  sufficient for one-user v1.

## Migration and acceptance

There is no runtime migration because implementation has not started. The exact
four table/column roster remains unchanged. Acceptance changes are A2.14, A4.1,
A4.13, A5.6–A5.8, A6.1, A6.11, A6.15, A6.16, A6.18, A7.9, and A7.11.
