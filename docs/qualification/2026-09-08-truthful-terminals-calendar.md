# Truthful terminals and Calendar completeness qualification — 2026-09-08

Status: **qualified**

This report qualifies ADR 0038 only. Evidence is sanitized: it contains no
message text, event text, provider identity, credential, token, native session
reference, or private Calendar identifier.

## Candidate

The immutable runtime candidate is:

| Identity | Exact value |
| --- | --- |
| Jarvis commit | `bacb52ee33f30d1bdc7a24fd703e0358c3662141` |
| Jarvis tree | `402f800cff0ef83e8f4371f9c23f842189577ca1` |
| `uv.lock` SHA-256 | `a20bc529aece840d145a40ff8362f23ac21c98f087b948a26272b52d106d2230` |
| Session manifest SHA-256 | `92d6c926365611bdc4de193b6b771f722787de036a93337d4261787ca807e168` |
| Terminal source SHA-256 | `626cc0d207cfd130bdfd31755e71485c2896f6ca06d1f491c2969d1aaa07409c` |
| Terminal test SHA-256 | `ee1d4ded7b0810654591934b33e61eb8a827368e298eaac97b7349c33d707c04` |

Exact dependencies remain:

- `llm-agent-kernel` `21084bec674023ea572950a18dde464506ea37ad`
- `provider-runtime` `4ddced3bb5487ce988858c4c6d45d2e5ee0acad9`
- `llm-tools` `9e6d155f3b64f03495911435b7cae8b8d131f9a2`
- `openai-codex` and bundled CLI `0.144.4`
- `local_account / gpt-5.6-terra`

The production Calendar probe observed Main definition
`d8ea532c3de23b7d9ab1dc00f2522e3ccc4e217fb402f183287724d7d309f774`,
session compatibility
`5eda5006f960249bc35d7161b98cb58c0871798adea52b017a7ac04b12930eb3`,
and selected plan
`5f214d9da5aaa4271e7b7827fef70cd3f26cc8955291ca4464e3eaa1d35ccdb0`.
The definition and plan changed; the application session revision did not.
The fingerprint change forces the intended cold bootstrap.

## Delivered boundary

Main now has one closed structured result with exactly five terminal
dispositions: `answered`, `partial`, `needs_input`, `failed`, and `silent`.
There is no selectable model-visible `say` branch and no continuing terminal.
Jarvis renders the disposition deterministically. Typed incomplete
Calendar evidence promotes `answered` or `silent` to a visible `partial`
settlement. Action suspension and host action-resolution remain separate and
unchanged.

`calendar.list_events` v6 owns discovery and fair bounded pagination across all
readable calendars. It returns at most 1,500 chronological compact items in a
524,288-byte canonical envelope. Normal items contain exact calendar/event IDs,
status, summary, start, observed end, and location. Cancelled items contain only
their exact IDs. `calendar.get_event` remains the full-detail boundary.

Calendar list identity is:

| Identity | Exact value |
| --- | --- |
| Contract | `908bb99fd8da9ea022051eddf48fb0e061712738620e6ef8842bc015dd7b7086` |
| Documentation | `3c53a920de00562eba17c55fbc872f4af3ce1ad852e5bb804d065f2f7976f06f` |
| Implementation | `jarvis-calendar-list_events-v6` |
| Policy | `b0b072d7b5abc2bde5ae6f3be6a2be9ccb3546d9432a755c9b282e9b16edebf2` |

No dependency, database table, column, migration, action semantic, workflow,
cache, cursor, or compatibility path was added.

## Deterministic gates

The exact candidate passed:

| Gate | Result |
| --- | --- |
| Jarvis | 765 passed |
| `llm-agent-kernel` | 211 passed; 8 paid tests deselected |
| `provider-runtime`, Linux all-extras | 1,016 passed; 2 skipped; 60 paid tests deselected |
| `llm-tools` | 203 passed; 2 paid tests deselected |
| Ruff / Pyright | clean / zero errors and warnings |
| Alembic | upgrade through `0003`; zero drift; no new migration |
| Package | wheel and sdist; clean Python 3.12 wheel/import/CLI smoke |
| Documentation | 54 files and every local link passed |
| Dependency audit | no known PyPI vulnerability; three exact Git packages outside the PyPI advisory index |

