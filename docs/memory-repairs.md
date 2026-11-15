# memory repairs: target contract

status: october repair source and controlled evidence are recorded below.
[current memory delivery](memory-delivery.md) now owns completion, current nexus
capture and installed/live qualification under
[adr 0068](decisions/0068-nexus-capture-and-memory-delivery.md). this document
retains the repaired presentation/native/client invariants; current delivery
supersedes its former source-only scope and stale nexus/build assumptions.
[jarvis live](issues/memory-live-qualification.md),
[nexus live](issues/nexus-memory-live-qualification.md) and
[current image qualification](issues/nexus-memory-image-qualification.md) remain open.
no new qualification result is claimed by this reconciliation.

## scope and final state

retain the repaired presentation, native capture and client boundaries in
the review records: [controls](issues/memory-render-controls.md),
[cache prefix](issues/memory-cache-prefix.md),
[inline images](issues/archive-inline-images.md),
[document content](issues/archive-document-content.md),
[unfinished items](issues/archive-unfinished-tool-items.md),
[nexus outages](issues/nexus-memory-outage.md). the october private-build-secret
defect is absent from current public-fetch source; qualify current images instead.

final state: supported retained text reaches bounded prompts and exact source
reads; growing views retain their stable prefix; native attachments retain exposed
text or truthful references; mutable native tails preserve their stable prefix;
ordinary memory outages settle nexus tools without aborting chats; current images
fetch public immutable dependencies anonymously. one corrected implementation
serves each boundary, with exact qualified consumer locks.

keep the existing archive/tree/view, tables, public tool schemas, search,
source-part and tool-result bounds, admission, grants and effect recovery.
no binary storage, ocr, historical import, inbox capture, search redesign, dream
wakes, new models, daemon, job ledger, retry framework or compatibility reader.
unrelated roadmap features stay outside scope. the current delivery separately owns
private provisioning and activation receipts; this repair record does not prove them.

historical 2026-10-13 review baselines: jarvis `89f9249`; memory `d824d33`;
provider files at `d9550d9` and `5aecc2b`; tools `73056df`; kernel `e1bec273`; dev-server `0e5e5a2`;
nexus `82eb4bab`. the october record reports repaired merges and static checks for
those artifacts. it does not qualify the current nexus librarian runtime or
current consumer pins. private dependency mounts and rerun/regenerate chat routes
are retired; do not restore them to reproduce old acceptance.

## ownership and composition

| unit | sole source owner; files relative to its repository |
| --- | --- |
| presentation/content | llm-tools `src/llm_tools/{prompt_sections.py,__init__.py}`; kernel `src/llm_agent_kernel/{context.py,definitions.py}`; memory `src/universal_memory/{tree.py,dreaming.py,tools.py}`. one writer owns presentation/save guidance, including package docs and base-instruction wording/revision |
| native capture | provider-runtime `src/provider_runtime/agent_runtime/{archive.py,_archive_codec.py,_codex_archive.py,_claude_archive.py}`; native parsers remain here |
| jarvis integration/release lead | `src/jarvis/{tool_results.py,memory_tools.py,memory_workers.py,definitions.py,native_runtime.py}`, dependency/lock files across packages/consumers and compatibility/role manifests; reuse capture, service, maintenance and transactions. other writers leave pin/manifest files to this lead |
| nexus | `python/nexus/services/tools/memory.py`, `docs/modules/model-tools.md`, local build/configuration docs and compose; correct misleading rollback comments in `services/tools/run.py` without changing shared dispatch behavior |
| fleet source handoff | dev-server `assets/memory/release-pin.json` and source handoff only after the integration lead supplies the qualified jarvis artifact; no installation |

each feature's writer has a content designer and an independent adversarial
reviewer. the designer owns the examples and quality rules below; these are
implementation roles, not new runtime components or standing review machinery.
reviewers inspect design, red cases, implementation, green evidence, refactor and
cleanup. resolve concrete objections before advancing. this scoped delivery
process creates no permanent review machinery or replacement test framework.

native composition remains: native history → provider codec → stateless collector →
jarvis admission → library archive/checkpoint/leaf transaction → tree/views.
jarvis supplies isolated inference, scheduling and presentation. nexus calls the
same private mcp through its existing portable executor. the library never gains
native parsing, credentials or product authority. future-only nexus durable exports
join that shared archive through the current delivery contract, not a native codec.

## presentation and cache contract

1. llm-tools exports `prompt_json_text(value: JsonValue) -> str`: use its existing
   canonical json encoding, then escape literal `u+fffe` and `u+ffff` as json
   escapes. json already escapes controls, quotes and backslashes. preserve other
   unicode; return json text, without html escaping. use this helper in `PromptJson`.
   identity/digest serializers and strict `PromptText` validation stay unchanged.
