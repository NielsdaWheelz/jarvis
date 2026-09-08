# 0038: Truthful terminals and bounded Calendar completeness

Status: **Accepted, 2026-09-08**

Supersedes ADR 0037 only where it fixes Calendar event-result size and
pagination. Amends SPEC sections 4.2, 7.3, 7.4, 11, and 12.

## Problem and target

Production returned:

> I checked every readable calendar. The combined result is truncated at 50
> events (with no calendar failures), so I’m narrowing the time windows to give
> you a complete two-week view.

The first sentence was true. The second was not: the kernel settled a terminal
`say`; no continuation existed. The connector also made a normal 35-calendar,
two-week request partial solely because the model-selectable global cap was 50.

Target behavior:

- An ordinary bounded two-week read across the current 35 calendars returns one
  complete, chronologically merged observation when it fits the new host bound.
- Jarvis emits one final natural response only after the evidence it describes
  exists.
- An incomplete read is visibly partial or asks one concrete question. It never
  implies that unscheduled work is continuing.
- Only a committed `action`/kernel suspension may support a promise of later
  work. Discord typing is the only synchronous progress indication.

## Goals

1. Make response completion an explicit Jarvis product contract.
2. Make collection completeness a typed connector fact, not model inference.
3. Complete the observed normal Calendar workload without a second model-planned
   subdivision.
4. Preserve finite calls, bytes, elapsed time, provider usage, and one-user
   operability.
5. Reuse the kernel, action, dispatcher, canonical JSON, typing, settlement, and
   context primitives already present.

## Non-goals

- Background jobs, workflows, cursors exposed to the model, or automatic run
  rearming.
- A Calendar mirror, sync tokens, new table/column, cache, or periodic polling.
- Unlimited calendars, events, pages, context, latency, or Google quota.
- Retrofitting every Gmail/Web collection in this change.
- A semantic regex, second-model prose critic, automatic provider retry, or a
  claim that arbitrary natural language can be mechanically proven truthful.
- A new kernel protocol or compatibility path for old Jarvis response/tool
  schemas.

## Required invariants

1. Main has no model-visible `say` terminal. It uses the kernel's existing
   `StructuredOutput` and terminates with one validated `finish.result`.
2. No terminal variant means `working`, `continuing`, or `will finish later`.
3. A terminal creates no successor run. Later work requires an already committed
   action and ordinary kernel suspension.
4. Incomplete Calendar coverage can never be rendered as `answered` or `silent`;
   host policy conservatively promotes either to a visible `partial` result.
5. The host, not model prose, renders disposition labels and coverage notices.
6. Calendar completeness is true only when Calendar discovery is untruncated,
   every selected Calendar page is exhausted, every selected Calendar succeeded,
   and no event/count/byte/deadline bound clipped the result.
7. Returned provider identities and event fields remain exact. The host omits a
   whole event at a result bound; it never shortens a stable field.
8. All progress visible during a live synchronous turn is host-owned Discord
   typing. Model commentary remains non-executable and invisible.

## Product response contract

Main changes from `ConversationalOutput()` to
`StructuredOutput("jarvis_terminal", JarvisTerminal)` using this closed direct
result object and closed direct union:

```text
JarvisTerminal
  response: Answered | Partial | NeedsInput | Failed | Silent

Answered
  type = answered
  text: UTF-8 string[1..2000]

Partial
  type = partial
  text: UTF-8 string[1..2000]
  limitation: UTF-8 string[1..500]
  question: null | UTF-8 string[1..500]

NeedsInput
  type = needs_input
  context: UTF-8 string[0..1000]
  question: UTF-8 string[1..500]

Failed
  type = failed
  explanation: UTF-8 string[1..2000]

Silent
  type = silent
  reason: owner_needs_no_response
```

All objects are closed. `response` is discriminated by `type`; the required
object root is compatible with the pinned structured-output compiler. The
deterministic host renderer enforces the final Discord character bound after
adding fixed labels:

- `answered`: render `text` unchanged.
- `partial`: render `Partial result — {limitation}`, then `text`, then the
  optional question.
- `needs_input`: render `context`, then `I need one detail: {question}`.
- `failed`: render `I couldn’t complete this: {explanation}`.
- `silent`: persist a silent conclusion and deliver nothing.

The existing host fallback remains authoritative for action-resolution and
scheduled-wake inputs: those inputs may not settle silently.

Settlement maps `answered`, `partial`, `needs_input`, and `failed` to
`conclusion_kind = conversation` with the terminal type as `outcome`; `silent`
maps to `conclusion_kind = silent`, `outcome = silent`. Every settled owner turn
remains eligible for the existing rememberer transaction. No trace field or
database column is added.

### Content definition of good

The response-content designer owns the role instruction, branch descriptions,
fixed renderer text, examples, and evaluation fixtures.

Good content is direct, answers with observed facts, names material limits once,
and asks at most one actionable question. It uses present/past tense for
completed work. It may say later work is scheduled only when supplied a durable
action reference by the host.

