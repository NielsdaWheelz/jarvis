# claude transcript metadata and post-cut recovery

recover every eligible parked claude chat under v3 before adr 0098 freezes workers. both releases use the same reader rule for existing and future chats. codex, missing devbox sources and compaction retain their own work. [incident and replay](issues/macbook-claude-data-flow-capture.md) · [v3 contract](decisions/0089-native-capture-repair.md) · [v4 contract](decisions/0098-conversation-capture.md)

## 1. classify at the source

claude code 2.1.329–2.1.331 writes provenance bookkeeping into the conversation file. its tracker updates, loss codes and self-compaction markers have no event identity. the reader currently parks before reaching the next reply.

after `record()` validates a complete jsonl object, recognize only the envelopes below. require exactly `type`, integer `v=1`, `sessionId` equal to the expected native session, and the listed fields. reject extra envelope keys from this rule. a child or workflow data-flow row also requires the matching `agentId` and uses its transcript’s parent as the session. root records omit `agentId`. `uuid` and `parentUuid` must be absent. existing physical (16 mib including newline) and decoded limits apply first.

| native type | additional fields and meaning |
| --- | --- |
| `data-flow-records` | `records` array of opaque tracker updates, plus optional boolean `snapshot` for a full inventory. |
| `data-flow-incomplete` | `codes` array of tracker loss codes. values stay opaque. chat completeness comes from the message stream. |
| `derived-from` | root only. `sessions` is exactly `[{"type":"claude_code_session","id":"<this session>","via":"compact"}]`. |

consume these rows before updating previous uuid, deduplication, tool/delivery state or conversation metadata. they contribute zero events, gaps or checkpoints. every other shape follows ordinary identity and error rules, including uuid-bearing gaps and uuid-less foreign or multiple origins. real fork references, branches and compaction boundaries keep their representations. additional keys or future versions can park. known cross-session branch/import/resume markers can also park and need separate lineage proof.

**reader owner.** extend `history()` in provider-runtime’s `src/provider_runtime/agent_runtime/_claude_archive.py` and document it in `docs/native-archive.md`. on v4 reuse the rule in direct-child `worker()`. only the native header proves worker identity. workflow discovery requires its first physical sidechain user message. pin the lane-wide inventory failure for a preceding diagnostic. public list/head/read, v4 capture, the shared codec, wire and database schema already suffice. [workflow header risk](issues/claude-workflow-leading-metadata.md)

## 2. prove the behavior on macbook

the content designer’s oracle uses session `s`, one text block per message and no timestamps. write user `u` “count the tiles”, assistant `a←u` “two blue tiles”, user `b←u` “turn one over”, then assistant `c←b` “one tile is amber”. expect `u,a,branch:b,b,c`, head `c`, inclusive checkpoint `a`. sha256 of ordered utf-8 `id + tab + lowercase native digest + lf` is `2c1d4b564dec519716117f883403de72b33dd16ebcb294a937a66337fe620262`.

1. reproduce each failure alone through predecessor `archive_read`. in roots, insert delta, snapshot, loss and self-compaction before, between and after messages. between and after child/workflow messages, add diagnostics bearing that worker’s agent id and preserve peer attribution. compare ids, digests, order and head to clean controls. a metadata-only tail cannot advance the checkpoint. test both lines for an extra envelope key, wrong session/agent, uuid-bearing gap checkpoint, uuid-less foreign/multiple origins, real fork/context, partial tail and oversized row. on v4 compare raw and capture to their respective controls, both digests and worker exclusion after leading metadata in a direct child.
2. the recovery designer freezes expected parts, omissions and reply hashes. use the normal collector → authenticated http → postgres 16 → `memory_open`. prove an exclusive cut, inclusive multi-page retry, lost acknowledgement, conflicting checkpoint and later append. require one copy and atomic parts/leaves/checkpoint per accepted batch. failed batches leave their prior receipt intact.
3. demonstrate red, implement, pass green, simplify, rerun. independent opus reviews the final diff and evidence. run existing capture regressions. use dev-server’s `scripts/rehearse-worktree` for detached mac proof. reopen and hash named evidence outside scratch. delete only new probes/fixtures and report fixture and checkout cleanup separately. the oracle survives probe deletion.

