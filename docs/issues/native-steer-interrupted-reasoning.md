# stock leaves an interrupted reasoning item open

open. in an isolated macbook rehearsal, stock codex `0.171.0` started a
normalized reasoning item. a real steer sent a correlated responses websocket
interrupt. the loopback peer reported the reasoning item interrupted. stock
recorded the steer and completed a fresh final, with no completion for the
reasoning item. the original read and write evidence stayed recorded.

[adr 0106](../decisions/0106-interrupted-answers-and-parked-work.md) deliberately
fences this turn. a stranded non-display item gives the adapter insufficient
evidence to accept the final. in the synthetic journey the affected requests
parked for operator inspection. the incident log has no interrupted item id,
so this fixture does not establish an installed occurrence or frequency.

to reproduce, use the adr's websocket sequence with a reasoning item as the
open item, then inspect the app-server start, completion, and summary events.
the macbook qualification evidence begins with
`~/.local/state/jarvis/qualification/adr0106/a-work/provider-before-reasoning.json`.
closure requires a stock or adapter contract that proves exact reasoning
closure across interruption, and the original isolated replay preserving
input, callback, and effect fences while accepting the valid final.
