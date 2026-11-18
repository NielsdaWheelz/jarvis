# native capture blocked by an oversized transcript record

status: open source limitation, 2026-11-16. no implementation defect established.

problem: one admitted `macbook/claude-work` conversation is parked with
`capture_error=event_too_large`. its valid preceding central capture remains
intact; later events in that conversation cannot enter shared memory. other
conversations remain eligible. original native history is preserved.

evidence: a read-only repeat of public `archive_read` at the retained cut and
checkpoint raises `ArchiveError(event_too_large)` in
`_claude_archive.record`, before normalization or any central request. its
bounded `readline` observes more than the existing 8,388,608-byte physical-record
limit. source paths, identities and bodies remain in private evidence; no cursor
was moved or error cleared. the installed collector and new runtime provider's
archive codecs are byte-identical. that observation also had 23 unreadable
pending baselines. the final quiesced inventory on november 18 had 21. those
baseline counts do not establish recovery of the oversized physical record.

the accepted memory contract preserves separate native parser/transport bounds.
this refusal is therefore a truthful coverage gap, not proof that new compaction
code lost material. raising limits, cropping records, skipping a rejected event
or moving an established cut is not authorized by the batching amendment.

resolved when: the original source becomes readable within its supported bounds,
or a separately scoped parser change retains complete native identity and all
eligible evidence with meaningful bound/retry proof. a final owner-authorized
reset may establish a new pending baseline; that is not recovery of this gap.
