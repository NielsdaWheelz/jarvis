# the cost of main's working context

open. the installed receipt repair removed the multi-megabyte recovery opening. a broad mail review still accounted for most of main's high-usage attempts. routine events also pay for a substantial opening before main can decide what to do. these workloads need separate comparisons. [original repair](../decisions/0086-native-recovery-and-memory-availability.md) · [earlier steering failure](../runtime-reliability-and-integration.md#installed-accounting-and-context-exhaustion)

## production evidence, november 20, 2026

the retained main journal spans november 18 at 07:00 through november 20 at 19:16 utc. 126 of 235 root attempts had a successful native terminal with reported usage. 108 were the historical pre-inference refusals. one failed because the selected model was at capacity and returned no usage. native success and acceptance of the answer by jarvis are separate facts.

| population | native successes with usage | at least 100,000 cumulative input tokens | at least two million |
| --- | ---: | ---: | ---: |
| retained journal | 126 | 68 | 11 |
| from the receipt repair, attempt 127 onward | 108 | 58 | 10 |
| november 19 at 23:00 to november 20 at 19:16 utc | 64 | 29 | 0 |

the rows overlap. ten of the eleven attempts above two million served the same three-week mailbox review. those ten reported 116,928,050 input tokens including 114,299,904 cached. the first attempt alone reported 58,190,354 input tokens including 57,155,072 cached. it made 37 searches, 218 message-metadata reads across 194 message ids and 84 readable-part reads across 81 ids. it settled two incoming host events and left the owner's review open. across the nine later high-usage attempts jarvis opened original receipts 95 times and read 94 distinct message ids from gmail. only eight of those ids overlapped the original 194. the eventual reply disclosed partial coverage. [installed disposition](../decisions/0086-native-recovery-and-memory-availability.md#production-cutover-evidence)

in the recent window the 64 successes produced 167 recorded sampling passes. stock's post-sampling context had a median of 57,089 tokens and a maximum of 76,089. the 34 single-pass successes had exact median input of 53,912 tokens. the largest cumulative input, 621,791, spanned eleven passes and peaked at 61,293 tokens of post-sampling context. this window contains mail, calendar and status traffic. the older high-usage roots predate the retained per-pass logs.

on the selected release `e7f5916`, 17 single-mail-event openings had median submitted text of 86,848 utf-8 bytes. median orientation was 84,971 bytes. its median share of the host text was 97.8%. instructions and tool definitions enter separately. every fresh main consumes the shared frozen ready view under the current memory contract. [opening assembly](../../src/jarvis/native_runtime.py) · [startup guarantees](../decisions/0092-memory-freshness.md#a-one-startup-view-for-all-clients)

the projector can include full text and action arguments on successive
deliveries. the later retained cohort had 320 openings and 69 confirmed steers
with no same-attempt component overlap. steer frames were reconstructed from
durable delivery ids. that sample cannot measure overlapping historical traffic.
the candidate deduplicates within a frame. new context pointers still require
the adr's repeated-byte or fit-failure gate. [context projection](../../src/jarvis/native_runtime.py) · [adr 0095](../decisions/0095-context-cost.md#b-keep-related-history-addressable)

the counts came from read-only production aggregates. group `native_attempt.terminal.usage` by attempt and join recorded deliveries to message ids to identify common work. measure the first text item in `request.submitted_request.params.input` and the `historical_memory_view` body in `request.submitted_sections` as utf-8. for the recent window match native session and turn ids to the stock journal's `codex_core::session::turn` events containing `post sampling token usage`. its `total_usage_tokens` field describes active context at that sample. terminal `input_tokens` accumulates consumption over the attempt and includes reported cache reads.

## resolution

the owner chose model-directed mail depth, working notes and report retention. compare compact message rows and full original reads at equivalent actual coverage. [adr 0095](../decisions/0095-context-cost.md) owns the contracts, fixtures and acceptance.

the owner approved one shared orientation conditional on recall. the candidate
passed the frozen paired cost and recall gates. installed outcome measurements
remain separate. [qualification](../decisions/0095-context-cost.md#implementation-evidence) · [memory evaluation](memory-usefulness-evaluation.md)
