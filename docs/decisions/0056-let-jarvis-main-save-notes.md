# adr 0056: let jarvis main save notes

[adr 0060](0060-remove-memory-forgetting.md) removes the forgetting obligations
and erasure-specific journal rules below; note-save recovery remains required.

- status: accepted implementation target, 2026-09-30; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner approved direct note saving for jarvis as well as every
  admitted, connected external agent.
- amends adr 0055's unchanged-main-catalog choice and the affected gate, action
  and read-position rules of SPEC 5–7 and 9. all other authority remains unchanged.

## decision

add `memory.save_note(text)` to main's full internal tool plan. it calls the same
validated, idempotent append function as external `memory_save_note`, writing to
the same `memory_log` with no extra model pass. jarvis does not connect to its own
mcp server. native mcp stays disabled; isolated roles and the scheduled-wake
read-only plan receive no new tool.

the host supplies the declared jarvis lane, a stable submission uuid derived from
the existing model-decision position, and null conversation association. require
jarvis lane admission, but no client bearer, `connect`, or native activation.
the model supplies only text. the provider thread and discord channel are not
jarvis archive conversation identities; do not invent a mapping.

classify the tool honestly as `Write + ReDispatchable`, with zero external
attempts. this exact canonical append bypasses AutomaticWriteGate and the action
ledger; it still uses the frozen plan, normal tool budgets, `llm-tools` executor
and durable recorder. extend the existing `read_position` recorder narrowly for
this local write, without another table or schema. use the existing invocation
position as the effect id too. the
[implementation contract](../universal-memory.md#jarvis-main-note-tool) specifies
identity derivation and crash reconciliation: a matching committed note returns
its original success, even if the resumed invocation has expired; a proven absent
note may retry with the same identity. paid-read uncertainty rules do not change.

## evidence, costs and acceptance

the pinned executor requires a durable recorder and stable effect id for writes;
it does not require jarvis's action table. jarvis's write dispatcher imposes that
table and the gate. its current read recorder rejects every unknown dispatch,
so merely reusing it would strand a note committed before receipt recording.

the cost is one explicit canonical-write exception and a narrow reconciliation
branch. main spends a tool call and may save duplicates or mistaken interpretations;
validation certifies neither truth nor authority. its unassociated notes are
outside conversation erasure, as already accepted for optional attribution.
central content guidance applies equally to both tool surfaces.

implement within the existing universal-memory packages; add no migration beyond
adr 0055's pending schema. update main's definition, binding and compatibility
revisions at cutover. retain focused checks for grants, shared storage, admission,
commit-before-receipt recovery and unchanged external-write authority in the
existing regression groups. no code, runtime configuration or deployment changes
are made by this decision.
