# adr 0055: save agent-authored notes over mcp

[adr 0060](0060-remove-memory-forgetting.md) removes association-based
exclusion/erasure restrictions and checks below. optional provenance and
idempotent saves remain unchanged.

amended by [adr 0056](0056-let-jarvis-main-save-notes.md): main also gets an internal
note tool backed by the same append function. the original decision below records
the external surface and its unchanged-main-catalog choice at that time.

- status: accepted implementation target, 2026-09-30; implementation and
  behavioral/live acceptance `NOT_RUN`.
- authority: the owner chose an explicit mcp note tool over reflections in
  user-facing replies, and made conversation attribution optional when readily
  available. no identity-discovery work is required.
- amends adrs 0051/0053's external mcp surface, note provenance and erasure
  contract. adr 0054's background batching remains. no new table, native tool
  access for jarvis cognition, or change to main's internal catalog.

## decision

add `memory_save_note(text, submission_id, native_conversation_id?)` to the shared
mcp server. save one validated agent-authored note directly in `memory_log`, with
its wording intact and without another model pass. reuse the existing 8,000-byte
bound, secret rejection, writer, search and asynchronous embedding paths.
background extraction remains responsible for ordinary conversation coverage.

the [implementation contract](../universal-memory.md#direct-note-submission)
defines the closed api, content guidance, schema and acceptance:

- reuse the lane-bound bearer as a client bearer. reads require `connect`;
  saves require both `connect` and `admit`. no native activation prerequisite.
- add one immutable, closed `agent_submission` object to each submitted note:
  host-owned machine/account/provider, caller submission uuid and nullable native
  conversation id. its source-range triple stays null. extracted notes keep their
  complete proven range and no submission object; legacy notes keep both null.
- derive note identity from a fixed namespace, stable lane and submission uuid,
  using the existing primary key for retry deduplication. changed input with the
  same key conflicts. successful receipts mean committed storage, not completed
  embedding. no receipt table, action, approval or additional model call.
- a supplied native id is caller-reported metadata, not verified source evidence.
  no discovery, existence requirement, synthetic source row or later relinking.
  reject known excluded/erased associations; conversation erasure removes matching
  submitted notes and their summaries once the conversation exists in the archive.
  omitted, incorrect or never-archived associations weaken that coverage,
  explicitly accepted by the owner. no separate note-erasure mechanism is added.
- archive save calls and results/errors as content-free references, even when
  failed or missing a receipt. otherwise tool arguments can reintroduce saved or
  erased prose as fresh evidence. ordinary restatement has no semantic ancestry
  guarantee.

## costs and scope

agents spend another tool call and may save noisy or duplicate notes. mechanical
validation does not certify truth. directly saved and extracted notes have equal
evidentiary status; synthesis remains the dreamer's job. optional association
trades simpler integration for incomplete conversation-level erasure. the closed
json object needs shape validation but adds no general metadata system.

retrieval stays pull-only; no hooks or injected memory are added. internal jarvis
roles keep their existing capability envelopes. ship this through the unimplemented
universal-memory migration and existing work packages; extend the small retained
note completion/replay and erasure checks, not the wider testing redesign.
this is documentation only; implementation and behavioral verification are not run.
