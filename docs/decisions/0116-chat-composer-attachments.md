# adr 0116. attach files to the open chat draft

**implemented. source and isolated acceptance passed. installation pending.**

the owner wants to paste a screenshot while writing to jarvis and drag a file
already in hand into the same message. today the web picker owns the bytes
and a second selection replaces the first. on android, sharing from another
app creates a new draft. the server already accepts a captionless message
with ordered files. this decision extends the two composers. [web composer](../../src/jarvis/static/home/home.js) · [android drafts](../../android/app/src/main/java/dev/niels/jarvis/Drafts.kt) · [submission contract](0087-private-web-home.md#web-interface)

## what the owner sees

| action | result |
| --- | --- |
| drop files anywhere on the web composer | the composer highlights while an eligible drag is over it. dropping appends the files in source order. leaving or cancelling clears the highlight. the canvas and conversation history keep their own interactions. |
| paste into the message field | a screenshot appears beside the caption. other files work when the browser or phone supplies their bytes or a readable local content uri. text and links paste at the current selection with normal undo. a url alone stays text. |
| choose **attach** on web, paste again, or drop another file | append after the existing files. preserve the caption and discussion reference. equal names are allowed. each entry has its filename and an accessible remove button. a small local thumbnail distinguishes screenshots. if preview fails, the filename still works. |
| paste from the android keyboard or drop onto the message field from another app in split screen | add to the open editable draft through the same receiver. android may move the caret to the drop point. the android sharesheet still starts its own draft, including when another draft is open. |
| send | allow files with an empty caption. only explicit send transmits bytes. removing a file before send leaves the others in order. |

handle the paste delivered by the platform. when a web paste offers both files
and alternative text or html, stage the files once. keep the caption and its
selection even if the batch is rejected. a copied spreadsheet range offered as
both a file and text follows this rule. a text/html paste without files gets
ordinary text-field behavior.
on android, consume each accepted file item once and pass separate text items
to the editor. never fetch a pasted link or parse html to find an image.
use the supplied filename, or assign one when staging unnamed bytes, such as
`pasted image.png` for a png. retain that name through retry. [clipboard formats](https://www.w3.org/TR/clipboard-apis/#mandatory-data-types)

the existing limits allow ten files, 16 kib of utf-8 caption and 90 mib for
the encoded request including multipart overhead. if a batch added to an open
composer would exceed the file count or known byte limit, reject that
addition as a unit and say why beside the attachments. keep the previous
draft editable. a later file-read or encoding error identifies what the owner
can remove or retry. the server measures the final request. [upload limits](0087-private-web-home.md#originals)

## web

the tab owns one ordered list of attachment entries. each pairs the existing
draft descriptor with its live `File` when available. take the files from the
picker, drop or paste event while handling it. render, remove, hash and build
multipart from that same list. keep the picker keyboard-accessible and reset
its selection after consuming it so choosing the same file again works.
scope file-drop handling to the composer and file paste to the message field.
draw a locally decoded raster to a small canvas under the shell's existing
content security policy. release preview resources on removal or draft clearance.

persist only the existing per-tab draft metadata. after reload, label files
whose bytes must be supplied again. in an editable draft, let the owner
reselect or remove each missing entry before send. an
uncertain send first checks its receipt. while checking or sending, freeze the
draft. a missing receipt leaves delivery unknown. the three inputs can now
restore bytes to missing slots by measured size and digest, filling the first
matching empty slot for duplicates. retry is explicit and sends the original
submission id, text, ref, ordered names and bytes, even if a re-supplied file
has a different name on disk. older uncertain drafts without digests remain
receipt-only. if the original is lost, offer to open an empty draft in an
independent tab without an opener. explain that the earlier message may still
arrive. the original tab keeps checking its receipt. clear only the draft that
owns a confirmed receipt. [replay identity](0087-private-web-home.md#conversation-records-and-decisions)

## android

use the shared `DraftComposer` with a state-based text field and compose's
`contentReceiver` for clipboard, keyboard and cross-app drops. consume a
`content://` item while its read grant is valid. retain the delivered grant
with the queued copy until the stream has been read. reuse the bounded private
copy, digest and atomic draft manifest in `Drafts`. the sharesheet's
new-draft entry point retains 0105's per-item errors and removable incomplete
slots. the composer's append operation reuses its byte copy.
plain text pasted into the field is owner text. text shared *to* jarvis through
the sharesheet remains a removable original under 0105. [composer](../../android/app/src/main/java/dev/niels/jarvis/ShareActivity.kt) · [compose receiver](https://developer.android.com/reference/kotlin/androidx/compose/foundation/content/contentReceiver.modifier) · [phone draft contract](0105-native-android.md#b-capture-and-submission)

copy off the ui thread into private staging. show “adding files” and keep the
editor usable. disable send and discard during copy. back or “save and return”
leaves after the files and current caption are saved. a copy failure keeps the
draft open with the error. sending still requires an explicit tap. enforce
edit, send and discard ordering in the draft store as well as the controls.

publish the whole addition to the same editable draft after all copies finish.
preserve the latest caption, ref and earlier files. serialize additions in
gesture order. allocate slots independently of list length so removing a middle
entry cannot overwrite a surviving original. loss of a grant, low space or
interruption leaves the previous manifest usable. name a failed copy and let
the owner add it again. on restart reclaim staged bytes and any slot files
absent from a successfully recovered manifest. once shown as saved, files
survive process death and the loss of the grant. the existing frozen
submission owns its exact bytes through retry.

## acceptance

1. on macbook, paste a real screenshot, drop two files from finder, then use
   the picker. remove the middle file and add one with the same name. check
   the draft thumbnail and verify the caption, file order and original bytes
   after receipt. paste text and a url over selected text and undo. try a
   file-bearing paste with a text alternative at the file limit. check the
   original selection. cancel a drag. observe that staging makes no upload
   and a screenshot alone sends successfully.
2. with an isolated service, exercise the eleventh file and a request that
   exceeds the limit only after encoding. lose the send response. reload and
   recover the existing receipt without reselecting. separately, with no
   receipt, re-supply files from mixed gestures. reject changed bytes with the
   same name and size. matching bytes under a different name replay with the
   original name. exact retry yields one owner message. lose a clipboard-only
   original on reload and open an empty draft while its receipt is unresolved.
3. on the s22+, paste a screenshot from a keyboard or clipboard that supplies
   it, and drop a file from split screen into a draft that already has text.
   remove a middle attachment and append again. reopen after process death
   and send the same private bytes. check ordinary text paste and a new
   sharesheet draft. in an isolated android run try send and back
   during copy. interrupt an append after bytes are installed but before the
   manifest commits. verify the earlier files and caption survive and the
   orphaned bytes are reclaimed. record which device, source app and keyboard
   delivered each gesture.

the packaged web shell and android app can ship independently against the
existing api. existing drafts, receipts and server records keep their formats.
the [roadmap](../implementation-plan.md#chat-composer-attachments) owns delivery order.

## implementation evidence · november 26, 2026

the predecessor failed native screenshot paste on both clients. the web
checks used chrome 158 on macbook and an independently rebuilt wheel at
`b9cc977` against postgres 16.12, schema `0025`, before integration with
the [bare-domain navigation change](0115-web-home-address.md). browser
probes also passed in chromium and webkit.
the macbook journey used a screenshot of the rendered composer on the macos
clipboard and two files from finder. finder cancellation cleared the
highlight on the browser's terminal dragleave. both the ordered upload and
the captionless screenshot returned receipts. independent reads compared
the downloaded bytes to the delivered clipboard and finder files.

the isolated service accepted ordered uploads once, rejected an eleventh
file and multipart overhead beyond 90 mib, recovered a committed send after
losing its response, and replayed a separate unconfirmed send with the
original names and digests. a rejected later attempt preserved the unresolved
original. an independent tab kept its own draft while the old tab recovered.
the fixture used the actual upload route and database, with a local object
sink.

the galaxy s22+ (`sm-s906w`, android 16) received a gboard screenshot from a
separate fixture app. an in-place candidate upgrade kept its private bytes.
the final candidate accepted split-screen drops from that app, removed a
middle file, appended again, pasted ordinary text and opened a separate
sharesheet draft. it reopened the original under a new process and sent the
same private bytes. the isolated handset build used a separate package and
loopback endpoint. the normal android debug build used the same product
sources. the owner waived the talkback check and the prior device setting
was restored.

on the emulator, suspending the old removal path let a subsequent send
include the removed original. the repair waits for the earlier edit; the
same fault run admitted only the remaining files. a separate kill between
slot installation and manifest publication retained the prior caption and
files and reclaimed the interrupted bytes. the probes also exercised
ordered additions, a failed batch, and send and back during a copy.

evidence was reopened and hashed under
`~/.local/state/jarvis/qualification/adr0116/`. see
`web-green-b9cc977-r2/receipt.json`, `web-browser-evidence.json`,
`mac-native-green.json`, `android/android-evidence.json`,
`phone-final-gestures.json`, `phone-final-send.json` and the independent
database and download comparison in `physical-fixture-final.json`.
teardown receipts cover the service fixture, emulator and handset.
docker desktop still holds a read-only descriptor on one failed setup
checkout. it contains no feature probes.
