# adr 0052: cut worker control to current skid

- status: source implemented and worker client qualified on all three production
  gateways, 2026-09-29. cognition and main-service activation remain `NOT_RUN`.
- authority: owner-approved skid-only retirement specification and subsequent
  implementation request. keep the existing shared codex app server; repairing
  its missing deployment is a separate follow-up, and jarvis may remain down.
- supersedes: worker transport, refs, tool roster, projections and historical
  receipt interpretation in adrs 0044, 0045, 0048 and 0049. cognition, memory,
  connectors and their durability contracts remain unchanged.

## decision

jarvis consumes the installed current skid cli, one subprocess per operation,
with fixed `--config` and `--json`, argv without a shell, and input text through
stdin. skid owns configuration validation, opaque refs, gateway routing,
conversation/process lifetime validation and native provider control. jarvis owns
current owner intent, the existing write gate and action recorder, bounded
current-shape decoding and truthful settlement. no second client, worker table,
provider-home table, ref codec or fallback transport remains.

exactly nine tools: list, info, start, read, send, text, keys, stop and close.
info requires terminal or conversation target; read requires latest, history or
terminal source; stop requires native or terminal mode; close requires
conversation_and_terminal or terminal_only scope. send uses native peer input;
text explicitly pastes terminal input. no interrupt or kill alias remains.

before preparatory lookups, writes require current owner input. native preflight
inspects the original captured conversation and turn. a second, optional terminal
inspection supplies its name only when its observed conversation matches the
captured one. terminal loss or reassociation never prevents explicit conversation
authority. terminal operations inspect the original terminal. compound close
inspects both original targets; failed native inspection retains the captured
identity and may still ground explicitly authorized exact terminal closure.
new `observedRef` never replaces the current action's ref. no worker text reaches
the write gate. the gateway owns races after preflight.

stdout drains concurrently with bounded stdin delivery, capped at one mib
inventory or 64 kib otherwise. stderr is discarded at the file descriptor;
no diagnostic bytes are captured or logged. early stdin closure does not erase
a valid owned stdout receipt. each process has twenty seconds around skid's
fifteen-second command clock. bounds are twenty seconds for reads/start,
forty-five for one preflight and a write, sixty-five for two preflights and a
write; native name grounding and compound close use the last bound. parse the
owned closed envelope before exit status. partial inventory and unconfirmed
outcomes can exit nonzero. cleanup terminates only the child cli.

writes retain `BilledOnce`, one executor entry and `max_attempts=1`. spawn
failure is not_sent. after spawn, timeout, stdout overflow or malformed reply
is unknown unless a valid owned receipt proves otherwise. known created conversations and separate halt/closure outcomes are
staged in the existing action before uncertainty. native acceptance proves
admission; terminal written proves dispatch; neither proves completion.
unknown writes are terminal uncertain and never replayed, including recovery.

## historical data and activation

delete agent_history.py and codex_history.py. finalized old agent revisions
v1 through v5 and the retired codex family are opaque archives, selected before
current catalog or payload decoding. validate common immutable effect, digest,
lineage, attempt, state and timestamp invariants; preserve raw arguments/results.
render only action id, tool, recorded status and `receipt details unavailable
after cutover`. current malformed data remains a defect. old nonterminal rows
block activation and have no recovery codec.

old code must settle or explicitly reconcile unfinished actions/turns, materialize
required action resolutions and drain their processing and delivery before the
catalog change. changing the cli or private client file requires a prepared
pause and clean stop; identical bytes are inert. activation also refuses
incompatible/in-flight actions, stale turns and undrained resolutions/delivery.

jarvis reads `/usr/local/libexec/skidbladnir` (regular root:root 0755) and
`/etc/jarvis/agent-client.json` (regular jarvis:jarvis 0600), configured by
`JARVIS_AGENT_CLI_PATH` and `JARVIS_AGENT_CLIENT_CONFIG_PATH`. dev-server installs
the admitted devbox gateway artifact as the root cli. human fleet provisioning
supplies all three peers' private configuration explicitly to
`deploy/install-agent-client`; full private-state install composes it and skid
remains its validator. `deploy/verify-agent-client` independently qualifies the
worker client while cognition is down; full containment composes it. full gateway bearer
access replaces ssh allowlisting, an accepted authority cost. service containment,
including ProtectHome, remains. actual service-uid/restriction probes are required
before any resume; absent cognition is reported separately, never repaired here.

costs: one cli process per call, coordinated cli maintenance, lost typed
interpretation of old receipts, and no automatic unknown-write retry. temporary
integration/live tests are deleted only after independent acceptance review;
this exception does not restore the retired behavioral harness.
