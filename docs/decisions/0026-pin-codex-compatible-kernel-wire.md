# ADR 0026: Pin the Codex-compatible kernel wire protocol

- Status: Accepted
- Date: 2026-09-03
- Supersedes: the exact `llm-agent-kernel` revision pinned by
  [ADR 0020](0020-pin-the-implemented-kernel-boundary.md); every other ADR 0020
  host-boundary decision remains accepted

## Context

The first paid Jarvis Slice 1 consumer probe reached the Codex backend with the
kernel's original Pydantic-generated discriminated-union schema. Both
`gpt-5.6-terra` and `gpt-5.4` rejected it before generation with HTTP 400
`invalid_json_schema`. Jarvis failed closed, consumed each probe input once with
a host-authored provider-error conclusion, and persisted no session reference.

The original provider schema had several incompatibilities, not merely the
first reported missing `required` member: its root was a union, optional
properties were not all required, and arbitrary JSON objects used schema-valued
`additionalProperties`. The
[official Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
requires an object root, every declared property to be required, and closed
objects with `additionalProperties: false`.

The kernel repository corrected the complete boundary and published
`c9eefcb458ee5245010dd5e99b48f7116cd1139a`, exactly one commit after ADR 0020's
pin. Public `main`, an independent HTTPS `ls-remote`, and a fresh bare fetch all
resolved to that revision. Its dependency revisions for `provider-runtime` and
`llm-tools` are unchanged.

## Decision

Pin Jarvis to `llm-agent-kernel` revision
`c9eefcb458ee5245010dd5e99b48f7116cd1139a`.

The logical `say | call_tool | finish` protocol remains unchanged. The kernel
alone projects it into a provider-wire envelope with the required fields
`type`, `say`, `call_tool`, and `finish`. Exactly the selected payload is a
closed object; the others are null. Optional logical values are explicit
nullable wire values.

The selected `call_tool.arguments` wire member is a string encoding one strict
JSON object. The kernel rejects duplicate keys, non-JSON constants, non-object
roots, malformed branch combinations, and invalid logical/tool arguments before
dispatch. Jarvis neither handles this encoding nor weakens the existing
independent semantic and `llm-tools` validation.

Structured result contracts compile into the Codex-supported closed schema
subset during immutable definition construction. An unsupported contract raises
`UnsupportedStructuredOutputError` before provider I/O. Variable-key result
data uses an array of closed key/value records rather than an arbitrary mapping.

The kernel exposes `provider_wire_schema`, `validate_provider_step`,
`StructuredOutput.wire_schema`, and `UnsupportedStructuredOutputError`.
`model_step_schema` remains as a compatibility name for the provider-wire
schema, while existing logical step classes and `validate_model_step` remain.
Jarvis normally consumes the higher-level run API and does not call these wire
helpers itself.

The kernel directly pins its certified `openai-codex==0.144.4` SDK. Jarvis's
lock and startup compatibility check must resolve that exact version. Any SDK
upgrade requires explicit provider-runtime and kernel requalification.

## Evidence

The corrected revision reported:

```text
unit/conformance                         165 passed, 5 deselected
gpt-5.6-terra paid provider probes      3 passed, 2 account-state skips
gpt-5.4 paid provider probes             3 passed, 2 account-state skips
pyright                                 0 errors, 0 warnings
ruff format and lint                    passed
wheel and sdist                         built
pip-audit                               no known PyPI vulnerabilities
```

The two skips are deliberately account-state-dependent exhausted-quota and
in-flight-cancellation probes, not provider-wire coverage gaps.

## Consequences

Benefits:

- The strict provider schema is accepted live by both qualified model routes.
- Provider transport constraints do not leak into Jarvis's logical step types.
- Unsupported structured contracts fail before a paid call.
- Containment, native-tool disablement, frozen plans, serial dispatch, session
  CAS, and recovery semantics are unchanged.

Accepted costs:

- The nullable envelope consumes additional output tokens.
- Tool argument structure is enforced after strict JSON-string decoding rather
  than natively inside the provider schema. Independent host validation remains
  authoritative and precedes dispatch.
- Arbitrary result mappings are unavailable; arrays of closed records are more
  verbose.
- The direct SDK pin makes upgrades deliberate and requires requalification.

## Migration and acceptance

Jarvis has no runtime, lockfile, checked-in compatibility manifest, or saved
provider session yet, so there is no deployed state migration. Slice 1 creates
its initial lock and compatibility manifest with the new kernel revision. Any
discarded experimental terminal fixture must emit the nullable envelope, with
tool arguments encoded as the strict JSON-object string expected by the kernel.

The affected criteria are A1.2, A1.5, A1.8, A2.10, A4.1, A4.4–A4.7, and the
three paid Slice 1 consumer probes. The signed Slice 0 report remains immutable
historical evidence for the revision it qualified; Slice 1 records this live
failure and the superseding pass in its own qualification evidence.
