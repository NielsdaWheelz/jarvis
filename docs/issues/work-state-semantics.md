# work-record adoption

recorded: 2026-09-30; updated 2026-11-14.

owner resolved the design: mutable current rows, physical deletion and a simple
todo table. [o7](../work-records.md) defines one
state field, ordinary CRUD, content and temporary acceptance. the previous
append-only/history proposal is rejected.

adoption is resolved by [adr 0071](../decisions/0071-simple-event-driven-v2.md)
and [spec](../../SPEC.md). the accepted target keeps optional one-time or repeated
wakes on work records, replacing separate schedule/recurring-wake products;
`due_date` alone is not a wake. implementation and its evidence remain pending.
the earlier source observation at `f3b4dc3` found no work table; this docs-only
change neither implements one nor establishes current deployed behavior.

impact: accepted bookkeeping and work wakes cannot be claimed as delivered.
resolved when focused implementation evidence proves the current contract and
receipts, including physical deletion plus replay without resurrection and the
distinction between due dates and wake configuration. do not create another
standing qualification gate.
[o9](../delegated-follow-through.md) now specifies ordinary agent judgment and
semantic stop. the owner rejected per-work execution links/eligibility/fencing;
attention states do not grant execution authority or stop workers. explicit wake
configuration schedules an input; deleting or changing a record does not reverse
an entered effect. no additional owner design decision blocks this implementation.
