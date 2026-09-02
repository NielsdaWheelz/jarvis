# ADR 0017: Extract the reusable bounded agent kernel

- Status: Accepted
- Date: 2026-09-01
- Amends: [ADR 0004](0004-python-codex-and-tool-kernel.md),
  [ADR 0007](0007-central-messages-and-unified-actions.md), and
  [ADR 0012](0012-resumable-session-and-context.md)
- Clarifies: [ADR 0006](0006-no-workflow-framework.md)

## Context

Jarvis needs a strict model protocol, provider-neutral reconstruction, bounded
model/tool loops, session-reference handling, cancellation, and race-safe drain
completion. Those mechanisms are not personal-assistant product behavior. They
will recur in other applications using the owner's `provider-runtime` and
`llm-tools` libraries.

A survey of Codapt2 at revision `62123f8c37b0` found several strong reusable
invariants: validate the complete model step before effects, return corrective
protocol feedback, keep canonical application events independent of provider
transcripts, give one drain exclusive ownership, and use a consumed-input
watermark when attempting to become idle so newly arrived work is not stranded.
Its broader implementation—durable workflow machinery, many state projections,
persistent peer agents, semantic tool discovery, and Lua execution—is not needed
for Jarvis v1.

Keeping the generic machinery inside Jarvis would make later extraction harder
and invite multiple subtly different crash and race implementations. Copying
Codapt2 wholesale would instead introduce more concepts than this one-user
prototype needs.

## Decision

Create an independent Python 3.12 repository and distribution named
`llm-agent-kernel`, imported as `llm_agent_kernel`. Jarvis consumes a qualified,
pinned git revision rather than a mutable sibling checkout.

Dependency direction is one way:

```text
Jarvis
  -> llm-agent-kernel
       -> provider-runtime
       -> llm-tools
```

Neither lower-level library depends on Jarvis or on another consumer. The kernel
does not create database tables, migrations, connectors, product policy, or user
interfaces.

Ownership is explicit:

| Owner | Responsibilities |
|---|---|
| `provider-runtime` | Provider calls and normalized events; Codex authentication, containment, session start/continue/resume/discard, and opaque session references |
| `llm-tools` | Typed prompt sections; tool declarations, frozen grants, schema validation, execution budgets, effect identity/replay semantics, and portable tools |
| `llm-agent-kernel` | Immutable agent definitions with maximum capability envelopes and output contracts; the exact model-step protocol; whole-step validation; bounded thread drains and isolated one-shot runs; continuation/bootstrap coordination; `ContextSourcePort`, `SessionRefPort`, `InputCheckpointPort`, `ToolDispatchPort`, `ClockPort`, cancellation, and optional `EventSinkPort`; reusable conformance tests |
| Jarvis | Product context selection; canonical messages and memories; implementations of kernel persistence ports; Discord; connectors; tool catalog composition; information-flow and authority policy; approval/action semantics; scheduling; credentials; user-visible delivery |

The kernel's exact discriminated model-step grammar is:

```text
say
  text

call_tools
  calls:
    call_id
    canonical tool ID
    arguments

finish
  optional reason
  result only as required by the frozen output contract
```

Unknown fields are rejected. Every `call_tools` step and every contained call
must validate before any call dispatches. `call_tools` has no user-facing text;
it returns correlated typed observations, and only a later separate `say` may
describe their actual outcome. A `say` concludes the current input visibly;
`finish` concludes it silently. Protocol-invalid output performs no effect and
becomes bounded corrective context.

The main definition has a conversational output contract and forbids
`finish.result`. Recaller, rememberer, and dreamer are isolated one-shot runs
whose closed structured contracts forbid user-facing text and require a
schema-valid `finish.result`. They use no input checkpoint or saved session
reference; their plans are strictly non-effectful, and Jarvis commits their
result or recomputes the run.

The kernel does not classify authority. Jarvis freezes the `llm-tools` per-run
capability plan as a subset of the definition envelope and supplies a dispatch
port that returns `executed`, `pending_approval`, `denied`, `failed`, or
`uncertain`.
Jarvis derives two kernel run classes from existing message fields:
`interactive` for owner and action-resolution rows, bound to the full Main plan,
and `proactive-read` for scheduled-wake rows, bound to the external-read plan.
The checkpoint adapter exposes only a maximal contiguous same-class prefix; a
class mismatch or differently classified next row arms the correct run and
defers without a provider call or cross-plan consumption.
`pending_approval` and `uncertain` settle the proposing input with a
host-referenced waiting conclusion; Jarvis persists and later resolves the
product action through the existing ledger. An outcome that cannot return to a
still-live originating loop creates one idempotent host-authored waking message
keyed by action ID plus resolved state, not the original turn-local call ID.
Due scheduled wakes use a distinct idempotent host input rendered from immutable
action arguments. Neither input may be consumed silently: a missing model `say`
gets a deterministic host-rendered assistant fallback.

