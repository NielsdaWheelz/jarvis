# historical compaction parked on a mismatched address set

on november 23 at 20:57:50 utc, `7e9d887` at schema `0018` parked at
`8232+8` under owner web resume 30. run `02ceabf6-3748-4121-9999-996069a771f8`
prepared five inferred leaves and three inferred parents. terra/medium
completed one uninterrupted turn in 20.313 seconds, reporting 14,312
input and 972 output tokens. the writer recorded `reason=address_set_mismatch`.
the result passed schema validation. its unique addresses differed from
the requested set. the journal gives the first selected address as the
park, but does not identify the missing or unexpected address.

the batch committed zero nodes. readback at 20:57:51 found the error
`invalid_completion`, 16,510 committed nodes and 8,269 of 85,336
positions covered. at 21:01:14 the (level 3, index 1029) parent was
still absent. the two transactions proving the [original range recovery](compactor-native-event-buffer.md)
were present. the sole authorized operator clear was for `8112+8`.
the new mark was preserved. the mac receipts are
`~/.local/state/jarvis/qualification/adr0093-production-20261123/8232-terminal.log`
and `8232-state.json`.

at 23:07 utc the mark, prefix and node count still matched the first
parked read. capture had admitted another 4,380 positions, bringing
the archive to 89,716, with 81,447 positions beyond the continuous prefix.
this check precedes the declared busy interval.

