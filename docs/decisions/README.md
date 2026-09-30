# Architecture decision records

Accepted ADRs are permanent records of why Jarvis is shaped this way. They are
not implementation suggestions.

[adr 0046](0046-reset-testing.md) supersedes earlier test-retention and
verification-execution requirements during the owner-approved reset. runtime
contracts remain binding; dated evidence remains historical.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-small-personal-agent.md) | One small personal agent system | Accepted; trace amended by 0010/0019; internal gate added by 0019 |
| [0002](0002-optmem-inspired-memory.md) | Immutable raw memory and rebuildable views | Accepted |
| [0003](0003-natural-discord-and-autonomy.md) | Natural Discord and a narrow approval boundary | Accepted; server organization superseded by 0011; generic local-write scope superseded by 0014 |
| [0004](0004-python-codex-and-tool-kernel.md) | Python, Codex, `provider-runtime`, and `llm-tools` | Accepted; session/context amended by 0012; portable-Web ownership by 0014; generic loop by 0017; exact provider boundary by 0018 |
| [0005](0005-reuse-integrations.md) | Reuse working integrations; defer new ones | Accepted; Discord tool scope superseded by 0011; public Web amended by 0014; revoked Google grant re-consent amended in place |
| [0006](0006-no-workflow-framework.md) | No v1 workflow framework | Accepted; bounded agent-kernel distinction clarified by 0017 |
| [0007](0007-central-messages-and-unified-actions.md) | Central messages and one action ledger | Accepted; schemas superseded by 0010; session by 0012; delivery by 0016; action-resolution by 0017; recorder/cross-run mapping by 0018/0019 |
| [0008](0008-embedding-source.md) | Embedding through an embedding-scoped OpenAI credential | Accepted; amends 0004 |
| [0009](0009-least-privilege-discord-and-host-rendered-approval.md) | Least-privilege Discord and a host-rendered approval preview | Accepted; Discord permissions superseded/amended by 0011 and 0025; approval remains |
| [0010](0010-minimal-durable-state.md) | Minimal message and action durable state | Accepted; tool naming amended by 0013; delivery amended by 0016; cross-run/recorder facts amended by 0018 and 0019; durable park amended by 0020 |
| [0011](0011-single-channel-discord.md) | One configured Discord channel, transport only | Accepted; supersedes Discord organization/tool scope in 0003, 0005, and 0009; permissions amended by 0025 |
| [0012](0012-resumable-session-and-context.md) | Resumable main session over provider-neutral context | Accepted; amends 0004 and 0007; implementation/polling/admission amended by 0017–0019; compatibility policy amended by 0020 |
| [0013](0013-unversioned-v1-tools.md) | Unversioned v1 tool names | Accepted; occupied-position evidence amended by 0018 and 0019 |
| [0014](0014-minimal-v1-tool-catalog.md) | Exact minimal v1 tool catalog with portable Web tools | Accepted; supersedes parts of 0003 and 0004; amends 0005; schedule tool spelling amended by 0030 |
| [0015](0015-explicit-v1-proactivity.md) | User-facing proactivity only through requested wakes | Accepted; schedule receipt semantics amended by 0019; tool spelling amended by 0030 |
| [0016](0016-provider-native-idempotency.md) | Provider-native idempotency before terminal uncertainty | Accepted; supersedes delivery semantics in 0007 and 0010; schema cost amended by 0018; attempt ceiling by 0019; Discord delivery amended by 0022; Gmail identity amended by 0024 |
| [0017](0017-extract-agent-kernel.md) | Extract the reusable bounded agent kernel | Accepted; corrected provider/loop/admission contract incorporated; durable mapping in 0018; final seams in 0019; final release boundary pinned by 0020 |
| [0018](0018-serial-kernel-and-bounded-recovery.md) | Map the serial kernel and bounded recovery into four tables | Accepted; amends 0010, 0012, 0013, and 0017; final seams amended by 0019; durable park amended by 0020 |
| [0019](0019-ground-writes-and-close-recovery-seams.md) | Ground writes and close the remaining recovery seams | Accepted; amends 0010, 0012, 0015, and 0018; claim/attempt ordering amended by 0020; schedule tool spelling amended by 0030 |
| [0020](0020-pin-the-implemented-kernel-boundary.md) | Pin the implemented kernel release boundary | Accepted; dependency revisions superseded by 0026 and 0027; other host-boundary decisions remain |
| [0021](0021-qualify-adapters-in-their-owning-slices.md) | Qualify adapters in their owning slices | Accepted; amends Slice 0 proof timing in 0017–0020 without weakening final acceptance |
| [0022](0022-accept-bounded-discord-delivery-ambiguity.md) | Accept bounded Discord delivery ambiguity | Accepted; amends 0016 |
| [0023](0023-use-a-stable-gmail-rfc-identity.md) | Use a stable Gmail RFC identity | Superseded by 0024 |
| [0024](0024-use-a-stable-gmail-effect-header.md) | Use a stable Gmail effect header | Accepted; supersedes 0023 and amends 0016 |
| [0025](0025-accept-existing-discord-role-authority.md) | Accept existing Discord role authority | Accepted; amends 0009 and 0011 |
| [0026](0026-pin-codex-compatible-kernel-wire.md) | Pin the Codex-compatible kernel wire protocol | Accepted; supersedes the kernel revision in 0020; revision superseded by 0027 |
| [0027](0027-bound-slice-2-read-observations.md) | Bound Slice 2 connector observations, Web boundaries, and usage accounting | Accepted; amends SPEC 7.3, supersedes prior kernel/provider/llm-tools pins, and supersedes the Slice 0 contract sketch where they differ |
| [0028](0028-qualify-current-local-account-models.md) | Qualify the exact current ChatGPT local-account model set without fixing its cardinality | Accepted; supersedes 0026's two-current-route conclusion while preserving its wire/schema decision |
| [0029](0029-represent-calendar-unspecified-ends.md) | Represent observed Calendar events whose end is unspecified | Accepted; supersedes 0027's concrete-end requirement for observed normal events |
| [0030](0030-namespace-the-scheduled-wake-tool.md) | Namespace the scheduled-wake tool while preserving its message source | Accepted; amends the tool spelling in 0014, 0015, and 0019 |
| [0031](0031-deploy-v1-on-the-existing-devbox.md) | Deploy v1 on the existing devbox with an isolated host-native service and database | Accepted; backup/reboot portions superseded by 0033 |
| [0032](0032-stream-encrypted-backups-to-dedicated-r2.md) | Stream encrypted backups to dedicated off-host R2 storage and restore only into clean state | Superseded by 0033 before activation |
| [0033](0033-defer-backups-and-host-reboot.md) | Deploy without a reboot and defer backup/restore beyond v1 | Accepted; supersedes 0032 and amends 0031/Slice 7 |
| [0034](0034-reserve-two-foreground-envelopes.md) | Reserve two worst-case foreground envelopes in each rolling admission window | Accepted; amends admission and Slice 7 |
| [0035](0035-contain-codex-app-server-authority.md) | Own and fail closed on the complete Codex App Server authority surface | Accepted; supersedes the active provider/kernel pins and strengthens 0020/0026 containment |
| [0036](0036-default-calendar-reads-to-primary.md) | Default Calendar list reads to the owner's primary calendar | Superseded by 0037 after the owner clarified the all-calendar product requirement |
| [0037](0037-read-and-use-all-owner-calendars.md) | Read and target every owner-visible Google calendar | Accepted; automatic predecessor admission migration superseded by 0047 |
| [0038](0038-truthful-terminals-and-bounded-calendar-completeness.md) | Use typed truthful terminals and host-owned bounded Calendar completeness | Accepted; supersedes 0037's event cap/pagination and amends the Main terminal contract |
| [0039](0039-personalize-only-the-main-agent.md) | Give Main the owner's voice and stable personal context | Accepted; amends the Main role and public-Web search behavior |
| [0040](0040-shared-kernel-durable-decisions.md) | Shared kernel with durable inference and Read positions | Accepted; six-table durability, authenticated model selection, and owner-bound transactions |
| [0041](0041-control-shared-codex-workers.md) | Control shared Codex workers through host-owned services | accepted; native pin superseded by 0042, worker control by 0044 |
| [0042](0042-track-latest-stable-codex.md) | Track latest stable native Codex without widening authority | Accepted; supersedes 0041's native executable pin |
| [0043](0043-retain-main-thread-through-native-compaction.md) | Retain Main's thread through native compaction | Accepted; removes host age-based rotation, preserves CAS and recovery |
| [0044](0044-control-tmux-agents-through-skid.md) | control peer tmux agents through the common skid cli | accepted implementation target; supersedes 0041's worker routing and launcher; native observation/halt, single-session closure, partial-stop uncertainty and 64 kib bounds superseded by 0048; transport by 0049 |
| [0045](0045-use-the-ordinary-fleet-cli.md) | ordinary fleet cli and opaque references | accepted implementation target; supersedes 0044 cli grammar and roster; info preflight, session projection and partial-stop uncertainty superseded by 0048; cli argv and refs by 0049 |
| [0046](0046-reset-testing.md) | remove the old testing system before redesign | accepted; suspends earlier test and qualification execution gates |
| [0047](0047-require-current-admission-journals.md) | require current admission journals | accepted; retires 0037's automatic predecessor recognition under the owner's hard-cut instruction |
| [0048](0048-align-with-the-herdr-fleet-cli.md) | align with the herdr fleet cli | accepted implementation target; live acceptance `NOT_RUN`; supersedes 0044/0045 native observation, single-session closure, info preflight and 64 kib bounds; skid cli codec superseded by 0049 |
| [0049](0049-drive-herdr-through-an-ssh-gate.md) | drive herdr through an ssh gate | accepted implementation target; production activation `NOT_RUN`; supersedes the skid cli transport, codec, refs and preflight of 0044/0045/0048 |
| [0052](0052-cut-worker-control-to-current-skid.md) | cut worker control to current skid | accepted implementation target; production activation and service qualification `NOT_RUN`; supersedes worker transport, roster, refs and receipt codecs of 0044/0045/0048/0049 |

To supersede an ADR, add a new ADR that names it, provides observed evidence,
documents migration impact, and updates the normative specification and current
verification requirements.

ADRs 0001 through 0006 were written on the same day as the specification they
justify. They are founding rationale rather than records of decisions taken under
observed pressure. That is worth knowing when reading SPEC section 13's
"observed evidence" bar for future ADRs: the bar applies to changing these
decisions, not to how they were originally reached.