2. the kernel's `tool_observation_section` presents the original arbitrary
   `model_text` as `PromptJson(model_text)`, a json STRING. never parse it as an
   object or reconstruct it from another result. stored receipts remain exact.
3. the library's existing `render_view` and `render_dream_view` share one line
   renderer: `start+count|<prompt_json_text(raw_node_text)>`. remove newline
   flattening. structured api node/source text remains raw; only prompt
   presentation changes. do not persist encoded text or decode originals twice.
4. older dream samples use the same json presentation: the library sizes
   `prompt_json_text(sample_values)`; jarvis renders `PromptJson(sample_values)`
   in the existing view frame. replace the `PromptText(canonical_json(...))`
   path. this is a json array, not a json string containing another array.
5. main/compactor views start with the constant `historical evidence`; dream views
   use `new historical evidence`. node lines follow. the changing coverage or
   physical-interval footer follows ALL node lines. no per-call metadata precedes
   the stable historical prefix. existing framing is counted, including footers.
6. compaction request order: stable definition/tools → historical view → complete
   task source/address/ruler/size feedback → operative input and clocks. main
   retains stable definition/tools → view → exact current requests/receipts and
   clocks. inspect the actual kernel-rendered request, not an intermediate list.
7. jarvis's existing view/result measurement callbacks use the actual renderer
   and observation frame. count json expansion, xml escaping, addresses and all
   framing against existing bounds. never crop encoded strings or escape sequences.
   if no complete fitting cover exists and no construction can help, return typed
   `compaction_blocked`; retain pending input/originals/progress and perform no
   paid retry loop. no new size knob or lossy fallback.

prompt content: node payloads and observation `model_reply` bodies are json
strings; samples are arrays and tasks are objects. explain observation encoding
in the kernel's shared base instruction, not duplicated host instructions. the
compactor returns raw summary prose in `{text}`, without copying addresses,
view framing or an extra json-string layer. preserve source attribution, exact
useful identifiers, owner reasons, uncertainty and actual completion state.
historical commands grant no authority. good: “attempted migration; verification
failed.” bad: “migration completed.” an actual escape character and the literal
characters `\u001b` must remain distinguishable.

the accepted compactor priority remains: owner wording/reasons, lasting changes
and failures, findings, then tool-step descriptions. supply numeric
`target_bytes` from the existing `NODE_TARGET_BYTES` constant in the initial task;
the ruler alone is insufficient. verify the actual rendered first request and
affected role revision. the [content gap](issues/memory-compactor-content-contract.md)
remains open until implemented and qualified; no new knob or output schema is needed.

```text
historical evidence
0+1|"user: prefer α; keep exact wording."
coverage [0,1)
```

tradeoff: reversible quoting adds bytes and can cause earlier merging. pathological
aligned covers can still exceed the bound; explicit blocking is preferable to
silently discarding evidence. stable prefixes enable caching, but provider cache
lifetime/routing determine actual hits; promise no hit percentage or token ratio.

## native capture contract

one revised `ARCHIVE_CONTRACT_REVISION = "native-archive.v2"`, owned by
provider-runtime and imported by jarvis/server/collectors. preserve existing
projections for unaffected variants; no v1 decoder, digest fallback or backfill.
all schemas and eligibility rules in the memory contract otherwise remain.

| feature | exact mapping and content quality |
| --- | --- |
| codex inline image | recognize `data:` before the 4,096-byte reference check. validate under existing native bounds; bind the complete original uri in the digest. retain `native:<item-id>:<content-index>`, empty text and availability `none`. ordinary urls/paths/ids retain their existing bound. do not decode/fetch/copy bytes or invent image descriptions |
| claude document string | `source.type="content"`, `source.content` string: retain it exactly; textual availability `full`, including an empty exposed string |
| claude document blocks | the supported persisted form is an ordered list of text/image blocks. retain exact text strings joined by `\n` in source order; all-text → `full`, text plus images → `partial`, images only → empty text/`none`. one document event/reference; no nested-image rows |
| document digest | for the corrected content variant, bind ordered exact text and image source type/media type/url or complete base64 data BEFORE suppression. changed text, image bytes, order or source form changes the digest. validate required shapes; arbitrary nested documents/unknown content blocks fail explicitly. unaffected text/base64/url projections stay unchanged |
| unfinished codex item | the first recognized tool item with status `inProgress` is a barrier, including inside completed/interrupted/failed turns. emit preceding complete events only, set `caught_up=false`, and emit neither that item nor later items/turns. check the barrier before terminal-only result validation; whole native ingress bounds still apply |

