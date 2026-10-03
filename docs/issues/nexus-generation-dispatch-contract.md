# nexus generation dispatch contract

status: open; requirement for planned provider/kernel o3–o4 (formerly prs 3–4)
origin: 2026-10-01 owner-requested nexus integration review
area: provider submission evidence and kernel settlement

## evidence and impact

nexus production 7dc68929b at database 0241 has a deterministic request mismatch:
its tool-bearing codex path requests workspace writes, network and mcp while
disabling built-ins; provider-runtime pin 97fbac7 rejects that combination.
the host maps it to `invalid_request`, and the consumer throws before accepting
a terminal. five lewis metadata jobs admitted on 2026-10-01 at 15:12 utc retain
dispatched children without terminals; three other retries failed catalog refresh.
none published metadata. exact identities are in nexus-web's
`docs/tickets/model-cutover-dead-media-generations.md`. the original exception
subtype was not retained, so the source mismatch is not a per-job exception proof.

current nexus a494f743 instead pins provider 6a7093f and kernel 937434b and uses
the approved remote-shell route. `codex_generation_contract.py:471–477` still
throws for `invalid_request`/`runtime_defect`; `llm_execution.py:564–579` retains
uncertainty after an armed exception. current host diagnostics are improved;
diagnostic retention and terminal settlement are distinct requirements.

## required shared contract

- provider-runtime validates the exact model/effort, execution lane, tool
  exposure, output schema and native capability combination before native
  submission. expose pure incompatibilities before the dispatch fence; catalog
  unavailability is an admission failure, never silent substitution.
- distinguish proven non-submission, an accepted native terminal, and unresolved
  submission. host admission/session creation is not native model acceptance.
  absence of an acceptance event proves nothing. a proven non-submission result
  must also guarantee no delayed native submission from that attempt.
- preserve bounded original failure type/code, stage and generation/child
  identity before normalization. a malformed protocol result remains a defect;
  do not fabricate terminal evidence from an exception name or missing usage.
- preserve valid native terminal evidence independently of application success.
  final json acceptance and useful metadata publication belong to nexus. callback
  invocation identity precedes effects; recorded results precede native replies.
- keep application jobs, transactions, schemas, recovery decisions and deadlines
  outside the kernel. support jarvis's planned contained callbacks and nexus's
  approved remote-shell lane through their explicit contracts. six hours is
  jarvis main policy, not a library or metadata default.

kernel spec section 17.2 and adr 0009 currently classify every exception after
provider entry as uncertain, including `TurnNotStarted`. a new proven
non-submission outcome requires a coordinated provider/kernel adr and spec
change; do not reinterpret the existing exceptions. kernel section 16 and
adr 0008 already preserve the distinct consumer protocols.

## acceptance and disposition

o3–o4 prove rejection before submission, accepted failed terminal, successful
strict-json output with actual tools, and lost response after possible submission.
only the last remains uncertain. preserve a valid terminal if later product
validation fails. include finite nexus luna/xhigh metadata research as the second
consumer case; observe actual search/read and strict final output together.
callback interruption/reply ordering and jarvis containment still need their
own proof; a passing nexus shell run cannot qualify callbacks.

old uncertain admissions remain fenced until the application owner completes
their existing audited recovery/disposition. adopting the new library cannot
retroactively establish that an old native request was never submitted.
close when the shared contracts, owning specs and consumer adapters implement
these distinctions and the exact installed routes have recorded acceptance.