the installed [addressed output contract](../decisions/0080-first-valid-compaction.md)
parks immediately on this result. [adr 0100](../decisions/0100-host-bound-summary-fields.md)
defines the current-main replacement. the private mac receipt
`summary-fields-design-20261124/8232-source-binding.json` binds the eight original
identities and content digests and both child text digests, read under the retained
park at 00:56 utc on november 24. its sha-256 is
`50a2f3de50fd9adfa19cea6556fbea32052c13d990ecbfb62bb57f1cb87b8cf3`.
the isolated reproduction below verifies own-source attribution and
whole-batch validation. [adr 0102](../decisions/0102-historical-capture-cleanup.md)
retires the old installed retry and preserves the stopped evidence. the [busy and quiet
observation](memory-usefulness-evaluation.md#installed-terra-observation) measures the cost of the park.

on november 24 at 01:34:15 utc, a read-only production transaction on
`43ed919/0019` found the same mark under owner web pause 31. all eight
original identities and content digests and both child text digests matched
the 00:56 receipt. parent `(3,1029)` was absent. the two prior recovery
transactions `2399982` and `2400027` were still present. the mac receipt is
`adr0093-production-20261123/window/release-43ed919-20261124T013415Z.json`,
sha-256 `716cc016957809c8ebf2376a728a7801a46b79265e7eef57c8a0f7c05b1fd908`.

## candidate evidence

jarvis `3bcfc51041899c388c861a00bce23630d80ce956` uses kernel
`799cbc6` and universal-memory `1030ab9`. the service and stopped rebuild
each made one contained terra/medium call with five inferred leaves and
three inferred parents. the reversed batches committed all eight results in
one transaction each. both preserved elm's hold pending a survey and oak's
approval on receipt `R17`. those paid runs preceded two final changes
limited to diagnostic event width and rollback before commit. the final
pins passed the full controlled writer suite.

controlled postgres checks on the final pins covered malformed retries,
actual escaped packet sizing, feedback rebinding, kernel stops and lost
events. a late cancellation test first reproduced both a surviving park
and a one-batch commit. the repaired worker left zero rows, a clear mark
and the original prefix on both paths. the next admission committed
independently. the retained capture retry check was repaired to inject
failure at the existing `append_main_events` call.

the x64 schema `0020` guest reproduced the failure shape with a scripted
provider. the target preserved the bound park under pause and refused a
second assistant owner. the installed command cleared once while the
memory lock stayed held. after the fixture's owner resume, parent `(3,0)`
committed in xid `803`, and disjoint leaf `(0,31)` in xid `805`. the prefix
advanced 24 → 29 → 32 with a clear mark. the exact saved reader restored
the pre-clear 24/31 cut and reopened an original event and a note.

the mac candidate manifest is
`adr0100-implementation-20261124/artifact-final/candidate.json`, sha-256
`ebcf2073db05a474c82984d9b843df7170c085b5aea53b39d62b53be3e921b98`.
this is the original isolated `0020` candidate. on november 24 at
04:02 utc production selected `403b1f7/0020` with both writers stopped
under web pause 33. it still held the old mark and absent parent;
the private mac readback is
`adr0100-current-main-20261124/production-0020-pre-rewrite.json`.
adr 0102 keeps the old evidence under its rewrite owner's custody.
the stopped snapshot sha-256 is
`8232ce8d62497401668e11b04e6a2f2cea21bb5aefd5eae2964f3585f7e46005`.
the dump sha-256 is
`e5fcd6dfe41771420ca8ff234b0b7b81ab9c55d633eddb855254020611e01b71`.
the replay stays retired. the current-main writer needs
a same-schema `0021` replacement after the archive rewrite. verify a new
inferred parent, a later independent commit, prefix growth and a clear
mark on the rewritten corpus under separate owner authorization.
[adr 0100](../decisions/0100-host-bound-summary-fields.md)

## current-main candidate

`d93fd66a6e4dcbc05d5db7b6e81c5481dc990aff` integrates the writer on current
main with kernel `6f4ec09`, provider `36c5b34` and library `aa88596`. the
kernel exercises the same codex terminal path on the updated provider.
on actual schema `0021`, the current-main predecessor parked after three
attempts and committed zero nodes. the new writer corrected one malformed
packet and committed three nodes in one transaction. the full and node
maintenance paths passed their generation checks. the actual packed calls
held six and two complete sources at 241,324 and 82,188 rendered bytes.
post-write cancellation rolled back a batch and a park before commit.

the x64 install verified the exact source and all four pins. the exact
reader restored the 21-table fixture, reopened an event and note, verified
retirement of a removed id, and traversed a generation-2 range.
private candidate manifest `adr0100-current-main-20261124/artifact-final/candidate.json`,
sha-256 `6079c082d1dbb900631eb8956a03ab0bfeb8e5dd5682a0e858d408167d55cec6`.
production progress and the two user outcome checks remain open.

## production writer cut

on november 24, `ea2b825` at schema `0022` passed the exact x64 install,
independent opus review and generation 2 postgres proof. one malformed
two-field call was corrected once. the isolated run committed all seven
expected nodes, including an inferred parent from a 2,581-byte frame.
the existing capture/retry regression passed.

owner web pause 41 committed at 06:47:56 utc. both writers were stopped
at 06:48:38. the baseline held 20,070 admitted positions, a ready prefix
of 7,760 and 15,390 tree nodes. the mark was clear and no retry ran.
the selected release and both services were verified at 06:49:32 under
the retained pause. the new backup reopened an event, a note and a
retired reference from both the remote and held copies. its timer was
active at 06:52:10. both v5 collectors retained their installed pins.
all 5,784 original checkpoint boundaries survived, and a later event
was admitted with exactly its declared distinct parts.

the private mac cut receipt is
`adr0100-final-20261124/production/cut-receipt.json`, sha-256
`ab1493c6182ff407a683b67eeff00f0538c60afa810f155daa31c9f761da6cda`.
owner web resume 42 committed at 06:58:17 utc. the new writer committed
absent parent `7628+4` (level 2, index 1907) in transaction `2485198`
at 06:58:32. its two immutable children framed to 2,305 bytes. the
batch completed one contained call with eight fields and committed
all eight inferred parents. disjoint parent `7632+8` (level 3, index
954) committed in transaction `2485200` at 06:58:48. the 06:59:17
read showed prefix 7,854 of 20,234 admitted positions, a clear mark
and both services active. no retry ran.

private mac proof `adr0100-final-20261124/production/live-writer-progress.json`,
sha-256 `c0bb96fb93fe8c240e4dab0a94bbbfe3574e855e0e0cbbba39f6cd12133b907c`.
installed recovery passed. the [capacity window](memory-usefulness-evaluation.md#installed-terra-observation)
and [recall verdict](memory-freshness-installed.md) remain open.
