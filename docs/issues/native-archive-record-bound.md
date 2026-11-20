# native capture blocked by an oversized transcript record

status: installed baseline repaired under adr 0089. later capture in the
real affected conversation awaits natural activity.

historical problem: on 2026-11-16 one admitted `macbook/claude-work`
conversation parked with `capture_error=event_too_large`. its preceding
capture stayed intact until the later corpus reset. the old pre-reset tail
and the 368 events preceding the current cut were excluded by that future-only
boundary. the native original remains readable.

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

a baseline reset cannot recover the unsupported original. adr 0089 widens
supported reading while preserving native identity.

at 08:03 utc on 2026-11-19, the current `macbook/claude-work` pending row had
no established cut, checkpoint or originals. its transcript contains one
15,957,980-byte complete jsonl record. it represents a tool result. claude
stores the same 7,978,388-byte base64 document in the result and a companion
field. one copy contributes to the 7,978,982-byte canonical event projection.
the normalized event is 574 bytes, including 147 characters of visible text.

in a read-only, isolated trial on the macbook, a 16 mib physical-record
allowance alone reached the existing 4 mib projection limit and failed. a
16 mib record allowance plus 8 mib for archive tool-result projections read
all 368 events and yielded a stable head with the existing digest algorithm.
the public head read peaked at 181 mib rss in a fresh process. the default
reader failed earlier at 115 mib. these are whole-process measurements on
this one history.

[adr 0089](../decisions/0089-native-capture-repair.md) targets ordinary claude
tool results. user image and document blocks still have a 4 mib native
projection budget. a larger attachment can therefore produce the same refusal.
no affected user attachment was established in this incident.

on 2026-11-20 at 02:23:58 utc the installed collector established the first
stable, exclusive cut at the 368th native event. a read-only check matched all
368 ordered native pairs and confirmed zero stored parts or leaves through the
cut, no checkpoint pair and no acknowledged later read. the installed disposable macbook chat proved later capture and reopening.
resolve this issue after a natural later turn in the affected conversation
commits once beyond its saved cut and its retained reply reopens.
