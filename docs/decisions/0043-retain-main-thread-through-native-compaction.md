# ADR 0043: Retain Main's thread through native compaction

- Status: Accepted
- Date: 2026-09-10
- Clarifies: [0012](0012-resumable-session-and-context.md) and
  [0020](0020-pin-the-implemented-kernel-boundary.md)

## Evidence

The owner explicitly requires Jarvis to reuse its Main thread and let Codex
compact it. Current Main's context allowances made the host's age calculation
return one. The reference adapter then hid every saved reference after its first
successful provider step. Generation counts compare-and-set writes, not owner
requests or context occupancy. This contradicted ADR 0012 and acceptance A2.10.

The paid consumer qualifier also retained a conversational `say` definition
after Main's structured-terminal cutover. Its first native response succeeded,
but the current checkpoint correctly rejected the obsolete conclusion. The
failed qualification remains historical evidence, not a production success.

## Decision

Keep one compatible Main thread across owner requests and ordinary restarts.
Remove age-based rotation and its dead configuration. Generation remains only
the existing compare-and-set concurrency token. Add no usage ledger, estimated
context counter, compaction scheduler, or manual compaction capability.

Codex owns native context sizing and automatic compaction. Compaction retains
thread identity and grants no execution authority. The provider adapter owns
normalization of native usage reports; estimated context size is not token
consumption, while actual compaction usage remains chargeable.

Retain static instruction/schema bounds, per-run context/output/elapsed limits,
rolling admission, containment, role isolation, definition fingerprints, and
speculative-reference discard before original-input recovery. A missing,
incompatible, unusable, or recovery-discarded session uses the existing canonical
bootstrap. Corrupt host reference state remains a configuration defect. No
unknown model decision or external effect is retried merely to recover a thread.

## Trade-offs

- There is no host guarantee that retained native history plus the next maximum
  input fits before submission. Native 0.154 compacts before inserting the next
  input; an unusually large continuation can exceed its context window and fail.
  Existing bounded failure handling remains authoritative; no silent retry or
  per-request limit increase is added.
- Native compaction is opaque, may lose detail, and may incur provider work.
  Canonical messages and memory remain the recovery source. Thread reuse does
  not promise a cache hit, latency, or token-cost reduction.
- Native drift remains an explicit availability risk under ADR 0042. A provider
  decoder must accept documented compaction reports without relaxing validation
  of actual cumulative billing counters or authority events.

## Cutover and proofs

The private reference shape and six application tables do not change. Removing
the age test does not require deleting a healthy reference. Any separately
changed dependency fingerprint takes the ordinary cold bootstrap; canonical
records and native history remain intact.

One adapter proof owns same-thread continuation across fresh runtime bundles,
CAS collisions, mismatch, and recovery. The paid consumer gate uses current
structured Main, real PostgreSQL checkpoint/decision/history ports, and an empty
tool-plan tightening: three owner inputs retain one native identity, followed
by deliberate reference loss and canonical reconstruction. It does not claim
the full memory-enabled service journey. Existing isolated structured and
JSON-string tool-argument probes remain separate.

The provider's external-protocol proof owns compaction usage normalization;
native automatic-compaction qualification must separately observe unchanged
thread identity. Missing live evidence is NOT_RUN, never a pass. A2.10 and A4.14
retain their reuse and paid-qualification requirements.

Activation also requires the corrected provider revision propagated through the
kernel and Jarvis's exact Git locks. Source worktrees and deterministic proofs
alone are not an integrated or live-qualified release.