The ownership-boundary tests prove the closed terminal schema, exact rendering,
incomplete-coverage promotion, structured checkpoint settlement, typing-only
progress, hard rejection of removed fields, and one connector path spanning 35
calendars, two fair page rounds, 1,170 events, exact chronology, concurrency ten,
71 attempts, 35/35 completion, and the canonical byte bound. Table-driven tests
cover failures, count/byte/page/deadline limits, cancellation, exact clipping,
and full-detail isolation.

## Live Calendar evidence

The first v5 production probe was valid negative evidence: all 35 calendar scans
completed and found 1,170 events, but the full-detail 200-item result reported
`event_limit`. That proved the v5 payload shape, not pagination, owned the normal
incompleteness.

The exact v6 deployment probe passed:

- 35 calendars discovered and completed
- 1,169 events matched and returned
- 25 calendars contributed an event in the window
- empty coverage reasons and `complete = true`
- two terminal Read records, zero uncertain records, and zero actions created
- no event text or identifier emitted as evidence

The one-event difference from the earlier probe is expected live-state drift;
both observations exhaust the current provider range truthfully.

The candidate is active as
`/opt/jarvis/releases/bacb52ee33f30d1bdc7a24fd703e0358c3662141` on the
existing devbox. Migration, activation, health, zero automatic restarts, and
the connector-secret/process-inspection boundary passed. No host reboot
occurred.

## Discord boundary

One exact owner-authored production request asked Jarvis to check all calendars
for the next two weeks and return the next three events. The result passed:

- canonical owner input: 118 UTF-8 bytes; processed and remembered
- settlement: `conversation / answered`
- provider work: two turns, 141,306 input tokens, 369 output tokens, 24.747
  seconds
- visible result: one direct three-event answer that states all 35 readable
  calendars were checked
- no unsupported continuation, internal pagination claim, question, failure,
  or partial disposition
- zero actions created
- one 268-byte assistant row persisted before delivery
- exactly one matching Discord bot message after the owner input
- 109-second delayed check: still one database row and one Discord message; no
  phantom follow-up

The persisted assistant content SHA-256 is
`d0bd7285d363fb652a0d46794cc772a006a69d03e4b6ad042e7377d51c34577b`.
The report intentionally omits its text and both Discord message IDs.

## Accepted trade-offs

- Compact listing omits description, people, recurrence, reminders, organizer,
  etag, and update time. A detail-dependent answer costs an explicit
  `calendar.get_event` call.
- A range beyond 1,500 items or 512 KiB remains visibly partial.
- The complete 1,169-event owner turn consumed 141,306 provider input tokens.
  Returning one truthful all-calendar observation avoids brittle model-planned
  subdivision, but dense calendars consume material subscription capacity and
  latency.
- Maximum and selected tool-output authority grows by exactly 262,144 bytes;
  provider turns, calls, external attempts, deadlines, active Main's 600,000-byte
  context ceiling, admission, and persistence do not grow.
- More Calendar pages consume more Google quota, latency, and bounded transient
  memory; ten-way concurrency, 100 pages, and 55 seconds remain hard limits.
- Incomplete Calendar evidence conservatively makes the whole response partial,
  even when the model relied on only a complete subset.
- Lifecycle and evidence truth are structural. Arbitrary prose truthfulness
  remains model-evaluated; no brittle phrase blacklist or second prose model was
  added.
- The three immutable Git dependencies cannot be correlated automatically with
  PyPI advisories; exact pins and their complete upstream suites are the
  compensating proof.

All earlier qualification reports remain byte-identical. The missing repository
`docs/rules/` and `testing-standards.md` were not available to add requirements;
ADR 0038's explicit 80/20 proof contract governed this release.
