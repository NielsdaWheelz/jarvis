# memory

[universal memory](universal-memory.md) is the accepted contract and the source
implementation in this branch. production activation and external client
qualification are separate. the [delivery plan](implementation-plan.md#memory-delivery)
owns remaining repository handoffs; [operations](operations.md#memory-operations)
owns inspection and stopped repair.

memory has three representations with different responsibilities:

- the append-only archive retains originals, source identity and source dates;
- the derived binary tree compresses contiguous positions in central arrival order;
- a persisted bounded view selects nodes covering an admitted prefix exactly once.

the standalone `universal-memory` package owns these mechanisms, source paging,
navigation and rank-fused retrieval. its write operations use the caller's sql
transaction. jarvis hosts one package instance and supplies admission, inference,
embeddings, scheduling and the private mcp/http endpoint. provider-runtime owns
native archive decoding; dev-server owns collectors and profile configuration.
nexus's [chats-only consumer handoff](issues/nexus-memory-client.md) remains
incomplete until its accepted client is implemented, verified and provisioned.

each new top-level jarvis turn receives a fixed-cutoff historical view plus exact
operative requests and receipts. compatible steering stays in its active native
loop. main can search, view, zoom, date and open memory, and optionally save an
authored note. memory remains evidence rather than authority or current external
truth. there is no recaller or rememberer.

one serial tool-free compactor builds missing nodes. nightly idle dreaming uses
new eligible material since `dream_through`, with optional older originals as
context. it quietly appends attributed synthesis notes and supporting references
in the same transaction as consumed-seed progress. synthesis notes create no new
seeds. interrupted inference may repeat; completed nodes and original receipts
persist. legacy notes and flat summaries remain searchable without invented
provenance or historical backfill.

capture/retry and memory completion are the two retained regression categories.
the [focused acceptance](universal-memory.md#11-acceptance-and-verification)
defines their boundaries; wider temporary integration/live checks are removed
after qualification. this does not restore the retired test suite.