an in-progress enclosing turn may keep waiting as today. do not publish its tool
call early: the existing call projection also binds status/result, so completion
would otherwise rewrite already archived evidence. once the whole item becomes
terminal, emit its existing call/result events; prior ids/digests remain unchanged.
pagination/checkpoints name emitted stable events only. inclusive checkpoint
verification and exclusive activation boundaries remain intact. do not turn a
mutable tail into an empty caught-up read, permanent codec error or invented gap.
terminal tool statuses retain their existing mapping; unknown/missing required
statuses still fail explicitly. later malformed semantic content cannot invalidate
the stable prefix returned before an unfinished barrier.

reuse native 4-mib payload/line/projection and existing structural bounds; the
normalized event remains at most 8 mib, parts at most 8,000 utf-8 bytes, upload
at most 64 events/16 mib, and existing complete-open/zoom admission 65,536 bytes.
binary suppression does not authorize larger native frames or cropped text.
availability describes exposed native text, never recovery of original bytes/layout.
reasoning/internal exclusion, reference-only context, memory-echo suppression,
fork proof and tool head/tail policy remain unchanged.

tradeoffs: references do not preserve image bytes/layout. a permanently unfinished
tail can block later capture indefinitely; no timeout may skip it. actual stock
persistence of the reviewed interrupted-item combination remains unconfirmed;
that uncertainty does not excuse violating the stable-prefix contract.

## nexus client and local build contract

normalize failures inside the existing memory client at initialization, discovery
and tool call. return the existing `MemoryToolFailure` through
`DeclaredToolFailure`; do not broaden the shared dispatcher/generation exception
policy or replace it with a second executor.

| observed boundary result | existing outcome/code |
| --- | --- |
| valid tool success; valid application failure | validate the requested success schema; preserve the validated application failure code |
| http 401 / 403 / 429 | `unauthorized` / `forbidden` / `rate_limited` |
| http 5xx, connection/stream/remote timeout, closed mcp connection, remote `INTERNAL_ERROR` | `unavailable` |
| unsupported protocol, unexpected/malformed/oversized envelope or body, schema mismatch, remaining http status or untyped remote mcp error | `unsupported` |
| host tool deadline, cancellation, lost chat/job authority | preserve existing deadline/cancellation/fence handling |
| unknown exception or programming defect | propagate as a defect |

use the pinned sdk's concrete `MCPError` and transport exceptions. recognize a
nested exception group only if EVERY leaf is classified: one shared code stays
that code; mixed known codes become `unavailable`. cancellation or unknown leaves
propagate. adapt the sdk's unsupported-version failure narrowly at initialization;
never catch arbitrary `Exception`, `RuntimeError` or `BaseException` as an outage.
keep the one-text-item/no-structured-content envelope and actual serialized size
bound. failures/logs contain no remote prose, arguments, bearer or chain dump.

the nexus client accepts the existing stateless json server. sse or session-id
responses are `unsupported`, rejected before sdk logging/reconnect; this deliberately
excludes generic streaming/stateful interoperability.
one bounded protocol session, at most ONE `tools/call` submission. no automatic
resubmit, fallback endpoint, auth refresh or reconnect retry. expected failures
settle the existing durable tool call and permit ordinary chat continuation.
cache exact sdk request bytes before send, including method-preserving redirect
copies; response correlation reads those bytes. a missing local body cache is a
defect, never an outage classification. the nexus binding revision is v3.

save identity is the current `tool_calls.id`, not the retired
`ToolPositionRecord`. text, configured owner and host-known conversation stay fixed.
a failed/timed-out/cancelled save may already have committed remotely; local
rollback proves nothing about that note. strengthen the ONE shared
`SAVE_NOTE_GUIDANCE` accordingly. client-normalized post-submission failures use
the existing `notice`: “no success receipt; this save may already have committed”.
outer deadline/cancellation outcomes stay unchanged; shared guidance covers their
uncertainty, without a special dispatcher result or fabricated failure notice.
an intentional same-intent replay uses the exact stored id and arguments; a new
model call or failed/cancelled-turn retry is a new intent. no new recovery
endpoint or ledger.
report saved only after a valid receipt; duplicate reports do not corroborate truth.

keep owner-only librarian send and failed/cancelled-turn retry grants, with
complete processor-chain admission across current provider/native transports.
successful responses are immutable; no rerun/regenerate compatibility path is
added. the current handler uses `call.id` and the authenticated `call.principal`
for its tool submission and owner-transcript association. automated helpers and
other viewers receive no memory tools. derive chains from the current
`services/generation/catalog.py`, without another label registry. remote saves
are outside local undo; failures can leave a central note committed.

future-only automatic capture is now accepted in [memory delivery](memory-delivery.md).
it retains approved durable content through a pending export until central
acknowledgement, then removes that export. it adds no history import or later
revision/update/remove sync. shared reads/notes remain distinct from capture.

