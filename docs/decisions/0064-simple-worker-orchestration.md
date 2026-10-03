# adr 0064: simple worker orchestration

- status: implemented design, 2026-10-02; corrected audit defects pass focused
  checks, darwin stock providers, real native consent cognition and real postgres
  process-crash/recovery. linux stock-provider controls, eleven service/cli/
  postgres checks and actual cognitive wait integration pass; installed paired
  fleet, external Discord delivery and production activation remain separate.
- authority: the owner settled the design and accepted retaining source written
  during investigation, then explicitly authorized complete implementation,
  temporary integration/live checks and adversarial review. installation and
  activation remain separate cutover work.
- supersedes: adr 0052's worker roster, ref-only model inputs, native-only send,
  old result codecs and notification/concurrency restrictions. its skid transport,
  authority, containment, one-shot mutation and stopped cutover rules remain.
- amendments: spec §§4.2, 5.1/5.4, 7.1/7.3/7.6 and 9.2. no application table,
  worker registry, request/reply protocol, provider lane or general workflow.

## evidence and decision

baseline source review found that skid session rows carry terminal status, short
handles and process identity that jarvis's old closed decoder rejected. jarvis also
used obsolete terminal flags, required native input for send and decoded an old
compound native-close result. these are consumer contract defects, not evidence
of installed provider failures.

the owner chose ordinary bounded conversation observations for both codex and
claude. jarvis decides reuse, steering, fanout, reading and waiting. it interprets
status/text; idle and latest output prove neither task success nor exact attribution
to a submitted request. no reply tool, task packet, worker ledger, single-open-job
rule or automatic terminal fallback is introduced.

model tools use `{target:{machine,handle}}`, with configured machine labels and
existing `t-`/`c-` handles. list/info/start and controls return compact facts.
wire decoding remains closed and distinct from this projection; refs, machine
uuids, process/account/native ids never enter model results. names are labels.

skid resolves targets: terminal capture uses `info HANDLE --machine HOST --json`;
native capture uses `inspect c-HANDLE --machine HOST --json`. after current-owner
input admission and before the gate/action insert, jarvis captures one target.
`execution_contract.agent_target` stores its short selector, original opaque ref
and normalized identity privately and immutably. canonical arguments are validated,
default-completed `model_dump(mode="json")`, then stored/hashed unchanged; capture
is separate. later execution/recovery uses original `--ref`; no ref codec, alias table
or renewed authority appears. a terminal handle can follow a pane on a fresh
call; captured effects/waits retain the old pane. native codex stop retains the
captured turn and refuses a successor. native claude interactive stop is unavailable;
its background helper captures its job at dispatch, not admission. this slice adds
no delayed background-job pinning. native wait/read/send retain conversation semantics.

retain known profile and optional current matching terminal-name consent context.
native inspect already supplies the profile; optional machine-scoped list can
ground a name only through the complete captured conversation tuple. ambiguous,
missing or reassociated terminals supply no name; native authority remains
independent of terminal presence. this extra metadata read stays within the
existing call budget and never changes target/turn/ref.

start takes optional name/cwd/group/model/effort and literal stdin prompt.
explicit provider values override only their fields; omissions preserve native
account defaults. the coordinated skid launch result carries independent creation,
prompt, optional target/handle/terminal and failure facts. nonzero exits do not
erase a valid envelope. raw known launch evidence is retained privately alongside
the public tool receipt or uncertainty evidence. created plus unsent prompt is a
partial launch; unknown creation/input is terminal uncertainty, without replay.

normal `send` on a terminal uses skid's guarded terminal input for either provider.
`text`/`keys` remain deliberate terminal controls. a `c-` target explicitly selects
native input/stop; claude native input remains unavailable. close is terminal-only
addressing and distinguishes interruption from closure, optionally omitting
interruption with `terminal_only`. closing does not assert shared work stopped.
definite partial close retains both facts in concise failure output and private
evidence. ordinary control `not_sent` is a definite refusal even with captured
identity; only `unknown` dispatch becomes mutation uncertainty.
wire failures retain the closed not_sent/unknown vocabulary. public compound
failures use sent when creation, interruption or closure is known to have occurred;
only definite no-effects failures use not_sent. recovery unwraps the public receipt
before classifying dispatch and retains raw control evidence privately. failed
lifecycle never means no effect.

conclusive staged evidence settles through the same ordinary outcome rules on
restart, without another executor entry. no-receipt uncertainty must still
publish one safe event/fallback. the shared receipt classifier owns both ordinary
execution and narrow durable settlement; recovery never invokes the executor.
native accepted-send evidence is not staged, so a crash before its generic
settlement remains uncertain. no new receipt variant or replay is added.

## durable observation

`agent.wait(target,state,timeout_seconds,maxBytes)` is a local gated write. defaults
are idle, 300 seconds and 16384 bytes; timeout is finite, 1–86400 seconds. terminal
states are idle/working/needs-input; native states idle/blocked/done/failed/stopped.
`agent.cancel_wait(action_id)` is a separate local gated write. both reuse the
existing action recorder and local redispatchable recovery with two lifetime
executor entries and zero external mutation attempts.

