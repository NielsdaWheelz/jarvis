# worker launch and asynchronous observation — o8

status: consolidated accepted contract, updated 2026-11-16. worker v10 adopted
the enrolled `dev-server` label under
[adr 0072](decisions/0072-native-memory-rollout.md). terminal-only behavior retains
the v9 source qualification in [adr 0069](decisions/0069-terminal-only-workers.md) and
[adr 0064](decisions/0064-simple-worker-orchestration.md)'s durable observation and
[adr 0068](decisions/0068-generalized-skid-consumer.md)'s installed-state composition.
installed jarvis qualification includes adr 0072's read-only live-state mount.
the [roadmap](implementation-plan.md#o8-richer-start-and-asynchronous-wait)
owns sequencing; [spec §7.3](../SPEC.md#73-tool-contracts-and-exact-catalog) and
the [terminal-only paired contract](https://github.com/NielsdaWheelz/skidbladnir/blob/2c2401e8b354cbcf7b8d97dbf22679ed5fad4504/docs/terminal-only-control.md)
own the current schemas. earlier native-era qualification applies only to its
recorded source.

current source: [adr 0076](decisions/0076-role-models-and-delegated-choices.md) and
[f3](subscription-model-runtime.md#delegated-model-choices) add per-session skid
model/effort choices and the v11 hard cut, with
[source/candidate qualification](subscription-model-runtime.md#implementation-evidence).
earlier v10 observations retain their original artifacts. this amendment
supersedes only the launch-override prohibition and affected binding revision;
terminal-only control, receipts and asynchronous observation remain unchanged.

## goal and boundaries

launch configured worker profiles with optional initial terminal input,
inspect/control existing terminals and observe a captured target without blocking
main. keep truthful creation/input/outcome facts through failure and restart.

jarvis owns admission, receipts, observation lifecycle and owner notices. skid
owns terminal identity, control, installed state and lifetime; dev-server consumes
its published release and personal configuration.
kernel/provider-runtime/llm-tools retain their existing native/tool contracts.
workers are trusted execution domains; jarvis connector approvals do not contain
their effects.

no new table, worker registry, task/reply packet, exact request-result correlation,
mandatory coordinator, polling model turn, scheduler or subtree cancellation.
o7 owns records; [o9](delegated-follow-through.md) owns discretionary follow-through
and slice 3 qualification. [o6](one-main-events.md)'s full-capability event path
is implemented in source under [adr 0071](decisions/0071-simple-event-driven-v2.md).
an admitted owner or host request can ground worker actions; main chooses useful
continuation, notification or silence. source acceptance is not v2 activation.

## capability and api

reuse closed models in `agent_tools.py`; every write retains `ActionRequest` and
the existing serial action lane. target is `{machine,handle}`: machine is
`macbook`, `dev-server` or `arch`; handle is `t-` plus 16 lowercase hex digits.
`devbox` is not a worker alias; memory retains its separate `devbox` provenance.
profiles are `personal`, `work`, `work2`, `claude-work`. names are labels.

| tools | contract |
| --- | --- |
| `agent.list` | machine/group/unassigned filters; group and unassigned exclusive; preserve empty versus partial/unavailable inventory |
| `agent.info` | target; preserve observed terminal status/unavailability |
| `agent.start` | machine/profile required; optional name/cwd/group/prompt/model/effort; profiles retain provider/account/executable defaults, and supplied native options select this launch |
| `agent.read` | target, `maxBytes = 16384`, range 1–32768; preserve terminal source/scope/truncation |
| `agent.send`, `agent.text`, `agent.keys` | send uses guarded terminal input for either provider; text/keys are deliberate terminal input |
| `agent.stop`, `agent.close` | stop interrupts the selected terminal; close is terminal-only, `terminal_only = false`; interruption and closure remain separate facts |
| `agent.wait` | target, `state = idle`, `timeout_seconds = 300` (1–86400), `maxBytes = 16384` (1–32768) |
| `agent.cancel_wait` | original wait `action_id`; returns cancelled/already_settled; observation only |

wait states: idle/working/needs-input. prompt/text is nonempty, at most 32768
utf-8 bytes, no nul, literal stdin. name uses skid's
existing 1–64 ascii grammar. keys use the existing 1–16-key allowlist. retain
cwd/group bounds and encoded-body preflight; never crop input to make it fit.
model/effort are absent/null or bounded native identifiers under
[f3's launch contract](subscription-model-runtime.md#delegated-model-choices).
there is no worker
native target, read-source selector, provider admission/result or conversation
history route. terminal text is limited to retained scrollback or the visible screen.

public launch facts: `{machine,target?,captured,creation,prompt,failure?}`.
creation is not_sent/created/unknown; prompt is not_requested/not_sent/written/
unknown. failed initial input retains known creation/target. `AgentFailure`
preserves code, dispatch and optional launch/close facts: not_sent is refusal,
sent retains a known partial effect, unknown is uncertainty. nonzero exit alone
does not discard a valid receipt or authorize retry.

skid wire decoding is separate and closed; optional wire fields are omitted,
not null. hide structured opaque refs/process/account identities from model
results; preserve their immutable private evidence. resolve fresh reads normally;
capture addressed writes/waits ONCE before insertion into
`execution_contract.agent_target`. dispatch uses the original opaque `--ref`;
changed panes/successors never renew it. native conversation targets and
read/write/identity paths are removed without compatibility decoding.

in live session replies, optional `terminalUsage` contains one or both windows
`fiveHour` and `sevenDay`. each carries an integer `usedPercent` in 0–100 and
may include `resetsAt`, a whole-second utc instant spelled
`YYYY-MM-DDTHH:MM:SSZ`. omit absent fields. quota stays private.

fixed `--config STATE_DIRECTORY --json`, with the live enrolled state directory
from `JARVIS_AGENT_STATE_DIRECTORY`; no retired private client-json or copied-state
fallback. argv uses no shell and only `PATH=/usr/bin:/bin`; input is literal stdin.
concurrent stdin/stdout, discarded stderr,
existing 1 mib inventory/64 kib other stdout caps. retain 20-second child fences
and current 20/45-second tool deadlines; cleanup kills only the cli child.

## durable composition

external start/send/text/keys/stop/close are `BilledOnce`: one executor entry.
known staged `agent_control_v5` evidence settles through the same classifier on
restart without dispatch. missing/unknown evidence remains uncertain; never
relaunch/resend automatically.

on reopening an `agent_control_v5` receipt, its optional
`observed.terminal.session.terminalUsage` is an opaque json object. validate
the parent, operation and captured target as usual. an empty observation can
carry `observed: null`. settlement preserves the original staged json in
`control`. the compact public result describes the worker outcome.

wait/cancel are local `ReDispatchable` actions: two lifetime entries, zero worker
mutation attempts. reuse `ActionStore`/`ActionPositionRecorder`:

```text
registration_receipt = {action_id,target,state,deadline,recorded_at,
                        arguments_digest,status:"watching"}
action.result = {registration_receipt,wait_outcome:null | AgentWaitOutcome}
wait_outcome = {target,outcome,recorded_at,cancellation_action_id?,
                terminalStatus?,output?,failure?}
```

return watching immediately; action stays queued. original callback always
replays its registration, even after settlement. outcome is matched/timeout/
target_changed/unavailable/cancelled. noncancel outcomes settle action succeeded;
that means observation finished, NOT task success.

existing service watcher uses original ref/deadline outside main's mutex:
15-second chunks within 20-second child fences. a matched state's later bounded
read is independent; retain read failure/truncation. outcome and one ordinary
`source=action` event commit together, deduplicated by action id/status.
cancellation commits its receipt with the original outcome/event; first outcome
commit wins. no automatic rearm or input replay.

registration may outlive a completed caller. its published result is an ordinary
event with main's full capabilities; jarvis chooses whether to continue, inspect,
notify or do nothing. deployment admission and original effect/read recovery
still apply; worker prose is evidence, never owner consent.
main need not poll worker sessions to notice completion: this existing host
watcher supplies the event. an idle observation still does not prove task success.
startup resumes observation and repairs missing events/stranded inputs through
existing primitives. administrative pause suspends registered observation while
its deadline advances; resume may timeout. parked requests are excluded by input
admission without suspending observation. conversational stop
does not suspend registered observation or stop a worker. main uses o6's scoped
request disposition and existing worker controls; later evidence preserves the
latest owner intent and cannot reopen a stopped parent.
shutdown cancels read children and joins database settlement before ownership ends.

## designer's content contract

brief: concrete objective, useful context/scope and requested evidence; ordinary
prose, no template or report protocol. results identify the worker and what
happened; include unknowns/next steps when material. distinguish creation, dispatched
bytes, observed terminal state and evidenced task completion.

good brief: `inspect the authentication flow in /srv/example. explain the expired-session 500; no code changes. include files and evidence.`

good partial result: `auth-review was created on dev-server, but its brief was not sent. the worker remains available; the launch will not repeat.`

good observation: `the worker reached idle; its latest output was unavailable, so i cannot verify the result.`

show material limits/blockers/questions when useful; main chooses ordinary
communication under o6, without a progress or completed-result subsystem.
idle/latest prose supplies no exact task
attribution. close never proves shared work stopped. content review judges facts
and usefulness, not wording; no new runtime critic.

## non-overlapping delivery

| owner | exclusive files / deliverable |
| --- | --- |
| jarvis adapter | `agent_tools.py`, `agent_control.py`: existing schemas, capture, transport/watcher; change only for a demonstrated defect |
| jarvis durability/composition | `actions.py`, `write_dispatch.py`, `service.py`, `native_journal.py`, `tool_composition.py`, `write_policy.py`, `definitions.py`, `cli.py`: existing receipts/events/admission; applies designer content |
| skid release | publish immutable artifacts containing the implemented paired contract; no new worker protocol/source redesign |
| dev-server consumer | matching published skid pin and desired personal yaml; skid owns installation/services |
| jarvis deployment | preserve adr 0072's qualified live-state mount and service containment; selected-release activation remains separately scoped |
| temporary qualification | scoped proof files only; installed artifact/configuration and actual service/discord evidence |

source qualification does not resolve installed deployment. generalized skid
reads the enrolled owner's live state through adr 0072's qualified root-managed
read-only id-mapped mount, including atomic membership-file replacement. preserve
that boundary; no copied identity or private jarvis client file. canonical control
is checked in postgres; the former file-pause installer proposal is superseded.

## cutover and acceptance

the matching cli and live-state access boundary are installed and read-qualified.
[slice 3 evidence](delegated-follow-through.md#implementation-evidence--2026-11-15)
qualifies candidate worker mutations and follow-through, with useful claude
execution explicitly unavailable by owner decision. selected-production proof
remains at final v2 cutover; no second installation workflow.

[operations](operations.md#skid-only-worker-cutover) owns eventual activation.
the intermediate v2 `activate-release` intentionally refuses. selected-release
cutover accounts for outstanding effects, approvals, reminders, waits and owed
delivery before changing incompatible contracts. retain finalized v1–v9 worker
bytes opaquely; unfinished retired state refuses activation. no compatibility
decoder or replay of unknown effects.

adr 0072 distinguishes routine stopped-release replacement, which preserves
canonical pause/resume, from migrations and private-configuration/authority
changes, which retain their pause requirements. do not synthesize a control or
silently restore an old installer. startup recovery and validated discord catch-up
remain mandatory; [todo conversion](operations.md#supervised-todo-setup) stays with
the selected v2 cutover.

rollback requires proof the prior release reads current schema/contracts and
paired configuration. incompatible conversion or new receipts requires preserving
evidence and forward repair. code rollback cannot undo worker effects; never
restore over them.

reuse [v9 source qualification](decisions/0069-terminal-only-workers.md) for
unchanged behavior. v10 additionally qualifies the enrolled label through actual
cli inventory/target capture and verifies finalized v9 preservation, unfinished
v9 refusal and strict current labels. preserve that qualified boundary and keep
candidate proof separate from selected-production acceptance.

remaining selected-production acceptance:
configured codex/claude profiles, optional
name/cwd/group/prompt and literal input, with provider options owned by the profile;
partial/refused/unknown effects with no mutation replay;
original-ref refusal on changed targets; register then serve unrelated owner input;
restart with original watching receipt and one outcome/event; cancel/match and
pause/deadline/shutdown; actual ordinary continuation and owner communication under
the adopted event contract. slice 3 uses synthetic briefs, real service restrictions,
jarvis native cognition, installed terminal cli/gateways and the actual discord
outbox. controlled ingress proves no production gateway behavior; selected-service
acceptance stays at final v2 cutover. provider archive/memory apis
remain separate and supply no worker-control fallback.

review each boundary, get green, refactor only demonstrated duplication, rerun
changed concerns/final journeys and have the designer review recorded content.
retain artifact/status evidence, then delete temporary tests and run
`scripts/verify`. unavailable boundaries remain `NOT_RUN`. no live tests,
publication, installation or activation are authorized by this documentation task.

trade-offs: ordinary conversation gives semantic judgment instead of exact task
correlation; bounded/non-atomic reads limit evidence; lost acknowledgements can
remain uncertain; capture plus one read child per active wait costs subprocesses.
eventual production cutover requires coordinated downtime and preserves the
qualified live-state access boundary. terminal-only control loses provider-native history and result
semantics. temporary-test deletion reduces
retained regression coverage. no new table, framework or shared-library api.