## 3. release and verify recovery

**release owner.** at 00:59 utc november 24 both collectors ran jarvis `8c82c5f`, provider `f72155db`, kernel `c8ed590`. central ran `7e9d887`/`0018`. fleet main selects v4 `3841c0f`. build v3 from the installed line. update kernel and jarvis `pyproject.toml` and `uv.lock`, then jarvis `src/jarvis/definitions.py` and `src/jarvis/session-compatibility.json`. `src/jarvis/collector.py` consumes the provider. forward-port to the selected v4 source and qualify its own pins. tag exact provider, kernel, jarvis and fleet commits. retire v3 selection at cutover. two builds buy recovery while workers are eligible.

base the temporary `dev-server/assets/memory/release-pin.json` on `fbca2e8`, the last v3 pin. `memory_install` also writes profiles and instructions. render from each host’s provisioned assets and private bundle. verify byte parity outside the collector before approval. even `fbca2e8`’s memory instructions differ on today’s mac. install only the authorized build while v3 serves. start on macbook. devbox shares the reader for future chats and needs its own named rollout scope. verify active process, loaded pins and authenticated lanes after each host. a host failure pauses rollout for forward repair.

**operator.** replay the actual candidate read-only from each original cut and inclusive checkpoint. privately compare the frozen manifest, bound any new suffix, and prove v3 normalization and the later reply hashes before proposing a retry. pending baselines take their first stable head as a fresh exclusive cut. submit exact collector/dependency/fleet and central revisions, hosts, individually justified uuids, expected arrivals, downtime and utc window for owner authorization. coordinate with 0098 and the historical-processing session. report actual outage times, retry set and backfill arrivals during november 24 17:00 to november 25 17:00 utc.

after v3 recovery, the 0098 owner verifies the `0020` capture rollout. the historical writer owner then qualifies current main, proves `8232+8` and finishes a subsequent busy/quiet measurement before any production rewrite renumbers positions. cleanup development can proceed in parallel. [owner’s cut order](issues/historical-tool-corpus.md)

hold the release lock, stop `jarvis-memory.service`, compare each stopped row to its approved cut, checkpoint pair and park. run `jarvis memory retry-capture SOURCE_CONVERSATION_UUID` once per matching row as os `jarvis-memory`, db `jarvis_memory`, under its writer key. verify only its diagnostic cleared. preserve changed or reparked cases for diagnosis. restore the same release/unit on every exit and resume ordinary capture. [memory operations](operations.md#memory-operations)

**closure per conversation**

| frozen cohort | chats | saved checkpoints | expected new events | later reply witnesses |
| --- | ---: | ---: | ---: | ---: |
| roots | 5 | 1 | 1,372 | 5 |
| children/workflows | 34 | 4 | 2,825 | 22 |

compare every ordered native id/digest to central from its original cut or checkpoint. these 39 include zero forks. an additional fork permits omission only with native direct-origin proof and complete central parts matching that origin digest. verify prior parts, unique contiguous parts, one leaf per part and acknowledged advancement to the frozen terminal pair or a verified extension. reopen each witness through installed paged `memory_open` and compare its normalized text hash. verify a fresh ordinary reply in one unaffected same-lane chat.

four workers already retain their terminal checkpoint pair. when replay finds an empty suffix, require a new caught-up acknowledgement at that same pair, a cleared diagnostic and identical prior parts and leaves. count these separately from the 35 chats with missing post-cut data.

before `0020`, require each closure receipt or an owner exception naming the outstanding ids, plus a qualified v4 collector with this fix. `3841c0f` predates it. report recovered, still parked and missing-source counts separately with totals and hashes. [stopped cut](operations.md#stopped-conversation-capture-cut-from-0019-to-0020) · [separate nul and missing-source cases](issues/macbook-claude-data-flow-capture.md)