registration commits `result.registration_receipt` with action id, short target,
state, exact deadline, clock and argument digest. the tool immediately returns
`status:watching`; lifecycle stays queued. replay always returns that immutable
receipt, including after an outcome. later writes affect only `wait_outcome` and
lifecycle status. observation does not increment or rearm worker-write attempts.

a process-local watcher runs outside main's mutex. each wait observes the original
ref in bounded 15-second skid chunks under the 20-second child fence. chunk timeout
continues until the stored deadline; no model polling turn or input replay occurs.
matched, deadline timeout, target change, unavailable evidence or cancellation
settles once. a matched state may be followed by a separate bounded read; read
failure/truncation remain distinct, and the read is not an atomic matched snapshot.

outcome and one ordinary source-deduplicated action-resolution message commit
atomically. cancellation commits the original outcome/event and the cancellation
receipt together; it stops observation, never worker execution. race settlement
retains whichever outcome committed first. startup resumes registered waits and
replays their receipt, closes stranded original inputs without replay and inserts
missing events. no new wait follows a terminal outcome automatically.
recovered wait reports are rendered from the freshly locked row, so fast
completion cannot pair a terminal event identity with a stale watching report.

pause/cognitive quarantine suspend observation; the original deadline continues.
resume may therefore produce timeout. shutdown cancels only read subprocesses and
joins database work before ownership closes. this does not implement the broader
v2 work table, continuation authority or six-hour main.

only a batch consisting entirely of `agent_wait_event_v1` host observations, with
no consumed owner row, may settle silently. jarvis decides whether an observation
has a useful owner outcome, material blocker or question. mixed owner input,
ordinary action resolutions and scheduled wakes retain existing visible-terminal
or deterministic-fallback behavior. worker evidence never grants new write
consent. once the original owner turn closes, observations permit reading,
integration and notification only; further input or fresh waits need new current
owner authority. the owner explicitly keeps broader follow-through in o6/o9.

## migration, cost and acceptance

worker implementation v7 hard-cuts v6. finalized v1–v6 records stay opaque after
common immutable checks; unfinished retired rows block activation. drain pending
effects, turns, required messages and delivery under the old release before the
coordinated cli/catalog change. canonical data remains; no schema migration or
legacy decoder is added. the gate definition change also rotates binding policy
fingerprints, so activation must validate all unfinished actions.

before new receipts, paired code/config/artifact rollback follows ordinary stopped
checks. adr 0053 requires rebuilding any discarded jarvis release from its exact
commit. after v7 writes canonical receipts, older readers are unqualified: pause, retain
records and forward-repair. whole-state restore must account for new data and
external effects; code rollback alone is not data rollback. no compatibility
decoder is added.

costs: a preparatory capture subprocess per addressed write, one read-only child
per active wait, existing database receipts and events, and no automatic recovery
of a lost mutation receipt. full skid json remains transport/inspection evidence;
compact results intentionally omit its implementation identities.

temporary checks cover strict schema rejection, literal argv/stdin, nonzero
partial launch, original refs, concise projections and notice isolation. 39 actual
postgres/process-exit/restart cases exercise immutable receipt replay, staged
evidence, registration/outcome/event commit windows, cancellation ordering and
true v1–v6 archives; the baseline fails 19 of the original 27. four actual native
cognitive gate decisions prove explicit/grounded targets and absent/conflicting
context. native short capture/read and matching name/profile also pass through
the real adapter. isolated darwin and linux gateways/stock providers exercise
launch, readiness, literal input, draft refusal, bounded read/wait and control.
darwin also exercises pane changes and lost acknowledgements. eleven actual
service/cli/postgres checks prove pending-read coexistence, restart, cancellation,
pause/quarantine deadlines and shutdown joined behind a real blocked commit.
actual main/gate/recaller and durable journals integrate a later wait event silently
with the original receipt/capture and zero additional worker effects. that scenario
tightens the public tool plan to agent reads/wait; embedding and Discord remain
controlled. temporary tests
are deleted after qualification; no retired behavioral suite is restored.

the repository engineering/build composition is `scripts/verify`. its dependency
audit initially identified three urllib3 2.7.0 advisories; the targeted lock update
to 2.8.0 resolves them; this source pr inherits that lock from published main.
the existing three pinned git libraries remain unauditable
by pypi. installed paired artifacts/fleet, external Discord delivery and production
activation remain `NOT_RUN`. local qualification does not close those dependencies.

the audit corrected optional uncertainty projection, conclusive receipt recovery,
native name/profile grounding and launch capture validation. paired skid fixes
encoded prompt admission, creation-only route members and readiness vocabulary.
positive submillisecond waits now preserve datetime precision. a suspected archive
defect was withdrawn against the actual historical format; no compatibility
wrapper was added. the [paired acceptance record](../../../skidbladnir/docs/jarvis-orchestration.md#implementation-sequence-and-acceptance)
owns detailed source/live boundary status and temporary test retirement.
