# skid follow-through — o9 / slice 3

status: specified 2026-11-15 under [adr 0071](decisions/0071-simple-event-driven-v2.md).
audited predecessor: merged `31f3dd9`; slices 1–2 are source-qualified. worker v10,
full-plan events, conversational stop and todos already exist. this slice qualifies
their composition and repairs demonstrated defects; it adds no orchestration layer.
[the roadmap](implementation-plan.md#v2-reviewable-pr-slices) owns sequence.

## goal, scope and final state

jarvis delegates useful work, remains responsive, receives a later observation and
chooses the next useful action without another owner message. the same main handles
owner input, worker outcomes and scheduled todos. todo state is context, not authority.
main may reuse a worker, coordinate/fan out, continue directly, inspect, ask, report
or do nothing. a coordinator is useful for substantial work, never mandatory.

owner decision: qualify a temporary candidate against the real installed skid
fleet now; production acceptance stays at final v2 cutover. do not restore
`deploy/activate-release`, migrate production, convert live reminders or change
its selected release/control state in this slice. the final state is qualified
candidate behavior, bounded repair diffs if needed, and an explicit production
handoff. production follow-through remains unproved until that handoff passes.

reuse [o6](one-main-events.md), [o7](work-records.md) and
[o8](worker-launch-observation.md). no new table, column, migration, tool, role,
callback endpoint, scheduler, worker registry/graph, job-result packet, task link,
notification component or consent framework. private repo/files, attachments,
email/calendar ingress, memory changes and production activation keep their own
owners. offline arch and untested profile combinations remain explicit deferrals.

## capability contract and existing schemas

[o8](worker-launch-observation.md#capability-and-api), [spec §7.3](../SPEC.md#73-tool-contracts-and-exact-catalog)
and `src/jarvis/agent_tools.py` own exact closed schemas. preserve these surfaces:

| operation | existing input / meaning |
| --- | --- |
| `agent.list`, `agent.info`, `agent.read` | inventory filters; short target; bounded retained terminal text, respectively. fresh reads retain availability, source, scope and truncation. |
| `agent.start` | required `machine`, `profile`; optional `name`, `cwd`, `group`, `prompt`. profile commands own provider/model/effort; no overrides. |
| `agent.send`, `agent.text`, `agent.keys` | target plus literal text or allowed keys. send is guarded input; text/keys are deliberate terminal interaction, not an automatic refusal bypass. |
| `agent.wait` | target; `state=idle` (`idle/working/needs-input`), `timeout_seconds=300` (1–86400), `maxBytes=16384` (1–32768). registers observation and returns immediately. |
| `agent.cancel_wait` | wait `action_id`; cancels observation only. |
| `agent.stop`, `agent.close` | interrupt the addressed terminal; or close with `terminal_only=false` by default. interruption and closure are separate facts. |

`target = {machine,handle}`; machines are `macbook|dev-server|arch`, handle is
`t-` plus 16 lowercase hex digits. profiles are `personal|work|work2|claude-work`.
`devbox` remains a memory identity, never a worker alias. every write uses existing
`ActionRequest = {request_ref,existing_action_ref,arguments}`: a delivered live
owner OR host request, null for a new action or an explicit original action ref,
and the exact typed input. equal arguments alone never imply replay.

existing persistence, shown schematically; do not add another representation:

```text
execution_contract.agent_target = original private capture for addressed writes/waits
registration_receipt = {action_id,target,state,deadline,recorded_at,
                        arguments_digest,status:"watching"}
action.result = {registration_receipt,wait_outcome:null | AgentWaitOutcome}
AgentWaitOutcome = {target,outcome,recorded_at,cancellation_action_id?,
                    terminalStatus?,output?,failure?}
outcome = matched | timeout | target_changed | unavailable | cancelled
host event = {type:"agent_wait_event_v1",action_id,tool_name,arguments,
              status,registration,result}
```

registration leaves the wait action queued; original callbacks always replay the
same watching receipt, including after settlement. a noncancel outcome settles
`succeeded`; cancelled settles `cancelled`. success here means observation ended,
not the task succeeded. `cancel_wait` returns `cancelled|already_settled`.
launch receipts retain `creation=not_sent|created|unknown` separately from
`prompt=not_requested|not_sent|written|unknown`; preserve known targets/partial effects.

## composition and invariants

1. existing native admission and serial dispatch validate a live request; addressed
   writes/waits capture the original terminal once before action insertion.
   skid resolves it; jarvis retains the opaque ref privately. later pane changes
   cannot retarget an existing action. reads may resolve the current terminal.
2. `AgentController.run_waits` runs outside main's dispatch mutex. it observes
   the original ref/deadline in 15-second chunks under 20-second child fences;
   registration changes signal it, with the existing five-second rescan as repair.
   a matched state's bounded read is a later observation, not an atomic task result.
3. `ActionStore.finish_agent_wait` or `cancel_agent_wait` commits the first outcome
   and its one canonical event atomically. `append_waking_input` supplies host
   role, `source=action`, source identity `<action-id>:<status>`, causal parent
   `origin_message_id` and structured `action_id`. use those primitives; do not
   parse the source string for correlation or create a second delivery ledger.
4. service notification starts/steers ordinary main with its full plan. a closed
   parent does not suppress the new fact. main dispositions the event independently,
   can issue another worker action/wait or use `work.*`, and preserves stopped
   parents/latest owner intent. no owner-message requirement or read-only event path.
5. restart uses the original watching receipt, ref and absolute deadline. existing
   startup repair republishes missing events idempotently. administrative pause
   suspends observation while deadlines advance; parked requests remain excluded
   by ordinary input admission, without suspending observation. shutdown cancels
   read children and joins database settlement before releasing ownership.
   conversational stop is not pause.
6. external start/send/text/keys/stop/close remain `BilledOnce`, one executor entry.
   recover conclusive staged `agent_control_v5` evidence without dispatch; missing
   or unknown evidence remains uncertain. never relaunch/resend an unknown effect.
   local wait/cancel remain `ReDispatchable`, at most two entries, zero worker
   mutations. ordinary connector consent, native journals and effect/read barriers
   remain; worker reports confer no owner consent. workers retain their own authority.

`stop` is ordinary conversation. main chooses scope and existing interruption or
observation actions; `InputOutcome.stop` cancels only named delivered requests'
proven unentered actions. entered effects settle. it neither stops workers nor
cancels descendants by implication. changing/deleting a todo also does neither.

## content design per feature

one designer owns these semantic criteria and reviews actual recorded output.
use the existing main prompt, tool inputs/results and native response variants;
add prompt text only for a demonstrated deficiency. no template or runtime critic.

| feature / content surface | good content; adversarial rejection |
| --- | --- |
| delegation / start prompt or send text | outcome, relevant context/location, actual scope and useful evidence; worker chooses method. reject invented context, extra authority or compulsory specialist hierarchies. |
| launch / ordinary response | distinguish creation from brief delivery. created + not sent means the terminal exists, not that investigation started. unknown delivery never promises safe resend. |
| observation / main continuation | relate evidence to outstanding work and latest intent. inspect/continue/ask/report/silence as useful. reject idle → done, stale output → exact task attribution, or obligatory rearming. |
| progress/blocker / native response | a finding, changed direction or actual obstacle and useful next step; ask only for a material missing decision. reject tool narration and unavailable → worker failed. |
| interruption / native response | distinguish request stop, observation cancellation, interruption dispatch and terminal closure. reject unproved worker/descendant cancellation or revival of an owner-stopped goal. |
| result / native response and optional todo | supported outcome, attributed evidence and material limits. mark done only when the intended outcome is supported; no mandatory independent recheck or todo per worker. |

brief: `inspect the expired-session failure in /srv/example. explain the cause with files and evidence; no code changes.`

result: `auth-review reports the integration check passed; production behavior remains unverified.`

interruption: `i sent the coordinator an interruption; i cannot yet confirm it stopped.`

useful silence and concise prose are valid; exact wording/tool sequences are not
acceptance criteria. once informed, the owner should know what happened and what
remains unresolved without decoding transport details.

## non-overlapping implementation boundaries

paths below are under `src/jarvis/` unless stated otherwise. ownership is for any
necessary repair, not an instruction to modify every file.

| owner | exclusive files / responsibility |
| --- | --- |
| adapter | `agent_tools.py`, `agent_control.py`: closed schemas, capture, cli receipt decoding, observation; incorporates designer edits to tool descriptions. |
| runtime | `action_requests.py`, `actions.py`, `messages.py`, `write_dispatch.py`, `write_policy.py`, `service.py`, `native_runtime.py`, `native_journal.py`, `tool_composition.py`: existing receipts, waking append, full-plan composition and recovery. |
| content | `definitions.py`: minimal main guidance when evidence exposes a gap; no extra role or prompt subsystem. |
| qualification/integration | temporary probes and this doc's evidence; matching inactive artifact, task resources and boundary observations. no production installer edit. |
| upstream, only if a defect is proved | skid owns terminal/protocol defects; kernel/provider-runtime/llm-tools own their existing interfaces. repair in the owning repo, pin exact qualified releases; no jarvis workaround or compatibility reader. |

read the landed predecessor before implementation. review contracts/content first;
then qualify unchanged source. adapter/runtime/content edits may proceed in parallel
only on their assigned files; the integrator composes revisions and final proof.
rotate affected binding/main revisions only when their behavior changes. preserve
finalized retired receipts opaquely; unfinished incompatible actions block later
activation. do not reopen completed gate/stop/scheduler removals.

## temporary qualification and acceptance

use existing inactive-release installation and transient service-uid execution
patterns from `deploy/install-release`, `deploy/agent-client-functions` and
`deploy/verify-containment`; add no persistent harness or service. task postgres
uses the actual migrated schema, application stores, action recorder, native runner
and service, with task-private configuration and initialized runtime state.
compose these existing objects through temporary probes with controlled
`GatewayPort`/catch-up; do not start another normal `jarvis serve` and its gateway
or memory listener. reuse the installed endpoint mapping and normal unique
cognition directories. retain the real jarvis uid/containment, contained cognition, fixed cli
and qualified read-only enrolled-state mount. no copied fleet state/credentials,
permission relaxation or production database/current-symlink change.

use owned disposable worker terminals and synthetic tasks. cover both codex/claude
and both online machines with representative available routes; record the actual
profile/host combinations, not an exhaustive account matrix. candidate ingress is
controlled canonical input; use the actual discord rest outbox for a bounded useful
result. do not start a second gateway consumer on the production channel or bypass
startup readiness. controlled ingress/catch-up is named in evidence, never called
physical-owner gateway acceptance. unavailable boundaries are `NOT_RUN`.

| feature | minimum proof / passing result |
| --- | --- |
| launch and responsiveness | actual native main delegates through installed skid; real profile produces useful evidence. watching returns before observation settles; an unrelated admitted owner input is answered meanwhile. partial/refused/unknown launch facts remain distinct. |
| event follow-through | after the original caller finishes, real observation commits one host event; main performs a useful follow-up worker action or todo mutation without new owner input and delivers a supported result. include a real scheduled-todo turn selecting delegation; no forced tool choreography. |
| restart | restart the candidate service process with a registered wait. preserve original receipt/ref/deadline, recover one outcome/event and continue without replaying worker mutations. replaying the original callback returns watching after settlement. |
| intent and content | scoped conversational stop during outstanding work, then a later observation/fresh context: stopped goal stays stopped; actual interruption claims match receipts. harmless observation may be silent. idle/unrelated text never proves completion; bounded or stale evidence supports only what it establishes, with material limits disclosed. |
| failure boundaries | focused real-postgres integration for cancel/match race (first commit wins), crash around atomic settlement/publication, absolute timeout after pause, changed target and unknown-effect no-replay. use controlled faults where necessary and label them; reuse unchanged o8 transport proof rather than requalifying every field live. |

for EACH feature: designer defines good content before probes; independent
adversary reviews design, red evidence, green behavior, refactor and cleanup.
run target journeys before edits. existing green behavior needs no manufactured
failure; missing installed evidence is not a red result. reproduce each discovered
defect, repair its owning layer, get green, remove actual duplication/dead paths,
and rerun changed concerns plus final journeys. then delete only new temporary
probes/resources and run `scripts/verify`; preserve approved memory regressions.

record concise implementation evidence here: exact commits/lock/cli/gateway/native
versions, migrated candidate head, tested hosts/profiles, real versus controlled
boundaries, failing observations/fixes, final receipts and content-review verdict,
probe cleanup and verification. never record secrets or private task bodies.
update existing [wait](issues/agent-wait.md) and [worker](issues/skid-terminal-flags.md)
issues; retain their production handoff until it is actually proved. no duplicate
qualification-report tree or permanent review machinery.

final production acceptance belongs to [operations](operations.md#skid-only-worker-cutover)
and [todo cutover](issues/work-installed-cutover.md): selected compatible release,
accounted-for effects/reminders, schema conversion and existing control rules;
then real owner gateway → main → installed worker → observation → useful main
continuation → discord, including selected-service restart. retain startup
catch-up and ordinary effect recovery. candidate receipts do not close that work.
this specification task changes documentation only and runs no behavioral/live
checks, publication, installation or activation.

## explicit costs

- terminal state plus bounded, non-atomic text lacks exact job-result correlation;
  main judges completion and attribution. no new worker protocol buys certainty.
- main chooses observation, follow-up and silence; no guaranteed notification,
  compulsory wait renewal or prescribed coordinator. conversation carries intent.
- unknown dispatch can remain uncertain; stop/close do not prove descendants ended.
  retain honest limits rather than repeat effects or claim cancellation.
- a candidate proves real worker composition while deferring production ingress,
  migration and restart acceptance. representative routes leave other profiles
  unqualified; existing arch deferral remains.
- deleting temporary probes reduces retained regression coverage. keep concise
  evidence and the existing approved checks, not another standing suite.
