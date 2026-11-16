# attachments and durable originals

status: slice 5 implementation contract under
[adr 0071](decisions/0071-simple-event-driven-v2.md); source-audited against merged
main `d93b84d`, 2026-11-15. source and a separate private-storage/native-host
candidate are qualified; see [implementation evidence](#implementation-evidence).
the [roadmap](implementation-plan.md#attachments-and-original-storage) owns sequence.

## target and scope

jarvis receives files, keeps exact originals privately and reads them with its
normal native tools. conversation determines useful handling. one metadata table,
one private r2 bucket, three attachment tools; no document-processing product.

| settled choice | contract |
| --- | --- |
| capture | configured-owner discord uploads automatically; gmail file parts only when main selects them for retention |
| reading | jpeg/png/webp, pdf, ordinary text, docx and csv through native tools and established utilities |
| originals | private cloudflare r2; indefinite retention; 100 mib per decoded original; no expiry lifecycle |
| deletion | ordinary conversational consent; remove our original/cache, preserve source mail/discord, derivatives, notes and memory |

unsupported files can still be stored; unreadable is not unsaved. defer audio/video,
office macros, xlsx/pptx qualification, outgoing sharing/public links, browser/ui,
interactive hosting/television, extraction indexes, bulk mailbox capture, backup
and [budget ingestion](budget-integration.md). storage credentials are ordinary
private deployment configuration, not a credential product.

[slice 4](private-notes-and-rolodex.md#implementation-evidence--2026-11-15) now supplies
borrowed workspace and trusted native execution with mixed callbacks. qualify
actual image/file viewing here; reuse its pinned kernel/provider contracts.
no media protocol or new native writable root.
[one main](one-main-events.md) owns requests/consent/recovery;
[memory](universal-memory.md) keeps its capture policy and schema. this slice adds
only the mail discovery needed to select files; the
[full search proposal](complete-and-continuable-searches.md) remains deferred.
production activation remains at final v2 cutover, after candidate proof.

## source audit and final composition

| present gap | owning change |
| --- | --- |
| `discord.py` rejects empty captions | accept upload-only input under existing owner/channel/bot checks |
| `input_framing.py` labels all text owner speech | preserve raw caption; render the immutable upload manifest separately as host metadata |
| gmail attachments lack part ids; thread reads have a small body envelope | exact file descriptors and two narrow discovery reads; shared mime traversal |
| cross-attempt reads can replay paths | reuse the work-read freshness rule for open and both new mail reads |
| `BilledOnce` recovery assumes worker commands | attachment-specific recovery before generic absence/retry; ordinary action recorder |
| app/native host have different users and private tmp namespaces | a shared absolute cache path, app-writable and native-readable only |

flow: discord ingress → canonical caption/manifest + pending rows → source copy →
r2 → ordinary main input; gmail discovery → main-selected retain → the same store.
`attachment.open` materializes verified bytes; native tools inspect them.
the store owns byte identity, state transitions and reconciliation. the service
owns scheduling; existing journals own action authority and original receipts.

## data and invariants

add `0011_attachments` after current `0010_work`; audit the actual predecessor
before implementation. one `attachment` table; all times are `timestamptz`.

| field | type / invariant |
| --- | --- |
| `id` | uuid primary key; stable reference `attachment:<id>` |
| `source`, `source_key` | closed jsonb source; sha-256 of existing canonical-json encoding; immutable |
| `r2_account`, `bucket` | nonempty text, immutable host-configured location |
| `origin_message_id`, `capture_action_id` | message fk; nullable unique action fk, null only for automatic discord capture; no cascading deletion |
| `filename`, `media_type`, `advertised_size` | nullable original metadata; size nonnegative bigint; never a path or actual-byte proof |
| `size_bytes`, `sha256` | nullable together; actual size 0..104857600 and lowercase 64-hex digest, frozen after complete download |
| `state` | `pending`, `ready`, `failed`, `deleting`, `deleted` |
| `put_entered_at`, `stored_at`, `deleted_at` | nullable factual times; put entry requires frozen size/hash; ready/deleting/deleted require stored evidence |
| `delete_action_id`, `error` | nullable action fk; nullable closed failure code below, never private diagnostic prose |
| `created_at` | immutable registration time |

source shapes are exact:

```text
discord: {kind, guild_id, channel_id, message_id, attachment_id}
gmail:   {kind, account, message_id, part_id}
```

discord ids are decimal snowflakes. gmail ids are exact provider strings bounded
at 1024 utf-8 bytes; only native root `part_id` may be empty.
account is the connector-verified profile email, never model input. check it again
when resolving a source after restart/configuration change. filenames, array
positions, equal contents and signed urls are not identity.
gmail's external `attachmentId` is a transient transport handle, refreshed from
the exact message/part for each download; it is never stored as source identity
or included in a page digest. the owner approved this correction after four live
reads of one unchanged fixture returned four different handles. google documents
[`message.id` and `partId`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages)
as immutable. source account and exact message/part are revalidated; a restarted
pre-put download must still match its frozen size/hash.

automatic ids are uuid5 under `NAMESPACE_URL` over
`jarvis:discord-attachment:<guild>:<channel>:<message>:<attachment>`; explicit
creation uses `action.id`. enforce unique `source_key` for pending/ready/deleting
rows. a ready source reuses its existing original and atomically receipts the
new caller's action; pending/deleting returns that state without transferring
capture lineage. distinct sources with equal bytes retain separate attribution.

failed/deleted rows remain. a fresh explicit retain can create a new id/key;
original callbacks and automatic discord replay always return their original
receipt/manifest. deletion is not a source blacklist. never resurrect an old row.
key is `attachments/<id>/original`; no overwrite or filename-derived key.
client account/bucket must match the row; credential rotation cannot retarget it.

state transitions: pending → ready or failed; ready → deleting → deleted.
unknown upload stays pending; incomplete deletion stays deleting. never reset
ready or rewrite original invocation receipts. populated put/storage/deletion
timestamps and delete lineage are write-once. `error` distinguishes unresolved or
definite failure; successful transitions clear it. enforce the immutable columns,
state prerequisites and active-source uniqueness in the database, reusing current
constraint/trigger conventions; no generic lifecycle framework.

## discord ingress and admission

in one transaction, source-deduplicate the message, store its exact raw caption,
register all originals and freeze ordered `trace.attachment_manifest` entries:
`{id, name, name_truncated, media_type, advertised_size}`. use the same display
descriptor below; no url, local path or mutable storage status. duplicate ingress
returns the stored manifest, never newly appearing files. no history backfill or
edit/delete synchronization.

keep `message.text` a non-null string. allow empty text only for owner/discord
rows with a validated nonempty manifest; otherwise retain the nonempty invariant.
extend the existing `message_cause` trigger to freeze the manifest key. preserve
the existing 16-kib trace bound; bounded previews must fit the supported discord
upload manifest without dropping entries. this is content, not scheduling state.

render nonempty caption as `owner_input` and file metadata as a separate
host-authored `attachment_manifest` section with the same `input_id`. upload-only
inputs remain explicitly dispositionable. never fabricate owner speech.
one deterministic manifest renderer supplies prompt and archive text; ordinary
archive projection includes those labelled references in its text/digest, without
new memory tables/events or binary content. no-manifest historical text/digests
stay unchanged.
classify administrative pause/resume from the raw caption using the existing
classifier, replacing the `text == control_kind` persistence assumption.
control plus uploads still captures files; control remains immediate and creates
no extra main turn. conversational stop keeps slice 1's behavior.

one service-owned capture task scans automatic pending rows in arrival order.
do no copying under `_active_lock`, `_dispatch_lane` or an open db transaction.
`MessageStore.pending_inputs` excludes an input only while one of its automatic
manifest originals is pending with no recorded outcome. ready, failed, deleting,
deleted or pending with `CaptureUnresolved`/`StorageConflict` releases that input.
this same predicate covers new turns and steering; no request state, parking bit,
first-attempt timestamp or jobs table. action-backed retains do not reblock inputs.

capture requires the existing deployment owner and continues as narrow ingress
bookkeeping while cognition is paused; ownership loss fences new mutation entry.
other ready input, consent and delivery stay responsive. finishing preparation
signals existing service work. startup resumes unfinished preparation, reconciles
entered puts and leaves recorded uncertainty for explicit repair. shutdown stops
new captures and joins entered io cooperatively. failed siblings never hide usable
files. no automatic summary, notification, todo or workflow is added.

## gmail discovery and source reads

reuse connector authorization and attempt accounting. resolve account with
`users.getProfile(me)` using existing scopes; never infer it from a token filename.
[profile contract](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile).

two closed automatic-read contracts, using existing result/failure envelopes:

```text
gmail.list_thread_messages({thread_id, offset, limit, expected_digest})
  -> {thread_id, digest, total, offset, message_ids, next_offset, observed_at}
gmail.list_attachments({message_id, offset, limit, expected_digest})
  -> {message_id, thread_id, digest, total, offset, attachments, next_offset, observed_at}
file descriptor: {part_id, name, name_truncated, media_type, advertised_size}
```

native callbacks supply every field explicitly, following the existing closed
tool contract: first-page values are offset 0, limit 50 and expected_digest null.
offset is a strict integer 0..2^53−1; limit is 1..50. offset > 0 requires the
expected digest's lowercase sha-256 value. no omission-normalization layer is
added before immutable callback recording, fingerprinting or replay.
mismatch returns `SourceChanged`, no page. next is offset + returned count if
below total, otherwise null; past-end offsets return empty. enumerate exact ids
lexically, explicitly not chronologically. digest canonical account/source ids
and the complete ordered list, including original names, types and advertised
sizes for files. transient external attachment handles are excluded. display
truncation never changes identity/digest. use current
128-kib read output limit. offset 0/null starts a new observation.

thread membership uses `threads.get(format=minimal, fields=id,messages(id))` under
the existing 2-mib/8-second metadata bound. validate returned identity and unique
ids. this makes discovery possible even when inline files defeat `read_thread`'s
small body envelope. [thread formats](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get).
file discovery gets one exact message with `format=full&fields=id,threadId,payload`.
no model-facing body data. recurse every container, including named containers;
only leaves are files: named leaves, attachment disposition, or non-text leaves
with inline/external data. unnamed images qualify; ordinary plain/html bodies do
not. preserve named text as a file. reject duplicate part ids or structural
overflow explicitly; existing depth 20/node 500 limits must not hide a tail.

share one mime walker/descriptor with `gmail.read_thread`. retain its body-reading
contract; replace its unusable filename-only attachment schema with the descriptor,
per-message `attachments_total` and `attachments_digest`. its first 50 entries
come from the same complete sorted list/digest, continuing at offset 50 through
`list_attachments`; no 25-mib discovery rejection. keep
search semantics unchanged. both new reads are fresh across attempts, while the
original callback replays its exact receipt. otherwise a stale first page could
loop forever after `SourceChanged`. reuse existing failures, adding only
`MessageNotFound` and `SourceChanged` to these read contracts.

retain validates the selected leaf again. external bodies use the documented
attachment endpoint; inline bodies require the enclosing message. decode exact
base64url bytes with standard libraries. a full message can contain unselected
inline bytes transiently; they are never separately retained, exposed or indexed.
partial-field syntax cannot select a mime array element by part id.
[gmail bodies](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments),
[partial fields](https://developers.google.com/workspace/gmail/api/guides/performance#fields_parameter_syntax_summary).

source/cache reads have a 300-second work deadline. cancellation stops subsequent
reads and joins entered blocking file/socket work before releasing its resources;
that cleanup can outlast the deadline. count streamed actual bytes:
100 mib decoded original, 140 mib external-body json, 160 mib enclosing-message
json, measured after http decompression. spool bounded responses; use standard
json/base64 libraries, not a new streaming parser. `TooLarge` means the selected
file exceeded its bound; `ProviderResponseTooLarge` means the enclosing response
could not be inspected, even if that file is small. never save a prefix. advertised
size can reject an oversized capture early, but must not cap discovery.

discord refreshes the known message's expiring attachment url; revalidate owner,
channel, message and attachment identity, then fetch the original, not its resized
proxy. accept no arbitrary model url. signed urls stay out of persistence, model
context and logs. [discord attachment urls](https://docs.discord.com/developers/reference#signed-attachment-cdn-urls).

## storage, tools and effect recovery

use one composed boto3 low-level s3 client, pinned/qualified during implementation;
blocking io runs off the event loop. explicit app credentials; sdk
`total_max_attempts=1`, `request_checksum_calculation=when_required`. use
`put_object`, not managed multipart upload. no signing adapter or transfer service.
[sdk configuration](https://docs.aws.amazon.com/botocore/latest/reference/config.html).

stage privately, calculate size/sha-256/md5, freeze size/hash, then persist
`put_entered_at` before the sole create-only put. send `IfNoneMatch="*"`, exact
`ContentLength`, `ContentMD5` and sha-256 metadata. qualify those headers against
r2; etag is not our sha-256. a restarted pre-put download must match frozen byte
facts or fail `SourceChanged`. a validated put success or matching head establishes
stored evidence; commit ready and any originating action receipt atomically.
[r2 conditional writes](https://developers.cloudflare.com/r2/api/s3/conditional-operations/),
[supported s3 headers](https://developers.cloudflare.com/r2/api/s3/api/).

after ambiguous entry, head the exact key at 0, 2 and 8-second backoffs, each
with a 10-second read deadline. matching length/hash metadata proves completion;
conflict stays pending `StorageConflict`. absent or unavailable evidence after
the bounded procedure stays pending `CaptureUnresolved`. negative head does not
prove an earlier put cannot still commit. do not repeat that put, replace its
key, or delete until positively reconciled. definite no-effect rejection/source
failure permits failed and a fresh retain. no private failure-body logging.
upload uses 10-second connect/60-second socket timeouts, without an outer timeout
that abandons a still-running mutation. this is not a 300-second total upload
guarantee. [r2 consistency](https://developers.cloudflare.com/r2/reference/consistency/).

below are tool-specific arguments; keep the normal `ActionRequest` envelope.

| tool | closed input → success | authority |
| --- | --- | --- |
| `attachment.retain` | `{source: {kind: discord, message_id, attachment_id} \| {kind: gmail, message_id, part_id}}` → snapshot | automatic write; no url or local path |
| `attachment.open` | `{id}` → `{attachment: snapshot, source, local_path}` | fresh read; materialize verified original |
| `attachment.delete` | `{id}` → `{id, deleted_at, scope: original_and_cache}` | consequential write; existing conversational consent |

snapshot is `{id, name, name_truncated, media_type, size_bytes, sha256}`. ids are
uuids; references render `attachment:<id>`. name is null or a deterministic
240-byte utf-8-safe preview, also bounded to 240 bytes after json escaping; type
is nullable MIME metadata, bounded at 255 utf-8 bytes, without C0/DEL controls. original
names stay in metadata. file descriptors expose advertised size separately.
success and failure return no r2 credentials, bucket urls or binary content.

typed attachment failures: `NotFound`, `TooLarge`, `ProviderResponseTooLarge`,
`SourceChanged`, `Unavailable`, `Pending`, `CaptureUnresolved`, `StorageConflict`,
`Deleting`, `DeleteUnresolved`, `CacheCleanupFailed`, `Deleted`. include registered
id when known; no freeform provider error. invalid arguments fail normal schema
validation. failed originals open as `Unavailable`; pending/deleting/deleted
return their truthful state. these tools join main's full event plan, not isolated
memory roles. no agent repair tool or mandatory reading choreography.

retain/delete use `ReDispatchable`, lifetime executor ceiling 2, and the existing
recorder. retain permits at most one actual put per original; delete permits at
most two actual deletes per action. executor entry and provider entry are
different facts. reconcile attachments before generic zero-attempt/absence retry;
do not route them through worker-specific `BilledOnce` handling. recover stored
receipts first. reuse `complete_local_action` for atomic final metadata/receipt;
uncertainty uses the existing action-resolution mechanism in the same transaction.
if pre-put recovery exhausts entry capacity, fail its owned pending row too;
never strand an active source reservation. an exact native callback replays its
original evidence. later proof may advance an uncertain action's current
resolution through `resolve_reconciliation`, preserving that invocation receipt
and earlier uncertainty message, without re-execution. otherwise the existing
causal-component write barrier would incorrectly survive successful repair.

## cache, deletion and operations

production cache path is `/var/cache/jarvis/attachments/<id>/original`, outside
private application state and writable notes. app owns directories/files with
`codex-clients` group and explicit 0750/0640 modes; private staging is 0700/0600.
publish only after sha-256 verification and a final ready-state check under the
row lock also used by deletion. download outside the transaction, then atomically
rename; abandon staging if state changed. verify existing cache bytes on open.
no native writes to originals or additional writable root. gitignored ordinary
workspace scratch holds derivatives; no original binaries in the notes repo.

`attachment.open` bypasses cross-attempt cached read receipts using the existing
work-read freshness policy; exact original callbacks still replay. paths are
disposable, not visual context or durable citations. on restart, discard stale
staging and app-owned published cache before fresh admission; r2 rematerializes
on demand. no cache database, lease or eviction daemon. operator may clear cache;
native file failure requires a fresh open. local disk growth between restarts is
an explicit cost, not a second permanent-storage promise.

delete requires ready, or recovery of its own delete action; pending put blocks.
latch deleting/delete-action id under the row lock before remote io. new open,
retain and cache publication cannot bypass it. delete the unique r2 key and app
cache, confirm absence, then atomically commit deleted plus receipt. after a lost
response, use bounded head observations; retry remote delete only under the
existing finite action/provider ceilings. this is safe because the sole put has
completed and the key is never reused; a later capture gets a new id/key. if the
object is already absent, retry only local cleanup. wrong metadata is a conflict,
not permission to delete an unrelated object. uncertain remote outcome stays
deleting/`DeleteUnresolved`; definite local cleanup failure is
`CacheCleanupFailed`: the action fails with partial completion stated honestly,
without an uncertainty barrier. failed preflight with no prior provider entry,
or a definite rejection of the first provider attempt, fails as `StorageConflict`
or `Unavailable`, without effect uncertainty. an earlier staged
delete still requires bounded reconciliation even if a later call is rejected.
incomplete rows remain deleting; never reset ready.

scope excludes source mail/discord, scratch/other copies, already-open file
handles, conversation, notes and memory. no revocation or forgetting claim.
replaying completed delete returns its original receipt; a fresh delete of an
already deleted id returns the same factual deletion snapshot without another
provider mutation, committing its own action receipt.

reuse stopped-owner cli checks for
`jarvis attachment-reconcile <id> [--after-manual-cleanup]`. it only observes the
same key/cache: matching pending bytes can become ready; absent deleting
object/cache can become deleted. absent unknown puts remain unresolved.

when evidence proves the original action outcome, atomically commit attachment
state, its current action resolution and the normal source-deduplicated action
outcome message. extract the existing resolution transaction body for shared use
with its existing publication helper; no second action ledger. original native
receipts and prior messages stay unchanged. default mode requires no manual
mutation of this key/cache since the action. manual cleanup through normal
operator tools MUST be reported with the flag: it records facts only, proving
neither the old action's outcome nor permission to clear its uncertainty.
that causal write block remains; independently authorized new owner work remains
possible. no claim that a manual purge was the original action's success.
later factual cleanup also preserves an earlier definite failed action and its
native receipt; publish the new observation rather than rewriting that failure.

automatic capture or manual-cleanup facts instead append one host observation
atomically with factual state, using `source=attachment`, identity `<id>:<new_state>`.
parent it to the capture/delete action's request or ordinary upload request.
control+upload has no eligible parent: use null and retain `origin_message_id` as
reference metadata; do not weaken the control-parent rule. no unbounded background
retry or model-callable repair.

deploy one private bucket with public domain/r2.dev and expiry disabled, scoped
application credentials. add required `JARVIS_ATTACHMENT_R2_ACCOUNT_ID`,
`JARVIS_ATTACHMENT_R2_BUCKET`, `JARVIS_ATTACHMENT_R2_ACCESS_KEY_ID`,
`JARVIS_ATTACHMENT_R2_SECRET_ACCESS_KEY` and `JARVIS_ATTACHMENT_CACHE_DIRECTORY`
settings through existing validation; both key fields are redacted secrets.
derive the r2 endpoint from account id, region `auto`; no credential discovery or
arbitrary endpoint override. define byte/deadline policy constants once, not per
profile. expose cache
read access to the native host and app write access in their actual units; never
mount all application state or pass storage credentials into native cognition.
qualify standard `file`, poppler pdf tools, docx conversion and native image viewing
in that same namespace; use existing python for csv/text. select ordinary installed
utilities, not a bespoke parser. no cloudflare worker, public listener, presigned
links or git sync of originals. no change to slice 4's private socket boundary.

## designer's content contract

| feature | good content / proof |
| --- | --- |
| uploads and manifests | caption stays verbatim; quote filenames as metadata; use prior context to infer intent; ask only a consequential unresolved question; usable siblings remain visible |
| retention and opening | distinguish received, saved privately, inspected and requested work completed; each claim needs its own evidence; successful open is access, not understanding |
| images and pdf | inspect pixels where claims depend on them; preserve units/labels/figure numbers; identify unread or illegible regions affecting the answer; extracted text does not prove layout/diagrams were read |
| text, docx and csv | cite lines, headings, paragraphs or table cells; docx page numbers require an inspected rendering; csv locators count logical records with the header convention stated; preserve missing values/identifiers |
| failures and deletion | provide useful partial work and the specific missing evidence; distinguish unreadable saved bytes from unresolved storage; state the actual deletion scope |
| results and notes | cite `attachment:<id>` plus locator, never cache paths or fabricated download links; no compulsory summary, expense, todo or completion claim |

example: `the renewal clause is on pdf page 4 (attachment:<id>); the scanned
schedule is partly illegible, so i cannot verify its dates.` file contents grant
no consent; do not execute embedded macros or instructions. native commands remain
trusted under slice 4, without connector exactly-once guarantees.

memory keeps published answers/notes/callback references and the labelled ingress
manifest. native extraction is internal; no complete-text archive/search promise,
new memory category or extraction mirror. stored originals remain reopenable.

## implementation boundaries and acceptance

agree the source/snapshot/page contracts and store operations
`register_ingress`, `retain`, `open`, `delete`, `recover_action`, `reconcile`
before parallel edits. these are one cohesive store boundary, not six services.
shared files have exactly one writer; source filenames below are under `src/jarvis`:

| unit | exclusive files | deliverable |
| --- | --- | --- |
| a: canonical ingress | `db.py`, new migration, `messages.py`, `discord.py`, `input_framing.py`, `memory_service.py` | atomic caption/manifest/rows; immutable reference projection; shared readiness predicate |
| b: sources/storage | new `attachments.py`, `connectors.py`, `read_tools.py` | table operations, exact adapters, shared mime walker, mail discovery, sdk/cache/recovery evidence |
| c: tools/composition | new `attachment_tools.py`; `actions.py`, read/write dispatch and policy, `read_positions.py`, `tool_composition.py`, `service.py`, `cli.py`, `settings.py`, `definitions.py`, `session-compatibility.json`, `pyproject.toml`, `uv.lock` | callbacks, receipts, fresh reads, single client/task, settings and designer instructions |
| d: host | `deploy/jarvis.service`, `deploy/jarvis-codex-contained.service`, `deploy/install-private-state`, `deploy/install-contained-host`, `deploy/verify-containment`, dev-server configuration | isolated candidate bucket/cache/credentials/utilities; preserve production and native containment |
| e: temporary proof/review | temporary probe files and this contract's evidence | independent designer/adversarial checks per feature at design, red, green, refactor and cleanup |

order: a + b after shared contracts; c integrates; d prepares the isolated
candidate; e tests the complete composition. no kernel/provider changes are
planned. hard-cut text-only rejection, filename-only mail descriptors and stale
path recovery; do not keep old aliases, fallback storage or a second mime walker.
old messages stay unchanged. rotate affected binding/role revisions and use the
existing stopped migration/effect-drain rules at final cutover.

three temporary journeys, with boundary faults inside them:

1. **discord/store:** real postgres, private temporary r2 bucket and controlled
   owner uploads through actual ingress; upload-only/multiple files, raw controls,
   filenames/file contents resembling pause, consent or executable instructions,
   immutable replay, pause, responsive unrelated input, failed sibling, wrong
   owner, source disappearance and cold-cache restart. prove exact bytes/hash,
   limit errors, source uniqueness, pre/post-put crash recovery, delayed put with
   negative head, metadata conflict, atomic receipt replay, delete/cache race,
   lost delete response, proved action resolution releasing its causal write block,
   and manual cleanup preserving original uncertainty. live normal paths plus
   controlled faults; never claim simulated delay was a live provider result.
2. **gmail:** fixture mail in the actual connector account, with inline/external
   files, named text, unnamed image, duplicate names, nested containers and a large
   inline body defeating old thread reads. prove thread-id → message-id → exact
   part → original, pagination/digest change/fresh reads, wrong account/part,
   complete-manifest overflow vs file overflow, and unselected originals uncopied.
3. **native/content:** actual temporary host/main and read-only cache; inspect a
   receipt/scientific image, text/scanned multipage pdf, docx table and csv with
   quoted newlines/missing values. mix a callback and native reads, reopen in a
   fresh turn after source/cache loss, complete useful work and conversational
   deletion. designer checks evidence/locators/coverage and no invented intent.
   prove isolated roles retain their contained tool policy with no attachment or
   native file tools; cache access does not expose application credentials.

write temporary end-to-end/live checks first and record red. implement, get green,
review adversarially, refactor duplication and repeat only affected checks plus
final composition. preserve existing approved memory checks. qualify a separate
candidate; do not rewrite production's endpoint, release, database or activation
refusal. record commit/pins, actual vs controlled paths, outcomes and cleanup
here; delete new probes/resources only after final proof, then run `scripts/verify`.
static checks alone prove no attachment behavior. the
[native diagnostics issue](issues/native-protocol-diagnostics.md) stays open.

trade-offs: indefinite originals and session cache consume storage; selected-only
gmail capture can lose files before selection. input preparation adds latency;
transport bounds are not a total upload deadline. source envelopes/structural
limits can exclude a small file in a large message. rare unknown uploads can
remain unresolved indefinitely; retaining one put avoids a resurrection/tombstone
protocol. bounded delete retries remove avoidable manual repair. native tools
have format/model limits below the storage cap. references are retrieval identity,
not a hosted viewer; scoped deletion is not forgetting. deleting temporary proofs
removes their future regression coverage.

specification review, 2026-11-15: independent architecture, content and storage
adversaries reviewed the source audit and final contract; identified gaps above
are resolved in the design. `scripts/verify` passed; final documentation links
and whitespace were rechecked. at that documentation-only review, implementation
and live acceptance were NOT_RUN; no code or provisioning had changed.

## implementation evidence

qualified 2026-11-16 in `feature/attachments-and-durable-originals`, based on
`d93b84d`. application implementation commit: `ad6c48eadd61d730228213d65c2cdec178373a9b`.
host utilities landed in [dev-server pr 220](https://github.com/NielsdaWheelz/dev-server/pull/220),
`30fc658009799b30a656c065b474b3811b848b5f`. this is source and separate temporary
candidate qualification. production application activation remains deferred to
final v2 cutover.

the owner selected native subagents with separate ingress, source/store and
tool/composition ownership. independent adversarial and content reviews checked
contracts, red results, green behavior, refactoring and cleanup. temporary checks
used actual postgres, action/native journals and the ordinary executor; controlled
failures exercised boundaries that a live provider cannot safely reproduce.

### fixed contracts and composition

- migration `0011` follows `0010`: one attachment table, 17 application tables
  including memory and work; no extraction/job/recovery ledger. fresh migration
  and runtime-role constraint checks passed. immutable source/location/byte facts,
  active-source uniqueness, manifest bounds, state prerequisites and write-once
  lineage/times were checked against real postgres, including rejected updates.
- the owner approved stable gmail identity `{kind, account, message_id, part_id}`
  after four reads of one unchanged live fixture returned different transport
  handles. fresh resolution supplies each download's handle; source keys and page
  digests exclude it. `gmail_account` and `FRESH_READ_IDS` are the shared public
  seams for slice 6. first-page callback fields are explicit `0`, `50`, `null`,
  matching the existing closed tool library rather than adding an input adapter.
- one composed boto3/botocore `1.44.3` client, one total attempt and zero sdk retries.
  existing dependency pins remain: kernel `9f5f951272536d51567995cbd693d1239ad59eb9`,
  provider `ea9f82025632926a7c7e47d6333fb9346f6ee86c`, llm-tools
  `8989f3afdcc640f775bd0cc9e7a0b4c246f10e57`, memory
  `93e02af07fee7e79250fb800835c324f092b5bec`. main/application and affected
  binding revisions rotate; isolated roles and provider/kernel contracts do not.

### exercised behavior

| boundary | proof and outcome |
| --- | --- |
| ingress | actual postgres and configured-owner discord upload with an empty caption; immutable raw-caption/host-manifest projection, exact source bytes/hash, cold reopen and original source preservation passed. controlled multiple uploads, failed siblings, raw pause plus files, hostile-looking metadata, wrong actors/channel/webhook/thread, duplicate edits and readiness/steering passed. old no-manifest archive bytes/digests stayed unchanged. |
| mail | three actual synthetic drafts exercised named root text, a 63-file nested/duplicate/unnamed bundle and a large body. complete digests/pagination, refreshed transport handles and exact selected retention passed; 54 of the bundle's 63 file parts were not selected or copied. gmail externalized the actual file bodies, including the large body: inline decoding and oversized enclosing-response paths were CONTROLLED http proofs, not live-inline claims. all three drafts were removed; no send or calendar mutation occurred. |
| source limits | controlled streamed http after decompression tested 100-mib decoded originals, 140-mib external json, 160-mib enclosing json, structural overflow, changed source/part/account and expiring discord source refresh. no retained prefix; selected-file overflow and enclosing-response overflow remained distinct. |
| private storage | actual private temporary r2 bucket verified conditional create-only headers, exact length, content-md5, sha-256 metadata and bytes; duplicate put returned 412, bad checksum 400 and absent key 404. actual store/postgres/sdk journeys passed retention, verified/cold cache and deletion. public endpoints/custom domains and object expiry were disabled. |
| recovery and receipts | actual journals/executor with controlled sdk faults proved sole-put/no-repeat, delayed put with negative head, conflict, byte-fact freeze after restart, original uncertain callback replay, late positive proof releasing the causal barrier, manual cleanup preserving uncertainty, bounded two-delete lifetime, queued completion and zero-entry failure guards. cache cleanup failure is a definite partial failure; no-entry preflight and definite first rejection fail without invented uncertainty. a prior possibly entered delete remains unresolved until bounded proof. |
| cancellation and races | repeated cancellation drained entered blocking io before resource cleanup and preserved the committed receipt. real postgres concurrency proved no byte or empty-directory publication after deletion. local preparation remains outside transactions; directory metadata/rename use the existing ready-state row lock. |
| native access | separate linux host and app, actual mixed callback/native composition and fresh cold process. all ten originals reopened; nine successful native image views covered original images and every rendered pdf page. independent namespace checks verified exact bytes, app ownership, 0750/0640 modes, read-only cache, denied append/unlink and unreadable application credentials. |
| useful content | independent inspection checked receipt total 39.75 without invented currency; labelled scientific graph peak 9 microvolts at 200 ms without statistical claims; every protocol/scanned pdf page; docx identifiers/missing versus zero and embedded newline; csv logical-record versus physical-line counts. useful prose used attachment references/locators rather than cache paths. originals stayed out of notes git; scratch derivatives were ignored. |
| policy and deletion | actual isolated compactor retained tool-free, read-only, network-disabled, approval-deny policy. actual main used ten ordinary conversational approval transitions and delete callbacks. each retain/delete action succeeded with one executor entry. final native reads returned ten `Deleted` results without mutation. ten r2 heads returned 404, bucket count was zero, no per-id cache remained; useful output, scratch and the actual source discord upload were preserved before temporary-candidate teardown. |

actual native successful attempts include
`a46d5316-f082-46db-ae18-40dfcb45b94f` (first useful inspection),
`f5811a79-925a-4416-baeb-fb8f036e3b18` (source-loss/cold-cache inspection),
`dfd9e3fb-b8f0-4b02-808b-cb2d2eec77e0` and
`1fd81746-06af-4654-a24c-f344b64c890e` (conversational deletion and outcomes),
`4f4ab710-1383-44fa-9df7-f6c24e55d8af` (final read-only deleted-state check).
exploratory native commands recovered from extensionless docx autodetection by
supplying `pandoc -f docx`; this required no product parser or format adapter.

the linux candidate used python 3.12.13, postgres 16.12 with pgvector 0.8.1,
stock codex 0.160.0 (sha-256
`12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad`),
file 5.45, poppler 24.02.0 and pandoc 3.1.3. the application preserved its
pid-only proc view; the native host retained the ordinary kernel metadata needed
by its existing sandbox. no account authentication or storage credential entered
the native checkout/environment.

### adversarial repairs and final checks

red probes exposed and green probes verified corrections to oversized escaped
filename previews, exact byte/source/location reuse, immutable uncertain native
receipts, action-specific manual-cleanup provenance, queued deletion resolution,
provider-attempt accounting, repeated cancellation, definite cleanup failures,
zero-mutation false uncertainty, sdk `ClientError` handling and final cache
directory publication. the final two repairs were exercised with current-source
postgres/executor/controlled sdk and concurrency probes. live native format and
policy paths were unchanged; independent review found no reason for another paid
format run. once-used wrappers and duplicate locking/resolution code were removed
or consolidated into the existing transaction owners.

`scripts/verify` passed after deleting the two new repository probes: frozen
resolution, formatting/lint, configured strict types, document links, clean
wheel/sdist installation, dependency identity and vulnerability audit. the three
non-pypi git libraries retain the audit tool's explicit skip classification.
the existing capture/retry group passed against real postgres; the pinned
memory library's existing completion regression passed separately. neither
approved group was deleted.
[hosted ci](https://github.com/NielsdaWheelz/jarvis/actions/runs/43830522400)
also passed for the exact application implementation commit.

all new temporary probes, fixtures, evidence logs and local/remote candidate
resources were removed after proof. both candidate postgres containers and their
volumes are gone; the temporary r2 bucket was empty before removal, and both its
object client and provisioning token were revoked. the separate host service,
checkout, mappings, runtime, notes and cache are gone. the host lane and exact
committed artifact were communicated to concurrent slice 6 and its independent
reviewer for combined `0011` → `0012` qualification.

a broader ad hoc strict check also found four preexisting historical-migration
annotation/stub errors outside the configured gate. fresh migration execution
found no runtime defect; the bounded follow-up is recorded in
[the typing issue](issues/migration-type-checking.md), without changing historical
sql or silently expanding the project gate.

### retained operational boundary

the temporary bucket/client/provisioning token, candidate host/db/runtime/cache,
synthetic mail and new probes are disposable proof resources. the existing private
`jarvis-storage` bucket remains private with no object expiry; its new object-only
application credential is stored in the existing private envs area at
`projects/jarvis/.secrets/attachments.env`, mode 0600. this is standby configuration,
not production activation. production's selected release
`b6cf4b32d32f2b01291d47291a206d4fc744fce4`, application pid 590939, endpoint and
database were preserved. installing the three ordinary utilities added about
205 mb; no existing package was upgraded or service restarted for that install.

the stated costs remain indefinite storage and between-restart cache growth,
selected-only source loss, enclosing-response/format limits, and potentially
permanent unknown-put uncertainty. entered io drains may outlast the read work
deadline; socket limits are not a total put deadline. deletion is scoped to our
original/cache, not forgetting. removing temporary tests trades future regression
coverage for the owner's selected proof method. a definite failed delete stays
latched `deleting` and may require operator cleanup, even after a transient
preflight outage; it creates no general uncertainty barrier. deferred formats, public sharing,
backup/restore and final installed v2 activation remain outside this slice. the
[native diagnostics issue](issues/native-protocol-diagnostics.md) remains open.
