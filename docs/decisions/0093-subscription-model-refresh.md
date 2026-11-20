# adr 0093. subscription models and memory cost

design for one cutover-ready release, 2026-11-20. scope ends at an isolated, built and qualified candidate. this amends [0076](0076-role-models-and-delegated-choices.md) for fixed roles and [0092](0092-memory-freshness.md) for future compaction. the predeclared installed capacity window keeps its original pins and results.

| role | personal codex at standard speed | contract |
| --- | --- | --- |
| main | `gpt-6.2-astra/max` | private checkout, explicit native children and host callbacks. answer the right request and commit its disposition. |
| compactor | `gpt-6.2-sol/medium` or the single qualified terra/luna winner below | tool-free. one addressed node per input. preserve that source’s corrections, reasons, attribution, uncertainty and tool-only facts. |
| dreamer | `gpt-6.2-sol/xhigh` | isolated memory reads. distinguish evidence from conjecture. zero supported notes is a valid completion. |

163 installed compactor runs reported 1.22m output tokens in 8h35m. the first eight-item sol comparison used 668 versus 897 output tokens, roughly one tenth of production output per inferred node. test representative workloads before claiming savings. the scheduler can spend efficiency gains on historical backlog. no quota cap, runtime router, new ledger, schema migration, embedding change or fleet rollout. prompts, tool contracts, foreground priority, isolated bounds and child/skid choices retain their owners. [diagnosis](../issues/memory-model-refresh.md)

## a. provider and transport

