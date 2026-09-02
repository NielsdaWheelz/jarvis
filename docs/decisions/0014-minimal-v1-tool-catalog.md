# ADR 0014: Freeze the minimal v1 tool catalog

- Status: Accepted
- Date: 2026-09-01
- Supersedes: the generic local-write scope in
  [ADR 0003](0003-natural-discord-and-autonomy.md) and the claim in
  [ADR 0004](0004-python-codex-and-tool-kernel.md) that every portable
  capability is new Jarvis work
- Amends: [ADR 0005](0005-reuse-integrations.md) by admitting the existing
  `llm-tools` public-Web family

## Context

Broad categories such as local writes, mailbox organization, and reversible
housekeeping do not identify a concrete v1 burden. They enlarge policy, schemas,
tests, and prompt surface before use proves their value. Removing them later
would also be harder than adding a named tool later.

Public-Web search and page reading are immediately useful for a general personal
assistant. The pinned `llm-tools` revision already ships typed, opt-in
`web.search` and `web.read` tools: a Brave adapter and a bounded public-Web
reader. Reimplementing them in Jarvis would duplicate a portable boundary.

## Decision

The exact catalog is normative in
[SPEC section 7.3](../../SPEC.md#73-tool-contracts-and-exact-catalog):

- Main: Gmail search/thread read, draft create/update, approved draft send;
  Calendar list/get/create/update/delete; Maps place search/get/directions;
  `web.search`, `web.read`; and `schedule_wake`.
- Recaller, rememberer, and dreamer: `memory.search` and `memory.open` only.
- Discord remains transport, not a model tool.

V1 exposes no local-filesystem, Gmail organization, attachment-download,
progressive-discovery, or other unlisted tool. The main agent receives recalled
memory but no direct memory tools.

Jarvis owns application-specific declarations, credentials, authority
classification, information-flow policy, and grants. It reuses the portable Web
declarations and bindings from the pinned `llm-tools` dependency. Native Codex
network and Web access remain disabled.

Web tools are automatic reads. `web.search` discloses the model-chosen query to
Brave; `web.read` discloses the URL and host IP to the public destination. They
never receive application cookies or connector credentials. Unmistakable secret
material is rejected before dispatch, and all returned text is untrusted data.

## Consequences

Positive:

- Every v1 model capability and authority rule can be enumerated and tested.
- Prompt and policy surface correspond to demonstrated product needs.
- Public research works without native Codex network access or duplicate code.
- Later tools can be added as narrow slices from observed use.

Accepted costs:

- Jarvis cannot organize the mailbox, download attachments, or edit local files
  in v1.
- Brave receives search queries, and page destinations observe reads.
- Public page reading has no authentication, cookies, JavaScript, subresources,
  or general browser behavior; some modern sites will not be readable.
- A missing Brave credential holds Slice 0 open rather than silently selecting a
  new provider.

## Rejected alternatives

- **Keep broad automatic categories without tools:** authority with no product
  behavior and no exact acceptance boundary.
- **Add generic filesystem access:** large ambient authority before an observed
  file workflow defines the root and operations.
- **Add Gmail organization now:** speculative destructive/reversible semantics
  and provider edge cases with no demonstrated need.
- **Use native Codex Web access:** breaks the single host-owned tool and
  credential boundary.
- **Copy the Web tools into Jarvis:** duplicates already-pinned portable code.

## Migration and acceptance

There is no runtime migration because implementation has not started. The
affected criteria are A1.9, A3.9, A3.10, A4.11, A6.1, A6.17, and the Slice 0
qualification gate.
