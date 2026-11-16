# adr 0076: role models and delegated choices

status: accepted target, 2026-11-16. owner refinement while specifying f3;
implementation, qualification and production activation remain separate.

[f3's implementation evidence](../subscription-model-runtime.md#implementation-evidence)
now qualifies source and a separate candidate, with installed skid v0.24.4 on
macbook/dev-server. production jarvis activation remains separate.

## decision

- main uses personal-subscription `gpt-6-astra/max` through `provider-runtime`.
- host-run compactor and dreamer use fixed `gpt-6.1-sol/xhigh` through that same
  subscription/library. they are not dynamically configured by main.
- main may choose supported models/efforts for native codex children and skid
  workers. these choices are independent of the host-role selections.
- extend skid start with per-session model/effort choices. profiles continue to
  own provider/account/executable defaults; no profile rewrite per task. explicit
  options take effect or fail clearly, never disappear into a default.

this supersedes adr 0075's shared main/memory selection and adr 0068's prohibition
on launch model/effort overrides. all other authority, terminal-only identity,
immutable arguments, one-entry writes and asynchronous observation contracts stay.
the [f3 contract](../subscription-model-runtime.md) owns exact interfaces, upstream
handoff and temporary acceptance; the [roadmap](../implementation-plan.md#v2-finishing-prs)
owns delivery. no implementation or installed success follows from this decision.

## mechanism and consequences

reuse the provider catalog/authentication and existing separate main/isolated
definition inputs. fixed role selections require exact actual catalog keys,
dispatch identities and effort values; no api-key generation route or downgrade.
worker choices use their native provider's supported identifiers/defaults, not
jarvis's fixed-role allowlist. existing embedding credentials are unaffected.

at decision time, the pinned provider/stock source included both host-role selections
and native child overrides, while actual personal-route support and useful
completion were unproved. installed skid lacked per-session override flags, so
that choice required a bounded upstream launch extension and jarvis adoption.
arbitrary shell profile commands cannot justify guessed flag injection.

main max and memory xhigh may increase latency/subscription usage; compaction can
delay foreground preparation. preserve actual role limits until evidence supports
an explicit amendment. retain one subscription's availability/quota dependency,
strict native protocols and original receipts. qualify useful delegated results,
not merely terminal creation or a model's claim about itself.

keep the owner-selected temporary integration/live red → green → refactor → delete
method, designer output review and independent adversarial review. f2 still owns
the native-progress defect and final assembled-product proof; stopped production
cutover remains separate.
