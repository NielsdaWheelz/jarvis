# delegated follow-through — o9

status: owner direction settled, 2026-10-06; docs only. supersedes the proposed
work-linked execution/fencing design. adopt with [o6](one-main-events.md) in
spec/an adr superseding affected adr 0065 chat-stop rules before implementation.
the [roadmap](implementation-plan.md#o9-continuation-and-coordination) owns sequencing.

## target and boundaries

jarvis is one agent with tools. every admitted event starts or steers the same
main with the same capabilities: owner message, worker result, action outcome,
scheduled wake, or a later source such as email. origin supplies context and
provenance; jarvis decides what to do, including nothing.

jarvis chooses priorities, direct work, delegation, worker reuse, coordination,
fanout, observation, follow-ups and integration. todo states inform judgment;
they neither authorize nor prevent execution. no work links, eligibility flags,
controller, worker graph, new table, model role or tool schema.

[o5/adr 0065](decisions/0065-native-agent-supervision.md) owns native continuity;
o6 owns equal event capability/visibility; [o7](work-records.md) owns optional
bookkeeping; [o8](worker-launch-observation.md) owns workers/observation. reuse
those contracts. email ingress, recurrence, memory and deployment redesign stay
with their existing owners.

## behavior and existing api

- substantial work normally gets one coordinator; simple work may use a worker
  or main directly. research/inspection count. jarvis chooses the method.
  existing preferences: `gpt-6-astra`/`xhigh` for coordination,
  `gpt-6-sol`/`xhigh` for individual work; preferences, not enforced assignments.
- use existing `agent.*` tools and freeform conversation. inspect when useful,
  register bounded `agent.wait` when observation helps, integrate later evidence
  and choose the next useful action. no mandatory procedure or report packet.
- use `work.*` to retain useful outcomes, next steps, blockers and references.
  one record per useful owner outcome, not per specialist. record updates are
  bookkeeping. choose finite `schedule.wake` follow-ups when useful under o6.
- submission, dispatched bytes and idle/done worker state do not prove the owner
  outcome. evaluate evidence before reporting success or marking a todo done.
- `stop`, including scope expressed in ordinary language, is normal owner input.
  honor the latest owner intent across later events and fresh threads. main
  interprets scope, chooses existing interruption/wait/schedule/record actions,
  and dispositions requests through the existing native output. no automatic
  work cancellation or hidden stop marker follows from the word.

schemas stay `ActionRequest`, short `{machine,handle}` targets with existing private
capture, original wait/schedule receipts, o7 records and `JarvisNativeMessage`/`InputOutcome`. every origin uses
o6's full frozen main plan and ordinary dispatch. work can proceed without a todo.
retain exact connector Approve/Deny, trusted worker independence, deployment
ownership, protocol validation and original effect/read recovery. fresh events
do not acquire reduced grants from a historical conversational stop.

## designer's content contract

briefs state outcome, relevant context, actual scope and useful evidence; leave
procedure to the worker. progress adds a finding, changed direction or blocker.
results identify the outcome, supporting evidence and material limits. requested
results/blockers need notice; routine observations follow o6's quiet policy.

brief: `inspect the expired-session failure. explain the cause and responsible layer; no code changes. include evidence; use helpers if useful.`

result: `the coordinator reports its integration check passed. i checked the redirect change; production behavior remains unverified.`

stop result: `i sent the coordinator an interruption. its latest state is unavailable, so i cannot confirm it stopped.`

judge factual support, relevance and usefulness, not exact wording. no mandatory
template, independent recheck of every claim or runtime critic.

## implementation boundaries and cutover

| unit | exclusive files / responsibility |
| --- | --- |
| content/composition | `src/jarvis/definitions.py`, `src/jarvis/session-compatibility.json`: merge this behavior into the one main prompt; remove contradictory rules |
| conversational stop | `src/jarvis/discord.py`, `service.py`, `messages.py`: retire `Control.STOP` interception/normalization/cancellation/acknowledgment; preserve original text through normal ingress/steering |
| temporary proofs | scoped proof files only: end-to-end/live behavior and designer review |

use one writer per shared file when integrating o6/o9.
keep existing administrative pause/resume controls for deployment operation;
they are outside this conversational-stop change. remove unreachable stop-specific
new-control handling; historical controls/receipts remain evidence. no fallback
keyword route, work controller or duplicate continuation loop. o6 removes origin
restrictions; do not implement another authority policy in o9.

adopt the reconciled o6/o9 contracts together, rotate affected main/session
revisions, then use the existing stopped release cutover. canonical requests,
original receipts and entered-effect recovery survive; no worker protocol upgrade.

## acceptance and costs

reuse o6/o8 proof for equal plans, transport and receipts. temporary red checks
show exact chat `stop` bypasses main today. green uses real postgres/native
composition to prove its original text reaches main, including during a pending
worker observation, without word-triggered cancellation or fabricated completion.

live contained-main/installed-worker/discord journeys prove: useful delegation
from owner and non-owner events; unrelated input remains responsive; later
observations integrate and prompt useful continuation/bookkeeping when useful;
valid do-nothing/silent choices on ambient events pass. ordinary stop
is interpreted and actual interruption evidence is reported. include a restart
with original receipts and latest owner intent, without repeated unknown effects.
designer reviews briefs/progress/results. avoid requalifying o8's whole transport.

record red, get green, adversarially review boundaries/content, refactor actual
duplication, recheck changed concerns/final journeys, then delete temporary tests
and run `scripts/verify`. no code or behavioral/live execution in this doc task.

cost: stopping depends on main responding, interpreting correctly and its tools
working; it is not an out-of-band fence. interrupting a coordinator proves no
descendant cancellation or reversal of effects. the current catalog cannot cancel
generic pending approvals: owner Deny remains available; do not claim stop prose
cancelled them. bookkeeping is not a durable execution stop. temporary test
deletion leaves less retained regression coverage.
