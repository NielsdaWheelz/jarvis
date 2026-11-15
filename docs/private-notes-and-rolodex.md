# private workspace — slice 4

status: specified 2026-11-15 under [adr 0071](decisions/0071-simple-event-driven-v2.md);
unimplemented. audited jarvis predecessor `dafb7e0`, kernel `da33773662089a72992c9aec1f938c76d9cb95ab`,
provider-runtime `70178ec8bb5b54304367ad60c0732447084a37c7`. audit the pinned git
sources, not a stale local environment. [the roadmap](implementation-plan.md#v2-reviewable-pr-slices)
owns sequence; production activation stays at final v2 cutover.

## target and scope

main gets one persistent ordinary checkout of the new private
`NielsdaWheelz/jarvis-notes` repository, initially a brief readme with no imported
material or required folder tree. it is a general workspace: authored notes,
people/context, research, drafts, scripts, reusable helpers, components, charts
and self-contained interactive pages. main reads/searches/creates/edits/moves/
deletes files, runs its tools and chooses git commit/fetch/pull/push when useful.
every admitted event has these same main capabilities; no notes approval or git cadence.

creation and local execution ship here. artifact hosting, deployment, presentation
ui and [television](https://television.run/) integration remain deferred, as do
browser access, credential products and attachment ingestion/storage. a helper
is an ordinary file run through native tools, not a new callback/mcp registration.
no notes api, table, document schema/index, sync daemon, agent framework, publishing
service, task graph, mandatory taxonomy or wholesale repo ingestion.

[work](work-records.md) owns todos, [memory](universal-memory.md) owns retained
conversational evidence, files own editable authored material. link useful context
rather than mirror current task state. existing capture rules remain; a document
or repo instruction cannot supply owner consent or override the application protocol.

## behavior and final state

- use native tools and ordinary git. preserve owner edits; resolve actual conflicts
  without reset/clean/force-push or overwriting unrelated work. history rewriting
  is outside this slice. no autonomous installer pull, reset or clone-over.
- distinguish local edits, local commits and successful pushes. an offline/failed
  push leaves useful local work. remote links must identify a version that exists
  remotely; html in a private repo is not a hosted interactive experience.
- relative links work within the repo; after moves, repair known internal links.
  no stable-id/redirect service. deleting a file removes its current version,
  retaining committed history and any existing memory observations.
- useful findings/results use ordinary conversation; silence remains valid. no
  automatic inventory, compulsory readme read, per-file todo or progress component.
- lease close, failed acquisition, process restart and release pruning preserve
  the checkout, dirty edits and git history. native sessions remain disposable.
  after interrupted work, inspect files/git and available evidence before deciding
  the next action; never automatically replay a command, patch, commit or push.

completion means qualified upstream pins, jarvis composition/deployment source,
content-reviewed temporary candidate proof and a final-cutover handoff. no live
production checkout, mapping, host unit, database or control is changed by this
specification or its candidate proof. production bootstrap happens at final cutover.

## capability contract

main is a trusted native execution domain, as already adopted in adr 0071.
native commands bypass jarvis's action ledger, connector consent and callback
replay guarantees. they may read beyond the repo and use network/account access
available to the native host. this is not repo-only confinement. connector tools
retain their existing immutable actions, ordinary conversational consent and
recovery; do not build transitive consent checks around shell commands.

| frozen field | main | isolated memory roles |
| --- | --- | --- |
| cwd | configured persistent checkout | existing private empty disposable directory |
| filesystem / network / approval | `workspace_write` / `unrestricted` / `deny` | `read_only` / `disabled` / `deny` |
| allowed native tools | existing `allowed_tools=("*",)`; `builtin_tools=None` | existing disabled built-ins |
| additional writable roots | exactly derived `<checkout>/.git` | empty |
| network confirmation | existing `UnsafeConfirmation(("network_unrestricted",))` | none |
| native web / mcp | `web_search=False`; no mcp servers; existing web callbacks remain | unchanged disabled posture |
| cognition retention | `archive_internal=True`, ephemeral threads | unchanged internal/disposable behavior |

retain stock `0.160.0`, the qualified personal `gpt-5.6-terra`/`high` selection,
host/application uid separation, root-only application secrets, non-dumpability
and privilege restrictions. never copy connector/database/discord/embedding
credentials into the native environment, account home or checkout. existing native
account/git authentication remains deployment configuration, outside repo files.

stock workspace writes also include ordinary scratch paths, constrained by the
host namespace. its [metadata protection](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/protocol/src/permissions.rs)
covers `.git`, `.agents`, `.codex` and `.aws`; override only `.git`. a normal checkout
with a `.git` directory is required, not a linked worktree. live git proof must
establish actual operability; failure does not authorize `full_access` or a sync proxy.

retain account `AGENTS.md`/`AGENTS.override.md` masking. ordinary project instruction
discovery may supply workspace guidance; require no such file or mutable-content
fingerprint. [stock project discovery](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/src/agents_md.rs)
is distinct from account instructions. inherited configuration must not silently
change the frozen policy, mcp exposure or callbacks. ordinary built-ins, including
native collaboration when exposed, share main's trust; qualify inherited authority
and internal-cognition exclusion for any exposed child path. no worker graph or
new archive mechanism. interruption remains best effort; detached work may survive.

## public contracts and deployment

current pins reject this target: kernel configuration fixes containment and owns
every temporary cwd; provider rejects mixed built-ins/callbacks; kernel rejects
native tool activity. fix those owners, not a jarvis shell wrapper or wire adapter.

### kernel: configuration and ownership

extend existing frozen `ProviderConfiguration`:

| field | exact contract |
| --- | --- |
| `cwd: str \| None = None` | none retains the provider-owned disposable directory; a normalized non-root absolute path borrows an existing application directory |
| `additional_dirs: tuple[str, ...] = ()` | immutable normalized absolute paths passed through to the provider; jarvis main supplies only derived `.git` |
| existing `policy`, `native` | explicit authority; no role-specific model/client selection |

remove the redundant `cwd_scope` field and its identity entry; no compatibility
alias. directory ownership follows `cwd`; policy defines authority. isolated
`AgentDefinition` rejects a borrowed cwd, nonempty additional directories or widened
policy/native options. `NativeDefinition` supports the declared native posture.

fingerprint configured cwd, additional directories, complete policy/native options
and kernel instructions in existing definition/session identities. exclude mutable
files and generated disposable paths. one internal lease ownership fact controls
cleanup: acquisition failure, discard and shutdown may chmod/remove only provider-
owned directories. validate borrowed access; never create, empty, chmod or delete
that checkout. no public lifecycle manager or persistent session recovery.

### provider-runtime: one session, two execution paths

reuse `CodexNativeOptions`, `PermissionPolicy`, session specification and existing
native stream types. preserve strict callback schemas, progress/final messages,
steering, cancellation, identity and usage. required changes are coupled:

1. support built-ins plus declared callbacks; enable the experimental protocol
   whenever callbacks require it, not only for the contained posture.
2. reuse explicit inherited-mcp suppression for BOTH postures. an empty
   `mcp_servers` mapping does not remove inherited servers. retain startup catalogue
   version/origin qualification and verify each requested supported policy. jarvis
   admits its two declared configurations; do not restrict other provider consumers.
3. validate returned `thread/start` settings before a session can submit work;
   also retain ongoing settings checks. compare actual cwd, model/provider/reasoning,
   sandbox roots/network and approval to the frozen request. the
   [pinned response](https://raw.githubusercontent.com/openai/codex/rust-v0.160.0/codex-rs/app-server-protocol/schema/typescript/v2/ThreadStartResponse.ts)
   does not echo native switches or dynamic callbacks: validate their emitted
   configuration/publication and qualify behavior, not an invented read-back api.
4. keep activity types distinct. `AgentToolCall` follows the existing host callback
   journal/dispatch/action path. declared `AgentToolUse` is native observation,
   never an action or durable shell receipt. under `approval=deny`, provider denies
   escalation; the kernel accepts its validated permission outcome without a
   connector approval. undeclared/granted authority, unknown active events or
   malformed identities still fence/fail. retain existing limits and receipt seals.

revise main's kernel-owned base instruction and native event handling together.
isolated strict grammar/containment remains intact. do not turn off validation or
hide unsupported native events as inert text. native effects acquire no second ledger.

### jarvis: composition and host mapping

resolve the authenticated model/catalog once. derive two immutable configurations
from that selection: main workspace and isolated containment. pass explicit
`main_provider` / `isolated_provider` into `build_definitions`; pass only isolated
configuration to compactor/dreamer. reuse clients, pools, native runner, journals
and callbacks; no shared mutable policy or duplicate model settings.

hard-cut the existing root-owned `/etc/jarvis/codex-host.json` loader to schema 5,
retaining existing fields and adding one required `notes_repository` path. use
`canonical_absolute_path`; derive `.git` rather than add another setting.
`cognition_cwd_parent` remains only for disposable isolated directories. application
preflight checks the existing checkout/local access; bootstrap verifies valid git,
selected private origin and authentication in the actual host environment.
missing/mismatched configuration requires repair, never fallback to a home/temp cwd.

final bootstrap creates ordinary `main` checkout `/var/lib/jarvis-notes`, with
private origin `NielsdaWheelz/jarvis-notes`. native-host uid owns it; the existing
client group gets only traversal/read required by preflight. keep it outside
releases, disposable paths and private application-state parents. add it to the
existing host unit's `ReadWritePaths`. root-owned host mapping/unit select the
same qualified release. installer preserves existing files/dirty state and never
auto-clones over or pulls an existing checkout.

prove git from `deploy/codex-host`'s actual `HOME`/`PATH`/account environment;
developer-shell authentication is insufficient and `SSH_AUTH_SOCK` is not forwarded.
use ordinary host-account git configuration; no runtime repo-creation, login,
credential-copy or credential-broker service. the selected private origin lives
in ordinary git configuration, not a duplicate application registry.

[adr 0074](decisions/0074-private-native-socket-publication.md) corrects the host
publication required by actual native execution. stock's physical daemon directory
stays private `0700` beneath an ancestor bound as `/tmp`; its private relative alias
is masked from native commands. systemd binds the one group-accessible socket onto
an inert public placeholder only inside the application namespace. retain the
configured endpoint, identities, account masks and other service restrictions.
host loss stops the application; repair/replacement requires a fresh application
start and socket remount. no public control hardlink, proxy or new supervisor.

## designer's content contract

a designer defines/reviews good content for EACH feature below, in existing files,
tool results and native response variants. these are semantic criteria, not schemas,
mandatory directories, templates or a runtime critic.

| feature | good content and hostile case |
| --- | --- |
| orientation | brief readme explains purpose and links material that exists. reject a forced directory tree, empty dossiers or a mandatory first read. |
| authored documents / people | useful title, relevant known facts, context, constraints and unresolved decisions; distinguish evidence/interpretation and date changing facts when material. reject invented facts, commitments or intimacy. |
| reusable helpers | clear purpose, short invocation example, inputs/outputs/units and meaningful failure behavior. prefer a small runnable file over scaffolding; reject a successful exit presented as proof of the wrong result. |
| components / visualizations | task-appropriate labels, units, readable scale/layout and useful interaction; preserve source/assumption context. reject decorative complexity, misleading scales or claims of hosted availability. |
| revision / delivery | preserve owner edits and known links; report local/committed/pushed facts accurately and provide a usable reference. a failed push is not sharing; deletion is not historical erasure. |
| interruption / failure | state the actual unresolved result and useful next step, retaining local work. reject fabricated cancellation, automatic replay or a synchronization guarantee. |

a draft or chart can be local, committed or pushed without being delivered
as a discord attachment or hosted page. existing response limits remain.

## non-overlapping delivery and acceptance

| owner | exclusive source / deliverable |
| --- | --- |
| provider-runtime | `agent_runtime/codex_sdk.py`, `codex_app_server.py`, `codex_containment.py`, existing public types only as needed: mixed execution, startup/thread checks and inherited-config handling |
| kernel | `definitions.py`, `provider.py`, `native_contract.py`, `native.py`: borrowed cwd, isolated validation, fingerprints, instructions/events; any package exports stay here |
| jarvis runtime/content | `src/jarvis/codex_config.py`, `kernel.py`, `definitions.py`, `cli.py`, `session-compatibility.json`, dependency manifests: consume exact upstream contracts, apply designer guidance |
| deployment | `deploy/codex-host`, `jarvis-codex-contained.service`, `install-contained-host`, affected verification files and operational docs: mapping, persistent checkout and actual host access |
| proof/integration | temporary probes, synthetic candidate resources and evidence here; no production changes or second implementation of runtime logic |

agree provider/kernel contracts first; their owners implement disjoint files,
then publish exact qualified pins. jarvis consumes them and rotates affected main/
shared compatibility identities. one integrator owns shared-file edits. no
llm-tools, skid, work or memory-schema change. hard-cut main's disabled-native path,
old `cwd_scope` and schema-4 loader acceptance; preserve isolated restrictions and
historical connector receipts. keep `deploy/activate-release`'s refusal until final
v2 cutover; no compatibility daemon, fallback policy or parallel notes API.

### temporary candidate proof

candidate isolation includes a SEPARATE native endpoint/unit and public mapping,
not slice 3's reuse of the unchanged production host. the installed host cannot
supply the new write mount/posture without modification. reuse existing unit/
qualification primitives with task paths/unit names and the configured application/
host os identities. preserve actual service restrictions and original credential
ownership, copying no credentials. use a task
checkout/private test remote, postgres, runtime/configuration and controlled
`GatewayPort`/catch-up. no second production gateway consumer or normal `jarvis serve`.
production mappings, units, database, checkout and selected release stay unchanged.

| feature | minimum temporary integration/live proof |
| --- | --- |
| file/content journey | actual native main creates useful project/person prose, searches/reads/edits it, preserves an owner edit, moves a file and repairs its link; deletes a committed file while history remains |
| helper/visual journey | synthetic project hours: alpha `2+3`, beta `4` → reusable script → self-contained html chart/filter. verify all-project total `9`, alpha `5`; a fresh main reuses the helper with changed input. temporary qualification renders/exercises the page; no product browser feature |
| actual git | commit/fetch/pull/push to a private test remote under the exact policy/environment; exercise conflict and failed push, retaining edits and truthful local/remote claims |
| mixed execution | native file/command and declared callback in one real turn with valid progress/final; a controlled consequential connector verifies existing conversational decision/action recovery without routing native effects through it |
| authority | actual workspace/.git access; isolated roles retain empty read-only cwd and disabled native/network; inherited mcp stays off, escalation stays denied, configured roots/settings cannot silently widen, and exposed child cognition preserves declared isolation from shared capture |
| lifecycle | failed acquisition, lease discard, cancellation and candidate restart retain dirty checkout; fresh main reopens it; original callback receipts survive and no native command is automatically replayed |

for each feature, adversary reviews design/red/green/refactor/cleanup and designer
reviews the actual content. first run target behavior against current pins to
record specific failures; never manufacture red for existing working behavior.
fix the responsible layer, get green, consolidate demonstrated duplication/dead
code and recheck changed concerns/final journeys. preserve content-free diagnostics
for failures; the [unexplained native defect](issues/native-protocol-diagnostics.md)
stays open without a reproduced cause and verified repair. do not relabel it fixed
because unrelated runs pass or introduce fallback output/automatic unpark.

record exact source/lock/host versions, tested postures, real versus controlled
boundaries, red/green results, content/adversarial verdicts and cleanup here.
then delete only new temporary probes/resources and run each changed repo's
required checks, including jarvis `scripts/verify`; preserve approved regressions.
remove temporary remotes/terminals only when task-owned. no credentials or private
material in fixtures/evidence. production acceptance remains a final-cutover
journey under [operations](operations.md), with existing reminder/effect accounting.
this task writes docs only: no code, behavioral/live tests, repo creation or deployment.

## explicit costs

- trusted native commands can act beyond repo content and lack connector-level
  consent, action recovery and exactly-once guarantees; stop may not end detached work.
- agent-chosen git leaves dirty/unpushed work without guaranteed off-host backup;
  moves can stale external links, and deletion retains committed history.
- repo files supply custom tools and interactive artifacts, but no hosting,
  discoverability ui, uptime promise or television integration.
- the borrowed path is explicit in compatibility identity; mutable content is not.
  main must inspect changing files rather than depend on a frozen content snapshot.
- separate candidate proof defers production acceptance; deleting temporary tests
  reduces retained regression coverage. no extra framework conceals those limits.
