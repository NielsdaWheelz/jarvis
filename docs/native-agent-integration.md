# native agent integration

status: candidate implementation; source qualification passed. final installed
immutable pins and release qualification remain owned by the shared integration
owner. this is not a deployment receipt. branch: `feature/native-agent-supervision`.

authority: [adr 0063](decisions/0063-native-agent-supervision.md), shared kernel
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

temporary probes in `tests/native_acceptance/` remain until final integrated
installed proof; remove them only at the integration owner's explicit release.

| target | evidence |
| --- | --- |
| n016 | real postgres stop before approval/entry and entry before stop; fresh consent on resume retains entered effect identity; live service outbox/new-topic/approval while controlled reasoning waits; entered controlled calendar handler settles once after stop; detached approval failure reaches its service owner |
| n017 | actual worker `SIGKILL`, actual task postgres backend termination, new owner local sealed-terminal replay with no provider methods, unknown billed-read refusal before handler reentry; raw-output and stop/resume settlement races; actual shared-native worker kill/restart completes the original request in a new native thread |
| n018 | real stopped migration retains old arguments/revisions/digests, creates fresh consent, imports pause and removes files; unknown legacy reads/entered effects refuse conversion and activation; repeated callback after steering preserves original lineage; current whole-source strict types and lint |
| n019 | actual stock app-server `0.160.0`, configured personal `gpt-5.6-terra/high`, successful real brave search plus official-page read, strict final and owner completion; separate actual public progress/new-topic native recorded receipt/both requests completed/accepted-native stop |

live source receipts are private task files (mode `0600`), named
`actual-jarvis-main-web.json` under `jarvis-native-web-*` task directories.
research receipt: suffix `bw7l5l_o`; progress/input/stop receipt: `ptmf56w2`.
native process restart receipt: `m2yitmqm`, a tool-free irrationality proof;
this separately proves resumed reasoning, not research-tool execution.
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
