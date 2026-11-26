# skid follow-through — o9 / slice 3

the source below describes the retired terminal-observation release.
[adr 0112](decisions/0112-managed-agent-delegation.md) owns the current
delegation implementation and cutover.


source and candidate qualified on 2026-11-15 under
[adr 0071](decisions/0071-simple-event-driven-v2.md). the
[production restart journey](runtime-reliability-and-integration.md#restart-catch-up-and-original-send)
subsequently qualified worker follow-through on the selected deployment.
audited predecessor: merged `31f3dd9`; slices 1–2 are source-qualified. worker v10,
full-plan events, conversational stop and todos already exist. this slice qualifies
their composition and repairs demonstrated defects; it adds no orchestration layer.
[the roadmap](implementation-plan.md#v2-reviewable-pr-slices) owns sequence.

[f3](subscription-model-runtime.md#implementation-evidence) implements and qualifies
owner-selected per-session worker model/effort and the v11 cutover through this
slice's existing follow-through path; this v10 evidence stays
at its original artifacts and does not qualify that extension.

## goal, scope and final state

jarvis delegates useful work, remains responsive, receives a later observation and
chooses the next useful action without another owner message. the same main handles
owner input, worker outcomes and scheduled todos. todo state is context, not authority.
main may reuse a worker, coordinate/fan out, continue directly, inspect, ask, report
or do nothing. a coordinator is useful for substantial work, never mandatory.

the owner selected a temporary candidate against the installed skid fleet for
this slice, with deployment activation, reminder conversion and production
acceptance deferred to f2. the candidate qualified behavior and the demonstrated
repairs under that original decision.

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
| `agent.start` | required `machine`, `profile`; optional `name`, `cwd`, `group`, `prompt`, `model`, `effort`. profiles retain provider/account/executable defaults; f3 owns native per-launch lowering. |
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
the [installed worker handoff](runtime-reliability-and-integration.md#restart-catch-up-and-original-send)
records the subsequent production restart, original wait outcome and discord
delivery.

final production acceptance belongs to [operations](operations.md#skid-only-worker-cutover)
and [todo cutover](operations.md#supervised-todo-setup): selected compatible release,
accounted-for effects/reminders, schema conversion and existing control rules;
then real owner gateway → main → installed worker → observation → useful main
continuation → discord, including selected-service restart. retain startup
catch-up and ordinary effect recovery. candidate receipts do not close that work.
the subsequent owner instruction authorized source implementation and temporary
integration/live qualification. production activation remains outside this slice.

## implementation evidence — 2026-11-15

candidate behavior, independent content review, cleanup and final repository
verification PASS. the
composition, corrected scheduled brief, restart, follow-through and repaired
installed skid gateway have passing evidence below. the owner selected explicit
unavailable status for claude; useful claude execution is NOT_RUN.

the branch is `feature/delegated-follow-through`, isolated from the owner's dirty
checkout. source predecessor is merged `31f3dd9`; the owner's current contract
edits were copied unchanged into the worktree before implementation. operational
candidate `2d1dbcc53e11cedbb5f6f7b74374e99aa9df1036` contains the final runtime
source and compatibility manifest. before integration with newer main, source,
pins, lock, migrations, deployment inputs and python version compared exactly to
that qualified artifact. later
candidate `3c8b4c94e2c2a27303941d1de2a17bcdd2227214` corroborated the journey with
an illustrative main prompt subsequently removed after rubric review.
that live candidate's `uv.lock` sha256 is
`ba15ecdb38dc2cac6bb12ba1eb6bc018b18ac2a923367f004f31392b2f9bf11e`.

| component | historical live-candidate identity / boundary |
| --- | --- |
| kernel | `419e5fe3e251e9ffdf506ae88fb7149fac6e1549` |
| provider-runtime | `adf1b714dec6b2517ba468085674665923c237fc` |
| llm-tools | `8989f3afdcc640f775bd0cc9e7a0b4c246f10e57` |
| universal-memory | `11f4220031d56f71d5a732b748a9bbb52c842e0e` |
| candidate | inactive immutable release; python 3.12.13, fresh migrated head `0010`; task postgres 16.16 / pgvector 0.8.6 |
| cognition | existing selected contained stock `0.160.0`, public provider qualification, actual `gpt-5.6-terra`/high; normal unique cognition directories |
| workers | baseline `v0.24.2` / `d4afbfcec963b1f231fc117675120eff1685e881`; final installed cli/gateways `v0.24.3` / `0c2874f9f9e33bb4037afa310f16ef6e0c584db8`; worker binding remains v10 |
| real routes | dev-server/personal codex and macbook/personal codex; macbook/claude-work and dev-server/claude-work reached their account limits before useful execution |

the transient candidate used the real jarvis uid, empty capabilities,
no-new-privileges, protected home/system, private temporary directory and the
qualified read-only id-mapped `/run/jarvis-skid-state` mount. task configuration,
postgres, runtime files and disabled memory admission were separate; no fleet
state or native credential was copied. the existing selected contained-host
verifier passed; candidate/selected host launcher and mapping code were identical.
the selected release has different application library pins, so its verifier is
not presented as candidate library qualification. candidate native calls used the
exact pins above against that existing public endpoint.

temporary probes composed the actual service, stores, recorder, native runner,
timer and rest outbox. a controlled `GatewayPort` exercised normal
`gateway_ready`/catch-up; no second gateway consumer, memory listener or normal
`jarvis serve` ran. canonical synthetic ingress is not physical-owner gateway
acceptance. actual nonce-backed discord delivery and durable watermarks were used.
production's selected release, control and schema were not changed: observed
predecessor `0fc3d6444231484f1762c14c83f15d8b166b7fd6`, schema `0008a`, canonical
resume sequence 4. final v2 cutover must reconcile that actual predecessor,
including its newer memory pins, rather than infer it from source `31f3dd9`.
candidate memory admission is disabled; ordinary native-fleet capture policy is
unchanged, so disposable worker histories retain their existing capture eligibility.

| feature | red / green evidence |
| --- | --- |
| private evidence | real-postgres probes exposed private v10 captures in accepted-action context and opaque retired arguments in both linked and unlinked callback context. the actions module now owns loading, public projection and the shared retired-binding predicate. fresh main gets current public arguments/receipts and historical metadata; original database evidence is unchanged. all three red cases and current receipt/connector-context regressions pass. actual prepared native input in four fresh live attempts also excludes the captured worker refs. |
| observation and recovery | unchanged adapter passes actual subprocess decoding plus controlled fault receipts; real-postgres/native journal/recorder proves first-commit cancel/match outcomes, one causal event, atomic rollback around settlement/publication/cancellation, idempotent startup repair and original watching replay after settlement. unknown billed-once recovery enters no executor and sends nothing. |
| pause, park and shutdown | real-postgres integration proves parked requests remain excluded while observation continues; canonical pause cancels the read child while the original deadline advances. resume after expiry emits one timeout without another cli read. shutdown joins a deliberately blocked database settlement before ownership closes. |
| responsiveness and restart | real native main launched a dev-server codex worker and registered observation, then answered unrelated arithmetic while it was still watching. an actual candidate process stop/restart retained exact arguments, private capture, watching receipt, absolute deadline and one executor entry; it later published one timeout without replaying launch. |
| intent | actual native scoped stop cancelled only the first todo/request. its worker and registered observation continued; a later event was handled without reviving that goal. separate real-postgres product/journal proof covers completed and stopped parents followed by a new full-plan host action. |
| scheduled delegation and follow-through | a real one-time todo woke main after its scheduling owner request completed and launched macbook claude-work. account-limit evidence led to explicit blocked state and an honest partial result. a later macbook codex journey timed out while working; main read its evidence, registered another wait, received a matched event, requested a compact supported restatement and completed the todo without another owner input. actual discord received the supported source result; source inspection was not described as runtime verification. |
| content | independent design/review covered briefs, partial launches, observations, progress, scoped stop and results. the owning start-tool copy clarifies terminal creation/optional brief delivery and no execution observation; common written semantics distinguish dispatch from acceptance/execution/completion. a scheduled brief demonstrably lost the requested host, path and inspection duration. shared create/update documentation now tells main to preserve the future turn's outcome, sources and material owner constraints. corrected real scheduled turns preserve them. |

the fresh-context launch-arrangement case completed its owner request before
observation, then used real host events for reads, compact worker restatement and
a supported source report without another owner message. three controlled
actual-native owner/host/partial-launch trials each ran once against real migrated
postgres, journals and service-uid contained cognition; only terminal transport and
delivery were controlled. independent semantic review accepted every progress and
final response, including explicit created/not-sent partial delivery without
relaunch. these trials are not real worker execution proof.

review initially rejected generic `verification is running; awaiting findings`
as a worker-execution assertion. adversarial review of the actual criterion
retracted that judgment: created terminal, dispatched brief, coordinated todo and
durable observation support workflow progress while findings remain pending.
there is no mandatory worker-read step. no retained earlier wording established
explicit worker activity. the attempted extra main clauses/example were removed;
main instructions remain unchanged. main's compatibility revision rotates to
`jarvis-main-follow-through-v1` for its changed recovery-context projection;
application-wide and isolated-role revisions remain unchanged. the owning tool copy
is a clarification, not a repair of a proved execution claim. created/not-sent
presented as inspection started, explicit activity without evidence, safe resend
after unknown delivery, hidden quota limits and idle-implies-success still fail.

the final installed operational journey at `2d1dbcc` retained the requested
dev-server, exact release cwd, 90-second inspection and read-only constraints in
the model-authored todo and the actual due-turn worker brief. main delegated;
the candidate process stopped/restarted after registration and caller settlement.
original arguments, captured ref, watching receipt, deadline and executor count
remained exact. one matched causal event triggered a useful worker follow-up,
another observation, todo completion and actual delivered source-qualified result
without another owner input. original callback replay is separately proved by
the real-postgres native journal/recorder group. all external worker writes had
one executor entry; the outbox and pending input/action counts reached zero.

the same actual due/restart journey passed at `3c8b4c9`: the original deadline and
watching receipt survived restart, one matched event led to todo completion and a
delivered source-qualified result, and every worker mutation entered once. the
generic progress notice above passed the corrected independent content rubric.
removing the unnecessary main example restored the exact qualified `2d1dbcc`
runtime, manifest and deployment inputs before later mainline integration. independent review accepted that
comparison without repeating an identical paid journey.

one earlier attempt raised an [unexplained NativeDefect](issues/native-protocol-diagnostics.md)
after accepted launch/bookkeeping callbacks. it was fenced and parked with a
visible notice. named operator repair and explicit owner correction stopped the
obsolete wake and deleted its incomplete brief; the original launch stayed at
one executor entry. the separately demonstrated brief-context loss was repaired
in shared create/update documentation. the unknown exception cause is not
retroactively resolved or called a model failure by later passing journeys.

the first synthetic codex inspection used an inactive-release cwd that normal
candidate replacement pruned. its responsiveness/receipt observations remain
valid; its report is not complete target-code qualification. subsequent useful
inspection used stable source paths. this setup error required no product change.

live proof also found a real upstream defect: a wrapped codex status footer at
80×24 occupies four physical rows, exceeding skid's arbitrary three-row parser
cap. the completed terminal remained `layout_unknown` and its idle wait timed
out. [skid pr 203](https://github.com/NielsdaWheelz/skidbladnir/pull/203), source
`fed8c48435ba5774cfc2dfc640f19202e2d8a2c5`, removes that cap within the existing
bounded parsed screen and retains composer/padding/overlay guards. an owning-source
probe on the same guarded linux codex 0.169.0 / tmux 3.8 pane went red→green;
466 existing and twelve temporary authored captures passed independent review.
the original corpus is unchanged, new probes are deleted, and post-cleanup
`scripts/check verify host` and github `verify` pass. an unrelated vercel account
check is blocked. the owner approved normal merge, signed publication and
gateway-only updates. artifact preflight exposed a second upstream defect:
the runtime comparator treated Go build IDs and their Mach-O UUID as behavioral
changes despite identical code/data/resources. [pr 204](https://github.com/NielsdaWheelz/skidbladnir/pull/204)
repairs the existing comparison after signature verification, normalizing only
those framed metadata fields in scratch memory. actual signed artifact red/green
and eight negative cases distinguish changed code/data/resources, signer,
designated requirement and malformed metadata; service differences still require
runtime replacement. no executable is rewritten and no comparator is bypassed.

the rebuilt immutable [v0.24.3 release](https://github.com/NielsdaWheelz/skidbladnir/releases/tag/v0.24.3)
is exact source `0c2874f9f9e33bb4037afa310f16ef6e0c584db8`, with nine verified signed
assets and successful exact-main github verify `43750704672`. [pin pr 205](https://github.com/NielsdaWheelz/skidbladnir/pull/205)
merged at `616deb3`; its exact artifact hashes and public release verification
pass. the abandoned unpublished draft was removed in full before the rebuild.

normal new-release bootstrap installation updated both online gateways. mac
runtime pid 15431/tmux 15439 and linux tmux/runtime pid 2132580 retained their
original starts/epochs; runtime files and effective service definitions were
unchanged. all eighteen mac and six linux pre-existing session/pane refs survived.
jarvis's fixed regular cli was verified under the restricted uid before atomic
replacement: root:root 0755, sha256
`ad086c5b099dc1a0f5bbc363b5ebdb7c74097281b1ee50fd8e809e652de9bea3`.
mount/source directory inode 2005629 and read-only id-mapped flags remained exact;
production jarvis pid 470625, selected release, schema and canonical control were
unchanged. the original affected captured ref now matches `idle/none/recognized`
in 0.05 seconds through the actual service-uid fixed cli; its prior 15-second
wait timed out with `layout_unknown`. independent installed review accepted these
receipts. the consumer pins an unchanged bootstrap checksum and selects latest
signed stable, so no second version mechanism was added.

the detector is a remote gateway conformance repair under unchanged wire and
state meanings; jarvis's bindings/decoder/policy remain v10. its definition
fingerprint does not claim to bind the external gateway executable. the exact
installed versions above supply that qualification. the owner selected explicit
unavailable status for both claude routes; arch and other profile combinations
remain deferred. final production
gateway/cutover acceptance stays with the existing operations/todo handoff.

all controlled source groups received independent design/red/green/refactor and
cleanup review. their temporary probes and local postgres resources were deleted;
the retained `tests/capture_retry.py` passes unchanged on a fresh `0010` database
(postgres 16.16 / pgvector 0.8.7). independent final source review found no blockers.

live cleanup drained pending actions, inputs and outbox before stopping both
candidate units. eight original captured terminals were closed once, preserving
all nineteen untargeted refs; the final corroborating terminal was then closed
once, preserving all twenty refs present at that later inventory. each receipt
separately proves interruption `written` and terminal `closed`, not descendant
cancellation. both task databases, runtime/configuration, diagnostic wrapper,
temporary probes and inactive release were removed. only the selected production
release remains. its pid/selection, schema `0008a` and resume sequence 4 compare
exactly to the pre-update observations. no production authority or memory capture
policy changed. pre-integration `scripts/verify` passed: frozen lock/install, formatting,
lint, types, all 125 documentation files, wheel/sdist build, fresh wheel install
and registry dependency audit. the three git-only kernel/tools/provider packages
are outside that registry audit. approved memory regression files are unchanged;
no temporary per-feature test or review machinery remains.

pre-pr integration incorporated current main `0833cf8` and its accepted adr 0073
memory baseline work without changing that source or reverting its pins. composed
pins are kernel `da33773662089a72992c9aec1f938c76d9cb95ab`, provider-runtime
`70178ec8bb5b54304367ad60c0732447084a37c7` and universal-memory
`93e02af07fee7e79250fb800835c324f092b5bec`; llm-tools is unchanged. composed
`uv.lock` sha256 is `7a8c28510d78d8e90c423bb3b3f450a646fccc92509743722bc5d867a1fcd246`.
independent exact-source review confirms no kernel python change, only provider
archive changes and memory baseline mechanisms; native cognition, worker control
and this slice's four runtime/tool files remain unchanged. main's context revision
is the only manifest difference from current main.

composed qualification passes fresh postgres 16.16 / pgvector 0.8.7 migration
`0001` through `0008a` to `0010`, asserting the head and baseline column; unchanged
least-privilege jarvis capture/retry and all three retained library capture/memory
completion checks; loaded dependency/manifest verification; and `scripts/verify`,
including all 126 documentation files and fresh packaged dependency verification.
the separate task databases/container were removed. adversarial review accepted
this affected-path proof without repeating an unchanged paid worker journey.
the historical live-candidate versions above remain explicit; this integration
does not establish another installed candidate or production cutover.

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
