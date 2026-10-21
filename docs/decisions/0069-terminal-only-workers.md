# adr 0069: terminal-only skid workers

- status: source implemented and isolated-qualified, 2026-10-21; installed cutover separate.
- supersedes: worker-native targeting, reads, writes, identity and waits in
  adrs 0052/0064/0068. separate native cognition and memory archives remain binding.
- paired contract: [terminal-only control](https://github.com/NielsdaWheelz/skidbladnir/blob/2c2401e8b354cbcf7b8d97dbf22679ed5fad4504/docs/terminal-only-control.md).

## decision

keep the eleven worker tools and their existing authority, durable read/action,
wait/cancel and no-replay owners. targets accept `t-` plus 16 lowercase hex only.
skid owns immutable terminal refs and foreground/screen observation. jarvis never
decodes refs, discovers conversations or substitutes provider-native history.
`agent.read` accepts target/maxBytes and returns bounded rendered terminal text.
wait states are idle/working/needs-input. terminal input proves written bytes,
never provider acceptance or completion; close retains separate effect facts.

reuse generalized installed-state composition from existing v8 source commit
`2353878ba768cb7ff544bb94e3f87065d5545e14`, cherry-picked onto current main with
upstream security fixes retained. remove native variants through worker v9's
existing catalog/fingerprint cutover. no compatibility decoder or fallback.

classify known retired revisions v1–v8 before decoding the nested target with
the v9 schema. finalized succeeded/failed/uncertain/cancelled rows retain opaque
target/arguments/results, with common immutable digest/effect/lineage/state/time
validation. archives never execute. unfinished retired rows block activation;
unknown/malformed revisions and malformed current rows cannot claim archival
exemption. no data rewrite or new table.

## evidence and cutover

temporary red/green proof passed against actual postgresql 16.15 and the public
skid `agentcli.Run` implementation over genuine signed installed state and an
authenticated tls gateway with real isolated tmux. the disposable runner maps
only its fixture origin to its random test port; it does not qualify installed
fleet networking or a stock provider. actual `ToolExecutor`, `PostgresReadRecorder`
and `ActionPositionRecorder` cover discovery/info/read replay, captured send,
wait/cancel, changed-pane refusal and lost-successful-reply no-replay on executor
re-entry. eight finalized v8 terminal/native status combinations preserve stored
json facts and digest; malformed common/current/unknown records refuse. activation
and recovery refuse retired required-event backlog and unfinished v8 waits.

the initial suite passed 12 checks; the final finalized-status query refinement
passed its two affected checks, including one new queued-v8-wait case: 13 distinct
checks in total. independent parent and host-engineer code/test/refactor review
passed. `scripts/verify`, ruff/format and full strict pyright pass. disposable
controllers, injected baseline sources, owned postgres and ssh forward are removed;
no new retained tests or dependencies. existing memory regressions were not run
by this worker slice; no memory behavior changes. whole installed activation
composition, physical provider/network/service and external delivery remain
`NOT_RUN`. action activation uses the same extracted authoritative database query
as `check_activation`; no fake cognition lifecycle is counted as acceptance.

installed cutover remains separate. drain old actions/waits/required events
under their owning release; the existing [service-state access blocker](../issues/skid-installed-state-access.md)
is outside this assignment. no privilege bridge, copied stale credentials or
silent activation is added.

accepted costs: saved-history and native-result/control/identity capability is
removed, including captured conversation refs. terminal history is limited to
what tmux retains. coordinated matching consumers are required; forward repair
replaces legacy compatibility. independent provider archive/memory APIs remain.
