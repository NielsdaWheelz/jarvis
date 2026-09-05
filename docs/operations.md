# Slice 2 operations

Jarvis Slice 2 is one Python 3.12 process, one PostgreSQL database, and one
configured Discord guild channel. It has no HTTP listener. Its model-callable
catalog is exactly the nine automatic reads in SPEC 7.3. Run it as a dedicated
unprivileged OS user in UTC.

## Install and configure

Install the locked environment from a clean checkout:

```sh
uv sync --frozen --no-dev
```

Copy `.env.example` to a service-manager credential file outside the checkout,
replace every placeholder, and make the file readable only by the service user.
For database access, it contains only the least-privilege `jarvis_runtime`
login. Keep the
separate migrator login represented by `.env.migration.example` in an
operator-only credential file; never load it into the Jarvis service.
The Codex state-root base must be an absolute, existing mode-0700 directory.
The profile named by `JARVIS_CODEX_PROFILE_KEY` must already contain the
owner's local-account authentication at the provider-runtime layout
`<state-root-base>/codex/<profile>/auth.json`. The Jarvis runtime directory may
be absent or an existing mode-0700 directory when it is initialized. Supply the
qualified mode-0600 Google OAuth state plus the exact Google client,
connector-encryption, Maps, and Brave settings shown in `.env.example`. They
remain host-owned and never enter Codex context or child-process environment.
An optional embedding key is only added to the host-side Web secret-rejection
set; Slice 2 does not implement embeddings.

Apply the schema and initialize the private state once:

```sh
JARVIS_MIGRATION_DATABASE_URL=postgresql://... uv run alembic upgrade head
set -a
. /path/to/private/jarvis.env
set +a
uv run jarvis initialize-state
```

Load secrets with the service manager in production; the `env` example is only
for an operator-controlled shell and must never be logged or pasted into model
context. Install `deploy/jarvis.service` after adjusting its paths, then start
the service. A deployment-wide PostgreSQL advisory lock makes a second process
fail rather than overlap.

## Verification

Point the verifier only at a disposable database. Migration tests downgrade it
to an empty schema.

```sh
docker compose up -d --wait
docker compose exec -T postgres createdb -U jarvis_migrator jarvis_test
docker compose exec -T postgres psql -U jarvis_migrator -d postgres \
  -c 'GRANT CONNECT ON DATABASE jarvis_test TO jarvis_runtime'
JARVIS_TEST_MIGRATION_DATABASE_URL=postgresql://jarvis_migrator:jarvis-migrator-dev@127.0.0.1:54328/jarvis_test \
JARVIS_TEST_DATABASE_URL=postgresql://jarvis_runtime:jarvis-runtime-dev@127.0.0.1:54328/jarvis_test \
  scripts/verify
```

The command checks the frozen environment, formatting, linting, typing, tests,
migrations and schema drift, package artifacts, and installed dependency
vulnerabilities.

## Paid Slice 2 qualifications

Run every live qualification from the exact revision being recorded and against
an empty, freshly migrated disposable database. Each runtime-state path must be
unused and its existing parent must be mode 0700. The Codex state-root base is
the private existing directory above the `codex/<profile>` provider scope; do
not copy its authentication into the checkout or process environment. The Codex
child receives an empty environment from the production adapter.

First run all nine live read operations through the production catalog,
dispatcher, frozen Main plan, and exact budget. The configured Gmail query must
match a thread. The Calendar probe requests 50 events and must contain at least
three normal events with `end.type=unspecified`; its sanitized output
reports only event totals and that count. The Maps query
must match a destination reachable from the origin, and the Web query's first
result must be a public readable page. The output contains counts and contract
identities only, never retrieved content or stable provider IDs.

```sh
JARVIS_LIVE_READS=1 \
JARVIS_LIVE_GMAIL_QUERY='newer_than:365d' \
JARVIS_LIVE_CALENDAR_ID=primary \
JARVIS_LIVE_MAPS_QUERY='configured synthetic destination' \
JARVIS_LIVE_MAPS_ORIGIN='configured synthetic origin' \
JARVIS_LIVE_WEB_QUERY='IANA reserved domains' \
  uv run python scripts/qualify_reads.py
```

`qualify_codex.py` performs the three required paid consumer probes in one run:
main-session continuation/rotation/reconstruction, an isolated closed
structured result, and a logical tool call whose provider wire carries JSON
string arguments. Run it once for every exact model recorded in the
compatibility manifest; the current set contains only `gpt-5.6-terra`:

