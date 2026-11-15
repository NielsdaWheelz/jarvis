# nexus owner-librarian memory handoff

status: open. current delivery adopted 2026-11-14; source and live acceptance
remain distinct. [memory delivery](../memory-delivery.md) and
[adr 0068](../decisions/0068-nexus-capture-and-memory-delivery.md) own the target.

problem: the october handoff describes retired send/rerun/regenerate routes,
`ToolPositionRecord` identity and a no-capture boundary. current nexus instead has
one owner librarian transcript, immutable user/assistant pairs and failed/cancelled
retries that append a new pair with `retry_of_run_id`. successful turns do not
regenerate; terminal turns may be physically deleted.

current source: `python/nexus/services/tools/memory.py` uses the canonical
`call.id` as note submission identity and `call.principal` as the owner-transcript
association. its backend-only client grants five reads and optional save to the
configured owner and declared complete processor chain. no automated helper or
other viewer gains memory tools. installed private access remains unproved.

the approved extension captures only future admitted runs: durable question/answer,
saved citation/attachment excerpts and available persisted tool receipts. a durable
temporary export survives source deletion and delivery failure until central
acknowledgement, then is removed. replay preserves source identity/content.
no historical import, revision/update/remove sync, reasoning capture or second
memory store/server is added. capture grants and progress are distinct from tools.

ownership: nexus owns canonical run/export creation, retry/ack cleanup, current
chat/tool admission and private backend consumption. jarvis/library own central
source admission, idempotent archive/tree commit and retrieval. dev-server owns
the private declaration/connectivity and selected release handoff. do not fake a
native machine/account for nexus application content.

historical evidence: the 2026-10-09 client at `5b282f2ec35a7624140a5935acc7a8d9b33b8524`
qualified its then-current routes and four pins, including two contained native
turns; api responses were synthetic. that receipt does not qualify today's routes,
exports, dependency locks or installed grants. the 2026-10-13 repair record adds
controlled client/network/postgres evidence only.

resolved when: current authenticated librarian send/retry, canonical tool rows,
all five reads/save, denied principals/processors/helpers, typed outage continuation
and uncertain-save identity pass live qualification; future-only export survives
deletion/outage/restart and central lost-ack replay; current artifacts and private
installed access have separate receipts. record exact commits/locks/images and
explicit unavailable routes. see [live qualification](nexus-memory-live-qualification.md).
