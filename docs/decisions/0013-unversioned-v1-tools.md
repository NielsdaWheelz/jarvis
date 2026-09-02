# ADR 0013: Keep v1 tool names unversioned

- Status: Accepted
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

`tool_name`, `arguments`, and `origin_message_id` remain immutable. Host code
resolves the current declaration and validates stored arguments again before
approval rendering and immediately before execution. An unsupported name or
invalid stored argument fails closed, cancels the non-executing action, and is
reported to the owner.

An existing tool name MUST remain backward-compatible while any non-terminal
action uses it. Before deploying an incompatible schema or semantic change, the
single deployment owner resolves or cancels those actions. If incompatible
implementations genuinely need to coexist, that specific future change may add
a versioned successor name and migration rule; v1 builds no general version
registry or contract-revision store.

## Consequences

Positive:

- Tool declarations, prompts, logs, and action rows use one obvious name.
- No version dispatcher or speculative contract registry exists.
- Approval and execution remain bound by the same immutable arguments.
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
- **Store contract digests:** records structural identity but still cannot prove
  semantic compatibility.
- **Execute old arguments without current validation:** permits deployment drift
  to cross the approval boundary.
- **Mutate pending action names or arguments during migration:** changes the
  exact action the owner saw or the model proposed.
