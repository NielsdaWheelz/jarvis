# ADR 0028: Qualify current ChatGPT local-account models

- Status: Accepted
- Date: 2026-09-04
- Supersedes: ADR 0026's requirement and conclusion that both `gpt-5.6-terra`
  and `gpt-5.4` are current qualified local-account routes; ADR 0026's wire,
  schema, and SDK decisions remain accepted
- Amends: SPEC sections 7.1 and 8, the compatibility manifest, acceptance A4,
  and the Slice 1/Slice 2 qualification gates
- Owner approval: the owner approved the single current route, early retired-
  model rejection, and model-count-independent qualification rule on 2026-09-04

## Context

ADR 0026 qualified `gpt-5.6-terra` and `gpt-5.4` through the personal
ChatGPT-backed `local_account` credential on 2026-09-03. That evidence remains
true for its time and exact dependency revision. Provider availability then
changed.

OpenAI's official Codex changelog entry published on 2026-07-31 says that
`gpt-5.4` and `gpt-5.4 mini` retire from ChatGPT-authenticated Codex on
2026-08-31, recommends replacing `gpt-5.4` with `gpt-5.6-terra`, and explicitly
distinguishes API/API-key availability from the ChatGPT-account path:
[GPT-5.4 and GPT-5.4 mini retire from Codex on August 31](https://learn.chatgpt.com/docs/changelog#codex-2026-07-31).
Jarvis intentionally has no generative API-key path, so continued API
availability does not make `gpt-5.4` a valid Jarvis route.

The exact final Slice 2 dependency set exposed the retirement before release.
Three fresh paid `gpt-5.4` attempts used empty disposable databases, unused
private runtime directories, and the required `local_account` profile. Each
attempt reached one provider turn and terminated as
`AgentFailure("backend_failed")` with usage `Absent`. The admission port retained
the complete 432,768-input-token and 48,192-output-token reservation; no session
reference was stored. The sanitized provider diagnostic was HTTP 400
`invalid_request_error`: `gpt-5.4` is not supported when Codex uses a ChatGPT
account. No action or memory row was created. This is retained negative
historical evidence, not a passing route probe.

Requiring exactly two routes would now either make the release permanently
impossible or pressure Jarvis toward an API-key/provider fallback forbidden by
the specification. Requiring exactly one route forever would encode the same
mistake in the opposite direction.

## Decision

The compatibility manifest records the complete ordered set of exact qualified
ChatGPT-local-account model IDs. Its schema becomes
`jarvis-session-compatibility.v2`, and the current set is:

```json
{"qualified_models":["gpt-5.6-terra"]}
```

Jarvis configuration accepts only an exact member of that set. The current
implementation therefore accepts `gpt-5.6-terra` and rejects `gpt-5.4` during
configuration, before message ingress, rolling admission, provider I/O, or tool
I/O. Definition builders independently enforce the same boundary for direct
library callers.

The set has no permanent cardinality. Adding, replacing, or removing a model
requires an explicit manifest/code/documentation change, a conservative
provider-context bound, deterministic configuration and definition tests, and
paid consumer qualification against the exact release code and dependency
lock. Every recorded model must be probed, and at least one exact model that the
provider currently supports through ChatGPT `local_account` authentication must
pass. A retired route is removed rather than counted as an expected failure.

Qualified-model membership does not enter
`session_compatibility_revision`. That revision continues to cover the owner-
controlled application/role session contract and exact dependency pins. The
selected model already participates in the immutable agent-definition
fingerprint, so a future model change cold-bootstraps automatically. Removing
an unselected retired route does not invalidate an otherwise compatible
`gpt-5.6-terra` session. This amendment therefore does not bump
`application_session_contract_revision`, recompose frozen plans or HostTables,
or change the exact compatibility hash.

No dependency pin, provider/runtime/kernel/tool behavior, admission accounting,
database schema, authority rule, replay rule, or recovery rule changes.

## Consequences

Benefits:

- Unsupported model configuration fails before owner input or paid provider
  work.
- Release qualification follows current provider reality without weakening the
  local-account-only boundary.
- The manifest makes the exact supported set inspectable while permitting a
  future evidence-backed one-to-many or many-to-one route change.
- Existing compatible Terra sessions do not cold-bootstrap merely because an
  unavailable alternative was removed.

Accepted costs:

- V1 currently has one model route, so a Terra retirement or account-specific
  outage has no model fallback. Startup must remain closed until a replacement
  route is explicitly qualified.
- Model availability is external mutable state. Exact dependency pins cannot
  guarantee that a previously qualified ChatGPT route remains available.
- Manifest schema v2 adds one required field even though the session-
  compatibility digest deliberately excludes it.

## Rejected alternatives

- Fall back to an OpenAI API key: violates the subscription-backed local-account
  product boundary and changes credential ownership and billing.
- Keep `gpt-5.4` configured and interpret HTTP 400 as an ordinary provider
  outage: admits owner work and paid capacity for a deterministic configuration
  defect.
- Permanently require exactly one or two routes: confuses a point-in-time
  provider catalog with a product invariant.
- Rotate `session_compatibility_revision`: duplicates model identity already in
  the definition fingerprint and unnecessarily discards compatible Terra
  sessions.

## Migration and acceptance

There is no database migration, action drain, dependency update, plan/HostTable
recomposition, or manual session-reference deletion. Existing deployment
configuration must name `gpt-5.6-terra`; a retired value fails startup.

Historical Slice 0 and Slice 1 qualification reports remain byte-identical.
ADR 0026 remains the immutable record of its earlier live two-route result; the
three exact-final `gpt-5.4` failures above record why that route is no longer in
the current manifest. Slice 2 must record a passing exact-final Terra consumer
qualification and the deterministic retired-route rejection before it can ship.

This decision affects A1.8, A2.10, A4.1, A4.4, A4.7, and adds A4.14.