Forbidden terminal content includes “I’m checking,” “I’m narrowing,” “I’ll get
back to you,” “working on it,” or any equivalent unsupported continuation. The
rule is enforced structurally by the absent in-progress branch, conservatively
by host coverage promotion, and semantically by focused model evaluation—not by
fragile phrase matching.

## Calendar API hard cut

Delete `CalendarListEventsInput.max_results`. The model supplies only:

```text
CalendarListEventsInput
  time_min: aware datetime
  time_max: aware datetime
  time_zone: installed IANA name
```

Delete `CalendarListEventsSuccess.truncated`. Add:

```text
CalendarCoverageReason =
  calendar_limit | calendar_failure | event_page_limit |
  event_limit | output_byte_limit | deadline

CalendarCoverage
  complete: boolean
  reasons: sorted unique tuple[CalendarCoverageReason, max 6]
  calendars_discovered: integer[0..50]
  calendars_completed: integer[0..50]
  matched_events: null | non-negative integer

CalendarListEventsSuccess
  calendars: existing bounded CalendarReference tuple
  events: existing exact CalendarEventSnapshot tuple[max 200]
  failures: existing bounded CalendarEventReadFailure tuple
  coverage: CalendarCoverage
  observed_at: aware UTC datetime
```

`matched_events` is non-null only when every in-scope event page was exhausted;
it may exceed `len(events)` when only the response count/byte bound clipped a
fully observed set. `complete` is equivalent to empty `reasons`; the model
cannot choose it. Cross-field invariants validate counts and failure reasons.

### Connector algorithm and bounds

The Calendar connector owns the complete operation:

1. Discover up to 50 reader-or-better calendars exactly as today.
2. Read the first event page for every discovered calendar.
3. Follow `nextPageToken` in deterministic calendar-ID rounds until exhausted or
   the shared page/deadline bound is reached.
4. Use at most ten concurrent Google requests.
5. Merge all observed normal events chronologically; sparse cancellations remain
   last. Preserve existing exact normalization and per-calendar failures.
6. Return the largest chronological whole-event prefix fitting both 200 events
   and the existing 262,144-byte canonical success envelope. Use the existing
   `llm_tools.canonical_json_bytes`; do not invent a second serializer.
7. Derive coverage after all observations and clipping. Never infer completeness
   from a count smaller than a requested page.

Fixed v1 bounds:

- 50 calendars; 10 concurrent requests.
- Google event page size 250.
- 100 total event-page requests, including each calendar's first page.
- 200 returned events.
- 262,144 encoded success bytes.
- 55-second connector-owned deadline inside the 60-second executor fence;
  caller cancellation still propagates unchanged.
- 202 maximum external attempts: one discovery plus 100 event-page requests,
  each retaining the existing two-attempt refresh bound.

Google documents that `maxResults` is only a page size and that a non-empty
`nextPageToken` proves incompleteness; the connector must follow that contract:
<https://developers.google.com/workspace/calendar/api/guides/pagination>.

The Calendar event-list contract and binding advance to v5. The new fields,
limits, page size, ordering, canonical-byte clipping, and coverage derivation
participate in contract/policy/implementation identity.

The model tool catalog and authority do not change. Main maximum/selected and
scheduled-read profiles keep the same tool IDs and call counts; only their
external-attempt ceilings increase by 100 (243, 242, and 222 respectively).
All affected profiles, plans, HostTables, role/output contracts, and Main
definition fingerprints are regenerated. Main cold-bootstraps once. Memory
roles and AutomaticWriteGate do not rotate. Provider-turn admission and the
rolling journal do not change because provider-turn/call/write-gate ceilings do
not change; there is no admission migration.

### Calendar content definition of good

The Calendar-content designer owns tool summary/documentation, coverage reason
descriptions, and response fixtures. Good complete answers do not mention
internal pagination. Good partial answers state what scope was checked, the
material reason it is incomplete, what can safely be concluded, and—only when
useful—one narrowing question. Provider IDs, page tokens, quotas, and retry
mechanics are never user-facing.

## Intra-system composition

```text
owner input
  -> Main StructuredOutput session
  -> calendar.list_events v5
  -> Google connector discovery + bounded paginator
  -> typed Calendar coverage observation
  -> Main finish.result
  -> Jarvis terminal-policy promotion
  -> deterministic content renderer
  -> canonical message settlement
  -> existing Discord outbox
```

A run-local `TurnEvidence` value records only typed incompleteness reason codes
and counts from completed collection observations. It contains no event text,
provider ID, prompt, or model prose; it is discarded on settlement/release. The
read dispatcher updates it and the checkpoint settlement adapter consumes it.
No persistent state or generic workflow abstraction is introduced.

If Main proposes `answered` after any incomplete Calendar observation, the host
keeps its text but renders and records `partial` with a deterministic coverage
limitation. If Main proposes `silent`, the host instead supplies the fixed body
“I couldn’t produce a complete calendar answer.” and renders `partial`. Other
validated dispositions remain model-selected. No result is reparsed from prose.

## Ownership and implementation boundaries

Work is sequential and file ownership does not overlap:

1. **Contract/content boundary** — owns a new `src/jarvis/terminal.py` and
   `tests/test_terminal.py`. Define the closed terminal union, exact renderer,
   content fixtures, and `TurnEvidence`; no connector or definition edits.
