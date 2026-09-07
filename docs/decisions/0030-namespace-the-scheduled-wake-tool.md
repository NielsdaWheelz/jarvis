# ADR 0030: Namespace the scheduled-wake tool

- Status: Accepted
- Date: 2026-09-06
- Supersedes: the `schedule_wake` model-tool spelling in ADRs 0014, 0015, and
  0019
- Amends: SPEC sections 4.4, 5.1, 7.3, 9.2, and 12; acceptance A6; the Slice 5
  catalog, plans, contracts, and qualification gates
- Owner approval: the owner explicitly directed this pre-release rename on
  2026-09-06

## Context

Slice 5 is the first slice that can create a scheduled-wake action. During its
implementation, the exact catalog exposed `schedule_wake` as the only
top-level, non-namespaced model tool. Every other application tool uses a
domain-qualified canonical ID such as `gmail.create_draft`,
`calendar.create_event`, or `memory.search`.

The base through Slice 4 contains no selectable scheduled-write binding and no
production scheduled-wake action. The inconsistent spelling can therefore be
corrected before any durable effect occupies it. Waiting until after Slice 5
would require draining or cancelling non-terminal actions under ADR 0013's
immutable-name rule.

The existing `message.source = schedule_wake` value has a different job. It is
a host protocol discriminator for a canonical waking input, not a model tool ID
or action name. Changing it would create needless message-provenance migration
and compatibility work without improving the catalog.

## Decision

The canonical model tool ID and every corresponding `action.tool_name` are
exactly:

```text
schedule.wake
```

The rename applies to the declaration, binding, maximum and selected profiles,
HostTables, frozen plans, prompts, execution contracts, durable recorder
positions, AutomaticWriteGate descriptors, recovery resolution, tests, and
current qualification evidence. The unversioned naming rule from ADR 0013 is
unchanged; the dot is a domain separator, not a version suffix.

The host-authored waking input remains exactly:

```text
message.source = schedule_wake
message.source_message_id = canonical_text(action.id)
```

Host code must not infer one identifier by mechanically replacing punctuation
in the other. Operational queries distinguish the action tool ID from the
message-source discriminator explicitly.

This is a model-visible and durable-contract change, so Slice 5 must generate
the affected tool, profile, plan, policy, role, and compatibility identities
from the final spelling. It must not preserve a stale fingerprint by hand.
Because the tool was not selectable in Slice 0–4, no previously qualified
identity is rotated solely to rewrite history.

## Consequences

Benefits:

- The catalog has one consistent domain-qualified tool-ID shape.
- Durable actions and recorder positions use an unambiguous scheduling-domain
  name before the first scheduled effect ships.
- The established waking-message source remains stable and keeps its existing
  checkpoint, recall-exclusion, and idempotency semantics.

Accepted costs:

- Tool, catalog, plan, policy, role, and compatibility fingerprints produced
  during Slice 5 differ from any in-progress pre-rename build.
- Code and operations must preserve two deliberately distinct exact strings:
  `schedule.wake` for tools/actions and `schedule_wake` for waking messages.
- A future diagnostic that compares actions with messages must map those values
  explicitly rather than assuming they are identical.

## Rejected alternatives

- Keep `schedule_wake`: leaves one catalog entry outside the otherwise exact
  domain-qualified convention before it has shipped.
- Rename the message source too: changes durable conversation provenance even
  though that value is not model-callable and gains nothing from namespacing.
- Accept both tool spellings: creates aliases, ambiguous recorder positions,
  and compatibility surface for an unshipped capability.
- Rewrite historical qualification reports: those immutable reports describe
  the exact source that was qualified at the time and contain no shipped
  scheduled-write capability.

## Migration and acceptance

There is no database migration and no production action drain because Slice 5
has not shipped and the Slice 4 base cannot create scheduled-wake actions.
Current Slice 5 qualification databases, if any, are disposable non-production
resources and must be recreated or cleaned under the report's explicit operator
procedure rather than migrated as production state.

Deterministic qualification must prove that the exact catalog, binding,
HostTable, frozen plans, AutomaticWriteGate descriptor, action contract,
recorder position, and recovery resolver use `schedule.wake`, while due and
overdue host inputs use `message.source = schedule_wake`. Historical Slice 0–4
qualification reports remain byte-identical.
