# Architecture decision records

Accepted ADRs are permanent records of why Jarvis is shaped this way. They are
not implementation suggestions.

[adr 0046](0046-reset-testing.md) supersedes earlier test-retention and
verification-execution requirements during the owner-approved reset. runtime
contracts remain binding; dated evidence remains historical. adr 0065 separately
owns the current native contract and its temporary integration/live proof; it
supersedes the affected session, main-loop, host and capacity decisions below.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-small-personal-agent.md) | One small personal agent system | Accepted; trace amended by 0010/0019; internal gate added by 0019 |
| [0002](0002-optmem-inspired-memory.md) | Immutable raw memory and rebuildable views | Accepted; 0051's erasure extension removed by 0061; append-only notes and derived rebuild remain |
| [0003](0003-natural-discord-and-autonomy.md) | Natural Discord and a narrow approval boundary | Accepted; server organization superseded by 0011; generic local-write scope superseded by 0014 |
| [0004](0004-python-codex-and-tool-kernel.md) | Python, Codex, `provider-runtime`, and `llm-tools` | Accepted; session/context amended by 0012; portable-Web ownership by 0014; generic loop by 0017; exact provider boundary by 0018 |
| [0005](0005-reuse-integrations.md) | Reuse working integrations; defer new ones | Accepted; Discord tool scope superseded by 0011; public Web amended by 0014; revoked Google grant re-consent amended in place |
| [0006](0006-no-workflow-framework.md) | No v1 workflow framework | Accepted; bounded agent-kernel distinction clarified by 0017 |
| [0007](0007-central-messages-and-unified-actions.md) | Central messages and one action ledger | Accepted; schemas superseded by 0010; session by 0012; delivery by 0016; action-resolution by 0017; recorder/cross-run mapping by 0018/0019 |
| [0008](0008-embedding-source.md) | Embedding through an embedding-scoped OpenAI credential | Accepted; amends 0004; disclosure scope amended by 0051 (target) |
| [0009](0009-least-privilege-discord-and-host-rendered-approval.md) | Least-privilege Discord and a host-rendered approval preview | Accepted; Discord permissions superseded/amended by 0011 and 0025; approval remains |
| [0010](0010-minimal-durable-state.md) | Minimal message and action durable state | Accepted; tool naming amended by 0013; delivery amended by 0016; cross-run/recorder facts amended by 0018 and 0019; durable park amended by 0020 |
| [0011](0011-single-channel-discord.md) | One configured Discord channel, transport only | Accepted; supersedes Discord organization/tool scope in 0003, 0005, and 0009; permissions amended by 0025 |
| [0012](0012-resumable-session-and-context.md) | Resumable main session over provider-neutral context | accepted; main saved-session resume/CAS superseded by 0065; canonical context reconstruction remains |
| [0013](0013-unversioned-v1-tools.md) | Unversioned v1 tool names | Accepted; occupied-position evidence amended by 0018 and 0019 |
| [0014](0014-minimal-v1-tool-catalog.md) | Exact minimal v1 tool catalog with portable Web tools | Accepted; supersedes parts of 0003 and 0004; amends 0005; schedule tool spelling amended by 0030 |
| [0015](0015-explicit-v1-proactivity.md) | User-facing proactivity only through requested wakes | Accepted; schedule receipt semantics amended by 0019; tool spelling amended by 0030 |
| [0016](0016-provider-native-idempotency.md) | Provider-native idempotency before terminal uncertainty | Accepted; supersedes delivery semantics in 0007 and 0010; schema cost amended by 0018; attempt ceiling by 0019; Discord delivery amended by 0022; Gmail identity amended by 0024 |
| [0017](0017-extract-agent-kernel.md) | Extract the reusable bounded agent kernel | accepted; main step loop and capacity admission superseded by 0065; isolated one-shot and shared ownership remain |
| [0018](0018-serial-kernel-and-bounded-recovery.md) | Map the serial kernel and bounded recovery into four tables | accepted; main step/checkpoint integration superseded by 0065; original action/read recovery remains |
| [0019](0019-ground-writes-and-close-recovery-seams.md) | Ground writes and close the remaining recovery seams | accepted; current-owner grounding and effect recovery remain; main claim/capacity mechanics superseded by 0065 |
| [0020](0020-pin-the-implemented-kernel-boundary.md) | Pin the implemented kernel release boundary | accepted; pins superseded by later locks; main session-reference CAS/admission mechanics superseded by 0065 |
| [0021](0021-qualify-adapters-in-their-owning-slices.md) | Qualify adapters in their owning slices | Accepted; amends Slice 0 proof timing in 0017–0020 without weakening final acceptance |
| [0022](0022-accept-bounded-discord-delivery-ambiguity.md) | Accept bounded Discord delivery ambiguity | Accepted; amends 0016 |
| [0023](0023-use-a-stable-gmail-rfc-identity.md) | Use a stable Gmail RFC identity | Superseded by 0024 |
| [0024](0024-use-a-stable-gmail-effect-header.md) | Use a stable Gmail effect header | Accepted; supersedes 0023 and amends 0016 |
| [0025](0025-accept-existing-discord-role-authority.md) | Accept existing Discord role authority | Accepted; amends 0009 and 0011 |
| [0026](0026-pin-codex-compatible-kernel-wire.md) | Pin the Codex-compatible kernel wire protocol | accepted for isolated one-shot wire; main wire replaced by native callbacks/output under 0065; pins superseded |
| [0027](0027-bound-slice-2-read-observations.md) | Bound Slice 2 connector observations, Web boundaries, and usage accounting | accepted per-operation connector/Web bounds; main aggregate quotas and old pins superseded by 0065 |
| [0028](0028-qualify-current-local-account-models.md) | Qualify the exact current ChatGPT local-account model set without fixing its cardinality | Accepted; supersedes 0026's two-current-route conclusion while preserving its wire/schema decision |
| [0029](0029-represent-calendar-unspecified-ends.md) | Represent observed Calendar events whose end is unspecified | Accepted; supersedes 0027's concrete-end requirement for observed normal events |
| [0030](0030-namespace-the-scheduled-wake-tool.md) | Namespace the scheduled-wake tool while preserving its message source | Accepted; amends the tool spelling in 0014, 0015, and 0019 |
| [0031](0031-deploy-v1-on-the-existing-devbox.md) | Deploy v1 on the existing devbox with an isolated host-native service and database | Accepted; backup/reboot portions superseded by 0033; listener and host collectors amended by 0051 (target) |
| [0032](0032-stream-encrypted-backups-to-dedicated-r2.md) | Stream encrypted backups to dedicated off-host R2 storage and restore only into clean state | Superseded by 0033 before activation |
| [0033](0033-defer-backups-and-host-reboot.md) | Deploy without a reboot and defer backup/restore beyond v1 | Accepted; supersedes 0032 and amends 0031/Slice 7 |
| [0034](0034-reserve-two-foreground-envelopes.md) | Reserve two worst-case foreground envelopes in each rolling admission window | superseded by 0065; no rolling turn/token reservations |
| [0035](0035-contain-codex-app-server-authority.md) | Own and fail closed on the complete Codex App Server authority surface | accepted containment principles; exact native host/version/catalogue and callback protocol superseded by 0065 |
| [0036](0036-default-calendar-reads-to-primary.md) | Default Calendar list reads to the owner's primary calendar | Superseded by 0037 after the owner clarified the all-calendar product requirement |
| [0037](0037-read-and-use-all-owner-calendars.md) | Read and target every owner-visible Google calendar | Accepted; automatic predecessor admission migration superseded by 0047 |
| [0038](0038-truthful-terminals-and-bounded-calendar-completeness.md) | Use typed truthful terminals and host-owned bounded Calendar completeness | accepted typed completeness; main terminal extended with waiting/input dispositions by 0065 |
| [0039](0039-personalize-only-the-main-agent.md) | Give Main the owner's voice and stable personal context | Accepted; amends the Main role and public-Web search behavior |
| [0040](0040-shared-kernel-durable-decisions.md) | Shared kernel with durable inference and Read positions | accepted isolated decision/read receipts and owner-bound transactions; 0065 adds three native journals and replaces main decision/session integration; memory changes remain targets |
| [0041](0041-control-shared-codex-workers.md) | Control shared Codex workers through host-owned services | historical worker control superseded by 0052; shared cognition endpoint/pin superseded by 0065 |
| [0042](0042-track-latest-stable-codex.md) | Track latest stable native Codex without widening authority | superseded by 0065 for the separate contained endpoint; unrelated coding hosts retain their own update policy |
| [0043](0043-retain-main-thread-through-native-compaction.md) | Retain Main's thread through native compaction | healthy in-process compaction/reuse remains; saved-session resume/CAS and old recovery superseded by 0065 |
| [0044](0044-control-tmux-agents-through-skid.md) | control peer tmux agents through the common skid cli | accepted implementation target; supersedes 0041's worker routing and launcher; native observation/halt, single-session closure, partial-stop uncertainty and 64 kib bounds superseded by 0048; transport by 0049 |
| [0045](0045-use-the-ordinary-fleet-cli.md) | ordinary fleet cli and opaque references | accepted implementation target; supersedes 0044 cli grammar and roster; info preflight, session projection and partial-stop uncertainty superseded by 0048; cli argv and refs by 0049 |
| [0046](0046-reset-testing.md) | remove the old testing system before redesign | accepted reset; scoped memory exception in 0051/0054 and temporary native integration/live exception in 0065 |
| [0047](0047-require-current-admission-journals.md) | require current admission journals | superseded by 0065; retired admission journal is removed during stopped cutover |
| [0048](0048-align-with-the-herdr-fleet-cli.md) | align with the herdr fleet cli | accepted implementation target; live acceptance `NOT_RUN`; supersedes 0044/0045 native observation, single-session closure, info preflight and 64 kib bounds; skid cli codec superseded by 0049 |
| [0049](0049-drive-herdr-through-an-ssh-gate.md) | drive herdr through an ssh gate | accepted implementation target; production activation `NOT_RUN`; supersedes the skid cli transport, codec, refs and preflight of 0044/0045/0048 |
| [0051](0051-universal-memory.md) | one corpus, admitted capture, pull-only retrieval and logical erasure | accepted implementation target; amends 0002, 0008, 0031, 0040 and scoped 0046 verification; simplified by 0054; exclusion/erasure removed by 0061 |
| [0052](0052-cut-worker-control-to-current-skid.md) | cut worker control to current skid | accepted implementation target; production activation and service qualification `NOT_RUN`; supersedes worker transport, roster, refs and receipt codecs of 0044/0045/0048/0049; worker schemas/targets/launch/observation superseded by 0064 |
| [0053](0053-retain-only-the-selected-release.md) | retain only the selected release, with one temporary installation candidate | accepted; amends 0031's deployment policy and 0047's temporary normalizer handling |
| [0054](0054-simplify-universal-memory.md) | postgres activation, independent extraction and small retained checks | accepted implementation target; extraction superseded by 0066; historical jarvis import/provenance joins v2 deferrals; erasure group removed by 0061 |
| [0055](0055-batch-native-memory-by-size-or-age.md) | native per-conversation size/age batches and independent episodes | extraction policy superseded by 0066's chronological compression; historical rationale, no runtime activation |
| [0056](0056-save-agent-notes-over-mcp.md) | direct agent notes with optional conversation attribution | accepted implementation target; amends 0051/0054's mcp, provenance and erasure contracts; main access extended by 0057 |
| [0057](0057-let-jarvis-main-save-notes.md) | jarvis main saves notes through the same append function | accepted implementation target; native invocation identity under 0065, existing durable recorder, no gate/action; implementation/live acceptance `NOT_RUN` |
| [0058](0058-start-dreaming-from-new-notes.md) | daily dreamer begins with pending notes; later v2 adds work context | seed coverage/representation/progress/output superseded by 0066; atomic completion and independent read-only work integration remain; implementation/live acceptance `NOT_RUN` |
| [0059](0059-let-main-search-memory-directly.md) | main searches memory directly, including scheduled read-only turns | accepted implementation target; shared retrieval and read recorder; retained recaller and ranking choices superseded by 0060; implementation/live acceptance `NOT_RUN` |
| [0060](0060-replace-recaller-with-reranked-search.md) | remove the recaller; shared search retrieves and reranks evidence | accepted implementation target; caller-driven search/open, bounded common results, strict paid pipeline, no new agent/table; ranking superseded by 0063; implementation/live acceptance pending |
| [0061](0061-remove-memory-forgetting.md) | remove forgetting from the one-user prototype | accepted implementation target; no conversation exclusion/erasure, policy, tombstones or dedicated checks; append-only sources/notes, repair and derived rebuild remain |
| [0062](0062-simplify-memory-recovery-and-capture.md) | disposable memory computation and atomic event capture | accepted memory target; disposable background inference/capture unchanged; rolling-capacity wording superseded by 0065; implementation/live acceptance `NOT_RUN` |
| [0063](0063-simplify-memory-policy-and-retrieval.md) | global memory policy, automatic activation, rank fusion and agent discretion | accepted implementation target; jarvis search-only orientation amended by 0066; learned reranking deferred, no mandatory agent procedure or mcp status; implementation/live acceptance `NOT_RUN` |
| [0064](0064-simple-worker-orchestration.md) | simple worker orchestration | implemented design; source, darwin/linux providers, native consent, real postgres crash/recovery and local service/cognitive wait checks pass; installed fleet, external Discord delivery and production activation `NOT_RUN`; supersedes affected 0052 worker contracts and amends notification/concurrency |
| [0065](0065-native-agent-supervision.md) | native main, canonical requests and durable callback evidence | implemented and merged; frozen worker-v7/native composition qualification PASS; production activation and physical google/discord integration NOT_RUN; replaces main step loop, capacity reservations and file pause state |
| [0066](0066-optchat-memory-adoption.md) | optchat memory adoption | accepted scoped target; standalone memory library hosted by jarvis, archive/tree/view with ordinary part leaves, bounded tool results, persisted binary views, search/navigation and fresh jarvis turns; native clients stay native; product/schema/integration contracts complete, first-delivery quiet dreaming; implementation/live acceptance `NOT_RUN` |

To supersede an ADR, add a new ADR that names it, provides observed evidence,
documents migration impact, and updates the normative specification and current
verification requirements.

ADRs 0001 through 0006 were written on the same day as the specification they
justify. They are founding rationale rather than records of decisions taken under
observed pressure. That is worth knowing when reading SPEC section 13's
"observed evidence" bar for future ADRs: the bar applies to changing these
decisions, not to how they were originally reached.