use merged provider `bc9b6cc`, kernel `b26c54d`, stock `0.171.0`, public catalog v4 and restricted catalog v3. reuse their vendor bytes, compiler, hashes and native model/effort/policy checks. validate the authenticated personal sdk row and refuse a reroute. preserve main’s explicit child, direct workspace tools and declared callbacks. isolated roles disable native shell, web, network, mcp and agents. [provider](https://github.com/NielsdaWheelz/llm-calling/pull/61) · [kernel](https://github.com/NielsdaWheelz/llm-agent-kernel/pull/34)

`deploy/codex-host start` passes `-c service_tier="default"` beside the catalog flag. jarvis publish and verify call the provider’s existing `qualify_codex_containment_host(endpoint, required_service_tier="default")`. extend its validator to require the effective tier and its `sessionFlags` origin from the same `config/read`. other consumers need no jarvis-specific tier policy. luna’s vendor row itself defaults to `priority`. for every arm, prove standard against both the model’s default and a priority-configured disposable profile. capture stock’s normalized value, actual outgoing request at a loopback model server and reported thread setting, including the explicit child. reject a conflicting override. distinguish configured, requested and reported tiers. a missing backend charge or served tier is unknown. [stock standard-tier sentinel](https://github.com/openai/codex/blob/rust-v0.171.0/codex-rs/protocol/src/config_types.rs#L492)

the [burst recovery contract](../compactor-burst-recovery.md) owns ordered delivery through transient byte pressure, the finite no-progress boundary, candidate proof and later installed readback. use this candidate and rehearsal for the [installed incident](../issues/compactor-native-event-buffer.md).

on 2026-11-20, independent opus 5.5 approved the candidate design and later installed-acceptance plan at contract sha-256 `01b2196fc28ac1aafa182a20520ca34d2567fdf2bf64b6ce0f94d383f5920277`. review settled local-stall retries, finite post-fence receipt delivery and grace-expiry evidence. implementation and installed behavior require their own proof.

**ownership.** a owns provider `agent_runtime/{codex_containment,codex_sdk,codex_app_server,runtime}.py` for demonstrated gaps, and jarvis `kernel.build_agent_runtime`, `collector` at `ArchiveHome`, `deploy/codex-host` start/publish/verify. adapt configured codex paths to `CodexUnixEndpoint` only at provider boundaries. verify archive discovery/reopen, original checkpoints, filesystem mount checks and claude homes. a publishes any provider correction and aligned kernel pin before release integration.

## b. product roles and recovery

make the packaged `session-compatibility.json` the single executable role declaration. `jarvis-session-compatibility.v4` replaces `qualified_models` and `role_contract_revisions` with closed `roles`, keyed exactly by `main|compactor|dreamer`. each entry holds `model` (catalog key and dispatch slug), `effort` (option key and native wire value) and `revision`. retain application revision and dependency pins. rotate all three role revisions and the application revision from jarvis `2fdc391`. include the selected role entry in the existing compatibility digest. retire `JARVIS_CODEX_MODEL`, both fixed model constants, the model-keyed effort map and shared isolated selection.

resolve `(role, authenticated_catalog) → ProviderConfiguration` from one snapshot per composition. require exactly one offered row and matching effort, freeze catalog revision/row fingerprint and assert the role at its builder. `serve` and `check-activation` compose all three. `dream` builds only the dreamer. full and node-only `rebuild-memory` build only the compactor. full rebuild keeps both writer locks and its embedding credential. node-only works without an embedding credential. serving memory, status and park release make zero cognition calls.

under deployment ownership, after validating canonical control, `_serve` uses `recover_native_products(owner)` before constructing current clients, models or tools. it already fences abandoned attempts and decodes original seals with their saved schema. keep note-save recovery, archive publication and notification at their memory-ready boundary and retain normal per-turn recovery. `check-activation` stays observational. inject missing target catalog into real startup with a predecessor seal. verify exactly one local settlement across restart, zero redispatch, and byte-identical prior read, invocation and action evidence, including uncertain effects. distinguish already-stopped input from pending work. an old live lease is incompatible.

**ownership.** b owns jarvis `definitions.py`, the resolver in `kernel.py`, `cli.py` composition/maintenance/startup, `native_runtime.py`, `service.py`, `settings.py`, the role manifest fields and example environment. preserve existing kernel fingerprints, addressed atomic compaction and atomic dream notes/references/seed progress. qualify a grounded candidate dream independently of the [unknown installed dream failure](../issues/nightly-dream-error.md).

## c. selection, build and cutover rehearsal

freeze the corpus, arm order, rates and grading key before inference. capture the full price per million input, cached input and output for every tested family, including both astra versions. the implementer chooses and minimally redacts a few real excerpts containing a correction and a tool-only result. preserve speaker, source order, byte class and omissions. add synthetic dense tool output, sibling decoys and ambiguous assent. hold out the real cases from screening. retain the exact redacted packet with ordinary private mac qualification evidence and its existing storage protection. remove working copies and source mappings. the qualification adds no encryption system. the same personal provider sees the excerpts during qualification.

| stage | bounded comparison and decision |
| --- | --- |
| screen | on one synthetic addressed batch, run sol/medium and `gpt-6.1-terra` and `gpt-6-luna` each at medium and xhigh. use disposable copies of the release manifest through the ordinary compactor. advance sol as control and the cheapest quality-passing effort per challenger family. advance both if cost evidence cannot order them. a critical-fact error disqualifies that setting. |
| qualify | use unmodified `e7f5916` with its own stock and `gpt-6.1-sol/xhigh` as incumbent. verify its catalog default, host `config/read`, reported thread tier and effective request before pricing it as standard. on each surviving arm and the incumbent, run three paired, order-balanced trials of the same held-out workload from identical raw leaves. drive the tree to the same cutoff and complete all aligned nodes ending there. each arm builds its own children and at least one genuinely inferred ancestor. predeclare enough dense sources to exceed the free-copy bound after framing. check the 512-byte target, 2,048-byte hard bound, atomic commits and actual free/inferred mix. blind the grader. a challenger that parks or misses coverage fails. if the incumbent parks, count work and missing usage, preserve the park, and grade only committed output. an unreachable cutoff, unavailable incumbent or unproved standard tier makes that paired cost comparison inconclusive. require all predeclared facts at their proper addresses and an original-backed correction and tool fact reachable through that arm’s ancestry. missing owner, wrong sibling receipt, or promotion of a draft to authority fails. |
| choose | for each trial divide all attributed generation cost by committed inferred nodes. include retries, rejected and cancelled work. separately report totals for the fixed cutoff, attempted/committed leaves and parents, free copies, latency, and input/cached/output including reasoning, once per native turn. standard credits = ((input − cached) × input rate + cached × cache rate + output × output rate) / 1m. bound unknown cache. missing usage leaves a lower bound. zero denominator is undefined. award a price win only when paired per-node bounds separate consistently in all three trials and total cost for the same coverage does not increase. label conflicting or overlapping results inconclusive. remove dominated passing arms. among indistinguishable survivors prefer sol, then terra, then luna, then lower effort within family. quality can pass with savings unproven. return a demonstrated regression versus the incumbent to the owner before declaring readiness. no qualifying arm means no ready candidate. [rate card](https://learn.chatgpt.com/docs/pricing#token-rates) |

compare one matched incumbent/target main turn as well. report root, delegated and dream usage separately. ship just the selected compactor entry. source and rebuild probes reject other role/effort assignments even when the catalog offers them. no automatic fallback or effort override. the final artifact must pass a real main workspace operation, declared callback and explicitly selected child, original reopen outside the four recent excerpts, a committed compaction, a useful referenced quiet dream, and a controlled valid empty dream and interrupted commit.

**ownership.** c alone integrates all exact dependency pins into `pyproject.toml`, `uv.lock`, packaged manifest and `EXPECTED_GIT_PINS`. c owns `deploy/install-contained-host`, `install-private-state`, release packaging and operations. base source on `2fdc391` and rehearse the installed `e7f5916 → target` at schema `0018`. use dev-server’s `scripts/rehearse-worktree` on macbook, disposable postgres 16/vector, isolated notes/sockets/state and intercepted external effects. only the stock host receives the existing read-only personal auth mount. verify the exact x64 stock executable, companion and required sandbox resources under a mac-hosted full-system x86_64 linux/systemd guest. arm64 or translated userspace alone leaves this boundary unqualified.

isolate the installer’s ssh configuration and host key so `dev-server-deploy` addresses only the guest. run the actual release and contained-host installers there. rehearse owner pause, stopped writers, atomic removal of the retired env assignment, target mapping/host, application socket remount and ordinary `activate-release TARGET`. preserve unrelated protected settings, file ownership/mode, control, originals, checkpoints and effect barriers. failed preflight leaves the service stopped for forward repair. copy no credentials and never rerun broad private-state provisioning to remove one setting. retain the installable source/wheel, lock and verified x64 distribution. the evidence records commit/tree, binary/helper/catalog digests, actual role/policy receipts, blinded scores and cost/unknowns. reopen and hash build and evidence outside scratch. separately report fixture cleanup. retain one candidate. installed activation, ordinary owner resumption and explicit retry/readback of `8112+8` need a later owner-authorized cut. [existing release and custody rules](0088-storage-and-memory-recovery.md)

**method.** each feature has a content designer. a specifies receipts with the observed tier source or queue stage, held bytes, incoming bytes and limit, without payloads. b specifies the scoring key. for example, preserve that an owner moved friday to thursday for a booking conflict, that receipt 17 confirms thursday, and that ‘looks good’ referred to the draft. reject a sibling’s receipt or unsupported assent. a dream cites both premises and names its proposed connection as a hypothesis. c specifies the operator report separating model, sample, missing usage, artifact and cleanup. for each, write temporary end-to-end/live red checks, show predecessor failure, implement, run green, refactor, rerun affected checks on final bytes and obtain adversarial opus review. delete only those temporary probes after review and keep existing regressions. small matched samples establish results on those inputs. they cannot guarantee population-wide fidelity, throughput or a share of weekly quota.

## candidate evidence

the x64 release is jarvis `7e9d88759910b1b73bf2b9b859e171c8b174a559`,
tree `301cd2e1f77a4dda6a46f21257a8eb66c9206be8`, on stock `0.171.0`
and schema `0018`. the wheel, lock, source tar and stock distribution are
bound by candidate manifest sha-256
`cd608597c44253529a35a0fcaed7068dd6da9d9d4b2c76ef770e3b6680f7b727`.
the kernel is `d5bde65eb181d585b5cbae8c3f5eac76f50b6310` and the
provider is `d20c75e13bae81d9ba80014c7611c44a50d625fd`.
[provider change](https://github.com/NielsdaWheelz/llm-calling/pull/62) · [kernel change](https://github.com/NielsdaWheelz/llm-agent-kernel/pull/35)

the selected compactor is `gpt-6.1-terra/medium`. in three blind comparisons
it retained the required facts at their source addresses and used 78.2% fewer
standard-credit equivalents per inferred node than the installed sol/xhigh.
six of twelve nodes exceeded the 512-byte target, with a maximum of 772.
the quiet scheduler remains uncapped. [sample and costs](../issues/memory-model-refresh.md)

the predecessor failed independently at its event-count and byte limits.
the candidate drained preloaded and gated streams, recovered from a finite
local stall and parked on retry exhaustion. true raw loss preserved the
native seal and reported a protocol fault. the executor refused a previously
queued callback after fencing. missing incorporated inputs stayed unresolved.
a live interrupted response also exposed abandoned assistant display ids.
the replacement provider retires observed ids on a validated same-turn stock
retry. previously unseen completion-only output remains usable under the
native seal. stock supplies no identifier for each upstream sampling attempt.

the ordinary guest upgrade preserved the pause, unrelated settings,
originals and parked range. the assistant remounted the new stock socket.
one operator clear on synthetic `0+8` preceded `(3,0)` at xid 1179 and
independent `(1,4)` at xid 1180. all eighteen nodes through ten were
present, the old fourteen survived and the prefix grew from eight to ten.
the journal recorded one terra turn and zero recovered waits. the four-node
deficit closed in 11.43 quiet seconds. [installed closure criteria](../issues/compactor-native-event-buffer.md)

the live astra/max main reopened an older original through the declared
callback, wrote the notes file and created one git object under the
checkout's `.git` root. its explicitly selected sol/medium child returned
the expected result. a grounded sol/xhigh dream cited two reopened
premises, labelled the inference as tentative and atomically advanced
the seed with its note. the owner-message count stayed unchanged.
a controlled interruption rolled back every write. valid empty completion
advanced just the seed. at unchanged systemd limits, a quiet stock stop
took 8.88 of ten seconds and start took 10.98 of twenty. two earlier starts
timed out under contention. [host margin](../issues/codex-host-entrypoint-imports.md)

the exact installed production range `8112+8`, subsequent historical
progress, genuinely sourced owner recall and subscription use remain for
a separately authorized cut.

opus 5.5/high and the independent verifier both accepted this exact isolated
candidate. the private mac record is
`~/.local/state/jarvis/qualification/adr0093-implementation-20261120/qualification.md`.
the joint functional disposition has sha-256
`d08b0ffbaf4db31a4e0d3bf3f20b72931f301a99b8b23ae15406d8e21dfed3f2`.
its component receipts are the opus verdict `84830ec4` and independent
functional verdict `753917c1`. qualification probe cleanup has a separate receipt.
