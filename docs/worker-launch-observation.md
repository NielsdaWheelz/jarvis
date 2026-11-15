# worker launch and asynchronous observation — o8

status: consolidated accepted contract, updated 2026-11-14. worker v9 source is
terminal-only and isolated-qualified under
[adr 0069](decisions/0069-terminal-only-workers.md), retaining
[adr 0064](decisions/0064-simple-worker-orchestration.md)'s durable observation and
[adr 0068](decisions/0068-generalized-skid-consumer.md)'s installed-state composition.
installed jarvis qualification remains blocked by
[service-uid access](issues/skid-installed-state-access.md).
the [roadmap](implementation-plan.md#o8-richer-start-and-asynchronous-wait)
owns sequencing; [spec §7.3](../SPEC.md#73-tool-contracts-and-exact-catalog) and
the [terminal-only paired contract](https://github.com/NielsdaWheelz/skidbladnir/blob/2c2401e8b354cbcf7b8d97dbf22679ed5fad4504/docs/terminal-only-control.md)
own the current schemas. earlier native-era qualification applies only to its
recorded source.

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
o7 owns records; [o9](delegated-follow-through.md) owns discretionary follow-through. current source
requires owner-grounded writes and permits isolated wait-event silence.
[adr 0071](decisions/0071-simple-event-driven-v2.md) adopts
[o6](one-main-events.md)'s separate full-capability event target; it remains
unimplemented. o8's observation transport does not need a new push api or worker
protocol for that change.

## capability and api

reuse closed models in `agent_tools.py`; every write retains `ActionRequest` and
the existing serial action lane. target is `{machine,handle}`: machine is
`macbook`, `devbox` or `arch`; handle is `t-` plus 16 lowercase hex digits.
profiles are `personal`, `work`, `work2`, `claude-work`. names are labels.

| tools | contract |
| --- | --- |
| `agent.list` | machine/group/unassigned filters; group and unassigned exclusive; preserve empty versus partial/unavailable inventory |
| `agent.info` | target; preserve observed terminal status/unavailability |
| `agent.start` | machine/profile required; optional name/cwd/group/prompt; the configured profile command owns provider/model/effort options |
| `agent.read` | target, `maxBytes = 16384`, range 1–32768; preserve terminal source/scope/truncation |
| `agent.send`, `agent.text`, `agent.keys` | send uses guarded terminal input for either provider; text/keys are deliberate terminal input |
| `agent.stop`, `agent.close` | stop interrupts the selected terminal; close is terminal-only, `terminal_only = false`; interruption and closure remain separate facts |
| `agent.wait` | target, `state = idle`, `timeout_seconds = 300` (1–86400), `maxBytes = 16384` (1–32768) |
| `agent.cancel_wait` | original wait `action_id`; returns cancelled/already_settled; observation only |

wait states: idle/working/needs-input. prompt/text is nonempty, at most 32768
utf-8 bytes, no nul, literal stdin. name uses skid's
existing 1–64 ascii grammar. keys use the existing 1–16-key allowlist. retain
cwd/group bounds and encoded-body preflight; never crop input to make it fit.
start has no model/effort fields; unknown overrides reject. there is no worker
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

registration may outlive a completed caller, but grants no new write authority.
after the original owner turn closes, reads/integration/notification only;
further worker input or new waits require current owner input in current source.
after o6 cutover, the published result is an ordinary event with main's full
capabilities; jarvis chooses whether to continue, inspect, notify or do nothing.
main need not poll worker sessions to notice completion: this existing host
watcher supplies the event. an idle observation still does not prove task success.
startup resumes observation and
repairs missing events/stranded inputs through existing primitives. in current source, stop/pause/
quarantine suspend registered observation while its deadline advances; resume may
timeout. stop cancels unentered authority, not an entered wait or worker.
shutdown cancels read children and joins database settlement before ownership ends.

## designer's content contract

brief: concrete objective, useful context/scope and requested evidence; ordinary
prose, no template or report protocol. results identify the worker and what
happened; include unknowns/next steps when material. distinguish creation, dispatched
bytes, observed terminal state and evidenced task completion.

good brief: `inspect the authentication flow in /srv/example. explain the expired-session 500; no code changes. include files and evidence.`

good partial result: `auth-review was created on devbox, but its brief was not sent. the worker remains available; the launch will not repeat.`

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
| jarvis deployment | separately resolve live installed-state access under the existing service containment before installed cutover |
| temporary qualification | scoped proof files only; installed artifact/configuration and actual service/discord evidence |

source qualification does not resolve installed deployment. generalized skid
reads the enrolled owner's live state; the jarvis service cannot access it under
its current uid and containment. `deploy/install-agent-client` refuses explicitly.
the [service-state access issue](issues/skid-installed-state-access.md) owns that
separate decision and proof. dev-server no longer installs a private jarvis
client or reads `jarvis-paused.v1`; the former file-pause installer proposal is
superseded. no copied state or privilege bridge is assigned by worker v9.

## cutover and acceptance

1. resolve and qualify the separately owned live-state access boundary before
   installed jarvis worker use. keep the service stopped until that blocker is
   resolved; this contract assigns no privilege bridge or copied identity.
   drain/reconcile predecessor actions and owed outcomes/delivery; pause and stop.
2. provision runtime environment/secrets and install exact target/contained host
   without starting jarvis; complete existing preparation/native
   conversion first. a fresh database needs migration and public
   `initialize-state` instead of importing predecessor state.
3. target `check-paused` must pass before changing worker cli/configuration.
   missing canonical pause, competing owner, unavailable database/qualified
   release or retired files refuse; preserve current executables on refusal.
4. install paired artifacts/configuration, run target pre-start activation checks,
   activate PAUSED, then run `deploy/verify-containment` before explicit owner
   resume. installed turn journeys require authorized resumed admission.
   finalized v1–v8 worker bytes stay opaque;
   unfinished retired state refuses activation. no compatibility decoder.

rollback requires proof the prior release reads current schema/contracts and
paired configuration. incompatible conversion or new receipts requires preserving
evidence and forward repair. code rollback cannot undo worker effects; never
restore over them.

reuse [v9 source qualification](decisions/0069-terminal-only-workers.md); do not
manufacture new red evidence for already-green source. installed work first needs
the separately chosen live-state access boundary and paused/stopped release
qualification; source fixtures do not establish either.

remaining installed live acceptance: configured codex/claude profiles, optional
name/cwd/group/prompt and literal input, with provider options owned by the profile;
partial/refused/unknown effects with no mutation replay;
original-ref refusal on changed targets; register then serve unrelated owner input;
restart with original watching receipt and one outcome/event; cancel/match and
pause/deadline/shutdown; actual ordinary continuation and owner communication under
the adopted event contract. use synthetic briefs and real installed service,
jarvis native cognition, terminal cli/gateway and discord boundaries;
controlled ports do not prove installed behavior. provider archive/memory APIs
remain separate and supply no worker-control fallback.

review each boundary, get green, refactor only demonstrated duplication, rerun
changed concerns/final journeys and have the designer review recorded content.
retain artifact/status evidence, then delete temporary tests and run
`scripts/verify`. unavailable boundaries remain `NOT_RUN`. no live tests,
publication, installation or activation are authorized by this documentation task.

trade-offs: ordinary conversation gives semantic judgment instead of exact task
correlation; bounded/non-atomic reads limit evidence; lost acknowledgements can
remain uncertain; capture plus one read child per active wait costs subprocesses.
hard cutover requires coordinated downtime and a separately qualified live-state
access boundary. terminal-only control loses provider-native history and result
semantics. temporary-test deletion reduces
retained regression coverage. no new table, framework or shared-library api.
