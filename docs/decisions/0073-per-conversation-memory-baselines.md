# adr 0073: per-conversation memory baselines

status: accepted, 2026-11-15; source implementation qualified; installed proof pending.

the owner approved capture for healthy and new conversations while unreadable
existing conversations remain explicitly blocked. this supersedes the
all-or-nothing head requirement in adr 0063 and the earlier rollout deferrals.
the complete inventory of existing conversation identities remains mandatory.

## decision

activate a lane from one complete stable identity inventory. atomically retain
every eligible identity: readable conversations receive their stable head;
unreadable or unstable conversations receive a pending baseline with its error.
an unreadable head is never represented as an empty conversation.

one nullable baseline_error on the existing source_conversation row distinguishes
pending from established cuts. existing rows default to established without
changing any cut, original or checkpoint. pending rows cannot ingest events.
ordinary discovery after the complete inventory admits genuinely new identities
from their beginning, under the existing post-activation capture rules.

the collector retries a pending conversation's head through the provider's
read-only archive_head contract. the first successful observation atomically
sets its cut and captured_from, then clears baseline_error. subsequent retries
return the original receipt and cannot move that cut. known empty heads remain
valid established cuts. post-activation capture_error and retry-capture stay
separate from establishing a baseline.

native-archive.v3 hard-cuts the capture protocol. provider-runtime owns native
identity, stable head reads and error classification; universal-memory owns
state and atomic transitions; jarvis owns admission, transport, collection and
operator status. no new table, timestamp eligibility rule, native-file repair,
historical import, fallback reader or memory-tool change is introduced.

## costs and delivery

activity in a pending conversation before its eventual successful baseline is
not captured. unrecoverable conversations can stay pending indefinitely; new
independent conversations can proceed. status must show these coverage gaps.
the missing originals' cause is unknown; native lineage can link earlier file
segments without a user-created fork.

the single installed deployment is on schema 0008. insert memory migration
0008a before the unactivated one-main migration 0009, preserving its identity
and data effects. qualify a memory-only patch of the installed release and merge
the same change into current main. do not activate the incomplete v2 slices.
keep the qualified cognition version; publish compatible immutable dependency
artifacts and merge their archive changes upstream, with no standing maintenance
branch. stop and replace the native collectors and service together for v3.

## acceptance

- healthy and newly created conversations capture exactly once while listed
  unreadable conversations remain visible and unable to ingest;
- old prefixes stay excluded, including after restart, lost acknowledgement and
  delayed recovery of a pending conversation;
- resolving a pending empty conversation is distinct from an unreadable head;
  no retry or operator capture-error reset moves an established cut;
- partial or ambiguous identity inventories cannot activate a lane;
- migration preserves all established cuts, checkpoints and originals; the
  deployed patch changes no one-main behavior;
- installed macbook/devbox tools, collector progress and explicit pending status
  pass bounded live checks; broad usefulness/load work remains deferred.

use the existing scoped temporary red/green/refactor method and independent
adversarial review. delete only the new probes after proof; retain the approved
small regression groups. the active sequence belongs in the implementation plan.
