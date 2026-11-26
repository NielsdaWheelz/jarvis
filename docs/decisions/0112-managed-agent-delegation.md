# adr 0112 · managed agent delegation

the [worker tools](../../SPEC.md#73-tool-contracts-and-exact-catalog) use a
native assignment result. jarvis owns action identity, consent and reporting.
skid owns machine placement, the live terminal and unacknowledged results.
the provider owns model execution and saved history.

## contract

a short brief names the outcome, scope and evidence expected. `agent.delegate`
records it with an action uuid and origin. its observer submits the brief to
the enrolled machine and holds a result request by uuid. a follow-up names a
prior assignment in the same causal component and uses its live worker. a busy
worker refuses. the owner can steer or answer in that terminal. later ordinary
turns create no assignment result.

the observer pins the machine before the first put and enters the effect under
the canonical pause fence. a lost receipt triggers exact reconciliation on that
machine. a sealed response carries its disposition and exact bytes. one
transaction stores the outcome and publishes its wake. the ack can resume after
restart. the wake says what the worker found and what remains unverified. reports
over 8 kib link their exact `receipt.read` selection `worker_answer`. worker
content remains evidence within the original authority.

the action row holds the acceptance, submission and result. one held request
per outstanding result replaces terminal observation. the new-job path reads
the installed roster once to avoid retargeting a reused label. live terminal
metadata appears in its receipt as soon as the host supplies it. later result
publication wakes the original conversation once.

## cutover

drain unfinished worker actions and outbound wakes on the selected old release.
verify the exact paired skid cli, gateways, worker pin and matching jarvis
artifact. every profile on macbook, dev-server and arch must qualify before the
switch. activate together. the catalog includes `agent.delegate` and explicit
terminal inspection and controls. finalized earlier receipts stay opaque in the
original action rows. retain a stopped restore point for pre-cut state and
repair forward after new effects unless the recovery procedure accounts for
them. [operations](../operations.md)
