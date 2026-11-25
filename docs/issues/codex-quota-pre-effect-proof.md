# stock codex does not prove pre-effect quota failure

stock `0.171.0` failures report `itemsView=notLoaded` and an empty `items` array, including failures after native activity. native subagent spawn can launch a child before the parent emits its typed activity item. a missing effect observation cannot be distinguished from no activity by the public failed seal. [failed seal](https://github.com/openai/codex/blob/rust-v0.171.0/codex-rs/app-server/src/bespoke_event_handling.rs#L1421-L1424) · [native spawn](https://github.com/openai/codex/blob/rust-v0.171.0/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs#L124-L174)

adr 0108's conservative branch parks accepted main turns affected by a quota-shaped failure when effects are uncertain. the existing never-written evidence can still qualify a bounded fresh opening. there is no new terminal proof field with stock `0.171.0`.

closure requires a pinned stock contract proving completeness for every granted effect-capable path. exercise genuine early refusal and controlled failure after shell, callbacks, child dispatch and pending steer. missing effect evidence must be rejected. only then add and qualify the authenticated seal tag. [adr 0108](../decisions/0108-codex-quota-standby.md)
