# adr 0102. remove historical external tool traffic

on november 24 the owner approved implementation and deployment of this
cut and waived a further rehearsal on a production copy and the capture
measurements. the old live recovery test
for `8232+8` is retired with its original evidence in the verified stopped
copy. [capture policy](0098-conversation-capture.md)

ship the prospective filter on `0020`. the one-time stopped `0020→0021`
migration owns historical cleanup. select the entire database under both
writer locks. merge time, commit time and source event time do not limit
membership. a rehearsal or manifest for an older database cannot authorize
a newer cut. an already-migrated database verifies its result on retry.

remove non-jarvis raw calls, results and memory-tool wrappers from active
originals, search and tree construction. preserve conversations, notes,
jarvis observations and canonical receipts. recover source-proven questions,
answers and reports once in the receiving conversation. correct a historical
speaker only with original delivery evidence. mark actual unresolved
conversation evidence as a content-free gap. preserve native checkpoints and
digests, including those that end on a removed event.

keep surviving original and note ids. maintain one content-free table of
retired part ids with their original event and part so an old direct or
full-event link reports removal. insertions cannot reuse those identities.
the compactor reads only live leaves. archive generation 2 assigns contiguous
positions to surviving records and recovered deliveries in source-carrier
order. old bare range and date lookups report retirement, old pagination
expires, and saved synthesis keeps
its original seed bounds and references. translate consumed dream progress,
retain unchanged embeddings, and discard summaries built over old positions.
the ordinary compactor then builds the new tree from surviving evidence.

prove a record admitted after the candidate was built is removed. prove an
older direct original reopens, a removed id reports retirement, a bare old
coordinate cannot open a different record, and the next admitted conversation
event appends once. verify protected rows, checkpoints, the stopped backup,
installed reads and restoration. native provider logs and backup retention
keep their existing owners. the [original issue](https://github.com/NielsdaWheelz/jarvis/blob/da02fbf4fbedc093ab30205e4c39e3c88316e704/docs/issues/historical-tool-corpus.md) records the baseline and the pilot audit.

## stopped production evidence, november 24, 2026

at 04:02 utc both writers stopped under owner web pause 33. the `0020`
archive had 107,097 positions, including 2,924 jarvis parts and 91 notes.
the writer had reached 8,269 positions, with 98,828 still to read. the
operator verified the stopped database dump and the source and target releases.
snapshot sha256 `8232ce8d62497401668e11b04e6a2f2cea21bb5aefd5eae2964f3585f7e46005`.

| material in the stopped archive | events | stored parts | utf-8 body bytes |
| --- | ---: | ---: | ---: |
| external calls | 39,995 | 40,297 | 24,224,252 |
| external results | 39,991 | 46,491 | 124,527,745 |
| external memory-tool wrappers | 1,823 | 1,823 | 0 |
| old text records carrying misattributed deliveries | 21 | 29 | 125,207 |

the stopped census included 143 calls and 143 results admitted after
[the cleanup pull request](https://github.com/NielsdaWheelz/jarvis/pull/94)
merged at 03:30:32 utc. those 302 parts held 499,472 bytes. the two hosts
identified 27 delivered reports, nine questions and nine answers in the
original source, including all 13 reports established by the earlier audit.
no ambiguous conversation gaps remained in the examined cohort. manifest
sha256 `3b1338938bc303555ace2402eb2970aa602140ff423d4065a5d11a8f8e6b8f06`.

the production migration to `58b9ebe` committed 18,507 generation-2 positions.
it retired 88,640 old parts and inserted 50 parts holding the 45 attributed
deliveries. external calls, results and memory-tool wrappers then totaled zero.
the transaction verified the surviving original contents and the protected
tables, including all 5,754 conversation checkpoints. all 91 notes and all
2,924 jarvis parts survived. the consumed dream position translated from
8,184 to 2,366. the old writer park cleared.

at 04:14 utc a fresh authenticated reader reopened a surviving original by
id with identical text hash and source digest. the old result at position
904 returned `retired` by id and full event. an unknown id returned `not_found`.
both bare old range and date reads returned `retired_range`. a generation-2
date lookup succeeded. the initial ready prefix was zero, with all 18,507
surviving positions available to rebuild.

a separate authenticated search returned a recovered worker report second
among 20 results. reopening the full event matched its text, sender, carrier
and receiving conversation against the stopped source. the live store had
zero matches for any retired id or retired source-event identity. private
search receipt sha256 `8a9500a2cbb40d3b02a3dc2f0df98fa4493568f72c67b8fe2812d586cfcc8534`.

the live archive lost 148,751,997 bytes of routine tool text. postgres
reported 839,097,367 allocated database bytes before the migration and
852,245,527 after it. there was no immediate disk-space saving. immutable
backups, the stopped copies and the native source logs retain their normal
lifetimes.

the target reader restored backup `20261124T041557883789Z-944bd4c586cd47fda8c67db8e47cb646`
separately from r2 and from the independently held macbook copy. each
reopened a surviving event and a note, resolved a retired identity and
reported zero failures. both reported 18,507 admitted and zero ready at the
backup. the r2 restore receipt has sha256 `c1566973b4a2f369ed1081d17ab5cb74b154f2c96f7df47f81bb406543962f46`.
the held restore receipt has sha256 `ce0970d655b6628c23e789e8be239ea1d2d1ffa26258174f99b98cd1712fdc3d`.

both services restarted on `58b9ebe`, the private web home answered, and the
backup timer resumed. owner web resume 34 committed at 04:20:28 utc. gmail
completed its next poll six seconds later. at 04:21:08 utc the ordinary
writer had already rebuilt 128 ready positions and cleared the old park.

## native reader correction

the first ordinary owner turn exposed another boundary. native main ran its
shell command, then restarted twice before publishing a reply. two paid
memory searches ended without a returned result. the service recorded both
as uncertain and parked the owner input and fourteen mail notifications.
there were no entered actions. the external memory client had successfully
read the same generation.

on the installed library an empty search encoded successfully, but a single
ordinary text hit reproduced a strict encoding failure. the native tool’s
schema required a field that historical source entries omit. the exact lost
results were unavailable. [the library correction](https://github.com/NielsdaWheelz/universal-memory/pull/14)
fills the declared fields when serializing public results. the regression
exercised all ten record kinds through search, open and leaf zoom, including
historical ranges and synthesis citations. the historical source bytes and
all six declared tool contracts matched before and after.

web pause 35 preceded the same-schema production replacement. `a28e639`
pins the corrected library `2f91195` in the package, runtime manifest and
dependency lock. [jarvis reader update](https://github.com/NielsdaWheelz/jarvis/pull/97)

on the corrected installation, a fresh search returned 20 hits with the
recovered peer report second. the selected native encoder accepted the
actual search (28,818 bytes), full report open (7,241 bytes) and a ready
speech leaf (1,163 bytes). the largest host frame was 30,960 bytes of
65,536 available. the report still matched its original sender, receiver
and content. receipt sha256 `a7a53ee4ea1815dcb9dc7294d5bf1258295449bb04965c7f6794ea1cc8be44d0`.

both independent copies of the corrected backup
`20261124T044706193463Z-fccaaba3b1e24e75b98a3e8294d0b3f3` restored.
each reopened the event, note and retired identity with no failed comparisons,
at 775 ready and 18,952 admitted. r2 receipt sha256
`d78017da1c69b9d5c98bb6f666e727c2500b47981840ba12afc6d9c458f485f5`.
held receipt sha256 `52989cd120e213fb02ed4e1682fde65d83017a6ca09f9171fd0a2b0495a502d4`.
