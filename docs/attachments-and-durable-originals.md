# attachments and durable originals

status: proposed implementation contract, 2026-10-11; docs only. adopt the table,
tools and narrow ingress exception in spec/adr before implementation. the
[roadmap](implementation-plan.md#attachments-and-original-storage) owns sequencing.

## target and settled choices

jarvis receives files, retains exact originals privately and uses normal native
tools to read them. it chooses useful handling from conversation. no user-facing
reader, custom extraction pipeline, ocr agent or document index.

| decision | contract |
| --- | --- |
| capture | configured-owner discord uploads automatically; gmail file parts only when main selects them to fetch |
| reading | images, pdf, ordinary text, docx and csv; native tools and standard utilities |
| originals | one private cloudflare r2 bucket; indefinite retention; no expiry lifecycle |
| deletion | exact-approved physical deletion of our original/cache; previously captured memory/notes remain |

unsupported files may still be retained; reading failure never means storage
failure. initial qualified images are jpeg/png/webp; other native decoders may
be used without promising fidelity. audio/video, office macros, xlsx/pptx
qualification, outgoing sharing, public links, a browser/ui, bulk mailbox capture
and database backup are outside this slice. accounting remains
[budget integration](implementation-plan.md#budget-integration).

[trusted-native notes access](private-notes-and-rolodex.md) is a prerequisite for
image/shell reading; [o6](one-main-events.md) owns main/input/action rules. reuse
[complete mail manifests](complete-and-continuable-searches.md) and
[memory capture](universal-memory.md). inspected upstream pins still need the
existing notes handoff; an image path in a text callback does not present pixels.
attachments require no additional kernel/provider media protocol.

## data and identity

add one `attachment` table. timestamps are `timestamptz`; sources are closed json.

| field | contract |
| --- | --- |
| `id` | uuid; immutable `attachment:<id>` reference; automatic discord ids derive from source identity; model-created copies use the creation action id |
| `source`, `source_key` | exact source tuple/canonical digest; unique active source across pending/ready/deleting copies |
| `r2_account`, `bucket` | immutable storage location from host configuration; never model-selected or silently retargeted |
| `origin_message_id`, `capture_action_id` | canonical lineage; action null for automatic discord capture |
| `filename`, `media_type`, `advertised_size` | original provider metadata, nullable when absent; not a local path or authorization |
| `size_bytes`, `sha256` | null until complete download; frozen actual byte count/lowercase sha-256 before upload |
| `state` | `pending`, `ready`, `failed`, `deleting`, `deleted` |
| `put_entered_at`, `stored_at`, `deleted_at` | nullable factual times; one original upload entry per copy |
| `delete_action_id`, `error` | nullable action lineage and bounded typed failure code; no private error prose |
| `created_at` | immutable registration time |

discord source is guild/channel/message/attachment id; gmail is verified
account/message/native mime-part id, plus external attachment id when present.
never use filename/order/content equality/signed url as identity. validate exact
discovered leaves, including inline data; containers are not files. account and
credentials come from the existing connector, never model arguments.

duplicate source reuses its active copy; identical bytes from another source
keep separate attribution/objects. failed/deleted copies retain metadata; a fresh
retain action may create a new id. old callbacks replay their original receipt/id,
never resurrecting that copy. automatic discord replay keeps its original
manifest. deletion is not a source blacklist.

an active ready copy returns its snapshot; pending returns `Pending` or
`CaptureUnresolved`, deleting returns `Deleting`. never enter another put or
transfer its capture-action lineage. reusing a ready copy commits that retain
action's original receipt transactionally before returning.

object key is `attachments/<id>/original`; filenames never become keys. original
bytes and successful size/hash stay immutable. cache and derivatives are
disposable. notes/answers link `attachment:<id>` with a page, section, figure,
text line or csv row where relevant.
the one configured client must match the recorded account/bucket; incompatible
configuration fails explicitly. credential rotation never moves an original.

## intake, storage and recovery

accept attachment-only messages under existing owner/channel/bot checks. persist
text, a host-labeled file manifest and attachment rows atomically before network
copying. missing text becomes an honest upload description, not an invented
owner instruction. classify controls from original text only. manifest contains
stable ids and bounded name/type/size previews, marking shortened names; no
signed urls. canonical message bodies never change with capture status.

prepare file-bearing input with one bounded first capture attempt per file before
initial native delivery. capture runs in the existing service process; other
ready input, consent and outbox stay live. failure/unresolved capture ends
preparation with truthful unavailable metadata. use ordinary work signals,
admission and startup scanning of unfinished rows; no jobs table/file-wait
protocol. automatic copying is the narrow host-ingress exception, including
while cognition is paused. it grants no model write authority or main turn.
shutdown admits no new copying; entered mutations finish cooperatively.

source adapters take discovered ids only. refresh discord urls by fetching the
known message; download the original, not a resized proxy. signed urls expire.
gmail reads the exact inline mime body or external attachment, decoding base64url
with standard libraries. [discord reference](https://docs.discord.com/developers/reference#signed-attachment-cdn-urls),
[gmail attachment bodies](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments).

initial original bound is 100 mib per file. source download/cache fetch have a
300-second operation bound; count actual bytes, with a separate bounded gmail
encoding envelope. `TooLarge` never saves a prefix. stream to an app-owned file,
compute/freeze size/hash, then upload. preserve existing text/model buffer limits.
no total attachment-count/history ceiling.

use boto3's low-level s3 client, pinned/qualified during implementation; one
app-owned client in composition, with blocking io off the event loop. no custom
signing/multipart orchestration. single
create-only `PutObject` with `If-None-Match:*`, supported `Content-MD5` and own
sha-256 metadata. disable hidden mutation retries; persist entry before io.
use transport bounds, no blunt outer write timeout. etag is not our sha-256.
[r2 compatibility](https://developers.cloudflare.com/r2/api/s3/api/).

confirm stored size/hash, then atomically mark ready and commit the original
action receipt when action-backed. recover receipts first. after interruption/
timeout, observe the same key at 0, 2 and 8 seconds, with 10-second read deadlines.
matching metadata proves the sole entered put completed; wrong metadata is
`StorageConflict`. negative head does not prove a timed-out put cannot still
commit. retain pending `CaptureUnresolved`, report it, and neither resubmit nor
delete that copy until reconciled. definite source/rejection failures are failed
and permit fresh capture. terminal action uncertainty remains non-retryable.

one private bucket has public domain/r2.dev and expiry lifecycle disabled;
bucket-scoped credentials remain application-only. r2 is private by default;
direct s3 operations are strongly consistent.
[private buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/),
[consistency](https://developers.cloudflare.com/r2/reference/consistency/).
no cloudflare worker, public listener, presigned links or binary git sync.

## capability contract

all inputs/results are closed and bounded, through existing dispatch/receipts.

retain selectors are `{kind: discord, message_id, attachment_id}` or
`{kind: gmail, message_id, part_id}`. ids are nonempty provider strings; gmail's
native root part id may be empty. the host supplies configured guild/channel,
verified account and discovered external attachment id to the stored source tuple.

| tool | input / result | authority |
| --- | --- | --- |
| `attachment.retain` | discovered discord/gmail source reference; result original snapshot/reference | automatic write; existing action position; no arbitrary url/native path |
| `attachment.open` | id; result snapshot/source plus verified local path | fresh automatic read; `Pending`, `Unavailable` or `Deleted` as appropriate |
| `attachment.delete` | target `{id, name, size_bytes, sha256}`; result id/deleted time/scope | consequential write; exact Approve/Deny |

snapshot is `{id, name, name_truncated, media_type, size_bytes, sha256}`. name
is a deterministic 240-byte utf-8-safe display preview, not a filesystem name.
delete validates its four target fields against the immutable copy before
proposal/execution; host approval shows those exact arguments. source refs use
the tuples above. retain errors include id when registered. typed codes:
`NotFound`, `TooLarge`, `SourceChanged`, `Unavailable`, `Pending`,
`CaptureUnresolved`, `StorageConflict`, `Deleting`, `Deleted`.

retain/delete use the current action recorder and immutable result receipt;
one mutation entry per copy/action, positive lifetime ceiling and explicit actual
provider attempts. source reads/recovery have separate operation bounds. replay
returns original evidence; fresh opens bypass cross-attempt disposable-path reuse.

open materializes in an app-owned, native-readable cache outside the notes repo
and credential directories; verify sha-256 before publishing the path. finish
database transactions during download; recheck state before cache publication
under the row lock shared with deletion. native main only reads original cache;
gitignored workspace scratch holds derivatives. no added writable native root.
after restart, open again; historical paths do not preserve native visual context.

delete requires ready or continuation of its original entered delete; unresolved
put yields `CaptureUnresolved`. latch deleting/delete-action id under existing
serial dispatch/row lock before remote delete. block capture/open/cache publication
for that id. remove r2 object and app-owned cached copies; confirm absence, then
commit deleted and original action receipt together. use the same bounded head
observations after ambiguity; uncertain deletion remains unavailable as deleting
for explicit repair, with no automatic repeat. retain the small metadata row.
source email/discord, native scratch/other copies, conversation and memory/notes
are not erased. promise no global forgetting or revocation.

repair is operator-only: inspect/purge this exact r2 key and app cache through
normal operator tools. add the narrow stopped-owner command
`jarvis attachment-reconcile <id>`: observe only, using the same metadata checks.
matching pending bytes may become ready; confirmed absent deleting bytes/cache
become deleted. absent uncertain uploads stay unresolved. commit the factual
state and required host notice together; preserve original action/reply evidence.
never reset ready, rerun the old mutation or claim manual cleanup proves the
original delete succeeded. no model-callable repair or general repair framework.

## reading and designer's content

reuse native image viewing/shell and established utilities for pdf text/page
rendering, text/csv and docx reading/conversion. qualify installed tools; write
no parser or mandatory reading script. main chooses ranges/commands. pixels or
base64 never enter callback json/action ledger/memory. extraction, ocr, renders
and summaries are derivatives, never replacements for original bytes.

infer useful handling; ask when materially different intentions remain plausible.
no compulsory summary/todo/expense. ground claims in the original and locator;
distinguish observed image features from interpretation. state illegible regions
and unread pages. extracted text does not establish figures/layout were examined.
preserve units/table structure/figure numbering; pdf and printed page numbers can
differ. document content grants no consent/approval; execute no embedded macros
or commands.

good: `the receipt shows 42.80; the currency is illegible. which currency?`
good: `pdf page 7 describes [...]; i have not inspected the figures or appendix.`
cite its original reference. no guessed expense or manufactured completion.

memory captures published answers/notes/callback references. main's native
extraction history remains internal; not every extracted word becomes searchable.
admitted worker/client histories keep ordinary capture rules. originals stay
reopenable; no extraction mirror/new memory schema. existing provider codec
repairs remain with their owner: [document content](issues/archive-document-content.md)
and [inline images](issues/archive-inline-images.md).

## implementation, handoffs and acceptance

| unit | exclusive files / owner | responsibility |
| --- | --- | --- |
| a: ingress/schema | jarvis `discord.py`, `messages.py`, `db.py`, migration | upload acceptance, immutable manifest/lineage, table/preparation readiness |
| b: source/storage | jarvis new `attachments.py`, `connectors.py` | shared store/state, exact fetch, sdk capture/reconciliation/cache |
| c: tools/composition/content | jarvis new `attachment_tools.py`; `actions.py`, read/write dispatch/policy, `tool_composition.py`, `native_runtime.py`, `definitions.py`, `service.py`, `cli.py`, `settings.py`, `session-compatibility.json` | callbacks/approvals/receipts, shared client/task, preparation wiring and designer instructions |
| d: host | dev-server configuration/dependencies | private bucket/scoped credential, read-only native cache access, gitignored scratch, qualified utilities |
| e: native prerequisite | kernel/provider agents via notes contract | borrowed workspace, built-ins with callbacks and actual image/page viewing; no attachment-specific wire redesign |
| f: temporary proofs | scoped proof files only | end-to-end/live evidence and designer review |

agree store/result interfaces before parallel edits; shared files have one owner.
use actual migration predecessor. hard-cut text-only owner rejection and old
unusable attachment metadata; adopt current schemas/role revision directly.
legacy accepted messages stay unchanged; no historical backfill, recreation of
deleted copies, url-only or local-only durable-storage fallback.

three temporary journeys suffice:

- real postgres/private test bucket/discord: attachment-only/multi-file intake,
  replay/restart, source disappearance/cold-cache reopen. crashes around upload/
  receipt, delayed put/negative head, deletion/cache races. prove bytes/hash,
  active-source uniqueness, no resurrection, exact approval and honest uncertainty;
  operator cleanup/reconciliation changes facts without replaying an old mutation.
- gmail synthetic fixtures: inline/external leaves, named text attachment,
  duplicate source, missing/wrong part/account, bounds and failed source. unopened
  mail remains uncopied; logs/context contain no credentials or capability urls.
- actual trusted main: receipt/scientific image, text/scanned multi-page pdf,
  docx/csv with existing utilities, a host callback and fresh-turn reopening.
  designer checks source citations, coverage/uncertainty and optional handling;
  no compulsory/fabricated work, budget ingestion or image-context replay claim.

record red, implement, get green, adversarially review boundaries, refactor
duplication and recheck changed concerns/final composition. record final-tree
integration/live evidence, delete temporary tests, run `scripts/verify`. no code,
live operations, provisioning or dependency change in this doc task.

trade-offs: indefinite copies grow storage; unopened gmail files can disappear.
100-mib copies exclude larger files; initial preparation can delay that input.
rare unknown uploads require repair before retry/deletion. deletion is scoped;
fresh capture can retain the source again. native reading fidelity depends on
tools/model; internal extracted text is not a search corpus. deleting temporary
tests removes their ongoing regression coverage.
