# adr 0101 — files in outgoing gmail

status — source, detached rehearsal and isolated connected-account acceptance passed. the [production cut and installed smoke](../issues/outgoing-mail-installed-cutover.md) are pending. this narrows the outgoing-file deferral in [0075](0075-v2-completion-and-subscription-model.md), amends the draft and recovery rules in spec §§5 and 9, and retains [0024’s creation-derived effect header](0024-use-a-stable-gmail-effect-header.md).

## what the owner can do

“send the pdf on my macbook to sam” and “reply with these two phone uploads” end in ordinary chat. jarvis obtains the files, saves an unsent gmail draft and presents its contents when fresh consent is needed. the owner can revise or approve it in web or mobile chat. after gmail draft readback verifies the bytes the source may go offline. a worker can already copy a readable file from a reachable machine using skid and ordinary ssh/scp. the macbook → dev-server direction passed a 4,096-byte hash check. arch was unavailable. permissions, connectivity and direction still apply. an unavailable arch machine earns “i couldn’t reach arch. reconnect it or upload the file here.”

reuse the web uploader, private originals, worker, gmail session and conversational approval. scope covers regular attachments in new messages and replies from the configured account. public links, a fleet file service, permanent storage of native exports, gmail rich editing, arbitrary gmail drafts, sender aliases and new approval controls are outside this cut.

## a. getting the bytes

the source designer’s “ready to attach `analysis.pdf` (42,016 bytes)” requires a complete verified copy. on failure give the machine, file, cause and one recovery.

