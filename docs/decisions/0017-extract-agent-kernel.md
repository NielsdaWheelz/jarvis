# ADR 0017: Extract the reusable bounded agent kernel

- Status: Accepted; corrected provider/loop/admission contract incorporated on
  2026-09-02 and durable Jarvis mapping recorded by
  [ADR 0018](0018-serial-kernel-and-bounded-recovery.md); final dispatch and
  admission seams amended by
  [ADR 0019](0019-ground-writes-and-close-recovery-seams.md)
- Date: 2026-09-01
- Amends: [ADR 0004](0004-python-codex-and-tool-kernel.md),
  [ADR 0007](0007-central-messages-and-unified-actions.md), and
  [ADR 0012](0012-resumable-session-and-context.md)
- Clarifies: [ADR 0006](0006-no-workflow-framework.md)

## Context

Jarvis needs strict structured steps, provider-neutral reconstruction, bounded
model/tool loops, session-reference handling, steering, cancellation, and safe
settlement. Those mechanisms recur outside a personal assistant.

Codapt2 supplied useful prior art: validate a whole step before effects, keep
canonical input independent of provider transcripts, poll ordered input inside
the loop, use one claim owner, and test crash boundaries. Its TypeScript/Effect/
PostgreSQL workflow substrate, product projections, peers, discovery, and Lua VM
do not belong in Jarvis v1.

The first extracted spec got the interior right but described seams the pinned
libraries did not have, allowed unsafe multi-call/parallel behavior, and bounded
only one run while cleanup could start unlimited successors. Those errors are
corrected and seam-hardened in kernel commit
`049bc9221860d6fc5310f21ad560a9ec39371add`.

## Decision

Jarvis consumes the independent Python 3.12 `llm-agent-kernel` distribution at
an immutable revision:

```text
Jarvis
  -> llm-agent-kernel
       -> provider-runtime AgentRuntime
       -> llm-tools
```

Ownership is:

| Owner | Responsibilities |
| --- | --- |
| `provider-runtime` | Native Codex authentication; `AgentRuntime` open/run/close; `PermissionPolicy`; native options; structured output; events, usage, quota, and session refs |
| `llm-tools` | Prompt sections; declarations/bindings; frozen profiles/plans; `HostTable`; pure validation; `ToolEffect`/`ReplayPolicy`; tool budgets; positions, recorder, execution, and results |
| `llm-agent-kernel` | Immutable definitions/fingerprints; containment and plan-tightening enforcement; `say | call_tool | finish`; semantic whole-step validation; serial loop; mid-loop polling; session/checkpoint/admission choreography; one-shots; outcomes and conformance |
| Jarvis | Product context; input/plan selection; canonical messages/memory; session-ref/checkpoint/admission/dispatch adapters; Discord/connectors; policy; action/effect identity and recorder implementation; reconciliation; scheduling and delivery |

V1 uses only subscription-backed
`provider_runtime.agent_runtime.AgentRuntime`. Jarvis application tools are
neither provider-native nor MCP tools. The native child has a private empty
read-only cwd, disabled network/environment/MCP/built-ins/Web, and approval deny.
Any native tool-use or permission-request event fails and discards the session.

The exact model grammar is one closed value:

```text
say(text)
call_tool(canonical tool ID, arguments)
finish(optional reason, output-contract result)
```

The model supplies no call ID, effect ID, preview, or authority. Exactly one
tool runs serially per step after independent whole-step, output-contract, plan,
and pure argument validation. A completed bounded result returns to a later
model turn. A durable host suspension releases resources and later resumes
product work through an action-resolution input containing original call
evidence.

The main definition is continuing and conversational. Recaller, rememberer, and
dreamer are isolated structured one-shots with no `Write` plan, checkpoint, or
saved ref. ADR 0019 adds a fourth isolated, empty-plan AutomaticWriteGate role.
Sessions are disposable; Jarvis stores generation-CAS refs outside PostgreSQL
and cold-bootstraps from canonical context.

The host claim returns one non-empty bounded batch and its chosen frozen plan.
The kernel has no run class. Jarvis prioritizes owner/action-resolution work with
the full Main plan; scheduled wakes run separately with a read-only plan.
Compatible owner input can append mid-loop. Stop/pause preempts. Ordinary input
racing finalization gets the prior valid answer and a later run.

`settle` atomically records conclusion plus `processed_at`. `release` never
arms. Deterministic poison exits consume the input with a host-authored stopped
conclusion. Crashes are bounded by `message.processing_attempts`; every provider
run also requires rolling admission. Writes map `action.id` to both
`InvocationPosition` and `EffectId` with durable action state.

Before implementation, `llm-tools` must expose and qualify public pure
validation, profile tightening, `HostTable` publication, and async durable
recorder/executor seams. The kernel and Jarvis may not replace them privately.

## Consequences

Benefits:

- Reusable run correctness has one truthful API and multi-run conformance suite.
- Codex session reuse remains valuable without becoming canonical.
- One serial call removes partial outcome vectors and parallel uncertainty.
- Provider work is bounded across crashes and fresh runs.

Costs:

- Jarvis gains another pinned dependency and must first upgrade `llm-tools`.
- Serial reads can take longer.
- V1 has typing state but no model-authored progress narration.
- Recaller/rememberer/dreamer open a native subprocess/session per invocation.
- A valid answer is retained when ordinary input races finalization rather than
  being regenerated with the new message.

## Rejected alternatives

- Keep the loop in Jarvis: duplicates subtle provider/effect/recovery seams.
- Copy Codapt2 wholesale: imports unneeded workflow and product machinery.
- Union stateless generation and AgentRuntime behind an imaginary port: matches
  neither dependency lifecycle.
- Multi-call or parallel dispatch: requires durable partial outcome vectors and
  not-initiated states v1 does not need.
- Kernel run classes: priority and compatibility are host product policy.
- Automatic rearm after cancellation/exhaustion: renews fresh provider budgets
  indefinitely.
- Put Jarvis policy in the kernel: couples reusable control flow to one product.

## Migration and acceptance

Implementation has not started. Slice 0 upgrades `llm-tools`, pins all three
libraries, and qualifies exact public APIs before Slice 1. Jarvis adds the three
columns authorized by ADR 0018 but no fifth application table. Acceptance A1.2,
A1.5, A1.9, A2.10–A2.13, A4.1, A4.4–A4.12, A6.10–A6.15, and A7.8–A7.10 cover
the corrected boundary.
