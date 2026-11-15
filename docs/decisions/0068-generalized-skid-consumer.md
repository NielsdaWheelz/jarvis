# adr 0068: generalized skid consumer

- status: source adapter implemented, 2026-10-20; installed cutover BLOCKED.
- authority: owner-approved skid standalone generalization and explicit decision
  to leave jarvis service deployment integration separate, recorded as an issue.
- supersedes: adr 0052's copied private client-json provisioning and adr 0064's
  launch model/effort overrides. exact target, one-shot write, observation,
  cognition and other authority contracts remain binding.

## decision

consume the matching skid cli with fixed `--config STATE_DIRECTORY` and `--json`,
argv without a shell and literal input through stdin. configure the absolute
state directory through `JARVIS_AGENT_STATE_DIRECTORY`; skid owns its installed
identity, signed routing and current membership. no legacy client-json reader.
retain jarvis's personal machine/profile enums and the separate terminal/native
contracts. wire-only profile descriptors admit an omitted provider for ordinary
command profiles. closed recovery, displayed quota and footer fields are decoded
and omitted from the existing compact model results. remove model/effort fields from the closed start schema and argv.
provider options belong to the configured profile command.

this changes the worker implementation revision from v7 to v8. finalized v7
worker records become opaque archives; unfinished v7 actions block cutover and
must settle under the old release. no new decoder or replay path is introduced.

## deployment and evidence

jarvis runs as its existing service uid with `ProtectHome=true` and
`NoNewPrivileges=true`; the enrolled devbox state belongs to the development
user with private modes. no worker cli privilege boundary exists. copied state
would miss later membership updates. the owner deferred this deployment
integration; [the issue](../issues/skid-installed-state-access.md) records its
resolution and real service-uid qualification requirements. the retired client
installer refuses before remote changes. no new bridge or global user change.

focused disposable checks exercise the new closed schema, literal cli argv,
explicit installed-state directory, native-read source rejection, and no replay
after malformed entered-write output. a separate fixture runs the actual
generalized cli engine against signed temporary installed state and an ephemeral
synthetic https host. its real JSON exercises command-only/codex/claude profile
rows, recovery, displayed quota/footer and the unchanged compact list projection. these are local source/subprocess proof;
no installed service, provider or fleet acceptance is claimed. independent
source review and all six disposable groups passed on 2026-10-20; the probes
were removed before commit. the existing dependency-audit issue remains open.
