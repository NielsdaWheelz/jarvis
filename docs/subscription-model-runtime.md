# subscription model/runtime

status: f3 implementation contract under [adr 0075](decisions/0075-v2-completion-and-subscription-model.md)
and [adr 0076](decisions/0076-role-models-and-delegated-choices.md),
2026-11-16. specification only; implementation, live qualification and production
activation NOT_RUN. the [roadmap](implementation-plan.md#v2-finishing-prs) owns
sequence; this document owns model selection and its qualification.

## goal and boundary

main uses authenticated `gpt-6-astra/max`; compactor and dreamer use fixed
`gpt-6.1-sol/xhigh`. both routes use the owner's personal codex subscription through
`provider-runtime` in `llm-calling`. preserve distinct role capabilities and recovery.
main chooses supported model/effort combinations for its native children and skid
workers. worker choices are not constrained by either host-owned model selection.

owner refinement, 2026-11-16: adr 0076 replaces the earlier shared-selection
decision. the owner also selected per-session skid choices, superseding adr 0068's
profile-command-only restriction for this bounded extension. profiles still own
provider/account/executable defaults; main chooses per-launch model/effort overrides.

`gpt6astra-max` is owner shorthand, never a wire identifier. no model substitution,
effort downgrade, api-key generation route, alternate provider or fallback for
the fixed host roles. deliberate child choices are not fallback. the
existing api-backed embeddings and connector credentials remain separate.

no new table, migration, journal, public tool, routing service, credential flow,
persona, benchmark or orchestrator. f2 owns the existing native-progress defect,
discord reliability and final combined journey. this slice neither closes those
issues by assertion nor activates production. no product preference is outstanding.

## audited starting point

jarvis `80af4e4` includes f1 and events. its resolver currently supplies one shared
selection. `build_definitions` already accepts separate main and isolated provider
configurations; reuse that interface. isolated roles keep empty read-only workspaces.

| artifact | current exact selection |
| --- | --- |
| provider-runtime | `ea9f82025632926a7c7e47d6333fb9346f6ee86c` |
| llm-agent-kernel | `fcb6ecfb4088d85f64aafd8689e728058db27b0a` |
| llm-tools | `662a63a863bfefbc9c4f16025bd82f47262d99d6` |
| universal-memory | `b616ee924454f40305c49d3b73e81694819ba1e4` |
| cognition | sole qualified catalog key `gpt-5.6-terra`; reasoning `high` |
| stock runtime | `0.160.0`, provider-owned startup containment catalog |

the pinned provider's own stock catalog contains both selected model/effort pairs;
its public catalog exposes dispatch identity. qualify this stack FIRST. source
support does not establish entitlement or successful inference on the actual
personal endpoint. newer upstream stock `0.165.0` is a different contract, not a
demonstrated prerequisite. do not upgrade unrelated dependencies for recency.

## selection contract and api

reuse `CredentialRef`, `AgentRuntime.model_catalog`, `ProviderConfiguration` and
the existing resolver. no second discovery client or copied provider model table.

| fact | required value/source |
| --- | --- |
| provider/transport | `codex` / `sdk` |
| auth reference | `CredentialRef("local_account", "personal")` |
| authentication | provider verifies actual subscription authentication; a local profile name alone is insufficient |
| main | `JARVIS_CODEX_MODEL`: only the release-qualified main row's exact `key`; dispatch `gpt-6-astra`, effort `max` |
| memory | fixed qualified memory row key; dispatch `gpt-6.1-sol`, effort `xhigh`; no new environment knob |
| dispatch identity | selected row's `dispatch_model` equals that role's target |
| reasoning | exactly one option whose `key` and `native_wire_value` equal that target effort |
| catalog binding | actual `catalog.definition_revision` and `row.row_fingerprint` |

qualification discovers both rows on the service-equivalent personal route and
records their actual keys. keep one fixed two-entry selection map: each key binds
its exact dispatch model and effort. main settings validate ONLY the main key;
the qualified-model manifest contains both. remove `gpt-5.6-terra/high` from active
selection. update `.env.example` and `deploy/install-private-state` to emit the
main key; the installer consumes the checked-in definition. do not guess an id,
choose the first/default row, accept a title match or keep the old key as an alias.
missing or ambiguous selection blocks qualification; repair the actual route.

target internal interface:

```python
async def resolve_provider_configuration(
    *, runtime: AgentRuntime, profile_key: str, model_key: str
) -> ProviderConfiguration:
    ...
```

remove its caller-selectable `reasoning` argument and `high` default. declare the
two fixed selections once in `definitions.py`; settings, resolver and composition
consume them. no new effort variable, mutable role policy or model-routing service.

resolver behavior, before model submission:

1. require the existing personal profile and a release-qualified selection key.
2. call `runtime.model_catalog("codex", auth, transport="sdk")`; require exactly
   one row with that key and its exact target dispatch identity and effort key/wire value.
3. construct `ProviderConfiguration` with that row's key/fingerprint, catalog
   revision, explicit effort and existing restricted native options. evidence
   changed between selection and session opening is an error, never permission
   to use defaults. a fresh process may bind a newly observed valid catalog.
4. `_compose_main` resolves main and memory through the same runtime/auth/resolver.
   derive main's workspace policy from its own resolved base using
   `main_provider_configuration`; rename its misleading `isolated_provider`
   parameter. `_isolated_memory_runtime` resolves only the fixed memory key,
   never `settings.codex_model`. reuse one discovered catalog within a composition
   where the existing runtime permits; no cache or second discovery protocol.
5. existing main and isolated definition boundaries assert their respective
   key/effort. widening a global allowlist must not admit sol as main or astra as
   memory. these checks never constrain native children or skid workers.

the provider owns subscription checks, catalog normalization, exact wire dispatch,
effective native selection/policy validation and native lifecycle. the kernel owns
definition fingerprints, supervision and base instructions. jarvis owns the fixed
product choice and composition. use these public contracts; add no private json-rpc
calls, auth-file parsing, duplicate validation protocol or alternate sdk adapter.
the current provider verifies `account.type == "chatgpt"`, rejects api-key native
authentication and validates returned model, `modelProvider == "openai"` and
reasoning effort against the resolved selection. catalog revision/row drift is
already rejected at session opening; add no catalog poller or duplicate fingerprint.

## native runtime, authority and limits

preserve slice 4's mixed main/native/callback contract and isolated-role containment:
main's ordinary private checkout, native tools/subagents and host callbacks; no
native web or mcp. isolated roles remain tool-free compaction and memory-read-only
dreaming through their existing plans. no new native authority or connector secrets.

qualify actual provider-reported model/effort and effective policies, not just
requested values or model-written claims. unexpected selection or permissions must
follow the existing provider/kernel failure path before usable work continues.
if the current public contract cannot establish a required fact, repair its owning
library and publish/adopt an exact commit; do not approximate it in jarvis.

`build_agent_runtime(max_turn_seconds=300.0)` limits isolated turns. controlled
main passes no aggregate deadline and is not capped by that setting. compactor
and dreamer separately retain 300-second cooperative run bounds, their existing
token/tool limits and foreground precedence. cooperative bounds are not a promised
wall-clock sla. measure live useful completion under the actual limits. no blanket
timeout increase, per-role effort exception or outer timeout around entered writes.
compaction can delay foreground preparation; exhausted/invalid compaction retains
its existing parked state. this is not merely a background-performance trade-off.
if the selected memory model/effort demonstrably conflicts with a bound, surface
measured evidence
and a recommended narrowly scoped amendment before changing that behavior.

reuse the schema-5 host mapping, original personal account, private physical socket,
application-only publication, distinct identities and existing host policies.
copy no credentials; initiate no login or codex/claude installation. the separately
specified skid release adoption below is required. the stock catalog
remains provider-owned. if a demonstrated repair changes runtime/provider pins,
qualify the complete compatible host/application pair and preserve the current
f1 tools/memory dependency composition. do not restore a retired transport or codec.

## delegated model choices

native codex children use stock `spawn_agent.model` and `reasoning_effort`.
`model` is the native dispatch slug, not the provider library's catalog key.
stock `0.160.0` already exposes these fields by default through
`features.multi_agent_v2.expose_spawn_agent_model_overrides`. preserve that exposure
for main; isolated roles still have no agents. children may use any model/effort
supported by the actual native runtime, not only the two jarvis role selections.
omitted fields retain native defaults/inheritance; explicit model without effort
uses that model's default. stock applies role configuration after explicit options;
inspect inherited/default roles and prove the chosen alternative survives the
actual configuration. repair a demonstrated default-role lock at that configuration
boundary. do not promise arbitrary role/model combinations. inspect effective child
settings and integrate its completed result. no wrapper, new subagent manager or forced
default-model policy. unsupported choices fail through the existing native tool.

installed skid `v0.24.3` has no override flags. extend its public start path first,
then consume it in jarvis; never inject `/model` commands or edit profile defaults.

| `AgentStartInput` addition | contract |
| --- | --- |
| `model: str \| None = None` | 1–255 utf-8 bytes, no controls or edge whitespace; native model identifier passed as literal data |
| `effort: str \| None = None` | 1–64 utf-8 bytes, no controls or edge whitespace; selected provider's native effort |

other start fields and the closed schema remain unchanged. absence/null means no
override; explicit values enter the immutable `ActionRequest` arguments. jarvis
passes separate argv elements `--model VALUE`, `--effort VALUE`; omit absent flags.
prompt remains literal stdin. no raw extra-argv or caller-provided launch command.
do not apply main's model allowlist or translate every provider to codex effort.

upstream wire: existing `POST /v1/sessions`, `kind: "agent"`, gains optional
`model`/`effort` strings with the same bounds. omit absent fields; null remains
absent under the existing decoder, while empty strings reject. `kind: "terminal"`
rejects supplied overrides. preserve `cwd`, `profile`, `optionalTmuxName`, `group`
and existing `objective` semantics. keep the closed request and current response
envelopes; no extra endpoint or wire-version selector.

skid owns launch translation, before terminal creation:

- when both fields are omitted, execute the existing profile command unchanged.
- with an override, require a provider-tagged `codex`/`claude` profile and a single
  plain command word: an executable name/path with no whitespace, shell operators,
  substitutions, assignments or embedded arguments. unsupported forms refuse
  inside the sessions manager before terminal/tmux creation; never silently drop
  a supplied option. map its narrow launch-option refusal through the gateway to
  existing `InvalidRequest`/not-sent evidence, with a useful non-secret reason.
- the supported profile contract requires its command/wrapper to forward arguments
  to the named native provider. the inspected personal/work/work2/claude-work local
  wrappers do so. qualify the actual selected machine's profile, not a local proxy.
- codex lowers to `--model VALUE` and `-c model_reasoning_effort=TOML_STRING`;
  claude lowers to `--model VALUE` and `--effort VALUE`. encode the toml string,
  then shell-quote each argument separately at skid's existing shell boundary.
  reuse its encoded launch → terminal-exec → initialized-shell route so existing
  account wrappers remain effective. no ad hoc shell parser or eval of model text.
- retain provider/account/environment/cwd/profile authority. validate supported
  option lowering and input shape before creation. native acceptance of model/
  effort and entitlement may still fail in the provider afterward; no invented
  preflight catalog or cross-provider effort enum. terminal creation/input receipts do not claim
  inference acceptance, effective model or completed work.

reuse the current start success/error schemas and separation of creation/input
facts. captured arguments prove what was requested, not what a worker ran. no
new worker state table, model telemetry ledger or mutable-session control tool.
main can deliberately launch a new worker with a different selection; changing
existing workers remains ordinary native terminal interaction, not a new api.

hard-cut jarvis's shared worker binding to `jarvis-agent-control-v11`; classify
finalized known v10 records as opaque before nested decoding, adding v10 to
`actions._RETIRED_AGENT_REVISIONS`. unfinished v10 work, including queued
registered waits, must finish or be cancelled and have its existing outcome
published under the original release before activation. a terminal uncertain
receipt stays opaque and non-retryable; it is not a blanket permanent cutover
block. preserve exact target refs, one executor entry,
observation/wait semantics and partial-launch evidence. do not revive v7/v8 paths
or add a second worker adapter. install the qualified skid release only as the
separate implementation handoff; preserve running terminal runtimes and profiles.

## compatibility, recovery and cutover

update the existing application session revision and both qualified-model entries;
retain the manifest schema. exact dependency changes, if any, must agree across
`pyproject.toml`, `uv.lock`, `EXPECTED_GIT_PINS` and `session-compatibility.json`.
use the kernel's complete definition fingerprint, including provider selection
and catalog binding. never add a second session cache or manually copied hash.

model/effort/catalog/runtime changes invalidate incompatible live leases. restart
reasoning in a fresh session from canonical requests and original receipts.
never rewrite historical fingerprints, executed arguments, read results, action
contracts or sealed terminal evidence to look current. existing journal recovery
and unknown-effect/paid-read barriers remain authoritative; model change grants
no repeat permission. preserve strict progress/terminal schemas and explicit stops.
an old sealed terminal still settles from its original stored schema and receipts
without new inference. a changed model does not invalidate that evidence; only
incompatible live session restoration is rejected. add no model migration.

qualification uses one temporary candidate: separate unit/endpoint/mapping,
database, runtime state and disposable task checkout; same actual personal
subscription route and service authority. production's host unit, socket, mapping,
checkout and running release remain untouched. candidate isolation is not a new
production deployment mode; follow [operations](operations.md#private-workspace-handoff).

final installed activation belongs to [f2](runtime-reliability-and-integration.md)
under [adr 0077](decisions/0077-production-acceptance-and-fresh-reset.md): isolated
fault proof and qualified artifacts precede cutover, then the actual production
journey and fresh history reset. apply existing activation checks: incompatible unfinished
contracts block; current unknown outcomes retain their reconciliation and causal
barriers. reconcile incompatible work with its original qualified release.
preserve opaque finalized evidence, not legacy execution paths.
host replacement requires application restart/remount under adr 0074. retain only
the selected release and one candidate; no permanent rollback installation.

## implementation boundaries and files

| owner | files and responsibility |
| --- | --- |
| jarvis selection/composition | `src/jarvis/definitions.py`, `kernel.py`, `settings.py`, `cli.py`, `.env.example`, `deploy/install-private-state`: two fixed role selections, exact dispatch/effort checks, main-only configuration, remove retired model/default |
| jarvis compatibility/integration | `src/jarvis/session-compatibility.json`, `pyproject.toml`, `uv.lock`; reconcile exact published pins once, update affected operational instructions/evidence |
| jarvis worker adapter | `src/jarvis/agent_tools.py`, `agent_control.py`, `actions.py`, affected definition guidance: optional immutable start fields, exact argv, v11 and retired-v10 disposition; no new receipt schema |
| skid cli/transport | `internal/agentcli/run.go`, `internal/fleetclient/{request,start}.go`, `internal/gateway/{sessions,gateway}.go`: optional `model`/`effort` through the existing request/create path, omit absent fields, map launch refusal to the existing invalid-request envelope |
| skid launch owner | `internal/sessions/{types,validation,create}.go`: provider/bare-command refusal before creation, exact native argument encoding through the current launch path; no wire-version field or new profile system |
| provider, only for a demonstrated gap | `llm-calling` public agent-runtime catalog/auth/dispatch/containment surfaces; repair here, not in jarvis; preserve public ownership and qualify exact replacement |
| kernel, only for a demonstrated gap | existing provider port/fingerprint/supervision contracts; no jarvis-specific model choice or duplicated provider checks |
| host, only if its contract changes | `deploy/codex-host`, contained service/install/verification files; candidate proof and later stopped pair replacement, never mutate production during qualification |
| f2, separate | discord/native diagnosis, required owning-layer failure repairs and final product journey; reconcile shared pins with f3 before combined acceptance |

one integration owner owns shared pins and final composition; other work stays on
these non-overlapping boundaries. no upstream handoff is necessary merely because
f3 exists. inspect the merged predecessor before editing, preserve concurrent
changes, and remove only actually superseded model selection paths/constants.

## content design

the content designer owns configuration/error wording and the usefulness rubric;
there is no new persona or owner-facing model feature.

- distinguish configured, catalog-advertised, provider-accepted and completed.
  evidence must never turn an advertised model into a claimed successful run.
- errors name the failed boundary and concrete repair: personal authentication,
  exact catalog row/effort, runtime policy or native protocol. use existing error
  surfaces, not a new status schema. claim non-submission only with provider proof.
- record non-secret model/key/effort, auth kind, artifact identities, elapsed time
  and result/disposition. omit account identifiers, tokens, raw exceptions,
  private prompts and hidden reasoning. no routine discord startup announcement.
- main output answers the task, grounds claims in observed results and states
  unfinished work. a launch or self-report is not evidence of tool/child completion.
- delegate guidance says main may choose supported model/effort for the task;
  omission uses the documented native/profile default, not main's fixed pin.
  keep briefs explicit about task, context, constraints and expected result. do
  not impose a model-ranking policy, cheapest-first routing or mandatory delegation.
- compaction preserves attribution, chronology, corrections and uncertainty within
  its existing result bound. dreaming stays quiet and grounded in retained evidence;
  an empty valid synthesis is allowed. no forced novelty or required search count.

## temporary proof and acceptance

implementation follows red → green → refactor → delete under adr 0075. assign an
independent adversary at contract, implementation and final evidence boundaries;
the designer reviews actual outputs against the rubric. no standing review system.

1. **red:** temporary integration checks exercise the real settings/resolver/role
   composition with controlled catalogs; current `gpt-5.6-terra/high` must fail the
   target assertions. cover wrong/missing/ambiguous key, swapped role selections,
   wrong dispatch/effort, non-subscription auth and incompatible catalog/policy
   evidence. test each rejection at its responsible public boundary, not every layer.
2. **green, real native:** on the actual personal route, run the assembled main
   definition with current tools. complete a small useful task using a real host
   callback and ordinary native checkout operation; exercise progress, steering
   and valid terminal settlement. use small synthetic image/pdf inputs already
   materialized in the checkout to prove existing attachment-reading capabilities;
   no repeat r2 ingestion proof. independently inspect results. prove a native
   child with an explicit supported alternative model/effort, actual reported
   child settings and completed useful result integrated by main.
3. **green, real memory:** run actual compactor and dreamer definitions through the
   fixed sol/xhigh selection with synthetic attributable source material, a
   correction and uncertainty. validate bounded output, isolated policies and memory reads
   when chosen and quiet/atomic completion. complete under existing enforced
   bounds; record elapsed time.
   don't demand an empty or nonempty dream, or script its tool sequence.
4. **focused recovery:** with old and target definitions plus real postgres,
   reject old live-lease reuse; settle a pre-cutover sealed terminal exactly once
   from its stored schema without provider inference, retaining current-request/
   stop checks. preserve original action/read bytes and unknown-outcome barriers.
   exact redelivery within an admitted original callback returns its original
   receipt without redispatch. after fencing, old callbacks remain rejected;
   fresh reasoning consumes preserved receipts. a genuinely new mutable read
   retains f1 freshness.
   use disposable local work; no outgoing mail, broad google/r2/fleet rerun or
   destructive production fixture is needed for this model change.
5. **delegation:** controlled cli → gateway → real launch-builder checks prove
   optional fields, exact literal argument lowering for codex/claude, omission
   defaults and refusal of unsupported profiles/forms before tmux. include quoted
   metacharacters as data and an unsupported native effort; distinguish pre-launch
   refusal from provider rejection after creation. prove stored override arguments
   and partial-launch receipts survive exact redelivery without relaunch. real
   candidate main launches one installed codex worker with an explicit alternative
   model/effort, observes actual provider settings and integrates its useful result
   through the existing wait/event path. local forwarding alone is not live proof.
   qualify available provider paths honestly; owner-deferred `claude-work` stays
   unavailable, with controlled lowering proof and live execution NOT_RUN. prove
   v10 pending waits block v11 activation until old-release disposition; finalized
   receipts stay opaque. preserve running terminals while updating installed skid.
6. **refactor/close:** remove duplicate selection/defaults and any demonstrated
   obsolete path. run affected libraries' required checks, retained approved memory
   regressions and `scripts/verify`; repeat live proof only for a changed relevant
   boundary or unresolved finding. delete only f3's new probes/resources after
   accepted green. retain concise evidence here, not another report/harness tree.

acceptance requires all three host roles to use the actual personal subscription
with their exact fixed model/effort; effective authority and strict protocols
remain intact; useful native, memory and selected worker work completes; original
recovery holds; pins/configuration agree; findings are resolved or named blockers.
unavailable target, quota failure or incompatible policy blocks the relevant proof.
never accept a substituted host-role model, simulated subscription or skipped host
role as proof. deliberate delegated choices retain their separate acceptance.

evidence records exact jarvis/library commits, stock version, selected catalog key,
dispatch/effort, revision/fingerprint, non-secret authentication proof, requested
versus provider-reported values, controlled versus live boundaries, useful outcomes,
timing, review conclusions and resource deletion. retain old evidence with its old
identities. f2 consumes these exact qualified artifacts; production and broader
competitor-parity claims remain outside this proof.

trade-offs: `max` for main and `xhigh` for memory can increase latency and
subscription usage; compaction can delay foreground work. one subscription is a
shared availability/quota dependency; no fallback for fixed roles means
an outage is explicit. qualifying the current pinned runtime minimizes unrelated
change but does not establish that it is newest. a candidate proves the selected
model/runtime boundary, not installed v2 acceptance or comparative intelligence.
per-session skid choice adds an upstream release/adoption and worker contract
cutover. bare forwarding commands cover the inspected fleet; compound profile
commands keep default launches but reject overrides. support for rewriting arbitrary
shell commands is deliberately excluded.