Jarvis supplies product-selected canonical context through the kernel
`ContextSourcePort`. `llm-tools` typed prompt sections render it without treating XML-like
markup as a security boundary. A continuation projection contains current
inputs and dynamic context; a bootstrap projection adds stable sections and
bounded canonical history. Provider-specific types appear only at the adapter
boundary. Provider session lifecycle remains implemented by `provider-runtime`;
the kernel only coordinates an opaque `SessionRefPort`, keyed by application
thread and immutable agent-definition fingerprint, with generation
compare-and-set. Jarvis stores the main session reference outside PostgreSQL and
gives memory roles fresh sessions. A valid response advances the reference
before canonical checkpoint settlement; if settlement is interrupted, the
still-unprocessed input causes recovery to discard the speculative reference
before replay. A stale compare-and-set stops before dispatch or settlement, and
each successful store advances the expected generation.

The kernel's `InputCheckpointPort` provides an exclusive drain claim, an ordered
waking-input snapshot and consumed watermark, atomic terminal
conclusion/checkpoint commit, and compare-and-set idle. If input arrives beyond the
consumed watermark while a drain attempts to become idle, the transition fails
and the drain continues only when the input has the same run class; otherwise
the adapter arms a correctly classified handoff. Jarvis implements this port
over its canonical message state and its single-process coordination; no
application table or column is added. Restart recovery still comes from null
`processed_at` rows. Read and protocol observations stay turn-local; effects
remain durable through `llm-tools` and Jarvis actions. The kernel's event sink
is optional best-effort observability, not a required canonical event store.

Checkpoint settlement returns `continue`, `idle`, or `deferred`. Same-class
later input may continue; different-class input or exhausted limits makes Jarvis
arm the correct next run before claim release and the kernel returns public
`pending_input`. Startup
scans null-`processed_at` inputs before becoming idle. One host-generated `as_of`
is captured per claimed input batch and remains unchanged through that batch's
tool loop; the batch itself is not repeated on later continuation calls.

V1 has no general subagent abstraction and no model-generated program runtime.
Recaller, rememberer, and dreamer are fixed Jarvis cognitive roles invoked
through the kernel's one-shot primitive, not delegated persistent agents.
Task-scoped delegation and CodeAct/Lua or another program-agent surface are separate future
experiments that require measured product need, explicit capability narrowing,
and their own ADRs.

## Consequences

Positive:

- Jarvis keeps one small product architecture while reusable agent-loop
  correctness has one implementation and conformance suite.
- A future stateless/API provider and lost native session use the same
  reconstruction boundary.
- Complete-step validation, budgets, cancellation, and idle races are tested
  independently of Discord and Google integrations.
- The existing four-table schema and approval/action design do not change.
- Other applications can reuse the kernel without inheriting Jarvis memory,
  policy, or UI.

Accepted costs:

- Jarvis gains another pinned dependency and release boundary before v1 ships.
- The port boundary needs careful fixtures so abstraction does not hide product
  transactions or provider failures.
- Provider-native compaction remains opaque, and a bootstrap restores useful
  semantic continuity rather than byte-identical reasoning history.
- The first consumer may not reveal every reusable interface; incompatible
  generalization waits for a second real consumer.

## Rejected alternatives

- **Keep the loop in Jarvis:** encourages duplicated orchestration and makes a
  later extraction harder without improving product behavior.
- **Copy Codapt2 wholesale:** imports workflow, state, discovery, and execution
  infrastructure that the v1 does not need.
- **Duplicate provider or tool layers:** conflicts with the deliberately
  authoritative `provider-runtime` and `llm-tools` libraries.
- **Put Jarvis policy in the kernel:** couples a reusable run loop to one
  product's approval and autonomy boundary.
- **Add persistent peer agents now:** Codapt2's peer mailbox lacks the narrowed
  task, lifetime, result, cancellation, and budget semantics a safe delegation
  facility would need.
- **Add `run(code)` or Lua now:** the small fixed tool catalog gets most of the
  benefit from batched structured calls without another parser, sandbox, replay,
  or approval boundary.

## Migration and acceptance

Implementation has not started, so there is no runtime or database migration.
Jarvis Slice 0 qualifies a pinned kernel revision alongside its existing
libraries. Slices 1 and 2 adopt its ports and conformance suite. A1.2, A1.3,
A1.5, A1.8, A2.10, A2.12, A2.13, A4.1, A4.5, A4.7, and A4.11 cover the boundary.
The existing-table action-resolution and scheduled-wake paths are covered by
A6.14 and A6.16.