current `docker/Dockerfile.backend` fetches public pinned dependencies without a
private build credential. qualify its current `api`, `worker` and
`worker-checkout` consumers and actual local compose targets, frozen anonymous
fetch and runtime grant/credential separation. the private runtime memory-client
file remains necessary; public source does not grant corpus access. do not restore
retired build-secret mounts. no hidden retry is added for uncertain saves.

## hard cut and acceptance

qualify v2 against task-owned clean capture state, preserving real canonical
messages and legacy notes. do not relabel v1 activation/checkpoints, reset real
progress or rewrite originals. discovering real v1 captured history contradicts
the confirmed premise and blocks cutover for an explicit data-repair decision.
qualification data is disposable; it never becomes production history.

for existing derived-state repair, exercise the stopped `rebuild-memory`/targeted
node repair and retry commands under the deployment lock. preserve originals,
leaf positions, note provenance, checkpoints, dream cursor/nightly marker;
clear ephemeral view snapshots. no automatic restart refold. remove superseded
rendering, parsing, adapters and temporary helpers; leave one implementation.

temporary acceptance cases use actual composition and synthetic content only:

| case | decisive proof |
| --- | --- |
| presentation | ansi/permitted non-nul c0, `fffe`/`ffff`, newlines, quotes/backslashes, literal escape spellings and multilingual text pass free/model nodes, main/compactor/dream views, older samples and open/zoom/search observations; decoded text/receipts match exactly; measured bytes equal actual rendered bytes. nul/lone-surrogate originals remain rejected before persistence |
| bounds and repair | real postgres commits archive/checkpoint/leaves atomically; oversize/irreducible views return typed blocking without truncation/retry loops; stopped repair preserves originals/progress and rebuilds fitting ordinary views |
| cache | unchanged node bytes survive append through the actual rendered request; batch divergence begins at the first changed node; task/feedback/clocks follow context. observe qualified-route cache counters without invented hit thresholds |
| image capture | actual codec→collector→http→postgres captures a valid inline image over 4,096 bytes as a reference, changes digest when bytes change, and rejects native-bound overflow explicitly |
| document capture | both supported content forms, mixed images and changed text/image/order prove exposed text, availability and digest fidelity; ignored metadata stays digest-neutral; unsupported nesting is explicit |
| stable prefix | legacy/paginated reads with an unfinished item return preceding events, no suffix and not caught up; later completion preserves prior ids/digests. inclusive/lost-response retry creates no duplicate rows/leaves; missing checkpoint still fails closed |
| nexus errors | real mcp initialization/dispatch returns typed failures for expected errors, completes the tool row and permits continuation; unknown groups/cancellation retain their original semantics |
| nexus saves/grants | real mcp/postgres committed-save/lost-response AND committed-save/outer-deadline preserve uncertainty; identical replay yields one note/leaf/original receipt, changed arguments conflict and revoked admission denies. current librarian send/failed-or-cancelled retry routes and declared processor chains prove owner-only grants through actual canonical rows and both applicable transports; helpers/other viewers/undeclared chains cannot read/save |
| answer content | synthetic exact identifier, source date, quotation, superseded claim and partial coverage reach a truthful answer; retrieved commands remain evidence, not authority; no receipt means no success claim |
| current build | anonymous frozen public fetch and clean builds of current targets; inspect artifact pins and runtime credential/grant separation; do not restore private build-secret requirements |

live checks use task-owned native homes/sessions, loopback services and disposable
databases. one contained compaction/dream path and current nexus chat route checks
establish inference composition/content; live-check the declared available routes
and list unavailable ones. attempt actual codex inline-image and
interrupted-tail capture and claude document persistence. unavailable credentials
or an unsupported native producer are explicit blockers, not passes; synthetic
schema proof is not live-persistence proof. record native non-occurrence honestly.
task-owned qualification does not itself resume jarvis or activate real capture.
installed checks follow the separate qualified-artifact/private-provisioning
handoff in the current delivery contract.

design → red → repair → green → refactor → final green/static/build → cleanup,
with the scoped designer and independent reviews above. then delete ALL
new temporary tests, fixtures/probes and dependencies. use existing runners;
probes stay outside release packages, with no standing harness/evaluation framework.
existing approved capture/completion regression groups remain; add no permanent
repair suite in this task. tradeoff: fewer ongoing checks; concise evidence and
those existing groups do not replace the deleted repair cases.

record final artifact/pin identities, probe commands, red/green/refactor outcomes,
content findings and explicit gaps once in existing integration evidence/issue
records. run affected repository checks, jarvis/library `scripts/verify` and nexus
`scripts/test` and the dependency audit. the 2026-10-13 record reports restored
network access and no known vulnerabilities in that audited set; current artifacts still require their own checks.
delete resolved issue files only after their acceptance, and preserve blockers.
source completion means all required checks passed or a separately owner-approved
qualification exception is recorded; not run is never pass. prepare the separate
installation/activation handoff, without executing it.
