# worker launch and asynchronous observation — o8

status: consolidated accepted contract, 2026-10-06. worker source is implemented
under [adr 0064](decisions/0064-simple-worker-orchestration.md); installed paired
qualification remains open. this task changes docs only. the [roadmap](implementation-plan.md#o8-richer-start-and-asynchronous-wait)
owns sequencing; [spec §7.3](../SPEC.md#73-tool-contracts-and-exact-catalog) and
the [paired contract](https://github.com/NielsdaWheelz/skidbladnir/blob/ab9e0acf0c01e2a94d785016cd9500e20bac1787/docs/jarvis-orchestration.md)
own the full existing schemas. no new product choice is required.

## goal and boundaries

launch codex/claude workers with optional initial input, inspect/control existing
sessions, and observe a captured target without blocking main. keep truthful
creation/input/outcome facts through failure and restart.

jarvis owns admission, receipts, observation lifecycle and owner notices. skid
owns worker identity, provider control and lifetime; dev-server owns installation.
kernel/provider-runtime/llm-tools retain their existing native/tool contracts.
workers are trusted execution domains; jarvis connector approvals do not contain
their effects.

no new table, worker registry, task/reply packet, exact request-result correlation,
mandatory coordinator, polling model turn, scheduler or subtree cancellation.
o7 owns records; [o9](delegated-follow-through.md) owns discretionary follow-through. current source
requires owner-grounded writes and permits isolated wait-event silence. [o6](one-main-events.md)
owns the separate broader event-authority/selective-notice cutover; adopt no part
of that policy implicitly in o8.

## capability and api

reuse closed models in `agent_tools.py`; every write retains `ActionRequest` and
the existing serial action lane. target is `{machine,handle}`: machine is
`macbook`, `devbox` or `arch`; handle is `t-`/`c-` plus 16 lowercase hex digits.
profiles are `personal`, `work`, `work2`, `claude-work`. names are labels.

| tools | contract |
| --- | --- |
| `agent.list` | machine/group/unassigned filters; group and unassigned exclusive; preserve empty versus partial/unavailable inventory |
| `agent.info` | target; preserve observed status and method availability |
| `agent.start` | machine/profile required; optional name/cwd/group/model/effort/prompt; omitted provider values retain account defaults |
| `agent.read` | target, source latest/history (history native-only), `maxBytes = 16384`, range 1–32768; preserve scope/truncation/output state |
| `agent.send`, `agent.text`, `agent.keys` | send uses guarded terminal input for either provider; explicit c-target selects native input; text/keys terminal-only; claude native input unavailable |
| `agent.stop`, `agent.close` | stop targets terminal/native explicitly; native claude interactive stop unavailable; close terminal-only, `terminal_only = false`; interruption and closure remain separate facts |
| `agent.wait` | target, `state = idle`, `timeout_seconds = 300` (1–86400), `maxBytes = 16384` (1–32768) |
| `agent.cancel_wait` | original wait `action_id`; returns cancelled/already_settled; observation only |

wait states: t-target idle/working/needs-input; c-target idle/blocked/done/failed/
stopped. prompt/text is nonempty, at most 32768 utf-8 bytes, no nul, literal stdin.
model/effort is at most 256 bytes without whitespace/controls. name uses skid's
existing 1–64 ascii grammar. keys use the existing 1–16-key allowlist. retain
cwd/group bounds and encoded-body preflight; never crop input to make it fit.

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
changed panes/successors never renew it. codex native stop retains its captured
turn; claude's background helper selects its job at dispatch, not admission.

fixed argv/config/json, no shell. concurrent stdin/stdout, discarded stderr,
existing 1 mib inventory/64 kib other stdout caps. retain 20-second child fences
and current 20/45-second tool deadlines; cleanup kills only the cli child.

## durable composition

external start/send/text/keys/stop/close are `BilledOnce`: one executor entry.
known staged `agent_control_v5` evidence settles through the same classifier on
restart without dispatch. missing/unknown evidence remains uncertain; never
relaunch/resend automatically. native accepted-send evidence is unstaged, so its
pre-settlement crash remains uncertain.

wait/cancel are local `ReDispatchable` actions: two lifetime entries, zero worker
mutation attempts. reuse `ActionStore`/`ActionPositionRecorder`:

```text
registration_receipt = {action_id,target,state,deadline,recorded_at,
                        arguments_digest,status:"watching"}
action.result = {registration_receipt,wait_outcome:null | AgentWaitOutcome}
wait_outcome = {target,outcome,recorded_at,cancellation_action_id?,
                status?,terminalStatus?,output?,failure?}
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
further worker input or new waits require current owner input until o6 cutover.
startup resumes observation and
repairs missing events/stranded inputs through existing primitives. in current source, stop/pause/
quarantine suspend registered observation while its deadline advances; resume may
timeout. stop cancels unentered authority, not an entered wait or worker.
shutdown cancels read children and joins database settlement before ownership ends.

## designer's content contract

brief: concrete objective, useful context/scope and requested evidence; ordinary
prose, no template or report protocol. results identify the worker and what
happened; include unknowns/next steps when material. distinguish creation, dispatched
bytes, native admission, observed state and evidenced task completion.

good brief: `inspect the authentication flow in /srv/example. explain the expired-session 500; no code changes. include files and evidence.`

good partial result: `auth-review was created on devbox, but its brief was not sent. the worker remains available; the launch will not repeat.`

good observation: `the worker reached idle; its latest output was unavailable, so i cannot verify the result.`

show material limits/blockers/questions; routine observations may remain internal
under the selected notice contract. idle/latest prose supplies no exact task
attribution. close never proves shared work stopped. content review judges facts
and usefulness, not wording; no new runtime critic.

## non-overlapping delivery

| owner | exclusive files / deliverable |
| --- | --- |
| jarvis adapter | `agent_tools.py`, `agent_control.py`: existing schemas, capture, transport/watcher; change only for a demonstrated defect |
| jarvis durability/composition | `actions.py`, `write_dispatch.py`, `service.py`, `native_journal.py`, `tool_composition.py`, `write_policy.py`, `definitions.py`, `cli.py`: existing receipts/events/admission; applies designer content |
| skid release | publish immutable artifacts containing the implemented paired contract; no new worker protocol/source redesign |
| dev-server installer | `devbox`, `assets/skidbladnir/release-pin.json`, `lib/skidbladnir.sh`, `ansible/playbooks/gateway.yml`, `SPEC.md`: paired cli/gateway pins and canonical-pause preflight |
| jarvis deployment | `deploy/activate-release`, `deploy/install-agent-client`, `deploy/install-private-state`, `docs/operations.md`: preparation boundary, explicit target selection and bootstrap order |
| temporary qualification | scoped proof files only; installed artifact/configuration and actual service/discord evidence |

source is already qualified; remaining code repair is the installer boundary.
dev-server still reads retired `jarvis-paused.v1`; native jarvis rejects that file.
use the target release's existing `jarvis check-paused` as jarvis:jarvis with the
existing runtime env files/systemd restrictions. retain stopped-service and
identical-byte/owner/mode no-op checks. no direct database query or file fallback.
the private-client installer must use that same target, not an obsolete `/current`.
track this in [cli cutover](issues/skid-terminal-flags.md).

planned deployment inputs:

- `deploy/activate-release FULL_GIT_COMMIT --prepare-only`: reuse one preparation
  implementation for release/env/clean-stop/contained-host checks, migration and
  native conversion. finish with target `check-paused`; exit before activation
  checks, service-unit/current changes or startup. ordinary activation reuses it.
- `deploy/install-agent-client FULL_GIT_COMMIT`: require the explicit target.
- `deploy/install-private-state`: install environment/connector secrets only;
  remove its eager client call, unused client input and misleading success text.
  client installation is explicit after canonical pause preparation.
- dev-server `devbox` forwards invocation input `JARVIS_RELEASE_COMMIT` as gateway
  playbook `jarvis_release_commit`: pass it as the preflight's
  fourth argument, replacing the pause-file path. require it for replacements;
  identical installs remain inert.

one full 40-hex commit selects admitted `/opt/jarvis/releases/COMMIT` for all three.
validate its existing `RELEASE.json` and executable through existing release
admission rules; never select arbitrary paths or fall back to `/current`.
reuse the deployment lock/retention rules; preparation preserves the candidate.
adoption supersedes adr 0052's full-private-state/client composition and updates
the runbook; no no-argument client-install fallback.

## cutover and acceptance

1. drain/reconcile predecessor actions and owed outcomes/delivery; pause and stop.
2. provision runtime environment/secrets and install exact target/contained host
   without starting jarvis; complete existing preparation/native
   conversion first. a fresh database needs migration and public
   `initialize-state` instead of importing predecessor state.
3. target `check-paused` must pass before changing gateway/cli/private client.
   missing canonical pause, competing owner, unavailable database/qualified
   release or retired files refuse; preserve current executables on refusal.
4. install paired artifacts/configuration, run target pre-start activation checks,
   activate PAUSED, then run `deploy/verify-containment` before explicit owner
   resume. installed turn journeys require authorized resumed admission.
   finalized v1–v6 worker bytes stay opaque;
   unfinished retired state refuses activation. no compatibility decoder.

rollback requires proof the prior release reads current schema/contracts and
paired configuration. incompatible conversion or new receipts requires preserving
evidence and forward repair. code rollback cannot undo worker effects; never
restore over them.

reuse [source qualification](native-agent-integration.md#qualification); do not
manufacture new red evidence for already-green source. for the installer defect,
temporary end-to-end red proves native pause/fileless bootstrap fails today;
green proves target selection, refusal-before-change and inert identical installs.
also prove fresh secrets → migration/initialize-state → checker → client →
paused activation. use actual postgres/public pause checker plus host installer
boundaries.

remaining installed live acceptance: both-provider explicit/omitted launch options
and literal input; partial/refused/unknown effects with no mutation replay;
original-ref refusal on changed targets; register then serve unrelated owner input;
restart with original watching receipt and one outcome/event; cancel/match and
pause/deadline/shutdown; actual delivered notices under the selected authority/
notice policy. use synthetic briefs and real installed service/native/cli/provider/
discord boundaries; controlled ports do not prove installed behavior.

review each boundary, get green, refactor only demonstrated duplication, rerun
changed concerns/final journeys and have the designer review recorded content.
retain artifact/status evidence, then delete temporary tests and run
`scripts/verify`. unavailable boundaries remain `NOT_RUN`. no live tests,
publication, installation or activation are authorized by this documentation task.

trade-offs: ordinary conversation gives semantic judgment instead of exact task
correlation; bounded/non-atomic reads limit evidence; lost acknowledgements can
remain uncertain; capture plus one read child per active wait costs subprocesses.
hard cutover requires coordinated downtime and updated operator commands for
explicit release selection/split bootstrap. temporary-test deletion reduces
retained regression coverage. no new table, framework or shared-library api.
