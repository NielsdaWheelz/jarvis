# ADR 0013: Keep v1 tool names unversioned

- Status: Accepted; occupied-position evidence amended by
  [ADR 0018](0018-serial-kernel-and-bounded-recovery.md) and
  [ADR 0019](0019-ground-writes-and-close-recovery-seams.md)
- Date: 2026-09-01
- Supersedes: the mandatory tool-name versioning portions of
  [ADR 0010](0010-minimal-durable-state.md)

## Context

Jarvis has one deployment and one action executor. V1 has no requirement to run
two incompatible implementations of one tool concurrently. Suffixing every
tool with `.v1` and maintaining version-dispatch policy would encode a future
coexistence problem before it exists.

The durable requirement is narrower: an approved action must execute the exact
stored arguments under compatible semantics. A name suffix alone does not prove
semantic compatibility, and immutable arguments already preserve what the owner
approved.

## Decision

V1 tool names are stable canonical identifiers without mandatory version
suffixes, for example `gmail.send_draft`.

`tool_name`, `arguments`, `execution_contract`, and `origin_message_id` remain
immutable. The closed host-authored execution contract records the exact
tool/policy/plan revisions, effect/replay declarations, and input digest for the
occupied durable position. It is evidence used to reject drift, not a registry
that selects an old implementation. Host code resolves the current declaration
and validates stored arguments and contract again before approval rendering and
execution. An unsupported name or invalid value fails closed, cancels the
non-executing action, and is reported to the owner.

An existing tool name MUST remain backward-compatible while any non-terminal
action uses it. Before deploying an incompatible schema or semantic change, the
single deployment owner resolves or cancels those actions. If incompatible
implementations genuinely need to coexist, that specific future change may add
a versioned successor name and migration rule; v1 builds no general version
registry.

## Consequences

Positive:

- Tool declarations, prompts, logs, and action rows use one obvious name.
- No version dispatcher or speculative contract registry exists.
- Approval and execution remain bound by the same immutable arguments.
- Durable recorder replay can prove that the occupied input and declarations
  still match.
- Versioning remains available later at the exact tool boundary that earns it.

Accepted costs:

- Incompatible deployments require draining or cancelling a small number of
  non-terminal actions.
- V1 cannot keep old and new incompatible executors live under one name.
- Semantic backward compatibility remains an engineering rule; a suffix would
  not have verified it automatically either.

## Rejected alternatives

- **Version every tool from launch:** ceremony and dispatch surface with no v1
  coexistence requirement.
- **Use a digest as a version dispatcher:** structural identity cannot select or
  prove an old implementation. V1 stores it only as one part of occupied-position
  evidence and still requires current compatibility.
- **Execute old arguments without current validation:** permits deployment drift
  to cross the approval boundary.
- **Mutate pending action names or arguments during migration:** changes the
  exact action the owner saw or the model proposed.
