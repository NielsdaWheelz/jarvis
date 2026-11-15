# action event context

problem: `native_receipt_context` parses action-event source identities as bare
uuids, but both publishers use `<action uuid>:<status>`. worker-wait publication
also omits the structured action/origin metadata emitted for other outcomes.

impact: a durable result can fail before reaching main; continuation cannot rely
on consistent causal evidence.

evidence: source `8c0bf36`, `native_runtime.py:841–868`, `actions.py:1607` and
`actions.py:3139`; read-only audit, 2026-11-14. no behavioral proof run.

reproduction: persist an ordinary action resolution, select its host message,
then construct the real runner's receipt context. uuid parsing receives the
deduplication key, including its status suffix.

resolved when [slice 1](../one-main-events.md) publishes both kinds through the
common transaction-level append, records validated action/parent facts and loads
receipts by structured action id. prove persisted outcome → real journal/runner
composition, duplicate publication and conflicting identity rejection; retain
original receipts. delete this record after accepted proof.
