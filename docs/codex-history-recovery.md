# capture the selected codex history after a rewind

the owner authorized selected-history capture. keep all stored originals and recover eligible replies in the version codex currently serves. older versions that codex no longer serves may contain uncaptured replies. this supersedes the proposed all-version import, source roster and operator admission of separate versions. [adr 0103](decisions/0103-codex-history-admission.md)

## reader contract

enable this policy for `macbook/codex-work` paginated histories. the collector normally reads its checkpoint inclusively and checks both available digests. when codex removes that checkpoint, reuse adr 0089's two complete, matching, non-active reads of the selected history to prove it absent. from the same verified read, return the next bounded page after the original exclusive admission cut, or from the beginning for a beginning cut. a missing non-null cut parks as `activation_boundary_lost`. a changing or incomplete read cannot recover the cursor. a present checkpoint with a different digest remains `source_conflict`.

provider-runtime owns native stability, selection and a result flag identifying a verified read from the cut. the collector checks the old receipt and uses the same bounded upload path. central ingest atomically checks the expected receipt generation, checkpoint and digests, reuses matching complete originals by native id and digest, and appends unseen originals with their existing provenance. keep the old archive uuid, leaf positions and sequence numbers. append new records in native order within each accepted batch and retain central arrival order across commits. equal text with different ids remains distinct. preserve native fork attribution.

once a page commits, resume inclusively from its last occurrence, even if its records were already stored or the page contains only skips. when the selected history contains no eligible occurrence, keep the old checkpoint and try again as ordinary polling observes later activity. an ingest committed before a lost acknowledgement is recovered from the next receipt. the same checkpoint can recur after a rewind. migration `0022` adds one generation counter per conversation. `native-archive.v5` requires it on every ingest and park request. advance the counter under the source lock whenever native progress or a park changes. idempotent no-ops leave it alone. old requests fail even when their checkpoint matches again. the cut upgrades all native collectors together and preserves the `capture.v4` digest domain. no new table, version rows, rollout parser or retrieval tool.

## verification and repair

- native fixture. use a disposable mac codex chat. capture two replies, revert before the saved reply, then add a different reply. distinguish a real, stable rewind from an unreadable cut, changed checkpoint, incomplete history and ordinary continuation on a shared checkpoint. verify later appends.
- archive fixture. run collector → authorized http ingest → disposable postgres → memory open. retain the original's id, digest, all parts and leaf positions. replay saved ids, lose an acknowledgement, retry with the central receipt, reject delayed events and errors after a rewind restores the same checkpoint, and reopen each distinct new reply once.
- installed proof. after the separately authorized schema and collector cut, privately freeze each of the three existing uuids, beginning cuts, checkpoints and 1,554 old parts. use the existing stopped memory-writer `retry-capture` on each exact park. compare the stable selected history to the archive, reopen the three original terminal replies and three selected terminal replies, and verify append progress after natural activity. the two inaccessible older tails stay out. record the gap once without chat bodies or private identifiers. [memory operations](operations.md#memory-operations)

use temporary red → green → refactor → green probes with independent adversarial review. keep hash-verified evidence outside scratch and delete temporary tests after final green. candidate proof and installed recovery have separate receipts. the preceding historical cut owns schema `0021`. preserve its retired event identities and current archive addresses.

## installed closure

on nov 24, 2026, `3e87705c573f00a6053214a371cdfea107a8252b` advanced
production to `0022` under owner web pause 37. macbook and devbox both
selected native v5, and v4 was refused. the stopped production copy
matched all 20 existing table inventories during the mac rehearsal.

the three original admission cuts and all 112 parts surviving the earlier
historical cleanup kept their addresses. selected-history recovery appended
112, 34 and 30 parts once in source order. all three parks cleared, all six
terminal replies reopened, and the retired witness stayed retired. the
backup cutoff contained 19,288 admitted positions. both backup copies
restored against all 21 table digests. owner web resume 38 committed at
05:59:24 utc, and production handed off to the outgoing-mail cut.

the owner closed the incident after the installed proof. a later natural
reply in the three target chats had yet to occur. later append behavior was
proved in the disposable mac journey. the two older inaccessible tails
remain the accepted coverage gap. [full incident and receipts](https://github.com/NielsdaWheelz/jarvis/blob/b7bbe2e9e425fdfd5a84c0088510739e75970396/docs/issues/macbook-codex-work-capture.md#installed-repair--november-24-utc)