2. **Calendar boundary** — owns `read_tools.py`, `connectors.py`,
   `tests/test_read_tools.py`, and `tests/test_connectors.py`. Hard-cut the old
   fields, implement bounded paging/coverage/byte clipping, and expose no host
   policy.
3. **Composition boundary** — owns `definitions.py`, `service.py`,
   `checkpoints.py`, `cli.py`, the compatibility manifest, and their focused
   tests. Wire existing structured conclusions, evidence, new limits, plans,
   fingerprints, settlement, and cold bootstrap. Reuse the existing
   `CapturingReadDispatcher` observation point rather than adding another
   dispatch wrapper.
4. **Release boundary** — owns normative docs, qualification scripts/report,
   deployment activation, and no runtime modules. Prove the exact production
   composition and preserve prior reports byte-for-byte.

During refactor, centralize the duplicated active Main role text and terminal
renderer. Remove old `max_results`, `truncated`, conversational-Main/say, v4
binding, old fingerprints, aliases, adapters, tests, and fixtures, including the
`Slice1ThreadRunner` compatibility alias after migrating its tests to
`JarvisThreadRunner`. Do not retain dual schemas or compatibility branches.
Slice-specific builders are outside this change unless an `rg` call graph proves
one is unreachable from production and all retained qualification callers are
migrated in the same refactor.

## Red / green / refactor plan

### Red

Write failing tests before production edits:

- Old input/result fields are rejected; the new closed schemas and cross-field
  invariants hold.
- Thirty-five calendars and more than 50 total events yield complete coverage.
- Multi-page reads exhaust tokens; page, event, byte, failure, and deadline
  bounds yield exact partial reasons.
- Paging is fair, deterministic, at most ten-wide, and settles exact attempts.
- Every terminal branch renders exactly; no in-progress branch exists.
- An `answered` or `silent` result after incomplete evidence is promoted to a
  visible `partial` result.
- Structured Main supports tool loops, action suspension, host inputs, silent
  owner turns, settlement, restart, and session cold bootstrap.

### Green

Implement only enough to pass each owning boundary's red tests. Do not change
dependencies, persistence, other tool schemas, or action semantics.

### Refactor

Remove legacy paths, consolidate current Main content, regenerate exact frozen
identities, and rerun focused tests after every deletion. A compatibility alias
or dormant v4 branch is a failure, not migration help.

## Acceptance and 80/20 proof shape

One proof per ownership boundary; no exhaustive combinatorial matrix:

1. **Schema:** deterministic compile/decode/encode rejection and cross-field
   tests for every branch and removed legacy field.
2. **Google connector:** one `httpx.MockTransport` happy path covers 35
   calendars, multiple pages, >50 events, ordering, attempts, and complete
   coverage; one table-driven bounded set covers a calendar failure and each
   clipping/deadline stop.
3. **Kernel/composition:** one fake-provider threaded tool-loop proves
   `StructuredOutput -> StructuredConclusion -> persisted rendered message`; one
   incomplete-evidence case proves host promotion; one suspension case proves
   actions remain unchanged.
4. **Discord:** one deterministic outbox test proves exactly one final message
   and typing-only progress.
5. **Live consumer:** one production-credential Calendar probe covers all 35
   calendars and a two-week range with >50 events; it must be complete or expose
   the exact legitimate bound that prevents acceptance.
6. **Paid end to end:** one exact production Codex/Discord prompt proves useful
   final content, correct disposition, no unsupported continuation, no action,
   and no later phantom message.

Final gate: targeted red tests, full Jarvis suite, Ruff, Pyright, fresh migration
plus zero drift, build/clean-wheel smoke, docs/link checks, and existing pinned
dependency canaries. Carry forward unchanged upstream paid qualification; do
not rerun unrelated Gmail/Maps/Web/memory/write/approval matrices.

## Final state

- Exactly four application tables and the existing action/suspension model.
- Main uses a typed structured terminal and host renderer; internal roles are
  unchanged.
- Calendar v5 normally completes the owner's observed two-week workload in one
  tool call and always proves whether it did.
- Discord shows typing during work and exactly one settled final message after
  work.
- No model-authored progress promise, automatic continuation, cache, workflow,
  fallback schema, or legacy Calendar v4 path remains.

## Trade-offs requiring owner acceptance

- Main's structured terminal adds schema/output tokens and rotates its definition
  fingerprint, causing one cold bootstrap.
- Calendar may use more Google requests, latency, transient memory, and quota;
  finite paging and concurrency contain this cost.
- A 200-event/256-KiB ceiling can still make unusually dense requests partial.
- Host promotion is deliberately conservative: any incomplete Calendar read
  makes the whole response visibly partial even if the model used only a subset.
- Semantic prose quality remains model-evaluated. The system proves lifecycle and
  evidence state, not the truth of every sentence, without adding a second model
  or brittle language filter.
- The missing repository `docs/rules/` and `testing-standards.md` cannot govern
  implementation until supplied. This plan defines the minimum test contract;
  if those files appear before implementation, their stricter requirements win.
