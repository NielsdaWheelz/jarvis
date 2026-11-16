# private workspace — slice 4

status: source implemented 2026-11-15 under [adr 0071](decisions/0071-simple-event-driven-v2.md)
and the demonstrated host repair in [adr 0074](decisions/0074-private-native-socket-publication.md).
[qualification below](#implementation-evidence--2026-11-15) separates source,
controlled integration and actual temporary candidate evidence. the audited
jarvis predecessor was `dafb7e0`, kernel `da33773662089a72992c9aec1f938c76d9cb95ab`,
provider-runtime `70178ec8bb5b54304367ad60c0732447084a37c7`.
[the roadmap](implementation-plan.md#v2-reviewable-pr-slices) owns sequence;
[production bootstrap and acceptance](issues/private-workspace-installed-cutover.md)
remain at final v2 cutover.

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

the predecessor pins rejected this target: kernel fixed containment and owned
every temporary cwd; provider rejected mixed built-ins/callbacks; kernel rejected
native tool activity. the qualified pins repair those owners; jarvis adds no
shell wrapper or wire adapter.

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
configured endpoint, identities, account masks and privilege restrictions.
the native host needs ordinary read-only kernel metadata for its unprivileged
sandbox; the application keeps its pid-only proc view.
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
the proof does not modify production mappings, units, database, checkout or
selected release. independently concurrent production changes must be recorded,
not reverted or reported as this candidate.

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
the owner authorized source implementation and the scoped temporary proof on
2026-11-15. that authority does not activate the intermediate production release.

## implementation evidence — 2026-11-15

source and separate temporary candidate qualification passed, with independent
adversarial design/red/green/refactor and content review for each feature.
qualification continued into 2026-11-16 utc. this is neither hosted ci nor
production activation. the original checkout and its owner-authored documentation
changes were preserved; work used separate `feature/private-workspace` worktrees.

### initial full candidate source and environment

| artifact | qualified identity |
| --- | --- |
| jarvis runtime/deployment candidate | `a649e58f33bfb4c4fb680e81488a907e3eb27cbe`; the subsequent compatible integration below has its own final pins |
| kernel | `b7218b9b59c0a58c0da548307320af9377486ed9` |
| provider-runtime | `d69c7c69a2ce60e46cfaf296d12e4535b21456c5` |
| unchanged llm-tools / memory library | `8989f3afdcc640f775bd0cc9e7a0b4c246f10e57` / `93e02af07fee7e79250fb800835c324f092b5bec` |
| jarvis lock sha256 | `977df51a5d0e2130147b670a37fda142986a5bc8c740f11f56b2489e9acb0034` |
| kernel lock sha256 | `54b5e2e6cd3987c5a90782b5f676714d58dee6939b250ad1e0e1d3b9a50813de` |
| provider lock sha256 | `bd54d94422ecf1093e9af2b37dbefcdf01eddfcd822ada7fb2ee9ce2e17ac459` |
| actual native host | linux x86_64, stock `0.160.0`, personal `gpt-5.6-terra` / `high`, existing native uid `1000`, application uid `jarvis`, group `codex-clients` |
| native binary sha256 | `12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad` |
| runtimes | python `3.12.13`, uv `0.13.4`; bubblewrap `0.9.0`; postgres `16.16`, vector `0.8.6`, candidate schema `0010` |
| rendered visual check | chrome `157.0.8103.51`, actual local page/filter, no external requests or page errors |

upstream commits are published exact git pins, with matching dependency guards
and session manifest. kernel removed `cwd_scope`, centralized existing provider
identity encoding, added one private cwd-ownership fact and advanced native base
instruction v4. isolated grammar remains strict. provider validates the exact
initial and ongoing settings; it never substitutes an unchecked configuration.
jarvis resolves selection once, derives immutable main/isolated configurations,
rotates main/application identities and uses schema 5 exclusively. no work,
memory, skid or llm-tools schema/binding change was needed.

### genuine red and owning repairs

- predecessor kernel probes failed on missing `cwd` and `additional_dirs` being
  `init=False`; native event handling rejected declared activity/denial. controlled
  public acquisition now preserves borrowed dirty files, modes and `.git` through
  failure/discard/shutdown; owned disposable directories still disappear.
- predecessor provider rejected mixed callbacks/built-ins and accepted six
  independently wrong initial settings. further probes exposed disabled-web,
  deny-policy automatic-review and permission-item identity misses. all are
  repaired at the provider boundary; 34 temporary protocol cases passed through
  the public runtime and a controlled real local websocket peer.
- actual stock showed that writable-root input must include cwd and `.git`, while
  canonical returned roots contain `.git` with cwd implicit. an intermediate fix
  incorrectly changed input too and failed before submission. final input and
  exact output validation follow the audited stock projection; no subset or
  widened-root fallback. scratch/network/boolean checks remain exact.
- schema-4 mapping/composition rejected the target. final temporary jarvis probes
  passed 2 original cases, 11 composition/bootstrap/environment cases and 11
  socket/unit/installer cases. bootstrap tests use real local git/files and
  controlled remote/privacy responses; actual private ssh operations are below.
- actual native commands first lacked an execution environment because the old
  host set `CODEX_EXEC_SERVER_URL=none`; removing that one override repaired its
  owner. the isolated configuration still explicitly disables native execution.
- actual stock rejected the old public daemon-directory layout. public hardlinks
  would expose privileged control and were rejected. adr 0074's private physical
  socket and application-only file bind passed actual linux uid/namespace
  handshake, ordinary stop, host crash, replacement inode and fresh-app remount.
  no proxy, privilege wrapper or automatic application activation was added.
- actual bubblewrap could not read overflowuid/overflowgid under native
  `ProcSubset=pid`. ordinary read-only kernel metadata repaired that exact
  prerequisite under unchanged uid, no-new-privileges and empty capabilities.
  application pid-only proc and native read-only kernel-tunable protection remain.
  no package, sysctl or apparmor change. a separate network-unshare mechanism
  attempt was incompatible with the retained address-family allowlist; the
  requested unrestricted native network passed, and that allowlist was preserved.

fixture setup failures, v1-specific child assumptions and optional shell-mechanism
experiments are not product red or accepted behavior. actual native errors and
failed tools remain in their original qualification results.

### actual candidate boundaries and results

candidate source, endpoint/unit/mapping, ordinary checkout/private test remote,
postgres database/role and runtime were task-owned and separate from production.
it ran the real settings/composition, kernel/provider, journals, native runner,
service, action dispatch and recovery under actual application/host identities,
namespace mounts, home masks, no-new-privileges and empty capabilities. no normal
`jarvis serve` or second gateway consumer ran. gateway catch-up/outbox delivery
and google transport were controlled; no real discord/email/calendar write is
claimed. synthetic task memory admission was false, with an empty memory view.
no credentials were copied or exposed to native commands.

| feature | observed result and independent verdict |
| --- | --- |
| files / orientation / people | actual main authored useful project/reviewer material, searched/read it and committed locally. reviewer rejected an unsupported pronoun; native revision removed it. brief readme links resolve; no invented commitments or taxonomy. pass |
| revision / deletion | preserved the exact owner-added review line, moved the project file and repaired its readme link. deleted current obsolete draft while its committed original remained readable. no history rewrite. pass |
| helpers / reuse | actual main wrote a small stdlib csv helper: original total `9`, alpha `5`; a fresh main reused byte-identical code on changed input giving `11` / `4`. review reproduced malformed-quote acceptance and aggregate overflow emitting invalid json; small native artifact revisions added strict csv/error handling and finite aggregates. four expected outputs and six meaningful failures passed independently. no numeric framework. pass |
| visual | actual native self-contained html uses readable bars, hours, source/assumptions and a filter. review rejected silent per-filter rescaling and a missing label; final fixed `0–5 hours` domain stays visible. actual browser totals `9→5→4→9`, beta width remains `80%` of alpha even alone. no hosting claim. pass |
| actual private git | exact native host environment, no forwarded ssh agent: real commit/fetch/pull/push/ls-remote matched `6ccc8d3ab9d5b480ca9c0da17a29f293793b8494`. native event start/completion ids prove the operations; independent remote state agrees. private version link was usable during proof; test remote is removed at cleanup. pass |
| conflict | separate actual owner clone pushed a concurrent change. original local `a6f9b4a` and remote `898a248` produced a real `UU` conflict. after explicit inspected continuation, merge `dff9dcc641b66b3f9049eeae10c10d325e7fd919` retained both parents/status lines and was pushed without reset/clean/force/rebase. original failed attempts/callbacks stayed unchanged. pass with failed turns retained below |
| failed push | bounded actual ssh connection refusal retained local `14f3a3d` and an untracked dirty marker, with truthful unpushed result. a later ordinary agent-chosen push included that ancestor; local-only was a fact at the failed-push phase, not a perpetual promise. pass |
| mixed native / callback | one actual main authored an agenda and used declared calendar list/create callbacks with valid progress/final. one action awaited conversational approval with attempts `0` and no post. no native command became an action. pass |
| consent / entered-effect recovery | ordinary owner approval committed its original `approval.respond` reply. probe exited `73` after the controlled provider retained one post, before its response. fresh-process recovery reconciled the same action to succeeded with attempts `1`, one post total, immutable arguments/contract and all original callback replies. a fresh main completed every owner/host request. actual product recovery, controlled provider effect. pass |
| authority | actual main had workspace plus `.git`; final isolated compactor had empty disposable read-only cwd, disabled network/built-ins and removed its cwd after success. inherited `jarvis-memory` was explicitly off in both configurations. one actual native command found all public/private/tmp control aliases inaccessible and the global public target regular mode `000`. pass |
| permission denial | exact startup readback proved `deny`; controlled modern permission requests were denied and malformed/foreign authority failed. the live escalation task made no command or permission request and reported unavailable escalation. this is model refusal, not a live protocol-denial receipt. pass at the stated separate boundaries |
| exposed native child | actual v2 started activity mapped one agent path to native uuid; loaded public metadata matched parent/depth `1`, checkout, terra/high and `ephemeral=true`, with native source and analytics `subagent`. all four complete collector-equivalent active/archive × default/all-provider inventories omitted parent and child while loaded. [stock source](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/src/agent/control/spawn.rs) proves inherited policy/mcp/ephemeral configuration. attributed child report retained; independent child terminal completion is not claimed. pass |
| interruption / restart | first probe cancelled after command output arrived late; it proves late cancellation only. stronger run externally observed new counter `1`, dirty text and absent later marker, then interrupted exactly one observed started/uncompleted native command. control accepted; native terminal sealed cancelled. immediate host restart and fresh direct plus real-product main read the same dirty files, counter `1` and absent later marker without replay. original seals, four callback replies and succeeded action stayed unchanged. no detached-process termination guarantee. pass |

native observations for final git/mixed/reopen journeys were captured by a
temporary forwarding-only event observer. it yielded the same events and delegated
submission/control/close unchanged; this was neither a product shell ledger nor
an alternate runtime. child probe assumptions were hard-cut to the actual stock
v2 contract. ephemeral child metadata uses `includeTurns=false`; stock rejects
history reads for those children. no archive mechanism or child controller added.

### retained failures and limits

two conflict qualification attempts fenced after native work. attempt
`27504691-87c7-4d88-b6f0-7b692a8d3216` retained its local commit; attempt
`504fc190-b269-477f-ad53-8f700d85b488` left the actual merge conflict. temporary
content-free diagnostics localized the second to
`PostgresNativeJournal.record` public-progress validation: pydantic root
`value_error`. duplicate input ids and nonempty progress dispositions are distinct
possible validators; exact cause was not retained. neither failed turn is green.
explicit named operator release and a new owner continuation inspected real state,
retained both fences and original receipts, and finished without replay. the
[existing native defect issue](issues/native-protocol-diagnostics.md) stays open;
this narrows one observed boundary, not slice 3's historical cause. no guessed
logging feature, fallback prose, validator relaxation or automatic unpark.

this task performed no production deployment or state/configuration mutation.
production nevertheless changed concurrently: selected release initially
`0fc3d6444231484f1762c14c83f15d8b166b7fd6`, later observed
`b6cf4b32d32f2b01291d47291a206d4fc744fce4`, with corresponding host-unit paths and
application pid change. that observation does not establish who deployed it.
schema-4 mapping hash remained unchanged, no production notes checkout existed,
and the later host unit retained the old containment layout. that independently
changed deployment was preserved. candidate proof is not installed acceptance.

### cleanup and final checks

all temporary candidate resources were removed: native unit/endpoint/mapping,
checkout, runtime/cognition directories, both task databases, task database role,
uploaded archives/scripts and the task-owned coding terminal. the global task
unit is not found/inactive, database/role queries return no rows and fixed task
paths are absent. github initially refused deletion without `delete_repo`; the
owner used the existing account settings, and authenticated lookup then returned
`404`. no new token or broader permission was introduced.

before deliberate checkout deletion, all 99 files (including `.git`), modes,
owners and head were unchanged across removal of the obsolete task candidate
source. aggregate snapshot sha256 was
`39dc9c1bac18134249e6629a591246de1b334ce8878ece04f8f58ff5bd10ae0b`, head
`ee26bf1e341aae2ce5271be7b6e2d4fe47b8d7b0`. the actual release-pruner deletion
loop targets only forty-hex directories under `/opt/jarvis/releases`; the
persistent checkout is outside that tree. the production pruner was not run.

final child-era host stop reached the existing ten-second deadline and systemd
force-killed stock; it was not a graceful child shutdown. [stock handles sigterm
and sigint through the same drain path](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/app-server/src/lib.rs), waiting on active turns/admissions and
bounded internal cleanup. changing signal would not repair that limit. the
accepted best-effort interruption contract and bounded kill were retained;
failed-unit bookkeeping was cleared only after recording the timeout. earlier
idle stop/crash/remount checks remain distinct. three native fork attempts also
reported missing parent rollout before child creation, as ephemeral history is
not persisted. successful fresh v2 child creation is separate; this does not
make all native spawning unavailable or add a product fallback.

after independent review consumed their evidence, task-local probes, logs,
archives, source cache and qualification environments were removed.
new temporary probes were deleted; standing regressions and their existing
controlled-peer fixture maintenance remain. final frozen checks after deletion:

| repository / check | result |
| --- | --- |
| kernel | lock/sync, 176 retained tests, formatting/lint, pyright, build, audit, diff check passed; 2 paid/live tests deselected |
| provider | 983 retained tests passed; 1 expected sdk-present skip; 40 paid tests not run. separate clean base-wheel absent-sdk node: 1 passed, zero skips. formatting/lint, pyright, audit, source/wheel build, base and claude-extra imports passed |
| jarvis | `scripts/verify` passed: frozen lock/sync, diff/format/lint, pyright, documentation links, wheel/sdist, fresh install/cli/dependency identities and audit |
| existing capture/retry | unchanged `tests/capture_retry.py` passed against a separately migrated disposable schema `0010`; expected synthetic failed-memory-publication diagnostics, exit zero |

audits reported no known vulnerabilities; private git packages are not
pypi-auditable. local upstream checks used darwin arm64; candidate and disposable
postgres proof used actual linux x86_64. no hosted ci or broad provider/model
matrix is claimed. the [installed handoff](issues/private-workspace-installed-cutover.md)
and pre-existing native protocol issue are the remaining explicit boundaries.

### compatible memory mainline integration

main advanced to `b5df0ec4a1e756691307e63435234598023fa5b3` during qualification.
its native archive paging and collector fairness repairs were merged rather than
regressed by the workspace dependency pins. jarvis integration candidate
`a72b29e55b8c31fea526dd55b7c6ce96a8668385` has parents `edb3b79` and that exact
mainline. the adopted collector is byte-identical to mainline. only collector
code and dependency guards/manifest/lock change from the completed workspace
source; workspace behavior and native-role revisions remain unchanged.

| final artifact | identity |
| --- | --- |
| provider | `ea9f82025632926a7c7e47d6333fb9346f6ee86c`, combining workspace `d69c7c6` with exact compatible paging `6582551ec87af440c53f30ce7357d7a90c32e549` |
| kernel | `9f5f951272536d51567995cbd693d1239ad59eb9`, combining workspace with compatible bridge `42e7ecdef3fc2a16fddef8a450456cfa503b1d3e` and final provider pin |
| jarvis lock sha256 | `6407b1908ae1144358203468413481e2f590cd9e2c1ec5159917a4d93b8576f4` |
| kernel lock sha256 | `a0022c587a8a65c723811451d1d2e3898d76ff6d440ac5f15c487b85e6ceea00` |
| provider lock sha256 | unchanged `bd54d94422ecf1093e9af2b37dbefcdf01eddfcd822ada7fb2ee9ce2e17ac459` |

source/adversarial audit proved provider native transport, policy, catalogue,
events, types, runtime and manifests byte-identical to `d69c7c6`; only its archive
reader and archive documentation changed. kernel production/test blobs remain
byte-identical to `b7218b9`. moving upstream mains with newer runtime/model
contracts were excluded deliberately; this composition retains stock `0.160.0`.
no compatibility shim, duplicate archive reader or restored temporary test.

an affected-boundary live proof used a new separate native host/unit/mapping,
ordinary local git checkout and application namespace with the same identities
and restrictions. actual jarvis selection/configuration factories, kernel native
supervision and provider executed file work plus one declared read callback in
one turn; an existing transient journal supplied the explicitly temporary host
boundary. independent native event and external filesystem/git inspection proved
exact `combined pins verified` plus newline, local commit
`4c4864325cc924ee170a480daabbf568ce3e6c4f` and clean checkout. borrowed modes
survived discard. the actual isolated jarvis compactor completed under the frozen
read-only/disabled policy and its generated cwd disappeared. this is combined
primitive/configuration proof, not a rerun of product journals, connector effects
or gateway delivery. those remain qualified at the initial full candidate above.
no new private remote, child or credential was needed.

the first new probe used an invalid request scope and failed before native
acquisition; correcting its fixture to `job` is not product red or a runtime
repair. a native git command also failed before the agent inspected staged state
and corrected its arguments; that failure is retained rather than counted as
successful execution. staging reused two generic temporary filenames and
overwrote their previous contents; the owner explicitly selected their disposal.
further staging used the task prefix. no production configuration or repository
file was overwritten.

independent source and affected-boundary review passed. final combined upstream
checks passed again: kernel 176 retained tests, two paid/live cases deselected;
provider 983 passed, one expected sdk-present skip and 40 paid cases excluded,
plus the separate absent-sdk clean-wheel execution. lint, types, build/imports,
lock checks and audits passed with the same private-git audit limits. the existing
capture/retry regression passed against another separately migrated disposable
schema `0010`. final jarvis `scripts/verify` passed after integration probe
deletion, including frozen install, source/type/docs, build/import and audit checks.
the second host/unit/mapping/checkout/runtime, disposable database, uploads,
temporary probe and task-owned managed-python link were removed after review;
local probes, logs, archives and upstream check artifacts were also deleted.
full paid feature journeys were not repeated: audited native behavior is unchanged
and the relevant combined interfaces were exercised. production remains separate.

## explicit costs

- trusted native commands can act beyond repo content and lack connector-level
  consent, action recovery and exactly-once guarantees; stop may not end detached work.
  the native host can reach its ten-second drain limit and force-kill; inspect
  files/git after restart rather than inferring command completion.
- agent-chosen git leaves dirty/unpushed work without guaranteed off-host backup;
  moves can stale external links, and deletion retains committed history.
- repo files supply custom tools and interactive artifacts, but no hosting,
  discoverability ui, uptime promise or television integration.
- the borrowed path is explicit in compatibility identity; mutable content is not.
  main must inspect changing files rather than depend on a frozen content snapshot.
- separate candidate proof defers production acceptance; deleting temporary tests
  reduces retained regression coverage. no extra framework conceals those limits.

## source delivery and library mainline preservation

merge-time integration preserves the exact qualified jarvis pins above. the
library mains had independently moved to stock `0.165.0` and typed endpoints;
workspace changes were ported onto those current contracts without downgrading
or adding a compatibility path. provider [pr 57](https://github.com/NielsdaWheelz/llm-calling/pull/57)
and kernel [pr 29](https://github.com/NielsdaWheelz/llm-agent-kernel/pull/29)
use merge ancestry so `ea9f820` and `9f5f951` remain reachable after task branches
are deleted. jarvis [pr 72](https://github.com/NielsdaWheelz/jarvis/pull/72) keeps
its own stock-0.160.0 selection and immutable pins.

a separate bounded current-library proof used offered `gpt-6.1-sol/high`, real
native file/git plus one callback, strict isolated execution, inherited-mcp
suppression and the private socket mask. [the provider evidence](https://github.com/NielsdaWheelz/llm-calling/blob/a1ed72f3a94e527a9255988215207c07d7b74a14/docs/native-agent-evidence.md#native-workspace-and-callbacks-on-current-stock)
records its separate account state, read-only existing authorization, disabled
refresh and exact limits. it does not activate or requalify jarvis on the newer
runtime. current-library source/hosted checks and task cleanup remain distinct
from the final production handoff.
