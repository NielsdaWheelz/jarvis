# recovered partial ended mid-word and omitted its material limit

open, 2026-11-19 utc. on release `e34608e`, production attempt 129
(`fb21ee30-eb7e-45ae-a38a-6a5f522c1fbd`) returned a partial with a
1,481-character body ending mid-word, the limitation `test` and a null question.
the owner received an unfinished thought and no explanation of what remained
unchecked. the turn completed 26 of 27 inputs and continued the original request.

the sealed stock final already contains those fields. the pinned adapter retains
the completed native message verbatim. a read-only comparison verified that the
1,504-character canonical reply matched the fixed label, separators and sealed
fields byte-for-byte. discord acknowledged that reply. the body reached its
generation budget. the seal provides no evidence of how stock arrived at that
ending. the earlier rendering overflow and its repair are recorded in
[adr 0086](../decisions/0086-native-recovery-and-memory-availability.md).

close this issue when a representative broad request reopened from original
receipts produces a useful partial under comparable length pressure. give it
more findings than one reply can hold and a known gap in coverage. check that
the body prioritizes a supported finding and finishes its thought, the
limitation names the actual gap and its consequence, and the disposition
preserves unfinished work. compare the stock seal to the canonical reply.
keep the single-message budget and lossless host rendering so every new final
can be persisted and delivered as authored. retain the original seal and its
settlement. [main response contract](../../SPEC.md#42-conversation-is-natural)
