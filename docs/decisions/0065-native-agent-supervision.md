# adr 0065: native agent supervision

status: accepted, 2026-10-02; `8f91c3b` installed worker-v7/native composition PASS
for actual model/high, web read, prose/steering/completion/sealed stop and the
separate controlled postgres callback/wait and release proofs. broader pre-merge
`796fb8` receipts remain historical.
deployed systemd activation and physical google/discord integration NOT_RUN.

adopt llm-agent-kernel SPEC section 18 and its native-agent-spec/plan n4.
the shared contract owns provider/kernel/tools semantics; jarvis owns canonical
requests, action authority, persistence, publication and reconciliation.

main uses one serial native callback lane and optional cumulative tool quotas.
isolated roles retain their actual operation bounds, with current owner permits
instead of paid-capacity reservations. no arbitrary main elapsed cutoff remains.
progress and useful partial answers persist before discord delivery without
settling owner requests. final input dispositions explicitly retain, complete or
wait each delivered request. topic changes preserve unfinished work.

add native_attempt, native_invocation and native_input_delivery, message request/
control fields and action supersedes_action_id. original proposals, request bytes,
native evidence and callback receipts remain immutable. native terminal recovery
requires original sealed provider evidence and frozen output schema/input lineage,
never parent product state or reconstruction of a current callback plan.

phase-aware output amendment: stock codex applies its strict output schema to
commentary as well as final messages. main declares `JarvisNativeMessage`, adding
one explicit `Progress` response (`type = progress`, bounded prose `text`) with
empty `input_outcomes`. under the conversation/attempt lock, stale commentary is
an atomic no-op; live commentary validates the whole raw message, records its
digest and persists only canonical prose. final settlement retains
final-only `JarvisTerminal`; a final progress response fails locally while its
native seal/usage remain intact. no fallback or terminal-envelope extraction.
recovery first decodes against the original frozen output schema, including an
earlier final-only schema, then applies final-only product validation. the shared
native base v3 permits application wire formatting and rotates fingerprints
automatically through its revision/digest. the cost is one additional wire case
and phase validation, preserving the same public prose and final product shape.
frozen noneditable installed content/control, nested gate and fresh-thread
recovery pass with matching source bytes; controlled postgres action/crash
boundaries also pass. exact receipts remain with the shared integration owner;
earlier source-overlay receipts remain historical. no deployment is claimed.

external write schemas contain request_ref, existing_action_ref and the original
typed arguments. action.arguments stores that entire exact input; authority and
approval render the inner payload. resumed old requests may only reuse accepted
actions until fresh owner intent permits another effect. pending approval returns
a durable receipt and independent reasoning continues.

stop, approval and actual dispatch use the same conversation/input/action lock
order. stop cancels unentered approvals, fences native authority and retains
entered-effect settlement. resume requires a fresh successor approval. controls
replace the file-backed pause writer. cold recovery preserves action/read barriers.
original native binding and existing prepared-delivery observations survive
fencing with their immutable identities/evidence. new delivery preparation stays
live-only. recording facts grants no input, dispatch or settlement authority.

delete run_thread integration, its step grammar and capacity arithmetic. retain
actual isolated roles, existing connectors, memory, scheduling and action recovery.
adr 0064's worker-v7 targets, captured refs, receipt recovery and durable wait
watcher remain. native product settlement permits a registered observation to
outlive its completed owner request. only an unmixed wait-event batch without
owner input may settle silently; it records no invented response identity.
mixed owner/ordinary action/scheduled input still requires visible notice. worker
observations grant no new mutation or wait authority.
startup blocks dispatched legacy effects requiring a removed decoder; reconcile
them before hard cutover. no legacy executor, fallback or compatibility alias.

costs: reasoning may repeat after connection loss; serial dispatch limits throughput;
native journal commits add latency; conservative write reuse may require new owner
intent. new acceptance probes are removed only after integrated final-tree proof,
leaving less automated regression coverage by the owner's explicit choice.

contained host amendment: the owner selected a separate personal endpoint under
kernel adr 0011. stock 0.160.0, provider-owned complete restricted startup
catalogue and public version/config preflight replace latest-stable native
admission for this endpoint only. systemd owns the additional host and private
socket mount namespace; no worker credential copy or unrelated server change.
the fixed catalogue costs automatic model discovery and requires explicit updates.
adr 0053's selected-release pruning reads the contained unit's loaded executable
before deleting inactive releases. an unretained live host refuses cleanup;
retention stays selected plus one candidate. this adds one bounded systemd fact
check, not another service lifecycle or rollback store.