```sh
JARVIS_CODEX_LIVE=1 \
JARVIS_CODEX_MODEL=gpt-5.6-terra \
JARVIS_CODEX_PROFILE_KEY=jarvis-runtime \
JARVIS_CODEX_STATE_ROOT=/private/existing/agent-state \
JARVIS_LIVE_RUNTIME_STATE_DIRECTORY=/private/unused/terra-runtime \
JARVIS_LIVE_DATABASE_URL=postgresql://jarvis_runtime:...@host/jarvis_terra_probe \
JARVIS_OWNER_TIMEZONE=America/Los_Angeles \
JARVIS_CODEX_REASONING_EFFORT=high \
  uv run python scripts/qualify_codex.py
```

`gpt-5.4` is deliberately rejected during configuration because OpenAI retired
it from ChatGPT-authenticated Codex on 2026-08-31. The negative final-code probe
that exposed that retirement is preserved in ADR 0028; do not retry it as a
supported route or switch Jarvis to API-key authentication.

Run the live Discord transport qualification with only the bot token and the
three configured IDs injected by the secret manager. It checks Gateway scope,
effective permissions, exact intents, mention/embed controls, and an accepted
response lost across a reconstructed client using one enforced nonce. Its
synthetic bot message is removed in `finally`.

```sh
JARVIS_DISCORD_LIVE=1 \
JARVIS_DISCORD_BOT_TOKEN=... \
JARVIS_DISCORD_OWNER_USER_ID=... \
JARVIS_DISCORD_GUILD_ID=... \
JARVIS_DISCORD_CHANNEL_ID=... \
  uv run python scripts/qualify_discord.py
```

The final end-to-end probe is deliberately incapable of consuming arbitrary
channel history. On an empty migrated database, the owner must post one natural
compound question that asks Jarvis to search and read a matching Gmail thread,
list Calendar events and read one returned event, search places and fetch one
returned place's details before routing to a returned place, search the public
Web and read a returned page, and include a unique non-secret marker. Then supply
both its Discord message ID and the marker. Inject the ordinary production
settings, plus the following guards, from operator-controlled credential files.
Keep the catch-up limit at most 100. The probe requires exactly one selected
owner input, one durable response, and one visible delivery, and removes only
that bot response.

```sh
JARVIS_LIVE_E2E=1 \
JARVIS_MAXIMUM_BATCH_SIZE=1 \
JARVIS_DELIVERY_BATCH_SIZE=1 \
JARVIS_DISCORD_CATCH_UP_LIMIT=100 \
JARVIS_LIVE_OWNER_MESSAGE_ID=... \
JARVIS_LIVE_EXPECTED_REPLY_MARKER=... \
  uv run python scripts/qualify_e2e.py
```

All four scripts emit bounded JSON containing statuses, counts, revisions,
timings, and token usage only. They never emit prompts, replies, Discord IDs,
session IDs, credentials, or provider event payloads.

Migrations own application objects and grant only the required DML to
`jarvis_runtime`. That role cannot delete or truncate `memory_log`, cannot
update its canonical columns, and can update only the derived `embedding`.
The append-only trigger remains enabled as defense in depth against accidental
owner-side mutation.

## Restart and recovery

Startup performs bounded Discord catch-up, retries persisted assistant rows
whose `source_message_id` is null, releases orphaned admission concurrency
without refunding its rolling charge, and scans unprocessed, unparked waking
rows. A compatible main-session reference is resumed. A missing, incompatible,
or invalid provider session cold-bootstraps from canonical message history.
Successful outbox delivery drains every current batch. A row that exhausts its
finite delivery retry schedule remains pending and stops that drain; the next
startup or ingress signal retries it with the same persisted UUID and nonce.
Catch-up selects Discord's newest bounded page after the canonical owner cursor,
then persists eligible owner messages in chronological order. If downtime
traffic exceeds that bound, the oldest overflow is intentionally skipped; this
prevents a full page of bot or non-owner traffic from permanently hiding a later
owner message without adding non-canonical cursor state.

`stop` and `pause` are exact, case-insensitive owner messages handled by the
host. `resume` clears the durable pause. Ordinary process termination cannot
undo an external effect; later slices reconcile effectful action rows before
any repeat.

If a configuration defect parks input, first stop the service and correct the
defect. Then clear only the reviewed UUIDs while the command owns the deployment
lock:

```sh
jarvis release-parked MESSAGE_ID [MESSAGE_ID ...]
```

This does not reset `processing_attempts` and does not arm hidden successor
work. Never edit `trace` to control scheduling.

If the admission journal is missing, corrupt, or has a changed configuration,
Jarvis fails closed. With the service stopped, preserve the bad journal for
diagnosis, verify that no cognitive process owns the deployment, and explicitly
replace only `admission.json` with a freshly initialized journal using the same
checked-in limits. Do not delete the session reference, pause state, or database
rows as part of that repair.

## Backup and logs

Back up all four application tables daily and retain an encrypted off-host copy.
Credentials and disposable provider session state are supplied separately and
must not be placed in the database backup. Ordinary logs contain event types,
bounded IDs, counts, and reason codes only—not messages, prompts, memory text,
tool payloads, tokens, or credentials.
