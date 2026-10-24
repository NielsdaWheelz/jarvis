# private notes and rolodex

status: owner choices settled, 2026-10-09; docs only. adopt in spec/an adr
superseding affected adr 0065 main-containment rules before implementation.
the [roadmap](implementation-plan.md#private-notes-repository-and-rolodex) owns
sequencing. this contract expands main's native authority; it is not shipped.

## target and scope

main runs in one persistent ordinary git checkout with a private github remote.
it reads, searches, creates, edits, moves, organizes and deletes documents using
native codex tools. it chooses when to commit, fetch, pull and push, including
self-initiated work. no notes approval or automatic git cadence.

[o6](one-main-events.md) supplies the same main capabilities for every admitted
event; [o9](delegated-follow-through.md) supplies ordinary agent judgment and
semantic stop. this feature adds access and content guidance, not another agent.

no notes api/tools, database, sync worker, importer, search index, document ui,
contacts service, metadata schema, revision ledger or filesystem broker.
reuse native tools, markdown, git and existing application callbacks.

## files and designer's content contract

one short root `README.md` explains the repo's purpose. create directories when
useful content exists; the following organization is advisory:

| directory | good content |
| --- | --- |
| `projects/` | briefs state outcomes, relevant context/constraints, open decisions and evidence |
| `procedures/` | instructions let a reader perform a task and recognize success; include actual prerequisites/exceptions |
| `research/` | distinguish source evidence, interpretation and unanswered questions; link sources |
| `drafts/` | the intended deliverable itself, in its appropriate voice and form |
| `people/` | one useful natural-language document per person: known facts, relationship/context and contact details when known |

a title and useful prose suffice. use descriptive filenames; disambiguate people
with a meaningful suffix. date changing facts when omission would mislead.
invent no facts. headings follow the material; no templates, placeholder dossiers,
mandatory fields, taxonomy or runtime content critic.

documents own editable authored material. [work records](work-records.md) own
current todos; [memory](universal-memory.md) owns retained conversational evidence.
link rather than mirror current task state. this adds no archive route or wholesale
repo ingestion; existing capture/admission rules still apply to eligible observed
content. a document cannot grant connector authority or owner consent.

## ordinary git and links

use ordinary git status/diff/history and agent judgment. preserve owner changes;
resolve conflicts without discarding them. no scripted reset, clean, force-push
or conflict overwrite. no commit-per-edit, push-on-turn-end or synchronization
guarantee. distinguish edited locally, committed locally and pushed successfully.
an offline/failed push leaves useful local work and an honest outstanding result.

use relative links within the repo. preserve paths when sensible; after a move,
repair known internal links through ordinary search/edit. external path links may
become stale; no stable-id or redirect service. deleting a file removes its current
version, retaining committed git history. it does not erase conversation/memory
observations or promise physical erasure. history rewriting is outside this slice.

## authority and composition

main is a trusted native execution domain, like existing coding workers.
native commands bypass jarvis's `AutomaticWriteGate`, `action` ledger, exact-action
approvals and callback replay guarantees. connector calls retain those mechanisms;
`Approve`/`Deny` governs connector calls only. native access can read beyond the repo
and make network effects using credentials accessible to the native host account.
this is an explicit authority expansion, not repo-only containment.
the ordinary stock built-in set, including native collaboration when exposed by
the qualified host, shares that trust; access is not a notes-only tool allowlist.

freeze this main provider configuration:

| field | value |
| --- | --- |
| cwd | configured persistent checkout |
| filesystem / network / approval | `workspace_write` / `unrestricted` / `deny` |
| allowed native tools | existing `allowed_tools = ("*",)`; ordinary built-ins enabled with `builtin_tools = None` |
| network confirmation | existing `UnsafeConfirmation(("network_unrestricted",))` |
| additional writable directory | exactly the derived `<checkout>/.git` |
| native web / mcp | `web_search = False`; empty mcp configuration; existing callback web tools remain available |

stock protects `.git` by default. explicit writable-root override is supported
by the [pinned stock source](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/protocol/src/permissions.rs#L759);
git operability here is a source inference, requiring live qualification below.
use an ordinary checkout with a `.git` directory, not a linked worktree.
retain stock `0.160.0`, qualified personal `gpt-5.6-terra`/`high` and the existing
dedicated host unless separately changed and qualified. unsupported behavior is
a blocker, not permission to widen to `full_access` or introduce a sync fallback.

retain native-host/application uid separation, root-only connector configuration,
application non-dumpability and privilege restrictions. never copy jarvis's
connector/database/discord/embedding credentials into native cwd, environment or
account home. native codex/git account credentials belong to the trusted domain.

isolated gates/memory roles keep private empty read-only directories, disabled
native tools/network and their strict grammar. main's wider posture never leaks
through a shared mutable configuration. existing model selection, clients/pools,
callback dispatch, canonical journals and connector recovery remain shared.

native interruption is best effort; entered or detached commands may survive.
after connection/process loss, inspect actual files, git and available native
evidence before choosing the next action. never automatically replay a saved
shell command, patch, commit or push. no native exactly-once claim or second
effect ledger. conversational stop remains agent interpretation under o9.

## public contracts and deployment

the [current dependency pins](../pyproject.toml) reject this target: kernel
configuration fixes containment and creates/removes temporary cwd; provider-runtime
rejects built-ins mixed with declared callbacks. upstream changes are required.

kernel extends existing `ProviderConfiguration`, not a notes-specific interface:

| field | contract |
| --- | --- |
| `cwd_scope` | `private_empty_read_only` or `application_workspace` |
| `cwd` | `None` for disposable scope; normalized absolute path required for application scope |
| `additional_dirs` | immutable tuple of normalized absolute paths; empty for isolated roles; main supplies only derived `.git` |
| existing `policy`, `native` | explicit frozen authority; isolated `AgentDefinition` rejects a widened/workspace configuration |

fingerprint actual cwd/scope/additional directories/policy/native options and base
instructions. mutable document contents are not definition identity. application
cwd is borrowed: lease close, shutdown and release pruning never chmod or delete
it. disposable isolated directories retain their existing cleanup.

provider-runtime supports and qualifies built-ins plus dynamic host callbacks in
one native session. preserve public identities, strict callback schemas,
phase-aware output, progress/final evidence, steering, interruption and usage.
extend provider-owned host qualification to admit both declared postures.
before submission, verify actual thread cwd, writable roots including `.git`,
network, approval denial, native options and callback publication against the frozen
request. host version/catalog checks alone are insufficient. retain isolated-role
checks; do not bypass preflight or invent jarvis wire adapters. native activity and
host callback namespaces stay distinct:

- `AgentToolCall`: existing host callback journal/dispatch/action/approval path.
- `AgentToolUse`: native activity evidence with original identity/phase/outcome;
  accepted only under the declared native posture, never converted to an action.
- `AgentPermissionRequest`: provider denies escalation under `approval = deny`
  and reports its outcome; never rendered as a connector approval.

kernel revises main's base instruction and event handling accordingly; malformed,
unknown or undeclared activity still fails. isolated-role containment stays strict.

hard-cut `/etc/jarvis/codex-host.json` to schema 5 with one required
`notes_repository` absolute path, using its existing closed loader/path validation.
derive `.git`; no second root setting. deployment selects the private origin and
bootstraps ordinary git authentication for the existing native-host account.
keep credentials outside repository files. no runtime repo-creation/auth service.

place the checkout outside release/disposable directories and private jarvis state
parents, e.g. `/var/lib/jarvis-notes`. native-host uid owns it; existing client
group can traverse/read for preflight. add it to the existing host unit's
`ReadWritePaths`. bootstrap verifies the selected private origin and git access;
application preflight verifies the configured checkout and required local access.
missing/mismatched configuration is a repair error. do not reset, clone over,
auto-pull or remove an existing checkout during installation.

## non-overlapping delivery and acceptance

| owner / unit | exclusive files and result |
| --- | --- |
| kernel | `definitions.py`, `provider.py`, `native_contract.py`, `native.py`: public configuration, fingerprints, borrowed cwd lifecycle, main instructions/events |
| provider-runtime | `agent_runtime/codex_sdk.py`, `codex_app_server.py`, affected `codex_containment.py`: mixed native/callback transport and actual host/thread qualification; public exports/types only if needed |
| jarvis composition | `src/jarvis/codex_config.py`, `kernel.py`, `definitions.py`, `cli.py`, `session-compatibility.json`: immutable main/isolated configurations from one qualified model selection; designer's content guidance |
| deployment | `deploy/codex-host`, `jarvis-codex-contained.service`, `install-contained-host`, affected verification/activation checks: mapping, persistent checkout/account access and same-release host operation |
| temporary proofs / designer review | scoped proof files only: integration/live behavior and content quality; no production edits by proof writer |

agree upstream contracts first; publish exact qualified kernel/provider pins,
then consume them through normal jarvis dependencies. no llm-tools, skid, work
or memory schema change. one writer integrates shared o6/o9/composition files.
adopt authority/instruction/config changes together in spec/adr and use the existing
stopped cutover. remove main-only disabled-native rules and schema-4 acceptance;
retain isolated rules and canonical connector journals. no dual-mode legacy path.

temporary red/green integration and one live synthetic-repo journey must prove:

1. useful project/person documents; native search/read/create/edit; move with
   repaired link; delete with retained committed history; preserve owner edits.
2. real git commit/fetch/pull/push to a private test remote under the exact frozen
   policy, including a failed/offline push with truthful local/remote status.
3. native tools and a declared callback in one turn; valid progress/final;
   connector approval still binds exact stored arguments; isolated tools stay disabled.
4. close/restart retains checkout and dirty changes; interruption/loss causes no
   automatic native replay or fabricated stop/success; fresh main retains access.

designer judges factual clarity, usefulness and proportionate content, not exact
wording. adversarially review authority, interfaces and content before coding,
after green and after refactor. consolidate actual duplication; retain one policy
definition and existing transport/journal mechanisms. record final-tree evidence,
delete temporary tests as requested, then run `scripts/verify`.
this doc task runs static/build checks only; behavioral/live verification is not run.

costs: trusted native effects lose connector-level approval/replay guarantees;
git discretion leaves dirty/unpushed work without guaranteed off-host backup;
moves may stale external links; deletion retains committed history; deleting
temporary tests leaves less retained regression coverage. no extra machinery is
added to conceal these choices.
