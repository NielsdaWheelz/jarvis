# adr 0063: native agent supervision

status: accepted, 2026-10-02; implementation qualification in progress.

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

external write schemas contain request_ref, existing_action_ref and the original
typed arguments. action.arguments stores that entire exact input; authority and
approval render the inner payload. resumed old requests may only reuse accepted
actions until fresh owner intent permits another effect. pending approval returns
a durable receipt and independent reasoning continues.

stop, approval and actual dispatch use the same conversation/input/action lock
order. stop cancels unentered approvals, fences native authority and retains
entered-effect settlement. resume requires a fresh successor approval. controls
replace the file-backed pause writer. cold recovery preserves action/read barriers.

delete run_thread integration, its step grammar and capacity arithmetic. retain
actual isolated roles, existing connectors, memory, scheduling and action recovery.
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
