# codex standby live enrollment and installed acceptance

on november 25, 2026 the owner kept live enrollment in scope and chose to correct enrollment for all three accounts. the included-only billing requirement still applies.

stock `0.171.0` observe-only reads on `dev-server` at 09:36 utc returned three distinct authenticated subjects. `personal` and `work` returned the exact included-limit denial with zero usable credits. `work2` reported ordinary allowance and usable purchased credits, so it is ineligible under included-only. later reads at 16:15 and 16:17 utc confirmed allowance, billing and subject separation. the macbook login called `personal` shared `work2`'s subject. no generation was started. private readback hashes are `3559cd364c2046d870351a3a6450170b547bac80b93fc151cf2274080b001e9f` for server allowance, `7ea704277282da9b5892618f13b52954306c0e7fd5629a7bda3be93c9c7c6329` for server subject comparison, and `841d863279f9c69e03ef9fa612c52e40c7d51de3da10abfe635a80f63034b7e7` for the macbook subject comparison.

closure requires three eligible accounts, live contained ordinary turns with exact role and account proof, and a separately authorized named production cut. verify one ordinary owner turn and inspect pending or parked requests under the original receipt rules. [adr 0108](../decisions/0108-codex-quota-standby.md)
