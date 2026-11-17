# calendar write precision prevents positive recovery

status: open; source repair qualified and actual positive recovery observed;
subsequent main progress pending, 2026-11-17.

problem: calendar writes encode fractional seconds and compare their complete
expected timestamps with provider observations. the actual entered create is
present at its deterministic id, but its fractional seconds were discarded.
the original comparison left a known event's action uncertain and blocked the
genuine main journey. later positive reconciliation now resolves that action;
the service remains clean-stopped pending repaired continuation. the original
observation never authorized a repeat post.

evidence: action `5b577ec6-cfbf-4bcc-b89a-3058400d812e` targets deterministic event
`cd56db077dd294490865c195308e1516`. the independently retained read-only
observation at 12:47:37 utc verifies the same owner account and event id. requested
start/end are `2026-11-17T12:56:40.954234Z` and
`2026-11-17T13:16:40.954234Z`; observed values are
`2026-11-17T04:56:40-08:00` and `2026-11-17T05:16:40-08:00`. each differs by
exactly -954,234 microseconds. both preserve `America/Los_Angeles`, and every
other writable field matches. the original arguments and uncertain receipt remain
unchanged. private observation sha256:
`55d6173916a4d101172cdd2c4da6c9b471956461a00748d8cb8d362048ad3540`.

the [events resource](https://developers.google.com/workspace/calendar/api/v3/reference/events)
and [insert contract](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
specify rfc3339 timestamps without promising fractional-second preservation.
list-filter millisecond behavior does not establish insert precision. the actual
provider observation above establishes this mismatch; documentation alone does
not prove it.

approved decision: encode timed creates/updates at whole-second precision and use
that same strict expected normalization for direct receipts and reconciliation.
preserve the immutable original input and exact observed snapshots. reject a
time interval that collapses under this normalization before provider entry.
do not use an epsilon, truncate observed read/precondition values or weaken other
field comparisons. rejecting all fractional inputs is the alternative, not the
current accepted input contract. source proof and actual same-effect recovery
remain separate requirements.

controlled source proof uses the actual connector and the retained normalized
provider shape: the red returns a create timeout and uncertain exact-id
reconciliation. eleven focused green checks cover direct/recovered create/update,
whole-second encoding, one-second/other-field conflicts, exact observed fractions,
collapsed intervals before any request, all-day dates and offset/zone preservation.
original inputs and the retained observation remain unchanged; no authenticated
production request is part of this controlled proof.

actual recovery: inactive candidate `0c3edfc5` uses the qualified stopped operator
and fresh verified owner identity to observe that same deterministic event. the
`2026-11-17T13:52:56Z` positive result resolves the original action to `Success`
without a calendar mutation or another executor entry. the v3 contract, fractional
arguments, entry count of one, both original callback rows and the old resolution
fact's immutable evidence remain unchanged. recovered account qualification stays
null. the atomic transition adds admitted success fact
`f16a39b2-00bf-567d-9b0b-458627ecb5fc`; an independent `13:54:29Z` database reread
confirms the result and the old-plus-new pair of facts. ordinary oauth refresh
does not imply a calendar post. private before/observed/after and independent
receipts retain the original uncertainty. subsequent main continuation is not
yet observed; the original event window was already missed and the fixture email
has never been sent.

resolved when: controlled actual-connector/reconciliation proof reproduces the
observed shape, qualifies consistent encoding/positive recovery and strict refusal
of other conflicts, then the already-entered exact event reconciles positively
without another post. preserve original uncertainty evidence and independently
verify subsequent main progress; source proof alone does not complete the journey.
