# ADR 0010: Keep only irreducible message and action state

- Status: Accepted; tool naming amended by ADR 0013; provider-native
  idempotency amended by ADR 0016; cross-run and recorder facts amended by
  [ADR 0018](0018-serial-kernel-and-bounded-recovery.md); lineage and finite
  attempt semantics amended by
  [ADR 0019](0019-ground-writes-and-close-recovery-seams.md); durable parking
  amended by [ADR 0020](0020-pin-the-implemented-kernel-boundary.md); delayed
  Discord delivery amended by
  [ADR 0022](0022-accept-bounded-discord-delivery-ambiguity.md)
- Date: 2026-09-01
- Amended: 2026-09-02
- Supersedes: the message/action schemas and lifecycle in
  [ADR 0007](0007-central-messages-and-unified-actions.md)

## Context

The first unified action design accumulated an intent key, client reference,
separate digest/revision columns, execution lease, and generic workflow retry
machinery. Jarvis has one user, one process, one deployment ownership lock, and
tool-specific reconciliation; those fields created invalid combinations without
resolving whether an external effect committed.

The later kernel boundary and implementation reviews found four facts that are not
reconstructable after a crash:

1. How many times one poison message has entered provider work.
2. Which exact tool/policy/plan/effect/replay/input contract occupied a durable
   write position.
3. How many actual executor entries occurred after evidence-authorized recovery.
4. Whether a configuration-defective input is in operator quarantine rather
   than ordinarily pending.

Those facts earn one message counter, one message park timestamp, one closed
action JSON value, and one action counter. They do not earn a workflow engine
or general tool-version registry.

The rule is:

> Persist a fact when losing it makes provider work, an external effect,
> approval, crash recovery, or historical diagnosis ambiguous. Reconstruct
> everything else until measured failure proves otherwise.

## Decision

The exact v1 message schema is:

```text
message
  id
  role
  text
  source
  source_conversation_id
  source_message_id
  created_at
  processed_at
  processing_attempts
  processing_parked_at
  remembered_at
  trace
```

An owner/host waking row starts with null `processed_at` and zero
`processing_attempts`. After rolling-capacity preflight, the latter increments
atomically when the checkpoint port acquires a claim. It conservatively counts
a crash or configuration defect after claim and records no retry policy;
crossing the configured ceiling stops work before provider I/O. Configuration
defects use the separate park.

`processing_parked_at` is null for ordinary work. A configuration defect stamps
it through the kernel checkpoint `park` transaction; claim and recovery scans
exclude it, and any parked row opens the single cognitive circuit until an
operator corrects the defect and explicitly clears the timestamp. A bounded
reason code may accompany it in `trace`, but diagnostic JSON is not control
state.

An assistant row starts with null `source_message_id`; a successful Create
Message response fills it. That single field is the retry watermark, so
`delivered_at` remains unnecessary. ADR 0022 records the rare delayed duplicate
accepted when Discord history omits nonce. V1 has no internal conversation
table.

Bounded `trace` contains recall IDs and compact run summaries—run/provider trace
IDs, provider turns, available normalized token usage, duration, and outcome.
It contains no message copies, prompts, model prose, tool payloads, or results.
ADR 0019 requires the same settlement identity on every consumed waking row so
multi-message groups remain reconstructable.

The exact v1 action schema is:

```text
action
  id
  tool_name
  arguments
  execution_contract
  status
  attempts
  execute_after
  origin_message_id
  approval_message_id
  created_at
  decided_at
  completed_at
  result
```

`tool_name`, `arguments`, `execution_contract`, and `origin_message_id` are
immutable. The closed host-authored `execution_contract` contains the exact
tool-contract, policy, and plan revisions, `ToolEffect`, `ReplayPolicy`, and
canonical input digest used to occupy the `llm-tools` position. ADR 0019 adds a
finite lifetime attempt ceiling, kernel claim/checkpoint/input/step lineage, and
supporting owner-input IDs from the write gate. This is one effect's recovery
evidence, not a dispatch registry or model field.

The action ID is both `InvocationPosition` and `EffectId` for `Write` and is a
provider idempotency key where supported. `attempts` increments immediately
before actual executor entry. Reconciliation reads do not increment it, and the
count never authorizes a repeat.

Action states remain exactly:

```text
queued
awaiting_approval
executing
succeeded
failed
uncertain
cancelled
```

There is no lease. One process owns execution. A timeout or `executing` row
enters tool-specific reconciliation; only proof that the effect is absent and a
repeat safe can return it to `queued`. `uncertain` is terminal for execution.

There is no semantic intent key. Source-message uniqueness prevents duplicate
input, an atomic state claim prevents duplicate execution of one row, action ID
and the occupied recorder position provide effect identity, and reconciliation
handles ambiguity. Two intentionally created identical rows remain two actions.

## Consequences

Benefits:

- Four application tables still express the complete product.
- Poison-input recovery and durable write replay are honest across restarts.
- Approval preview and execution consume the same immutable arguments and
  contract.
- No intent deduplication, lease, client bag, or general version dispatcher
  exists.

Costs:

- Four columns survived the simplification pass.
- The JSON contract must have one closed host schema and migration discipline.
- `trace` is bounded and not a complete execution log.
- Multi-process execution would require a new ownership decision.

## Rejected alternatives

- Remove `processing_attempts`: a crash loop can renew provider budgets.
- Remove `processing_parked_at` or hide it in `trace`: configuration poison
  becomes indistinguishable from runnable work after restart.
- Derive the occupied execution contract from current code: deployment drift can
  reinterpret a pending write.
- Reconstruct executor count from logs: ordinary logs are non-canonical and
  intentionally payload-poor.
- Restore the original field set: intent keys, client refs, leases, and parallel
  revision columns remain unearned.
- Add separate recorder/workflow tables now: the action row can conform to the
  required durable recorder semantics in v1; Slice 0 must stop for a new ADR if
  that mapping fails qualification.
