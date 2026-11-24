# historical tool corpus

remove routine external calls and results from production shared memory.
keep conversations, jarvis's observations and reports delivered to a parent.
install the prospective filter first. historical removal has its own cut.
[capture decision](../decisions/0098-conversation-capture.md) · [installation](adr0098-installed-capture.md)

## measured impact

the november 23 study counted 62,298 of the first 77,150 positions and
104,581,930 of 111,233,397 retained body bytes after excluding external results
with a child id. a launch can have a child id and a delivered report can lack
one. study note `memory_log/6df7a803-8fe5-5f3d-8a20-a5ade8f39799`.

at 00:46 utc on november 24, production had 92,340 admitted positions and a
ready prefix of 8,269. the table counts *all* codex and claude `tool_call` and
`tool_result` parts at that cut, including potential conversation carriers.

| positions examined | external tool parts / all positions | external / all retained body bytes |
| --- | ---: | ---: |
| whole archive | 75,066 / 92,340 | 127,581,762 / 134,857,675 |
| beyond the ready prefix | 69,212 / 84,071 | 115,950,119 / 120,830,370 |

to reproduce, join `memory_leaf` to `source_record` and `source_conversation`
by id, including `memory_log` for the all-body denominator. use
`octet_length(text)` and the fixed intervals `[0,92340)` and `[8269,92340)`.
this cut also held 1,699 jarvis tool parts and 1,579 external inspection
wrappers with empty bodies. physical storage and model usage require separate
measurements.

## stopped-copy dry run

two isolated macbook restores of the production `0018` snapshot at owner
pause 31 reconciled all 93,679 source parts and 91 notes. pairing known
routine calls with their results inside each conversation, then retaining
both phases when either had a stored citation or fork origin, selected
69,314 positions and 117,301,973 body bytes for removal. the first was
position 8,270. at this cut that would reduce the writer backlog from
85,501 to 16,187. five native checkpoints name selected events and must
retain their original ids and digests.

stored ranges alone held another 5,706 routine positions. the audit kept
all 2,896 jarvis parts, 81 explicit notes and ten dream notes. remove the
1,649 empty external inspection wrappers when their old addresses can report
what happened. explicit saves remain separate.
both temporary databases were removed. repeat `historical-tool-audit-detail.sql`
from the private `qualification/capture-production-20261124/` evidence directory
on the eventual stopped cut. the report is `history-0018/details/audit.json`,
sha-256 `88523524ba73e2212a684b35a989b15d689aefa5bf4967244ab7faedade80958`.

the pinned v4 adapters checked all 1,030 possible-carrier or ambiguous
positions against original sources on macbook and dev-server. three positions
held six distinct peer reports. seven more reports matched linked text that
the old archive attributed to the owner. preserve each once in its receiving
chat with its proved speaker. 101 positions belonged to proven workers.
894 matched a native event without a direct typed utterance. 32 used
unsupported forms. a decoder miss leaves speech unproven. private receipt
`historical-carrier-pilot/followthrough/combined-receipt.json`, sha-256
`29ea5bfdd7d13eacb95ac0b1493155f0c197924279b9e339cd15a627a4bfd103`.

## authorized migration and closure

1. on an isolated macbook restore, classify complete native events and every
   part. use the capture adapters and available original delivery evidence to
   recover attributed questions, answers and delivered reports once, in their
   receiving conversation. retire the raw carriers and mark actual unresolved conversation evidence as a content-free gap.
   reconcile the counts and bytes for each outcome before any production cut.
2. preserve surviving record ids, multipart content, conversations, notes,
   jarvis observations and canonical execution receipts. keep native capture
   checkpoints and fork evidence. prove the next source event appends once
   even where the last checkpoint names an omitted tool.
3. build the tree over the surviving positions. blanking text leaves each
   old position for the writer. version numeric positions and expire old
   cursors so an old citation opens the original evidence or reports its
   retirement. ten dream notes contain 21 range references and cite two
   distinct external tool parts. jarvis inspections contain 14 ranges and
   cite four. keep their provenance and original dream seed bounds, translate
   consumed progress and rebuild affected summaries and search state. reuse
   surviving text embeddings.
4. the owner waived the final rehearsal on a production copy. compare protected
   records and checkpoints, exercise old citations and fresh search, and verify
   the new backup by restoring it. close after the separately authorized
   production cut reproduces those checks. report positions removed, the
   remaining writer backlog, ambiguous cases and actual storage recovered.

native logs keep their own retention. inventory the stopped database copies
on the production host, including the `adr0096` cut, and retire superseded
copies only after verifying a replacement and obtaining the owner's disposal
approval. r2 backups have a 30-day object lock. the independently held mac
copy has its own lifetime. an older restore requires the migration before
its writers resume. the writer was parked at `8232+8`
at the measured cut. its old live recovery test is retired.
[backup contract](../decisions/0088-storage-and-memory-recovery.md) · [writer capacity](memory-usefulness-evaluation.md)

on november 24 the owner waived the measurements and chose deletion first.
the old `8232+8` live recovery test is retired. retain its verified stopped
evidence. the one-time deployment migration must examine the entire stopped
archive, including everything admitted after the pull request merged.
[cleanup specification](../decisions/0102-historical-capture-cleanup.md)
