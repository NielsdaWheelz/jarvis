# native agent integration

status: `8f91c3b` frozen noneditable worker-v7/native composition qualification PASS.
actual personal model/high, web read, prose progress, steering, completion and
sealed stop pass; real-postgres callback/wait and controlled release proofs pass
separately. exact pins and receipts remain owned by the shared integration owner.
pre-merge `796fb8` broader receipts remain historical. deployed systemd
activation and physical google/discord integration NOT_RUN; this is not a
deployment receipt. branch: `feature/native-agent-supervision`.

authority: [adr 0065](decisions/0065-native-agent-supervision.md), shared kernel
native spec section 18 and n4. the pending universal-memory/delegation roadmap
does not alter this cutover.

## contract

- main is `NativeDefinition` plus one `FrozenToolPlan`; contained isolated roles
  still use `AgentDefinition` and `run_one_shot`. the exact configured main route
  remains personal `gpt-5.6-terra`, reasoning `high`; no aliases or model fallback.
- `JarvisOwner` requires the existing dedicated postgres owner connection and
  immutable owner permit. conversation locks order request/control, attempt,
  invocation and action authority. losing that connection stops that process.
- `native_attempt` stores original prepared request, provider attempt, native
  binding, independent submission/local/control/terminal facts and product outcome.
  `native_invocation` stores immutable callback identity/lineage, frozen contract,
  validation and original read/action reference plus reply. `native_input_delivery`
  stores initial/steered input identity and actual delivery evidence. no fourth
  native store, parent-outcome inference or second effect ledger.
- provider `terminal_to_json`/`terminal_from_json` are the sole terminal codec.
  native sealed evidence is persisted before strict application validation.
  `AgentNotSubmitted` requires authoritative provider evidence; exceptions and
  missing native ids never prove non-submission. local stops never become seals.
- callbacks use existing `ToolExecutor`/recorder/budget primitives. cumulative
  main quotas are null; serial in-flight and finite operation bounds remain.
  repeated callbacks keep original invocation, original input lineage and reply.
  the action owner supplies one validated original-result projection for wait,
  schedule and private worker-control envelopes; reply recording and replay
  read it in the existing journal transaction.
- every write publishes `ActionRequest[original input]`: required `request_ref`,
  nullable `existing_action_ref`, exact `arguments`. the action ledger stores the
  complete envelope; classification/consent render its operation payload. only
  the canonical delivered owner request can grant new effect authority.
- fresh reasoning reuses old accepted action/read references. unknown entered
  work blocks redispatch. canonical context includes all actions of unfinished
  requests even when their callbacks leave the recent-observation window.
- progress commits canonical discord outbox without completing owner requests.
  a closed `JarvisTerminal` contains explicit complete/continue/waiting dispositions.
  its mutually exclusive required type literals use portable `anyOf` on the wire.
  malformed raw output cannot fall back to valid-looking final text.
- stop commits control and outbox, permanently fences old callbacks, cancels
  unentered approvals/queued work and retains entered effects. ingress, approval
  and delivery remain live during reasoning. entered effect tasks survive callback
  cancellation. resume re-pends stopped requests with new approval identities.
- an original sealed terminal can settle locally under the new owner without
  another provider call. a later stop/resume makes old product settlement stale
  while retaining original terminal evidence. otherwise restart fresh reasoning.

## stopped cutover

1. stop the old process and drain/reconcile entered legacy effects with its
   original release. ambiguous/entered legacy actions and unknown billed-once
   old-main reads block both conversion and activation, even without old files.
   no old read decoder or execution path is retained.
2. install the exact qualified shared pins, apply migration `0005`, then run
   `jarvis cutover-native` under deployment ownership. it validates all old
   unentered payloads before one transaction, retains original evidence, cancels
   old authority, re-pends requests and creates fresh approval identities.
3. import old pause truth as canonical control, then remove old pause/admission/
   session files. startup rejects remaining legacy execution authority/files.
4. start only after the integration owner qualifies the installed artifacts.
   do not resume a paused/stopped service implicitly. existing scheduled wakes,
   isolated memory, google connectors and action reconciliation remain.

## qualification

the [shared acceptance evidence](acceptance.md#native-cutover-acceptance) owns
exact artifact/receipt identities. `8f91c3b` installed bytes match source. its
actual official web read, phase-aware prose, native new input, both completions
and sealed stop pass. controlled real-postgres proofs separately qualify v7 wait
registration/product/observer/stop and initial/duplicate/existing-action native
callback results for waits, controls and schedules. controlled release proofs
cover loaded-host pruning and the shared host-install lock. earlier `796fb8`
content, delayed-fact, nested gate, recovery, migration and action/crash receipts
remain historical; no controlled peer substitutes for actual research. temporary
probes were deleted after integrated green; shared kernel conformance remains.

controlled boundaries in those probes: saved empty recall, rememberer enqueue,
unused private connectors and discord outbox inspection. they do not qualify
memory models, google mutations, worker commands or physical discord delivery.

observed red -> green: stock native output rejected `oneOf`; replacing only the
discriminator annotation with the equivalent closed ordinary union passed actual
strict output. stale local brave credentials returned `SUBSCRIPTION_TOKEN_INVALID`;
the authorized deployed credential passed both research tools without tool changes.
new postgres proof rejected json-null optional facts and malformed frozen-json
serialization; using sql-null optional columns and the public json copy fixed them.
unfinished approval hidden behind 100 callbacks now remains in canonical context.
an approval task could lose its fatal error after its gateway caller cancelled;
the service now retains that task, stops processing, and reports its error after
owned tasks are closed. this adds no separate effect ledger or task supervisor.

trade-offs: computation may repeat after loss; serial effects limit throughput;
journal commits add latency; conservative recovered write matching sometimes
requires fresh owner intent. deleting target probes after final qualification
reduces retained regression coverage, as explicitly requested. no release claim
is made from controlled peers or source overlays.
