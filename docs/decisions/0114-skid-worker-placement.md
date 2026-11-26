# adr 0114 · skid worker placement

accepted design, 2026-11-25. the target binding is `jarvis-agent-control-v14`.
at 21:44 pacific the mac's skid v0.31.0 (`334626e`) listed `desktop` alongside
`macbook`, `dev-server` and `arch`. the dev-server release pointer selected
the four-name v13 build (`00f579e`), based on managed delegation v12
(`0584972`). these reads establish the planning baseline. the installed v14
check will exercise the jarvis service account and an actual assignment.

## ownership

skid owns enrolled computers, their names, authenticated routes and applied
launch profiles. jarvis owns the owner's request, permission to act, the
selected destination and the resulting receipt. enrollment makes a computer
discoverable. each write still needs authority for that particular action.
this decision adds no placement bans. a future restriction such as keeping
development work off production belongs at jarvis write admission and must
apply to the captured identity. shared-memory enrollment has its own grant.

this supersedes the personal machine enum retained by [0068](0068-generalized-skid-consumer.md)
and [0072](0072-native-memory-rollout.md), the four-name rule in
[0113](0113-desktop-worker.md), and observer-time placement in
[0112](0112-managed-agent-delegation.md).
in a decoder fixture, two healthy peers remained present throughout. v12
rejected the inventory when an offline fourth peer appeared. v13 accepted
that peer and rejected the inventory when an offline fifth peer appeared.
in both versions a fresh assignment can return `accepted` with only its
label recorded. the observer repeats unsuccessful name lookups. enrolling
a new computer under that label can therefore activate an older request.

## discovery and admission

`agent.list` projects every peer skid reports within the existing inventory
bound, including unavailable peers and their errors. filtered list, info,
read, start, delegate, terminal targets and public receipts accept skid
computer names. names are case-sensitive selectors at lookup. preserve spelling,
interior spaces and unicode. use skid's name grammar and its existing transport
bounds. keep closed reply shapes, identity validation and partial-result
checks. profile choices come from the selected computer's applied config.
skid evaluates launch capability at dispatch and reports refusals.

for a fresh `agent.delegate(machine, …)` or `agent.start`, require a live
request and resolve the supplied name once against the service account's
local `skid status --json` snapshot. use the existing applications-to-members
join by device id. require one exact name match joined to one enrolled
computer whose handle is `mh-` followed by 32 lowercase hex digits.
the roster identifies a computer even when its gateway is asleep.

| lookup outcome | result before any worker action is inserted |
| --- | --- |
| one enrolled computer | capture its machine handle with the action under the normal write gate |
| no matching name in a valid snapshot | return `machine_unknown` for the requested name |
| two or more enrolled computers match that name | return `machine_ambiguous` for the requested name |
| roster unreadable, malformed or missing a required join | return `roster_unavailable` |

all three lookup failures have zero dispatches and leave no queued assignment.
a fresh request can try again. returning an existing action or replaying its
receipt uses its original capture, even when the roster is unavailable.

## execution

store the machine handle once in the action's immutable private execution
contract before insertion. keep the original model arguments, label and digest.
the existing action row owns the capture. a public `accepted` receipt means
that a specific destination and job id are durable. after commit, a crash
before receipt delivery recovers the same action. public receipts keep
human-readable names and terminal handles. machine ids and opaque refs are
private routing evidence.

- **assignment.** register and submit from the capture. every submit, result
  page and ack uses the same action uuid and machine handle. an eligible
  `after` inherits the prior assignment's handle and worker. before insertion,
  require the prior job's origin to belong to the current request's causal
  component, as `receipt.read` already does. an unrelated or unpinned job
  returns `job_not_found` with zero dispatches. a busy or departed worker
  gets its skid outcome. [current registration gap](../issues/worker-follow-up-scope.md)
  removal, rename, an unreachable gateway or a change of profile never selects
  a replacement. preserve pause and current ownership at effect entry.
  reconcile an uncertain submission on its original host. only authoritative
  job absence there permits the existing idempotent resubmit. retain the
  exact answer, one committed wake and any outstanding acknowledgement.
  permanent loss of that handle can leave a previously entered job or its ack
  unresolved and hold a later incompatible cut. retain the obligation for
  reconciliation under the owning release.
- **terminal creation.** add `skid start --machine-id HANDLE` to the cli.
  it accepts only a canonical handle and is mutually exclusive with
  `--machine LABEL`. keep label lookup literal, including for a label that
  happens to look like a handle. the id path uses the existing membership
  lookup and authenticated gateway route. a missing handle fails before
  dispatch. jarvis uses the id path exclusively for accepted starts. validate
  the returned machine against the capture. a rename may change the returned
  label. use the observed label in a newly returned terminal target. a wrong-id
  or lost reply after entry is uncertain under the existing one-shot start
  policy. never issue a second start to reconstruct a receipt.
- **terminal controls.** info and read are fresh observations. send, text,
  keys, stop and close capture the selected terminal's opaque ref at admission
  and execute by that ref. a terminal handle identifies its session lifetime.
  a stored label in an old receipt is historical. fresh inventory can supply
  the current label for an explicit control after a rename.

## compatibility and deployment

extend v13's retirement and receipt handling to cover its own records.
stopped preflight and startup both block incompatible pending actions and completed delegations with
`ack_pending`. settle those obligations and outstanding wakes on their owning
release. preserve finalized v12 and v13 receipts, public terminal handles, bounded
previews and the exact `worker_answer` bytes under the original action id.
keep private refs out of historical public replies. use the stored capture
for eligible historical follow-ups. for v12 and v13 the capture is in the
registered result's `machine_id`. v14 reads its immutable contract. older
opaque archives keep their existing reader. historical reads use only stored
evidence. the existing jsonb columns hold the new contract.

the deployment verifier requires one healthy `macbook` and one healthy
`dev-server` for this installation. check the existing service containment,
reply shape, partial flag and exit status. report each additional peer's
observed status. optional peer outages do not fail the check. a missing
required peer, a failed required peer or malformed inventory still fails
it. desktop enrollment and subsequent fleet changes are ordinary skid
operations once the pair is active. [delivery and proof](../implementation-plan.md#skid-worker-placement)