- **web uploads and retained gmail files.** accept a ready attachment uuid. read its complete stored filename, media type, measured size and sha-256. reject an excessive total before fetching. copy a verified cache entry. on a cache miss return `OriginalNeedsOpen{ids:[uuid]}` before action insertion. main uses the existing journaled `attachment.open` and retries. this preserves r2 read accounting.
- **native files.** a remote worker uses existing scp into a request-private 0700 directory under `/var/lib/jarvis-notes/.git/jarvis-mail/incoming` on dev-server. compare the source size/hash with the published copy. on dev-server the native identity runs the selected release’s `deploy/jarvis-mail-file prepare PATH [--name NAME]`. bounded-copy one regular file. publish `<uuid>/{original,manifest.json}` under the same mail root. manifest = `{id,filename,media_type,size_bytes,sha256}`. return `{ref:{kind:"native",id,manifest_sha256},file}` using the digest of the manifest bytes. reuse native owner, `codex-clients` group and 0750/0640 modes. fsync files and directory, rename the private temporary sibling, fsync parent. remove only the transfer copy. the installer creates the directories and installs an age-only tmpfiles `e` rule. the system cleanup timer reaps abandoned incoming copies and publications eligible after 24 hours. [native publication](0087-private-web-home.md#authored-canvas)
- **admission.** check owner, request replay and unknown-effect barrier before reading sources. use pinned directory descriptors, fixed uuid/leaf names, no symlinks and regular single-link files. validate the complete native manifest (4 kib maximum) and its digest. hash and count the actual stream into `/var/lib/jarvis/mail-stage/<action-uuid>/<slot>`, owned by jarvis, 0700/0600. fsync bytes, directories and parent. recheck admission and cancellation at the atomic action/invocation insert. any failure stops the whole draft before a gmail write. return `FileUnavailable{slot,reason}` using the original’s existing failure or `native_missing|invalid_name|digest_mismatch|local_io|secret`. `MailLimit{measure,actual,maximum}` names the failed count or byte limit.

**secret check before insert.** keep `contains_secret` for small arguments and filenames. inspect one size-verified staged file at a time, off the event loop under a 60-second aggregate intake deadline. search its literal bytes for configured secret bytes. scan one bounded utf-8 view (replace invalid sequences) using the shared marker expression as a case-insensitive pattern string with the pinned pydantic-core `rust-regex` engine and boolean `SchemaValidator.isinstance_python`. a whole-file view covers markers across read chunks. release bytes and text before the next slot. file inspection performs zero url-decoding passes and retains no alternate representations. reject a match as `FileUnavailable{slot,reason:"secret"}`. timeout or scan failure rejects the draft. log only the slot/reason. the cost is one bounded file view and possible plaintext false positives. encoded, archived and encrypted secrets are outside this literal check. [pydantic regex contract](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.regex_engine)

replay the recorded action before restaging. reverify slots after restart. retain them while the action can use them, delete a rejected insert’s slots immediately, clean on settlement, and sweep orphans under sole-writer startup ownership before dispatch. an entered mutation requires reconciliation. file fields in mail journals and memory contain refs/descriptors. ordinary chat and native history keep their existing capture rules.

## b. composing a gmail revision

the draft designer owns these closed schemas and their content. preserve the ordinary `ActionRequest{request_ref,existing_action_ref,arguments}` and `GmailContent` text/envelope fields. new required fields are explicit, including empty arrays and nulls.

```text
new_file      = {kind:"original",id:uuid} | {kind:"native",id:uuid,manifest_sha256:hex64}
update_file   = new_file | {kind:"existing",existing_part:positive_integer}
file          = {filename,media_type,size_bytes,sha256:hex64}
create_draft  = {content:GmailContent,files:[new_file]}
update_draft  = {draft_ref:uuid,replacement:GmailContent,files:null|[update_file]}
send_draft    = {draft_ref:uuid}
snapshot      = {from,to,cc,bcc,subject,body_text,in_reply_to,references,files:[file]}
revision      = {account,draft_id,thread_id,message_id,jarvis_effect_id,content_digest}
draft_success = {state:"draft",draft_ref:uuid,revision,in_reply_to,references,files:[file],observed_at}
              | {state:"already_sent",draft_ref:null,sent:GmailSendDraftSuccess,files:[file],observed_at}
```

the owner selected the retained-file discriminator during implementation. the pinned tool-schema compiler requires a common literal field on object alternatives.

a `draft_ref` is a verified current-format create/update action uuid in this account. it works across turns. `existing_action_ref` replays the original request. resolve the creation lineage and its stable effect marker from trusted receipts. retain the exact submitted arguments and their digest. add one typed `execution_contract.mail` member. compose freezes the creation action id, optional base revision and ordered source slots/manifests. send freezes the creation id, verified revision and complete snapshot. no new table or column.

create with `[]` for text alone. update with `null` preserves ordered files, `[]` clears them, and an array declares the final order. old slot 1 is the first file in that revision. reject missing or repeated old slots. preserve duplicate names and multiplicity. the draft designer’s “replaced `results.csv` and kept `methods.pdf`” requires verified readback. accept zero bytes and complete unicode basenames up to 255 utf-8 bytes. reject controls, separators and dot entries. ask for a named copy if needed. unknown or composite media types use `application/octet-stream`. report gmail’s file-policy rejection. [provider restrictions](https://support.google.com/mail/answer/6590?hl=en)

**mime.** one standard-library codec handles a utf-8 plain body, or multipart/mixed with that body first and ordered attachment leaves. reject inline/html, ambiguous mime or routing headers, sender overrides and unsupported structure. write exactly one `From` mailbox using the primary address verified by the account profile. at draft readback, preflight and sent-message verification require exactly that addr-spec, ignoring display name. `snapshot.from` contains only that normalized bare address. reject a different `Sender`, send-as alias or routing override. canonical digest = sha-256 of the snapshot’s sorted compact utf-8 json. preserve mailbox order, all to/cc/bcc, decoded filenames, media types and hashes, and body whitespace including the final newline. normalize body crlf/cr to lf. transport folding, date, outer message-id, encoding and boundaries may change.

**write.** in the metered executor verify account, parent provider id and thread. request `Message-ID`, `References` and `Subject` in the reply parent’s metadata. compare decoded subjects after stripping leading case-insensitive `re:` prefixes and following spaces. require the remainder to match exactly and send the selected subject verbatim. take the parent references chain and append its id once. update keeps the base thread and parent. reopen its exact draft message id, marker and digest before retaining old parts. identical desired content earns “already matches” on that verified revision. before mutation freeze the resulting account, exact old revision and desired snapshot once in the existing action result’s reconciliation basis. latch any definite write acknowledgement and ids there. confirm a write by raw readback of the desired snapshot, draft id and thread. confirm a newly allocated thread from the provider response or recovery. a changed/unreadable readback enters reconciliation. reconstruct settled snapshots from the source action’s text/envelope, verified reply headers and files. [thread requirements](https://developers.google.com/workspace/gmail/api/guides/threads#add_drafts_and_messages_to_threads)

**recover.** ambiguous create uses three observations of at most five unfiltered pages × eight drafts. get listed message metadata with only the marker header. raw-get only a matching draft and cross-check both identities. one verified match with no observed duplicate/conflict proves creation. zero never authorizes another create. a replacement requires a different message id and exact desired content. only three full observations of the intact old id/content may prove an unacknowledged update absent. if the draft disappeared, c’s verified sent evidence earns `already_sent`, which cannot be used as a draft. a recorded write acknowledgement precludes an absence retry.

## c. approval, send and recovery

**owner copy.** render the frozen action’s subject, every to/cc/bcc, ordered filenames, sizes and total as text. distinguish same-name entries by slot and, for equal sizes, digest suffix. “read email” retrieves `proposal.mail_body` through the existing single-message endpoint. omit the body from list polls. “send ‘results’ to sam@example.org with `analysis.pdf` (42,016 bytes)?” uses ordinary chat and `approval.respond`. clear prior owner consent covering that snapshot suffices. display its manifest and receipt on the cited owner message. if the file or recipient choice is unresolved, ask first. distinguish saved unsent, awaiting approval, denied, sent and unknown. “gmail didn’t confirm whether it sent. check sent mail before trying again.” [conversational proposals](0097-todo-home.md#b-conversation-references-and-authority)

**send.** in the proposal-insert transaction lock the creation action and check for pending, entered, uncertain or successful sends of this draft across requests. surface the existing proposal or outcome. denial permits a fresh proposal. after approval verify account, draft id, message id, thread, marker and digest. on an observed edit, stop. the owner may finish in gmail or request a fresh draft from available verified inputs. rebuild using approved fields and the verified file bytes held by this read. gmail has no conditional update/send. a simultaneous edit after preflight can be overwritten or consumed. the approved message is what leaves. [gmail draft semantics](https://developers.google.com/workspace/gmail/api/guides/drafts#send_drafts)

use one multipart media request for every write. at the method’s `/upload/gmail/v1/users/{account}/drafts…?uploadType=multipart` endpoint send json draft metadata followed by the complete `message/rfc822` bytes. create omits id, replies carry their thread, update addresses the base id. send to `drafts/send` with `{id,message:{threadId}}` plus the approved mime, including text-only. require returned new message id, expected thread, `SENT` and no `DRAFT` for direct success. gmail consumes the draft and creates a new sent message. “sent” means gmail accepted it. [gmail media upload](https://developers.google.com/workspace/gmail/api/guides/uploads#multipart_upload) · [draft send endpoint](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/send)

**lost acknowledgement.** inspect the account-bound draft and known thread at 0/2/8-second backoffs. `threads.get(format=metadata,metadataHeaders=X-Jarvis-Effect-ID)` projects ids, labels and marker. inspect the first 100 returned messages without assuming priority. raw-get only an eligible match. finish the selected slice. one unique exact marker, expected thread, new id, message-level `SENT` without `DRAFT` and matching decoded snapshot proves sending. a tail permits positive proof only. a sole `DRAFT` with failed draft lookup cannot establish a send. an expected draft may coexist with positive sent evidence. an extra marked draft, two eligible sent ids, ambiguous labels or conflicting content latch a conflict across rounds. missing bcc evidence cannot prove a matching bcc envelope. malformed/incomplete observations preclude absence. preserve the nullable echo-account rule only for independently proved success. only three complete conflict-free observations of the intact draft and no sent match may authorize a fresh preflight and repeat within remaining authority. otherwise record uncertainty. for later evidence the stopped operator runs `jarvis gmail-send-reconcile ACTION_UUID` on one current-format uncertain send. reuse deployment ownership, the same reads and locked action settlement. record success on positive proof or failure on proved absence, preserving the original invocation receipt. inconclusive evidence leaves uncertainty. this command has no gmail mutation or requeue path. [thread metadata](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get)

**limits.** 0–10 files, **25,000,000 decoded bytes combined**. cap serialized mime at 36,700,160 bytes, the complete multipart request at 36 mib, selected raw-json responses at 48 mib and metadata at 2 mib. filter raw responses to identifiers, labels and raw. count real bytes, check outbound lengths before mutation, preserve short-header bounds. use one gmail write policy for connector, grants and recovery. allow 180 seconds per direct operation or recovery and 320 mib cumulative recovery traffic. each exchange gets the lesser of 60 seconds and the remaining deadline. reserve no further mutation after deadline. cap direct attempts at 12 including refreshes across at most two executor entries. source reads use a’s separate grant. budget streamed bytes and time even on failure. measure peak memory and elapsed time. if the target cannot send **and** recover, bring the measured lower ceiling and cause to the owner before changing the promise. [account limit](https://support.google.com/mail/answer/6584?hl=en) · [gmail discovery](https://gmail.googleapis.com/$discovery/rest?version=v1)

## delivery and acceptance

| exclusive implementer | files and discriminating proof |
| --- | --- |
| a · file intake | new `src/jarvis/mail_files.py`, `deploy/jarvis-mail-file`, `attachments.py`, `read_dispatch.py` for the shared marker definition, installer `deploy/install-contained-host` and its tmpfiles rule. reuse the existing store and descriptor helpers in `home_uploads.py`. prove phone upload and actual macbook worker/scp handoff. a synthetic credential spanning read chunks fails before insert under any filename. measure peak rss and elapsed time for a 25,000,000-byte binary and a nested-percent fixture. assert bounded inspection and exact bytes. replace input with same-length bytes, deny access, break the second file, restart after staging and sweep an abandoned slot. prove all-or-nothing and exact digests. |
| b · gmail drafts | `src/jarvis/write_tools.py` owns all three public schemas. new `gmail_drafts.py` owns shared mime, verified revision loading, draft writes and their recovery. prove text-only, unicode/empty/same-name parts, body-only edit, reorder/remove, reply thread, bcc and the 12,000-byte regression. reject a stale revision, wrong sender, changed byte and unsupported gmail edit. |
| c · send and owner copy | new `src/jarvis/gmail_send.py` consumes b’s revision reader/renderer. own `home_reads.py`, `static/home/home.js` and `write_policy.py` for the existing conversational proposal. prove denial, scoped prior consent, drift before/after check, dropped send acknowledgement, 429 plus a sole draft, duplicate sent markers and restart. prove correct recipients/bytes or an explicit unresolved outcome. |
| integration lead | sole editor of shared `actions.py`, `write_dispatch.py`, `write_connectors.py`, `tool_composition.py`, `definitions.py`, `service.py`, `cli.py`, `session-compatibility.json` and release verification. wire a → b → c and the stopped reconciliation command at their normal entry points. rotate affected tool/implementation/policy/plan and main binding revisions. remove the old text-only serializer/parser, id-only send, model-authored send basis, raw-string cap on mime, full-raw thread fanout and retired executable codecs. leave shared calendar/metadata limits intact. |

each designer freezes good and bad content examples before red. independent claude opus reviews each feature’s red, green and refactored evidence. write temporary end-to-end tests through normal chat, native, postgres and gmail. reproduce red on the predecessor, implement, pass, simplify, rerun. use deterministic provider faults for timing, distinct recipients and bcc. run the detached macbook rehearsal through dev-server’s `scripts/rehearse-worktree`.

**live acceptance.** use isolated state and one authorized mailbox actor. address mail only to the connected account itself with subject `[jarvis attachment test <run-id>]`. approve on the actual phone after the temporary source copies have gone. interpose a distinct, self-addressed edit between preflight and the real send. use an independent gmail reader to download/hash the received attachments and compare from/to/cc/bcc, approved text, thread and sent id. self-mail can be one message carrying both `SENT` and `INBOX`. this proves this account’s stored delivery. use a self-bcc’d reply in that thread for lost-ack recovery at exactly 25,000,000 bytes. reject 25,000,001 bytes and an eleventh file before mutation. retain the thread and near-limit file for inspection. record red/green/refactor results, message ids, digests, timings and peak service memory outside scratch. reopen and hash the evidence. delete the new probes and test fixtures after final green. report cleanup separately. installed smoke has its own receipt.

**hard cut.** pause admission, cancel unentered old proposals through existing controls and wait for entered calls to quiesce. the old result does not distinguish direct from recovered success. in a stopped, read-only cutover check, look up every old successful send’s recorded message id in its account. a missing/unreadable id, thread mismatch, missing `SENT`, present `DRAFT` or contrary evidence disputes the outcome. inspect disputed and entered/uncertain sends with c’s positive or complete absence evidence, using the old captured envelope. record the owner’s evidence and disposition in the cut receipt, preserving the original action history. the audit never invokes the old executor. an old send of genuinely unknown outcome holds the entire jarvis mail cut, including unrelated mail, until the owner resolves it. gmail remains available manually. require zero incompatible unfinished actions before replacement. preserve terminal receipts with their original certainty, classified before payload decoding. old drafts stay in gmail for manual use. a fresh jarvis draft starts a new verified lineage. old approvals never execute on the new binding.

## implementation evidence

the exact `7220123ec9ea8621ee23f78f211ed86693dc829b` source passed the
detached macbook rehearsal. `detached-final-7220123/receipt.json`
records exit 0 and checkout removal in the private adr 0101 evidence directory.
its reopened `checks.log` has sha-256
`3d53570893811fa39449d25de72b85f5f02bb8b488c368c1802b829eec4c5aa5`.
it covers build and static checks, the home http projection, native journal
and postgres 0020 approval, provider fault injection, 25,000,000-byte multipart
send and recovery, the cut audit and bounded intake. 25,000,001 bytes and an
eleventh file fail before a gmail write. a sole `DRAFT` after a 429 never
proves sending. the admitted 12,000-byte body round-trips through the mail codec.

opus found lossy headers that could leave an unverifiable draft. the shared
header round trip now rejects them before a write and rfc 2231 filenames keep
literal encoded-word text. the probe killed all 13 targeted mutations. the
exact regex runs in one short-lived process per staged file so the service loop
can continue while it scans. at the byte ceiling, the final detached intake
took 4.95 seconds and the maximum sampled home read was 19.4 ms. peak scanner
rss was 248,332,288 bytes. format controls that can disguise filenames are
refused.

the isolated installed-style candidate passed publication and cross-identity
readback of both native fixtures and completed a real native turn. its first
startup exceeded the existing main prompt bound. placing attachment guidance
with the mail tools preserved the bound and repaired startup. independent opus
accepted the technical implementation and startup delta. live gmail profile
and primary send-as reads confirmed the account and the absence of a configured
primary reply-to.

the live candidate at `7220123ec9ea8621ee23f78f211ed86693dc829b` saved
`[jarvis attachment test a101phone]` as an unsent self-addressed gmail draft.
an independent raw read verified the exact 25,000,000-byte binary against the
macbook sha-256. gmail stored 34,211,513 mime bytes and returned 45,615,526
bytes of projected raw json. the service peaked at 676,319,232 bytes with a
3 gib limit. three complete observations of the same intact draft proved
send absence in 29.80 seconds. the raw receipts are `a101phone-live-draft.txt` and
`a101phone-intact-draft-recovery.txt` in the private evidence directory.

the owner uploaded the jpg from a physical phone and approved in chat after
the temporary source copies disappeared. an initial fixture failed before
provider entry. the owner authorized one send of the unchanged draft. a real
gmail edit between preflight and send created a different draft message id
and content digest. gmail sent the approved message in one entry. an independent
raw gmail read verified both attachments, all recipients and the approved body
in message `1a20ba09890d8155`, labeled `SENT` and `INBOX` in thread
`1a20b8ede92f1eed`. the reopened `a101phone-initial-send.txt` receipt has sha-256
`8f7e91b43970532d3b7cc6765dd31775de561de990914e87551d8e923a0b5bd3`.

the owner separately approved the self-bcc reply from the same phone after
the temporary full-size source publication disappeared. the wire fixture
discarded gmail’s http 200 acknowledgement after recording it. jarvis recovered
the success in one executor entry, 37.67 seconds after approval, about nine
seconds after gmail responded. an independent gmail reader and mime parser
verified the parent, thread, from, to, cc, bcc, subject, body and all
25,000,000 file bytes in the new `SENT` and `INBOX` message
`1a20ba886aed74a1`. the request used 34,211,475 mime bytes and 34,211,763
multipart bytes. peak service memory was 778,285,056 bytes against 3 gib.
the reopened `a101phone-fullsize-reply.txt` receipt has sha-256
`4f00a312077d8e3ad1720380c02471fb6e486e078dcc30d9cc644d3a27718da1`.

the original production release and home socket were restored and the
deployment lock handed back to the adr 0098 operator. the test thread and
full-size macbook file remain for inspection. cleanup removed the extra
unsent draft, temporary r2 original, isolated host runtime and postgres
database. the temporary integration and live probes were deleted after green. the
[earlier detached checkout residue](../issues/outgoing-mail-rehearsal-residue.md)
is tracked separately.
