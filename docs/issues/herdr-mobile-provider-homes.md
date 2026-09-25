# herdr worker provider-home cutover

problem: jarvis's four worker profiles now name private herdr interactive homes,
but source and static checks cannot establish that those homes are configured,
authenticated, trusted, and selected by the host shell and ssh gate on all three
machines.

impact: `agent.start` may be refused by the gate or may start a provider under
the wrong account. changing the profile map also changes every agent binding's
serialized policy inputs; pending incompatible agent actions must be settled or
explicitly resolved before activation, never replayed under the new mapping.

source evidence: `src/jarvis/agent_tools.py` selects the four
`~/.local/share/herdr/providers/` leaves; `agent_control.py` joins each leaf to
the configured owner home. dev-server's `assets/herdr/herdr-gate` admits those
four paths and the separate `claude-personal` shell default. `scripts/verify`
passes static and build checks. no provider calls, service changes, or live
worker launches were made in this source change.

resolved when the coordinated cutover proves, on macbook, devbox, and arch,
that all four jarvis profiles launch under their intended private homes,
the fifth personal-claude shell default stays herdr-owned, and cognition homes
and action accounting remain intact. check launches from ordinary shells and
from the opposite product's shell in `$HOME` and a shared project. record any
missing login or trust as a prerequisite rather than a passing launch.
