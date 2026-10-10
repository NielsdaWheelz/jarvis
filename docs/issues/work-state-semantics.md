# work-record adoption

recorded: 2026-09-30; updated 2026-10-06.

owner resolved the design: mutable current rows, physical deletion and a simple
todo table. [o7](../work-records.md) defines one
state field, ordinary CRUD, content and temporary acceptance. the previous
append-only/history proposal is rejected.

remaining: adopt the table/tool target in spec/adr and implement it. no work table
exists at source `f3b4dc3`; documentation is not behavioral evidence.

resolved when focused real-database/native/live acceptance proves the contract
and receipts, especially physical deletion plus replay without resurrection.
[o9](../delegated-follow-through.md) now specifies ordinary agent judgment and
semantic stop. the owner rejected per-work execution links/eligibility/fencing;
attention states and record edits have no runtime execution meaning.
