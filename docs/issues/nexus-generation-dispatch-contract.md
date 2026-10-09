# nexus generation dispatch contract

status: shared native repair implemented, qualified and merged; historical job disposition remains with nexus
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

the later pre-cutover nexus snapshot a494f743 pinned provider 6a7093f and kernel 937434b and used
the approved remote-shell route. `codex_generation_contract.py:471–477` still
throws for `invalid_request`/`runtime_defect`; `llm_execution.py:564–579` retains
uncertainty after an armed exception. current host diagnostics are improved;
diagnostic retention and terminal settlement are distinct requirements.

## shared repair

provider/runtime now prepares exact attempts before arm, exposes authoritative
non-submission separately from unresolved sends, and preserves native seals before
product validation. nexus and jarvis use the shared native callback supervisor;
the replaced shell dispatch path and jarvis main capacity/six-hour policy are cut.

qualified personal luna/xhigh strict-json research returns useful results from
all four actual nexus tools. real-store sealed recovery and lost-response barriers
pass. final immutable artifacts and current acceptance are recorded in the kernel
`llm-agent-kernel/docs/integrations/nexus-metadata.md` handoff.

## remaining operational disposition

old uncertain admissions remain fenced until the nexus owner completes their
existing audited recovery/disposition. new evidence cannot retroactively prove
that an old request was never submitted. close this historical record when the
owning nexus ticket accounts for every original job; deploying new pins alone
does not establish that. deployment is outside this implementation task.
